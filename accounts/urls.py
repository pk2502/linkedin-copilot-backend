from django.urls import path
from accounts.views import ExtensionTokenView, RegisterView, MeView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("extension-token/", ExtensionTokenView.as_view(), name="extension_token"),
]
