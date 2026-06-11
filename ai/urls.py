from django.urls import path
from ai.views import (
    GenerateConnectionRequestView,
    GenerateReferralRequestView,
    GenerateRecruiterReplyView,
    GenerateFollowupView,
)

urlpatterns = [
    path("connection-request/", GenerateConnectionRequestView.as_view(), name="generate_connection_request"),
    path("referral-request/", GenerateReferralRequestView.as_view(), name="generate_referral_request"),
    path("recruiter-reply/", GenerateRecruiterReplyView.as_view(), name="generate_recruiter_reply"),
    path("followup/", GenerateFollowupView.as_view(), name="generate_followup"),
]
