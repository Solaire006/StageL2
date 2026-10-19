import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import runner
from .exporting import jobs_dataframe, write_workbook
from .models import Job

MAX_UI_PAGES = 10


def _filtered_jobs(params):
    qs = Job.objects.select_related("company")
    q = params.get("q", "").strip()
    contract = params.get("contract", "").strip()
    location = params.get("location", "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(company__name__icontains=q)
            | Q(skills__icontains=q) | Q(description__icontains=q)
        )
    if contract:
        qs = qs.filter(contract_type=contract)
    if location:
        qs = qs.filter(location__icontains=location)
    return qs, q, contract, location


def job_list(request):
    qs, q, contract, location = _filtered_jobs(request.GET)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "scraper/job_list.html", {
        "page": page,
        "total": page.paginator.count,
        "q": q, "contract": contract, "location": location,
        "contracts": (Job.objects.exclude(contract_type="")
                      .values_list("contract_type", flat=True).distinct().order_by("contract_type")),
        "querystring": params.urlencode(),
        "scrape": runner.get_state(),
    })


def job_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related("company"), pk=pk)
    return render(request, "scraper/job_detail.html", {"job": job})


def export_excel(request):
    """Download the jobs matching the current filters as .xlsx."""
    qs, *_ = _filtered_jobs(request.GET)
    df = jobs_dataframe(qs)
    if df.empty:
        messages.warning(request, "Aucune offre à exporter.")
        return redirect("scraper:job_list")
    buf = io.BytesIO()
    write_workbook(df, buf)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="jobs_{timezone.localtime():%Y%m%d_%H%M}.xlsx"'
    return resp


@require_POST
def start_scrape(request):
    try:
        pages = max(1, min(int(request.POST.get("pages", 1)), MAX_UI_PAGES))
    except ValueError:
        pages = 1
    if runner.start_scrape(max_pages=pages):
        messages.success(request, "Scraping lancé en arrière-plan.")
    else:
        messages.info(request, "Un scraping est déjà en cours.")
    return redirect("scraper:job_list")


def scrape_status(request):
    state = runner.get_state()
    state = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in state.items()}
    return JsonResponse(state)
