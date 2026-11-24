"""4단계 회원 기능 테스트:  python manage.py test accounts"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
STRONG_PW = "VisionAction!2026"


class SignupLoginTests(TestCase):
    def test_signup_creates_normal_user(self):
        res = self.client.post(reverse("signup"), {
            "username": "member_a", "password1": STRONG_PW, "password2": STRONG_PW})
        self.assertRedirects(res, reverse("login"))
        user = User.objects.get(username="member_a")
        self.assertFalse(user.is_staff)

    def test_duplicate_username_rejected(self):
        User.objects.create_user("member_a", password=STRONG_PW)
        res = self.client.post(reverse("signup"), {
            "username": "member_a", "password1": STRONG_PW, "password2": STRONG_PW})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.filter(username="member_a").count(), 1)

    def test_password_mismatch_rejected(self):
        res = self.client.post(reverse("signup"), {
            "username": "member_b", "password1": STRONG_PW, "password2": STRONG_PW + "x"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(username="member_b").exists())

    def test_login_and_logout(self):
        User.objects.create_user("member_a", password=STRONG_PW)
        res = self.client.post(reverse("login"), {"username": "member_a", "password": STRONG_PW})
        self.assertRedirects(res, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("me")).status_code, 302)


class AccessControlTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        res = self.client.get(reverse("me"))
        self.assertRedirects(res, f"{reverse('login')}?next={reverse('me')}")

    def test_normal_user_cannot_open_admin(self):
        User.objects.create_user("member_a", password=STRONG_PW)
        self.client.login(username="member_a", password=STRONG_PW)
        res = self.client.get("/admin/")
        self.assertEqual(res.status_code, 302)             # 관리자 로그인 화면으로 돌려보냄

    def test_staff_can_open_admin(self):
        User.objects.create_superuser("boss", password=STRONG_PW)
        self.client.login(username="boss", password=STRONG_PW)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
