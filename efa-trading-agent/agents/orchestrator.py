# agents/orchestrator.py
from agents.research import ResearchAgent
from datetime import datetime

class Orchestrator:
    def __init__(self):
        self.research = ResearchAgent()
        print("🧠 Orchestrator Initialized - EFA Multi-Agent System v1.0 Beta")

    def run_cycle(self, ticker: str = "TSLA", context=None):
        print(f"\n🚀 Starting trading cycle for {ticker} @ {datetime.now().strftime('%H:%M:%S')}")

        research = self.research.analyze_ticker(ticker)

        goals = context.get("goals", {}) if context and isinstance(context, dict) else {}
        investment_type = goals.get("investment_type", "Core")
        goal_type = goals.get("goal_type", "Long Term (>1 Yr)")

        current_price = research.get("current_price", 250.0)
        rsi = research.get("rsi", 52)
        sma20 = research.get("sma_20", current_price)
        sma50 = research.get("sma_50", current_price)
        sma200 = research.get("sma_200", current_price)
        trend = research.get("trend", "neutral")
        analyst_target = research.get("analyst_target", current_price * 1.22)
        confidence = research.get("confidence", 0.55)
        macd_hist = research.get("macd_hist", 0.0)

        # === DYNAMIC ENTRY / EXIT ===
        if current_price > sma20:
            entry_price = round(sma20 * 0.985, 2)
        else:
            entry_price = round(current_price * 0.96, 2)
        if rsi < 38:
            entry_price = round(current_price * 0.935, 2)

        exit_target = round(analyst_target, 2)
        if "Short Term" in goal_type:
            exit_target = round(analyst_target * 0.88, 2)

        # === BETA RECOMMENDATION ENGINE (much more differentiated) ===
        recommendation = "Hold"
        reason = "Neutral setup - waiting for clearer signal"

        # === AGGRESSIVE / MOONSHOT NAMES (TE, TSLA, ACHR, SMR, FSLR) ===
        if investment_type == "Moonshot" or ticker in ["TE", "TSLA", "ACHR", "SMR"]:
            if trend in ["strong_bullish", "bullish"] and rsi < 58 and macd_hist > 0:
                recommendation = "Accumulate Aggressively"
                reason = f"Moonshot setup in uptrend. Buy dips near ${entry_price}"
            elif rsi < 42:
                recommendation = "Accumulate on Weakness"
                reason = f"Strong oversold condition. Excellent entry near ${entry_price}"
            elif rsi > 75:
                recommendation = "Trim Position"
                reason = "Overbought - take some profits on this moonshot"
            else:
                recommendation = "Hold & Accumulate"
                reason = f"Constructive setup for {ticker}. Add on weakness near ${entry_price}"

        # === CORE / STABLE NAMES (SPY, etc.) ===
        elif ticker in ["SPY", "QQQ", "IWM"] or investment_type == "Core":
            if trend == "strong_bullish" and rsi < 65:
                recommendation = "Hold & Accumulate"
                reason = "Broad market uptrend - maintain core position, add on dips"
            elif rsi > 78:
                recommendation = "Hold"
                reason = "Market overbought - stay patient"
            else:
                recommendation = "Hold"
                reason = "Core holding - maintain allocation"

        # === GENERAL CASES ===
        elif trend == "strong_bullish" and macd_hist > 0 and rsi < 60:
            recommendation = "Accumulate on Weakness"
            reason = f"Strong momentum + healthy RSI. Buy dips near ${entry_price}"
        elif rsi < 40 and trend != "strong_bearish":
            recommendation = "Accumulate on Weakness"
            reason = f"Oversold condition. Good entry near ${entry_price}"
        elif rsi > 78:
            recommendation = "Trim Position"
            reason = "Extremely overbought - reduce exposure"
        elif trend == "strong_bearish":
            recommendation = "Hold / Reduce"
            reason = "Strong downtrend - protect capital, wait for stabilization"

        # Final safety net
        if recommendation == "Hold" and confidence > 0.68 and trend in ["bullish", "strong_bullish"]:
            recommendation = "Hold & Accumulate"
            reason = f"Constructive setup. Add on weakness near ${entry_price}"

        result = {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "recommended_action": recommendation,
            "reason": reason,
            "entry_price": entry_price,
            "exit_target": exit_target,
            "rsi": round(rsi, 1),
            "trend": trend.replace("_", " ").title(),
            "confidence": round(confidence, 2),
            "macd_hist": round(macd_hist, 3),
            "quantity": 0,
            "status": "success"
        }

        print(f"   🎯 {ticker} → {recommendation} | RSI {rsi} | Conf {confidence} | Entry ${entry_price} | Target ${exit_target}")
        return result