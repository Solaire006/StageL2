from django.core.management.base import BaseCommand
from django.utils import timezone

from scraper.exporting import jobs_dataframe, write_workbook
from scraper.models import Job


class Command(BaseCommand):
    help = "exporte les jobs scrap vers fichier excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", type=str, default=None,
            help="Output file path. Default: jobs_YYYYMMDD_HHMM.xlsx",
        )

    def handle(self, *args, **options):
        output = options["output"] or f"jobs_{timezone.localtime():%Y%m%d_%H%M}.xlsx"
        df = jobs_dataframe(Job.objects.all())
        if df.empty:
            self.stdout.write(self.style.WARNING("No jobs to export."))
            return
        write_workbook(df, output)
        self.stdout.write(self.style.SUCCESS(f"Exported {len(df)} jobs to {output}"))
