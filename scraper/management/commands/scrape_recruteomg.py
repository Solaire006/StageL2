import time 
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import transaction

from scraper.models import Company, Job

#url de test avant de passer a linkedin
BASE_URL = "https://recruteo.mg"
JOBS = "https://recruteo.mg/offres?recruteurs=1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Compatible; JobAutomatorBot/0.1; "
        "+https://github.com/your-team/job-automator)"
    ),
    "Accept-Language" : "fr-FR,fr;q=0.9,en;q=0.8",
}

class Command(BaseCommand):
    help = "scrape jobs from recruteo.mg"

   # def add_arguments(self, parser):
    #    parser.add_argument("--max-pages", type=int, default=1)

    def handle(self, *args, **options):
        self.stdout.write(f"fetching {JOBS}")
        html = self._fetch(JOBS)
        if html is None:
            return
        jobs = self._parse(html)
        saved = self._save(jobs)
        self.stdout.write(self.style.SUCCESS(f"{saved} new jobs saved."))

    def _fetch(self, url: str) -> str | None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            self.stderr.write(self.style.WARNING(f"failed {url}: {e}"))
            return None 

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('a[href^="/offres/annonce/"]')
        jobs = []
        for card in cards:
            company_el = card.select_one('span.truncate.text-sm.font-semibold')
            title_el = card.select_one('h3')
            location_el = card.select_one('div.mt-3.flex.items-center.gap-1\\.5')
            contract_el = card.select_one(
                'span[class*="bg-rose-100"], '
                'span[class*="bg-emerald-100"], '
                'span[class*="bg-sky-100"]'
            )
            date_el = card.select_one('div.mt-auto span.shrink-0')

            if not (title_el and company_el):
                continue

            jobs.append({
                "title": title_el.get_text(strip=True),
                "company": company_el.get_text(strip=True),
                "location": (
                    location_el.get_text(strip=True).replace("📍", "").strip()
                    if location_el else ""
                ),
                "contract_type": contract_el.get_text(strip=True) if contract_el else "",
                "published_date": date_el.get_text(strip=True) if date_el else "",
                "source_url": urljoin(BASE_URL, card["href"]),
            })
        return jobs
    
    @transaction.atomic
    def _save(self, jobs: list[dict]) -> int:
        new_count = 0
        for raw in jobs:
            company, _ = Company.objects.get_or_create(
                name=raw["company"],
                defaults={"location": raw["location"]},
            )
            _, created = Job.objects.update_or_create(
                source_url=raw["source_url"],
                defaults={
                    "company": company,
                    "title": raw["title"],
                    "location": raw["location"],
                    "contract_type": raw["contract_type"],
                    "published_date": raw["published_date"],
                },
        )
        if created:
            new_count += 1
        return new_count
