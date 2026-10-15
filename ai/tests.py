import importlib
from unittest import mock

from django.test import SimpleTestCase

import ai.providers.groq_provider as groq_provider


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
