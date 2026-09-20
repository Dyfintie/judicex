from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from judicex_memory_os.web_app import create_app
except ModuleNotFoundError as exc:
    if exc.name == "flask":
        create_app = None
    else:
        raise


@unittest.skipIf(create_app is None, "Flask is not installed")
class WebAppTests(unittest.TestCase):
    def test_index_and_matter_api(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        app = create_app(db_path=Path(tempdir.name) / "memory.db", default_model="fake", default_area="civile")
        app.config.update(TESTING=True)
        client = app.test_client()

        index = client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn(b"Judicex", index.data)
        for path in ("/chat", "/onboarding", "/search", "/dashboard", "/documents", "/workflows", "/tables", "/drafts", "/tools", "/settings", "/provider-ai", "/memory", "/sources", "/security", "/backup"):
            self.assertEqual(client.get(path).status_code, 200)
        auth_status = client.get("/api/auth/status")
        self.assertEqual(auth_status.status_code, 200)
        self.assertFalse(auth_status.get_json()["configured"])
        bundles = client.get("/api/official-bundles")
        self.assertEqual(bundles.status_code, 200)
        self.assertIn("bundles", bundles.get_json())
        completed = client.post("/api/onboarding/complete", json={})
        self.assertEqual(completed.status_code, 200)
        self.assertTrue(completed.get_json()["onboarding"]["completed"])

        settings = client.get("/api/settings/llm")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("providers", settings.get_json()["settings"])
        ollama_provider = next(item for item in settings.get_json()["settings"]["providers"] if item["id"] == "ollama")
        self.assertIn("glm-5:cloud", ollama_provider["model_options"])
        updated_settings = client.patch(
            "/api/settings/llm",
            json={"provider": "none", "model": "", "base_url": ""},
        )
        self.assertEqual(updated_settings.status_code, 200)
        self.assertEqual(updated_settings.get_json()["settings"]["provider"], "none")

        memory = client.post(
            "/api/agent-memory",
            json={
                "kind": "preference",
                "title": "Stile recupero crediti",
                "content": "Usa tono pratico per recupero crediti B2B.",
                "tags": ["recupero_crediti"],
                "importance": 0.9,
            },
        )
        self.assertEqual(memory.status_code, 200)
        memory_id = memory.get_json()["memory"]["id"]
        memory_search = client.get("/api/search?q=recupero&scope=memory")
        self.assertEqual(memory_search.status_code, 200)
        self.assertTrue(any(item["id"] == memory_id for item in memory_search.get_json()["results"]))

        created = client.post(
            "/api/matters",
            json={"title": "Recupero credito Beta", "client_name": "Alfa", "area": "civile"},
        )
        self.assertEqual(created.status_code, 200)
        matter_id = created.get_json()["matter"]["id"]

        chat = client.post("/api/chat-sessions", json={"title": "Chat test", "matter_id": matter_id})
        self.assertEqual(chat.status_code, 200)
        chat_id = chat.get_json()["session"]["id"]
        message = client.post(f"/api/chat-sessions/{chat_id}/messages", json={"role": "user", "content": "Domanda demo"})
        self.assertEqual(message.status_code, 200)
        self.assertEqual(len(client.get(f"/api/chat-sessions/{chat_id}").get_json()["session"]["messages"]), 1)
        search = client.get("/api/search?q=Domanda")
        self.assertEqual(search.status_code, 200)
        self.assertTrue(any(item["type"] == "message" for item in search.get_json()["results"]))
        self.assertEqual(client.delete(f"/api/chat-sessions/{chat_id}").status_code, 200)

        context = client.get(f"/api/matters/{matter_id}/context")
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.get_json()["context"]["matter"]["id"], matter_id)
        matter_export = client.get(f"/api/matters/{matter_id}/export?format=docx")
        self.assertEqual(matter_export.status_code, 200)
        matter_zip = client.get(f"/api/matters/{matter_id}/export?format=zip")
        self.assertEqual(matter_zip.status_code, 200)
        artifact = client.post(
            "/api/artifacts",
            json={
                "title": "Diffida di pagamento",
                "content": "Oggetto: diffida di pagamento\n\nSpett.le Beta, pagare Euro 8.500.",
                "format": "docx",
                "session_id": chat_id,
                "matter_id": matter_id,
                "save_to_matter": True,
            },
        )
        self.assertEqual(artifact.status_code, 200)
        artifact_payload = artifact.get_json()
        artifact_id = artifact_payload["artifact"]["id"]
        self.assertEqual(artifact_payload["artifact"]["format"], "docx")
        self.assertIsNotNone(artifact_payload["document"])
        self.assertEqual(client.get(f"/api/artifacts/{artifact_id}").status_code, 200)
        artifact_docx = client.get(f"/api/artifacts/{artifact_id}/download?format=docx")
        self.assertEqual(artifact_docx.status_code, 200)
        self.assertIn("wordprocessingml.document", artifact_docx.headers["Content-Type"])
        artifact_pdf = client.get(f"/api/artifacts/{artifact_id}/download?format=pdf")
        self.assertEqual(artifact_pdf.status_code, 200)
        self.assertTrue(artifact_pdf.data.startswith(b"%PDF"))

        template = client.post(
            "/api/draft-templates",
            json={
                "title": "Atto semplice",
                "name": "atto semplice",
                "body": "Per {attore} contro {convenuto}.",
                "required_params": ["attore", "convenuto"],
            },
        )
        self.assertEqual(template.status_code, 200)
        template_id = template.get_json()["template"]["id"]
        assistant_draft = client.post(
            f"/api/matters/{matter_id}/drafts/assistant",
            json={
                "template_name": template_id,
                "instruction": "Prepara un atto semplice\nattore: Alfa\nconvenuto: Beta",
            },
        )
        self.assertEqual(assistant_draft.status_code, 200)
        self.assertEqual(assistant_draft.get_json()["draft"]["status"], "drafted")

        upload_path = Path(tempdir.name) / "memo.md"
        upload_path.write_text("Alfa S.r.l. deve pagare Euro 1200 entro 40 giorni.", encoding="utf-8")
        with upload_path.open("rb") as handle:
            uploaded = client.post(
                f"/api/matters/{matter_id}/documents",
                data={"files": (handle, "memo.md")},
                content_type="multipart/form-data",
            )
        self.assertEqual(uploaded.status_code, 200)
        upload_payload = uploaded.get_json()
        self.assertEqual(upload_payload["uploads"][0]["status"], "ok")
        self.assertGreaterEqual(upload_payload["uploads"][0]["facts_count"], 1)

        image_path = Path(tempdir.name) / "prova.png"
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is not installed")
        Image.new("RGB", (2, 3), color="white").save(image_path)
        with image_path.open("rb") as handle:
            image_uploaded = client.post(
                f"/api/matters/{matter_id}/documents",
                data={"files": (handle, "prova.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(image_uploaded.status_code, 200)
        image_payload = image_uploaded.get_json()
        image_result = image_payload["uploads"][0]
        self.assertEqual(image_result["status"], "ok")
        self.assertEqual(image_result["document"]["kind"], "image")
        self.assertEqual(image_result["document"]["metadata"]["width"], 2)
        self.assertTrue(Path(image_result["document"]["source_path"]).exists())

        deleted = client.delete(f"/api/matters/{matter_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(any(item["id"] == matter_id for item in deleted.get_json()["matters"]))
        self.assertEqual(client.get(f"/api/matters/{matter_id}").status_code, 404)

    def test_local_password_gate_when_configured(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        with patch.dict("os.environ", {"JUDICEX_LOCAL_PASSWORD": "secret-pass"}, clear=False):
            app = create_app(db_path=Path(tempdir.name) / "memory.db", default_model="fake", default_area="civile")
        app.config.update(TESTING=True)
        client = app.test_client()

        blocked = client.get("/api/state")
        self.assertEqual(blocked.status_code, 401)
        login = client.post("/api/auth/login", json={"password": "secret-pass"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(client.get("/api/state").status_code, 200)


if __name__ == "__main__":
    unittest.main()
