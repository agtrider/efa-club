# agents/orchestrator.py
from agents.research import ResearchAgent
from datetime import datetime

class Orchestrator:
    def __init__(self):
        self.research = ResearchAgent()
        print("🧠 Orchestrator Initialized - EFA Multi-Agent System v1.1")

    def _build_reason(self, ticker, recommendation, research, entry_price, exit_target, goal_type, investment_type):
        rsi = research.get("rsi", 50)
        trend = research.get("trend", "neutral").replace("_", " ")
        macd_hist = research.get("macd_hist", 0)
        macd = research.get("macd", 0)
        macd_signal = research.get("macd_signal", 0)
        confidence = research.get("confidence", 0.5)
        data_quality = research.get("data_quality", "unknown")
        current_price = research.get("current_price", 0)
        analyst_target = research.get("analyst_target", exit_target)
        upside_pct = ((analyst_target - current_price) / current_price * 100) if current_price > 0 else 0

        quality_note = {
            "main_app_history": "Indicators computed from live club price feed + daily history.",
            "yfinance_history": "Indicators computed from recent Yahoo daily bars.",
            "yfinance_1y": "Indicators computed from 1-year Yahoo history.",
            "local_cache": "Indicators computed from cached daily closes.",
            "insufficient_history": "Limited price history — treat signals cautiously.",
            "fallback": "Sparse data — recommendation leans on price/trend heuristics.",
            "error": "Data fetch failed — recommendation is low-confidence.",
        }.get(data_quality, "Indicators sourced from available market data.")

        macd_view = "bullish momentum" if macd_hist > 0 and macd > macd_signal else (
            "bearish momentum" if macd_hist < 0 else "neutral momentum"
        )

        base = (
            f"{quality_note} {ticker} is {trend} with RSI {rsi:.0f} "
            f"({self._rsi_label(rsi)}), MACD histogram {macd_hist:+.3f} ({macd_view}), "
            f"and model confidence {confidence:.0%}. "
            f"Analyst/consensus target ${analyst_target:.2f} implies {upside_pct:+.1f}% from ${current_price:.2f}. "
            f"For a {investment_type} / {goal_type} position: {recommendation}. "
            f"Suggested add near ${entry_price:.2f}, exit/review near ${exit_target:.2f}."
        )
        return base

    def _rsi_label(self, rsi):
        if rsi < 30:
            return "oversold"
        if rsi < 40:
            return "approaching oversold"
        if rsi > 75:
            return "overbought"
        if rsi > 65:
            return "elevated"
        return "neutral zone"

    def run_cycle(self, ticker: str = "TSLA", context=None):
        print(f"\n🚀 Starting trading cycle for {ticker} @ {datetime.now().strftime('%H:%M:%S')}")

        context = context if isinstance(context, dict) else {}
        research = self.research.analyze_ticker(ticker, context=context)

        goals = context.get("goals", {})
        investment_type = goals.get("investment_type", "Core")
        goal_type = goals.get("goal_type", "Long Term (>1 Yr)")

        live_price = context.get("live_price")
        current_price = live_price if live_price and live_price > 0 else research.get("current_price", 0)
        rsi = research.get("rsi", 50)
        sma20 = research.get("sma_20", current_price)
        sma50 = research.get("sma_50", current_price)
        sma200 = research.get("sma_200", current_price)
        trend = research.get("trend", "neutral")
        analyst_target = research.get("analyst_target", current_price * 1.15 if current_price else 0)
        confidence = research.get("confidence", 0.55)
        macd_hist = research.get("macd_hist", 0.0)
        macd = research.get("macd", 0.0)
        macd_signal = research.get("macd_signal", 0.0)

        if current_price > sma20:
            entry_price = round(sma20 * 0.985, 2)
        else:
            entry_price = round(current_price * 0.96, 2) if current_price > 0 else 0
        if rsi < 38 and current_price > 0:
            entry_price = round(current_price * 0.935, 2)

        exit_target = round(analyst_target, 2)
        if "Short Term" in goal_type:
            exit_target = round(analyst_target * 0.92, 2)

        recommendation = "Hold"
        reason = "Neutral setup — awaiting clearer trend confirmation."

        if investment_type == "Moonshot" or ticker in ["TE", "TSLA", "ACHR", "SMR", "FSLR"]:
            if trend in ["strong_bullish", "bullish"] and rsi < 58 and macd_hist > 0:
                recommendation = "Accumulate Aggressively"
            elif rsi < 42:
                recommendation = "Accumulate on Weakness"
            elif rsi > 75:
                recommendation = "Trim Position"
            else:
                recommendation = "Hold & Accumulate"

        elif ticker in ["SPY", "QQQ", "IWM"] or investment_type == "Core":
            if trend == "strong_bullish" and rsi < 65:
                recommendation = "Hold & Accumulate"
            elif rsi > 78:
                recommendation = "Hold"
            else:
                recommendation = "Hold"

        elif trend == "strong_bullish" and macd_hist > 0 and rsi < 60:
            recommendation = "Accumulate on Weakness"
        elif rsi < 40 and trend != "strong_bearish":
            recommendation = "Accumulate on Weakness"
        elif rsi > 78:
            recommendation = "Trim Position"
        elif trend == "strong_bearish":
            recommendation = "Hold / Reduce"

        if recommendation == "Hold" and confidence > 0.68 and trend in ["bullish", "strong_bullish"]:
            recommendation = "Hold & Accumulate"

        reason = self._build_reason(
            ticker, recommendation, research, entry_price, exit_target, goal_type, investment_type
        )

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
            "macd": round(macd, 3),
            "macd_signal": round(macd_signal, 3),
            "macd_hist": round(macd_hist, 3),
            "analyst_target": round(analyst_target, 2),
            "data_quality": research.get("data_quality", "unknown"),
            "quantity": 0,
            "status": "success"
        }

        print(f"   🎯 {ticker} → {recommendation} | RSI {rsi} | Conf {confidence} | Entry ${entry_price} | Target ${exit_target}")
        return result