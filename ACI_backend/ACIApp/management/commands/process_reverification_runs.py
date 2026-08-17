from django.core.management.base import BaseCommand

from ACI_backend.integrations.verification.service import (
    process_next_reverification_run,
)


class Command(BaseCommand):
    help = "Process queued ACI re-verification runs."

    def handle(self, *args, **options):
        processed = 0

        while process_next_reverification_run() is not None:
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} re-verification run(s)."
            )
        )
