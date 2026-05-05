# main.py
import time
from datetime import datetime
from agents.orchestrator import Orchestrator

print("🚀 EFA AI Trading Agent - LIVE MODE")
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

orchestrator = Orchestrator()

tickers = ["TSLA", "NVDA", "AAPL", "HOOD", "SMR", "FSLR", "TE", "MSTR", "NOW", "CRM"]

cycle_count = 0

while True:
    try:
        cycle_count += 1
        print(f"\n{'='*80}")
        print(f"🔄 CYCLE #{cycle_count} @ {datetime.now().strftime('%H:%M:%S')}")
        print(f"Scanning {len(tickers)} tickers...")
        print('='*80)

        for ticker in tickers:
            print(f"\n→ Analyzing {ticker}")
            try:
                orchestrator.run_cycle(ticker)
            except Exception as e:
                print(f"   Error analyzing {ticker}: {e}")
            time.sleep(2)  # Small pause between tickers

        print(f"\n✅ Cycle #{cycle_count} completed. Next cycle in 60 seconds...")
        print('='*80)

        time.sleep(60)   # 1 minute between full cycles

    except KeyboardInterrupt:
        print("\n\n🛑 Trading Agent stopped by user.")
        break
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        time.sleep(60)