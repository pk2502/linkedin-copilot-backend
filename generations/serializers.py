from django.contrib.auth.models import User
from rest_framework import serializers
from generations.models import Generation


class GenerationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Generation
        fields = ["id", "generation_type", "input_data", "output", "created_at"]
        read_only_fields = ["id", "created_at"]
