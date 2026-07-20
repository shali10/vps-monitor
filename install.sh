#!/usr/bin/env bash
set -euo pipefail

REPO="shali10/vps-monitor"
BRANCH="main"
INSTALL_DIR="/opt/vps-monitor"
VENV_DIR="$INSTALL_DIR/.venv"

# ── colors ─────────────────────────────────────
BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*"; exit 1; }
step()  { printf "\n${BOLD}${CYAN}==>${NC} ${BOLD}%s${NC}\n" "$*"; }

# ── preflight ──────────────────────────────────
for cmd in python3 git; do
    command -v "$cmd" &>/dev/null || err "'$cmd' not found — install it first"
done

pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    info "Python $pyver"
else
    err "Python >= 3.10 required (got $pyver)"
fi

# ── clone / update ─────────────────────────────
step "Installing vps-monitor to $INSTALL_DIR"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Already cloned — pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
else
    git clone --depth 1 -b "$BRANCH" "https://github.com/$REPO.git" "$INSTALL_DIR"
    info "Cloned $REPO"
fi

# ── venv & deps ────────────────────────────────
step "Creating virtualenv"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install -q -U pip setuptools
pip install -q -r "$INSTALL_DIR/requirements.txt"

# Install bs4 (needed by bnm source)
pip install -q beautifulsoup4
info "Dependencies installed"

# ── config ─────────────────────────────────────
CONFIG_FILE="$INSTALL_DIR/config.json"
if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$INSTALL_DIR/config.example.json" "$CONFIG_FILE"
    info "Created config.json from example"
    warn "EDIT config.json with your Telegram bot token and chat IDs!"
    echo "   $ nano $CONFIG_FILE"
else
    info "config.json exists, skipped"
fi

# ── systemd timer links ────────────────────────
step "Installing systemd timers (user mode)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

for timer in czl dujiaojing; do
    ln -sf "$INSTALL_DIR/systemd/vps-monitor-v4-$timer.timer" "$SYSTEMD_DIR/"
    ln -sf "$INSTALL_DIR/systemd/vps-monitor-v4-$timer.service" "$SYSTEMD_DIR/"
done
systemctl --user daemon-reload

step "Creating .env from config"
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$INSTALL_DIR/.env.example" "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"
    warn "EDIT $ENV_FILE with your API tokens"
fi

# ── symlink CLI ────────────────────────────────
if [[ -d /usr/local/bin ]]; then
    ln -sf "$VENV_DIR/bin/vpsmon-v4" /usr/local/bin/vpsmon-v4 2>/dev/null || true
fi

# ── done ───────────────────────────────────────
step "Installation complete"
echo ""
echo "  ${BOLD}Next steps:${NC}"
echo ""
echo "  1. Edit config:    nano $CONFIG_FILE"
echo "     — set telegram.bot_token_env / chat_ids_env"
echo ""
echo "  2. Enable timers:"
echo "     systemctl --user enable --now vps-monitor-v4-czl.timer"
echo "     systemctl --user enable --now vps-monitor-v4-dujiaojing.timer"
echo ""
echo "  3. Test run:"
echo "     cd $INSTALL_DIR && $VENV_DIR/bin/vpsmon-v4 --source czl"
echo ""
echo "  4. Live: add --send"
echo ""
echo "  ${BOLD}Uninstall:${NC}"
echo "     rm -rf $INSTALL_DIR $HOME/.config/systemd/user/vps-monitor-v4-*"
