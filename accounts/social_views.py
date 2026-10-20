from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.providers.openid_connect.views import OpenIDConnectOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from config.throttles import AuthRateThrottle


class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = "postmessage"
    client_class = OAuth2Client


class LinkedInOAuth2Adapter(OpenIDConnectOAuth2Adapter):
    """Sign In with LinkedIn using OpenID Connect (provider_id "linkedin")."""

    def __init__(self, request):
        super().__init__(request, "linkedin")

    def complete_login(self, request, app, token, **kwargs):
        login = super().complete_login(request, app, token, **kwargs)
        # Accounts are linked by email (SOCIALACCOUNT_EMAIL_AUTHENTICATION), so
        # only an address LinkedIn has verified may sign in.
        if not any(address.verified for address in login.email_addresses):
            raise ValidationError({"non_field_errors": ["Your LinkedIn email address isn't verified."]})
        return login


class LinkedInLoginView(SocialLoginView):
    """POST {code, redirect_uri} from the web app's /auth/linkedin/callback page.

    Exchanges the code with LinkedIn and returns the same {access, refresh,
    user} as the other sign-in methods.
    """

    adapter_class = LinkedInOAuth2Adapter
    client_class = OAuth2Client
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        if not (settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET):
            return Response(
                {"error": "LinkedIn sign-in is not available."}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        # Only the authorization code flow: an access token from some other
        # LinkedIn app must not be accepted as proof of identity.
        if request.data.get("access_token") or request.data.get("id_token"):
            raise ValidationError({"code": ["Sign in with the authorization code."]})
        redirect_uri = request.data.get("redirect_uri", "")
        if redirect_uri not in settings.LINKEDIN_REDIRECT_URIS:
            raise ValidationError({"redirect_uri": ["Unknown redirect URI."]})
        # The code was issued for this redirect URI; LinkedIn checks they match.
        self.callback_url = redirect_uri
        return super().post(request, *args, **kwargs)
