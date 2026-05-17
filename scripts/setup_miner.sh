#!/usr/bin/env bash
# Engram Miner Setup — one-shot setup on Ubuntu 22.04 / Debian 12
# Usage: curl -fsSL https://raw.githubusercontent.com/Dipraise1/-Engram-/main/scripts/setup_miner.sh | bash
set -euo pipefail

ENGRAM_DIR="/opt/engram"
PYTHON="python3.11"
VENV="$ENGRAM_DIR/.venv"
REPO="https://github.com/Dipraise1/-Engram-.git"
NETUID=450

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[engram]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()    { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ "$EUID" -ne 0 ]] && fail "Run as root: sudo bash setup_miner.sh"

echo ""
echo "  ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗"
echo "  ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║"
echo "  █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║"
echo "  ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║"
echo "  ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║"
echo "  ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝"
echo ""
echo "  Miner Setup · Subnet 450 (Testnet)"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages…"
apt-get update -qq
apt-get install -y -qq git curl wget build-essential \
    python3.11 python3.11-venv python3.11-dev \
    pkg-config libssl-dev docker.io 2>/dev/null || true

systemctl enable docker --now 2>/dev/null || true
success "System packages installed"

# ── 2. Rust ───────────────────────────────────────────────────────────────────
if ! command -v cargo &>/dev/null; then
    info "Installing Rust…"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --quiet
    source "$HOME/.cargo/env"
fi
success "Rust $(rustc --version | cut -d' ' -f2)"

# ── 3. Clone / update repo ───────────────────────────────────────────────────
if [[ -d "$ENGRAM_DIR/.git" ]]; then
    info "Updating existing repo…"
    git -C "$ENGRAM_DIR" pull --ff-only
else
    info "Cloning Engram…"
    git clone --depth 1 "$REPO" "$ENGRAM_DIR"
fi
success "Repo at $ENGRAM_DIR"

# ── 4. Python venv + dependencies ────────────────────────────────────────────
info "Creating Python venv…"
$PYTHON -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

info "Installing Python dependencies…"
"$VENV/bin/pip" install --quiet -e "$ENGRAM_DIR[dev]"
success "Python environment ready"

# ── 5. Build Rust wheel (optional) ───────────────────────────────────────────
info "Building Rust core wheel…"
"$VENV/bin/pip" install --quiet maturin
cd "$ENGRAM_DIR/engram-core"
"$VENV/bin/maturin" develop --release --quiet && success "Rust wheel built (faster proofs)" \
    || warn "Rust wheel build failed — miner will use pure Python fallback"
cd "$ENGRAM_DIR"

# ── 6. Qdrant ─────────────────────────────────────────────────────────────────
info "Starting Qdrant vector store…"
mkdir -p /opt/engram/qdrant_storage
if docker ps | grep -q qdrant; then
    success "Qdrant already running"
else
    docker run -d --name qdrant --restart unless-stopped \
        -p 6333:6333 \
        -v /opt/engram/qdrant_storage:/qdrant/storage \
        qdrant/qdrant >/dev/null 2>&1
    sleep 3
    curl -sf http://localhost:6333/healthz >/dev/null && success "Qdrant healthy" \
        || warn "Qdrant not yet healthy — it may still be starting"
fi

# ── 7. .env.miner ─────────────────────────────────────────────────────────────
if [[ ! -f "$ENGRAM_DIR/.env.miner" ]]; then
    info "Creating .env.miner…"
    PUBLIC_IP=$(curl -4 -sf https://ifconfig.me || echo "0.0.0.0")
    cat > "$ENGRAM_DIR/.env.miner" <<EOF
# Engram Miner — generated by setup_miner.sh
WALLET_NAME=engram
WALLET_HOTKEY=miner
SUBTENSOR_NETWORK=test
NETUID=$NETUID

MINER_PORT=8091
EXTERNAL_IP=$PUBLIC_IP

USE_LOCAL_EMBEDDER=true
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384

VECTOR_STORE_BACKEND=qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

LOG_LEVEL=INFO
EOF
    success ".env.miner created (EXTERNAL_IP=$PUBLIC_IP)"
else
    warn ".env.miner already exists — skipping"
fi

# ── 8. Wallet setup ───────────────────────────────────────────────────────────
info "Checking wallet…"
if "$VENV/bin/python" -c "
import os; os.environ.update(open('$ENGRAM_DIR/.env.miner').read().strip().split('\n') and {})
" 2>/dev/null; then
    : # just a syntax check
fi

echo ""
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo -e "${CYAN}  WALLET SETUP (do this now if not done yet)  ${NC}"
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo ""
echo "  btcli wallet new_coldkey --wallet.name engram"
echo "  btcli wallet new_hotkey  --wallet.name engram --wallet.hotkey miner"
echo ""
echo "  # Then register on testnet subnet 450:"
echo "  btcli subnet register \\"
echo "    --netuid 450 \\"
echo "    --wallet.name engram \\"
echo "    --wallet.hotkey miner \\"
echo "    --subtensor.network test"
echo ""

# ── 9. systemd service ────────────────────────────────────────────────────────
info "Installing systemd service…"
cat > /etc/systemd/system/engram-miner.service <<EOF
[Unit]
Description=Engram Miner — Bittensor Subnet 450
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
WorkingDirectory=$ENGRAM_DIR
EnvironmentFile=$ENGRAM_DIR/.env.miner
ExecStart=$VENV/bin/python neurons/miner.py
Restart=on-failure
RestartSec=30
MemoryMax=2G
MemoryHigh=1700M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
success "systemd service installed"

# ── 10. Seed initial data ─────────────────────────────────────────────────────
info "Seeding ground truth data (runs after miner starts)…"
# We schedule the seed after a delay so the miner is up
cat > /opt/engram/seed-after-start.sh <<'SEED'
#!/bin/bash
sleep 60
curl -sf http://localhost:8091/health >/dev/null 2>&1 && \
    /opt/engram/.venv/bin/python /opt/engram/scripts/seed_miner_ground_truth.py \
        --miner-url http://localhost:8091 2>/dev/null || true
SEED
chmod +x /opt/engram/seed-after-start.sh

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete! Next steps:           ${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}1.${NC} Set up your wallet (see above)"
echo -e "  ${CYAN}2.${NC} Edit ${YELLOW}$ENGRAM_DIR/.env.miner${NC} if needed"
echo -e "  ${CYAN}3.${NC} Start the miner:"
echo ""
echo "       systemctl enable --now engram-miner"
echo ""
echo -e "  ${CYAN}4.${NC} Watch logs:"
echo ""
echo "       journalctl -u engram-miner -f"
echo ""
echo -e "  ${CYAN}5.${NC} Check health:"
echo ""
echo "       curl http://localhost:8091/health"
echo ""
echo -e "${YELLOW}  Docs: https://github.com/Dipraise1/-Engram-/blob/main/docs/miner.md${NC}"
echo ""
