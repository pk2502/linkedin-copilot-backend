from django.urls import path
from accounts.views import ExtensionTokenView, LogoutView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("extension-token/", ExtensionTokenView.as_view(), name="extension_token"),
]
