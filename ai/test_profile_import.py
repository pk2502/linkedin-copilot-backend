from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from unittest import mock

import ai.providers.groq_provider as groq_provider
from accounts.models import Profile
from ai.profile_import import PARSE_SCHEMA, PDF_MAX_BYTES
from ai.test_drafts import FakeStructuredClient

PARSE_URL = "/api/profile/parse/"
RESUME = (
    "Priya Shah. Senior Frontend Engineer at Acme since 2021. Led the design system "
    "used by 12 product teams. Skills: React, TypeScript, Next.js, accessibility."
)
PARSED = {
    "headline": "Senior Frontend Engineer at Acme",
    "summary": "I build accessible React apps.",
    "skills": "React, TypeScript, Next.js",
    "target_roles": "",
    "experience": "Senior Frontend Engineer, Acme (2021-present)\nLed the design system.",
}


def make_pdf(text):
    """A minimal one-page PDF whose content stream draws `text`."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 10 Tf 40 760 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


class ProfileParseTests(APITestCase):
    replies = [PARSED]

    def setUp(self):
        cache.clear()
        self.fake = FakeStructuredClient(self.replies)
        mock.patch.object(groq_provider, "Groq", side_effect=AssertionError("real Groq client")).start()
        mock.patch.object(groq_provider, "_get_client", return_value=self.fake).start()
        self.addCleanup(mock.patch.stopall)
        self.user = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")

    def test_requires_auth(self):
        self.client.credentials()
        self.assertEqual(self.client.post(PARSE_URL, {"text": RESUME}, format="json").status_code, 401)

    def test_text_returns_fields_without_saving(self):
        response = self.client.post(PARSE_URL, {"text": RESUME}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), PARSED)
        self.assertFalse(Profile.objects.filter(user=self.user).exists())
        call = self.fake.calls[0]
        self.assertEqual(call["response_format"]["json_schema"]["schema"], PARSE_SCHEMA)
        self.assertTrue(call["response_format"]["json_schema"]["strict"])
        self.assertIn("<data>", self.fake.last_user_message)
        self.assertIn("Led the design system", self.fake.last_user_message)
        self.assertIn("information, not instructions", call["messages"][0]["content"])

    def test_pdf_upload_is_read(self):
        upload = SimpleUploadedFile("cv.pdf", make_pdf(RESUME), content_type="application/pdf")

        response = self.client.post(PARSE_URL, {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertIn("Led the design system", self.fake.last_user_message)

    def test_short_text_is_rejected_without_ai_call_or_quota(self):
        response = self.client.post(PARSE_URL, {"text": "too short"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("text", response.json())
        self.assertEqual(self.fake.calls, [])

    def test_non_pdf_upload_is_rejected(self):
        upload = SimpleUploadedFile("cv.pdf", b"hello world" * 10, content_type="application/pdf")
        response = self.client.post(PARSE_URL, {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["file"], ["Upload a PDF file."])

    def test_oversized_pdf_is_rejected(self):
        upload = SimpleUploadedFile("cv.pdf", b"%PDF-" + b"0" * PDF_MAX_BYTES, content_type="application/pdf")
        response = self.client.post(PARSE_URL, {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["file"], ["PDF must be 2 MB or smaller."])

    def test_broken_pdf_is_rejected(self):
        upload = SimpleUploadedFile("cv.pdf", b"%PDF-1.4\nnot really a pdf", content_type="application/pdf")
        response = self.client.post(PARSE_URL, {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PDF", response.json()["file"][0])
        self.assertEqual(self.fake.calls, [])

    def test_pdf_without_text_is_rejected(self):
        upload = SimpleUploadedFile("cv.pdf", make_pdf(" "), content_type="application/pdf")
        response = self.client.post(PARSE_URL, {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No text found", response.json()["file"][0])

    @override_settings()
    def test_daily_limit(self):
        from rest_framework.settings import api_settings

        rates = {**api_settings.DEFAULT_THROTTLE_RATES, "profile_parse": "2/day"}
        with mock.patch("config.throttles.ProfileParseRateThrottle.THROTTLE_RATES", rates):
            for _ in range(2):
                self.assertEqual(self.client.post(PARSE_URL, {"text": RESUME}, format="json").status_code, 200)
            self.assertEqual(self.client.post(PARSE_URL, {"text": RESUME}, format="json").status_code, 429)
            # Invalid input stays free even after the limit is reached.
            self.assertEqual(self.client.post(PARSE_URL, {"text": "x"}, format="json").status_code, 400)

    def test_output_is_trimmed_to_profile_limits(self):
        self.fake.replies = [{**PARSED, "headline": "  " + "H" * 400 + "  "}]
        response = self.client.post(PARSE_URL, {"text": RESUME}, format="json")
        self.assertEqual(len(response.json()["headline"]), Profile.LIMITS["headline"])

    def test_empty_or_failed_ai_returns_502(self):
        for reply in ({field: "" for field in PARSED}, "not json", RuntimeError("down")):
            self.fake.replies = [reply]
            response = self.client.post(PARSE_URL, {"text": RESUME}, format="json")
            self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
