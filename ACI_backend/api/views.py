from rest_framework import viewsets

from ACI_backend.ACIApp.models import (
    Evidence,
    Repository,
    Verification,
    VerificationRun,
)
from ACI_backend.api.serializers import (
    EvidenceSerializer,
    RepositorySerializer,
    VerificationRunSerializer,
    VerificationSerializer,
)


class RepositoryViewSet(viewsets.ModelViewSet):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer


class EvidenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EvidenceSerializer

    def get_queryset(self):
        queryset = Evidence.objects.select_related(
            "requirement",
            "pull_request",
            "commit",
            "changed_file",
        ).order_by("-updated_at")
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        if repository_id:
            queryset = queryset.filter(requirement__repository_id=repository_id)
        if status:
            queryset = queryset.filter(status=status)
        return queryset


class VerificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VerificationSerializer

    def get_queryset(self):
        queryset = Verification.objects.select_related(
            "requirement",
            "pull_request",
        ).prefetch_related("evidence_links").order_by("-created_at")
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        if repository_id:
            queryset = queryset.filter(requirement__repository_id=repository_id)
        if status:
            queryset = queryset.filter(status=status)
        return queryset


class VerificationRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VerificationRunSerializer

    def get_queryset(self):
        queryset = VerificationRun.objects.select_related(
            "verification",
            "triggering_changed_file",
        ).order_by("-requested_at")
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        if repository_id:
            queryset = queryset.filter(
                verification__requirement__repository_id=repository_id,
            )
        if status:
            queryset = queryset.filter(status=status)
        return queryset
