from unittest import mock

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.social_views import LinkedInOAuth2Adapter

URL = "/api/auth/social/linkedin/"
REDIRECT = "https://connect-pilot.vercel.app/auth/linkedin/callback"
OPENID_CONFIG = {
    "issuer": "https://www.linkedin.com/oauth",
    "authorization_endpoint": "https://www.linkedin.com/oauth/v2/authorization",
    "token_endpoint": "https://www.linkedin.com/oauth/v2/accessToken",
    "userinfo_endpoint": "https://api.linkedin.com/v2/userinfo",
    "jwks_uri": "https://www.linkedin.com/oauth/openid/jwks",
    "token_endpoint_auth_methods_supported": ["client_secret_post"],
}
USERINFO = {
    "sub": "li-123",
    "name": "Priya Shah",
    "given_name": "Priya",
    "family_name": "Shah",
    "email": "priya@example.com",
    "email_verified": True,
    "picture": "https://media.licdn.com/p.jpg",
}
LINKEDIN_APP = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "linkedin",
                "name": "LinkedIn",
                "client_id": "test-client",
                "secret": "test-secret",
                "settings": {"server_url": "https://www.linkedin.com/oauth", "token_auth_method": "client_secret_post"},
            }
        ]
    }
}


@override_settings(
    LINKEDIN_CLIENT_ID="test-client",
    LINKEDIN_CLIENT_SECRET="test-secret",
    LINKEDIN_REDIRECT_URIS=[REDIRECT],
    SOCIALACCOUNT_PROVIDERS=LINKEDIN_APP,
)
class LinkedInLoginTests(APITestCase):
    """The LinkedIn token and userinfo endpoints are mocked; nothing leaves the test."""

    def setUp(self):
        cache.clear()
        self.userinfo = dict(USERINFO)
        self.exchanged = []

        def get_access_token(client, code, **kwargs):
            self.exchanged.append({"code": code, "redirect_uri": client.callback_url, "client_id": client.consumer_key})
            return {"access_token": "li-access", "expires_in": 3600}

        patches = [
            mock.patch("allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token", get_access_token),
            mock.patch.object(
                LinkedInOAuth2Adapter, "openid_config", new_callable=mock.PropertyMock, return_value=OPENID_CONFIG
            ),
            mock.patch.object(LinkedInOAuth2Adapter, "_fetch_user_info", lambda adapter, token: self.userinfo),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def login(self, **overrides):
        return self.client.post(URL, {"code": "auth-code", "redirect_uri": REDIRECT, **overrides}, format="json")

    def test_new_user_gets_tokens_and_their_linkedin_name(self):
        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])
        user = User.objects.get(email="priya@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Priya", "Shah"))
        self.assertEqual(SocialAccount.objects.get(user=user).uid, "li-123")
        self.assertEqual(self.exchanged, [{"code": "auth-code", "redirect_uri": REDIRECT, "client_id": "test-client"}])

    def test_signing_in_again_reuses_the_account(self):
        self.login()
        self.login()
        self.assertEqual(User.objects.count(), 1)

    def test_existing_account_with_the_same_email_is_linked(self):
        existing = User.objects.create_user(username="priya", email="priya@example.com", password="x" * 12)

        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["user"]["pk"], existing.id)
        self.assertEqual(SocialAccount.objects.get().user, existing)

    def test_unverified_email_is_rejected(self):
        self.userinfo["email_verified"] = False
        User.objects.create_user(username="priya", email="priya@example.com", password="x" * 12)

        response = self.login()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SocialAccount.objects.exists())

    def test_unknown_redirect_uri_is_rejected_before_any_exchange(self):
        response = self.login(redirect_uri="https://evil.example.com/callback")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.exchanged, [])

    def test_access_tokens_are_not_accepted(self):
        response = self.client.post(URL, {"access_token": "stolen", "redirect_uri": REDIRECT}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    @override_settings(LINKEDIN_CLIENT_ID="", LINKEDIN_CLIENT_SECRET="")
    def test_disabled_without_credentials(self):
        self.assertEqual(self.login().status_code, 503)
        self.assertEqual(self.exchanged, [])
