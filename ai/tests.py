import importlib
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

import ai.providers.groq_provider as groq_provider
from generations.models import Generation


class GroqClientInitializationTests(SimpleTestCase):
    def tearDown(self):
        # Restore a clean module so other tests see the real, unconstructed client.
        importlib.reload(groq_provider)

    def test_import_does_not_construct_client(self):
        with mock.patch("groq.Groq", side_effect=AssertionError("constructed at import")):
            module = importlib.reload(groq_provider)
        self.assertIsNone(module._client)

    def test_client_is_created_once_on_first_use(self):
        with mock.patch.object(groq_provider, "Groq") as groq_cls:
            first = groq_provider._get_client()
            second = groq_provider._get_client()
        groq_cls.assert_called_once()
        self.assertIs(first, second)

    def test_missing_key_fails_only_when_generation_is_attempted(self):
        with mock.patch.object(groq_provider, "Groq", side_effect=RuntimeError("missing key")):
            with self.assertRaises(RuntimeError):
                groq_provider.generate_connection_request("A", "B", "C")


# --- API integration tests -------------------------------------------------

GENERATORS = {
    "connection_request": {
        "slug": "connection-request",
        "payload": {"name": "Priya Shah", "company": "Acme", "role": "Engineering Manager"},
    },
    "referral_request": {
        "slug": "referral-request",
        "payload": {
            "name": "Priya Shah",
            "company": "Acme",
            "role": "Engineering Manager",
            "job_title": "Senior Frontend Engineer",
            "your_background": "8 years of React and Next.js",
        },
    },
    "recruiter_reply": {
        "slug": "recruiter-reply",
        "payload": {
            "recruiter_name": "Sam Lee",
            "company": "Acme",
            "job_title": "Staff Engineer",
            "your_background": "8 years of full-stack work",
            "interest_level": "interested",
        },
    },
    "followup": {
        "slug": "followup",
        "payload": {
            "name": "Priya Shah",
            "company": "Acme",
            "role": "Engineering Manager",
            "context": "Met at a React meetup",
            "days_since": "7",
        },
    },
}

SYNC_REPLY = "Hi Priya, great to connect."
STREAM_CHUNKS = ["Hi ", "Priya, ", "great to connect."]


class FakeGroqClient:
    """Stands in for groq.Groq; records prompts and never touches the network."""

    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])
                for text in STREAM_CHUNKS + [None]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"  {SYNC_REPLY}  "))]
        )

    @property
    def last_prompt(self):
        return self.calls[-1]["messages"][0]["content"]


class GenerationAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.fake = FakeGroqClient()
        # Any attempt to build a real Groq client fails the test.
        real_client_guard = mock.patch.object(
            groq_provider, "Groq", side_effect=AssertionError("real Groq client constructed")
        )
        fake_client = mock.patch.object(groq_provider, "_get_client", return_value=self.fake)
        real_client_guard.start()
        fake_client.start()
        self.addCleanup(mock.patch.stopall)

        self.user = User.objects.create_user(
            username="alice", password="correct-horse-battery-staple",
            first_name="Alice", last_name="Smith",
        )
        token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    @staticmethod
    def sync_url(slug):
        return f"/api/generate/{slug}/"

    @staticmethod
    def stream_url(slug):
        return f"/api/generate/stream/{slug}/"


class SyncGenerationTests(GenerationAPITestCase):
    def test_each_generator_returns_message_and_saves_history(self):
        for generation_type, spec in GENERATORS.items():
            with self.subTest(generation_type=generation_type):
                Generation.objects.all().delete()
                payload = {**spec["payload"], "tone": "formal"}

                response = self.client.post(self.sync_url(spec["slug"]), payload, format="json")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data, {"message": SYNC_REPLY})
                generation = Generation.objects.get()
                self.assertEqual(generation.user, self.user)
                self.assertEqual(generation.generation_type, generation_type)
                self.assertEqual(generation.input_data, payload)
                self.assertEqual(generation.output, SYNC_REPLY)
                self.assertFalse(self.fake.calls[-1].get("stream", False))

    def test_prompt_includes_inputs_sender_name_and_requested_tone(self):
        spec = GENERATORS["connection_request"]

        self.client.post(
            self.sync_url(spec["slug"]), {**spec["payload"], "tone": "concise"}, format="json"
        )

        prompt = self.fake.last_prompt
        self.assertIn("Recipient Name: Priya Shah", prompt)
        self.assertIn("Recipient Company: Acme", prompt)
        self.assertIn("Your Name (the sender): Alice Smith", prompt)
        self.assertIn(groq_provider.TONE_INSTRUCTIONS["concise"], prompt)

    def test_unknown_or_missing_tone_falls_back_to_friendly(self):
        spec = GENERATORS["connection_request"]
        for tone in ("shouty", None):
            with self.subTest(tone=tone):
                payload = dict(spec["payload"])
                if tone is not None:
                    payload["tone"] = tone

                self.client.post(self.sync_url(spec["slug"]), payload, format="json")

                self.assertIn(groq_provider.TONE_INSTRUCTIONS["friendly"], self.fake.last_prompt)

    def test_sender_name_falls_back_to_username(self):
        self.user.first_name = ""
        self.user.last_name = ""
        self.user.save()
        spec = GENERATORS["connection_request"]

        self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")

        self.assertIn("Your Name (the sender): alice", self.fake.last_prompt)

    @unittest.expectedFailure
    def test_missing_required_fields_are_rejected(self):
        # Known gap, scheduled for Phase 3: there is no request validation, so
        # missing fields reach the prompt as the literal text "None" and the
        # endpoint returns 200 instead of 400.
        response = self.client.post(self.sync_url("connection-request"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StreamingGenerationTests(GenerationAPITestCase):
    @staticmethod
    def read_events(response):
        body = b"".join(response.streaming_content).decode()
        events = [block for block in body.split("\n\n") if block]
        for event in events:
            assert event.startswith("data: "), event
        return [event[len("data: "):] for event in events]

    def test_each_stream_emits_chunks_then_done_and_saves_history(self):
        for generation_type, spec in GENERATORS.items():
            with self.subTest(generation_type=generation_type):
                Generation.objects.all().delete()

                response = self.client.post(
                    self.stream_url(spec["slug"]), spec["payload"], format="json"
                )

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response.streaming)
                self.assertEqual(response["Content-Type"], "text/event-stream")
                self.assertEqual(response["Cache-Control"], "no-cache")

                events = self.read_events(response)
                self.assertEqual(events[-1], "[DONE]")
                chunks = [json.loads(event)["chunk"] for event in events[:-1]]
                self.assertEqual(chunks, STREAM_CHUNKS)
                self.assertTrue(self.fake.calls[-1]["stream"])

                generation = Generation.objects.get()
                self.assertEqual(generation.user, self.user)
                self.assertEqual(generation.generation_type, generation_type)
                self.assertEqual(generation.input_data, spec["payload"])
                self.assertEqual(generation.output, "".join(STREAM_CHUNKS))

    def test_history_is_saved_only_after_stream_is_consumed(self):
        spec = GENERATORS["connection_request"]

        response = self.client.post(self.stream_url(spec["slug"]), spec["payload"], format="json")

        self.assertFalse(Generation.objects.exists())
        self.read_events(response)
        self.assertEqual(Generation.objects.count(), 1)


class GenerationAuthAndThrottleTests(GenerationAPITestCase):
    def test_all_generation_endpoints_require_authentication(self):
        self.client.credentials()
        for spec in GENERATORS.values():
            for url in (self.sync_url(spec["slug"]), self.stream_url(spec["slug"])):
                with self.subTest(url=url):
                    response = self.client.post(url, spec["payload"], format="json")
                    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(Generation.objects.exists())

    def test_generation_is_throttled_after_daily_limit(self):
        # DEFAULT_THROTTLE_RATES["generate"] is "20/day", shared by all generators.
        spec = GENERATORS["connection_request"]
        for _ in range(20):
            response = self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        blocked_sync = self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")
        blocked_stream = self.client.post(
            self.stream_url("followup"), GENERATORS["followup"]["payload"], format="json"
        )

        self.assertEqual(blocked_sync.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(blocked_stream.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(len(self.fake.calls), 20)
        self.assertEqual(Generation.objects.count(), 20)


class GroqRequestOptionsTests(GenerationAPITestCase):
    def test_sync_request_uses_default_model_and_hides_reasoning(self):
        spec = GENERATORS["connection_request"]

        self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")

        call = self.fake.calls[-1]
        self.assertEqual(call["model"], "openai/gpt-oss-120b")
        self.assertEqual(call["reasoning_effort"], "low")
        self.assertIs(call["include_reasoning"], False)
        self.assertEqual(call["max_completion_tokens"], groq_provider.MAX_COMPLETION_TOKENS)
        self.assertNotIn("max_tokens", call)

    def test_stream_request_uses_same_options_with_stream_enabled(self):
        spec = GENERATORS["followup"]

        response = self.client.post(self.stream_url(spec["slug"]), spec["payload"], format="json")
        b"".join(response.streaming_content)

        call = self.fake.calls[-1]
        self.assertTrue(call["stream"])
        self.assertEqual(call["model"], "openai/gpt-oss-120b")
        self.assertIs(call["include_reasoning"], False)

    def test_groq_model_environment_variable_overrides_default(self):
        spec = GENERATORS["connection_request"]
        with mock.patch.dict("os.environ", {"GROQ_MODEL": "qwen/qwen3.8-27b"}):
            self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")

        call = self.fake.calls[-1]
        self.assertEqual(call["model"], "qwen/qwen3.8-27b")
        # gpt-oss-specific reasoning options are not sent to other models.
        self.assertNotIn("reasoning_effort", call)
        self.assertNotIn("include_reasoning", call)

    def test_stream_skips_chunks_without_choices_and_reasoning_only_chunks(self):
        def create(**kwargs):
            self.fake.calls.append(kwargs)
            return iter([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))]),
                SimpleNamespace(choices=[]),
            ])

        self.fake.chat.completions.create = create
        spec = GENERATORS["connection_request"]

        response = self.client.post(self.stream_url(spec["slug"]), spec["payload"], format="json")
        body = b"".join(response.streaming_content).decode()

        self.assertIn('"chunk": "Hello"', body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))
        self.assertEqual(Generation.objects.get().output, "Hello")

    def test_sync_reply_with_empty_content_returns_empty_message(self):
        def create(**kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
            )

        self.fake.chat.completions.create = create
        spec = GENERATORS["connection_request"]

        response = self.client.post(self.sync_url(spec["slug"]), spec["payload"], format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": ""})
