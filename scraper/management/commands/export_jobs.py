import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from scraper.models import Job

EXCEL_CELL_LIMIT = 32000  # Excel max is 32767 chars per cell

COLUMNS = {
    "id": "ID",
    "title": "Job Title",
    "company__name": "Company",
    "location": "Job Location",
    "contract_type": "Contract Type",
    "published_date": "Published",
    "skills": "Skills",
    "requirements": "Requirements",
    "missions": "Missions",
    "description": "Description",
    "source_url": "Source URL",
    "scraped_at": "Scraped At",
}


class Command(BaseCommand):
    help = "exporte les jobs scrap vers fichier excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", type=str, default=None,
            help="Output file path. Default: jobs_YYYYMMDD_HHMM.xlsx",
        )

    def handle(self, *args, **options):
        output = options["output"] or self._default_filename()

        qs = Job.objects.values(*COLUMNS.keys())  # values() follows the FK itself
        df = pd.DataFrame(list(qs))
        if df.empty:
            self.stdout.write(self.style.WARNING("No jobs to export."))
            return

        # Excel can't store timezone-aware datetimes.
        df["scraped_at"] = (
            pd.to_datetime(df["scraped_at"])
            .dt.tz_convert(settings.TIME_ZONE)
            .dt.tz_localize(None)
        )
        for col in ("skills", "requirements", "missions", "description"):
            df[col] = df[col].fillna("").astype(str).str.slice(0, EXCEL_CELL_LIMIT)

        df = df[list(COLUMNS)].rename(columns=COLUMNS)

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Jobs")
            ws = writer.sheets["Jobs"]
            ws.freeze_panes = "A2"
            for column_cells in ws.columns:
                max_len = max((len(str(c.value)) for c in column_cells if c.value), default=8)
                ws.column_dimensions[column_cells[0].column_letter].width = min(max_len + 2, 60)

        self.stdout.write(self.style.SUCCESS(f"Exported {len(df)} jobs to {output}"))

    def _default_filename(self) -> str:
        return f"jobs_{timezone.localtime().strftime('%Y%m%d_%H%M')}.xlsx"
