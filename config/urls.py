from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from accounts.views import ProfileView
from ai.profile_import import ProfileParseView
from generations.views import OnboardingView
from config.views import database_health_check, health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("health/db/", database_health_check, name="database_health_check"),
    path("admin/", admin.site.urls),

    path("api/auth/", include("accounts.urls")),
    path("api/profile/", ProfileView.as_view(), name="profile"),
    path("api/profile/parse/", ProfileParseView.as_view(), name="profile_parse"),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/auth/social/", include("accounts.social_urls")),

    # allauth URLs (required internally)
    path("accounts/", include("allauth.urls")),

    path("api/generate/", include("ai.urls")),
    path("api/drafts/", include("ai.draft_urls")),
    path("api/history/", include("generations.urls")),
    path("api/onboarding/", OnboardingView.as_view(), name="onboarding"),
    path("api/contacts/", include("contacts.urls")),
]
