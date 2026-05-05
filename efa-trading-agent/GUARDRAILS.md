#EFA AI TRADING AGENT - GUARDRAILS (V1)

## CORE SAFETY RULES
- Starting capital: $500 - $1,000 maximum
- No MARGIN ever (hard-coded block)
- Max risk per trade: 1% of total account ($5-$10 max)
- Max daily loss limit: $30 (emergency stop)
- Only approved assets (major stocks & crypto - no penny stocks, no shitcoins)

##Human-in-th-loop Rule
- Agent will only **suggest** trades in Phase 1
- All actual trades require human approval
- Full autonomous mode only after extensive paper trading success

##Kill Switch
- Immediate stop if daily loss exceeds $30
- Easy manual shutdown button

##Approved Trading Style (for now)
- Swing trading (1-10 day holds)
- Clear entry, stop-loss, and target rules required

This document will evolve as we test.

Last Updated: April 2026
