from efa_club_kelly import (
    build_half_kelly_matrix,
    classic_kelly_fraction,
    find_kelly_workbook,
    half_kelly_fraction,
    load_workbook_formulas,
    suggested_stake,
    workbook_c19,
)
from efa_club_logos import build_logos_pdf, build_logos_prompt
from efa_club_research import (
    assessment_download_name,
    build_assessment_pdf,
    build_assessment_prompt,
    build_printable_report,
    parse_assessment_response,
)


def test_classic_kelly_known_value():
    # p=0.60, b=1.5, q=0.40 → (0.90 - 0.40) / 1.5 = 1/3
    assert abs(classic_kelly_fraction(0.60, 1.5) - (1.0 / 3.0)) < 1e-9
    assert abs(half_kelly_fraction(0.60, 1.5) - (1.0 / 6.0)) < 1e-9
    assert abs(suggested_stake(0.60, 1.5, 3) - 0.5) < 1e-9


def test_half_kelly_matrix_shape():
    matrix = build_half_kelly_matrix()
    assert matrix["win_probs"] == [0.55, 0.65, 0.70]
    assert matrix["net_odds"] == [1.0, 1.5, 3.0]
    assert matrix["bankrolls"] == [1.0, 2.0, 3.0, 5.0]
    assert len(matrix["fraction_grid"]) == 3
    assert len(matrix["stake_rows"]) == 3 * 3 * 4
    p55_b1 = half_kelly_fraction(0.55, 1.0)
    assert abs(p55_b1 - 0.05) < 1e-9


def test_workbook_c19_is_more_aggressive_than_classic():
    classic_stake = suggested_stake(0.55, 1.0, 1.0)
    c19 = workbook_c19(0.55, 1.0, 1.0)
    assert classic_stake > 0
    assert c19 > classic_stake


def test_workbook_formulas_load_from_xlsx():
    path = find_kelly_workbook()
    assert path is not None, "EFA - Kelly Formula.xlsx should sit next to the app"
    formulas = load_workbook_formulas(path)
    assert "p*b-q" in formulas["binary_formula"].replace(" ", "")
    assert formulas["kelly_adjustment"] == 0.5
    assert formulas["path"]


def test_assessment_prompt_contains_numbered_sections_and_kelly_handoff():
    prompt = build_assessment_prompt("First Solar", "FSLR", snapshot={"fact_lines": ["- current_price: $100"]})
    assert "Enter Stock" not in prompt or "Ticker: FSLR" in prompt
    assert "Ticker: FSLR" in prompt
    assert "12-month growth and EPS targets" in prompt
    assert "leveraged and unlevered cash flow" in prompt
    assert "Do NOT invent a Kelly formula" in prompt
    assert "current_price: $100" in prompt


def test_parse_assessment_and_printable_report_includes_both_sides():
    raw = """{
      "company": "First Solar, Inc.",
      "ticker": "FSLR",
      "narrative_markdown": "## 1) Summary\\nFirst Solar makes cadmium-telluride modules.",
      "recommendation": "Hold",
      "recommendation_rationale": "Fairly valued versus the cycle.",
      "kelly_win_probability": 0.65,
      "kelly_net_odds": 1.5,
      "kelly_rationale": "Base case is a modest edge at 1.5:1."
    }"""
    parsed = parse_assessment_response(raw)
    assert parsed["ticker"] == "FSLR"
    assessment = {
        "ticker": "FSLR",
        "company": "First Solar, Inc.",
        "parsed": parsed,
        "analysis": raw,
    }
    assessment["timestamp"] = "2026-08-22 13:10"
    html = build_printable_report(assessment, build_half_kelly_matrix())
    assert "First Solar" in html
    assert "Half-Kelly" in html
    assert "Grok assessment" in html
    assert "Bankroll = 5" in html
    assert "f* = (p * b - q) / b" in html or "p * b - q" in html
    assert "2026-08-22 13:10" in html
    assert "2026-08-22_1310" in assessment_download_name(assessment, "pdf")
    pdf = build_assessment_pdf(assessment, build_half_kelly_matrix())
    assert pdf[:4] == b"%PDF"


def test_logos_prompt_covers_seven_sections():
    assessment = {
        "parsed": {
            "what_they_do": "Makes CdTe modules",
            "recommendation": "Hold",
            "kelly_win_probability": 0.65,
            "kelly_net_odds": 1.5,
            "kelly_rationale": "Modest edge.",
        },
        "kelly_matrix": build_half_kelly_matrix(),
    }
    prompt = build_logos_prompt(
        "First Solar",
        "FSLR",
        snapshot={"fact_lines": ["- current_price: $214"]},
        assessment=assessment,
    )
    assert "LOGOS means" in prompt or "What is true" in prompt
    assert "Who pays it?" in prompt
    assert "LEAP" in prompt
    assert "How much risk has the evidence earned" in prompt
    assert "Makes CdTe modules" in prompt
    assert "current_price: $214" in prompt
    assert "Do not invent a new Kelly equation" in prompt


def test_logos_pdf_is_stamped():
    raw = """{
      "company": "First Solar, Inc.",
      "ticker": "FSLR",
      "narrative_markdown": "1. Logos — What is true?\\nMakes modules.",
      "logos": {"what_company_does": "Makes CdTe modules", "who_pays": "Utilities"},
      "stewardship": {"vehicle": "Stock", "capital_size": "half-Kelly on bankroll 1"},
      "kelly": {"summary": "Evidence supports a modest half-Kelly.", "half_kelly": "12.5%"}
    }"""
    parsed = parse_assessment_response(raw)
    entry = {
        "ticker": "FSLR",
        "company": "First Solar, Inc.",
        "timestamp": "2026-08-22 15:40",
        "parsed": parsed,
        "analysis": raw,
    }
    pdf = build_logos_pdf(entry)
    assert pdf[:4] == b"%PDF"
    assert "LOGOS_FSLR" in assessment_download_name({**entry, "ticker": "LOGOS_FSLR"}, "pdf")
