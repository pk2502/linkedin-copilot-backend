from rest_framework import serializers

from contacts.models import Contact


class ContactSerializer(serializers.ModelSerializer):
    follow_up_due = serializers.BooleanField(read_only=True)
    days_since_sent = serializers.IntegerField(read_only=True, allow_null=True)
    last_draft_id = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = [
            "id",
            "name",
            "company",
            "role",
            "linkedin_url",
            "status",
            "outcome",
            "notes",
            "sent_at",
            "replied_at",
            "follow_up_on",
            "follow_up_due",
            "days_since_sent",
            "last_draft_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "linkedin_url", "sent_at", "replied_at", "created_at", "updated_at"]

    def get_last_draft_id(self, contact):
        latest = getattr(contact, "latest_draft_id", None)
        return latest

    def update(self, contact, validated_data):
        status = validated_data.pop("status", None)
        if status and status != contact.status:
            if status == Contact.SENT:
                contact.mark_sent()
            elif status == Contact.REPLIED:
                contact.mark_replied()
            elif status == Contact.DONE:
                contact.mark_done()
            else:
                contact.status = status
                contact.follow_up_on = None
        return super().update(contact, validated_data)


class TouchSerializer(serializers.Serializer):
    linkedin_url = serializers.CharField(max_length=300)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    company = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.CharField(max_length=150, required=False, allow_blank=True)
    event = serializers.ChoiceField(choices=["sent", "replied"])
