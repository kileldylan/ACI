import json
import hashlib
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ACI_backend.integrations.github.service import process_pull_request_event


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

    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    event = request.headers.get("X-GitHub-Event")
    if event == "pull_request" and isinstance(payload, dict) and "repository" in payload and "pull_request" in payload:
        # delegate full processing (including commits) to the service layer
        process_pull_request_event(payload)

    return JsonResponse({"message": "Webhook received.", "event": event}, status=200)