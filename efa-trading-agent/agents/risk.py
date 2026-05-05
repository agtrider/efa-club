from config.guardrails import Guardrails
from datetime import datetime

class RiskAgent:
    def __init__(self):
        self.guardrails = Guardrails()
        print(" Risk Management Agent Initialize")

    def evaluate_trade(self, ticker: str, risk_amount: float):
        """Evaluate if a trade is allowed under guardrails"""
        print(f"\n Evaluating risk for {ticker} (${risk_amount:.2f} risk)")

        if self.guardrails.can_trade(risk_amount):
            print(" Trade PASSED risk checks")
            return{
                "approved": True,
                "max_position_size": self.guardrails.account_size * self.guardrails.max_risk_per_trade,
                "reason": "All guardrails passed"
            }
        else:
            print(" Trade BLOCKED by guardrails")
            return{
                "approved": False,
                "reason": "Guardrails violation (risk, daily limit, or position count)"
            }

# ==================================Quick Test ===============================================        
if __name__ == "__main__":
    print("===Running Risk Agent Test ===")
    agent = RiskAgent()
    result = agent.evaluate_trade("TSLA", 10.0)
    print("\nRrisk Evaluation Result:", result)
    print("=== Test Complete ===")        
        