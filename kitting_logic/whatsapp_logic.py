"""
WhatsApp messaging logic — no ROS, no hardware dependency.

Fully testable and usable tonight: this doesn't touch the Dobot or the
lab camera at all. Get this working end-to-end before tomorrow.
"""
import os
from typing import List, Optional

import yaml


def format_missing_message(mode: str, missing: List[str]) -> str:
    if not missing:
        return f"[{mode}] Kit complete — all required items present."
    items = ", ".join(missing)
    return f"[{mode}] Still missing: {items}"


class WhatsAppNotifier:
    """
    Thin wrapper around the Twilio client so the rest of the code doesn't
    need to know Twilio's API directly, and so this class can be swapped
    for a fake/no-op version during testing without touching callers.
    """

    def __init__(self, account_sid: str, auth_token: str, from_whatsapp: str, to_whatsapp: str):
        from twilio.rest import Client  # imported here so this file still
        # loads even before you've pip-installed twilio, for testing the
        # rest of the logic in isolation.

        self._client = Client(account_sid, auth_token)
        self._from = from_whatsapp  # e.g. "whatsapp:+14155238886" (Twilio sandbox number)
        self._to = to_whatsapp      # e.g. "whatsapp:+91XXXXXXXXXX" (your phone, after joining the sandbox)

    def send(self, body: str) -> str:
        message = self._client.messages.create(body=body, from_=self._from, to=self._to)
        return message.sid


class FakeWhatsAppNotifier:
    """Drop-in stand-in for WhatsAppNotifier that just remembers what it was told to send.
    Useful for running the whole pipeline tonight without real Twilio credentials yet."""

    def __init__(self):
        self.sent: List[str] = []

    def send(self, body: str) -> str:
        self.sent.append(body)
        print(f"[FAKE WHATSAPP] {body}")
        return "fake-sid"


class RateLimitedNotifier:
    """
    Wraps any notifier (real or fake) and only actually sends when the
    message content has changed, or `min_interval` seconds have passed —
    so you don't spam WhatsApp every camera frame while items are missing.
    """

    def __init__(self, notifier, min_interval: float = 8.0):
        self._notifier = notifier
        self._min_interval = min_interval
        self._last_body: Optional[str] = None
        self._last_sent_at: float = 0.0

    def maybe_send(self, body: str, now: float) -> bool:
        changed = body != self._last_body
        stale = (now - self._last_sent_at) >= self._min_interval
        if changed or stale:
            self._notifier.send(body)
            self._last_body = body
            self._last_sent_at = now
            return True
        return False


def build_notifier(secrets_path: str, min_interval: float = 8.0):
    """
    Shared by whatsapp_node.py and demo_integration.py, so both behave
    the same way: if config/secrets.yaml exists with real Twilio details,
    use it and send REAL WhatsApp messages. Otherwise, safely fall back
    to printing what would have been sent.
    """
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            creds = (yaml.safe_load(f) or {}).get("twilio", {})
        try:
            real = WhatsAppNotifier(
                account_sid=creds["account_sid"],
                auth_token=creds["auth_token"],
                from_whatsapp=creds["from_whatsapp"],
                to_whatsapp=creds["to_whatsapp"],
            )
            print("[whatsapp] Found config/secrets.yaml — sending REAL WhatsApp messages.")
            return RateLimitedNotifier(real, min_interval=min_interval)
        except Exception as e:
            print(f"[whatsapp] config/secrets.yaml exists but failed to use it ({e}) "
                  f"— falling back to fake/printed messages.")

    print("[whatsapp] No config/secrets.yaml found — messages will only be printed, "
          "not really sent. Copy config/secrets.example.yaml to config/secrets.yaml "
          "and fill in your Twilio details to send real WhatsApp messages.")
    return RateLimitedNotifier(FakeWhatsAppNotifier(), min_interval=min_interval)
