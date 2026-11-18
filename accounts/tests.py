import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile

User = get_user_model()
PW = "S3cure-pass-phrase!"


def make_user(username="alice", email="alice@example.com", **kw):
    return User.objects.create_user(username, email=email, password=PW, **kw)


class AccessControlTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        for name in ("scraper:job_list", "scraper:export", "scraper:scrape_status"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), r["Location"])

    def test_next_parameter_is_kept(self):
        r = self.client.get(reverse("scraper:export"))
        self.assertIn("next=", r["Location"])

    def test_regular_user_can_browse_but_not_scrape(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("scraper:job_list")).status_code, 200)
        r = self.client.post(reverse("scraper:start_scrape"), {"pages": "1"})
        self.assertEqual(r.status_code, 403)

    def test_scrape_button_hidden_for_regular_user(self):
        self.client.force_login(make_user())
        self.assertNotContains(self.client.get(reverse("scraper:job_list")), "Lancer le scraping")

    @mock.patch("scraper.views.runner.start_scrape", return_value=True)
    def test_staff_can_scrape(self, start):
        self.client.force_login(make_user("boss", "boss@example.com", is_staff=True))
        r = self.client.post(reverse("scraper:start_scrape"), {"pages": "2"})
        self.assertEqual(r.status_code, 302)
        start.assert_called_once_with(max_pages=2)

    def test_anonymous_cannot_scrape(self):
        r = self.client.post(reverse("scraper:start_scrape"), {"pages": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_login_page_renders(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "Se connecter")

    def test_login_success_goes_to_job_list(self):
        r = self.client.post(reverse("accounts:login"), {"username": "alice", "password": PW})
        self.assertRedirects(r, reverse("scraper:job_list"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_follows_next(self):
        url = reverse("accounts:login") + "?next=" + reverse("scraper:export")
        r = self.client.post(url, {"username": "alice", "password": PW, "next": reverse("scraper:export")})
        self.assertEqual(r["Location"], reverse("scraper:export"))

    def test_wrong_password(self):
        r = self.client.post(reverse("accounts:login"), {"username": "alice", "password": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_post(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse("accounts:login"), {"username": "alice", "password": PW})
        self.assertNotIn("_auth_user_id", self.client.session)


class BruteForceTests(TestCase):
    def setUp(self):
        make_user()

    def test_lockout_after_repeated_failures(self):
        url = reverse("accounts:login")
        last = None
        for _ in range(5):
            last = self.client.post(url, {"username": "alice", "password": "wrong"})
        self.assertEqual(last.status_code, 429)
        self.assertContains(last, "Trop de tentatives", status_code=429)
        # even the right password is refused while locked
        r = self.client.post(url, {"username": "alice", "password": PW})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lockout_is_per_username(self):
        make_user("bob", "bob@example.com")
        url = reverse("accounts:login")
        for _ in range(5):
            self.client.post(url, {"username": "alice", "password": "wrong"})
        r = self.client.post(url, {"username": "bob", "password": PW})
        self.assertEqual(r.status_code, 302)  # bob is unaffected


class SecurityLogTests(TestCase):
    def setUp(self):
        make_user()

    def test_failed_login_logged_without_password(self):
        with self.assertLogs("security", level="INFO") as cm:
            self.client.post(reverse("accounts:login"), {"username": "alice", "password": "hunter2"})
        text = "\n".join(cm.output)
        self.assertIn('LOGIN_FAILED user="alice" ip=127.0.0.1', text)
        self.assertNotIn("hunter2", text)

    def test_success_and_logout_logged(self):
        with self.assertLogs("security", level="INFO") as cm:
            self.client.post(reverse("accounts:login"), {"username": "alice", "password": PW})
            self.client.post(reverse("accounts:logout"))
        text = "\n".join(cm.output)
        self.assertIn('LOGIN_OK user="alice"', text)
        self.assertIn('LOGOUT user="alice"', text)

    def test_lockout_logged(self):
        with self.assertLogs("security", level="INFO") as cm:
            for _ in range(5):
                self.client.post(reverse("accounts:login"), {"username": "alice", "password": "x"})
        self.assertIn("LOCKOUT", "\n".join(cm.output))


class SignupTests(TestCase):
    data = {"username": "newbie", "first_name": "Ny", "last_name": "Rakoto",
            "email": "Ny@Example.com", "password1": PW, "password2": PW}

    def test_signup_creates_user_profile_and_logs_in(self):
        r = self.client.post(reverse("accounts:signup"), self.data)
        self.assertRedirects(r, reverse("scraper:job_list"), fetch_redirect_response=False)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.email, "ny@example.com")  # normalised to lower case
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertFalse(user.is_staff)
        self.assertIn("_auth_user_id", self.client.session)

    def test_duplicate_email_rejected_case_insensitive(self):
        make_user(email="ny@example.com")
        r = self.client.post(reverse("accounts:signup"), self.data)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "déjà cette adresse")
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_password_mismatch_and_weak_password(self):
        r = self.client.post(reverse("accounts:signup"), {**self.data, "password2": "different"})
        self.assertFalse(User.objects.filter(username="newbie").exists())
        r = self.client.post(reverse("accounts:signup"),
                             {**self.data, "password1": "12345678", "password2": "12345678"})
        self.assertFalse(User.objects.filter(username="newbie").exists())

    @override_settings(ALLOW_SIGNUP=False)
    def test_signup_can_be_disabled(self):
        self.assertEqual(self.client.get(reverse("accounts:signup")).status_code, 404)
        self.assertEqual(self.client.post(reverse("accounts:signup"), self.data).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Créer un compte")


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_update(self):
        r = self.client.post(reverse("accounts:profile"), {
            "first_name": "Alice", "last_name": "R", "email": "new@example.com",
            "phone": "034 00 000 00", "skills": "Python\n\nDjango\n"})
        self.assertRedirects(r, reverse("accounts:profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.profile.skills_list, ["Python", "Django"])

    def test_cannot_take_someone_elses_email(self):
        make_user("bob", "bob@example.com")
        r = self.client.post(reverse("accounts:profile"), {
            "first_name": "A", "last_name": "B", "email": "BOB@example.com", "phone": "", "skills": ""})
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "alice@example.com")

    def test_profile_created_for_user_without_one(self):
        Profile.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())


class PasswordTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_change_password(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:password_change"), {
            "old_password": PW, "new_password1": "An0ther-strong-one!", "new_password2": "An0ther-strong-one!"})
        self.assertRedirects(r, reverse("accounts:password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("An0ther-strong-one!"))

    def test_change_password_wrong_old(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:password_change"), {
            "old_password": "bad", "new_password1": "An0ther-strong-one!", "new_password2": "An0ther-strong-one!"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PW))

    def test_reset_flow(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "alice@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://[^/\s]+(/\S+)", mail.outbox[0].body).group(1)
        r = self.client.get(link, follow=True)
        self.assertEqual(r.status_code, 200)
        set_url = r.redirect_chain[-1][0]
        r = self.client.post(set_url, {"new_password1": "Br4nd-new-secret!", "new_password2": "Br4nd-new-secret!"})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Br4nd-new-secret!"))

    def test_reset_unknown_email_does_not_leak(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))  # same answer
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_with_bad_token(self):
        r = self.client.get(reverse("accounts:password_reset_confirm", args=["abc", "bad-token"]))
        self.assertContains(r, "Lien invalide")


class AdminTests(TestCase):
    def test_superuser_sees_profile_inline_and_axes_logs(self):
        admin_user = User.objects.create_superuser("root", "root@example.com", PW)
        self.client.force_login(admin_user)
        r = self.client.get(reverse("admin:auth_user_change", args=[admin_user.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "profile-0-phone")
        self.assertEqual(self.client.get("/admin/axes/accessattempt/").status_code, 200)

    def test_regular_user_cannot_use_admin(self):
        self.client.force_login(make_user())
        r = self.client.get("/admin/")
        self.assertEqual(r.status_code, 302)


class ProxyHeaderNote(TestCase):
    def test_header_shows_user_menu(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("scraper:job_list"))
        self.assertContains(r, "Déconnexion")
        self.assertNotContains(r, "Administration")
