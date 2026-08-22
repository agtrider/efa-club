"""
EFA LOGOS framework — seven-section "what is true" memo.

Sits at the bottom of Stock Assessment + Kelly. Reuses club snapshot,
prior Grok assessment, and the in-app Kelly matrix.
"""
from __future__ import annotations

from datetime import datetime

from efa_club_kelly import (
    build_half_kelly_matrix,
    format_pct,
    highlight_cell,
)
from efa_club_research import (
    _pdf_safe,
    assessment_download_name,
    assessment_run_stamp,
    fetch_assessment_snapshot,
    parse_assessment_response,
)

LOGOS_SECTIONS = [
    (
        "logos",
        "1. Logos — What is true?",
        [
            ("what_company_does", "What does the company actually do?"),
            ("economic_problem", "What economic problem does it solve?"),
            ("who_pays", "Who pays it?"),
            ("secular_drivers", "What are the secular drivers?"),
        ],
    ),
    (
        "direction",
        "2. Direction — Where is it going?",
        [
            ("rev_eps_yoy_qoq", "Revenue and EPS growth YoY and QoQ"),
            ("rev_eps_3yr", "Revenue and EPS 3-year trajectory"),
            ("industry_growth", "Industry growth"),
            ("competitive_position", "Competitive position"),
            ("catalysts", "Catalysts"),
        ],
    ),
    (
        "execution",
        "3. Execution — Can management actually deliver?",
        [
            ("gross_net_margins", "Gross and net margins"),
            ("cash_flow", "Cash flow"),
            ("cash_and_debt", "Balance sheet: cash and debt"),
            ("capex", "CapEx"),
            ("milestones", "Milestones"),
            ("guidance_vs_results", "Guidance vs results"),
        ],
    ),
    (
        "valuation",
        "4. Valuation — What are we being asked to pay?",
        [
            ("price_and_cap", "Stock price and market cap"),
            ("forward_pe", "Forward P/E or appropriate alternative"),
            ("analyst_targets", "Analyst targets"),
            ("sma_50_200", "50-day and 200-day averages"),
        ],
    ),
    (
        "market_structure",
        "5. Market structure — What is the market doing?",
        [
            ("price_trend", "Price trend"),
            ("volume", "Volume"),
            ("support_resistance", "Support / resistance"),
            ("order_flow", "Order flow"),
            ("sentiment", "Sentiment"),
        ],
    ),
    (
        "stewardship",
        "6. Stewardship — How should EFA own it?",
        [
            ("vehicle", "Stock, LEAP, spread, private shares, or wait"),
            ("capital_size", "How much capital (ties to Kelly)"),
            ("rationale", "Why this vehicle and size"),
        ],
    ),
    (
        "kelly",
        "7. Kelly — How much risk has the evidence earned?",
        [
            ("summary", "Summary from the club Kelly work"),
            ("win_probability", "Win probability used"),
            ("net_odds", "Net odds used"),
            ("half_kelly", "Half-Kelly fraction"),
        ],
    ),
]


def _section_dict(parsed, key):
    value = (parsed or {}).get(key)
    return value if isinstance(value, dict) else {}


def kelly_evidence_brief(assessment=None):
    """Deterministic Kelly numbers for the LOGOS Kelly section."""
    parsed = (assessment or {}).get("parsed") or {}
    matrix = (assessment or {}).get("kelly_matrix") or build_half_kelly_matrix()
    p = parsed.get("kelly_win_probability")
    b = parsed.get("kelly_net_odds")
    hl = highlight_cell(matrix, p, b)
    lines = [
        f"Classic half-Kelly: f½ = 0.5 × (p × b − q) / b",
        f"Grid p = 0.55 / 0.65 / 0.70; b = 1 / 1.5 / 3; bankroll = 1 / 2 / 3 / 5.",
    ]
    if parsed.get("kelly_rationale"):
        lines.append(str(parsed["kelly_rationale"]))
    if hl:
        lines.append(
            f"Mapped grid: p={hl['win_probability']*100:.0f}%, b={hl['net_odds']:g} → "
            f"half-Kelly {format_pct(hl['half_kelly'])} (full Kelly {format_pct(hl['full_kelly'])})."
        )
    elif p is not None and b is not None:
        lines.append(f"Grok inputs: p={p}, b={b} (not on the default grid).")
    return {
        "text": " ".join(lines),
        "highlight": hl,
        "rationale": parsed.get("kelly_rationale") or "",
        "win_probability": p,
        "net_odds": b,
    }


def _prior_assessment_block(assessment):
    if not assessment:
        return "None yet — fill from public filings and the club snapshot."
    parsed = assessment.get("parsed") or {}
    bits = []
    for key in (
        "summary",
        "what_they_do",
        "industry",
        "competitors",
        "differentiators",
        "best_of_breed",
        "growth_eps_targets",
        "forward_pe_target",
        "market_cap_price",
        "yoy_performance",
        "sma_50",
        "sma_200",
        "analyst_ratings",
        "average_price_target",
        "total_cash",
        "cash_flow",
        "recommendation",
        "recommendation_rationale",
    ):
        val = parsed.get(key)
        if val not in (None, ""):
            bits.append(f"- {key}: {val}")
    return "\n".join(bits) or "Assessment ran but structured fields were empty."


def build_logos_prompt(company_name, ticker, snapshot=None, assessment=None, analyst_name="EFA member"):
    facts_block = "None available."
    if snapshot and snapshot.get("fact_lines"):
        facts_block = "\n".join(snapshot["fact_lines"])
    kelly = kelly_evidence_brief(assessment)
    display = (company_name or "").strip() or (snapshot or {}).get("company") or ticker
    tkr = str(ticker or "").upper().strip()

    return f"""You are a senior investment analyst for the Equity for All Investment Club (EFAIC).
Fill the club LOGOS framework for this publicly traded company.

Company: {display}
Ticker: {tkr}
Prepared for: {analyst_name}

LOGOS means "What is true" — separate evidence from story. Be specific. If a number is missing, say "not disclosed" rather than inventing it.

CLUB MARKET SNAPSHOT (ground truth when present):
{facts_block}

PRIOR GROK STOCK ASSESSMENT (reuse these facts; do not contradict the snapshot):
{_prior_assessment_block(assessment)}

CLUB KELLY WORK (do not invent a different formula; summarize this evidence):
{kelly.get("text")}

Write a concise memo covering these seven sections, in this order:

1) Logos — What is true?
   What does the company actually do? What economic problem does it solve? Who pays it? What are the secular drivers?
2) Direction — Where is it going?
   Revenue and EPS growth YoY and QoQ. Revenue and EPS 3-year trajectory. Industry growth. Competitive position. Catalysts.
3) Execution — Can management actually deliver?
   Gross and net margins. Cash flow. Balance sheet cash and debt. CapEx. Milestones. Guidance vs results.
4) Valuation — What are we being asked to pay?
   Stock price, market cap, forward P/E or the right alternative metric, analyst targets, 50-day and 200-day averages.
5) Market structure — What is the market doing?
   Price trend, volume, support/resistance, order flow, sentiment.
6) Stewardship — How should EFA own it?
   Stock, LEAP, spread, private shares, or wait. How much capital (this must tie to the Kelly number above).
7) Kelly — How much risk has the evidence earned?
   Summarize the club Kelly work above. Use the provided p, b, and half-Kelly fraction. Do not invent a new Kelly equation.

Return ONLY valid JSON. No markdown fences.

{{
  "company": "{display}",
  "ticker": "{tkr}",
  "narrative_markdown": "full memo with headings 1-7",
  "logos": {{
    "what_company_does": "",
    "economic_problem": "",
    "who_pays": "",
    "secular_drivers": ""
  }},
  "direction": {{
    "rev_eps_yoy_qoq": "",
    "rev_eps_3yr": "",
    "industry_growth": "",
    "competitive_position": "",
    "catalysts": ""
  }},
  "execution": {{
    "gross_net_margins": "",
    "cash_flow": "",
    "cash_and_debt": "",
    "capex": "",
    "milestones": "",
    "guidance_vs_results": ""
  }},
  "valuation": {{
    "price_and_cap": "",
    "forward_pe": "",
    "analyst_targets": "",
    "sma_50_200": ""
  }},
  "market_structure": {{
    "price_trend": "",
    "volume": "",
    "support_resistance": "",
    "order_flow": "",
    "sentiment": ""
  }},
  "stewardship": {{
    "vehicle": "Stock or LEAP or Spread or Private shares or Wait",
    "capital_size": "",
    "rationale": ""
  }},
  "kelly": {{
    "summary": "",
    "win_probability": {kelly.get("win_probability") if kelly.get("win_probability") is not None else 0.65},
    "net_odds": {kelly.get("net_odds") if kelly.get("net_odds") is not None else 1.5},
    "half_kelly": ""
  }}
}}
"""


def flatten_logos_rows(parsed):
    rows = []
    for key, title, fields in LOGOS_SECTIONS:
        block = _section_dict(parsed, key)
        for field, label in fields:
            val = block.get(field)
            if val not in (None, ""):
                rows.append({"Section": title, "Item": label, "Grok": str(val)})
    return rows


def build_logos_pdf(entry, generated_at=None):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    parsed = entry.get("parsed") or {}
    ticker = entry.get("ticker") or parsed.get("ticker") or ""
    company = parsed.get("company") or entry.get("company") or ticker
    stamp = assessment_run_stamp(entry, generated_at)

    def write_line(doc, height, text, **kwargs):
        doc.set_x(doc.l_margin)
        doc.cell(0, height, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kwargs)

    class LogosPDF(FPDF):
        def header(self):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", 13)
            write_line(self, 7, "EFA Investment Club - LOGOS (What is true)")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(70)
            write_line(self, 5, f"Run: {stamp}  |  {company} ({ticker})")
            self.set_text_color(0)
            self.ln(1)
            self.set_draw_color(170)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)

        def footer(self):
            self.set_y(-12)
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(90)
            self.cell(
                0,
                8,
                f"Generated {stamp}  |  Page {self.page_no()}/{{nb}}  |  Not investment advice",
                align="C",
            )

    pdf = LogosPDF(format="letter")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(14, 16, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    write_line(pdf, 7, f"{company} ({ticker})")
    pdf.set_font("Helvetica", "I", 9)
    write_line(pdf, 5, f"LOGOS — What is true?  |  Run {stamp}")
    pdf.ln(2)

    narrative = parsed.get("narrative_markdown") or entry.get("analysis") or ""
    if narrative:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.4, _pdf_safe(narrative))
        pdf.ln(2)

    for key, title, fields in LOGOS_SECTIONS:
        block = _section_dict(parsed, key)
        pdf.set_font("Helvetica", "B", 10)
        write_line(pdf, 6, title)
        pdf.set_font("Helvetica", "", 8)
        for field, label in fields:
            val = block.get(field)
            if val in (None, ""):
                continue
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 8)
            pdf.multi_cell(0, 4, _pdf_safe(label))
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "", 8)
            pdf.multi_cell(0, 4, _pdf_safe(val))
            pdf.ln(0.4)
        pdf.ln(1)

    return bytes(pdf.output())


def run_grok_logos(client, company_name, ticker, snapshot=None, assessment=None, analyst_name="EFA member"):
    if client is None:
        raise RuntimeError("Grok API client is not configured.")
    prompt = build_logos_prompt(
        company_name,
        ticker,
        snapshot=snapshot,
        assessment=assessment,
        analyst_name=analyst_name,
    )
    response = client.chat.completions.create(
        model="grok-4-1-fast",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.35,
        max_tokens=5000,
    )
    content = (response.choices[0].message.content or "").strip()
    parsed = parse_assessment_response(content)
    tokens = 0
    if getattr(response, "usage", None) is not None:
        tokens = getattr(response.usage, "total_tokens", 0) or 0
    kelly = kelly_evidence_brief(assessment)
    kelly_block = _section_dict(parsed, "kelly")
    if kelly.get("highlight") and not kelly_block.get("half_kelly"):
        kelly_block["half_kelly"] = format_pct(kelly["highlight"]["half_kelly"])
        parsed["kelly"] = kelly_block
    now = datetime.now()
    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M"),
        "run_at": now.isoformat(timespec="seconds"),
        "ticker": str(ticker).upper().strip(),
        "company": parsed.get("company") or company_name or ticker,
        "analysis": content,
        "parsed": parsed,
        "tokens": tokens,
        "snapshot": snapshot or {},
        "kelly_brief": kelly,
        "prompt_version": "logos_v1",
        "analyst_name": analyst_name,
    }


def render_logos_panel(
    *,
    grok_client,
    get_fundamentals,
    ticker,
    company_name,
    latest_assessment,
    analyst_name,
    finnhub_client=None,
):
    import pandas as pd
    import streamlit as st

    from efa_club_persistence import load_logos_analyses, save_logos_analyses

    st.markdown("---")
    st.markdown("### LOGOS — What is true?")
    st.caption(
        "Seven-section club memo (Logos, Direction, Execution, Valuation, Market structure, Stewardship, Kelly). "
        "Uses the ticker above and reuses any assessment/Kelly numbers already run. "
        "Saved runs collapse like Tab 6."
    )

    st.session_state.logos_analyses = load_logos_analyses()
    logos_history = list(st.session_state.logos_analyses or [])

    if st.button("🧭 Run LOGOS framework", type="primary", key="run_logos_framework"):
        tkr = (ticker or (latest_assessment or {}).get("ticker") or "").strip().upper()
        if not tkr:
            st.error("Enter a ticker at the top of this tab first.")
        elif grok_client is None:
            st.error("Grok API key not configured.")
        else:
            with st.spinner(f"Grok is filling LOGOS for {tkr}..."):
                try:
                    fund_data = get_fundamentals(tkr) or {}
                    name = company_name or (latest_assessment or {}).get("company") or fund_data.get("Company") or tkr
                    snapshot = (latest_assessment or {}).get("snapshot") or fetch_assessment_snapshot(
                        tkr,
                        fundamentals_row=fund_data,
                        finnhub_client=finnhub_client,
                    )
                    entry = run_grok_logos(
                        grok_client,
                        name,
                        tkr,
                        snapshot=snapshot,
                        assessment=latest_assessment,
                        analyst_name=analyst_name or "EFA member",
                    )
                    logos_history.append(entry)
                    st.session_state.logos_analyses = logos_history
                    if save_logos_analyses(logos_history):
                        st.success(f"LOGOS saved — {entry['ticker']} @ {entry['timestamp']}")
                    else:
                        st.warning("Saved in this session only — persistence write failed.")
                    st.session_state.latest_logos = entry
                except Exception as e:
                    st.error(f"LOGOS run failed: {e}")

    latest_logos = st.session_state.get("latest_logos")
    if not latest_logos and logos_history:
        latest_logos = logos_history[-1]
        st.session_state.latest_logos = latest_logos

    if latest_logos:
        parsed = latest_logos.get("parsed") or {}
        stamp = assessment_run_stamp(latest_logos)
        vehicle = _section_dict(parsed, "stewardship").get("vehicle") or "n/a"
        st.markdown(f"#### Latest LOGOS: {latest_logos.get('company')} ({latest_logos.get('ticker')}) — run {stamp}")
        st.info(f"**Stewardship:** {vehicle}")
        st.markdown(parsed.get("narrative_markdown") or latest_logos.get("analysis") or "_No LOGOS memo_")
        rows = flatten_logos_rows(parsed)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        try:
            pdf_bytes = build_logos_pdf(latest_logos)
        except Exception as e:
            pdf_bytes = b""
            st.warning(f"LOGOS PDF could not be built: {e}")
        name = latest_logos.copy()
        name["ticker"] = f"LOGOS_{latest_logos.get('ticker', 'STOCK')}"
        st.download_button(
            "📄 Download LOGOS PDF (timestamped)",
            data=pdf_bytes or b"",
            file_name=assessment_download_name(name, "pdf"),
            mime="application/pdf",
            key="dl_logos_pdf",
            disabled=not pdf_bytes,
        )

    st.markdown("### 📜 Saved LOGOS memos")
    st.caption("Each LOGOS run is saved. Expand a row to reread it or download the timestamped PDF.")
    if not logos_history:
        st.info("No saved LOGOS memos yet. Run the framework above.")
        return

    for idx, entry in enumerate(sorted(logos_history, key=lambda x: x.get("timestamp", ""), reverse=True)[:25]):
        parsed = entry.get("parsed") or {}
        stamp = assessment_run_stamp(entry)
        token_info = f" ({entry.get('tokens', 'N/A')} tokens)" if entry.get("tokens") else ""
        company = parsed.get("company") or entry.get("company") or entry.get("ticker")
        vehicle = _section_dict(parsed, "stewardship").get("vehicle") or "n/a"
        title = f"🧭 {entry.get('ticker')} — {company} — {stamp}{token_info}"
        with st.expander(title, expanded=False):
            st.info(f"**Stewardship:** {vehicle}  |  Run {stamp}")
            st.markdown(parsed.get("narrative_markdown") or entry.get("analysis") or "No memo.")
            rows = flatten_logos_rows(parsed)
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            try:
                pdf_bytes = build_logos_pdf(entry)
            except Exception:
                pdf_bytes = b""
            dl_name = dict(entry)
            dl_name["ticker"] = f"LOGOS_{entry.get('ticker', 'STOCK')}"
            st.download_button(
                "📄 PDF",
                data=pdf_bytes or b"",
                file_name=assessment_download_name(dl_name, "pdf"),
                mime="application/pdf",
                key=f"dl_logos_hist_{idx}_{entry.get('ticker')}_{stamp}",
                disabled=not pdf_bytes,
            )
