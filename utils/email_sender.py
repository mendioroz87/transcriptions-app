"""Email sending utilities for team invitations."""

from __future__ import annotations

import html
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

import streamlit as st

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
INVITE_BASE_URL = "https://xcribe.streamlit.app/?invite="


def _get_required_secret(secret_name: str) -> str:
    value = st.secrets.get(secret_name)
    if not value or not str(value).strip():
        raise ValueError(f"Missing required Streamlit secret: {secret_name}")
    return str(value).strip()


def _format_expiration_utc(expires_at: str) -> str:
    if not expires_at or not str(expires_at).strip():
        raise ValueError("Invitation expiration timestamp is missing.")

    raw_value = str(expires_at).strip()
    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid invitation expiration timestamp: {raw_value}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")


def _build_plain_text(
    *,
    inviter_name: str,
    team_name: str,
    invite_url: str,
    invite_token: str,
    formatted_expiration: str,
) -> str:
    return (
        "MLabs Transcription App Invitation\n\n"
        f"{inviter_name} invited you to join the team \"{team_name}\".\n\n"
        f"Accept invitation: {invite_url}\n\n"
        f"Invite token: {invite_token}\n"
        f"Expires: {formatted_expiration}\n\n"
        "If the button does not work, open the app and paste the token in the Accept Invite tab."
    )


def _build_html(
    *,
    inviter_name: str,
    team_name: str,
    invite_url: str,
    invite_token: str,
    formatted_expiration: str,
) -> str:
    safe_inviter = html.escape(inviter_name)
    safe_team = html.escape(team_name)
    safe_token = html.escape(invite_token)
    safe_expiration = html.escape(formatted_expiration)

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f2f4f8;font-family:Arial,sans-serif;color:#1f2937;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #dbe2ea;">
                <tr>
                  <td style="background:#111827;padding:24px 28px;">
                    <h1 style="margin:0;font-size:22px;line-height:1.2;color:#ffffff;">MLabs Transcription App</h1>
                    <p style="margin:8px 0 0 0;color:#cbd5e1;font-size:14px;">Team Invitation</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:28px;">
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;">
                      <strong>{safe_inviter}</strong> invited you to join the team
                      <strong>{safe_team}</strong>.
                    </p>
                    <p style="margin:0 0 24px 0;font-size:14px;line-height:1.6;color:#4b5563;">
                      Click the button below to accept your invitation.
                    </p>
                    <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 24px 0;">
                      <tr>
                        <td style="border-radius:8px;background:#2563eb;">
                          <a href="{invite_url}" style="display:inline-block;padding:12px 20px;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;">
                            Accept Invitation
                          </a>
                        </td>
                      </tr>
                    </table>
                    <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;padding:14px 16px;margin:0 0 16px 0;">
                      <p style="margin:0 0 8px 0;font-size:13px;color:#475569;">Backup invite token</p>
                      <code style="font-family:Consolas,'Courier New',monospace;font-size:13px;color:#0f172a;word-break:break-all;">{safe_token}</code>
                    </div>
                    <p style="margin:0;font-size:13px;line-height:1.6;color:#64748b;">
                      This invitation expires on <strong>{safe_expiration}</strong>.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def send_team_invitation_email(
    invitee_email: str,
    team_name: str,
    inviter_name: str,
    invite_token: str,
    expires_at: str,
) -> tuple[bool, str]:
    """Send a team invitation email via Gmail SMTP using Streamlit secrets."""
    try:
        gmail_user = _get_required_secret("GMAIL_USER")
        gmail_app_password = _get_required_secret("GMAIL_APP_PASSWORD")
        formatted_expiration = _format_expiration_utc(expires_at)
    except Exception as exc:
        return False, str(exc)

    safe_invitee = (invitee_email or "").strip()
    safe_team_name = (team_name or "Team").strip() or "Team"
    safe_inviter_name = (inviter_name or "Team Admin").strip() or "Team Admin"
    safe_token = (invite_token or "").strip()

    if not safe_invitee:
        return False, "Invitee email is required."
    if not safe_token:
        return False, "Invite token is required."

    encoded_token = quote(safe_token, safe="")
    invite_url = f"{INVITE_BASE_URL}{encoded_token}"
    subject = f"You've been invited to join {safe_team_name} - MLabs Transcription App"

    plain_text = _build_plain_text(
        inviter_name=safe_inviter_name,
        team_name=safe_team_name,
        invite_url=invite_url,
        invite_token=safe_token,
        formatted_expiration=formatted_expiration,
    )
    html_body = _build_html(
        inviter_name=safe_inviter_name,
        team_name=safe_team_name,
        invite_url=invite_url,
        invite_token=safe_token,
        formatted_expiration=formatted_expiration,
    )

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = gmail_user
    message["To"] = safe_invitee
    message.attach(MIMEText(plain_text, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, [safe_invitee], message.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        smtp_error = getattr(exc, "smtp_error", b"")
        detail = smtp_error.decode("utf-8", errors="ignore") if isinstance(smtp_error, bytes) else str(smtp_error)
        return False, f"Gmail authentication failed. {detail.strip() or str(exc)}"
    except smtplib.SMTPException as exc:
        return False, f"SMTP error while sending invitation email: {exc}"
    except OSError as exc:
        return False, f"Network error while sending invitation email: {exc}"

    return True, "Invitation email sent successfully."
