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


# --- /api/drafts/ ---
# Same fields as the original endpoints, plus optional page context. your_background
# is optional: the saved profile supplies it when left empty.
# recipient_context and job_description are used for the prompt only and are
# never stored (see EPHEMERAL_FIELDS).

RECIPIENT_CONTEXT_MAX = 4000
JOB_DESCRIPTION_MAX = 6000
CONVERSATION_MAX = 4000
EPHEMERAL_FIELDS = ("recipient_context", "job_description", "conversation")


def optional_text(max_length):
    return serializers.CharField(max_length=max_length, required=False, allow_blank=True)


class RecipientContextMixin(serializers.Serializer):
    # Visible text from the recipient's LinkedIn profile (About, experience,
    # education), read by the extension when the user opens it.
    recipient_context = optional_text(RECIPIENT_CONTEXT_MAX)


class DraftConnectionSerializer(RecipientContextMixin, ConnectionRequestSerializer):
    pass


class DraftReferralSerializer(RecipientContextMixin, ReferralRequestSerializer):
    your_background = optional_text(LONG_TEXT)
    job_description = optional_text(JOB_DESCRIPTION_MAX)


class ConversationMixin(serializers.Serializer):
    """The recent LinkedIn messages with this person, read by the extension.

    With a conversation the model can see what was said, so the fields that
    only describe it (OPTIONAL_WITH_CONVERSATION) may be left empty. Without
    one they stay required.
    """

    OPTIONAL_WITH_CONVERSATION = ()

    conversation = optional_text(CONVERSATION_MAX)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.OPTIONAL_WITH_CONVERSATION:
            field = self.fields[name]
            field.required = False
            if isinstance(field, serializers.CharField):
                field.allow_blank = True
            else:
                field.allow_null = True

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not (attrs.get("conversation") or "").strip():
            missing = {
                name: [serializers.Field.default_error_messages["required"]]
                for name in self.OPTIONAL_WITH_CONVERSATION
                if attrs.get(name) in (None, "")
            }
            if missing:
                raise serializers.ValidationError(missing)
        return attrs


class DraftRecruiterSerializer(ConversationMixin, RecipientContextMixin, RecruiterReplySerializer):
    OPTIONAL_WITH_CONVERSATION = ("company", "job_title")
    your_background = optional_text(LONG_TEXT)


class DraftFollowupSerializer(ConversationMixin, RecipientContextMixin, FollowupSerializer):
    OPTIONAL_WITH_CONVERSATION = ("company", "role", "context", "days_since")


DRAFT_SERIALIZERS = {
    "connection_request": DraftConnectionSerializer,
    "referral_request": DraftReferralSerializer,
    "recruiter_reply": DraftRecruiterSerializer,
    "followup": DraftFollowupSerializer,
}

NEEDS_BACKGROUND = {"referral_request", "recruiter_reply"}


class TweakSerializer(serializers.Serializer):
    variant = serializers.IntegerField(min_value=0, max_value=2)
    instruction = serializers.ChoiceField(choices=("shorter", "warmer", "more_specific", "more_formal"))
