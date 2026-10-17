import json
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.serializers import (
    DEFAULT_TONE,
    ConnectionRequestSerializer,
    FollowupSerializer,
    RecruiterReplySerializer,
    ReferralRequestSerializer,
)
from ai.services import (
    generate_connection_request,
    generate_referral_request,
    generate_recruiter_reply,
    generate_followup,
    stream_connection_request,
    stream_referral_request,
    stream_recruiter_reply,
    stream_followup,
)
from config.throttles import GenerateRateThrottle
from generations.models import Generation

logger = logging.getLogger(__name__)

AI_UNAVAILABLE = "AI service unavailable. Try again."


def get_sender_name(user):
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


class GenerationView(APIView):
    """Shared behaviour for every generation endpoint.

    Subclasses set `serializer_class`, `generation_type` and the provider
    function (`generate` or `stream`).
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]
    serializer_class = None
    generation_type = None

    def check_throttles(self, request):
        # DRF runs authentication -> permissions -> throttles before the
        # handler. Validating here (after auth, before throttling) means an
        # invalid request returns 400 without using up the daily quota.
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.validated_data = dict(serializer.validated_data)
        super().check_throttles(request)

    def provider_kwargs(self):
        kwargs = {k: v for k, v in self.validated_data.items() if k != "tone"}
        kwargs["sender_name"] = get_sender_name(self.request.user)
        kwargs["tone"] = self.validated_data.get("tone") or DEFAULT_TONE
        return kwargs

    def save_history(self, output):
        Generation.objects.create(
            user=self.request.user,
            generation_type=self.generation_type,
            input_data=self.validated_data,
            output=output,
        )


def ai_unavailable_response():
    return Response({"error": AI_UNAVAILABLE}, status=status.HTTP_502_BAD_GATEWAY)


# --- Non-streaming views ---

class SyncGenerationView(GenerationView):
    generate = None

    def post(self, request):
        try:
            message = type(self).generate(**self.provider_kwargs())
        except Exception:
            logger.exception("AI provider failed for %s", self.generation_type)
            return ai_unavailable_response()
        self.save_history(message)
        return Response({"message": message})


class GenerateConnectionRequestView(SyncGenerationView):
    serializer_class = ConnectionRequestSerializer
    generation_type = "connection_request"
    generate = staticmethod(generate_connection_request)


class GenerateReferralRequestView(SyncGenerationView):
    serializer_class = ReferralRequestSerializer
    generation_type = "referral_request"
    generate = staticmethod(generate_referral_request)


class GenerateRecruiterReplyView(SyncGenerationView):
    serializer_class = RecruiterReplySerializer
    generation_type = "recruiter_reply"
    generate = staticmethod(generate_recruiter_reply)


class GenerateFollowupView(SyncGenerationView):
    serializer_class = FollowupSerializer
    generation_type = "followup"
    generate = staticmethod(generate_followup)


# --- Streaming views ---

def sse_event(payload):
    return f"data: {json.dumps(payload)}\n\n"


class StreamGenerationView(GenerationView):
    stream = None

    def post(self, request):
        chunks = type(self).stream(**self.provider_kwargs())

        # Pull the first chunk before sending headers: if the provider is
        # down, the client gets a real 502 instead of an empty 200 stream.
        try:
            first = next(chunks, None)
        except Exception:
            logger.exception("AI provider failed for %s", self.generation_type)
            return ai_unavailable_response()

        response = StreamingHttpResponse(
            self.event_stream(first, chunks), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def event_stream(self, first, chunks):
        full_message = []
        try:
            if first is not None:
                full_message.append(first)
                yield sse_event({"chunk": first})
            for chunk in chunks:
                full_message.append(chunk)
                yield sse_event({"chunk": chunk})
        except Exception:
            # Headers are already sent; report the failure in-band and skip
            # history so a partial message is never saved.
            logger.exception("AI provider failed mid-stream for %s", self.generation_type)
            yield sse_event({"error": AI_UNAVAILABLE})
            return
        self.save_history("".join(full_message))
        yield "data: [DONE]\n\n"


class StreamConnectionRequestView(StreamGenerationView):
    serializer_class = ConnectionRequestSerializer
    generation_type = "connection_request"
    stream = staticmethod(stream_connection_request)


class StreamReferralRequestView(StreamGenerationView):
    serializer_class = ReferralRequestSerializer
    generation_type = "referral_request"
    stream = staticmethod(stream_referral_request)


class StreamRecruiterReplyView(StreamGenerationView):
    serializer_class = RecruiterReplySerializer
    generation_type = "recruiter_reply"
    stream = staticmethod(stream_recruiter_reply)


class StreamFollowupView(StreamGenerationView):
    serializer_class = FollowupSerializer
    generation_type = "followup"
    stream = staticmethod(stream_followup)
