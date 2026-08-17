from rest_framework.routers import DefaultRouter

from ACI_backend.api.views import (
    EvidenceViewSet,
    RepositoryViewSet,
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

urlpatterns = router.urls
