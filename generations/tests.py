from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from generations.models import Generation

HISTORY_URL = "/api/history/"


class DatabaseBackendTests(TestCase):
    def test_tests_run_against_postgresql(self):
        self.assertEqual(
            connection.vendor,
            "postgresql",
            "Integration tests must run on PostgreSQL; check DB_* settings in .env.",
        )


class HistoryAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(username="alice", password="pw-alice-123456")
        self.bob = User.objects.create_user(username="bob", password="pw-bob-123456")
        self.authenticate(self.alice)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def make_generation(self, user, generation_type, output, minutes_ago=0):
        generation = Generation.objects.create(
            user=user,
            generation_type=generation_type,
            input_data={"name": "Priya"},
            output=output,
        )
        # auto_now_add ignores explicit values on create, so set the time afterwards.
        Generation.objects.filter(pk=generation.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
        return generation

    def test_list_returns_own_generations_newest_first(self):
        older = self.make_generation(self.alice, "followup", "Older message", minutes_ago=10)
        newer = self.make_generation(self.alice, "connection_request", "Newer message")

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [newer.id, older.id])
        self.assertEqual(
            set(response.data[0]),
            {"id", "generation_type", "input_data", "output", "variants", "parent", "created_at"},
        )

    def test_list_excludes_other_users_generations(self):
        mine = self.make_generation(self.alice, "followup", "Alice's message")
        self.make_generation(self.bob, "followup", "Bob's message")

        response = self.client.get(HISTORY_URL)

        self.assertEqual([item["id"] for item in response.data], [mine.id])

    def test_search_matches_output_and_generation_type_case_insensitively(self):
        by_output = self.make_generation(
            self.alice, "connection_request", "Loved your talk on Kubernetes", minutes_ago=5
        )
        by_type = self.make_generation(self.alice, "referral_request", "Could you refer me?")
        self.make_generation(self.alice, "followup", "Just checking in", minutes_ago=1)

        output_hits = self.client.get(HISTORY_URL, {"search": "kubernetes"})
        type_hits = self.client.get(HISTORY_URL, {"search": "REFERRAL"})

        self.assertEqual([item["id"] for item in output_hits.data], [by_output.id])
        self.assertEqual([item["id"] for item in type_hits.data], [by_type.id])

    def test_search_never_returns_other_users_generations(self):
        self.make_generation(self.bob, "followup", "Bob's secret kubernetes note")
        self.make_generation(self.bob, "referral_request", "Bob's referral")

        for term in ("kubernetes", "referral"):
            with self.subTest(search=term):
                response = self.client.get(HISTORY_URL, {"search": term})
                self.assertEqual(response.data, [])

    def test_search_with_no_matches_returns_empty_list(self):
        self.make_generation(self.alice, "followup", "Just checking in")

        response = self.client.get(HISTORY_URL, {"search": "nothing-matches-this"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_delete_own_generation(self):
        generation = self.make_generation(self.alice, "followup", "Delete me")

        response = self.client.delete(f"{HISTORY_URL}{generation.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Generation.objects.filter(pk=generation.pk).exists())

    def test_cannot_delete_another_users_generation(self):
        bobs = self.make_generation(self.bob, "followup", "Bob's message")

        response = self.client.delete(f"{HISTORY_URL}{bobs.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Generation.objects.filter(pk=bobs.pk).exists())

    def test_delete_missing_generation_returns_404(self):
        response = self.client.delete(f"{HISTORY_URL}999999/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_requires_authentication(self):
        generation = self.make_generation(self.alice, "followup", "Private")
        self.client.credentials()

        list_response = self.client.get(HISTORY_URL)
        delete_response = self.client.delete(f"{HISTORY_URL}{generation.id}/")

        self.assertEqual(list_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(delete_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Generation.objects.filter(pk=generation.pk).exists())


class RollingDeployCompatibilityTests(APITestCase):
    def test_insert_without_new_columns_still_works(self):
        # Code deployed before the variants/parent migration does not send these
        # columns; the database default must cover them during a rollout.
        user = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO generations_generation (user_id, generation_type, input_data, output, created_at) "
                "VALUES (%s, 'followup', '{}'::jsonb, 'old row', NOW()) RETURNING id",
                [user.id],
            )
            pk = cursor.fetchone()[0]

        generation = Generation.objects.get(pk=pk)
        self.assertEqual(generation.variants, [])
        self.assertIsNone(generation.parent)
