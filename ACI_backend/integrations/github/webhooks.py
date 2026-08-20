import json
import hashlib
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ACI_backend.integrations.github.service import (
    process_github_evidence_event,
    process_pull_request_event,
)

PULL_REQUEST_ACTIONS = {"opened", "reopened", "synchronize", "closed"}
CHECK_RUN_ACTIONS = {"created", "rerequested", "completed"}


@csrf_exempt
def github_webhook(request):
    """Django view that receives GitHub webhooks and dispatches processing.

    Verifies the `X-Hub-Signature-256` header using
    `settings.GITHUB_WEBHOOK_SECRET` and returns 401 on failure.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature or not signature.startswith("sha256="):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)

    webhook_secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return JsonResponse(
            {"detail": "Webhook secret is not configured."},
            status=503,
        )
    expected = "sha256=" + hmac.new(
        webhook_secret.encode(), request.body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    event = request.headers.get("X-GitHub-Event")
    if not isinstance(payload, dict) or not event:
        return JsonResponse({"detail": "Invalid webhook payload."}, status=400)

    try:
        if event == "pull_request":
            if not isinstance(payload.get("repository"), dict):
                return JsonResponse({"detail": "Invalid pull request payload."}, status=400)
            if not isinstance(payload.get("pull_request"), dict):
                return JsonResponse({"detail": "Invalid pull request payload."}, status=400)
            if payload.get("action") not in PULL_REQUEST_ACTIONS:
                return JsonResponse(
                    {"message": "Webhook action ignored.", "event": event},
                    status=202,
                )
            process_pull_request_event(payload)
        elif event == "check_run":
            if not isinstance(payload.get("repository"), dict):
                return JsonResponse({"detail": "Invalid check run payload."}, status=400)
            if payload.get("action") not in CHECK_RUN_ACTIONS:
                return JsonResponse(
                    {"message": "Webhook action ignored.", "event": event},
                    status=202,
                )
            process_github_evidence_event(event, payload)
        elif event == "status":
            if not isinstance(payload.get("repository"), dict):
                return JsonResponse({"detail": "Invalid status payload."}, status=400)
            process_github_evidence_event(event, payload)
        else:
            return JsonResponse(
                {"message": "Webhook event ignored.", "event": event},
                status=202,
            )
    except (KeyError, TypeError, ValueError):
        return JsonResponse({"detail": "Invalid webhook payload."}, status=400)

    return JsonResponse({"message": "Webhook received.", "event": event}, status=200)