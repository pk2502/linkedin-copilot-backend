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
LOGOUT_URL = "/api/auth/logout/"

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


class ExtensionTokenTests(AuthTestCase):
    URL = "/api/auth/extension-token/"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.web_refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.web_refresh.access_token}")

    def test_requires_authentication(self):
        self.client.credentials()

        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_get(self):
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_returns_a_new_token_pair_for_the_same_user(self):
        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"access", "refresh"})
        self.assertNotEqual(response.data["refresh"], str(self.web_refresh))

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me = self.client.get(ME_URL)
        self.assertEqual(me.data["id"], self.user.id)

    def test_extension_and_web_sessions_rotate_independently(self):
        extension = self.client.post(self.URL).data
        self.client.credentials()

        rotated = self.client.post(REFRESH_URL, {"refresh": extension["refresh"]}, format="json")
        web = self.client.post(REFRESH_URL, {"refresh": str(self.web_refresh)}, format="json")

        # Rotating (and blacklisting) the extension token leaves the web session working.
        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertEqual(web.status_code, status.HTTP_200_OK)


class LogoutTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.refresh = RefreshToken.for_user(self.user)

    def test_logout_revokes_the_refresh_token(self):
        response = self.client.post(LOGOUT_URL, {"refresh": str(self.refresh)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refreshed = self.client.post(REFRESH_URL, {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(refreshed.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_works_with_an_expired_access_token_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")

        response = self.client.post(LOGOUT_URL, {"refresh": str(self.refresh)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_refresh_token_is_rejected(self):
        response = self.client.post(LOGOUT_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_or_already_revoked_token_is_rejected(self):
        self.client.post(LOGOUT_URL, {"refresh": str(self.refresh)}, format="json")
        for token in ("garbage", str(self.refresh)):
            with self.subTest(token=token[:10]):
                response = self.client.post(LOGOUT_URL, {"refresh": token}, format="json")
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logging_out_one_session_keeps_the_other(self):
        extension = RefreshToken.for_user(self.user)

        self.client.post(LOGOUT_URL, {"refresh": str(extension)}, format="json")

        web = self.client.post(REFRESH_URL, {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(web.status_code, status.HTTP_200_OK)

    def test_logout_does_not_use_the_login_budget(self):
        for _ in range(12):
            self.client.post(LOGOUT_URL, {"refresh": "garbage"}, format="json")

        login = self.client.post(LOGIN_URL, {"username": "alice", "password": PASSWORD}, format="json")

        self.assertEqual(login.status_code, status.HTTP_200_OK)
