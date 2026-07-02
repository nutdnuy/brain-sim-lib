from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage


class Notifier:
    def send_login_link(self, to_email: str, url: str) -> None:
        raise NotImplementedError


@dataclass
class MemoryNotifier(Notifier):
    sent_messages: list[dict[str, str]] = field(default_factory=list)

    def send_login_link(self, to_email: str, url: str) -> None:
        self.sent_messages.append(
            {
                "to_email": to_email,
                "subject": "WorldQuant BRAIN login verification",
                "body": f"Open this WorldQuant BRAIN verification link: {url}",
            }
        )


class SmtpNotifier(Notifier):
    def __init__(self) -> None:
        self.host = os.environ.get("BRAIN_SIM_SMTP_HOST", "")
        self.port = int(os.environ.get("BRAIN_SIM_SMTP_PORT", "587"))
        self.user = os.environ.get("BRAIN_SIM_SMTP_USER", "")
        self.password = os.environ.get("BRAIN_SIM_SMTP_PASSWORD", "")
        self.sender = os.environ.get("BRAIN_SIM_SMTP_FROM", self.user)

    def send_login_link(self, to_email: str, url: str) -> None:
        if not self.host or not self.sender:
            raise RuntimeError(
                "Email notification requires BRAIN_SIM_SMTP_HOST and BRAIN_SIM_SMTP_FROM."
            )
        message = EmailMessage()
        message["Subject"] = "WorldQuant BRAIN login verification"
        message["From"] = self.sender
        message["To"] = to_email
        message.set_content(f"Open this WorldQuant BRAIN verification link: {url}")
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(message)
