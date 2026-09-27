from django.contrib.auth import get_user_model
from django.test import TestCase

from extraction.models import LV, LVItem, LVSection
from projects.models import Document, DocumentSet, Project

from .models import Bid, BidItem, Provider

User = get_user_model()


class BidFlowTest(TestCase):
    """End-to-end: staff-created provider bids on a published LV, staff levels."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(email="staff@x.de", password="x", is_staff=True)
        cls.puser = User.objects.create_user(email="bieter@trockenbau.de", password="x")
        cls.provider = Provider.objects.create(user=cls.puser, company="Trockenbau Müller")
        cls.project = Project.objects.create(name="Testprojekt", created_by=cls.staff)

        ds = DocumentSet.objects.create(project=cls.project, uploaded_by=cls.staff)
        cls.doc = Document.objects.create(
            document_set=ds, original_filename="lv.pdf", doc_type="lv",
            status=Document.Status.APPROVED,
        )
        lv = LV.objects.create(document=cls.doc, number="11", gewerk="Trockenbau")
        sec = LVSection.objects.create(lv=lv, kind="titel", number="01", title="Wände", ordering=1)
        cls.i1 = LVItem.objects.create(
            section=sec, number="10", oz="01.010", short_text="Wand 100mm",
            menge=100, einheit="m²", ordering=1,
        )
        cls.i2 = LVItem.objects.create(
            section=sec, number="20", oz="01.020", short_text="Wand 125mm",
            menge=50, einheit="m²", ordering=2,
        )

    def test_full_bid_cycle(self):
        # anonymous portal → login redirect
        self.assertEqual(self.client.get("/portal/").status_code, 302)

        # unpublished project: no bid editor
        self.client.login(email="bieter@trockenbau.de", password="x")
        self.assertEqual(self.client.get(f"/portal/bid/{self.project.slug}/").status_code, 404)

        # publish
        self.project.publish()
        r = self.client.get("/portal/")
        self.assertContains(r, "Testprojekt")

        # draft a bid: price i1, skip i2 (scope gap), German decimal comma
        r = self.client.post(
            f"/portal/bid/{self.project.slug}/",
            {f"price_{self.i1.pk}": "65,50", f"note_{self.i1.pk}": "inkl. Material"},
            follow=True,
        )
        bid = Bid.objects.get(project=self.project, provider=self.provider)
        self.assertEqual(bid.status, "draft")
        self.assertEqual(bid.items.count(), 1)
        self.assertEqual(float(bid.items.first().price), 65.50)

        # submit
        r = self.client.post(f"/portal/bid/{self.project.slug}/", {"submit": "1"}, follow=True)
        bid.refresh_from_db()
        self.assertEqual(bid.status, "submitted")
        self.assertIsNotNone(bid.submitted_at)
        # editor closed after submission
        self.assertEqual(self.client.get(f"/portal/bid/{self.project.slug}/").status_code, 302)

        # leveling (staff)
        self.client.login(email="staff@x.de", password="x")
        r = self.client.get(f"/projects/{self.project.slug}/bids/")
        self.assertContains(r, "Trockenbau Müller")
        self.assertContains(r, "65,50".replace(",", "."))  # prices render with dot in mono cells? no: floatformat uses dot

    def test_bid_total_and_gap(self):
        self.project.publish()
        bid = Bid.objects.create(project=self.project, provider=self.provider)
        BidItem.objects.create(bid=bid, lv_item=self.i1, price=10)
        self.assertEqual(float(bid.total), 1000.0)  # 10 € × 100 m²
        self.assertEqual(bid.priced_count, 1)

    def test_user_without_provider_profile_forbidden(self):
        User.objects.create_user(email="plain@x.de", password="x")
        self.client.login(email="plain@x.de", password="x")
        self.assertEqual(self.client.get("/portal/").status_code, 403)
