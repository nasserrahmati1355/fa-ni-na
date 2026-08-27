from __future__ import annotations

import os
from typing import Any

from flask import Flask, render_template, request
import mysql.connector
from mysql.connector import Error as MySqlError

from seo_auditor import AuditError, AuditReport, audit_site


server = Flask(__name__)
server.config["MAX_CONTENT_LENGTH"] = 16 * 1024


class AuditRepository:
    def __init__(self) -> None:
        self.host = os.getenv("DB_HOST", "db")
        self.database = os.getenv("DB_NAME", "example")
        self.user = os.getenv("DB_USER", "root")
        self.password_file = os.getenv(
            "DB_PASSWORD_FILE",
            "/run/secrets/db-password",
        )

    def _read_password(self) -> str:
        with open(self.password_file, "r", encoding="utf-8") as file:
            return file.read().strip()

    def _connect(self) -> mysql.connector.MySQLConnection:
        return mysql.connector.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self._read_password(),
            connection_timeout=5,
        )

    @staticmethod
    def _ensure_schema(cursor: Any) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS seo_audits (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
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
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    def save(self, report: AuditReport) -> None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            self._ensure_schema(cursor)
            cursor.execute(
                """
                INSERT INTO seo_audits (
                    target_url,
                    pages_checked,
                    not_found_links,
                    http_errors,
                    pages_without_h1,
                    pages_without_title,
                    pages_without_meta,
                    total_issues,
                    elapsed_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
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
            cursor.close()
        finally:
            connection.close()

    def recent(self, limit: int = 8) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 20))
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            self._ensure_schema(cursor)
            cursor.execute(
                f"""
                SELECT
                    target_url,
                    pages_checked,
                    not_found_links,
                    pages_without_h1,
                    total_issues,
                    elapsed_ms,
                    created_at
                FROM seo_audits
                ORDER BY id DESC
                LIMIT {safe_limit}
                """
            )
            rows = list(cursor.fetchall())
            connection.commit()
            cursor.close()
            return rows
        finally:
            connection.close()


repository = AuditRepository()


@server.get("/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@server.route("/", methods=["GET", "POST"])
def index() -> str:
    report: AuditReport | None = None
    error: str | None = None
    database_warning: str | None = None
    submitted_url = ""
    submitted_max_pages = 10

    if request.method == "POST":
        submitted_url = request.form.get("url", "").strip()
        try:
            submitted_max_pages = int(request.form.get("max_pages", "10"))
        except ValueError:
            submitted_max_pages = 10

        try:
            report = audit_site(submitted_url, submitted_max_pages)
            try:
                repository.save(report)
            except (MySqlError, OSError) as exc:
                database_warning = f"گزارش ساخته شد ولی ثبت تاریخچه در دیتابیس ناموفق بود: {exc}"
        except (AuditError, ValueError) as exc:
            error = str(exc)
        except Exception:
            server.logger.exception("Unexpected SEO audit failure")
            error = "هنگام بررسی سایت خطای غیرمنتظره‌ای رخ داد. Log سرویس Backend را بررسی کنید."

    try:
        history = repository.recent()
    except (MySqlError, OSError) as exc:
        history = []
        database_warning = database_warning or f"تاریخچه دیتابیس در دسترس نیست: {exc}"

    return render_template(
        "index.html",
        report=report,
        error=error,
        database_warning=database_warning,
        history=history,
        submitted_url=submitted_url,
        submitted_max_pages=submitted_max_pages,
    )


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8000)
