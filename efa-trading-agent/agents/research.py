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
        print("📡 Research Agent Initialized (v8 - Main App Price Bridge)")

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

    def analyze_ticker(self, ticker: str, context=None):
        print(f"   🔍 Fetching data for {ticker}...")
        context = context if isinstance(context, dict) else {}

        current_price = None
        rsi = None
        sma20 = None
        sma50 = None
        sma200 = None
        trend = "neutral"
        analyst_target = context.get("analyst_target")
        confidence = 0.55
        macd_data = {"macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0}
        data_quality = "fallback"
        close = None

        live_price = context.get("live_price")
        if live_price and float(live_price) > 0:
            current_price = float(live_price)
            print(f"   💰 Live price from main app: ${current_price:.2f}")

        close_prices = context.get("close_prices") or []
        if close_prices and len(close_prices) >= 14:
            close = pd.Series(close_prices, dtype=float).dropna()
            data_quality = "main_app_history"
            print(f"   📈 Using {len(close)} closes from main app history")

        try:
            stock = yf.Ticker(ticker)
            info = {}
            try:
                info = stock.info or {}
            except Exception:
                info = {}

            if current_price is None:
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if not price or price <= 0:
                    price = info.get("regularMarketPreviousClose") or info.get("previousClose")
                if not price or price <= 0:
                    hist = stock.history(period="5d", auto_adjust=True)
                    if not hist.empty:
                        price = float(hist["Close"].iloc[-1])
                if price and price > 0:
                    current_price = float(price)
                    print(f"   💰 yfinance price: ${current_price:.2f}")

            if close is None or len(close) < 14:
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
                    if len(close) >= 14:
                        data_quality = "yfinance_history"
                except Exception:
                    close = None

            if close is None or len(close) < 40:
                cached_prices = price_cache.get_prices(ticker, 200)
                if len(cached_prices) >= 40:
                    print(f"   📦 Using cached data ({len(cached_prices)} days)")
                    close = pd.Series(list(reversed(cached_prices)), dtype=float)
                    data_quality = "local_cache"
                else:
                    try:
                        full_data = stock.history(period="1y", auto_adjust=True)
                        if not full_data.empty:
                            if isinstance(full_data.columns, pd.MultiIndex):
                                close_full = full_data[ticker]["Close"] if ticker in full_data.columns.get_level_values(0) else full_data.iloc[:, 0]
                            else:
                                close_full = full_data["Close"]
                            close_full = close_full.astype(float).dropna().tolist()
                            price_cache.update_ticker(ticker, close_full)
                            close = pd.Series(close_full[-200:], dtype=float)
                            data_quality = "yfinance_1y"
                    except Exception:
                        close = None

            if current_price is None or current_price <= 0:
                if close is not None and len(close) > 0:
                    current_price = float(close.iloc[-1])
                else:
                    current_price = 0.0

            if close is not None and len(close) >= 14 and current_price > 0:
                rsi = self._calculate_rsi(close, 14)
                sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else current_price
                sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else current_price
                sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else current_price
                macd_data = self._calculate_macd(close)
                print(f"   📈 RSI={rsi:.1f} | MACD_Hist={macd_data['macd_hist']} | source={data_quality}")
            else:
                print(f"   ⚠️ Not enough history for {ticker} — limited indicator confidence")
                rsi = 50.0
                sma20 = current_price
                sma50 = current_price
                sma200 = current_price
                data_quality = "insufficient_history"

            if not analyst_target or analyst_target <= 0:
                try:
                    analyst_target = info.get("targetMeanPrice")
                except Exception:
                    analyst_target = None

            if not analyst_target or (current_price and analyst_target < current_price * 0.5):
                analyst_target = current_price * 1.15 if current_price > 0 else 0.0

            sma50 = sma50 or current_price
            sma200 = sma200 or current_price
            sma20 = sma20 or current_price

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

            confidence = 0.50
            if data_quality in ("main_app_history", "yfinance_history", "yfinance_1y"):
                confidence += 0.10
            elif data_quality == "local_cache":
                confidence += 0.05

            if rsi is not None:
                if 40 <= rsi <= 65:
                    confidence += 0.12
                elif rsi < 35 or rsi > 75:
                    confidence -= 0.08

            if trend in ["strong_bullish", "strong_bearish"]:
                confidence += 0.15
            elif trend == "bullish":
                confidence += 0.08

            if current_price and analyst_target:
                upside = (analyst_target - current_price) / current_price
                if 0.08 < upside < 0.45:
                    confidence += 0.10
                elif upside > 0.60:
                    confidence += 0.05
                elif upside < 0:
                    confidence -= 0.10

            if macd_data["macd_hist"] > 0 and macd_data["macd"] > macd_data["macd_signal"]:
                confidence += 0.08
            elif macd_data["macd_hist"] < 0:
                confidence -= 0.05

            confidence = max(0.30, min(0.92, round(confidence, 2)))

            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "rsi": round(rsi if rsi is not None else 50.0, 1),
                "sma_20": round(sma20, 2),
                "sma_50": round(sma50, 2),
                "sma_200": round(sma200, 2),
                "trend": trend,
                "analyst_target": round(float(analyst_target), 2),
                "confidence": confidence,
                "macd": macd_data["macd"],
                "macd_signal": macd_data["macd_signal"],
                "macd_hist": macd_data["macd_hist"],
                "data_quality": data_quality,
            }

        except Exception as e:
            print(f"   ❌ Critical error on {ticker}: {e}")
            safe_price = current_price or 0.0
            return {
                "ticker": ticker,
                "current_price": round(safe_price, 2),
                "rsi": 50.0,
                "sma_20": round(safe_price, 2),
                "sma_50": round(safe_price, 2),
                "sma_200": round(safe_price, 2),
                "trend": "neutral",
                "analyst_target": round(safe_price * 1.15, 2) if safe_price > 0 else 0.0,
                "confidence": 0.35,
                "macd": 0.0,
                "macd_signal": 0.0,
                "macd_hist": 0.0,
                "data_quality": "error",
            }