from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase, override_settings

from extraction.models import LV, LVItem
from extraction.services.pipeline import extract_document
from projects.models import Document, DocumentSet, Project

FIXTURES = Path(__file__).parent / "fixtures"


def make_document(user, filename, doc_type, run_judge=False) -> Document:
    project = Project.objects.create(name="Testprojekt", created_by=user)
    doc_set = DocumentSet.objects.create(project=project, uploaded_by=user)
    with open(FIXTURES / filename, "rb") as f:
        return Document.objects.create(
            document_set=doc_set,
            file=File(f, name=filename),
            original_filename=filename,
            doc_type=doc_type,
            run_judge=run_judge,
        )


@override_settings(OPENROUTER_API_KEY="")  # deterministic: no LLM calls in tests
class PipelineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="staff@example.com", password="x", is_staff=True
        )

    def test_pdf_pipeline(self):
        doc = make_document(self.user, "trockenbauarbeiten.pdf", "lv")
        extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertEqual(doc.page_count, 90)
        self.assertEqual(doc.lv.item_count, 178)
        self.assertEqual(doc.extraction_report["section_count"], 12)
        # provenance: every item carries page refs
        for item in LVItem.objects.filter(section__lv=doc.lv):
            self.assertIsNotNone(item.page_start)

    def test_pdf_pipeline_with_judge_failure_still_succeeds(self):
        """Judge crashes (e.g. serialization) must not fail the extraction."""
        from unittest import mock

        doc = make_document(self.user, "trockenbauarbeiten.pdf", "lv", run_judge=True)
        with mock.patch(
            "extraction.services.llm.judge_extraction",
            side_effect=TypeError("Object of type Decimal is not JSON serializable"),
        ):
            extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertEqual(doc.lv.item_count, 178)
        self.assertIn("judge", doc.extraction_report)

    def test_gaeb_import(self):
        doc = make_document(self.user, "sample.x83", "gaeb")
        extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        lv = doc.lv
        self.assertEqual(lv.number, "11")
        self.assertEqual(lv.gewerk, "Trockenbauarbeiten")
        items = LVItem.objects.filter(section__lv=lv).order_by("ordering")
        self.assertEqual(items.count(), 2)
        first = items.first()
        self.assertEqual(first.oz, "02.01.0010")
        self.assertEqual(float(first.menge), 6900.0)
        self.assertEqual(first.einheit, "m2")
        self.assertEqual(first.source, LVItem.Source.GAEB)
        # priced item keeps prices
        second = items.last()
        self.assertEqual(float(second.unit_price), 65.50)
        self.assertEqual(float(second.total_price), 5240.00)
        # section nesting preserved
        untertitel = first.section
        self.assertEqual(untertitel.kind, "untertitel")
        self.assertEqual(untertitel.parent.kind, "titel")

    def test_scan_goes_to_manual_queue(self):
        doc = make_document(self.user, "scan_like.pdf", "lv")
        extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.MANUAL_QUEUE)
        self.assertFalse(LV.objects.filter(document=doc).exists())

    def test_narrative_doc_as_lv_is_not_garbage_parsed(self):
        """A notice/procedure PDF has no position table: manual queue, no items."""
        doc = make_document(
            self.user, "interessenbekundungsverfahren-haus-der-gesundheit.pdf", "lv"
        )
        extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.MANUAL_QUEUE)
        self.assertIn(
            "no LV position table", doc.extraction_report.get("reason", "")
        )
        self.assertFalse(LV.objects.filter(document=doc).exists())

    def test_narrative_doc_as_spec_is_summarized(self):
        """Non-LV docs with text get an LLM document_intel summary."""
        from unittest import mock

        doc = make_document(
            self.user, "interessenbekundungsverfahren-haus-der-gesundheit.pdf", "spec"
        )
        fake = {
            "document_kind": "Interessenbekundungsverfahren",
            "title": "Haus der Gesundheit",
            "summary": "…",
            "key_facts": {"deadlines": [], "contact": "", "scope": ""},
        }
        with mock.patch(
            "extraction.services.llm.summarize_document", return_value=fake
        ):
            extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertEqual(
            doc.extraction_report["document_intel"]["document_kind"],
            "Interessenbekundungsverfahren",
        )

    def test_scan_spec_goes_to_manual_queue(self):
        doc = make_document(self.user, "scan_like.pdf", "spec")
        extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.MANUAL_QUEUE)


@override_settings(OPENROUTER_API_KEY="")
class PublishFlowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="staff2@example.com", password="x", is_staff=True
        )

    def test_approve_publish_public_api(self):
        doc = make_document(self.user, "sample.x83", "gaeb")
        extract_document(doc)
        project = doc.document_set.project

        client = self.client
        self.assertTrue(client.login(email="staff2@example.com", password="x"))

        # publish requires an approved LV
        resp = client.post(f"/projects/{project.slug}/publish/", follow=True)
        project.refresh_from_db()
        self.assertFalse(project.is_published)

        resp = client.post(f"/extraction/documents/{doc.pk}/approve/", follow=True)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.APPROVED)

        resp = client.post(f"/projects/{project.slug}/publish/", follow=True)
        project.refresh_from_db()
        self.assertTrue(project.is_published)

        # review UI renders the extracted tree
        resp = client.get(f"/extraction/documents/{doc.pk}/review/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "02.01.0010")

        # public JSON API via token
        resp = client.get(f"/api/v1/p/{project.public_token}/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["name"], "Testprojekt")
        lv = payload["lvs"][0]
        self.assertEqual(lv["gewerk"], "Trockenbauarbeiten")
        section = lv["sections"][0]["sections"][0]
        self.assertEqual(section["items"][0]["oz"], "02.01.0010")

        # public HTML
        resp = client.get(f"/p/{project.public_token}/")
        self.assertContains(resp, "Metallständerwand")

        # unpublish closes the door
        client.post(f"/projects/{project.slug}/unpublish/", follow=True)
        self.assertEqual(client.get(f"/api/v1/p/{project.public_token}/").status_code, 404)

    def test_staff_gating(self):
        doc = make_document(self.user, "sample.x83", "gaeb")
        # anonymous users get redirected away from staff views
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(f"/documents/{doc.pk}/file/")
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(f"/extraction/documents/{doc.pk}/review/")
        self.assertEqual(resp.status_code, 302)

    def test_private_file_download(self):
        """file.url must actually serve the file (regression: PrivateStorage
        pointed at /media/ where the files are not)."""
        doc = make_document(self.user, "sample.x83", "gaeb")
        client = self.client
        self.assertTrue(client.login(email="staff2@example.com", password="x"))

        # via file.url (admin links, templates)
        resp = client.get(doc.file.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Content-Type"], "application/xml")
        content = b"".join(resp.streaming_content)
        self.assertIn(b"<GAEB", content)

        # via the pk-based view
        resp = client.get(f"/documents/{doc.pk}/file/", follow=True)
        self.assertEqual(resp.status_code, 200)

        # traversal + unknown files are refused
        resp = client.get("/files/../manage.py/")
        self.assertIn(resp.status_code, (400, 404))
        resp = client.get("/files/projects/999/set-9/nope.pdf/")
        self.assertEqual(resp.status_code, 404)
