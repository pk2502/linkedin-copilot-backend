from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/auth/", include("accounts.urls")),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/auth/social/", include("accounts.social_urls")),

    # allauth URLs (required internally)
    path("accounts/", include("allauth.urls")),

    path("api/generate/", include("ai.urls")),
    path("api/history/", include("generations.urls")),
]
