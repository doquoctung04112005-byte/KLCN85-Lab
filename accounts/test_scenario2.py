from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserProfile


class ForcedBrowsingScenario2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="lab_user_a")
        UserProfile.objects.create(user=cls.employee, role=UserProfile.Role.EMPLOYEE)
        cls.admin = get_user_model().objects.create_user(username="lab_admin")
        UserProfile.objects.create(user=cls.admin, role=UserProfile.Role.ADMIN)

    def test_employee_force_browses_real_admin_account_directory(self):
        self.client.force_login(self.employee)

        page = self.client.get(reverse("user_list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "lab_admin")
        self.assertContains(page, "lab_user_a")

        # Reading the directory does not change the employee's stored role.
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)
        self.assertEqual(self.client.get(reverse("user_create")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("user_edit", args=[self.admin.pk])).status_code,
            403,
        )

    def test_anonymous_still_goes_to_login(self):
        self.assertRedirects(
            self.client.get(reverse("user_list")),
            f"{reverse('login')}?next={reverse('user_list')}",
            fetch_redirect_response=False,
        )

    def test_admin_reads_account_directory(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 200)

    @override_settings(DEBUG=False)
    def test_debug_off_does_not_restore_role_check(self):
        self.client.force_login(self.employee)
        page = self.client.get(reverse("user_list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "lab_admin")
