from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView
from config.throttles import AuthRateThrottle, LogoutRateThrottle

from accounts.models import Profile
from accounts.serializers import ProfileSerializer, RegisterSerializer, UserSerializer


class RegisterView(APIView):
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ExtensionTokenView(APIView):
    """Issue a token pair dedicated to the browser extension.

    Called by the web app's /connect-extension page for a signed-in user (any
    sign-in method, including Google). The extension gets its own refresh
    token, so rotating it never invalidates the web app's session and vice
    versa.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = RefreshToken.for_user(request.user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class LogoutView(TokenBlacklistView):
    """Revoke a refresh token. Body: {"refresh": "<token>"}.

    Needs no access token, so logout still works after the access token has
    expired. Each session (web, extension) revokes only its own refresh token;
    access tokens stay valid until they expire (at most 30 minutes).
    """

    throttle_classes = [LogoutRateThrottle]


class ProfileView(APIView):
    """GET or PUT the signed-in user's profile. PUT replaces all fields;
    omitted fields become empty."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(ProfileSerializer(profile).data)

    def put(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        data = {field: request.data.get(field, "") for field in Profile.LIMITS}
        serializer = ProfileSerializer(profile, data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
