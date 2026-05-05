import yfinance as yf
import json
from datetime import datetime
import os
import csv

class ExecutionAgent:
    def __init__(self):
        self.portfolio_file = "data/portfolio.json"
        self.history_file = "data/portfolio_history.json"
        self.portfolio = self.load_portfolio()
        self.history = self.load_history()
        print("✅ Execution Agent (Paper Trading + Performance Tracking) Initialized")

    def load_portfolio(self):
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {     
            "cash": 1000.0,
            "positions": {},
            "total_trades": 0,
            "winning_trades": 0,
        }
    
    def save_portfolio(self):
        os.makedirs("data", exist_ok=True)
        with open(self.portfolio_file, 'w') as f:
            json.dump(self.portfolio, f, indent=2)

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_history(self):
        os.makedirs("data", exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def execute_trade(self, ticker: str, signal: str, current_price: float, risk_amount: float = 10.0):
        if signal == "Buy":
            quantity = risk_amount / current_price
            self.portfolio["cash"] -= risk_amount
            
            if ticker not in self.portfolio["positions"]:
                self.portfolio["positions"][ticker] = {"quantity": 0, "avg_price": 0}

            pos = self.portfolio["positions"][ticker]
            total_cost = pos["quantity"] * pos["avg_price"] + quantity * current_price
            pos["quantity"] += quantity
            pos["avg_price"] = total_cost / pos["quantity"] if pos["quantity"] > 0 else current_price

            self.portfolio["total_trades"] += 1
            print(f"✅ PAPER BUY: {quantity:.4f} shares of {ticker} @ ${current_price:.2f}")

        elif signal == "Sell" and ticker in self.portfolio["positions"]:
            pos = self.portfolio["positions"][ticker]
            if pos["quantity"] > 0:
                sell_value = pos["quantity"] * current_price
                self.portfolio["cash"] += sell_value
                print(f"✅ PAPER SELL: {pos['quantity']:.4f} shares of {ticker} @ ${current_price:.2f}")
                del self.portfolio["positions"][ticker]
                self.portfolio["total_trades"] += 1
                self.portfolio["winning_trades"] += 1

        self.save_portfolio()
        self.log_portfolio()
        return self.portfolio

    def log_portfolio(self):
        total_value = self.portfolio["cash"]
        for ticker, pos in self.portfolio["positions"].items():
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                current_price = info.get("currentPrice") or info.get("regularMarketPreviousClose") or 250.0
                position_value = pos["quantity"] * current_price
                total_value += position_value
            except:
                total_value += pos["quantity"] * 250.0

        win_rate = (self.portfolio["winning_trades"] / self.portfolio["total_trades"] * 100) if self.portfolio["total_trades"] > 0 else 0
        pnl = total_value - 1000.0

        print("\n=== DAILY SUMMARY ===")
        print(f"Total Portfolio Value : ${total_value:,.2f}")
        print(f"Cash                  : ${self.portfolio['cash']:,.2f}")
        print(f"Total P&L             : ${pnl:,.2f} ({pnl/10:+.1f}%)")
        print(f"Trades                : {self.portfolio['total_trades']}")
        print(f"Win Rate              : {win_rate:.1f}%")
        print(f"Open Positions        : {len(self.portfolio['positions'])}")
        print("="*40)

        self.history.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "portfolio_value": round(total_value, 2),
            "pnl": round(pnl, 2),
            "trades": self.portfolio["total_trades"]
        })
        self.save_history()

    def print_daily_summary(self):
        """Print clean daily performance summary"""
        portfolio = self.portfolio
        total_value = portfolio.get("cash", 1000.0)
        
        for pos in portfolio.get("positions", {}).values():
            total_value += pos.get("quantity", 0) * 100   # placeholder for backtest

        total_pnl = total_value - 1000.0
        total_trades = portfolio.get("total_trades", 0)
        win_rate = (portfolio.get("winning_trades", 0) / total_trades * 100) if total_trades > 0 else 0.0

        print(f"\n{'='*80}")
        print("📊 DAILY PERFORMANCE SUMMARY")
        print('='*80)
        print(f"💰 Total Portfolio Value : ${total_value:,.2f}")
        print(f"📈 Total P&L            : ${total_pnl:,.2f} ({total_pnl/10:+.1f}%)")
        print(f"📉 Trades Today         : {total_trades}")
        print(f"🏆 Win Rate             : {win_rate:.1f}%")
        print(f"💵 Current Cash         : ${portfolio.get('cash', 1000.0):,.2f}")
        print(f"📍 Open Positions       : {len(portfolio.get('positions', {}))}")
        print('='*80)

    def log_decision(self, ticker: str, signal: str, confidence: float, research_data: dict):
        os.makedirs("data", exist_ok=True)
        log_file = "data/trade_log.csv"
        
        if not os.path.exists(log_file):
            with open(log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "ticker", "signal", "confidence", "action"])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        action = "PROPOSED" if signal in ["Buy", "Sell"] else "HOLD"
        
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, ticker, signal, round(confidence, 3), action])

        print(f"📝 Logged: {action} {ticker} | {signal} | Conf: {confidence:.2f}")


# ============== Quick Test ==============
if __name__ == "__main__":
    print("=== Running Execution Agent Test ===")
    agent = ExecutionAgent()
    agent.execute_trade("TSLA", "Buy", 250.0, 50.0)
    agent.print_daily_summary()
    print("=== Test Complete ===")