from __future__ import annotations

from datetime import timedelta
import os
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFError, CSRFProtect
import mysql.connector
from mysql.connector import Error as MySqlError
from werkzeug.middleware.proxy_fix import ProxyFix

from auth import AuthRepository, User, is_safe_redirect_target, read_secret
from seo_auditor import AuditError, AuditReport, audit_site


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _trusted_hosts() -> list[str]:
    raw_hosts = os.getenv(
        "TRUSTED_HOSTS",
        "nhref.ir,localhost,127.0.0.1,backend",
    )
    hosts = [
        item.strip()
        for item in raw_hosts.split(",")
        if item.strip()
    ]
    if not hosts:
        raise RuntimeError("TRUSTED_HOSTS must contain at least one host.")
    return hosts


flask_secret_key = read_secret(
    os.getenv(
        "FLASK_SECRET_KEY_FILE",
        "/run/secrets/flask-secret-key",
    ),
    minimum_length=32,
)

server = Flask(__name__)
server.config.update(
    SECRET_KEY=flask_secret_key,
    MAX_CONTENT_LENGTH=16 * 1024,
    MAX_FORM_MEMORY_SIZE=16 * 1024,
    SESSION_COOKIE_NAME="nhref_session",
    SESSION_COOKIE_SECURE=_env_bool(
        "SESSION_COOKIE_SECURE",
        default=True,
    ),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_DOMAIN=None,
    PERMANENT_SESSION_LIFETIME=timedelta(
        minutes=max(
            15,
            min(
                int(os.getenv("SESSION_LIFETIME_MINUTES", "480")),
                1440,
            ),
        )
    ),
    SESSION_REFRESH_EACH_REQUEST=True,
    PREFERRED_URL_SCHEME="https",
    TRUSTED_HOSTS=_trusted_hosts(),
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_CHECK_DEFAULT=True,
    WTF_CSRF_TIME_LIMIT=3600,
    WTF_CSRF_SSL_STRICT=True,
)

server.wsgi_app = ProxyFix(
    server.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
)

csrf = CSRFProtect(server)
login_manager = LoginManager(server)
login_manager.login_view = "login"
login_manager.login_message = "برای ادامه ابتدا وارد حساب کاربری شوید."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"


class AuditRepository:
    def __init__(self) -> None:
        self.host = os.getenv("DB_HOST", "db")
        self.database = os.getenv("DB_NAME", "example")
        self.user = os.getenv("DB_USER", "root")
        self.password_file = os.getenv(
            "DB_PASSWORD_FILE",
            "/run/secrets/db-password",
        )

    def _connect(self) -> mysql.connector.MySQLConnection:
        return mysql.connector.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=read_secret(self.password_file),
            connection_timeout=5,
            autocommit=False,
        )

    @staticmethod
    def _column_exists(
        cursor: Any,
        table_name: str,
        column_name: str,
    ) -> bool:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.COLUMNS
            WHERE
                TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = %s
                AND COLUMN_NAME = %s
            """,
            (table_name, column_name),
        )
        row = cursor.fetchone()
        if isinstance(row, dict):
            return int(row["count"]) > 0
        return int(row[0]) > 0

    @staticmethod
    def _index_exists(
        cursor: Any,
        table_name: str,
        index_name: str,
    ) -> bool:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.STATISTICS
            WHERE
                TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = %s
                AND INDEX_NAME = %s
            """,
            (table_name, index_name),
        )
        row = cursor.fetchone()
        if isinstance(row, dict):
            return int(row["count"]) > 0
        return int(row[0]) > 0

    @classmethod
    def _ensure_schema(cls, cursor: Any) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS seo_audits (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                user_id BIGINT UNSIGNED NULL,
                target_url VARCHAR(2048) NOT NULL,
                pages_checked INT UNSIGNED NOT NULL,
                not_found_links INT UNSIGNED NOT NULL,
                http_errors INT UNSIGNED NOT NULL,
                pages_without_h1 INT UNSIGNED NOT NULL,
                pages_without_title INT UNSIGNED NOT NULL,
                pages_without_meta INT UNSIGNED NOT NULL,
                total_issues INT UNSIGNED NOT NULL,
                elapsed_ms INT UNSIGNED NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY ix_seo_audits_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        if not cls._column_exists(cursor, "seo_audits", "user_id"):
            cursor.execute(
                """
                ALTER TABLE seo_audits
                ADD COLUMN user_id BIGINT UNSIGNED NULL
                AFTER id
                """
            )

        if not cls._index_exists(
            cursor,
            "seo_audits",
            "ix_seo_audits_user_created",
        ):
            cursor.execute(
                """
                CREATE INDEX ix_seo_audits_user_created
                ON seo_audits (user_id, created_at)
                """
            )

    def save(self, report: AuditReport, user_id: int) -> None:
        connection = self._connect()
        cursor = connection.cursor()
        try:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                INSERT INTO seo_audits (
                    user_id,
                    target_url,
                    pages_checked,
                    not_found_links,
                    http_errors,
                    pages_without_h1,
                    pages_without_title,
                    pages_without_meta,
                    total_issues,
                    elapsed_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(user_id),
                    report.root_url[:2048],
                    report.summary["pages_checked"],
                    report.summary["not_found_links"],
                    report.summary["http_errors"],
                    report.summary["pages_without_h1"],
                    report.summary["pages_without_title"],
                    report.summary["pages_without_meta"],
                    report.summary["total_issues"],
                    report.elapsed_ms,
                ),
            )
            connection.commit()
        except MySqlError:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def recent(
        self,
        user: User,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 20))
        connection = self._connect()
        cursor = connection.cursor(dictionary=True)
        try:
            self._ensure_schema(cursor)

            if user.role == "admin":
                cursor.execute(
                    f"""
                    SELECT
                        a.target_url,
                        a.pages_checked,
                        a.not_found_links,
                        a.pages_without_h1,
                        a.total_issues,
                        a.elapsed_ms,
                        a.created_at,
                        COALESCE(u.username, 'legacy') AS owner_username
                    FROM seo_audits AS a
                    LEFT JOIN users AS u ON u.id = a.user_id
                    ORDER BY a.id DESC
                    LIMIT {safe_limit}
                    """
                )
            else:
                cursor.execute(
                    f"""
                    SELECT
                        a.target_url,
                        a.pages_checked,
                        a.not_found_links,
                        a.pages_without_h1,
                        a.total_issues,
                        a.elapsed_ms,
                        a.created_at,
                        COALESCE(u.username, 'legacy') AS owner_username
                    FROM seo_audits AS a
                    LEFT JOIN users AS u ON u.id = a.user_id
                    WHERE a.user_id = %s
                    ORDER BY a.id DESC
                    LIMIT {safe_limit}
                    """,
                    (user.id,),
                )

            rows = list(cursor.fetchall())
            connection.commit()
            return rows
        except MySqlError:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()


auth_repository = AuthRepository()
audit_repository = AuditRepository()


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        return auth_repository.get_by_id(int(user_id))
    except (ValueError, MySqlError, OSError):
        server.logger.exception("Unable to reload an authenticated user")
        return None


@server.after_request
def add_private_response_headers(response: Any) -> Any:
    response.headers.setdefault(
        "Cache-Control",
        "no-store, no-cache, must-revalidate, private",
    )
    response.headers.setdefault("Pragma", "no-cache")
    response.headers.setdefault("Expires", "0")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@server.errorhandler(CSRFError)
def handle_csrf_error(error: CSRFError) -> tuple[str, int]:
    return (
        render_template(
            "csrf_error.html",
            reason=error.description,
        ),
        400,
    )


@server.get("/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@server.route("/login", methods=["GET", "POST"])
def login() -> str | Any:
    if current_user.is_authenticated:
        return redirect(url_for("index"), code=303)

    error: str | None = None
    username = request.form.get("username", "").strip()
    next_target = (
        request.form.get("next")
        or request.args.get("next")
        or ""
    )

    if request.method == "POST":
        password = request.form.get("password", "")

        try:
            user, _status = auth_repository.authenticate(
                username,
                password,
            )
        except (MySqlError, OSError):
            server.logger.exception("Authentication repository failure")
            user = None
            error = (
                "سرویس ورود موقتاً در دسترس نیست. "
                "لطفاً چند دقیقه دیگر دوباره تلاش کنید."
            )

        if user is not None:
            if next_target and not is_safe_redirect_target(
                next_target,
                request.host_url,
            ):
                abort(400)

            session.clear()
            session.permanent = True
            if not login_user(
                user,
                remember=False,
                fresh=True,
            ):
                abort(403)

            return redirect(
                next_target or url_for("index"),
                code=303,
            )

        if error is None:
            error = "نام کاربری یا رمز عبور صحیح نیست."

    return render_template(
        "login.html",
        error=error,
        username=username,
        next_target=next_target,
    )


@server.post("/logout")
@login_required
def logout() -> Any:
    logout_user()
    session.clear()
    flash("با موفقیت از حساب کاربری خارج شدید.", "success")
    return redirect(url_for("login"), code=303)


def _load_history(
    database_warning: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return audit_repository.recent(current_user), database_warning
    except (MySqlError, OSError) as exc:
        warning = database_warning or (
            "تاریخچه دیتابیس در دسترس نیست: "
            f"{exc}"
        )
        return [], warning


def _render_dashboard(
    *,
    report: AuditReport | None = None,
    error: str | None = None,
    database_warning: str | None = None,
    submitted_url: str = "",
    submitted_max_pages: int = 10,
) -> str:
    history, database_warning = _load_history(database_warning)

    return render_template(
        "index.html",
        report=report,
        error=error,
        database_warning=database_warning,
        history=history,
        submitted_url=submitted_url,
        submitted_max_pages=submitted_max_pages,
    )


@server.get("/")
@login_required
def index() -> str:
    return _render_dashboard()


@server.post("/audit")
@login_required
def run_audit() -> str:
    submitted_url = request.form.get("url", "").strip()

    try:
        submitted_max_pages = int(
            request.form.get("max_pages", "10")
        )
    except ValueError:
        submitted_max_pages = 10

    report: AuditReport | None = None
    error: str | None = None
    database_warning: str | None = None

    try:
        report = audit_site(
            submitted_url,
            submitted_max_pages,
        )
        try:
            audit_repository.save(
                report,
                int(current_user.get_id()),
            )
        except (MySqlError, OSError) as exc:
            database_warning = (
                "گزارش ساخته شد ولی ثبت تاریخچه در دیتابیس "
                f"ناموفق بود: {exc}"
            )
    except (AuditError, ValueError) as exc:
        error = str(exc)
    except Exception:
        server.logger.exception("Unexpected SEO audit failure")
        error = (
            "هنگام بررسی سایت خطای غیرمنتظره‌ای رخ داد. "
            "Log سرویس Backend را بررسی کنید."
        )

    return _render_dashboard(
        report=report,
        error=error,
        database_warning=database_warning,
        submitted_url=submitted_url,
        submitted_max_pages=submitted_max_pages,
    )


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8000)
