"""Email sender — send review report via Gmail BCC with reference attachments."""

from __future__ import annotations

import os
import smtplib
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
BCC_TO = os.environ.get("BCC_TO", "")


def _zip_references(refs_dir: Path, zip_path: Path) -> Path | None:
    """Zip all files in refs_dir. Returns zip_path if files exist, else None."""
    files = [f for f in refs_dir.iterdir() if f.is_file()]
    if not files:
        return None
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    return zip_path


def send_review_email(
    book_name: str,
    html_report_path: Path,
    refs_dir: Path,
) -> dict:
    """Send review report email via Gmail.

    - Subject: {book_name}-审核报告
    - Body: HTML report content
    - BCC: recipients from .env
    - Attachment: {book_name}引用.zip (zipped references folder)
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return {"success": False, "error": "GMAIL_USER or GMAIL_APP_PASSWORD not set in .env"}
    if not BCC_TO:
        return {"success": False, "error": "BCC_TO not set in .env"}

    subject = f"{book_name}-审核报告"
    html_content = html_report_path.read_text(encoding="utf-8")
    html_bytes = html_content.encode("utf-8")

    # Build email — same pattern as GlobalCapitalRadar:
    # HTML rendered as body + HTML file also as attachment for download.
    # Use multipart/mixed so both the rendered body and attachment are present.
    msg = MIMEMultipart("mixed")
    msg["From"] = f"AI审稿系统 <{GMAIL_USER}>"
    msg["Subject"] = subject
    msg["Bcc"] = BCC_TO

    # HTML body inside a multipart/alternative wrapper (proper MIME structure)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(f"请查看审核报告（书名：{book_name}）", "plain", "utf-8"))
    alt.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt)

    # Also attach the HTML file for download / archiving
    attachment = MIMEApplication(html_bytes, Name=html_report_path.name)
    attachment["Content-Disposition"] = f'attachment; filename="{html_report_path.name}"'
    msg.attach(attachment)

    # Parse BCC recipients
    recipients = [addr.strip() for addr in BCC_TO.replace(",", ";").split(";") if addr.strip()]

    # Send via Gmail SMTP — use send_message() instead of sendmail() so that
    # the email library handles UTF-8 header encoding automatically (same way
    # nodemailer does it in GlobalCapitalRadar).
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)
        return {
            "success": True,
            "subject": subject,
            "recipients": len(recipients),
            "has_attachment": False,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
