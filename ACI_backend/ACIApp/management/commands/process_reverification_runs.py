from django.core.management.base import BaseCommand

from ACI_backend.integrations.verification.llm import create_openai_evaluator
from ACI_backend.integrations.verification.service import (
    process_next_reverification_run,
    recover_stuck_reverification_runs,
)


class Command(BaseCommand):
    help = "Process queued ACI re-verification runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--evaluator",
            choices=["deterministic", "openai"],
            default="deterministic",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum runs to process; 0 means no limit.",
        )

    def handle(self, *args, **options):
        recover_stuck_reverification_runs()
        evaluator = None
        if options["evaluator"] == "openai":
            evaluator = create_openai_evaluator()
        processed = 0

        while (
            options["limit"] == 0 or processed < options["limit"]
        ) and process_next_reverification_run(evaluator=evaluator) is not None:
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} re-verification run(s)."
            )
        )
