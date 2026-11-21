"""Outgoing email via Brevo's HTTP API.

Render's free plan blocks SMTP ports, so mail goes over HTTPS instead.
Needs BREVO_API_KEY and MAIL_FROM (a sender verified in Brevo). Without
them (e.g. running locally) emails are printed to the terminal instead of
sent, so you can still read verification codes while testing.
"""
import json
import urllib.request

from flask import current_app, url_for


def send_email(to, subject, text):
    cfg = current_app.config
    key, sender = cfg.get("BREVO_API_KEY"), cfg.get("MAIL_FROM")
    if not key or not sender:
        msg = f"[email not sent - BREVO_API_KEY/MAIL_FROM not set]\nTo: {to}\nSubject: {subject}\n\n{text}\n"
        current_app.logger.warning(msg)
        return False
    payload = {
        "sender": {"name": cfg.get("MAIL_FROM_NAME") or "EBCS Coaching", "email": sender},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        headers={"api-key": key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:  # never crash a page because email failed
        current_app.logger.error("email to %s failed: %s", to, exc)
        return False


def absolute_url(endpoint, **values):
    """Full link for emails. Uses SITE_URL when set (recommended on Render)."""
    base = (current_app.config.get("SITE_URL") or "").rstrip("/")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)
