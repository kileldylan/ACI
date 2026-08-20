from rest_framework import viewsets

from ACI_backend.ACIApp.models import (
    DeliveryDecision,
    Evidence,
    Repository,
    TestExecution,
    Verification,
    VerificationRun,
)
from ACI_backend.api.serializers import (
    DeliveryDecisionSerializer,
    EvidenceSerializer,
    RepositorySerializer,
    VerificationRunSerializer,
    TestExecutionSerializer,
    VerificationSerializer,
)
from ACI_backend.api.permissions import visible_repositories


class RepositoryViewSet(viewsets.ModelViewSet):
    serializer_class = RepositorySerializer

    def get_queryset(self):
        return visible_repositories(
            Repository.objects.all(),
            self.request.user,
        )

    def perform_create(self, serializer):
        repository = serializer.save()
        repository.members.add(self.request.user)


class EvidenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EvidenceSerializer

    def get_queryset(self):
        queryset = visible_repositories(
            Evidence.objects.select_related(
            "requirement",
            "pull_request",
            "commit",
            "changed_file",
            ).prefetch_related(
            "invalidations__triggering_changed_file",
            ).order_by("-updated_at"),
            self.request.user,
            membership_path="requirement__repository__members",
        )
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
        queryset = visible_repositories(
            Verification.objects.select_related(
            "requirement",
            "pull_request",
            ).prefetch_related(
            "evidence_links__evidence__invalidations__triggering_changed_file",
            "decisions",
            ).order_by("-created_at"),
            self.request.user,
            membership_path="requirement__repository__members",
        )
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
        queryset = visible_repositories(
            VerificationRun.objects.select_related(
            "verification",
            "triggering_changed_file",
            ).order_by("-requested_at"),
            self.request.user,
            membership_path="verification__requirement__repository__members",
        )
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        if repository_id:
            queryset = queryset.filter(
                verification__requirement__repository_id=repository_id,
            )
        if status:
            queryset = queryset.filter(status=status)
        return queryset


class TestExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TestExecutionSerializer

    def get_queryset(self):
        queryset = visible_repositories(
            TestExecution.objects.select_related(
            "verification_run",
            "commit",
            ).order_by("-created_at"),
            self.request.user,
            membership_path="verification_run__verification__requirement__repository__members",
        )
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        if repository_id:
            queryset = queryset.filter(
                verification_run__verification__requirement__repository_id=(
                    repository_id
                ),
            )
        if status:
            queryset = queryset.filter(status=status)
        return queryset


class DeliveryDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliveryDecisionSerializer

    def get_queryset(self):
        queryset = visible_repositories(
            DeliveryDecision.objects.select_related(
            "verification",
            "verification__requirement",
            "verification__pull_request",
            ).prefetch_related(
            "verification__evidence_links",
            "verification__decisions",
            ).order_by("-decided_at"),
            self.request.user,
            membership_path="verification__requirement__repository__members",
        )
        repository_id = self.request.query_params.get("repository")
        status = self.request.query_params.get("status")
        current = self.request.query_params.get("current")
        if repository_id:
            queryset = queryset.filter(
                verification__requirement__repository_id=repository_id,
            )
        if status:
            queryset = queryset.filter(status=status)
        if current is not None:
            queryset = queryset.filter(is_current=current.lower() == "true")
        return queryset
