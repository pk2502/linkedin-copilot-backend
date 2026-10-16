from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
ME_URL = "/api/auth/me/"

PASSWORD = "correct-horse-battery-staple"


class AuthTestCase(APITestCase):
    def setUp(self):
        # Throttle counters live in the cache and would leak between tests.
        cache.clear()


class RegisterTests(AuthTestCase):
    def test_register_creates_user_and_returns_tokens(self):
        response = self.client.post(
            REGISTER_URL,
            {"username": "alice", "email": "alice@example.com", "password": PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {"user", "access", "refresh"})
        self.assertEqual(response.data["user"]["username"], "alice")
        self.assertEqual(response.data["user"]["email"], "alice@example.com")
        self.assertNotIn("password", response.data["user"])

        user = User.objects.get(username="alice")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username="alice", password=PASSWORD)

        response = self.client.post(
            REGISTER_URL, {"username": "alice", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertEqual(User.objects.filter(username="alice").count(), 1)

    def test_register_rejects_short_password(self):
        response = self.client.post(
            REGISTER_URL, {"username": "alice", "password": "short"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_register_rejects_missing_fields(self):
        response = self.client.post(REGISTER_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("password", response.data)


class LoginAndRefreshTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password=PASSWORD
        )

    def test_login_returns_token_pair(self):
        response = self.client.post(
            LOGIN_URL, {"username": "alice", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_wrong_password(self):
        response = self.client.post(
            LOGIN_URL, {"username": "alice", "password": "wrong-password"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_refresh_rotates_and_blacklists_old_refresh_token(self):
        old_refresh = str(RefreshToken.for_user(self.user))

        first = self.client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIn("access", first.data)
        # ROTATE_REFRESH_TOKENS=True: a new refresh token is issued.
        self.assertIn("refresh", first.data)
        self.assertNotEqual(first.data["refresh"], old_refresh)

        # BLACKLIST_AFTER_ROTATION=True: the old refresh token is now rejected.
        reused = self.client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
        self.assertEqual(reused.status_code, status.HTTP_401_UNAUTHORIZED)

        # The rotated token still works.
        second = self.client.post(
            REFRESH_URL, {"refresh": first.data["refresh"]}, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)

    def test_refresh_rejects_garbage_token(self):
        response = self.client.post(REFRESH_URL, {"refresh": "not-a-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password=PASSWORD
        )

    def test_me_requires_authentication(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejects_invalid_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_with_access_token_from_login(self):
        login = self.client.post(
            LOGIN_URL, {"username": "alice", "password": PASSWORD}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"id": self.user.id, "username": "alice", "email": "alice@example.com"},
        )


class GoogleLoginTokenTests(AuthTestCase):
    GOOGLE_URL = "/api/auth/social/google/"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="googler", email="g@example.com")
        # Skip the OAuth code exchange with Google; it is not under test.
        patcher = mock.patch(
            "dj_rest_auth.registration.serializers.SocialLoginSerializer.validate",
            lambda serializer, attrs: {"user": self.user},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_google_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(self.GOOGLE_URL, {"code": "fake-code"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("access"))
        # Without a refresh token Google users were logged out after 30 minutes.
        self.assertTrue(response.data.get("refresh"))

    def test_refresh_token_from_google_login_can_be_rotated(self):
        login = self.client.post(self.GOOGLE_URL, {"code": "fake-code"}, format="json")

        response = self.client.post(REFRESH_URL, {"refresh": login.data["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
