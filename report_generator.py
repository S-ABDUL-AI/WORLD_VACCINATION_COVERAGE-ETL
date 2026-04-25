"""
PDF report generator for Global Vaccination Coverage Explorer.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _save_plot(series: pd.DataFrame, campaign_start: int) -> BytesIO:
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    ax.plot(series["year"], series["coverage_pct"], marker="o", color="#0A1F44")
    ax.axvline(campaign_start, color="#C8382A", linestyle="--")
    ax.set_title("Coverage trend")
    ax.set_xlabel("Year")
    ax.set_ylabel("Coverage percent")
    ax.set_ylim(0, 100)
    ax.grid(False)
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _build_cover(country: str, antigen: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading1"], textColor=colors.HexColor("#0A1F44"), fontSize=22, leading=26)
    s = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.HexColor("#2C3E50"), fontSize=11, leading=15)
    story = [
        Spacer(1, 1.1 * inch),
        Paragraph("Global Vaccination Coverage Explorer", h),
        Spacer(1, 0.12 * inch),
        Paragraph("Policy report for country vaccination coverage monitoring", s),
        Spacer(1, 0.3 * inch),
        Paragraph(f"Country: <b>{country}</b>", s),
        Paragraph(f"Antigen: <b>{antigen}</b>", s),
        Paragraph(f"Generated on: <b>{date.today().isoformat()}</b>", s),
    ]
    doc.build(story)
    return buf.getvalue()


def _build_body(
    series: pd.DataFrame,
    country: str,
    antigen: str,
    campaign_start: int,
    pre_years: int,
    post_years: int,
    p_val: float,
    avg_before: float,
    avg_after: float,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.65 * inch, rightMargin=0.65 * inch)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading2"], textColor=colors.HexColor("#0A1F44"), fontSize=14)
    b = ParagraphStyle("b", parent=styles["Normal"], textColor=colors.HexColor("#2C3E50"), fontSize=10, leading=14)
    diff = avg_after - avg_before if pd.notna(avg_after) and pd.notna(avg_before) else np.nan
    sig_text = f"{p_val:.4f}" if pd.notna(p_val) else "N/A"

    table_df = series.copy()
    table_df = table_df.head(20)
    data = [list(table_df.columns)] + table_df.values.tolist()
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A1F44")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E6EC")),
            ]
        )
    )

    chart_img = _save_plot(series, campaign_start)

    story = [
        Paragraph("Executive summary", h),
        Paragraph(
            f"Country <b>{country}</b> and antigen <b>{antigen}</b> were analyzed over a reference year of "
            f"<b>{campaign_start}</b> with windows of <b>{pre_years}</b> years before and <b>{post_years}</b> years after.",
            b,
        ),
        Spacer(1, 0.08 * inch),
        Paragraph(
            f"Before mean is <b>{avg_before:.1f}%</b>, after mean is <b>{avg_after:.1f}%</b>, difference is "
            f"<b>{diff:+.1f} percentage points</b>, and p-value is <b>{sig_text}</b>.",
            b,
        ),
        Spacer(1, 0.18 * inch),
        Paragraph("Coverage trend chart", h),
        Image(chart_img, width=6.1 * inch, height=2.5 * inch),
        Spacer(1, 0.18 * inch),
        Paragraph("Data table (top 20 rows)", h),
        tbl,
        Spacer(1, 0.2 * inch),
        Paragraph(
            "Built by Sherriff Abdul-Hamid · Product leader specializing in government digital services and safety net benefits delivery.",
            ParagraphStyle("foot", parent=b, fontSize=8.5, textColor=colors.HexColor("#6B7280")),
        ),
    ]
    doc.build(story)
    return buf.getvalue()


def build_report_bytes(
    series: pd.DataFrame,
    country: str,
    antigen: str,
    campaign_start: int,
    pre_years: int,
    post_years: int,
    p_val: float,
    avg_before: float,
    avg_after: float,
) -> bytes:
    cover = _build_cover(country=country, antigen=antigen)
    body = _build_body(
        series=series,
        country=country,
        antigen=antigen,
        campaign_start=campaign_start,
        pre_years=pre_years,
        post_years=post_years,
        p_val=p_val,
        avg_before=avg_before,
        avg_after=avg_after,
    )
    writer = PdfWriter()
    for src in (cover, body):
        reader = PdfReader(BytesIO(src))
        for p in reader.pages:
            writer.add_page(p)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
