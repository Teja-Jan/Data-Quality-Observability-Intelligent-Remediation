"""
DQ Agent Framework — Email Service
Sends DQ analysis results and Excel attachments via SMTP or SendGrid.
"""

import os
import io
import smtplib
import base64
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").lower()
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
DQ_ALERT_RECIPIENTS = os.getenv("DQ_ALERT_RECIPIENTS", "")


def score_label(score: float) -> str:
    if score >= 90: return "EXCELLENT"
    if score >= 70: return "GOOD"
    if score >= 50: return "FAIR"
    if score >= 25: return "POOR"
    return "CRITICAL"


def build_html_email(domain: str, analysis_output: dict) -> str:
    """Build a rich HTML email body for DQ notifications."""
    overall_score = analysis_output.get("overall_score", 0)
    total_issues = analysis_output.get("total_issues", 0)
    results = analysis_output.get("results", {})
    run_id = analysis_output.get("run_id", "N/A")
    duration = analysis_output.get("duration_sec", 0)
    status_label = score_label(overall_score)

    score_color = (
        "#10b981" if overall_score >= 90 else
        "#f59e0b" if overall_score >= 70 else
        "#ea580c" if overall_score >= 50 else
        "#ef4444"
    )

    dimension_rows = ""
    for dim, result in sorted(results.items(), key=lambda x: x[1].score if x[1] else 100):
        if result is None:
            continue
        sc = result.score
        sc_color = (
            "#10b981" if sc >= 90 else
            "#f59e0b" if sc >= 70 else
            "#ea580c" if sc >= 50 else
            "#ef4444"
        )
        bar_width = int(sc)
        dimension_rows += f"""
        <tr>
            <td style="padding:8px 12px; font-size:13px;">{result.dimension_icon} {result.display_name}</td>
            <td style="padding:8px 12px; text-align:center;">
                <span style="font-weight:bold; color:{sc_color}; font-size:14px;">{sc:.1f}</span>
            </td>
            <td style="padding:8px 12px; text-align:center; font-size:12px; color:#64748b;">{result.issues_found}</td>
            <td style="padding:8px 12px; text-align:center;">
                <span style="background:{sc_color}; color:white; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold;">{result.severity}</span>
            </td>
        </tr>
        """

    # Top issues
    top_issues_html = ""
    all_issues = []
    for dim, result in results.items():
        if result:
            for issue in result.issues:
                all_issues.append(issue)
    all_issues.sort(key=lambda x: x.affected_rows, reverse=True)

    for issue in all_issues[:8]:
        sev_color = {"CRITICAL": "#dc2626", "HIGH": "#ea580c", "MEDIUM": "#d97706", "LOW": "#16a34a"}.get(issue.severity, "#64748b")
        top_issues_html += f"""
        <tr>
            <td style="padding:7px 10px; font-size:12px; color:#374151;">{issue.column}</td>
            <td style="padding:7px 10px; font-size:12px; color:#374151;">{issue.description[:80]}...</td>
            <td style="padding:7px 10px; font-size:12px; text-align:center;">{issue.affected_rows:,}</td>
            <td style="padding:7px 10px; text-align:center;">
                <span style="color:{sev_color}; font-weight:bold; font-size:11px;">{issue.severity}</span>
            </td>
            <td style="padding:7px 10px; font-size:11px; color:#6366f1;">{issue.fix_action.replace('_', ' ').title()}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:30px 0;">
<tr><td align="center">
<table width="700" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,#1E3A8A,#2563EB);padding:36px 40px;text-align:center;">
      <h1 style="color:white;margin:0;font-size:22px;font-weight:700;">Data Quality Alert</h1>
      <p style="color:#e0e7ff;margin:8px 0 0;font-size:14px;">
        Domain: <b>{domain.replace('_', ' ').title()}</b> | Run ID: {run_id}
      </p>
      <p style="color:#c7d2fe;margin:4px 0 0;font-size:12px;">{datetime.now().strftime('%B %d, %Y at %H:%M:%S')}</p>
    </td>
  </tr>

  <!-- KPI BAR -->
  <tr>
    <td style="padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:24px 16px;border-right:1px solid #e2e8f0;">
            <div style="font-size:40px;font-weight:800;color:{score_color};">{overall_score:.1f}</div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">Overall DQ Score</div>
            <div style="font-size:13px;color:{score_color};font-weight:700;margin-top:4px;">{status_label}</div>
          </td>
          <td align="center" style="padding:24px 16px;border-right:1px solid #e2e8f0;">
            <div style="font-size:40px;font-weight:800;color:#ef4444;">{total_issues:,}</div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">Total Issues</div>
          </td>
          <td align="center" style="padding:24px 16px;border-right:1px solid #e2e8f0;">
            <div style="font-size:40px;font-weight:800;color:#6366f1;">{len(results)}</div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">Dimensions Analyzed</div>
          </td>
          <td align="center" style="padding:24px 16px;">
            <div style="font-size:40px;font-weight:800;color:#8b5cf6;">{duration:.1f}s</div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">Analysis Duration</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- DIMENSION SCORES -->
  <tr>
    <td style="padding:24px 32px;">
      <h2 style="color:#1e293b;font-size:16px;margin:0 0 16px;font-weight:700;">DQ Dimension Scores</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
        <tr style="background:#f8fafc;">
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#475569;font-weight:600;">Dimension</th>
          <th style="padding:10px 12px;text-align:center;font-size:12px;color:#475569;font-weight:600;">Score</th>
          <th style="padding:10px 12px;text-align:center;font-size:12px;color:#475569;font-weight:600;">Issues</th>
          <th style="padding:10px 12px;text-align:center;font-size:12px;color:#475569;font-weight:600;">Severity</th>
        </tr>
        {dimension_rows}
      </table>
    </td>
  </tr>

  <!-- TOP ISSUES -->
  <tr>
    <td style="padding:0 32px 24px;">
      <h2 style="color:#1e293b;font-size:16px;margin:0 0 16px;font-weight:700;">Issues Requiring Attention</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;font-size:12px;">
        <tr style="background:#f8fafc;">
          <th style="padding:8px 10px;text-align:left;color:#475569;font-weight:600;">Column</th>
          <th style="padding:8px 10px;text-align:left;color:#475569;font-weight:600;">Description</th>
          <th style="padding:8px 10px;text-align:center;color:#475569;font-weight:600;">Rows</th>
          <th style="padding:8px 10px;text-align:center;color:#475569;font-weight:600;">Severity</th>
          <th style="padding:8px 10px;text-align:left;color:#475569;font-weight:600;">Fix</th>
        </tr>
        {top_issues_html}
      </table>
    </td>
  </tr>

  <!-- ACTION REQUIRED -->
  <tr>
    <td style="padding:0 32px 24px;">
      <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;">
        <div style="font-weight:700;color:#1e3a8a;margin-bottom:6px;">Action Required</div>
        <div style="color:#78350f;font-size:13px;line-height:1.6;">
          Please review the attached Excel report for the complete issue list and remediation recommendations.
          Log into the DQ Agent Framework UI to select and execute fixes.
          An Excel attachment with full details is included below.
        </div>
      </div>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#f8fafc;padding:16px 32px;text-align:center;border-top:1px solid #e2e8f0;">
      <p style="margin:0;font-size:11px;color:#94a3b8;">
        DQ Agent Framework | Deterministic Data Quality Engine | No AI/LLM Dependency<br>
        This is an automated notification. Do not reply to this email.
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>
"""
    return html


def send_dq_alert(
    domain: str,
    analysis_output: dict,
    excel_buffer: io.BytesIO,
    recipients: list[str] = None,
    sender: str = None,
) -> dict:
    """
    Send DQ alert email with Excel attachment.

    Returns:
        dict: {"success": bool, "message": str, "provider": str}
    """
    if not recipients:
        raw = DQ_ALERT_RECIPIENTS.strip()
        if not raw:
            return {"success": False, "message": "No recipients configured", "provider": EMAIL_PROVIDER}
        recipients = [r.strip() for r in raw.split(",") if r.strip()]

    if not recipients:
        return {"success": False, "message": "No valid recipients", "provider": EMAIL_PROVIDER}

    if not sender:
        sender = SMTP_USER or "dq-agent@noreply.com"

    overall_score = analysis_output.get("overall_score", 0)
    total_issues = analysis_output.get("total_issues", 0)
    subject = (
        f"[DQ Alert] {domain.replace('_', ' ').title()} — "
        f"Score: {overall_score:.1f}/100 | {total_issues:,} Issues Found"
    )

    html_body = build_html_email(domain, analysis_output)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"DQ_Issues_{domain}_{ts}.xlsx"

    if EMAIL_PROVIDER == "sendgrid" and SENDGRID_API_KEY:
        return _send_via_sendgrid(
            sender, recipients, subject, html_body, excel_buffer, excel_filename
        )
    else:
        return _send_via_smtp(
            sender, recipients, subject, html_body, excel_buffer, excel_filename
        )


def _send_via_smtp(sender, recipients, subject, html_body, excel_buffer, excel_filename) -> dict:
    """Send email using SMTP."""
    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # HTML body
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        # Excel attachment
        excel_buffer.seek(0)
        excel_data = excel_buffer.read()
        attachment = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        attachment.set_payload(excel_data)
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", f'attachment; filename="{excel_filename}"')
        msg.attach(attachment)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(sender, recipients, msg.as_string())

        return {
            "success": True,
            "message": f"Email sent to {', '.join(recipients)} via SMTP",
            "provider": "smtp",
        }

    except Exception as e:
        return {"success": False, "message": f"SMTP error: {str(e)}", "provider": "smtp"}


def _send_via_sendgrid(sender, recipients, subject, html_body, excel_buffer, excel_filename) -> dict:
    """Send email using SendGrid API."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import (
            Mail, Attachment, FileContent, FileName,
            FileType, Disposition, To
        )

        excel_buffer.seek(0)
        excel_b64 = base64.b64encode(excel_buffer.read()).decode()

        message = Mail(
            from_email=sender,
            to_emails=[To(r) for r in recipients],
            subject=subject,
            html_content=html_body,
        )

        attachment = Attachment(
            file_content=FileContent(excel_b64),
            file_name=FileName(excel_filename),
            file_type=FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            disposition=Disposition("attachment"),
        )
        message.attachment = attachment

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 202):
            return {"success": True, "message": f"Email sent via SendGrid to {len(recipients)} recipients", "provider": "sendgrid"}
        else:
            return {"success": False, "message": f"SendGrid returned {response.status_code}", "provider": "sendgrid"}

    except Exception as e:
        return {"success": False, "message": f"SendGrid error: {str(e)}", "provider": "sendgrid"}


def build_approval_html_email(domain: str, analysis_output: dict, high_risk_count: int) -> str:
    """Build HTML email body specifically for high-risk approval requests."""
    overall_score = analysis_output.get("overall_score", 0)
    results = analysis_output.get("results", {})
    run_id = analysis_output.get("run_id", "N/A")

    high_risk_rows = ""
    for dim, result in results.items():
        if result is None:
            continue
        for issue in result.issues:
            if getattr(issue, "risk_level", "LOW") in ("HIGH", "CRITICAL"):
                sev_color = "#dc2626" if issue.severity == "HIGH" else "#ea580c"
                high_risk_rows += f"""
                <tr>
                    <td style="padding:8px 10px;font-size:12px;">{result.display_name}</td>
                    <td style="padding:8px 10px;font-size:12px;">{issue.column or 'Table-Level'}</td>
                    <td style="padding:8px 10px;font-size:12px;">{issue.description[:80]}...</td>
                    <td style="padding:8px 10px;text-align:center;">
                        <span style="color:{sev_color};font-weight:bold;">{issue.severity}</span>
                    </td>
                    <td style="padding:8px 10px;font-size:11px;color:#6366f1;">{issue.fix_action.replace('_',' ').title()}</td>
                </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:30px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr>
    <td style="background:linear-gradient(135deg,#dc2626,#b91c1c);padding:32px 36px;text-align:center;">
      <h1 style="color:white;margin:0;font-size:22px;font-weight:700;">⛔ DQ Approval Required</h1>
      <p style="color:#fecaca;margin:8px 0 0;font-size:13px;">
        Domain: <b>{domain.replace('_',' ').title()}</b> | Run ID: {run_id} | {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}
      </p>
    </td>
  </tr>
  <tr>
    <td style="padding:24px 32px;">
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
        <b style="color:#991b1b;">Action Required:</b>
        <p style="color:#7f1d1d;margin:8px 0 0;font-size:13px;">
          The AI-Agent Orchestrated DQ system has flagged <b>{high_risk_count} high-risk data quality issues</b>
          in the <b>{domain.replace('_',' ').title()}</b> dataset (DQ Score: {overall_score:.1f}/100).
          These issues cannot be auto-resolved and require your explicit review and approval.
          The complete Excel report is attached.
        </p>
      </div>
      <h2 style="color:#1e293b;font-size:15px;font-weight:700;margin-bottom:12px;">⚠️ High-Risk Issues Requiring Approval</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
        <tr style="background:#f8fafc;">
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:#475569;">Dimension</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:#475569;">Column</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:#475569;">Issue</th>
          <th style="padding:8px 10px;text-align:center;font-size:11px;color:#475569;">Severity</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:#475569;">Recommended Fix</th>
        </tr>
        {high_risk_rows}
      </table>
    </td>
  </tr>
  <tr>
    <td style="background:#f8fafc;padding:14px 32px;text-align:center;border-top:1px solid #e2e8f0;">
      <p style="margin:0;font-size:11px;color:#94a3b8;">
        AI-Agent Orchestrated Data Quality Observability & Intelligent Remediation<br>
        This is an automated high-risk approval request. Please review the Excel attachment and respond to your DQ team.
      </p>
    </td>
  </tr>
</table>
</td></tr></table>
</body></html>"""


def send_high_risk_approval_email(
    domain: str,
    analysis_output: dict,
    excel_buffer: io.BytesIO,
    recipients: list = None,
) -> dict:
    """Send high-risk DQ issues for manual approval with Excel attachment."""
    if not recipients:
        recipients = ["teja.jan220@gmail.com"]

    results = analysis_output.get("results", {})
    high_risk_count = sum(
        1 for r in results.values() if r
        for i in r.issues if getattr(i, "risk_level", "LOW") in ("HIGH", "CRITICAL")
    )

    subject = (
        f"[DQ Approval Required] {domain.replace('_', ' ').title()} "
        f"— {high_risk_count} High-Risk Issues Detected | Score: {analysis_output.get('overall_score', 0):.1f}/100"
    )
    html_body = build_approval_html_email(domain, analysis_output, high_risk_count)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"DQ_HighRisk_{domain}_{ts}.xlsx"

    sender = SMTP_USER or "dq-agent@noreply.com"
    if EMAIL_PROVIDER == "sendgrid" and SENDGRID_API_KEY:
        return _send_via_sendgrid(sender, recipients, subject, html_body, excel_buffer, excel_filename)
    else:
        return _send_via_smtp(sender, recipients, subject, html_body, excel_buffer, excel_filename)

