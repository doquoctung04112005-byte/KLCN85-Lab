import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, UserProfile

from .models import Document


class DocumentAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department_a = Department.objects.create(code="A", name="Phòng A")
        cls.department_b = Department.objects.create(code="B", name="Phòng B")

        def make_user(username, role, department):
            user = get_user_model().objects.create_user(
                username=username, password="TestPass123!"
            )
            UserProfile.objects.create(
                user=user, role=role, department=department
            )
            return user

        cls.a1 = make_user("nhanvien_a1", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.a2 = make_user("nhanvien_a2", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.head_a = make_user(
            "truongphong_a", UserProfile.Role.DEPARTMENT_HEAD, cls.department_a
        )
        cls.b1 = make_user("nhanvien_b1", UserProfile.Role.EMPLOYEE, cls.department_b)
        cls.admin = make_user("admin_profile", UserProfile.Role.ADMIN, None)
        cls.no_department = make_user(
            "missing_department", UserProfile.Role.EMPLOYEE, None
        )
        cls.no_profile = get_user_model().objects.create_user(
            username="missing_profile", password="TestPass123!"
        )

        cls.a1_document = Document.objects.create(
            title="Tài liệu riêng A1",
            content="Nội dung riêng A1",
            owner=cls.a1,
            department=cls.department_a,
        )
        cls.a2_document = Document.objects.create(
            title="Tài liệu riêng A2",
            content="Nội dung riêng A2",
            owner=cls.a2,
            department=cls.department_a,
        )
        cls.head_document = Document.objects.create(
            title="Tài liệu trưởng phòng A",
            content="Nội dung trưởng phòng A",
            owner=cls.head_a,
            department=cls.department_a,
        )
        cls.b1_document = Document.objects.create(
            title="Tài liệu riêng B1",
            content="Nội dung riêng B1",
            owner=cls.b1,
            department=cls.department_b,
        )

    def detail_url(self, document):
        return reverse("document_detail", kwargs={"pk": document.pk})

    def edit_url(self, document):
        return reverse("document_edit", kwargs={"pk": document.pk})

    def test_anonymous_requests_redirect_to_login(self):
        urls = (
            reverse("document_list"),
            reverse("document_create"),
            self.detail_url(self.a1_document),
            self.edit_url(self.a1_document),
        )
        for url in urls:
            for method, data in (("get", None), ("post", {"title": "Lạ", "content": "Lạ"})):
                with self.subTest(method=method, url=url):
                    response = getattr(self.client, method)(url, data) if data else self.client.get(url)
                    self.assertRedirects(
                        response,
                        f"{reverse('login')}?next={url}",
                        fetch_redirect_response=False,
                    )
        self.a1_document.refresh_from_db()
        self.assertEqual(self.a1_document.title, "Tài liệu riêng A1")
        self.assertFalse(Document.objects.filter(title="Lạ").exists())

    def test_list_respects_owner_department_and_admin_role(self):
        all_documents = (
            self.a1_document,
            self.a2_document,
            self.head_document,
            self.b1_document,
        )
        cases = (
            (self.a1, (self.a1_document,)),
            (self.a2, (self.a2_document,)),
            (self.head_a, all_documents[:3]),
            (self.b1, (self.b1_document,)),
            (self.admin, all_documents),
        )
        for user, visible in cases:
            with self.subTest(username=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("document_list"))
                self.assertEqual(response.status_code, 200)
                for document in all_documents:
                    if document in visible:
                        self.assertContains(response, document.title)
                    else:
                        self.assertNotContains(response, document.title)
                self.client.logout()

    def test_detail_allows_owner_head_of_department_and_admin(self):
        cases = (
            (self.a2, self.a2_document),
            (self.head_a, self.a2_document),
            (self.admin, self.b1_document),
        )
        for user, document in cases:
            with self.subTest(username=user.username, document=document.pk):
                self.client.force_login(user)
                self.assertContains(self.client.get(self.detail_url(document)), document.content)
                self.client.logout()

    def test_other_employee_and_other_department_cannot_see_detail(self):
        cases = (
            (self.a1, self.a2_document),
            (self.a2, self.a1_document),
            (self.a1, self.b1_document),
            (self.head_a, self.b1_document),
            (self.b1, self.a1_document),
        )
        for user, document in cases:
            with self.subTest(username=user.username, document=document.pk):
                self.client.force_login(user)
                response = self.client.get(self.detail_url(document))
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(document.content, response.content.decode())
                self.client.logout()

    def test_owner_and_admin_can_edit_only_title_and_content(self):
        cases = (
            (self.a1, self.a1_document, self.a2, self.department_b),
            (self.head_a, self.head_document, self.a2, self.department_b),
            (self.admin, self.b1_document, self.a1, self.department_a),
        )
        for user, document, forged_owner, forged_department in cases:
            with self.subTest(username=user.username, document=document.pk):
                self.client.force_login(user)
                old_owner_id = document.owner_id
                old_department_id = document.department_id
                old_pk = document.pk
                old_role = user.profile.role
                edit_url = self.edit_url(document)
                get_response = self.client.get(edit_url)
                self.assertEqual(get_response.status_code, 200)
                self.assertEqual(set(get_response.context["form"].fields), {"title", "content"})

                response = self.client.post(
                    edit_url,
                    {
                        "title": f"Đã sửa bởi {user.username}",
                        "content": f"Nội dung sửa bởi {user.username}",
                        "owner": forged_owner.pk,
                        "department": forged_department.pk,
                        "id": str(uuid.uuid4()),
                        "role": UserProfile.Role.ADMIN,
                    },
                )
                self.assertEqual(response.status_code, 302)
                document.refresh_from_db()
                user.profile.refresh_from_db()
                self.assertEqual(document.title, f"Đã sửa bởi {user.username}")
                self.assertEqual(document.content, f"Nội dung sửa bởi {user.username}")
                self.assertEqual(document.pk, old_pk)
                self.assertEqual(document.owner_id, old_owner_id)
                self.assertEqual(document.department_id, old_department_id)
                self.assertEqual(user.profile.role, old_role)
                self.client.logout()

    def test_head_can_view_but_cannot_edit_employee_document(self):
        self.client.force_login(self.head_a)
        self.assertContains(
            self.client.get(self.detail_url(self.a2_document)),
            self.a2_document.content,
        )
        edit_url = self.edit_url(self.a2_document)
        get_response = self.client.get(edit_url)
        self.assertEqual(get_response.status_code, 403)
        self.assertNotIn(self.a2_document.content, get_response.content.decode())
        post_response = self.client.post(
            edit_url, {"title": "Sửa trái phép", "content": "Nội dung trái phép"}
        )
        self.assertEqual(post_response.status_code, 403)
        self.a2_document.refresh_from_db()
        self.assertEqual(self.a2_document.title, "Tài liệu riêng A2")
        self.assertEqual(self.a2_document.content, "Nội dung riêng A2")

    def test_edit_link_only_appears_when_user_can_edit(self):
        cases = (
            (self.a2, True),
            (self.head_a, False),
            (self.admin, True),
        )
        for user, can_edit in cases:
            with self.subTest(username=user.username):
                self.client.force_login(user)
                response = self.client.get(self.detail_url(self.a2_document))
                self.assertEqual(response.status_code, 200)
                if can_edit:
                    self.assertContains(response, self.edit_url(self.a2_document))
                else:
                    self.assertNotContains(response, self.edit_url(self.a2_document))
                self.client.logout()

    def test_employee_cannot_edit_other_owner_or_department(self):
        self.client.force_login(self.a1)
        for document in (self.a2_document, self.b1_document):
            with self.subTest(document=document.pk):
                edit_url = self.edit_url(document)
                self.assertEqual(self.client.get(edit_url).status_code, 404)
                response = self.client.post(
                    edit_url,
                    {"title": "Sửa trái phép", "content": "Nội dung trái phép"},
                )
                self.assertEqual(response.status_code, 404)
                document.refresh_from_db()
                self.assertNotEqual(document.title, "Sửa trái phép")

    def test_create_assigns_current_owner_and_department_despite_forged_post(self):
        self.client.force_login(self.a1)
        create_url = reverse("document_create")
        get_response = self.client.get(create_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(set(get_response.context["form"].fields), {"title", "content"})

        forged_id = uuid.uuid4()
        post_response = self.client.post(
            create_url,
            {
                "title": "Tài liệu mới của A1",
                "content": "Nội dung tài liệu mới",
                "owner": self.b1.pk,
                "department": self.department_b.pk,
                "id": str(forged_id),
                "role": UserProfile.Role.ADMIN,
            },
        )
        self.assertEqual(post_response.status_code, 302)
        document = Document.objects.get(title="Tài liệu mới của A1")
        self.a1.profile.refresh_from_db()
        self.assertEqual(document.owner_id, self.a1.pk)
        self.assertEqual(document.department_id, self.department_a.pk)
        self.assertNotEqual(document.pk, forged_id)
        self.assertEqual(self.a1.profile.role, UserProfile.Role.EMPLOYEE)

    def test_missing_profile_or_department_cannot_create(self):
        for user, guidance in (
            (self.no_profile, "hồ sơ"),
            (self.no_department, "phòng ban"),
            (self.admin, "phòng ban"),
        ):
            with self.subTest(username=user.username):
                self.client.force_login(user)
                create_url = reverse("document_create")
                self.assertContains(self.client.get(create_url), guidance, status_code=403)
                self.assertContains(
                    self.client.post(
                        create_url,
                        {"title": f"Không được tạo bởi {user.username}", "content": "x"},
                    ),
                    guidance,
                    status_code=403,
                )
                self.assertFalse(
                    Document.objects.filter(
                        title=f"Không được tạo bởi {user.username}"
                    ).exists()
                )
                self.client.logout()

    def test_missing_profile_cannot_see_documents(self):
        self.client.force_login(self.no_profile)
        response = self.client.get(reverse("document_list"))
        self.assertContains(response, "hồ sơ")
        for document in Document.objects.all():
            self.assertNotContains(response, document.title)
        self.assertEqual(self.client.get(self.detail_url(self.a1_document)).status_code, 404)
