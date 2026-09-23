"""Register a receiver, inspect deliveries, and re-drive queued work."""
import argparse
import os
from urllib.parse import quote

from appointment_events import call


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register")
    register.add_argument("url")
    register.add_argument("event")
    deliveries = sub.add_parser("deliveries")
    deliveries.add_argument("webhook_id")
    redrive = sub.add_parser("redrive")
    redrive.add_argument("queue")
    args = parser.parse_args()
    if args.command == "register":
        result = call("POST", "/v1/account/webhooks/register", {
            "url": args.url,
            "events": [args.event],
            "secret": os.environ["WEBHOOK_SECRET"],
        })
    elif args.command == "deliveries":
        result = call("GET", "/v1/account/webhooks/deliveries/" + quote(args.webhook_id, safe=""))
    else:
        result = call("POST", "/v1/queue/dlq/redrive/" + quote(args.queue, safe=""),
                      {"idempotency_key": os.environ["REDRIVE_ID"]})
    print(result)


if __name__ == "__main__":
    main()
