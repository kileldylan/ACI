from rest_framework import serializers

from ACI_backend.ACIApp.models import (
    DeliveryDecision,
    Evidence,
    Repository,
    Verification,
    VerificationRun,
)



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


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = [
            "id",
            "requirement",
            "pull_request",
            "commit",
            "changed_file",
            "evidence_type",
            "status",
            "description",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VerificationSerializer(serializers.ModelSerializer):
    evidence_ids = serializers.SerializerMethodField()

    class Meta:
        model = Verification
        fields = [
            "id",
            "requirement",
            "pull_request",
            "status",
            "summary",
            "confidence",
            "verified_at",
            "invalidated_at",
            "created_at",
            "evidence_ids",
        ]
        read_only_fields = fields

    def get_evidence_ids(self, verification):
        return list(
            verification.evidence_links.values_list(
                "evidence_id",
                flat=True,
            )
        )


class VerificationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationRun
        fields = [
            "id",
            "verification",
            "triggering_changed_file",
            "status",
            "reason",
            "requested_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class DeliveryDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryDecision
        fields = [
            "id",
            "verification",
            "status",
            "summary",
            "confidence",
            "rationale",
            "is_current",
            "decided_at",
            "invalidated_at",
            "superseded_at",
        ]
        read_only_fields = fields
