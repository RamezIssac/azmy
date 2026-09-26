import re

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class SignUpVerifyLoginTest(TestCase):
    def test_full_registration_flow(self):
        # 1. Sign up
        response = self.client.post(
            reverse("account_signup"),
            {"email": "user@example.com", "password1": "Str0ng!Pass", "password2": "Str0ng!Pass"},
        )
        self.assertEqual(response.status_code, 302)

        # 2. Verification email was queued (console backend counts as outbox in tests)
        email_address = EmailAddress.objects.get(email="user@example.com")
        self.assertFalse(email_address.verified)

        # 3. Click the verification link (simulate following the link from the email)
        key = EmailConfirmationHMAC(email_address).key
        response = self.client.post(reverse("account_confirm_email", args=[key]))
        self.assertEqual(response.status_code, 302)

        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

        # 4. Sign in and land on the home page
        response = self.client.post(
            reverse("account_login"),
            {"login": "user@example.com", "password": "Str0ng!Pass"},
        )
        self.assertRedirects(response, reverse("coming_soon"))

    def test_email_verification_via_outbox_link(self):
        # 1. Sign up — triggers the verification email
        self.client.post(
            reverse("account_signup"),
            {"email": "user@example.com", "password1": "Str0ng!Pass", "password2": "Str0ng!Pass"},
        )

        # 2. One email was sent and it's addressed correctly
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("user@example.com", email.to)

        # 3. Extract the confirmation path from the email body
        match = re.search(r"(/accounts/confirm-email/[^/\s]+/)", email.body)
        self.assertIsNotNone(match, "Confirmation URL not found in email body")
        confirm_path = match.group(1)

        # 4. Follow the link — email is now verified
        email_address = EmailAddress.objects.get(email="user@example.com")
        self.assertFalse(email_address.verified)

        response = self.client.post(confirm_path)
        self.assertEqual(response.status_code, 302)

        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)
