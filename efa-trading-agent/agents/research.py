# agents/research.py
import yfinance as yf
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

# ====================== LOCAL PRICE CACHE ======================
PRICE_CACHE_FILE = Path("local_data/price_cache.json")
PRICE_CACHE_FILE.parent.mkdir(exist_ok=True)

class PriceCache:
    def __init__(self):
        self.cache = self._load()

    def _load(self):
        if PRICE_CACHE_FILE.exists():
            try:
                with open(PRICE_CACHE_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save(self):
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(self.cache, f, indent=2)

    def get_prices(self, ticker: str, days: int = 200):
        """Return list of closing prices (most recent first)"""
        data = self.cache.get(ticker, {})
        prices = data.get("prices", [])
        return prices[:days] if prices else []

    def update_ticker(self, ticker: str, prices: list):
        """Store up to 200 days of closing prices"""
        self.cache[ticker] = {
            "prices": prices[:200],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self._save()

    def has_sufficient_data(self, ticker: str, min_days: int = 40):
        return len(self.get_prices(ticker)) >= min_days

# Global cache instance
price_cache = PriceCache()

# ====================== RESEARCH AGENT ======================
class ResearchAgent:
    def __init__(self):
        print("📡 Research Agent Initialized (v7 - Local Price Cache)")

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, close: pd.Series):
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "macd": round(float(macd_line.iloc[-1]), 4),
            "macd_signal": round(float(signal_line.iloc[-1]), 4),
            "macd_hist": round(float(histogram.iloc[-1]), 4)
        }

    def analyze_ticker(self, ticker: str):
        print(f"   🔍 Fetching data for {ticker}...")

        current_price = 250.0
        rsi = 52.0
        sma20 = 245.0
        sma50 = 240.0
        sma200 = 230.0
        trend = "neutral"
        analyst_target = 310.0
        confidence = 0.55
        macd_data = {"macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0}

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # === REAL CURRENT PRICE (always fresh) ===
            price = info.get("currentPrice") or info.get("regularMarketPreviousClose") or info.get("previousClose")
            if price and price > 0:
                current_price = float(price)
            else:
                hist5 = stock.history(period="5d", auto_adjust=True)
                if not hist5.empty:
                    current_price = float(hist5["Close"].iloc[-1])

            print(f"   💰 Real price: ${current_price:.2f}")

            # === TRY YFINANCE FIRST (3 months) ===
            close = None
            try:
                data = stock.history(period="3mo", auto_adjust=True)
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker in data.columns.get_level_values(0):
                        close = data[ticker]["Close"]
                    else:
                        close = data.iloc[:, 0]
                else:
                    close = data["Close"]
                close = close.astype(float).dropna()
            except:
                close = None

            # === FALLBACK TO LOCAL CACHE IF NEEDED ===
            if close is None or len(close) < 40:
                cached_prices = price_cache.get_prices(ticker, 200)
                if len(cached_prices) >= 40:
                    print(f"   📦 Using cached data ({len(cached_prices)} days)")
                    close = pd.Series(cached_prices)
                else:
                    # First time seeing this ticker → fetch and cache
                    print(f"   💾 Building cache for {ticker}...")
                    try:
                        full_data = stock.history(period="1y", auto_adjust=True)
                        if not full_data.empty:
                            if isinstance(full_data.columns, pd.MultiIndex):
                                close_full = full_data[ticker]["Close"] if ticker in full_data.columns.get_level_values(0) else full_data.iloc[:, 0]
                            else:
                                close_full = full_data["Close"]
                            close_full = close_full.astype(float).dropna().tolist()
                            price_cache.update_ticker(ticker, close_full)
                            close = pd.Series(close_full[-200:])  # use last 200 days
                    except:
                        close = None

            # === CALCULATE REAL INDICATORS ===
            if close is not None and len(close) >= 40:
                rsi = self._calculate_rsi(close, 14)
                sma20 = float(close.rolling(20).mean().iloc[-1])
                sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else sma20
                sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50
                macd_data = self._calculate_macd(close)
                print(f"   📈 RSI={rsi:.1f} | MACD_Hist={macd_data['macd_hist']}")
            else:
                print(f"   ⚠️ Not enough data for {ticker} - using defaults")

            # === ANALYST TARGET ===
            try:
                analyst_target = info.get("targetMeanPrice")
                if not analyst_target or analyst_target < current_price * 0.5:
                    analyst_target = current_price * 1.22
            except:
                analyst_target = current_price * 1.22

            # === TREND ===
            if current_price > sma50 > sma200:
                trend = "strong_bullish"
            elif current_price > sma20 > sma50:
                trend = "bullish"
            elif current_price < sma20 < sma50:
                trend = "bearish"
            elif current_price < sma50 < sma200:
                trend = "strong_bearish"
            else:
                trend = "neutral"

            # === CONFIDENCE ===
            confidence = 0.55
            if 40 <= rsi <= 65: confidence += 0.12
            elif rsi < 35 or rsi > 75: confidence -= 0.08
            if trend in ["strong_bullish", "strong_bearish"]: confidence += 0.15
            elif trend == "bullish": confidence += 0.08
            upside = (analyst_target - current_price) / current_price
            if 0.10 < upside < 0.45: confidence += 0.10
            elif upside > 0.60: confidence += 0.05
            if macd_data["macd_hist"] > 0 and macd_data["macd"] > macd_data["macd_signal"]:
                confidence += 0.08
            elif macd_data["macd_hist"] < 0: confidence -= 0.05
            confidence = max(0.35, min(0.92, round(confidence, 2)))

            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "rsi": round(rsi, 1),
                "sma_20": round(sma20, 2),
                "sma_50": round(sma50, 2),
                "sma_200": round(sma200, 2),
                "trend": trend,
                "analyst_target": round(float(analyst_target), 2),
                "confidence": confidence,
                "macd": macd_data["macd"],
                "macd_signal": macd_data["macd_signal"],
                "macd_hist": macd_data["macd_hist"],
            }

        except Exception as e:
            print(f"   ❌ Critical error on {ticker}: {e}")
            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "rsi": 52.0,
                "sma_20": round(current_price * 0.98, 2),
                "sma_50": round(current_price * 0.96, 2),
                "sma_200": round(current_price * 0.92, 2),
                "trend": "neutral",
                "analyst_target": round(current_price * 1.22, 2),
                "confidence": 0.50,
                "macd": 0.0,
                "macd_signal": 0.0,
                "macd_hist": 0.0,
            }