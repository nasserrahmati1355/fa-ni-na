#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

if [[ "$#" -ne 5 ]]; then
    echo "Usage: $0 DOMAIN BASIC_USER BASIC_PASSWORD_FILE APP_USER APP_PASSWORD_FILE" >&2
    exit 64
fi

DOMAIN="$1"
BASIC_USER="$2"
BASIC_PASSWORD_FILE="$3"
APP_USER="$4"
APP_PASSWORD_FILE="$5"

for required_file in "$BASIC_PASSWORD_FILE" "$APP_PASSWORD_FILE"; do
    if [[ ! -s "$required_file" ]]; then
        echo "ERROR: Required credential file is missing or empty: $required_file" >&2
        exit 66
    fi
done

for required_command in curl python3; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "ERROR: Required command is unavailable: $required_command" >&2
        exit 69
    fi
done

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

NETRC_FILE="$WORK_DIR/netrc"
COOKIE_JAR="$WORK_DIR/cookies.txt"
LOGIN_HTML="$WORK_DIR/login.html"
LOGIN_FORM="$WORK_DIR/login-form.txt"
LOGIN_HEADERS="$WORK_DIR/login-headers.txt"
LOGIN_RESPONSE="$WORK_DIR/login-response.html"
DASHBOARD_HEADERS="$WORK_DIR/dashboard-headers.txt"
DASHBOARD_HTML="$WORK_DIR/dashboard.html"
LOGOUT_FORM="$WORK_DIR/logout-form.txt"
LOGOUT_HEADERS="$WORK_DIR/logout-headers.txt"
POST_LOGOUT_HEADERS="$WORK_DIR/post-logout-headers.txt"

BASIC_PASSWORD="$(tr -d '\r\n' < "$BASIC_PASSWORD_FILE")"
printf 'machine %s\nlogin %s\npassword %s\n' \
    "$DOMAIN" "$BASIC_USER" "$BASIC_PASSWORD" > "$NETRC_FILE"
unset BASIC_PASSWORD
chmod 600 "$NETRC_FILE"

touch "$COOKIE_JAR"
chmod 600 "$COOKIE_JAR"

CURL_COMMON=(
    --silent
    --show-error
    --connect-timeout 10
    --max-time 60
    --header 'Cache-Control: no-cache'
    --header 'Pragma: no-cache'
)

NOAUTH_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --output /dev/null \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login?outer_check=$(date +%s%N)"
)"

if [[ "$NOAUTH_STATUS" != "401" ]]; then
    echo "ERROR: Expected Nginx Basic Auth status 401, received $NOAUTH_STATUS." >&2
    exit 1
fi

LOGIN_GET_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --netrc-file "$NETRC_FILE" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --output "$LOGIN_HTML" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login?login_check=$(date +%s%N)"
)"

if [[ "$LOGIN_GET_STATUS" != "200" ]]; then
    echo "ERROR: Expected GET /login status 200, received $LOGIN_GET_STATUS." >&2
    exit 1
fi

CSRF_TOKEN="$(python3 - "$LOGIN_HTML" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import sys


class CsrfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token = None

    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:
        if tag.casefold() != "input" or self.token is not None:
            return

        values = dict(attrs)
        if values.get("name") == "csrf_token" and values.get("value"):
            self.token = str(values["value"])


parser = CsrfParser()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))

if not parser.token:
    raise SystemExit("CSRF token was not found in the login page.")

print(parser.token)
PY
)"

python3 - "$LOGIN_FORM" "$APP_USER" "$APP_PASSWORD_FILE" "$CSRF_TOKEN" <<'PY'
from pathlib import Path
import sys
from urllib.parse import urlencode

output_path = Path(sys.argv[1])
username = sys.argv[2]
password = Path(sys.argv[3]).read_text(encoding="utf-8").strip()
csrf_token = sys.argv[4]

output_path.write_text(
    urlencode(
        {
            "username": username,
            "password": password,
            "csrf_token": csrf_token,
            "next": "/",
        }
    ),
    encoding="utf-8",
)
PY

LOGIN_POST_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --netrc-file "$NETRC_FILE" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --request POST \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --header "Origin: https://${DOMAIN}" \
        --referer "https://${DOMAIN}/login" \
        --data-binary "@$LOGIN_FORM" \
        --dump-header "$LOGIN_HEADERS" \
        --output "$LOGIN_RESPONSE" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login"
)"

case "$LOGIN_POST_STATUS" in
    302|303)
        ;;
    *)
        echo "ERROR: Expected POST /login status 302 or 303, received $LOGIN_POST_STATUS." >&2
        exit 1
        ;;
esac

COOKIE_NAMES="$(
    awk \
        'NF >= 7 && ($1 !~ /^#/ || $1 ~ /^#HttpOnly_/) {print $6}' \
        "$COOKIE_JAR" |
    sort -u |
    paste -sd, -
)"

if ! awk \
    'NF >= 7 && ($1 !~ /^#/ || $1 ~ /^#HttpOnly_/) && $6 == "nhref_session" {found=1} END {exit !found}' \
    "$COOKIE_JAR"
then
    echo "ERROR: Flask session cookie was not stored. Cookie names: ${COOKIE_NAMES:-none}." >&2
    exit 1
fi

DASHBOARD_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --netrc-file "$NETRC_FILE" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --dump-header "$DASHBOARD_HEADERS" \
        --output "$DASHBOARD_HTML" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/?dashboard_check=$(date +%s%N)"
)"

if [[ "$DASHBOARD_STATUS" != "200" ]]; then
    DASHBOARD_LOCATION="$(
        awk \
            'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, ""); print $2}' \
            "$DASHBOARD_HEADERS" |
        tail -n 1
    )"

    echo "ERROR: Expected dashboard status 200, received $DASHBOARD_STATUS; location=${DASHBOARD_LOCATION:-none}." >&2
    exit 1
fi

grep -Fq 'SEO Auditor' "$DASHBOARD_HTML" || {
    echo "ERROR: SEO Auditor marker is missing from the dashboard." >&2
    exit 1
}

grep -Fq "$APP_USER" "$DASHBOARD_HTML" || {
    echo "ERROR: Authenticated username marker is missing from the dashboard." >&2
    exit 1
}

grep -Fq 'خروج' "$DASHBOARD_HTML" || {
    echo "ERROR: Logout marker is missing from the dashboard." >&2
    exit 1
}

LOGOUT_CSRF_TOKEN="$(python3 - "$DASHBOARD_HTML" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import sys


class CsrfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token = None

    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:
        if tag.casefold() != "input" or self.token is not None:
            return

        values = dict(attrs)
        if values.get("name") == "csrf_token" and values.get("value"):
            self.token = str(values["value"])


parser = CsrfParser()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))

if not parser.token:
    raise SystemExit("CSRF token was not found in the dashboard.")

print(parser.token)
PY
)"

python3 - "$LOGOUT_FORM" "$LOGOUT_CSRF_TOKEN" <<'PY'
from pathlib import Path
import sys
from urllib.parse import urlencode

Path(sys.argv[1]).write_text(
    urlencode({"csrf_token": sys.argv[2]}),
    encoding="utf-8",
)
PY

LOGOUT_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --netrc-file "$NETRC_FILE" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --request POST \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --header "Origin: https://${DOMAIN}" \
        --referer "https://${DOMAIN}/" \
        --data-binary "@$LOGOUT_FORM" \
        --dump-header "$LOGOUT_HEADERS" \
        --output /dev/null \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/logout"
)"

case "$LOGOUT_STATUS" in
    302|303)
        ;;
    *)
        echo "ERROR: Expected POST /logout status 302 or 303, received $LOGOUT_STATUS." >&2
        exit 1
        ;;
esac

POST_LOGOUT_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --netrc-file "$NETRC_FILE" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --dump-header "$POST_LOGOUT_HEADERS" \
        --output /dev/null \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/"
)"

POST_LOGOUT_LOCATION="$(
    awk \
        'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, ""); print $2}' \
        "$POST_LOGOUT_HEADERS" |
    tail -n 1
)"

if [[ "$POST_LOGOUT_STATUS" != "302" && "$POST_LOGOUT_STATUS" != "303" ]]; then
    echo "ERROR: Expected post-logout redirect, received $POST_LOGOUT_STATUS." >&2
    exit 1
fi

if [[ "$POST_LOGOUT_LOCATION" != *"/login"* ]]; then
    echo "ERROR: Post-logout location does not point to /login: ${POST_LOGOUT_LOCATION:-none}." >&2
    exit 1
fi

printf '%s\n' \
    "outer_basic_auth_status=$NOAUTH_STATUS" \
    "login_page_status=$LOGIN_GET_STATUS" \
    "login_submit_status=$LOGIN_POST_STATUS" \
    "session_cookie_present=yes" \
    "dashboard_status=$DASHBOARD_STATUS" \
    "dashboard_user_marker=yes" \
    "logout_submit_status=$LOGOUT_STATUS" \
    "post_logout_status=$POST_LOGOUT_STATUS" \
    "post_logout_location=$POST_LOGOUT_LOCATION" \
    "layered_authentication=passed"
