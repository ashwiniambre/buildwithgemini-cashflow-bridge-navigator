# My agent: Cashflow Bridge Navigator

One-liner: A conversational agent that helps individuals navigating temporary income gaps (such as medical/disability leave awaiting EDD) prioritize upcoming bills and arrange payment extensions with creditors using a catalog of their active cards and pending expenses.

Tool coverage:
- Memory: User's income gap context (current cash reserve, expected payout date, estimated deposit amount, and hardship preferences).
- Tools:
  - `calculate_cashflow_runway`: Calculates cashflow deficits, days until income arrival, and recommends payment priority (must-pay vs. safe-to-defer).
  - `draft_hardship_request`: Generates a professional, empathetic payment arrangement script for card issuers and utility providers.
- Catalog/UI: Catalog of pending bills and credit cards (balance, minimum due, due date, APR, hardship status) rendered as A2UI cards and a timeline table.
- Image gen: Generates a personalized visual "Cashflow Runway & Peace of Mind" roadmap summary.
- Sandbox: Python code sandbox execution for interest accrual math and cashflow date delta computations.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): Code sandbox for financial interest/runway calculations, Cloud Trace for observability.
