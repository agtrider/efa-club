"""
EFA stock assessment template — Grok research prompt + printable Kelly report.

Used by Tab 10. No Streamlit import except inside render_stock_assessment_tab().
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from efa_club_kelly import (
    DEFAULT_KELLY_ADJUSTMENT,
    build_half_kelly_matrix,
    format_pct,
    format_units,
    highlight_cell,
    load_workbook_formulas,
    matrix_to_fraction_table,
    matrix_to_stake_table,
)

ASSESSMENT_FIELDS = [
    ("summary", "1. Company summary"),
    ("years_public", "2. Years publicly traded"),
    ("what_they_do", "3. What they do"),
    ("industry", "4. Industry"),
    ("competitors", "5. Competitors"),
    ("differentiators", "6. What differentiates them"),
    ("best_of_breed", "7. Best of breed?"),
    ("growth_eps_targets", "8. 12-month growth and EPS targets"),
    ("forward_pe_target", "9. Forward P/E target"),
    ("market_cap_price", "10. Current market cap and price"),
    ("yoy_performance", "11. Year-over-year performance"),
    ("sma_50", "12. 50-day moving average"),
    ("sma_200", "13. 200-day moving average"),
    ("analyst_ratings", "14. Analyst coverage (buy / hold / sell)"),
    ("average_price_target", "15. Average price target"),
    ("total_cash", "16. Total cash (latest quarter)"),
    ("cash_flow", "17. Levered and unlevered cash flow"),
    ("recommendation", "18. Stock recommendation"),
    ("recommendation_rationale", "18b. Recommendation rationale"),
]


def _fmt_billions(val):
    try:
        number = float(val)
    except (TypeError, ValueError):
        return None
    if abs(number) >= 1_000_000:
        return f"${number / 1e9:.2f}B"
    if abs(number) >= 1_000:
        return f"${number / 1e6:.1f}M"
    return f"${number:,.0f}"


def _fmt_price(val):
    try:
        number = float(val)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return f"${number:.2f}"


def fetch_assessment_snapshot(ticker, fundamentals_row=None, finnhub_client=None):
    """Club market snapshot passed into Grok so price/SMA/cash are not hallucinated."""
    from efa_club_services import fetch_ticker_info, safe_float, safe_int

    tkr = str(ticker or "").upper().strip()
    snapshot = {
        "ticker": tkr,
        "company": tkr,
        "facts": {},
        "fact_lines": [],
    }
    if not tkr:
        return snapshot

    info = {}
    try:
        info = fetch_ticker_info(tkr, finnhub_client=finnhub_client, use_cache=True) or {}
    except Exception as e:
        snapshot["facts"]["info_error"] = str(e)

    company = (fundamentals_row or {}).get("Company") or info.get("longName") or info.get("shortName") or tkr
    snapshot["company"] = company

    facts = {
        "company": company,
        "industry": info.get("industry") or (fundamentals_row or {}).get("Industry"),
        "sector": info.get("sector"),
        "summary": (info.get("longBusinessSummary") or "")[:1200] or None,
        "current_price": (fundamentals_row or {}).get("Current Price"),
        "market_cap": (fundamentals_row or {}).get("Market Cap") or _fmt_billions(info.get("marketCap")),
        "forward_pe": (fundamentals_row or {}).get("Forward P/E") or (
            f"{safe_float(info.get('forwardPE')):.2f}" if safe_float(info.get("forwardPE")) else None
        ),
        "sma_50": (fundamentals_row or {}).get("50d SMA") or _fmt_price(info.get("fiftyDayAverage")),
        "sma_200": (fundamentals_row or {}).get("200d SMA") or _fmt_price(info.get("twoHundredDayAverage")),
        "analyst_target": (fundamentals_row or {}).get("Analyst Target") or _fmt_price(info.get("targetMeanPrice")),
        "analyst_count": (fundamentals_row or {}).get("Analysts") or safe_int(info.get("numberOfAnalystOpinions")),
        "trailing_eps": (fundamentals_row or {}).get("12MMT EPS"),
        "forward_eps": (fundamentals_row or {}).get("Forward EPS"),
        "total_cash": (fundamentals_row or {}).get("Cash (B)") or _fmt_billions(info.get("totalCash")),
        "free_cash_flow": (fundamentals_row or {}).get("FCF (B)") or _fmt_billions(info.get("freeCashflow")),
        "ebitda": (fundamentals_row or {}).get("3MMT EBIT") or _fmt_billions(info.get("ebitda")),
        "operating_cash_flow": _fmt_billions(info.get("operatingCashflow")),
        "price_source": (fundamentals_row or {}).get("Price Source"),
    }

    epoch = safe_float(info.get("firstTradeDateEpochUtc") or info.get("firstTradeDateEpoch"))
    if epoch and epoch > 0:
        listed = datetime.fromtimestamp(epoch, tz=timezone.utc)
        years = (datetime.now(timezone.utc) - listed).days / 365.25
        facts["listed_since"] = listed.strftime("%Y-%m-%d")
        facts["years_public"] = f"{years:.1f} years (listed {listed.strftime('%Y-%m-%d')})"

    try:
        import yfinance as yf

        stock = yf.Ticker(tkr)
        hist = stock.history(period="2y", auto_adjust=True)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) >= 2:
                last = float(close.iloc[-1])
                facts.setdefault("current_price", _fmt_price(last))
                if len(close) >= 252:
                    prior = float(close.iloc[-252])
                    if prior:
                        yoy = (last / prior) - 1.0
                        facts["yoy_performance"] = f"{yoy * 100:+.1f}% (last close vs ~1y ago)"
                if facts.get("sma_50") in (None, "N/A") and len(close) >= 50:
                    facts["sma_50"] = _fmt_price(float(close.rolling(50).mean().iloc[-1]))
                if facts.get("sma_200") in (None, "N/A") and len(close) >= 200:
                    facts["sma_200"] = _fmt_price(float(close.rolling(200).mean().iloc[-1]))
        rec = getattr(stock, "recommendations_summary", None)
        if rec is not None and getattr(rec, "empty", True) is False:
            row = rec.iloc[0]
            parts = []
            total = 0
            for label, col in (
                ("Strong Buy", "strongBuy"),
                ("Buy", "buy"),
                ("Hold", "hold"),
                ("Sell", "sell"),
                ("Strong Sell", "strongSell"),
            ):
                n = safe_int(row.get(col)) or 0
                total += n
                if n:
                    parts.append(f"{label} {n}")
            if total:
                facts["analyst_count"] = total
                facts["analyst_ratings"] = f"{total} analysts — " + "; ".join(parts)
        cf = getattr(stock, "cashflow", None)
        if cf is not None and getattr(cf, "empty", True) is False:
            from efa_club_services import _yf_latest_row_value

            levered = _yf_latest_row_value(cf, ("Free Cash Flow",))
            ocf = _yf_latest_row_value(cf, ("Operating Cash Flow", "Total Cash From Operating Activities"))
            if levered is not None:
                facts["levered_fcf"] = _fmt_billions(levered)
            if ocf is not None:
                facts["operating_cash_flow"] = _fmt_billions(ocf)
    except Exception as e:
        facts["market_data_note"] = f"Supplemental market pull failed: {e}"

    snapshot["facts"] = {k: v for k, v in facts.items() if v not in (None, "", "N/A")}
    snapshot["fact_lines"] = [
        f"- {key.replace('_', ' ')}: {value}" for key, value in snapshot["facts"].items()
    ]
    return snapshot


def build_assessment_prompt(company_name, ticker, snapshot=None, analyst_name="EFA member"):
    facts_block = "None available — use latest public filings and market data."
    if snapshot and snapshot.get("fact_lines"):
        facts_block = "\n".join(snapshot["fact_lines"])

    display_name = (company_name or "").strip() or (snapshot or {}).get("company") or ticker
    tkr = str(ticker or "").upper().strip()

    return f"""You are a senior investment analyst for the Equity for All Investment Club (EFAIC).
Prepare a simple stock assessment template for the following publicly traded company.

Company name: {display_name}
Ticker: {tkr}
Prepared for: {analyst_name}

CLUB MARKET SNAPSHOT (treat as ground truth when a value is present; if a field is missing, fill from latest public information and label it Estimated):
{facts_block}

Write a 1-2 page assessment that will be the club's reusable template for future public-company writeups.

Cover these numbered sections, in this order:
1) Summary of the company
2) How long they have been publicly traded
3) What they do
4) What their industry is
5) Who their competitors are
6) What differentiates them
7) Determine if they are best of breed
8) Provide 12-month growth and EPS targets
9) Provide forward P/E target
10) Provide current market cap and price
11) Provide YoY performance
12) Provide 50-day moving average price
13) Provide 200-day moving average price
14) Provide how many analysts are following the stock and a breakdown of buy, hold, sell ratings
15) Provide average price target
16) Provide total cash as of latest quarter
17) Provide leveraged and unlevered cash flow
18) Provide a stock recommendation based on all available public information

Do NOT invent a Kelly formula or a Kelly matrix. The club app will attach a half-Kelly matrix after your writeup. You MUST still estimate Kelly inputs from the thesis:
- kelly_win_probability: a number in [0, 1], typically near 0.55, 0.65, or 0.70
- kelly_net_odds: expected net odds per unit risked (1 = +100, 1.5 = +150, 3 = +200/+300 style payoff). Use 1, 1.5, or 3 when that is a fair approximation.
- kelly_rationale: one or two sentences explaining those two numbers.

IMPORTANT:
- Return ONLY valid JSON. No markdown fences. No text before or after the JSON.
- Be honest, specific, and data-driven. Say "not disclosed" rather than guessing silently.
- narrative_markdown must be a complete 1-2 page club memo using numbered headings 1-18.

Return this exact JSON structure:
{{
  "company": "Full company name",
  "ticker": "{tkr}",
  "narrative_markdown": "full 1-2 page memo with numbered sections 1-18",
  "summary": "",
  "years_public": "",
  "what_they_do": "",
  "industry": "",
  "competitors": "",
  "differentiators": "",
  "best_of_breed": "",
  "growth_eps_targets": "",
  "forward_pe_target": "",
  "market_cap_price": "",
  "yoy_performance": "",
  "sma_50": "",
  "sma_200": "",
  "analyst_ratings": "",
  "average_price_target": "",
  "total_cash": "",
  "cash_flow": "",
  "recommendation": "Buy, Hold, Sell, or Avoid",
  "recommendation_rationale": "one clear paragraph",
  "kelly_win_probability": 0.65,
  "kelly_net_odds": 1.5,
  "kelly_rationale": ""
}}
"""


def parse_assessment_response(content):
    text = (content or "").strip()
    if not text:
        return {"raw": "", "narrative_markdown": ""}
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    payload = match.group(0) if match else cleaned
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            parsed.setdefault("raw", text)
            if not parsed.get("narrative_markdown"):
                parsed["narrative_markdown"] = text
            return parsed
    except Exception:
        pass
    return {"raw": text, "narrative_markdown": text}


def _md_to_html(text):
    raw = (text or "").replace("\r\n", "\n")
    if not raw.strip():
        return "<p>No narrative.</p>"
    lines = []
    in_list = False
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif re.match(r"^\d+[\.\)]\s+", stripped):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p><strong>{html.escape(stripped)}</strong></p>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            item = stripped[2:]
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(item))
            lines.append(f"<li>{item}</li>")
        elif stripped == "":
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append("")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            escaped = html.escape(stripped)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            lines.append(f"<p>{escaped}</p>")
    if in_list:
        lines.append("</ul>")
    return "\n".join(lines)


def _rec_class(rec):
    text = str(rec or "").lower()
    if "buy" in text and "avoid" not in text:
        return "buy"
    if "hold" in text:
        return "hold"
    if "sell" in text or "avoid" in text:
        return "avoid"
    return "neutral"


def build_printable_report(assessment, matrix, workbook=None, snapshot=None, generated_at=None):
    parsed = assessment.get("parsed") or {}
    ticker = assessment.get("ticker") or parsed.get("ticker") or ""
    company = parsed.get("company") or assessment.get("company") or ticker
    generated_at = generated_at or assessment_run_stamp(assessment)
    rec = parsed.get("recommendation") or "n/a"
    rec_class = _rec_class(rec)
    highlight = highlight_cell(
        matrix,
        parsed.get("kelly_win_probability"),
        parsed.get("kelly_net_odds"),
    )
    workbook = workbook or load_workbook_formulas()
    wb_name = Path(workbook.get("path") or "EFA - Kelly Formula.xlsx").name

    fact_rows = []
    for key, label in ASSESSMENT_FIELDS:
        value = parsed.get(key)
        if value in (None, ""):
            continue
        fact_rows.append(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        )
    facts_html = "\n".join(fact_rows) or "<tr><td colspan='2'>No structured fields parsed.</td></tr>"

    odds = matrix.get("net_odds") or []
    frac_header = "".join(f"<th>b={odds_val:g}</th>" for odds_val in odds)
    frac_rows = []
    for item in matrix.get("fraction_grid") or []:
        p = item["win_probability"]
        cells = [f"<th>{p * 100:.0f}%</th>"]
        for odds_val in odds:
            cell = item.get(f"odds_{odds_val:g}") or {}
            marked = ""
            if highlight and abs(highlight["win_probability"] - p) < 1e-9 and abs(highlight["net_odds"] - odds_val) < 1e-9:
                marked = " class='hl'"
            cells.append(f"<td{marked}>{html.escape(format_pct(cell.get('half_kelly')))}</td>")
        frac_rows.append("<tr>" + "".join(cells) + "</tr>")

    stake_tables = []
    by_bankroll = {}
    for row in matrix.get("stake_rows") or []:
        by_bankroll.setdefault(row["bankroll"], []).append(row)
    for br in matrix.get("bankrolls") or []:
        header = "".join(f"<th>b={odds_val:g}</th>" for odds_val in odds)
        body = []
        for p in matrix.get("win_probs") or []:
            cells = [f"<th>{p * 100:.0f}%</th>"]
            for odds_val in odds:
                match = next(
                    (
                        r
                        for r in by_bankroll.get(br, [])
                        if abs(r["win_probability"] - p) < 1e-9 and abs(r["net_odds"] - odds_val) < 1e-9
                    ),
                    None,
                )
                marked = ""
                if highlight and abs(highlight["win_probability"] - p) < 1e-9 and abs(highlight["net_odds"] - odds_val) < 1e-9:
                    marked = " class='hl'"
                cells.append(
                    f"<td{marked}>{html.escape(format_units(match['suggested_stake'] if match else None))}</td>"
                )
            body.append("<tr>" + "".join(cells) + "</tr>")
        stake_tables.append(
            f"<h4>Bankroll = {br:g} unit{'s' if br != 1 else ''}</h4>"
            f"<table><thead><tr><th>Win p</th>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        )

    highlight_html = ""
    if highlight:
        highlight_html = (
            f"<p class='callout'>Grok base case nearest grid: "
            f"p={highlight['win_probability'] * 100:.0f}%, b={highlight['net_odds']:g} → "
            f"half-Kelly {html.escape(format_pct(highlight['half_kelly']))} "
            f"(full Kelly {html.escape(format_pct(highlight['full_kelly']))}).</p>"
        )
    kelly_note = html.escape(str(parsed.get("kelly_rationale") or ""))

    snapshot_note = ""
    if snapshot and snapshot.get("facts"):
        snapshot_note = (
            "<p class='muted'>Club snapshot used as ground truth for price, SMAs, cash, and analyst counts where available.</p>"
        )

    css = """
      @page { size: letter; margin: 0.55in; }
      body { font-family: Georgia, "Times New Roman", serif; color: #1b1b1b; margin: 0; }
      h1,h2,h3,h4 { font-family: "Segoe UI", Arial, sans-serif; margin: 0.4em 0 0.25em; }
      h1 { font-size: 20px; }
      h2 { font-size: 16px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
      h3 { font-size: 14px; }
      h4 { font-size: 12px; margin-top: 10px; }
      p, li, td, th { font-size: 11.5px; line-height: 1.35; }
      .banner { background: #111827; color: #fff; padding: 12px 16px; }
      .banner .meta { font-size: 11px; opacity: 0.85; }
      .layout { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 16px; padding: 12px 16px 20px; }
      .panel { break-inside: avoid; }
      table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; }
      th, td { border: 1px solid #d4d4d4; padding: 4px 6px; text-align: left; vertical-align: top; }
      th { background: #f3f4f6; }
      td.hl, tr td.hl { background: #fef3c7; font-weight: 700; }
      .rec { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: 700; }
      .rec.buy { background: #dcfce7; color: #166534; }
      .rec.hold { background: #dbeafe; color: #1e40af; }
      .rec.avoid { background: #fee2e2; color: #991b1b; }
      .rec.neutral { background: #f3f4f6; }
      .callout { background: #fff7ed; border-left: 4px solid #f59e0b; padding: 8px 10px; }
      .muted { color: #6b7280; font-size: 11px; }
      .formula { font-family: Consolas, "Courier New", monospace; background: #f8fafc; padding: 8px; }
      .print-btn { margin: 10px 16px 0; padding: 8px 12px; background: #111827; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
      @media print {
        .no-print { display: none !important; }
        .layout { grid-template-columns: 1fr 1fr; gap: 10px; padding: 0; }
        a { text-decoration: none; color: inherit; }
      }
      @media (max-width: 900px) {
        .layout { grid-template-columns: 1fr; }
      }
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>EFA Stock Assessment — {html.escape(str(ticker))} {html.escape(str(company))}</title>
  <style>{css}</style>
</head>
<body>
  <div class="banner">
    <h1>EFA Investment Club — Stock Assessment Template</h1>
    <div class="meta">{html.escape(str(company))} ({html.escape(str(ticker))}) · {html.escape(generated_at)} · Kelly source: {html.escape(wb_name)}</div>
  </div>
  <button class="print-btn no-print" onclick="window.print()">Print assessment + Kelly together</button>
  <div class="layout">
    <section class="panel">
      <h2>Grok assessment</h2>
      <p><span class="rec {rec_class}">{html.escape(str(rec))}</span></p>
      {_md_to_html(parsed.get("narrative_markdown") or assessment.get("analysis") or "")}
      {snapshot_note}
      <h3>Structured answers</h3>
      <table>{facts_html}</table>
    </section>
    <section class="panel">
      <h2>20. Half-Kelly matrix</h2>
      <div class="formula">
        Classic (workbook B3): {html.escape(workbook.get("binary_formula", "f* = (p * b - q) / b"))}<br/>
        Half-Kelly: f½ = {matrix.get("adjustment", 0.5):g} × f*<br/>
        Suggested units = f½ × bankroll<br/>
        Workbook C19 (comparison): {html.escape(str(workbook.get("workbook_equation", "")))}
      </div>
      <p class="muted">Grid: win probability {", ".join(f"{p*100:.0f}%" for p in matrix.get("win_probs", []))} ·
      net odds {", ".join(f"{b:g}" for b in odds)} ·
      bankroll {", ".join(f"{br:g}" for br in matrix.get("bankrolls", []))}.</p>
      {highlight_html}
      {f"<p>{kelly_note}</p>" if kelly_note else ""}
      <h3>Half-Kelly fraction of bankroll</h3>
      <table>
        <thead><tr><th>Win p</th>{frac_header}</tr></thead>
        <tbody>{''.join(frac_rows)}</tbody>
      </table>
      <h3>Suggested units by bankroll</h3>
      {''.join(stake_tables)}
      <p class="muted">Classic half-Kelly is the club sizing number. Workbook C19 is more aggressive because it uses (p×(b+1) − q) / bankroll rather than (p×b − q) / b.</p>
    </section>
  </div>
  <p class="muted" style="padding:0 16px 16px;">Template for future assessments of publicly traded companies. Not investment advice. Print this page (Ctrl+P) to keep the writeup and Kelly matrix together.</p>
</body>
</html>
"""


def build_markdown_report(assessment, matrix, workbook=None):
    parsed = assessment.get("parsed") or {}
    ticker = assessment.get("ticker") or parsed.get("ticker") or ""
    company = parsed.get("company") or assessment.get("company") or ticker
    lines = [
        f"# EFA Stock Assessment — {company} ({ticker})",
        "",
        parsed.get("narrative_markdown") or assessment.get("analysis") or "",
        "",
        "## 20. Half-Kelly matrix",
        "",
        f"- Classic (B3): `{matrix.get('formula', {}).get('classic')}`",
        f"- Half-Kelly: `{matrix.get('formula', {}).get('half')}`",
        f"- Suggested units: `{matrix.get('formula', {}).get('stake')}`",
        f"- Workbook C19: `{matrix.get('formula', {}).get('workbook_c19')}`",
        "",
    ]
    if parsed.get("kelly_rationale"):
        lines.extend([parsed["kelly_rationale"], ""])
    highlight = highlight_cell(matrix, parsed.get("kelly_win_probability"), parsed.get("kelly_net_odds"))
    if highlight:
        lines.append(
            f"Grok base case nearest grid: p={highlight['win_probability']*100:.0f}%, "
            f"b={highlight['net_odds']:g} → half-Kelly {format_pct(highlight['half_kelly'])}."
        )
        lines.append("")
    lines.append("### Half-Kelly fractions")
    lines.append("")
    for row in matrix_to_fraction_table(matrix):
        bits = [f"{k} {v}" for k, v in row.items()]
        lines.append("- " + "; ".join(bits))
    lines.append("")
    lines.append("### Suggested units (f½ × bankroll)")
    lines.append("")
    for row in matrix_to_stake_table(matrix):
        lines.append(
            f"- p={row['Win p']}, b={row['Net odds b']}, BR={row['Bankroll']}: "
            f"{row['Suggested units (f½ × BR)']} (C19 {row['Workbook C19']})"
        )
    return "\n".join(lines)


def assessment_run_stamp(assessment=None, generated_at=None):
    if generated_at:
        return str(generated_at)
    if assessment:
        if assessment.get("timestamp"):
            return str(assessment["timestamp"])
        run_at = assessment.get("run_at")
        if run_at:
            try:
                return datetime.fromisoformat(str(run_at)).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return str(run_at)
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def assessment_download_name(assessment, ext):
    ticker = str(assessment.get("ticker") or "STOCK").upper()
    stamp = assessment_run_stamp(assessment).replace(":", "").replace(" ", "_")
    stamp = re.sub(r"[^0-9A-Za-z_-]+", "", stamp)
    return f"EFA_assessment_{ticker}_{stamp}.{ext}"


def _pdf_safe(text):
    raw = str(text or "")
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00d7": "x",
        "\u00bd": "1/2",
        "\u03bc": "u",
        "\u03c3": "s",
        "\u2192": "->",
    }
    for src, dest in replacements.items():
        raw = raw.replace(src, dest)
    raw = re.sub(r"[#*_`]+", "", raw)
    return raw.encode("latin-1", "replace").decode("latin-1")


def _entry_matrix(entry):
    matrix = entry.get("kelly_matrix")
    if isinstance(matrix, dict) and matrix.get("stake_rows"):
        return matrix
    return build_half_kelly_matrix()


def build_assessment_pdf(assessment, matrix=None, workbook=None, generated_at=None):
    """1-2 page PDF of the Grok writeup + Kelly matrix, stamped with run date/time."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    parsed = assessment.get("parsed") or {}
    matrix = matrix or _entry_matrix(assessment)
    workbook = workbook or load_workbook_formulas()
    ticker = assessment.get("ticker") or parsed.get("ticker") or ""
    company = parsed.get("company") or assessment.get("company") or ticker
    stamp = assessment_run_stamp(assessment, generated_at)
    rec = parsed.get("recommendation") or "n/a"
    highlight = highlight_cell(matrix, parsed.get("kelly_win_probability"), parsed.get("kelly_net_odds"))
    narrative = parsed.get("narrative_markdown") or assessment.get("analysis") or "No narrative."

    def write_line(doc, height, text, **kwargs):
        doc.set_x(doc.l_margin)
        doc.cell(0, height, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kwargs)

    class AssessmentPDF(FPDF):
        def header(self):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", 13)
            write_line(self, 7, "EFA Investment Club - Stock Assessment + Half-Kelly")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(70)
            write_line(self, 5, f"Run: {stamp}  |  {company} ({ticker})  |  Saved club research memo")
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

    pdf = AssessmentPDF(format="letter")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(14, 16, 14)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 11)
    write_line(pdf, 7, f"{company} ({ticker})")
    pdf.set_font("Helvetica", "B", 10)
    write_line(pdf, 6, f"Recommendation: {rec}   |   Run {stamp}")
    rationale = parsed.get("recommendation_rationale") or ""
    if rationale:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, _pdf_safe(rationale))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    write_line(pdf, 7, "Grok assessment")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4.4, _pdf_safe(narrative))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    write_line(pdf, 7, "Structured answers")
    for _key, label in ASSESSMENT_FIELDS:
        value = parsed.get(_key)
        if value in (None, ""):
            continue
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 8)
        pdf.multi_cell(0, 4, _pdf_safe(label))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(0, 4, _pdf_safe(value))
        pdf.ln(0.5)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    write_line(pdf, 7, "20. Half-Kelly matrix")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        0,
        4.2,
        _pdf_safe(
            f"Classic (B3): {workbook.get('binary_formula')}\n"
            f"Half-Kelly: f1/2 = {matrix.get('adjustment', 0.5):g} x f*\n"
            "Suggested units = f1/2 x bankroll\n"
            f"Workbook C19: {workbook.get('workbook_equation')}"
        ),
    )
    if highlight:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            0,
            5,
            _pdf_safe(
                f"Grok base case nearest grid: p={highlight['win_probability']*100:.0f}%, "
                f"b={highlight['net_odds']:g} -> half-Kelly {format_pct(highlight['half_kelly'])}"
            ),
        )
    if parsed.get("kelly_rationale"):
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.2, _pdf_safe(parsed.get("kelly_rationale")))

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    write_line(pdf, 6, "Half-Kelly fraction of bankroll")
    odds = matrix.get("net_odds") or []
    col_w = [28] + [40] * len(odds)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(col_w[0], 6, "Win p", border=1)
    for i, odds_val in enumerate(odds):
        pdf.cell(col_w[i + 1], 6, f"b={odds_val:g}", border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for item in matrix.get("fraction_grid") or []:
        pdf.set_x(pdf.l_margin)
        pdf.cell(col_w[0], 6, f"{item['win_probability']*100:.0f}%", border=1)
        for i, odds_val in enumerate(odds):
            cell = item.get(f"odds_{odds_val:g}") or {}
            pdf.cell(col_w[i + 1], 6, format_pct(cell.get("half_kelly")), border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    write_line(pdf, 6, "Suggested units by bankroll (f1/2 x BR)")
    pdf.set_font("Helvetica", "B", 7)
    headers = ["Win p", "Odds b", "f1/2", "BR", "Units", "C19"]
    widths = [22, 22, 24, 18, 40, 40]
    pdf.set_x(pdf.l_margin)
    for header, width in zip(headers, widths):
        pdf.cell(width, 6, header, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for row in matrix.get("stake_rows") or []:
        pdf.set_x(pdf.l_margin)
        values = [
            f"{row['win_probability']*100:.0f}%",
            f"{row['net_odds']:g}",
            format_pct(row["half_kelly"]),
            f"{row['bankroll']:g}",
            format_units(row["suggested_stake"]),
            format_units(row["workbook_c19"]),
        ]
        for value, width in zip(values, widths):
            pdf.cell(width, 5, _pdf_safe(value), border=1)
        pdf.ln()

    pdf.set_font("Helvetica", "I", 8)
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        0,
        4,
        _pdf_safe(
            f"Template for future assessments of publicly traded companies. Run timestamp: {stamp}."
        ),
    )
    return bytes(pdf.output())


def run_grok_assessment(client, company_name, ticker, snapshot=None, analyst_name="EFA member"):
    if client is None:
        raise RuntimeError("Grok API client is not configured.")
    prompt = build_assessment_prompt(company_name, ticker, snapshot=snapshot, analyst_name=analyst_name)
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
        "prompt_version": "stock_assessment_kelly_v1",
        "analyst_name": analyst_name,
    }


def render_stock_assessment_tab(
    *,
    grok_client,
    get_fundamentals,
    portfolio_tickers,
    watchlist_tickers,
    analyst_name,
    finnhub_client=None,
):
    import pandas as pd
    import streamlit as st
    import streamlit.components.v1 as components

    from efa_club_logos import render_logos_panel
    from efa_club_persistence import load_stock_assessments, save_stock_assessments

    st.subheader("📄 Stock Assessment + Half-Kelly")
    st.caption(
        "New research template (local review). Grok writeup and the EFA Kelly workbook matrix "
        "print together on one 1–2 page report. Not pushed to Git until you batch it."
    )

    workbook = load_workbook_formulas()
    wb_path = workbook.get("path")
    if wb_path:
        st.success(f"Kelly workbook loaded: `{Path(wb_path).name}`")
    else:
        st.info("Using built-in Kelly formulas (workbook file not found beside the app).")

    st.session_state.stock_assessments = load_stock_assessments()

    suggestions = list(dict.fromkeys([t for t in (portfolio_tickers or []) + (watchlist_tickers or []) if t]))
    col_a, col_b, col_c = st.columns([1.2, 1, 1])
    with col_a:
        company_name = st.text_input("Company name", key="assess_company_name", placeholder="e.g. First Solar")
    with col_b:
        preset = st.selectbox(
            "Fill ticker from club lists",
            options=["(type below)"] + suggestions,
            key="assess_preset_ticker",
        )
    with col_c:
        typed_ticker = st.text_input("Ticker", key="assess_ticker", placeholder="e.g. FSLR")
        ticker = (typed_ticker or ("" if preset == "(type below)" else preset)).strip().upper()

    with st.expander("Kelly grid parameters (defaults match the club prompt)", expanded=False):
        st.write(
            f"Classic formula: `{workbook.get('binary_formula')}` · "
            f"Adjustment: {workbook.get('kelly_adjustment')}"
        )
        st.caption("Win probabilities 0.55 / 0.65 / 0.70 · Net odds 1 / 1.5 / 3 · Bankroll 1 / 2 / 3 / 5")

    run_col, logos_col = st.columns([1, 1])
    with run_col:
        run = st.button("🧠 Run Grok assessment + Kelly matrix", type="primary", key="run_stock_assessment")
    with logos_col:
        st.caption("Use **Run LOGOS framework** in the LOGOS block directly under these buttons.")

    if run:
        if not ticker:
            st.error("Enter a ticker (and company name) to start the assessment.")
        elif grok_client is None:
            st.error("Grok API key not configured. Add GROK_API_KEY to the local environment or secrets.toml.")
        else:
            with st.spinner(f"Pulling club snapshot and asking Grok to assess {ticker}..."):
                try:
                    fund_data = get_fundamentals(ticker) or {}
                    if not company_name:
                        company_name = fund_data.get("Company") or ticker
                    snapshot = fetch_assessment_snapshot(
                        ticker,
                        fundamentals_row=fund_data,
                        finnhub_client=finnhub_client,
                    )
                    entry = run_grok_assessment(
                        grok_client,
                        company_name,
                        ticker,
                        snapshot=snapshot,
                        analyst_name=analyst_name or "EFA member",
                    )
                    matrix = build_half_kelly_matrix()
                    entry["kelly_matrix"] = matrix
                    history = list(st.session_state.get("stock_assessments") or [])
                    history.append(entry)
                    st.session_state.stock_assessments = history
                    if save_stock_assessments(history):
                        st.success(f"Assessment saved — {entry['ticker']} @ {entry['timestamp']}")
                    else:
                        st.warning("Saved in this session only — persistence write failed.")
                    st.session_state.latest_stock_assessment = entry
                except Exception as e:
                    st.error(f"Assessment failed: {e}")

    history = st.session_state.get("stock_assessments") or []
    latest = st.session_state.get("latest_stock_assessment")
    if not latest and history:
        latest = history[-1]
        st.session_state.latest_stock_assessment = latest

    logos_kwargs = dict(
        grok_client=grok_client,
        get_fundamentals=get_fundamentals,
        ticker=ticker or (latest or {}).get("ticker"),
        company_name=company_name or (latest or {}).get("company"),
        latest_assessment=latest,
        analyst_name=analyst_name,
        finnhub_client=finnhub_client,
    )
    render_logos_panel(**logos_kwargs)

    if not latest:
        st.info("Enter a ticker, then run the assessment and/or LOGOS. Kelly is computed in-app from the EFA workbook.")
        with st.expander("Preview half-Kelly matrix (template)", expanded=False):
            preview = build_half_kelly_matrix()
            st.dataframe(pd.DataFrame(matrix_to_fraction_table(preview)), hide_index=True, width="stretch")
            st.dataframe(pd.DataFrame(matrix_to_stake_table(preview)), hide_index=True, width="stretch")
        return

    parsed = latest.get("parsed") or {}
    matrix = _entry_matrix(latest)
    report_html = build_printable_report(latest, matrix, workbook=workbook, snapshot=latest.get("snapshot"))
    report_md = build_markdown_report(latest, matrix, workbook=workbook)
    try:
        report_pdf = build_assessment_pdf(latest, matrix, workbook=workbook)
    except Exception as pdf_err:
        report_pdf = b""
        st.warning(f"PDF could not be built: {pdf_err}")
    rec = parsed.get("recommendation") or "n/a"
    highlight = highlight_cell(matrix, parsed.get("kelly_win_probability"), parsed.get("kelly_net_odds"))
    stamp = assessment_run_stamp(latest)

    st.markdown(f"### Latest: {latest.get('company', latest.get('ticker'))} ({latest.get('ticker')}) — run {stamp}")
    rec_l = str(rec).lower()
    if "buy" in rec_l and "avoid" not in rec_l:
        st.success(f"Recommendation: {rec}")
    elif "hold" in rec_l:
        st.info(f"Recommendation: {rec}")
    else:
        st.warning(f"Recommendation: {rec}")
    if parsed.get("recommendation_rationale"):
        st.caption(parsed["recommendation_rationale"])

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            "📄 Download PDF (timestamped)",
            data=report_pdf or b"",
            file_name=assessment_download_name(latest, "pdf"),
            mime="application/pdf",
            key="dl_assess_pdf",
            disabled=not report_pdf,
        )
    with dl2:
        st.download_button(
            "🖨️ Download printable HTML",
            data=report_html.encode("utf-8"),
            file_name=assessment_download_name(latest, "html"),
            mime="text/html",
            key="dl_assess_html",
        )
    with dl3:
        st.download_button(
            "📝 Download markdown",
            data=report_md.encode("utf-8"),
            file_name=assessment_download_name(latest, "md"),
            mime="text/markdown",
            key="dl_assess_md",
        )

    if highlight:
        st.caption(
            f"Kelly base case: p={highlight['win_probability']*100:.0f}%, "
            f"b={highlight['net_odds']:g} → half-Kelly {format_pct(highlight['half_kelly'])}."
        )

    with st.expander("Grok assessment writeup (click to expand)", expanded=False):
        st.markdown(parsed.get("narrative_markdown") or latest.get("analysis") or "_No narrative_")
        rows = []
        for key, label in ASSESSMENT_FIELDS:
            value = parsed.get(key)
            if value not in (None, ""):
                rows.append({"Item": label, "Grok": str(value)})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with st.expander("Half-Kelly matrix (click to expand)", expanded=False):
        st.code(
            f"{workbook.get('binary_formula')}\n"
            f"f½ = {matrix.get('adjustment', DEFAULT_KELLY_ADJUSTMENT):g} × f*\n"
            "suggested units = f½ × bankroll"
        )
        if highlight:
            st.info(
                f"Grok base case mapped to p={highlight['win_probability']*100:.0f}%, "
                f"b={highlight['net_odds']:g} → half-Kelly {format_pct(highlight['half_kelly'])}."
            )
        if parsed.get("kelly_rationale"):
            st.caption(parsed["kelly_rationale"])
        st.markdown("**Fraction of bankroll (classic half-Kelly)**")
        st.dataframe(pd.DataFrame(matrix_to_fraction_table(matrix)), hide_index=True, width="stretch")
        st.markdown("**Suggested units by bankroll (1, 2, 3, 5)**")
        st.dataframe(pd.DataFrame(matrix_to_stake_table(matrix)), hide_index=True, width="stretch")
        st.write(workbook.get("binary_terms"))
        st.caption("C19 comparison column uses the Excel Kelly Equation, which is more aggressive than classic Kelly.")

    with st.expander("1–2 page printable template (collapsed by default)", expanded=False):
        st.caption("Assessment + Kelly together. PDF includes the run date/time in the header and footer.")
        components.html(report_html, height=1100, scrolling=True)

    st.markdown("### 📜 Saved Stock Assessments")
    st.caption("Each Grok + Kelly run is saved. Expand a row to reread it or download the timestamped PDF — same pattern as Tab 6 Deep Analysis.")
    if not history:
        st.info("No saved assessments yet. Run one above and it will appear here.")
    else:
        for idx, entry in enumerate(sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)[:25]):
            parsed_entry = entry.get("parsed") or {}
            entry_matrix = _entry_matrix(entry)
            entry_stamp = assessment_run_stamp(entry)
            token_info = f" ({entry.get('tokens', 'N/A')} tokens)" if entry.get("tokens") else ""
            company = parsed_entry.get("company") or entry.get("company") or entry.get("ticker")
            rec_entry = parsed_entry.get("recommendation") or "n/a"
            title = f"🔍 {entry.get('ticker')} — {company} — {entry_stamp}{token_info}"
            with st.expander(title, expanded=False):
                rec_l_entry = str(rec_entry).lower()
                if "buy" in rec_l_entry and "avoid" not in rec_l_entry:
                    st.success(f"**Recommendation: {rec_entry}**  |  Run {entry_stamp}")
                elif "hold" in rec_l_entry:
                    st.info(f"**Recommendation: {rec_entry}**  |  Run {entry_stamp}")
                else:
                    st.warning(f"**Recommendation: {rec_entry}**  |  Run {entry_stamp}")
                if parsed_entry.get("recommendation_rationale"):
                    st.caption(parsed_entry["recommendation_rationale"])

                st.markdown("**Full Analysis:**")
                st.markdown(parsed_entry.get("narrative_markdown") or entry.get("analysis") or "No analysis available.")

                st.markdown("**Half-Kelly matrix**")
                st.dataframe(
                    pd.DataFrame(matrix_to_fraction_table(entry_matrix)),
                    hide_index=True,
                    width="stretch",
                )

                try:
                    pdf_bytes = build_assessment_pdf(entry, entry_matrix, workbook=workbook)
                except Exception:
                    pdf_bytes = b""
                html_bytes = build_printable_report(
                    entry, entry_matrix, workbook=workbook, snapshot=entry.get("snapshot")
                ).encode("utf-8")
                md_bytes = build_markdown_report(entry, entry_matrix, workbook=workbook).encode("utf-8")
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.download_button(
                        "📄 PDF",
                        data=pdf_bytes or b"",
                        file_name=assessment_download_name(entry, "pdf"),
                        mime="application/pdf",
                        key=f"dl_hist_pdf_{idx}_{entry.get('ticker')}_{entry_stamp}",
                        disabled=not pdf_bytes,
                    )
                with d2:
                    st.download_button(
                        "🖨️ HTML",
                        data=html_bytes,
                        file_name=assessment_download_name(entry, "html"),
                        mime="text/html",
                        key=f"dl_hist_html_{idx}_{entry.get('ticker')}_{entry_stamp}",
                    )
                with d3:
                    st.download_button(
                        "📝 Markdown",
                        data=md_bytes,
                        file_name=assessment_download_name(entry, "md"),
                        mime="text/markdown",
                        key=f"dl_hist_md_{idx}_{entry.get('ticker')}_{entry_stamp}",
                    )


