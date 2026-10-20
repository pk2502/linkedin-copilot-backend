"""/api/contacts/: the outreach tracker."""
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contacts.models import Contact
from contacts.serializers import ContactSerializer, TouchSerializer
from contacts.services import find_or_create, normalize_linkedin_url, record_event

LIST_LIMIT = 200


def _with_latest_draft(qs):
    return qs.annotate(latest_draft_id=Max("generations__id", filter=Q(generations__parent__isnull=True)))


class ContactListView(APIView):
    """GET ?status=drafted|sent|replied|done &due=1 &search= -> contacts, newest activity first."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Contact.objects.filter(user=request.user)
        status_filter = request.query_params.get("status", "")
        if status_filter:
            if status_filter not in dict(Contact.STATUSES):
                raise ValidationError({"status": ["Unknown status."]})
            qs = qs.filter(status=status_filter)
        if request.query_params.get("due") == "1":
            qs = qs.filter(status=Contact.SENT, follow_up_on__lte=timezone.localdate())
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(company__icontains=search) | Q(notes__icontains=search))
        qs = _with_latest_draft(qs).order_by("-updated_at")[:LIST_LIMIT]
        return Response(ContactSerializer(qs, many=True).data)


class ContactDetailView(APIView):
    """PATCH {status?, outcome?, notes?, follow_up_on?, name?, company?, role?}; DELETE."""

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return get_object_or_404(_with_latest_draft(Contact.objects.filter(user=request.user)), pk=pk)

    def patch(self, request, pk):
        contact = self.get_object(request, pk)
        serializer = ContactSerializer(contact, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ContactSerializer(self.get_object(request, pk)).data)

    def delete(self, request, pk):
        self.get_object(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactLookupView(APIView):
    """GET ?linkedin_url= -> the contact for that profile, or 404."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        url = normalize_linkedin_url(request.query_params.get("linkedin_url", ""))
        if not url:
            raise ValidationError({"linkedin_url": ["Not a LinkedIn profile URL."]})
        contact = get_object_or_404(_with_latest_draft(Contact.objects.filter(user=request.user)), linkedin_url=url)
        return Response(ContactSerializer(contact).data)


class ContactTouchView(APIView):
    """POST {linkedin_url, name?, company?, role?, event: sent|replied} from the extension."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TouchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        url = normalize_linkedin_url(data["linkedin_url"])
        if not url:
            raise ValidationError({"linkedin_url": ["Not a LinkedIn profile URL."]})
        existing = Contact.objects.filter(user=request.user, linkedin_url=url).exists()
        if not existing and data["event"] == "replied":
            # A reply from someone we never wrote to is not outreach to track.
            return Response(status=status.HTTP_204_NO_CONTENT)
        contact = find_or_create(request.user, data.get("name", ""), data.get("company", ""), data.get("role", ""), url)
        if contact is None:
            raise ValidationError({"name": ["Needed for a new contact."]})
        record_event(contact, data["event"])
        contact = _with_latest_draft(Contact.objects.filter(pk=contact.pk)).get()
        return Response(ContactSerializer(contact).data)
