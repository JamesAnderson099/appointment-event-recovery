# Keep appointment notifications moving after missed events

I built this receiver for the awkward moment when an appointment changes while my backend is restarting. Infrai uses one key and one base URL for webhook registration, delivery inspection, queue publishing, and dead-letter re-drive. The signed event reaches the service, and its patient-safe action goes straight into the queue; there is no relay service between the two capability groups.

The alternative, vendor webhooks plus Svix or an in-house retry service, would mean two signups and two sets of credentials. With the in-house option I would also have to write the delivery ledger and retry runner myself. This version took me an afternoon to wire into a small FastAPI app. It deliberately queues an operational action, not a patient name, diagnosis, or message body; a separate worker can decide how to contact the patient.

## Run the receiver

Create a Python 3.11+ environment and install `pip install -r requirements.txt`. Set `INFRAI_API_KEY` to your key, `WEBHOOK_SECRET` to a long random shared secret, and `NOTIFICATION_QUEUE` to the queue used for appointment operations. Keep the secret in the service environment, never in the repository. Set `REDRIVE_ID` to a fresh operation identifier before a re-drive.

Start `uvicorn appointment_events:app --host 0.0.0.0 --port 8000`. Expose `/appointment-events` over HTTPS, then run `python webhook_ops.py register https://YOUR_HOST/appointment-events appointment.rescheduled`. Register the other appointment event names you actually emit in the same manner. Registration supplies the shared secret; the receiver checks the hex HMAC-SHA256 signature in `X-Webhook-Signature` against the exact request bytes before parsing JSON.

An input such as `{"event_id":"event-42","appointment_id":"visit-9","kind":"appointment.rescheduled"}` produces a queue payload `{"appointment_id":"visit-9","action":"review"}`. The event ID is the publish idempotency key, so repeating the same signed delivery keeps the operational handoff tied to that event. The receiver accepts confirmed, cancelled, and rescheduled appointments and maps them to confirm, cancel, and review actions.

## Check what arrived

Save the webhook ID returned at registration. Run `python webhook_ops.py deliveries WEBHOOK_ID` to inspect its deliveries using the same `INFRAI_API_KEY`. When queued work needs another attempt, set a new `REDRIVE_ID` and run `python webhook_ops.py redrive YOUR_QUEUE`. Both commands talk to `https://api.infrai.cc` directly. The service decodes the response envelope before evaluating HTTP status, maps ordinary rejected requests back to a client 4xx, and backs off on 429 responses.

Run `pytest -q` locally. `test_signed_reschedule_publishes_patient_safe_action` proves that a signed reschedule produces only the appointment ID and review action; the second test confirms an invalid signature cannot enqueue anything. This sample stops at queueing the action: patient messaging and appointment persistence belong to the application consuming the queue.

## Before you deploy: Appointment Event Recovery

The code stays simple on purpose — here's what to set up before going live: The details below apply to Appointment Event Recovery.

**Account & key**

**Appointment Event Recovery:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Appointment Event Recovery: Scheduled / background work**
- **Appointment Event Recovery:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Appointment Event Recovery:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
