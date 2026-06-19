---
name: Bug Report
about: 报告 bug 帮助我们改进
title: "[Bug] "
labels: ["bug", "needs-triage"]
assignees: []
---

## Bug 描述
简洁清楚的 bug 描述。

## 复现步骤
1. 跑了 ...
2. 看到 ...
3. 期望 ...
4. 实际 ...

## 期望行为
应该怎样。

## 实际行为
实际怎样。

## 环境
- OS: (e.g. Ubuntu 22.04 / Debian 12 / Arch)
- Python 版本: `python3 --version`
- vps-monitor 版本: `git describe --tags` 或 commit SHA
- 部署方式: systemd / Docker / manual

## 日志 / 截图
```bash
# 跑这些收集信息(脱敏后贴)
vpsmonctl status
vpsmonctl check
journalctl -u vps-monitor -n 50 --no-pager
tail -50 /opt/vps-monitor/monitor.log
```

## .env (脱敏!)
```
SITE_A_NAME=...
SITE_A_API_URL=https://...
SITE_A_TOKEN=ghp_xxxxx... (脱敏)
```

## Checklist
- [ ] 看过 [PITFALLS.md](https://github.com/shali10/vps-monitor/blob/main/docs/PITFALLS.md)
- [ ] 跑过 `vpsmonctl status` 看到 active
- [ ] 跑过 `vpsmonctl check` 看到合理数字
- [ ] 搜过 [已有 issues](https://github.com/shali10/vps-monitor/issues) 没重复
