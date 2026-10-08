from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Department, UserProfile


class AuthenticationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="A", name="Phòng A")
        other_department = Department.objects.create(code="B", name="Phòng B")

        cls.user = get_user_model().objects.create_user(
            username="sample_employee",
            password="TestPass123!",
        )
        UserProfile.objects.create(
            user=cls.user,
            role=UserProfile.Role.EMPLOYEE,
            department=cls.department,
        )

        other_user = get_user_model().objects.create_user(
            username="other_employee",
            password="TestPass123!",
        )
        UserProfile.objects.create(
            user=other_user,
            role=UserProfile.Role.DEPARTMENT_HEAD,
            department=other_department,
        )

        cls.user_without_profile = get_user_model().objects.create_user(
            username="missing_profile",
            password="TestPass123!",
        )

    def test_anonymous_visitors_are_sent_to_login(self):
        for name in ("dashboard", "profile"):
            with self.subTest(page=name):
                self.assertRedirects(
                    self.client.get(reverse(name)),
                    f"{reverse('login')}?next={reverse(name)}",
                    fetch_redirect_response=False,
                )

    def test_valid_login_shows_only_the_current_users_profile(self):
        response = self.client.post(
            reverse("login"),
            {"username": "sample_employee", "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("dashboard"))

        for name in ("dashboard", "profile"):
            with self.subTest(page=name):
                page = self.client.get(reverse(name))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "sample_employee")
                self.assertContains(page, "Nhân viên")
                self.assertContains(page, "Phòng A")
                self.assertNotContains(page, "other_employee")
                self.assertNotContains(page, "Phòng B")

    def test_invalid_password_does_not_log_in(self):
        response = self.client.post(
            reverse("login"),
            {"username": "sample_employee", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tên đăng nhập hoặc mật khẩu không đúng")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_missing_profile_shows_guidance_instead_of_server_error(self):
        self.client.force_login(self.user_without_profile)

        for name in ("dashboard", "profile"):
            with self.subTest(page=name):
                page = self.client.get(reverse(name))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "missing_profile")
                self.assertContains(page, "Quản trị viên cần bổ sung hồ sơ")

    def test_logout_requires_post_and_clears_session(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("login"))
        csrf_token = client.cookies["csrftoken"].value
        login_response = client.post(
            reverse("login"),
            {
                "username": "sample_employee",
                "password": "TestPass123!",
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        self.assertRedirects(login_response, reverse("dashboard"))
        self.assertEqual(client.get(reverse("logout")).status_code, 405)

        csrf_token = client.cookies["csrftoken"].value
        logout_response = client.post(
            reverse("logout"),
            {"csrfmiddlewaretoken": csrf_token},
        )
        self.assertRedirects(logout_response, reverse("login"))
        self.assertNotIn("_auth_user_id", client.session)

        for name in ("dashboard", "profile"):
            with self.subTest(page=name):
                self.assertEqual(client.get(reverse(name)).status_code, 302)
