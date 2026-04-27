"""
DQ Agent Framework — PDF Report Generator
Generates comprehensive Data Quality reports using ReportLab.
"""

import io
import pandas as pd
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Color palette
DQ_COLORS = {
    "primary": colors.HexColor("#6366f1"),
    "secondary": colors.HexColor("#8b5cf6"),
    "success": colors.HexColor("#10b981"),
    "warning": colors.HexColor("#f59e0b"),
    "danger": colors.HexColor("#ef4444"),
    "dark": colors.HexColor("#1e293b"),
    "medium": colors.HexColor("#475569"),
    "light": colors.HexColor("#f1f5f9"),
    "white": colors.white,
    "background": colors.HexColor("#0f172a"),
}

SEVERITY_COLORS = {
    "CRITICAL": colors.HexColor("#dc2626"),
    "HIGH": colors.HexColor("#ea580c"),
    "MEDIUM": colors.HexColor("#d97706"),
    "LOW": colors.HexColor("#16a34a"),
    "OK": colors.HexColor("#059669"),
}


def score_color(score: float) -> colors.Color:
    if score >= 90: return SEVERITY_COLORS["OK"]
    if score >= 70: return SEVERITY_COLORS["LOW"]
    if score >= 50: return SEVERITY_COLORS["MEDIUM"]
    if score >= 25: return SEVERITY_COLORS["HIGH"]
    return SEVERITY_COLORS["CRITICAL"]


def score_label(score: float) -> str:
    if score >= 90: return "EXCELLENT"
    if score >= 70: return "GOOD"
    if score >= 50: return "FAIR"
    if score >= 25: return "POOR"
    return "CRITICAL"


def generate_pdf_report(analysis_output: dict, domain: str,
                        df_info: dict = None, output_path: Path = None) -> Path:
    """
    Generate a PDF Data Quality report.

    Args:
        analysis_output: dict returned by DQAgent.run_analysis()
        domain: dataset domain name
        df_info: dict with row_count, col_count, dataset_name
        output_path: where to save the PDF

    Returns:
        Path to generated PDF
    """
    if output_path is None:
        out_dir = Path(__file__).parent.parent.parent / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = out_dir / f"DQ_Report_{domain}_{ts}.pdf"

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Data Quality Report — {domain.title()}",
        author="DQ Agent Framework",
    )

    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        "DQTitle",
        parent=styles["Title"],
        fontSize=26,
        textColor=DQ_COLORS["primary"],
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "DQSubtitle",
        parent=styles["Normal"],
        fontSize=12,
        textColor=DQ_COLORS["medium"],
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    h1_style = ParagraphStyle(
        "DQH1",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=DQ_COLORS["dark"],
        spaceBefore=16,
        spaceAfter=8,
        borderPadding=(0, 0, 4, 0),
        fontName="Helvetica-Bold",
    )
    h2_style = ParagraphStyle(
        "DQH2",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=DQ_COLORS["primary"],
        spaceBefore=10,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "DQBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=DQ_COLORS["dark"],
        spaceAfter=4,
        leading=14,
    )
    small_style = ParagraphStyle(
        "DQSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=DQ_COLORS["medium"],
        spaceAfter=2,
    )

    # ── TITLE PAGE ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("🎯 Data Quality Report", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Domain: {domain.replace('_', ' ').title()}", subtitle_style))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}",
        subtitle_style
    ))
    story.append(Spacer(1, 0.3 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=DQ_COLORS["primary"]))
    story.append(Spacer(1, 0.3 * inch))

    # Overall score box
    overall_score = analysis_output.get("overall_score", 0)
    results = analysis_output.get("results", {})
    total_issues = analysis_output.get("total_issues", 0)
    run_id = analysis_output.get("run_id", "N/A")
    duration = analysis_output.get("duration_sec", 0)

    score_col = score_color(overall_score)
    score_lbl = score_label(overall_score)

    kpi_data = [
        ["Overall DQ Score", "Status", "Total Issues", "Dimensions", "Duration"],
        [
            f"{overall_score:.1f} / 100",
            score_lbl,
            f"{total_issues:,}",
            f"{len(results)}",
            f"{duration:.1f}s",
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[3.5 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (0, 1), 16),
        ("TEXTCOLOR", (0, 1), (0, 1), score_col),
        ("TEXTCOLOR", (1, 1), (1, 1), score_col),
        ("FONTSIZE", (1, 1), (-1, 1), 12),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, DQ_COLORS["light"]),
        ("BACKGROUND", (0, 1), (-1, 1), DQ_COLORS["light"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [5]),
    ]))
    story.append(kpi_table)

    # Dataset info
    if df_info:
        story.append(Spacer(1, 0.3 * inch))
        info_data = [
            ["Dataset", "Rows", "Columns", "Analysis Run ID"],
            [
                df_info.get("dataset_name", domain),
                f"{df_info.get('row_count', 0):,}",
                f"{df_info.get('col_count', 0)}",
                str(run_id),
            ],
        ]
        info_table = Table(info_data, colWidths=[5 * cm, 3 * cm, 3 * cm, 4.5 * cm])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["dark"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, DQ_COLORS["light"]),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, DQ_COLORS["light"]]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)

    story.append(PageBreak())

    # ── EXECUTIVE SUMMARY ─────────────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=DQ_COLORS["light"]))
    story.append(Spacer(1, 0.1 * inch))

    # Count by severity
    critical = sum(1 for r in results.values() if r and r.severity == "CRITICAL")
    high = sum(1 for r in results.values() if r and r.severity == "HIGH")
    medium = sum(1 for r in results.values() if r and r.severity == "MEDIUM")
    low = sum(1 for r in results.values() if r and r.severity in ("LOW", "OK"))

    summary_text = f"""
    The Data Quality analysis of the <b>{domain.replace('_', ' ').title()}</b> dataset has been completed.
    The overall DQ Score is <b>{overall_score:.1f}/100</b> ({score_lbl}).
    A total of <b>{total_issues:,} issues</b> were identified across <b>{len(results)} quality dimensions</b>.
    """
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.1 * inch))

    sev_data = [
        ["Severity Level", "Dimensions Affected", "Risk Impact"],
        ["🔴 Critical", str(critical), "Immediate action required"],
        ["🟠 High", str(high), "High priority remediation"],
        ["🟡 Medium", str(medium), "Scheduled remediation"],
        ["🟢 Low / OK", str(low), "Monitor and maintain"],
    ]
    sev_table = Table(sev_data, colWidths=[5 * cm, 5 * cm, 5.5 * cm])
    sev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["dark"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, DQ_COLORS["light"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, DQ_COLORS["light"]]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sev_table)
    story.append(Spacer(1, 0.2 * inch))

    # ── DQ DIMENSION SCORECARD ─────────────────────────────────────────────────
    story.append(Paragraph("2. DQ Dimension Scorecard", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=DQ_COLORS["light"]))
    story.append(Spacer(1, 0.1 * inch))

    score_data = [["Dimension", "Score", "Status", "Issues Found", "Severity"]]
    for dim, result in sorted(results.items(), key=lambda x: x[1].score if x[1] else 100):
        if result is None:
            continue
        icon = result.dimension_icon
        score_data.append([
            f"{icon} {result.display_name}",
            f"{result.score:.1f}",
            score_label(result.score),
            str(result.issues_found),
            result.severity,
        ])

    score_table = Table(score_data, colWidths=[5.5 * cm, 2.5 * cm, 3 * cm, 3 * cm, 2.5 * cm])
    score_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, DQ_COLORS["light"]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    # Alternate row backgrounds
    for i in range(1, len(score_data)):
        bg = DQ_COLORS["light"] if i % 2 == 0 else colors.white
        score_styles.append(("BACKGROUND", (0, i), (-1, i), bg))
        # Color the score column
        if i < len(score_data):
            try:
                sc = float(score_data[i][1])
                score_styles.append(("TEXTCOLOR", (1, i), (1, i), score_color(sc)))
                score_styles.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
            except Exception:
                pass

    score_table.setStyle(TableStyle(score_styles))
    story.append(score_table)
    story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())

    # ── DETAILED ISSUE REPORT ─────────────────────────────────────────────────
    story.append(Paragraph("3. Detailed Issue Analysis", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=DQ_COLORS["light"]))

    for dim, result in sorted(results.items(), key=lambda x: x[1].score if x[1] else 100):
        if result is None or result.issues_found == 0:
            continue

        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(
            f"{result.dimension_icon} {result.display_name} — Score: {result.score:.1f}/100",
            h2_style
        ))

        issue_data = [["Column", "Issue Type", "Affected Rows", "% of Records", "Severity", "Recommended Fix"]]
        for issue in result.issues[:15]:  # limit to 15 per dimension
            issue_data.append([
                str(issue.column)[:25],
                issue.issue_type.replace("_", " ").title()[:30],
                f"{issue.affected_rows:,}",
                f"{issue.affected_pct*100:.1f}%",
                issue.severity,
                issue.fix_action.replace("_", " ").title()[:25],
            ])

        issue_table = Table(issue_data, colWidths=[3.5 * cm, 4 * cm, 2.5 * cm, 2.5 * cm, 2 * cm, 3.5 * cm])
        issue_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["dark"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.3, DQ_COLORS["light"]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("WORDWRAP", (0, 0), (-1, -1), True),
        ]
        for i in range(1, len(issue_data)):
            bg = DQ_COLORS["light"] if i % 2 == 0 else colors.white
            issue_styles.append(("BACKGROUND", (0, i), (-1, i), bg))
            sev = issue_data[i][4]
            if sev in SEVERITY_COLORS:
                issue_styles.append(("TEXTCOLOR", (4, i), (4, i), SEVERITY_COLORS[sev]))
                issue_styles.append(("FONTNAME", (4, i), (4, i), "Helvetica-Bold"))

        issue_table.setStyle(TableStyle(issue_styles))
        story.append(issue_table)

        if len(result.issues) > 15:
            story.append(Paragraph(
                f"... and {len(result.issues) - 15} more issues (see UI for full list)",
                small_style
            ))

    story.append(PageBreak())

    # ── RECOMMENDATIONS ────────────────────────────────────────────────────────
    story.append(Paragraph("4. Recommendations & Remediation Plan", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=DQ_COLORS["light"]))
    story.append(Spacer(1, 0.1 * inch))

    rec_data = [["Priority", "Dimension", "Action", "Risk Level", "Est. Impact"]]
    priority = 1
    for dim, result in sorted(results.items(), key=lambda x: x[1].score if x[1] else 100):
        if result is None or result.score >= 85:
            continue
        for issue in result.critical_issues[:3]:
            rec_data.append([
                f"P{priority}",
                result.display_name[:20],
                issue.fix_action.replace("_", " ").title()[:35],
                issue.risk_level,
                f"~{issue.affected_rows:,} rows",
            ])
            priority += 1
            if priority > 15:
                break
        if priority > 15:
            break

    if len(rec_data) > 1:
        rec_table = Table(rec_data, colWidths=[1.5 * cm, 4 * cm, 5.5 * cm, 2.5 * cm, 3 * cm])
        rec_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), DQ_COLORS["primary"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 0), (2, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, DQ_COLORS["light"]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for i in range(1, len(rec_data)):
            rec_styles.append(("BACKGROUND", (0, i), (-1, i),
                               DQ_COLORS["light"] if i % 2 == 0 else colors.white))
        rec_table.setStyle(TableStyle(rec_styles))
        story.append(rec_table)
    else:
        story.append(Paragraph("No critical recommendations — dataset quality is good!", body_style))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=DQ_COLORS["light"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        f"Generated by DQ Agent Framework | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Deterministic Engine — No AI/LLM",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                       textColor=DQ_COLORS["medium"], alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path


def generate_excel_issues_report(analysis_output: dict, domain: str) -> io.BytesIO:
    """Generate an Excel report with issues for email attachment."""
    output = io.BytesIO()
    results = analysis_output.get("results", {})
    overall_score = analysis_output.get("overall_score", 0)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: Summary
        summary_rows = []
        for dim, result in results.items():
            if result is None:
                continue
            summary_rows.append({
                "Dimension": result.display_name,
                "Score": round(result.score, 2),
                "Status": score_label(result.score),
                "Issues Found": result.issues_found,
                "Severity": result.severity,
            })

        if summary_rows:
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name="DQ Summary", index=False)

        # Sheet 2: All Issues
        all_issues = []
        for dim, result in results.items():
            if result is None:
                continue
            for issue in result.issues:
                all_issues.append({
                    "Dimension": result.display_name,
                    "Column": issue.column,
                    "Issue Type": issue.issue_type,
                    "Description": issue.description,
                    "Affected Rows": issue.affected_rows,
                    "Affected %": round(issue.affected_pct * 100, 2),
                    "Severity": issue.severity,
                    "Risk Level": issue.risk_level,
                    "Recommended Fix": issue.fix_action,
                    "Auto-Fixable": "Yes" if issue.auto_fixable else "No",
                })

        if all_issues:
            pd.DataFrame(all_issues).to_excel(writer, sheet_name="All Issues", index=False)

        # Sheet 3: Recommendations
        recs = []
        priority = 1
        for dim, result in sorted(results.items(), key=lambda x: x[1].score if x[1] else 100):
            if result is None:
                continue
            for issue in result.critical_issues[:5]:
                recs.append({
                    "Priority": f"P{priority}",
                    "Dimension": result.display_name,
                    "Issue": issue.description[:100],
                    "Fix Action": issue.fix_action,
                    "Risk Level": issue.risk_level,
                    "Rows Affected": issue.affected_rows,
                })
                priority += 1

        if recs:
            pd.DataFrame(recs).to_excel(writer, sheet_name="Recommendations", index=False)

    output.seek(0)
    return output
