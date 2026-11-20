import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from scraper.models import Company, Job
from scraper.parsers import parse_detail

#url de test avant de passer a linkedin
BASE_URL = "https://recruteo.mg"
JOBS = "https://recruteo.mg/offres?recruteurs=1"
HEADERS = {
    "User-Agent": settings.SCRAPER_USER_AGENT,  # set in config/settings.py
    "Accept-Language" : "fr-FR,fr;q=0.9,en;q=0.8",
}

class Command(BaseCommand):
    help = "scrape jobs from recruteo.mg"

    def add_arguments(self, parser):
        parser.add_argument("--max-pages", type=int, default=1,
                            help="Number of listing pages to scrape (default 1).")
        parser.add_argument("--page-param", type=str, default="page",
                            help="Query-string parameter used for pagination (default 'page').")
        parser.add_argument("--no-details", action="store_true",
                            help="Only scrape the listing page, skip detail pages.")
        parser.add_argument("--refresh-details", action="store_true",
                            help="Re-scrape details even for jobs that already have them.")
        parser.add_argument("--delay", type=float, default=1.0,
                            help="Seconds to wait between detail requests (default 1).")

    def handle(self, *args, **options):
        self._robots = {}  # one robots.txt per site, fetched once per run
        jobs = self._scrape_listing(options["max_pages"], options["page_param"])
        if not jobs:
            self.stderr.write(self.style.WARNING("no jobs found."))
            return
        self.stdout.write(f"{len(jobs)} jobs found")
        saved = self._save(jobs)
        self.stdout.write(self.style.SUCCESS(f"{saved} new jobs saved."))

        if not options["no_details"]:
            done = self._scrape_details(
                [j["source_url"] for j in jobs],
                refresh=options["refresh_details"],
                delay=options["delay"],
            )
            self.stdout.write(self.style.SUCCESS(f"details scraped for {done} jobs."))

    def _scrape_listing(self, max_pages: int, page_param: str) -> list[dict]:
        """Walk the listing pages; stop at max_pages or when a page adds nothing new."""
        seen, jobs = set(), []
        for page in range(1, max_pages + 1):
            url = JOBS if page == 1 else f"{JOBS}&{page_param}={page}"
            self.stdout.write(f"fetching {url}")
            html = self._fetch(url)
            if html is None:
                break
            fresh = [j for j in self._parse(html) if j["source_url"] not in seen]
            if not fresh:
                break  # empty page, or the site ignored our page parameter
            seen.update(j["source_url"] for j in fresh)
            jobs.extend(fresh)
            if page < max_pages:
                time.sleep(1)
        return jobs

    def _allowed(self, url: str) -> bool:
        """Respect the site's robots.txt. If it can't be read (404, network
        error) we assume everything is allowed, as browsers and search engines do."""
        parts = urlsplit(url)
        site = f"{parts.scheme}://{parts.netloc}"
        if site not in self._robots:
            rp = RobotFileParser()
            try:
                r = requests.get(f"{site}/robots.txt", headers=HEADERS, timeout=10)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[site] = rp
        return self._robots[site].can_fetch(HEADERS["User-Agent"], url)

    def _fetch(self, url: str) -> str | None:
        if not self._allowed(url):
            self.stderr.write(self.style.WARNING(f"skipped {url}: disallowed by robots.txt"))
            return None
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
            company, _ = Company.objects.get_or_create(name=raw["company"])
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

    def _scrape_details(self, urls: list[str], refresh: bool, delay: float) -> int:
        qs = Job.objects.filter(source_url__in=urls)
        if not refresh:
            qs = qs.filter(detail_scraped_at__isnull=True)
        done = 0
        for job in qs:
            time.sleep(delay)
            html = self._fetch(job.source_url)
            if html is None:
                continue  # leave detail_scraped_at empty so it is retried next run
            detail = parse_detail(html)
            if not any(detail.values()):
                self.stderr.write(self.style.WARNING(
                    f"no details found on {job.source_url} (page layout changed?)"))
            job.description = detail["description"]
            job.missions = detail["missions"]
            job.requirements = detail["requirements"]
            job.skills = detail["skills"]
            job.detail_scraped_at = timezone.now()
            job.save()
            done += 1
        return done
