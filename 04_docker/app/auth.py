from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from flask_login import UserMixin
import mysql.connector
from mysql.connector import Error as MySqlError
from werkzeug.security import check_password_hash, generate_password_hash


AuthenticationStatus = Literal["ok", "invalid", "inactive", "locked"]


def read_secret(path: str, *, minimum_length: int = 1) -> str:
    """Read a required UTF-8 secret without exposing it to logs."""
    if not path:
        raise RuntimeError("Secret path is empty.")

    with open(path, "r", encoding="utf-8") as secret_file:
        value = secret_file.read().strip()

    if len(value) < minimum_length:
        raise RuntimeError(f"Secret file is empty or too short: {path}")

    return value


def normalize_username(value: str) -> str:
    """Normalize usernames consistently before lookup or storage."""
    return value.strip().casefold()


def is_safe_redirect_target(target: str | None, host_url: str) -> bool:
    """Allow only same-origin http(s) redirect targets."""
    if not target:
        return False

    reference = urlsplit(host_url)
    candidate = urlsplit(urljoin(host_url, target))

    return (
        candidate.scheme == reference.scheme
        and candidate.scheme in {"http", "https"}
        and candidate.netloc == reference.netloc
    )


@dataclass(slots=True)
class User(UserMixin):
    id: int
    username: str
    role: str
    active: bool

    @property
    def is_active(self) -> bool:
        return self.active

    def get_id(self) -> str:
        return str(self.id)


class AuthRepository:
    def __init__(self) -> None:
        self.host = os.getenv("DB_HOST", "db")
        self.database = os.getenv("DB_NAME", "example")
        self.user = os.getenv("DB_USER", "root")
        self.password_file = os.getenv(
            "DB_PASSWORD_FILE",
            "/run/secrets/db-password",
        )
        self.connection_timeout = max(
            1,
            min(int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "5")), 30),
        )
        self.max_failed_attempts = max(
            3,
            min(int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5")), 20),
        )
        self.lockout_minutes = max(
            1,
            min(int(os.getenv("AUTH_LOCKOUT_MINUTES", "15")), 1440),
        )
        self._dummy_password_hash = generate_password_hash(
            os.urandom(32).hex()
        )

    def _connect(self) -> mysql.connector.MySQLConnection:
        return mysql.connector.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=read_secret(self.password_file),
            connection_timeout=self.connection_timeout,
            autocommit=False,
        )

    @staticmethod
    def _ensure_schema(cursor: Any) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                username VARCHAR(64) NOT NULL,
                password_hash VARCHAR(512) NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                failed_login_attempts INT UNSIGNED NOT NULL DEFAULT 0,
                locked_until DATETIME NULL,
                last_login_at DATETIME NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_users_username (username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @staticmethod
    def _to_user(row: dict[str, Any] | None) -> User | None:
        if not row:
            return None

        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            active=bool(row["is_active"]),
        )

    def ensure_schema(self) -> None:
        connection = self._connect()
        cursor = connection.cursor()
        try:
            self._ensure_schema(cursor)
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def get_by_id(self, user_id: int) -> User | None:
        connection = self._connect()
        cursor = connection.cursor(dictionary=True)
        try:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                SELECT id, username, role, is_active
                FROM users
                WHERE id = %s
                LIMIT 1
                """,
                (int(user_id),),
            )
            row = cursor.fetchone()
            connection.commit()
            return self._to_user(row)
        finally:
            cursor.close()
            connection.close()

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> tuple[User | None, AuthenticationStatus]:
        normalized_username = normalize_username(username)
        if (
            not normalized_username
            or len(normalized_username) > 64
            or not password
            or len(password) > 256
        ):
            return None, "invalid"

        connection = self._connect()
        cursor = connection.cursor(dictionary=True)
        try:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    role,
                    is_active,
                    failed_login_attempts,
                    locked_until
                FROM users
                WHERE username = %s
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_username,),
            )
            row = cursor.fetchone()

            if not row:
                check_password_hash(
                    self._dummy_password_hash,
                    password,
                )
                connection.commit()
                return None, "invalid"

            if not bool(row["is_active"]):
                connection.commit()
                return None, "inactive"

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            locked_until = row.get("locked_until")
            if locked_until and locked_until > now:
                connection.commit()
                return None, "locked"

            if not check_password_hash(str(row["password_hash"]), password):
                attempts = int(row["failed_login_attempts"] or 0) + 1
                new_locked_until: datetime | None = None

                if attempts >= self.max_failed_attempts:
                    new_locked_until = now + timedelta(
                        minutes=self.lockout_minutes,
                    )
                    attempts = 0

                cursor.execute(
                    """
                    UPDATE users
                    SET
                        failed_login_attempts = %s,
                        locked_until = %s
                    WHERE id = %s
                    """,
                    (attempts, new_locked_until, int(row["id"])),
                )
                connection.commit()

                if new_locked_until:
                    return None, "locked"
                return None, "invalid"

            cursor.execute(
                """
                UPDATE users
                SET
                    failed_login_attempts = 0,
                    locked_until = NULL,
                    last_login_at = UTC_TIMESTAMP()
                WHERE id = %s
                """,
                (int(row["id"]),),
            )
            connection.commit()
            return self._to_user(row), "ok"
        except MySqlError:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def create_or_update_admin(
        self,
        username: str,
        password: str,
        *,
        rotate_password: bool,
    ) -> Literal["created", "updated", "unchanged"]:
        normalized_username = normalize_username(username)

        if not normalized_username:
            raise ValueError("Admin username is required.")
        if len(normalized_username) > 64:
            raise ValueError("Admin username must be 64 characters or fewer.")
        if len(password) < 16:
            raise ValueError(
                "Admin password must contain at least 16 characters."
            )

        connection = self._connect()
        cursor = connection.cursor(dictionary=True)
        try:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                SELECT id, password_hash, role, is_active
                FROM users
                WHERE username = %s
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_username,),
            )
            row = cursor.fetchone()

            if not row:
                cursor.execute(
                    """
                    INSERT INTO users (
                        username,
                        password_hash,
                        role,
                        is_active,
                        failed_login_attempts,
                        locked_until
                    ) VALUES (%s, %s, 'admin', TRUE, 0, NULL)
                    """,
                    (
                        normalized_username,
                        generate_password_hash(password),
                    ),
                )
                connection.commit()
                return "created"

            needs_password_update = (
                rotate_password
                and not check_password_hash(
                    str(row["password_hash"]),
                    password,
                )
            )
            needs_account_update = (
                str(row["role"]) != "admin"
                or not bool(row["is_active"])
            )

            if not needs_password_update and not needs_account_update:
                connection.commit()
                return "unchanged"

            if needs_password_update:
                cursor.execute(
                    """
                    UPDATE users
                    SET
                        password_hash = %s,
                        role = 'admin',
                        is_active = TRUE,
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = %s
                    """,
                    (
                        generate_password_hash(password),
                        int(row["id"]),
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE users
                    SET
                        role = 'admin',
                        is_active = TRUE,
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = %s
                    """,
                    (int(row["id"]),),
                )

            connection.commit()
            return "updated"
        except MySqlError:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
