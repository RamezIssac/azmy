from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase, override_settings

from extraction.services.lv_parser import parse_lv_pages
from extraction.services.ocr import ocr_document
from extraction.services.pdf_text import PdfContent, PageText, read_pdf
from extraction.services.pipeline import classify_document, extract_document
from projects.models import Document, DocumentSet, Project

FIXTURES = Path(__file__).parent / "fixtures"
User = get_user_model()


def make_document(user, filename, doc_type, **kw) -> Document:
    project = Project.objects.create(name="T", created_by=user)
    ds = DocumentSet.objects.create(project=project, uploaded_by=user)
    with open(FIXTURES / filename, "rb") as f:
        return Document.objects.create(
            document_set=ds, file=File(f, name=filename),
            original_filename=filename, doc_type=doc_type, **kw,
        )


class ClassifyTest(TestCase):
    def test_lv_by_content(self):
        content = read_pdf(str(FIXTURES / "trockenbauarbeiten.pdf"))
        self.assertEqual(classify_document(content, "irgendwas.pdf"), "lv")

    def test_narrative_is_spec(self):
        content = read_pdf(str(FIXTURES / "interessenbekundungsverfahren-haus-der-gesundheit.pdf"))
        self.assertEqual(classify_document(content, "notice.pdf"), "spec")

    def test_gaeb_by_extension(self):
        content = read_pdf(str(FIXTURES / "interessenbekundungsverfahren-haus-der-gesundheit.pdf"))
        self.assertEqual(classify_document(content, "lv11.x83"), "gaeb")

    def test_plan_by_filename_when_no_text(self):
        content = read_pdf(str(FIXTURES / "scan_like.pdf"))
        self.assertEqual(classify_document(content, "grundrisse.pdf"), "plan")
        self.assertEqual(classify_document(content, "scan.pdf"), "plan")


@override_settings(OPENROUTER_API_KEY="")
class OcrTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="s@x.de", password="x", is_staff=True)

    def test_ocr_cache_and_content(self):
        doc = make_document(self.user, "scan_like.pdf", "spec")
        with mock.patch(
            "extraction.services.ocr.transcribe_page",
            side_effect=[
                "Seite eins: transkribierter Inhalt der ersten Seite",
                "Seite zwei: transkribierter Inhalt der zweiten Seite",
                "Seite drei: transkribierter Inhalt der dritten Seite",
            ],
        ) as t:
            content = ocr_document(doc)
        self.assertEqual(t.call_count, 3)
        self.assertEqual(content.pages[0].text, "Seite eins: transkribierter Inhalt der ersten Seite")
        self.assertEqual(content.text_coverage, 1.0)
        self.assertTrue(getattr(content, "ocr_applied", False))

        # second run: fully cached, no new transcriptions
        with mock.patch("extraction.services.ocr.transcribe_page") as t2:
            content2 = ocr_document(doc)
        self.assertEqual(t2.call_count, 0)
        self.assertEqual(content2.pages[1].text, "Seite zwei: transkribierter Inhalt der zweiten Seite")

    def test_scan_spec_via_ocr_gets_intelligence(self):
        """scan → OCR text → document_intel → extracted (not manual queue)."""
        doc = make_document(self.user, "scan_like.pdf", "spec")
        with mock.patch(
            "extraction.services.ocr.transcribe_page",
            side_effect=["Energieausweis für ein Wohngebäude, Seite 1",
                         "Energieausweis, Seite 2: Kennwerte",
                         "Energieausweis, Seite 3: Anlagen"],
        ), mock.patch(
            "extraction.services.llm.summarize_document",
            return_value={"document_kind": "Energieausweis", "summary": "…",
                          "key_facts": {"procedure_deadline": ""}},
        ):
            extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertTrue(doc.extraction_report.get("ocr"))
        self.assertEqual(
            doc.extraction_report["document_intel"]["document_kind"], "Energieausweis"
        )

    def test_ocr_empty_still_manual_queue(self):
        doc = make_document(self.user, "scan_like.pdf", "spec")
        with mock.patch("extraction.services.ocr.transcribe_page", return_value=""):
            extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.MANUAL_QUEUE)

    def test_auto_classify_routes_scanned_lv_through_ocr(self):
        """A scanned LV uploaded as 'auto': OCR → positions found → parsed."""
        doc = make_document(self.user, "scan_like.pdf", "auto")
        lv_page = (
            "Leistungsverzeichnis\nAufstellung der Leistungspositionen\n"
            " 01 LV Trockenbau\n01 Titel Wände\n"
            "10 Wand 100mm\nPosition Metallständerwand, Typ A\n100 m2 EP .... GP ....\n"
        )
        with mock.patch(
            "extraction.services.ocr.transcribe_page",
            side_effect=["Deckblatt des Bauvorhabens Projekt X", lv_page, "Anhang und sonstige Hinweise"],
        ), mock.patch("extraction.services.llm.extract_project_metadata", return_value={}), \
             mock.patch("extraction.services.llm.suggest_din276", return_value=""):
            extract_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertEqual(doc.extraction_report.get("auto_classified_as"), "lv")
        self.assertEqual(doc.lv.item_count, 1)
        from extraction.models import LVItem

        item = LVItem.objects.filter(section__lv=doc.lv).first()
        self.assertEqual(item.oz, "01.10")
