# agents/signal.py
class SignalAgent:
    def __init__(self):
        print("📈 Signal Agent Initialized (Rule-based + Confidence Driven)")

    def generate_signal(self, research_data: dict) -> str:
        """
        Generate trading signal based on rich research data
        """
        ticker = research_data.get("ticker", "UNKNOWN")
        price = research_data.get("current_price", 250.0)
        rsi = research_data.get("rsi", 50.0)
        return_20d = research_data.get("return_20d", 0.0)
        trend = research_data.get("trend", "neutral")
        sentiment = research_data.get("sentiment", "neutral")
        confidence = research_data.get("confidence", 0.5)

        signal = "Hold"
        reason = ""

        # === Strong Bullish Conditions ===
        if (trend in ["strong_bullish", "bullish"] and 
            rsi < 65 and 
            return_20d > 3 and 
            confidence >= 0.65):
            
            signal = "Buy"
            reason = f"Strong momentum + RSI {rsi:.1f} + Trend {trend}"

        # === Oversold Bounce ===
        elif rsi < 35 and trend != "bearish":
            signal = "Buy"
            reason = f"Oversold bounce (RSI {rsi:.1f})"

        # === Strong Bearish Conditions ===
        elif (trend == "bearish" and rsi > 68) or (return_20d < -8):
            signal = "Sell"
            reason = f"Overextended / Weak momentum (RSI {rsi:.1f})"

        # === Take Profit on Strong Run ===
        elif rsi > 75 and return_20d > 15:
            signal = "Sell"
            reason = "Take profit - Overbought"

        # === Default Hold ===
        else:
            reason = f"Neutral conditions (RSI {rsi:.1f}, Trend: {trend})"

        print(f"   🎯 {ticker} → {signal.upper():<4} | Conf: {confidence:.2f} | {reason}")

        return signal