import pandas as pd 
from django.core.management.base import BaseCommand
from django.utils import timezone

from scraper.models import Job

class Command(BaseCommand):
    help = "exporte les jobs scrap vers fichier excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", type=str, default=None,
            help="Output file path. Default: jobs_DDMMYYYY_HHMM.xlsx",
        )

    def handle(self, *args, **options):
        output = options["output"] or self._default_filename()

        qs = (
            Job.objects
            .select_related("Company")
            .values(
                "id",
                "title",
                "company__name",
                "company__location",
                "location",
                "source_url",
                "scraped_at",
            )
        )

        df = pd.DataFrame(list(qs))

        if df.empty:
            self.sdtout.write(self.style.WARNING("No jobs to export."))
            return

        df = df.rename(columns={
            "company__name": "Company",
            "company__location": "Company Location",
            "title": "Job Title",
            "location": "Job Location",
            "source_url": "Source URL",
            "scraped_at": "Scraped At",
            "id": "ID",
        })

        df = df[[
            "ID", "Job Title", "Company", "Company Location",
            "Job Location", "Source URL", "Scraped At",
        ]]

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Jobs")

            # Auto-fit column widths (openpyxl-specific nicety).
            worksheet = writer.sheets["Jobs"]
            for column_cells in worksheet.columns:
                max_len = max(len(str(c.value)) for c in column_cells if c.value)
                col_letter = column_cells[0].column_letter
                worksheet.column_dimensions[col_letter].width = min(max_len + 2, 60)

        self.stdout.write(self.style.SUCCESS(
            f"Exported {len(df)} jobs to {output}"
        ))

    def _default_filename(self) -> str:
        stamp = timezone.now().strftime("%Y%m%d_%H%M")
        return f"jobs_{stamp}.xlsx"