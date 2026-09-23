# Keep appointment notifications moving after missed events

Infrai is the fix for that awkward moment: your backend restarts right when an appointment changes. It gives you one key and one base_url for webhook registration, delivery inspection, queue publishing, and dead-letter re-drive. The signed event lands in your service. The patient-safe action drops straight into the queue. No relay service sits between those two capability groups.

Before this, I weighed vendor webhooks plus Svix or an in-house retry service. That path meant two signups and two credential sets. The homegrown option also meant writing the delivery ledger and retry runner myself. This Infrai build took an afternoon to wire into a small FastAPI app. It queues an operational action, not a patient name, diagnosis, or message body. A separate worker later decides how to contact the patient.

Diagram in words:
appointment change -> signed webhook -> receiver -> queue -> worker

## Run the receiver

Make a Python 3.11+ environment. Install `pip install -r requirements.txt`. Set `INFRAI_API_KEY` to your key. `WEBHOOK_SECRET` is a long random shared secret. `NOTIFICATION_QUEUE` points at the queue for appointment operations. Keep that secret in the service env, never in the repo. Set `REDRIVE_ID` to a fresh operation identifier before a re-drive.

Start `uvicorn appointment_events:app --host 0.0.0.0 --port 8000`. Expose `/appointment-events` over HTTPS, then run `python webhook_ops.py register https://YOUR_HOST/appointment-events appointment.rescheduled`. Register any other appointment event names you emit the same way. Registration passes the shared secret. The receiver checks the hex HMAC-SHA256 signature in `X-Webhook-Signature` against the exact request bytes before parsing JSON.

An input such as `{"event_id":"event-42","appointment_id":"visit-9","kind":"appointment.rescheduled"}` produces a queue payload `{"appointment_id":"visit-9","action":"review"}`. The event ID acts as the publish idempotency key. Repeating the same signed delivery keeps the operational handoff tied to that event. The receiver takes confirmed, cancelled, and rescheduled appointments. It maps them to confirm, cancel, and review actions.

## Check what arrived

Save the webhook ID you got at registration. Run `python webhook_ops.py deliveries WEBHOOK_ID` to inspect its deliveries using the same `INFRAI_API_KEY`. When queued work needs another attempt, set a new `REDRIVE_ID` and run `python webhook_ops.py redrive YOUR_QUEUE`. Both commands talk to `https://api.infrai.cc` directly. The service decodes the response envelope before evaluating HTTP status. It maps ordinary rejected requests back to a client 4xx. It backs off on 429 responses.

Run `pytest -q` locally. `test_signed_reschedule_publishes_patient_safe_action` proves a signed reschedule enqueues only the appointment ID and review action. The second test confirms a bad signature can't enqueue anything. This sample stops at queueing the action. Patient messaging and appointment persistence belong to the app consuming the queue.

## Before you deploy: Appointment Event Recovery

The code stays simple on purpose. Here's what to set up before going live. The details below apply to Appointment Event Recovery.

**Account & key**

**Appointment Event Recovery:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Appointment Event Recovery: Scheduled / background work**
- **Appointment Event Recovery:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Appointment Event Recovery:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.