"""Excel export shared by the `export_jobs` command and the download view."""
import pandas as pd
from django.conf import settings

EXCEL_CELL_LIMIT = 32000

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


def jobs_dataframe(queryset) -> pd.DataFrame:
    df = pd.DataFrame(list(queryset.values(*COLUMNS.keys())))
    if df.empty:
        return df
    df["scraped_at"] = (
        pd.to_datetime(df["scraped_at"]).dt.tz_convert(settings.TIME_ZONE).dt.tz_localize(None)
    )
    for col in ("skills", "requirements", "missions", "description"):
        df[col] = df[col].fillna("").astype(str).str.slice(0, EXCEL_CELL_LIMIT)
    return df[list(COLUMNS)].rename(columns=COLUMNS)


def write_workbook(df: pd.DataFrame, target) -> None:
    """`target` is a path or a file-like object."""
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Jobs")
        ws = writer.sheets["Jobs"]
        ws.freeze_panes = "A2"
        for cells in ws.columns:
            longest = max((len(str(c.value)) for c in cells if c.value), default=8)
            ws.column_dimensions[cells[0].column_letter].width = min(longest + 2, 60)
