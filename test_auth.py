"""
Automated Security & Authentication Test Suite for NSFLUX.
Verifies session login/logout, credentials verification, remember me, API protection,
and HTTP Basic Auth backward compatibility.
"""
import unittest
import os
import sys

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

import config
from web.app import app

class TestAuthenticationSubsystem(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_secret_key_nsflux_2026"
        self.client = app.test_client()
        self.valid_user = config.DASHBOARD_USERNAME
        self.valid_pass = config.DASHBOARD_PASSWORD

    def test_login_page_renders(self):
        """Verify GET /login loads the institutional HTML template."""
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"NSFLUX Trading Platform", res.data)
        self.assertIn(b"AUTHORIZED PERSONNEL ONLY", res.data)
        self.assertIn(b"ACCESS DASHBOARD", res.data)

    def test_unauthenticated_dashboard_redirects(self):
        """Verify GET / redirects unauthenticated browser requests to /login."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_unauthenticated_api_returns_401_without_basic_header(self):
        """Verify GET /api/status returns 401 JSON without WWW-Authenticate pop-up header."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 401)
        self.assertNotIn("WWW-Authenticate", res.headers)
        data = res.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_invalid_login_credentials(self):
        """Verify invalid credentials return 401 and error message."""
        res = self.client.post(
            "/login",
            json={"username": "wrong_user", "password": "bad_password"},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get("success", True))
        self.assertIn("Invalid username or password", data.get("message", ""))

    def test_successful_login_and_session(self):
        """Verify valid login sets session and grants dashboard access."""
        res = self.client.post(
            "/login",
            json={"username": self.valid_user, "password": self.valid_pass, "remember": False},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("redirect"), "/")

        # Test session persistence on dashboard index
        dash_res = self.client.get("/")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"NoStressCapital", dash_res.data)

        # Test session access to API endpoints
        api_res = self.client.get("/api/status")
        self.assertEqual(api_res.status_code, 200)

    def test_remember_me_functionality(self):
        """Verify remember me option marks session as permanent."""
        with self.client:
            res = self.client.post(
                "/login",
                json={"username": self.valid_user, "password": self.valid_pass, "remember": True},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(res.status_code, 200)
            from flask import session
            self.assertTrue(session.get("authenticated"))
            self.assertTrue(session.permanent)

    def test_logout_destroys_session(self):
        """Verify logout clears session and revokes dashboard access."""
        # Login first
        self.client.post(
            "/login",
            json={"username": self.valid_user, "password": self.valid_pass},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(self.client.get("/api/status").status_code, 200)

        # Perform logout
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)
        self.assertIn("/login", logout_res.headers.get("Location", ""))

        # Verify access is revoked
        self.assertEqual(self.client.get("/api/status").status_code, 401)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_http_basic_auth_backward_compatibility(self):
        """Verify HTTP Basic Auth header continues to work for automated scripts."""
        import base64
        credentials = f"{self.valid_user}:{self.valid_pass}"
        encoded_cred = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {encoded_cred}"}

        res = self.client.get("/api/status", headers=headers)
        self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
