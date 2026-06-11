import json
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from generations.models import Generation
from config.throttles import GenerateRateThrottle
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


def get_sender_name(user):
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


def get_tone(request):
    tone = request.data.get("tone", "friendly")
    return tone if tone in ("formal", "friendly", "concise") else "friendly"


# --- Non-streaming views ---

class GenerateConnectionRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        message = generate_connection_request(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        Generation.objects.create(
            user=request.user, generation_type="connection_request",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateReferralRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        message = generate_referral_request(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        Generation.objects.create(
            user=request.user, generation_type="referral_request",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateRecruiterReplyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        message = generate_recruiter_reply(
            recruiter_name=request.data.get("recruiter_name"),
            company=request.data.get("company"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            interest_level=request.data.get("interest_level"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        Generation.objects.create(
            user=request.user, generation_type="recruiter_reply",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateFollowupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        message = generate_followup(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            context=request.data.get("context"),
            days_since=request.data.get("days_since"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        Generation.objects.create(
            user=request.user, generation_type="followup",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


# --- Streaming views ---

def _sse_stream(generator, user, generation_type, input_data):
    full_message = []

    def event_stream():
        for chunk in generator:
            full_message.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        Generation.objects.create(
            user=user,
            generation_type=generation_type,
            input_data=input_data,
            output="".join(full_message),
        )
        yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class StreamConnectionRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        generator = stream_connection_request(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        return _sse_stream(generator, request.user, "connection_request", request.data)


class StreamReferralRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        generator = stream_referral_request(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        return _sse_stream(generator, request.user, "referral_request", request.data)


class StreamRecruiterReplyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        generator = stream_recruiter_reply(
            recruiter_name=request.data.get("recruiter_name"),
            company=request.data.get("company"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            interest_level=request.data.get("interest_level"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        return _sse_stream(generator, request.user, "recruiter_reply", request.data)


class StreamFollowupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GenerateRateThrottle]

    def post(self, request):
        generator = stream_followup(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            context=request.data.get("context"),
            days_since=request.data.get("days_since"),
            sender_name=get_sender_name(request.user),
            tone=get_tone(request),
        )
        return _sse_stream(generator, request.user, "followup", request.data)
