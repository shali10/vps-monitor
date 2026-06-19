# 安装详解

## 系统要求

- Linux(任意 systemd 发行版:Debian / Ubuntu / CentOS / Arch)
- Python 3.9+
- 1 个 Telegram bot(token + chat_id)
- 可选:对应商家的 Bearer token / 公开 API URL

## 一键安装(推荐)

```bash
git clone https://github.com/<your-user>/vps-monitor.git
cd vps-monitor
sudo bash scripts/install.sh
```

脚本流程:
1. 检测 `python3` + `requests`,缺则 `pip3 install requests`(root 权限)
2. `install -m 755 vpsmonctl /usr/local/bin/`(让全局可调)
3. `cp -r ./* /opt/vps-monitor/`(部署主程序)
4. `cp .env.example .env && chmod 600 .env`(建空配置)
5. **暂停让你 `vim .env` 填真实 token**(不自动填,避免误填)
6. `cp vps-monitor.service /etc/systemd/system/`
7. `systemctl daemon-reload && systemctl enable --now vps-monitor`
8. `sleep 3 && vpsmonctl status` + `vpsmonctl check` 验证

## 手动安装

```bash
sudo mkdir -p /opt/vps-monitor
sudo cp -r ./* /opt/vps-monitor/
cd /opt/vps-monitor
pip3 install -r requirements.txt
sudo cp .env.example .env
sudo chmod 600 .env
sudo $EDITOR .env   # 填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / SITE_X_TOKEN

sudo cp vps-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vps-monitor

# 验证
vpsmonctl status
vpsmonctl check
```

## 升级

```bash
cd /opt/vps-monitor
sudo systemctl stop vps-monitor
sudo cp /opt/vps-monitor/monitor.py /opt/vps-monitor/monitor.py.bak.upgrade
sudo cp <new-repo>/monitor.py /opt/vps-monitor/
sudo systemctl start vps-monitor
sleep 3
vpsmonctl status   # 确认 active
```

**风险**:`monitor.py` 大改时可能改 schema,`state.json` 老格式不兼容。详见 `docs/PITFALLS.md` Pitfall 16(整合独立 cron 实战)。

## 卸载

```bash
sudo systemctl stop vps-monitor
sudo systemctl disable vps-monitor
sudo rm /etc/systemd/system/vps-monitor.service
sudo systemctl daemon-reload
sudo rm -rf /opt/vps-monitor/
sudo rm /usr/local/bin/vpsmonctl
```

`.env` / `state.json` / `monitor.log` 都在 `/opt/vps-monitor/` 下,删目录即清。

## 多台机器部署

如果想监控多个 Telegram bot / 多组 chat_id,直接部署到多台机器,各自独立 `state.json` 即可。
**注意**:`state.json` 是 baseline,如果两台同时跑同一个站点的轮询,会冲突(都尝试推"新到货")。一个站只在一台机器跑。

## Docker 化(未实现,欢迎 PR)

目前没有 Dockerfile,因为:
- systemd 是设计核心(进程守护 + journalctl)
- .env 走 EnvironmentFile 而不是 docker secrets
- 部署目标都是裸 LXC / VPS,不需要容器隔离

如果想要 docker 化,可以参考:
- 用 `docker-compose.yml` + `restart: always` 替代 systemd
- `.env` 走 env_file 而不是 EnvironmentFile
- 容器内 `tail -f /dev/null` 保活,然后用外部脚本拉日志
