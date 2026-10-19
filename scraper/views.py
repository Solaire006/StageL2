from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Job


def job_list(request):
    qs = Job.objects.select_related("company")

    q = request.GET.get("q", "").strip()
    contract = request.GET.get("contract", "").strip()
    location = request.GET.get("location", "").strip()

    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(company__name__icontains=q)
            | Q(skills__icontains=q) | Q(description__icontains=q)
        )
    if contract:
        qs = qs.filter(contract_type=contract)
    if location:
        qs = qs.filter(location__icontains=location)

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
    })


def job_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related("company"), pk=pk)
    return render(request, "scraper/job_detail.html", {"job": job})
