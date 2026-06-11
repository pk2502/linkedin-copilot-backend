from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from generations.models import Generation
from ai.services import (
    generate_connection_request,
    generate_referral_request,
    generate_recruiter_reply,
    generate_followup,
)


def get_sender_name(user):
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


class GenerateConnectionRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = request.data.get("name")
        company = request.data.get("company")
        role = request.data.get("role")

        message = generate_connection_request(
            name=name, company=company, role=role,
            sender_name=get_sender_name(request.user),
        )
        Generation.objects.create(
            user=request.user, generation_type="connection_request",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateReferralRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = generate_referral_request(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            sender_name=get_sender_name(request.user),
        )
        Generation.objects.create(
            user=request.user, generation_type="referral_request",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateRecruiterReplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = generate_recruiter_reply(
            recruiter_name=request.data.get("recruiter_name"),
            company=request.data.get("company"),
            job_title=request.data.get("job_title"),
            your_background=request.data.get("your_background"),
            interest_level=request.data.get("interest_level"),
            sender_name=get_sender_name(request.user),
        )
        Generation.objects.create(
            user=request.user, generation_type="recruiter_reply",
            input_data=request.data, output=message,
        )
        return Response({"message": message})


class GenerateFollowupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = generate_followup(
            name=request.data.get("name"),
            company=request.data.get("company"),
            role=request.data.get("role"),
            context=request.data.get("context"),
            days_since=request.data.get("days_since"),
            sender_name=get_sender_name(request.user),
        )
        Generation.objects.create(
            user=request.user, generation_type="followup",
            input_data=request.data, output=message,
        )
        return Response({"message": message})
