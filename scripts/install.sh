#!/usr/bin/env bash
# vps-monitor 一键装机脚本
# 流程: 检查依赖 → 装 vpsmonctl → 部署 → 配 .env → systemd → 验证

set -euo pipefail

RED="\033[0;31m"; GRN="\033[0;32m"; YLW="\033[0;33m"; NC="\033[0m"
log_info() { echo -e "${GRN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YLW}[WARN]${NC} $*"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="/opt/vps-monitor"

[[ $EUID -eq 0 ]] || { log_err "请用 root 跑: sudo bash install.sh"; exit 1; }

# 1. 检查 python3
log_info "检查 python3 ..."
command -v python3 >/dev/null || { log_err "python3 未装,Ubuntu/Debian: apt install python3"; exit 1; }
PY_VER=$(python3 -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")")
log_info "  python3 $PY_VER"

# 2. 检查 / 装 requests
log_info "检查 requests ..."
if ! python3 -c "import requests" 2>/dev/null; then
    log_warn "  requests 未装,正在 pip3 install ..."
    pip3 install --quiet requests || { log_err "pip install 失败"; exit 1; }
fi
log_info "  requests OK"

# 3. 装 vpsmonctl 到 /usr/local/bin
log_info "装 vpsmonctl 到 /usr/local/bin ..."
install -m 755 "$REPO_DIR/vpsmonctl" /usr/local/bin/vpsmonctl

# 4. 部署到 /opt/vps-monitor
log_info "部署到 $DEPLOY_DIR ..."
mkdir -p "$DEPLOY_DIR"
cp -r "$REPO_DIR"/* "$DEPLOY_DIR"/
# 注: cp 会保留文件所有权,如果已有 .env 会覆盖,先备份
if [[ -f "$DEPLOY_DIR/.env" && ! -f "$DEPLOY_DIR/.env.bak.install_$(date +%Y%m%d_%H%M%S)" ]]; then
    cp "$DEPLOY_DIR/.env" "$DEPLOY_DIR/.env.bak.install_$(date +%Y%m%d_%H%M%S)"
    log_warn "  已有 .env,已备份为 .env.bak.install_*"
fi

# 5. 配 .env(如果还没)
if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
    log_info "建空 .env(请手动填值)..."
    cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
    chmod 600 "$DEPLOY_DIR/.env"
    log_warn "  请编辑: sudo vim $DEPLOY_DIR/.env"
    log_warn "  填入 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS / SITE_X_TOKEN"
    log_warn "  填完按任意键继续..."
    read -r _
fi

# 6. 装 systemd
log_info "装 systemd unit ..."
cp "$REPO_DIR/vps-monitor.service" /etc/systemd/system/vps-monitor.service
systemctl daemon-reload
systemctl enable --now vps-monitor

# 7. 验证
log_info "等 3 秒让 service 启动 ..."
sleep 3

if systemctl is-active --quiet vps-monitor; then
    log_info "✅ service active"
else
    log_err "❌ service 未 active,查看 journal:"
    journalctl -u vps-monitor -n 30 --no-pager
    exit 1
fi

log_info ""
log_info "🎉 装机完成!"
log_info ""
log_info "下一步:"
log_info "  vpsmonctl status   # 看监控状态"
log_info "  vpsmonctl check    # 看当前命中数量"
log_info "  vpsmonctl logs 50  # 看最近 50 行日志"
log_info "  vpsmonctl --help   # 看所有命令"
