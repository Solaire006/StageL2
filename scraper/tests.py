import os
import tempfile
from unittest import mock

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from scraper.models import Company, Job
from scraper.parsers import parse_detail

User = get_user_model()


def login_staff(testcase):
    """Log the test client in as a staff user (can view and start scrapes)."""
    user = User.objects.create_user("staff", password="pw-12345-xyz", is_staff=True)
    testcase.client.force_login(user)
    return user

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
    def setUp(self):
        login_staff(self)

    def test_scrape_counts_and_details(self, get, sleep):
        call_command("scrape_recruteomg")
        self.assertEqual(Job.objects.count(), 2)  # both new jobs saved
        job = Job.objects.get(title="Développeur Python")
        self.assertEqual(job.location, "Antananarivo")
        self.assertEqual(job.contract_type, "CDI")
        self.assertEqual(job.skills_list, ["Python", "SQL"])
        self.assertIsNotNone(job.detail_scraped_at)
        n_calls = get.call_count
        call_command("scrape_recruteomg")  # details already there -> only robots.txt + listing refetched
        self.assertEqual(get.call_count, n_calls + 2)
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


def _card(n, title, company="Acme"):
    return (f'<a href="/offres/annonce/{n}-x"><span class="truncate text-sm font-semibold">{company}</span>'
            f'<h3>{title}</h3></a>')


PAGES = {
    "1": _card(1, "Job 1") + _card(2, "Job 2"),
    "2": _card(3, "Job 3"),
    "3": _card(3, "Job 3"),  # site repeats the last page -> scraper must stop
}


def paged_get(url, **kw):
    r = mock.Mock()
    r.raise_for_status = lambda: None
    if "annonce" in url:
        r.text = DETAIL_HEADINGS
    else:
        r.text = PAGES.get(url.rsplit("page=", 1)[-1] if "page=" in url else "1", "")
    return r


@mock.patch("scraper.management.commands.scrape_recruteomg.time.sleep")
@mock.patch("scraper.management.commands.scrape_recruteomg.requests.get", side_effect=paged_get)
class PaginationTests(TestCase):
    def test_walks_pages_and_stops_on_repeat(self, get, sleep):
        call_command("scrape_recruteomg", max_pages=5, no_details=True)
        self.assertEqual(Job.objects.count(), 3)
        listing_calls = [c for c in get.call_args_list
                         if "annonce" not in c.args[0] and "robots.txt" not in c.args[0]]
        self.assertEqual(len(listing_calls), 3)  # pages 1, 2, then 3 (repeat) -> stop

    def test_default_is_one_page(self, get, sleep):
        call_command("scrape_recruteomg", no_details=True)
        self.assertEqual(Job.objects.count(), 2)


class UiActionTests(TestCase):
    def setUp(self):
        login_staff(self)
        c = Company.objects.create(name="Acme")
        Job.objects.create(company=c, title="Dev", contract_type="CDI", source_url="https://x.test/1")
        Job.objects.create(company=c, title="Ops", contract_type="CDD", source_url="https://x.test/2")

    def test_export_download_respects_filters(self):
        r = self.client.get(reverse("scraper:export"), {"contract": "CDI"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn("attachment", r["Content-Disposition"])
        path = os.path.join(tempfile.mkdtemp(), "d.xlsx")
        open(path, "wb").write(r.content)
        self.assertEqual(list(pd.read_excel(path)["Job Title"]), ["Dev"])

    def test_export_empty_redirects(self):
        r = self.client.get(reverse("scraper:export"), {"q": "nomatch"})
        self.assertRedirects(r, reverse("scraper:job_list"))

    def test_start_scrape_requires_post(self):
        self.assertEqual(self.client.get(reverse("scraper:start_scrape")).status_code, 405)

    @mock.patch("scraper.views.runner.start_scrape", return_value=True)
    def test_start_scrape_clamps_pages(self, start):
        r = self.client.post(reverse("scraper:start_scrape"), {"pages": "999"})
        self.assertRedirects(r, reverse("scraper:job_list"))
        start.assert_called_once_with(max_pages=10)

    @mock.patch("scraper.views.runner.start_scrape", return_value=False)
    def test_start_scrape_already_running(self, start):
        r = self.client.post(reverse("scraper:start_scrape"), {"pages": "2"}, follow=True)
        self.assertContains(r, "déjà en cours")

    def test_status_endpoint(self):
        self.assertIn("running", self.client.get(reverse("scraper:scrape_status")).json())


class RunnerTests(TestCase):
    @mock.patch("scraper.runner.connection")
    @mock.patch("scraper.runner.call_command")
    def test_run_success_and_failure(self, cmd, conn):
        from scraper import runner
        runner._state.update(running=True)
        runner._run(1)
        s = runner.get_state()
        self.assertFalse(s["running"]); self.assertTrue(s["ok"])

        cmd.side_effect = RuntimeError("boom")
        runner._state.update(running=True)
        runner._run(1)
        s = runner.get_state()
        self.assertFalse(s["ok"]); self.assertIn("boom", s["message"])

    @mock.patch("scraper.runner.threading.Thread")
    def test_only_one_at_a_time(self, thread):
        from scraper import runner
        runner._state.update(running=False)
        self.assertTrue(runner.start_scrape(1))
        self.assertFalse(runner.start_scrape(1))  # second call refused while running
        runner._state.update(running=False)


class RunningStateUiTest(TestCase):
    def setUp(self):
        login_staff(self)

    def test_list_shows_running_state_and_polls(self):
        from scraper import runner
        runner._state.update(running=True, message="")
        try:
            r = self.client.get(reverse("scraper:job_list"))
            self.assertContains(r, "Scraping en cours")
            self.assertContains(r, "setInterval")
            self.assertContains(r, "disabled")
        finally:
            runner._state.update(running=False)
        r = self.client.get(reverse("scraper:job_list"))
        self.assertContains(r, "Lancer le scraping")
        self.assertNotContains(r, "setInterval")


class RobotsTxtTests(TestCase):
    def test_disallowed_pages_are_not_fetched(self):
        def get(url, **kw):
            r = mock.Mock(status_code=200)
            r.raise_for_status = lambda: None
            r.text = "User-agent: *\nDisallow: /offres\n" if url.endswith("robots.txt") else LISTING
            return r
        with mock.patch("scraper.management.commands.scrape_recruteomg.requests.get",
                        side_effect=get) as g:
            call_command("scrape_recruteomg", no_details=True)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual([c.args[0] for c in g.call_args_list], ["https://recruteo.mg/robots.txt"])


class ExcelFormulaInjectionTests(TestCase):
    def test_scraped_formula_is_exported_as_plain_text(self):
        import openpyxl
        c = Company.objects.create(name="=1+1")
        Job.objects.create(company=c, title='=HYPERLINK("http://evil.test","clic")',
                           source_url="https://x.test/evil")
        path = os.path.join(tempfile.mkdtemp(), "e.xlsx")
        call_command("export_jobs", output=path)
        ws = openpyxl.load_workbook(path).active
        cells = [cell for row in ws.iter_rows(min_row=2) for cell in row]
        self.assertFalse([cell.coordinate for cell in cells if cell.data_type == "f"])
        self.assertIn('=HYPERLINK("http://evil.test","clic")', [cell.value for cell in cells])


class DeploymentTests(TestCase):
    def test_healthz_is_public(self):
        r = self.client.get("/healthz/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"ok")

    def test_custom_404_page(self):
        r = self.client.get("/does-not-exist/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Page introuvable", status_code=404)

    def test_production_refuses_to_start_without_secret_key(self):
        import subprocess, sys
        from django.conf import settings
        env = {**os.environ, "DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "",
               "DJANGO_LOG_DIR": tempfile.mkdtemp()}
        r = subprocess.run([sys.executable, "manage.py", "check"], cwd=settings.BASE_DIR,
                           env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY must be set", r.stderr)
