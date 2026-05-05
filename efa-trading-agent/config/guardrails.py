#========================EFA TRADING AGENT GUARDRAILS================================
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Guardrails:
    account_size:               float = 1000.0
    max_risk_per_trade:         float = 0.01
    daily_loss_limit:           float = 30.0
    max_concurrent_positions:   int = 3
    no_margin:                  bool = True
    min_confidence:             float = 0.65

    def __post_init__(self):
        self.daily_loss_today = 0.0
        self.current_positions = 0
        self.start_time = datetime.now()

    def can_trade(self, risk_amount: float) -> bool:
        if self.no_margin and risk_amount > (self.account_size * self.max_risk_per_trade):
            return False
        if self.daily_loss_today >= self.daily_loss_limit:
            return False
        if self.current_positions >= self.max_concurrent_positions:
            return False
        return True   
    
    def print_status(self):
        print(f"Account Size        : ${self.account_size:,.2f}")
        print(f"Max Risk/Trade      : {self.max_risk_per_trade*100:.1f}% (${self.account_size*self.max_risk_per_trade:.2f})")
        print(f"Daily Loss Limit    : ${self.daily_loss_limit:.2f}")
        print(f"Max Positions       : {self.max_concurrent_positions}")
        print(f"No Margin           : {'Enabled' if self.no_margin else 'Disabled'}")
        print(f"Current Positions   : {self.current_positions}")






