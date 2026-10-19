import os
import tempfile
from unittest import mock

import pandas as pd
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from scraper.models import Company, Job
from scraper.parsers import parse_detail

LISTING = """
<a href="/offres/annonce/1-dev"><span class="truncate text-sm font-semibold">Acme</span>
 <h3>Développeur Python</h3><div class="mt-3 flex items-center gap-1.5">📍 Antananarivo</div>
 <span class="bg-sky-100">CDI</span><div class="mt-auto"><span class="shrink-0">il y a 2 j</span></div></a>
<a href="/offres/annonce/2-ux"><span class="truncate text-sm font-semibold">Beta</span>
 <h3>Designer UX</h3><div class="mt-3 flex items-center gap-1.5">📍 Toamasina</div>
 <span class="bg-rose-100">CDD</span><div class="mt-auto"><span class="shrink-0">hier</span></div></a>
"""

DETAIL_JSONLD = """<html><head><script type="application/ld+json">
{"@type":"JobPosting","description":"<p>Build APIs.</p><ul><li>Django</li></ul>",
 "skills":"Python, Django; SQL","qualifications":"Bac+3","responsibilities":"Coder"}
</script></head><body></body></html>"""

DETAIL_HEADINGS = """<html><body><main><h1>Dev</h1>
<h2>Vos missions</h2><p>Développer des APIs</p>
<h2>Profil recherché</h2><p>Bac+3 informatique</p>
<h2>Compétences</h2><ul><li>Python</li><li>SQL</li></ul>
<h2>Autre</h2><p>ignored</p></main></body></html>"""


class ParserTests(TestCase):
    def test_jsonld(self):
        d = parse_detail(DETAIL_JSONLD)
        self.assertIn("Build APIs", d["description"])
        self.assertEqual(d["skills"].splitlines(), ["Python", "Django", "SQL"])
        self.assertEqual(d["requirements"], "Bac+3")

    def test_headings(self):
        d = parse_detail(DETAIL_HEADINGS)
        self.assertIn("APIs", d["missions"])
        self.assertIn("Bac+3", d["requirements"])
        self.assertEqual(d["skills"].splitlines(), ["Python", "SQL"])
        self.assertNotIn("ignored", d["skills"])


def fake_get(url, **kw):
    r = mock.Mock()
    r.raise_for_status = lambda: None
    r.text = LISTING if "offres?" in url else DETAIL_HEADINGS
    return r


@mock.patch("scraper.management.commands.scrape_recruteomg.time.sleep")
@mock.patch("scraper.management.commands.scrape_recruteomg.requests.get", side_effect=fake_get)
class ScrapeExportUiTests(TestCase):
    def test_scrape_counts_and_details(self, get, sleep):
        call_command("scrape_recruteomg")
        self.assertEqual(Job.objects.count(), 2)  # both new jobs saved
        job = Job.objects.get(title="Développeur Python")
        self.assertEqual(job.location, "Antananarivo")
        self.assertEqual(job.contract_type, "CDI")
        self.assertEqual(job.skills_list, ["Python", "SQL"])
        self.assertIsNotNone(job.detail_scraped_at)
        n_calls = get.call_count
        call_command("scrape_recruteomg")  # details already there -> only listing refetched
        self.assertEqual(get.call_count, n_calls + 1)
        self.assertEqual(Job.objects.count(), 2)

    def test_export(self, get, sleep):
        call_command("scrape_recruteomg")
        path = os.path.join(tempfile.mkdtemp(), "out.xlsx")
        call_command("export_jobs", output=path)
        df = pd.read_excel(path)
        self.assertEqual(len(df), 2)
        self.assertIn("Skills", df.columns)

    def test_export_empty(self, get, sleep):
        call_command("export_jobs", output="/tmp/never.xlsx")
        self.assertFalse(os.path.exists("/tmp/never.xlsx"))

    def test_views(self, get, sleep):
        call_command("scrape_recruteomg")
        r = self.client.get(reverse("scraper:job_list"))
        self.assertContains(r, "Développeur Python")
        r = self.client.get(reverse("scraper:job_list"), {"q": "designer"})
        self.assertContains(r, "Designer UX")
        self.assertNotContains(r, "Développeur Python")
        r = self.client.get(reverse("scraper:job_list"), {"contract": "CDI"})
        self.assertEqual(r.context["total"], 1)
        job = Job.objects.get(title="Développeur Python")
        r = self.client.get(reverse("scraper:job_detail", args=[job.pk]))
        self.assertContains(r, "Compétences requises")
        self.assertEqual(self.client.get(reverse("scraper:job_detail", args=[999])).status_code, 404)
