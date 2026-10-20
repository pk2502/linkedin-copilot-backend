from django.contrib.auth.models import User
from django.db import connection
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Profile
from generations.models import Generation

URL = "/api/onboarding/"


class OnboardingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")

    def make(self, user=None, **fields):
        return Generation.objects.create(
            user=user or self.user, generation_type="connection_request", input_data={}, output="x", **fields
        )

    def test_requires_auth(self):
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_new_user_has_nothing_done(self):
        self.assertEqual(
            self.client.get(URL).json(),
            {"profile_completeness": 0, "has_draft": False, "used_extension": False},
        )

    def test_reports_profile_drafts_and_extension_use(self):
        Profile.objects.create(user=self.user, experience="Built things", summary="Engineer")
        self.make()
        self.assertEqual(
            self.client.get(URL).json(),
            {"profile_completeness": 50, "has_draft": True, "used_extension": False},
        )
        self.make(source="extension")
        self.assertTrue(self.client.get(URL).json()["used_extension"])

    def test_only_counts_the_users_own_drafts(self):
        other = User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        self.make(user=other, source="extension")
        self.assertEqual(self.client.get(URL).json()["has_draft"], False)

    def test_source_defaults_to_web_for_inserts_without_it(self):
        # Code from before this column (a rolling deploy) inserts without source.
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO generations_generation (user_id, generation_type, input_data, output, created_at)"
                " VALUES (%s, 'followup', '{}', 'x', NOW())",
                [self.user.id],
            )
        self.assertEqual(Generation.objects.get().source, "web")
