from __future__ import annotations

import os

from auth import AuthRepository, read_secret


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def main() -> None:
    username = os.getenv("APP_ADMIN_USERNAME", "admin")
    password_file = os.getenv(
        "APP_ADMIN_PASSWORD_FILE",
        "/run/secrets/app-admin-password",
    )
    password = read_secret(password_file, minimum_length=16)

    repository = AuthRepository()
    result = repository.create_or_update_admin(
        username,
        password,
        rotate_password=_env_bool(
            "APP_ADMIN_ROTATE_PASSWORD",
            default=True,
        ),
    )

    print(f"Application admin bootstrap completed: {result}")


if __name__ == "__main__":
    main()
