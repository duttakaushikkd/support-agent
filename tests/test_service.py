from pathlib import Path

from fastapi.testclient import TestClient

from src.api import app
from src.config import Settings
from src.service import SupportService
from src.persistence import DecisionLog
from evaluation.harness import _ground_truth_metrics, evaluate
import json
from sqlalchemy import select


ROOT = Path(__file__).parents[1]


def test_service_logs_each_decision(tmp_path):
    settings = Settings(
        data_dir=ROOT / "tests/fixtures",
        database_url=f"sqlite:///{tmp_path / 'decisions.db'}",
        auto_response_threshold=0.0, retrieval_threshold=0.0,
        llm_api_key=None, llm_base_url=None, llm_model="test",
    )
    service = SupportService(settings)
    result = service.process({"ticket_id": "TEST-1", "channel": "email", "subject": "login", "body": "invalid credentials"})
    assert result.decision_id is not None
    assert service.store.count() == 1
    with service.store.session_factory() as session:
        row = session.scalar(select(DecisionLog))
        assert row.stage == "routing"
        assert row.channel == "email"
        assert row.model_name
        assert row.model_version
        assert row.prompt_version == "generation-v1"
        assert json.loads(row.requirement_ids_json)


def test_bad_ticket_degrades_to_logged_escalation(tmp_path):
    settings = Settings(ROOT / "tests/fixtures", f"sqlite:///{tmp_path / 'decisions.db'}", .8, .08, None, None, "test")
    result = SupportService(settings).process({"ticket_id": "TEST-2", "channel": "phone"})
    assert result.action == "escalate"
    assert result.decision_id is not None


def test_api_exposes_health_and_ticket_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("DATA_DIR", str(ROOT / "tests/fixtures"))
    import src.api as api
    api.service = None
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert "fetch('/ticket'" in client.get("/").text
    assert client.get("/health").status_code == 200
    assert "support_tickets_processed_total" in client.get("/metrics").text
    response = client.post("/ticket", json={"ticket_id": "API-1", "channel": "chat", "subject": "", "body": "Cannot log in"})
    assert response.status_code == 200
    assert response.json()["action"] in {"auto_respond", "escalate", "block"}
    alias_response = client.post("/tickets", json={"ticket_id": "API-2", "channel": "forum", "body": "Need help"})
    assert alias_response.status_code == 200
    malformed = client.post("/ticket", json=None)
    assert malformed.status_code == 422
    invalid_json = client.post("/ticket", content=b"{malformed", headers={"Content-Type": "application/json"})
    assert invalid_json.status_code == 422


def test_kill_switch_forces_escalation_and_is_logged(tmp_path):
    disabled = tmp_path / "auto_response.disabled"
    disabled.touch()
    settings = Settings(
        data_dir=ROOT / "tests/fixtures",
        database_url=f"sqlite:///{tmp_path / 'kill.db'}",
        auto_response_threshold=0.0, retrieval_threshold=0.0,
        llm_api_key=None, llm_base_url=None, llm_model="test",
        auto_response_kill_switch_file=disabled,
    )
    result = SupportService(settings).process({
        "ticket_id": "KILL-1", "channel": "email", "subject": "Password reset",
        "body": "I cannot log in after resetting my password",
    })
    assert result.action == "escalate"
    assert result.guardrail_results["kill_switch"] == "block"


def test_harness_emits_metrics_and_reference_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'eval.db'}")
    monkeypatch.setenv("DATA_DIR", str(ROOT / "tests/fixtures"))
    incoming = tmp_path / "tickets.json"
    incoming.write_text(json.dumps([{
        "ticket_id": "FIX-1", "channel": "email", "subject": "Password reset",
        "body": "I cannot log in after resetting my password",
        "received_at": "2026-11-01T10:00:00Z", "replied_at": "2026-11-01T10:02:00Z",
        "history": {"first_contact_resolution": True, "repeat_contact": False, "csat_rating": 4.0},
    }]))
    report = evaluate(incoming, tmp_path / "out")
    assert report["volume"]["processed"] == 1
    assert report["governance"]["log_coverage"] == 1.0
    assert report["business"]["mean_first_reply_minutes"] == 2.0
    assert report["business"]["historical_ticket_outcomes"]["repeat_contact_rate"] == 0.0
    assert "system_first_contact_resolution" in report["business"]
    assert report["technical"]["ground_truth_response_checks"]["available"] is False
    assert (tmp_path / "out/decisions.json").exists()
    assert (tmp_path / "out/metrics.json").exists()


def test_ground_truth_phrase_checks_are_ticket_id_matched(tmp_path):
    reference_path = tmp_path / "ground_truth_responses.json"
    reference_path.write_text(json.dumps([{
        "ticket_id": "REF-1", "expected_doc_ids": ["DOC-1"],
        "must_mention": ["check the role"], "must_not_claim": ["refund issued"],
        "reference_response": "A full stylistic example.",
    }]))
    tickets = [{"ticket_id": "REF-1"}, {"ticket_id": "NO-MATCH"}]
    decisions = [{
        "action": "auto_respond", "answer": "Please check the role settings.",
        "sources": [{"doc_id": "DOC-1"}],
    }, {"action": "auto_respond", "answer": "refund issued", "sources": []}]
    metrics = _ground_truth_metrics(decisions, tickets, reference_path)
    assert metrics["matched_tickets"] == 1
    assert metrics["expected_document_hit_rate"] == 1.0
    assert metrics["must_mention_phrase_coverage"] == 1.0
    assert metrics["answers_with_exact_must_not_claim_phrase"] == 0
    assert metrics["reference_response_used_for_generation"] is False
