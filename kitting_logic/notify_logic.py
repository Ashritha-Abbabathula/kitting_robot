"""
Notification logic — no ROS, no hardware dependency.

Sends plain email instead of SMS/WhatsApp: no Twilio account, no sandbox,
no trial limits, no phone verification. Just your own email address and
an "app password" from your provider (see config/secrets.example.yaml for
exactly how to get one from Gmail).

Fully testable and usable tonight: this doesn't touch the Dobot or the
lab camera at all.
"""
import os
import smtplib
from email.mime.text import MIMEText
from typing import List, Optional

import yaml


def format_missing_message(mode: str, missing: List[str]) -> str:
    if not missing:
        return f"[{mode}] Kit complete — all required items present."
    items = ", ".join(missing)
    return f"[{mode}] Still missing: {items}"


class EmailNotifier:
    """
    Sends a real email via SMTP. Works with Gmail out of the box (using
    an App Password, not your normal password); any other provider that
    exposes SMTP works too if you change smtp_server/smtp_port.
    """

    def __init__(self, smtp_server: str, smtp_port: int, sender_email: str,
                 sender_password: str, receiver_email: str):
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port
        self._sender_email = sender_email
        self._sender_password = sender_password
        self._receiver_email = receiver_email

    def send(self, body: str) -> str:
        msg = MIMEText(body)
        msg["Subject"] = "Kitting Robot Alert"
        msg["From"] = self._sender_email
        msg["To"] = self._receiver_email

        with smtplib.SMTP_SSL(self._smtp_server, self._smtp_port) as server:
            server.login(self._sender_email, self._sender_password)
            server.sendmail(self._sender_email, [self._receiver_email], msg.as_string())
        return "sent"


class FakeEmailNotifier:
    """Drop-in stand-in for EmailNotifier that just remembers what it was told to send.
    Useful for running the whole pipeline without real email credentials yet."""

    def __init__(self):
        self.sent: List[str] = []

    def send(self, body: str) -> str:
        self.sent.append(body)
        print(f"[FAKE EMAIL] {body}")
        return "fake-id"


class RateLimitedNotifier:
    """
    Wraps any notifier (real or fake) and only actually sends when the
    message content has changed, or `min_interval` seconds have passed —
    so you don't get an email every camera frame while items are missing.
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
    Shared by notify_node.py and demo_integration.py, so both behave the
    same way: if config/secrets.yaml exists with real email details, use
    it and send REAL emails. Otherwise, safely fall back to printing what
    would have been sent.
    """
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            creds = (yaml.safe_load(f) or {}).get("email", {})
        try:
            real = EmailNotifier(
                smtp_server=creds.get("smtp_server", "smtp.gmail.com"),
                smtp_port=int(creds.get("smtp_port", 465)),
                sender_email=creds["sender_email"],
                sender_password=creds["sender_app_password"],
                receiver_email=creds["receiver_email"],
            )
            print("[notify] Found config/secrets.yaml — sending REAL emails.")
            return RateLimitedNotifier(real, min_interval=min_interval)
        except Exception as e:
            print(f"[notify] config/secrets.yaml exists but failed to use it ({e}) "
                  f"— falling back to fake/printed messages.")

    print("[notify] No config/secrets.yaml found — messages will only be printed, "
          "not really sent. Copy config/secrets.example.yaml to config/secrets.yaml "
          "and fill it in to send real emails.")
    return RateLimitedNotifier(FakeEmailNotifier(), min_interval=min_interval)
