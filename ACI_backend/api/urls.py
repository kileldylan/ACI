from rest_framework.routers import DefaultRouter

from ACI_backend.api.views import (
    DeliveryDecisionViewSet,
    EvidenceViewSet,
    RepositoryViewSet,
    TestExecutionViewSet,
    VerificationRunViewSet,
    VerificationViewSet,
)

router = DefaultRouter()

router.register(
    "repositories",
    RepositoryViewSet,
    basename="repository",
)
router.register(
    "evidence",
    EvidenceViewSet,
    basename="evidence",
)
router.register(
    "verifications",
    VerificationViewSet,
    basename="verification",
)
router.register(
    "verification-runs",
    VerificationRunViewSet,
    basename="verification-run",
)
router.register(
    "test-executions",
    TestExecutionViewSet,
    basename="test-execution",
)
router.register(
    "delivery-decisions",
    DeliveryDecisionViewSet,
    basename="delivery-decision",
)

urlpatterns = router.urls
