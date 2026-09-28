import time 
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import transaction

from scraper.models import Company, Job

#url de test avant de passer a linkedin
BASE_URL = "https://realpython.github.io/fake-jobs/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Compatible; JobAutomatorBot/0.1; "
        "+https://github.com/your-team/job-automator)"
}

class Command(BaseCommand):
    help = "Scrape fake jobs from the realpython.github.io/fake-jobs website and store them in the database."

    def add_arguments(self, parser):
        parser.add_arguments("--max-pages", type=int, default=1)

    def handle(self, *args, **options):
        max_pages = options["max_pages"]
        total_new = 0

        for page in range(1, max_pages + 1):
            url = BASE_URL if page == 1 else urljoin(BASE_URL, f"page/{page}/")
            self.stdout.write(f"Fetching {url}")
            html = self._fetch(url)
            jobs = self._parse(html)
            saved = self._save(jobs)
            total_new += saved
            self.stdout.write(self.style.SUCCESS(f" {saved} new jobs"))
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS(f"Done. {total_new} new jobs total."))

        def _fetch(self, url: str) -> str:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.text

        def _parse(self, html: str) -> list[dict]:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.card-content")
            jobs = []
            for card in cards:
                title_el = card.select_one("h2.title")
                company_el = card.select_one("h3.company")
                location_el = card.select_one("p.location")
                link_el = card.select_one("a[href]")

                if not (title_el and company_el):
                    continue

                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "location": location_el.get_text(strip=True) if location_el else "",
                    "source_url": urljoin(BASE_URL, link_el["href"]) if link_el else "",
                })
            return jobs

            @transaction.atomic
            def _save(self, jobs: list[dict]) -> int:
                new_count = 0
                for raw in jobs:
                    company, _ = Company.objects.get_or_create(
                        name=raw["comapny"],
                        defaults={"location": raw["location"]},
                    )
                    _, created = JobListing.objects.uptdate_or_create(
                        source_url=raw["source_url"],
                        defaults={
                            "company": company,
                            "title": raw["title"],
                            "location": raw["location"],
                        },
                )
                if created:
                    new_coutn += 1
            return new_count
            