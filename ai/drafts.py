"""/api/drafts/: three personalised drafts per request, and tweaks."""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from ai.prompts import (
    DRAFTS_SCHEMA,
    TWEAK_SCHEMA,
    build_draft_messages,
    build_tweak_messages,
)
from ai.providers import groq_provider
from ai.serializers import DEFAULT_TONE, DRAFT_SERIALIZERS, NEEDS_BACKGROUND, TweakSerializer
from ai.views import AI_UNAVAILABLE, get_sender_name
from config.throttles import GenerateRateThrottle, TweakRateThrottle
from generations.models import Generation

logger = logging.getLogger(__name__)

NEEDS_BACKGROUND_MESSAGE = "Add your background here or fill in your profile first."


def _clean_drafts(result):
    drafts = result.get("drafts") if isinstance(result, dict) else None
    if not isinstance(drafts, list):
        raise groq_provider.ProviderResponseError("No drafts in response")
    cleaned = [d.strip() for d in drafts if isinstance(d, str) and d.strip()]
    if len(cleaned) != 3:
        raise groq_provider.ProviderResponseError("Expected three drafts")
    return cleaned


def _unavailable():
    return Response({"error": AI_UNAVAILABLE}, status=status.HTTP_502_BAD_GATEWAY)


class DraftView(APIView):
    """POST {type, tone?, ...fields} -> {id, variants: [3 drafts]}.

    Counts once against the daily generation limit. Validation runs before the
    throttle (as in the original endpoints), so invalid requests are free.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def check_throttles(self, request):
        generation_type = request.data.get("type")
        serializer_class = DRAFT_SERIALIZERS.get(generation_type)
        if serializer_class is None:
            raise ValidationError({"type": [f"Must be one of: {', '.join(DRAFT_SERIALIZERS)}."]})
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.generation_type = generation_type
        self.validated = dict(serializer.validated_data)
        self.profile = Profile.objects.filter(user=request.user).first()

        if generation_type in NEEDS_BACKGROUND:
            override = (self.validated.get("your_background") or "").strip()
            if not override and not (self.profile and self.profile.background):
                raise ValidationError({"your_background": [NEEDS_BACKGROUND_MESSAGE]})
        super().check_throttles(request)

    def post(self, request):
        tone = self.validated.pop("tone", None) or DEFAULT_TONE
        messages = build_draft_messages(
            self.generation_type, self.validated, tone, get_sender_name(request.user), self.profile
        )
        try:
            drafts = _clean_drafts(
                groq_provider.structured_chat(messages, DRAFTS_SCHEMA, "drafts")
            )
        except Exception:
            logger.exception("Draft generation failed for %s", self.generation_type)
            return _unavailable()

        generation = Generation.objects.create(
            user=request.user,
            generation_type=self.generation_type,
            input_data={**self.validated, "tone": tone},
            output=drafts[0],
            variants=drafts,
        )
        return Response({"id": generation.id, "variants": drafts}, status=status.HTTP_201_CREATED)


class TweakView(APIView):
    """POST {variant: 0-2, instruction} -> {id, text}. Rewrites one draft."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [TweakRateThrottle]

    def check_throttles(self, request):
        serializer = TweakSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.validated = serializer.validated_data
        self.source = get_object_or_404(Generation, pk=self.kwargs["pk"], user=request.user)
        if self.validated["variant"] >= len(self.source.variants):
            raise ValidationError({"variant": ["This draft has no such variant."]})
        super().check_throttles(request)

    def post(self, request, pk):
        source = self.source
        # Tweaks of tweaks hang off the original draft and reuse its request
        # data, so the model always sees the full context.
        root = source.parent or source
        variant = self.validated["variant"]
        instruction = self.validated["instruction"]
        messages = build_tweak_messages(
            source.generation_type, source.variants[variant], instruction, root.input_data
        )
        try:
            result = groq_provider.structured_chat(messages, TWEAK_SCHEMA, "tweak", 800)
            text = (result.get("text") or "").strip() if isinstance(result, dict) else ""
            if not text:
                raise groq_provider.ProviderResponseError("Empty tweak")
        except Exception:
            logger.exception("Tweak failed for generation %s", source.pk)
            return _unavailable()

        generation = Generation.objects.create(
            user=request.user,
            generation_type=source.generation_type,
            input_data={"instruction": instruction, "variant": variant},
            output=text,
            variants=[text],
            parent=root,
        )
        return Response({"id": generation.id, "text": text}, status=status.HTTP_201_CREATED)
