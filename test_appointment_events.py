import hashlib
import hmac
import json

from fastapi.testclient import TestClient

import appointment_events


def test_signed_reschedule_publishes_patient_safe_action(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("NOTIFICATION_QUEUE", "appointment-ops")
    sent = []
    monkeypatch.setattr(appointment_events, "call", lambda method, path, body: sent.append((method, path, body)) or {"message_id": "m1"})
    body = json.dumps({"event_id": "event-42", "appointment_id": "visit-9", "kind": "appointment.rescheduled"}).encode()
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    response = TestClient(appointment_events.app).post("/appointment-events", content=body, headers={"X-Webhook-Signature": signature})
    assert response.status_code == 200
    assert sent == [("POST", "/v1/queue/publish", {
        "queue": "appointment-ops", "payload": {"appointment_id": "visit-9", "action": "review"},
        "idempotency_key": "event-42",
    })]


def test_bad_signature_never_publishes(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(appointment_events, "call", lambda *args: (_ for _ in ()).throw(AssertionError("published")))
    response = TestClient(appointment_events.app).post("/appointment-events", content=b"{}", headers={"X-Webhook-Signature": "bad"})
    assert response.status_code == 401
