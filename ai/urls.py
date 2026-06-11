from django.urls import path
from ai.views import (
    GenerateConnectionRequestView,
    GenerateReferralRequestView,
    GenerateRecruiterReplyView,
    GenerateFollowupView,
    StreamConnectionRequestView,
    StreamReferralRequestView,
    StreamRecruiterReplyView,
    StreamFollowupView,
)

urlpatterns = [
    path("connection-request/", GenerateConnectionRequestView.as_view(), name="generate_connection_request"),
    path("referral-request/", GenerateReferralRequestView.as_view(), name="generate_referral_request"),
    path("recruiter-reply/", GenerateRecruiterReplyView.as_view(), name="generate_recruiter_reply"),
    path("followup/", GenerateFollowupView.as_view(), name="generate_followup"),

    path("stream/connection-request/", StreamConnectionRequestView.as_view(), name="stream_connection_request"),
    path("stream/referral-request/", StreamReferralRequestView.as_view(), name="stream_referral_request"),
    path("stream/recruiter-reply/", StreamRecruiterReplyView.as_view(), name="stream_recruiter_reply"),
    path("stream/followup/", StreamFollowupView.as_view(), name="stream_followup"),
]
