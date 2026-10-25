from pathlib import Path

from fastapi.testclient import TestClient

from src.api import app
from src.config import Settings
from src.service import SupportService


ROOT = Path(__file__).parents[1]


def test_service_logs_each_decision(tmp_path):
    settings = Settings(
        data_dir=ROOT / "Capstone_Pack/05_Datasets",
        database_url=f"sqlite:///{tmp_path / 'decisions.db'}",
        auto_response_threshold=0.0, retrieval_threshold=0.0,
        llm_api_key=None, llm_base_url=None, llm_model="test",
    )
    service = SupportService(settings)
    result = service.process({"ticket_id": "TEST-1", "channel": "email", "subject": "login", "body": "invalid credentials"})
    assert result.decision_id is not None
    assert service.store.count() == 1


def test_bad_ticket_degrades_to_logged_escalation(tmp_path):
    settings = Settings(ROOT / "Capstone_Pack/05_Datasets", f"sqlite:///{tmp_path / 'decisions.db'}", .8, .08, None, None, "test")
    result = SupportService(settings).process({"ticket_id": "TEST-2", "channel": "phone"})
    assert result.action == "escalate"
    assert result.decision_id is not None


def test_api_exposes_health_and_ticket_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    import src.api as api
    api.service = None
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    response = client.post("/tickets", json={"ticket_id": "API-1", "channel": "chat", "subject": "", "body": "Cannot log in"})
    assert response.status_code == 200
    assert response.json()["action"] in {"auto_respond", "escalate", "block"}
