"""Request validation for the generation endpoints.

Every field the prompt builders use is required, trimmed and length-capped, so
missing input can no longer reach the prompt as the text "None" and oversized
input cannot inflate prompt cost. Only validated fields are stored in history.
"""
from rest_framework import serializers

TONES = ("formal", "friendly", "concise")
DEFAULT_TONE = "friendly"
INTEREST_LEVELS = ("very interested", "somewhat interested", "not interested")

SHORT_TEXT = 150
LONG_TEXT = 2000


def short_text():
    return serializers.CharField(max_length=SHORT_TEXT)


def long_text():
    return serializers.CharField(max_length=LONG_TEXT)


class GenerationRequestSerializer(serializers.Serializer):
    # Lenient on purpose: an unknown or empty tone falls back to the default
    # instead of failing the request (existing clients rely on this).
    tone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_tone(self, value):
        return value if value in TONES else DEFAULT_TONE


class ConnectionRequestSerializer(GenerationRequestSerializer):
    name = short_text()
    company = short_text()
    role = short_text()


class ReferralRequestSerializer(GenerationRequestSerializer):
    name = short_text()
    company = short_text()
    role = short_text()
    job_title = short_text()
    your_background = long_text()


class RecruiterReplySerializer(GenerationRequestSerializer):
    recruiter_name = short_text()
    company = short_text()
    job_title = short_text()
    your_background = long_text()
    interest_level = serializers.ChoiceField(choices=INTEREST_LEVELS)


class FollowupSerializer(GenerationRequestSerializer):
    name = short_text()
    company = short_text()
    role = short_text()
    context = long_text()
    days_since = serializers.IntegerField(min_value=0, max_value=3650)
