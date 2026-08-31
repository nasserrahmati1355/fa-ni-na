from __future__ import annotations

import unittest

from auth import User, is_safe_redirect_target, normalize_username
from werkzeug.security import check_password_hash, generate_password_hash


class AuthenticationHelpersTests(unittest.TestCase):
    def test_normalize_username(self) -> None:
        self.assertEqual(normalize_username("  Admin  "), "admin")

    def test_local_redirect_is_allowed(self) -> None:
        self.assertTrue(
            is_safe_redirect_target(
                "/audits?page=2",
                "https://nhref.ir/",
            )
        )

    def test_external_or_downgrade_redirect_is_rejected(self) -> None:
        self.assertFalse(
            is_safe_redirect_target(
                "https://attacker.example/",
                "https://nhref.ir/",
            )
        )
        self.assertFalse(
            is_safe_redirect_target(
                "//attacker.example/",
                "https://nhref.ir/",
            )
        )
        self.assertFalse(
            is_safe_redirect_target(
                "http://nhref.ir/",
                "https://nhref.ir/",
            )
        )

    def test_user_identifier_and_active_state(self) -> None:
        user = User(
            id=42,
            username="admin",
            role="admin",
            active=True,
        )
        self.assertEqual(user.get_id(), "42")
        self.assertTrue(user.is_active)

    def test_password_hash_is_not_plaintext(self) -> None:
        password = "example-long-password"
        password_hash = generate_password_hash(password)
        self.assertNotEqual(password_hash, password)
        self.assertTrue(check_password_hash(password_hash, password))


if __name__ == "__main__":
    unittest.main()
