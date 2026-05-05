# backtest.py
import yfinance as yf
from agents.research import ResearchAgent
from agents.signal import SignalAgent
from agents.risk import RiskAgent
from agents.execution import ExecutionAgent

class Backtester:
    def __init__(self):
        self.research = ResearchAgent()
        self.signal = SignalAgent()
        self.risk = RiskAgent()
        self.execution = ExecutionAgent()
        print("📊 Backtester Initialized")

    def run_backtest(self, tickers: list, start_date: str = "2025-01-01"):
        print(f"\n📅 Starting Backtest from {start_date}")
        print(f"Testing {len(tickers)} tickers: {tickers}\n")

        for ticker in tickers:
            print(f"\n{'='*70}")
            print(f"BACKTESTING {ticker.upper()}")
            print('='*70)

            data = yf.download(ticker, start=start_date, progress=False)
            if len(data) < 60:
                print(f"   → Skipped: Not enough data")
                continue

            # Reset portfolio
            self.execution.portfolio = {
                "cash": 1000.0,
                "positions": {},
                "total_trades": 0,
                "winning_trades": 0
            }

            # Use .values for reliable scalars
            close_prices = data['Close'].values

            for i in range(40, len(close_prices)):
                try:
                    current_price = float(close_prices[i])

                    research_data = {
                        "ticker": ticker,
                        "current_price": current_price,
                        "return_1m": 0.0,
                        "rsi": 50.0,
                        "sentiment": "neutral",
                        "confidence": 0.55
                    }

                    signal = self.signal.generate_signal(research_data)
                    risk_result = self.risk.evaluate_trade(ticker, 10.0)

                    if risk_result.get("approved", False) and signal in ["Buy", "Sell"]:
                        self.execution.execute_trade(ticker, signal, current_price, 10.0)

                except Exception:
                    continue

            # Final results for this ticker
            final_value = self.execution.portfolio["cash"]
            last_price = float(close_prices[-1].item() if hasattr(close_prices[-1], 'item') else close_prices[-1])

            for pos in self.execution.portfolio["positions"].values():
                final_value += pos["quantity"] * last_price

            first_price = float(close_prices[0].item() if hasattr(close_prices[0], 'item') else close_prices[0])
            buy_hold = (1000.0 / first_price) * last_price

            print(f"   Agent Strategy : ${final_value:,.2f}  ({(final_value-1000)/1000*100:+.1f}%)")
            print(f"   Buy & Hold     : ${buy_hold:,.2f}  ({(buy_hold-1000)/1000*100:+.1f}%)")
            print(f"   Trades Made    : {self.execution.portfolio['total_trades']}")

            # Print daily summary after each ticker (or at the end)
            self.execution.print_daily_summary()
            
        print(f"\n{'='*70}")
        print("✅ FINAL BACKTEST Completed")
        print('='*70)
        
        


# ====================== RUN ======================
if __name__ == "__main__":
    bt = Backtester()
    
    your_tickers = ["TSLA", "NVDA", "AAPL", "HOOD", "SMR", "FSLR", "TE", "MSTR", "NOW", "CRM"]

    bt.run_backtest(tickers=your_tickers, start_date="2025-01-01")

