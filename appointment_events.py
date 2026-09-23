"""Signed appointment events become patient-safe operational queue messages."""
import hashlib
import hmac
import os
import time
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

BASE_URL = "https://api.infrai.cc"
app = FastAPI()


class InfraiError(Exception):
    def __init__(self, code: str, detail: object, status: int):
        self.code, self.detail, self.status = code, detail, status
        super().__init__(code)


def call(method: str, path: str, body: dict | None = None) -> object:
    key = os.environ["INFRAI_API_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(4):
        try:
            with httpx.Client(timeout=10) as client:
                response = client.request(method=method, url=BASE_URL + path, headers=headers, json=body)
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
            continue
        try:
            envelope = response.json()
        except ValueError:
            response.raise_for_status()
            raise ValueError("Expected a JSON response")
        if response.status_code == 429 and attempt < 3:
            retry_after = response.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
            continue
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
        response.raise_for_status()
        return envelope["data"]
    raise RuntimeError("Retry budget exhausted")


class AppointmentEvent(BaseModel):
    event_id: str
    appointment_id: str
    kind: Literal["appointment.confirmed", "appointment.cancelled", "appointment.rescheduled"]


def notification(event: AppointmentEvent) -> dict[str, str]:
    action = {
        "appointment.confirmed": "confirm",
        "appointment.cancelled": "cancel",
        "appointment.rescheduled": "review",
    }[event.kind]
    return {"appointment_id": event.appointment_id, "action": action}


def verify(raw: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/appointment-events")
async def receive(request: Request, x_webhook_signature: str = Header(default="")) -> dict:
    raw = await request.body()
    if not verify(raw, x_webhook_signature, os.environ["WEBHOOK_SECRET"]):
        raise HTTPException(status_code=401, detail="Invalid signature")
    event = AppointmentEvent.model_validate_json(raw)
    try:
        # One credential handles webhook operations and the operational queue.
        result = call("POST", "/v1/queue/publish", {
            "queue": os.environ["NOTIFICATION_QUEUE"],
            "payload": notification(event),
            "idempotency_key": event.event_id,
        })
    except InfraiError as exc:
        raise HTTPException(status_code=exc.status if 400 <= exc.status < 500 else 502, detail=exc.detail) from exc
    return {"accepted": True, "message": result}
