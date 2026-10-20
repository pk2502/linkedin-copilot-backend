from django.urls import path
from accounts.social_views import GoogleLoginView, LinkedInLoginView

urlpatterns = [
    path("google/", GoogleLoginView.as_view(), name="google_login"),
    path("linkedin/", LinkedInLoginView.as_view(), name="linkedin_login"),
]
