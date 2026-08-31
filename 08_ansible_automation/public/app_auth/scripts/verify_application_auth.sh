#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

if [[ "$#" -ne 3 ]]; then
    echo "Usage: $0 DOMAIN APP_USER APP_PASSWORD_FILE" >&2
    exit 64
fi

DOMAIN="$1"
APP_USER="$2"
APP_PASSWORD_FILE="$3"

if [[ ! -s "$APP_PASSWORD_FILE" ]]; then
    echo "ERROR: Application password file is missing or empty: $APP_PASSWORD_FILE" >&2
    exit 66
fi

for required_command in curl python3; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "ERROR: Required command is unavailable: $required_command" >&2
        exit 69
    fi
done

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

COOKIE_JAR="$WORK_DIR/cookies.txt"
LOGIN_HTML="$WORK_DIR/login.html"
LOGIN_HEADERS="$WORK_DIR/login-headers.txt"
LOGIN_FORM="$WORK_DIR/login-form.txt"
LOGIN_POST_HEADERS="$WORK_DIR/login-post-headers.txt"
LOGIN_POST_BODY="$WORK_DIR/login-post-body.html"
DASHBOARD_HEADERS="$WORK_DIR/dashboard-headers.txt"
DASHBOARD_HTML="$WORK_DIR/dashboard.html"
LOGOUT_FORM="$WORK_DIR/logout-form.txt"
LOGOUT_HEADERS="$WORK_DIR/logout-headers.txt"
POST_LOGOUT_HEADERS="$WORK_DIR/post-logout-headers.txt"

: > "$COOKIE_JAR"
chmod 600 "$COOKIE_JAR"

CURL_COMMON=(
    --silent
    --show-error
    --connect-timeout 10
    --max-time 60
    --header 'Cache-Control: no-cache'
    --header 'Pragma: no-cache'
)

LOGIN_PAGE_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --dump-header "$LOGIN_HEADERS" \
        --output "$LOGIN_HTML" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login?stage5_login=$(date +%s%N)"
)"

if [[ "$LOGIN_PAGE_STATUS" != "200" ]]; then
    echo "ERROR: Expected public GET /login status 200, received $LOGIN_PAGE_STATUS." >&2
    exit 1
fi

if grep -qi '^WWW-Authenticate:[[:space:]]*Basic' "$LOGIN_HEADERS"; then
    echo "ERROR: Nginx still returned a Basic Authentication challenge." >&2
    exit 1
fi

grep -Fq 'ورود به SEO Auditor' "$LOGIN_HTML" || {
    echo "ERROR: The Flask login page marker was not found." >&2
    exit 1
}

UNAUTH_DASHBOARD_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --dump-header "$DASHBOARD_HEADERS" \
        --output /dev/null \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/?stage5_unauth=$(date +%s%N)"
)"

case "$UNAUTH_DASHBOARD_STATUS" in
    302|303) ;;
    *)
        echo "ERROR: Expected unauthenticated dashboard redirect, received $UNAUTH_DASHBOARD_STATUS." >&2
        exit 1
        ;;
esac

UNAUTH_DASHBOARD_LOCATION="$(
    awk \
        'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, ""); print $2}' \
        "$DASHBOARD_HEADERS" |
    tail -n 1
)"

if [[ "$UNAUTH_DASHBOARD_LOCATION" != *"/login"* ]]; then
    echo "ERROR: Unauthenticated dashboard did not redirect to /login: ${UNAUTH_DASHBOARD_LOCATION:-none}." >&2
    exit 1
fi

# Negative CSRF test: Flask-WTF must reject this before credentials are checked.
CSRF_NEGATIVE_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --request POST \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --header "Origin: https://${DOMAIN}" \
        --referer "https://${DOMAIN}/login" \
        --data 'username=csrf-test&password=csrf-test' \
        --output /dev/null \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login"
)"

if [[ "$CSRF_NEGATIVE_STATUS" != "400" ]]; then
    echo "ERROR: Expected missing-CSRF login status 400, received $CSRF_NEGATIVE_STATUS." >&2
    exit 1
fi

LOGIN_CSRF_TOKEN="$(python3 - "$LOGIN_HTML" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import sys


class CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
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

python3 - "$LOGIN_FORM" "$APP_USER" "$APP_PASSWORD_FILE" "$LOGIN_CSRF_TOKEN" <<'PY'
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

LOGIN_SUBMIT_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --request POST \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --header "Origin: https://${DOMAIN}" \
        --referer "https://${DOMAIN}/login" \
        --data-binary "@$LOGIN_FORM" \
        --dump-header "$LOGIN_POST_HEADERS" \
        --output "$LOGIN_POST_BODY" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/login"
)"

case "$LOGIN_SUBMIT_STATUS" in
    302|303) ;;
    *)
        echo "ERROR: Expected POST /login status 302 or 303, received $LOGIN_SUBMIT_STATUS." >&2
        exit 1
        ;;
esac

if ! awk \
    'NF >= 7 && ($1 !~ /^#/ || $1 ~ /^#HttpOnly_/) && $6 == "nhref_session" {found=1} END {exit !found}' \
    "$COOKIE_JAR"
then
    COOKIE_NAMES="$(
        awk \
            'NF >= 7 && ($1 !~ /^#/ || $1 ~ /^#HttpOnly_/) {print $6}' \
            "$COOKIE_JAR" |
        sort -u |
        paste -sd, -
    )"

    echo "ERROR: Flask session cookie was not stored. Cookie names: ${COOKIE_NAMES:-none}." >&2
    exit 1
fi

SESSION_SET_COOKIE="$(
    awk \
        'BEGIN {IGNORECASE=1} /^Set-Cookie:[[:space:]]*nhref_session=/ {sub(/\r$/, ""); print}' \
        "$LOGIN_POST_HEADERS" |
    tail -n 1
)"

for cookie_attribute in Secure HttpOnly SameSite=Lax; do
    if [[ "$SESSION_SET_COOKIE" != *"$cookie_attribute"* ]]; then
        echo "ERROR: Session cookie is missing attribute: $cookie_attribute." >&2
        exit 1
    fi
done

DASHBOARD_STATUS="$(
    curl "${CURL_COMMON[@]}" \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --dump-header "$DASHBOARD_HEADERS" \
        --output "$DASHBOARD_HTML" \
        --write-out '%{http_code}' \
        "https://${DOMAIN}/?stage5_dashboard=$(date +%s%N)"
)"

if [[ "$DASHBOARD_STATUS" != "200" ]]; then
    DASHBOARD_LOCATION="$(
        awk \
            'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, ""); print $2}' \
            "$DASHBOARD_HEADERS" |
        tail -n 1
    )"

    echo "ERROR: Expected authenticated dashboard status 200, received $DASHBOARD_STATUS; location=${DASHBOARD_LOCATION:-none}." >&2
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


class LogoutCsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_logout_form = False
        self.token = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)

        if tag.casefold() == "form":
            action = str(values.get("action") or "")
            self.in_logout_form = action.endswith("/logout")
            return

        if (
            self.in_logout_form
            and tag.casefold() == "input"
            and values.get("name") == "csrf_token"
            and values.get("value")
        ):
            self.token = str(values["value"])

    def handle_endtag(self, tag):
        if tag.casefold() == "form":
            self.in_logout_form = False


parser = LogoutCsrfParser()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))

if not parser.token:
    raise SystemExit("Logout CSRF token was not found in the dashboard.")

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
    302|303) ;;
    *)
        echo "ERROR: Expected POST /logout status 302 or 303, received $LOGOUT_STATUS." >&2
        exit 1
        ;;
esac

POST_LOGOUT_STATUS="$(
    curl "${CURL_COMMON[@]}" \
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
    "nginx_basic_auth_challenge=absent" \
    "login_page_status=$LOGIN_PAGE_STATUS" \
    "unauthenticated_dashboard_status=$UNAUTH_DASHBOARD_STATUS" \
    "unauthenticated_dashboard_location=$UNAUTH_DASHBOARD_LOCATION" \
    "csrf_negative_test_status=$CSRF_NEGATIVE_STATUS" \
    "login_submit_status=$LOGIN_SUBMIT_STATUS" \
    "session_cookie_present=yes" \
    "session_cookie_secure=yes" \
    "dashboard_status=$DASHBOARD_STATUS" \
    "dashboard_user_marker=yes" \
    "logout_submit_status=$LOGOUT_STATUS" \
    "post_logout_status=$POST_LOGOUT_STATUS" \
    "post_logout_location=$POST_LOGOUT_LOCATION" \
    "application_authentication=passed"
