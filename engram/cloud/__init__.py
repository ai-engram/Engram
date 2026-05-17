"""
Engram Cloud Mining Layer

Allows users to mine Engram (netuid 450) from their phones by renting
managed cloud compute nodes. Payment flows through the x402 protocol
(HTTP 402 + on-chain settlement) via Dexter Cash.

Architecture:
  Phone (identity/wallet) ──HTTPS──► Cloud Gateway ──► Managed Mining Node
         │                                │
         │  sr25519 hotkey signs          │  x402 payment verified
         │  all session requests          │  before node is provisioned
         └────────────────────────────────┘

Components:
  session.py    — CloudMiningSession lifecycle
  provisioner.py — managed node pool allocation
  x402.py       — x402 payment middleware (Dexter Cash)
"""
