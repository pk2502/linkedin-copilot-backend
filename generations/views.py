from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from accounts.models import Profile
from generations.models import Generation
from generations.serializers import GenerationSerializer


class GenerationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.query_params.get("search", "").strip()
        qs = Generation.objects.filter(user=request.user).order_by("-created_at")

        if search:
            qs = qs.filter(output__icontains=search) | \
                 Generation.objects.filter(user=request.user, generation_type__icontains=search)
            qs = qs.order_by("-created_at")

        serializer = GenerationSerializer(qs, many=True)
        return Response(serializer.data)


class GenerationDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            generation = Generation.objects.get(pk=pk, user=request.user)
            generation.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Generation.DoesNotExist:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class OnboardingView(APIView):
    """GET -> the first-run checklist state for the dashboard.

    {profile_completeness: 0-100, has_draft: bool, used_extension: bool}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = Profile.objects.filter(user=request.user).first()
        drafts = Generation.objects.filter(user=request.user)
        return Response({
            "profile_completeness": profile.completeness if profile else 0,
            "has_draft": drafts.exists(),
            "used_extension": drafts.filter(source="extension").exists(),
        })
