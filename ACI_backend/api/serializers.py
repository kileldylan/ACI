from rest_framework import serializers

from ACI_backend.ACIApp.models import Repository



class RepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = [
            "id",
        "github_id",
            "owner",
            "name",
            "full_name",
            "default_branch",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]