# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 3.0.x   | ✅ Active          |
| < 3.0   | ❌ Internal only   |

## Reporting a Vulnerability

**Please DO NOT file public issues for security vulnerabilities.**

报告方式(按优先级):
1. **GitHub Security Advisories**(推荐):https://github.com/shali10/vps-monitor/security/advisories/new
2. **Email**:见 repo 主页的 `security` 联系方式
3. **Encrypted**:`pgp` key 即将提供

我们承诺:
- 24 小时内回复确认
- 7 天内评估严重程度
- 30 天内出修复或 workaround(按 CVSS 严重度)

## Security Best Practices for Users

部署时务必:
1. ✅ `.env` 权限 `chmod 600`(install.sh 自动)
2. ✅ 不要把 `.env` / `state.json` / `*.bak` commit 进 git(`.gitignore` 已排除)
3. ✅ Telegram bot token 只用于指定 chat_id,别公开发
4. ✅ systemd `Restart=always` 让 service 异常自动拉起
5. ✅ 定期 `vpsmonctl status` 检查 active + journalctl 看日志

## Token Lifecycle

- **Bearer Token**(SITE_A/C):商家发的,商家可主动撤销。Pitfall 14 实战经验。
- **Telegram Bot Token**:`@BotFather` 创建,owner 可随时 revoke
- **PAT**(个人):仅用于 GitHub push,事后立即删除

## Known Security Considerations

- 监控脚本读 `.env` → 加 chmod 600
- systemd 进程常驻 → 加 `User=` 非 root(如适用)
- 日志可能含商家域名 / plan id → 默认本地,无外发

## Vulnerability Disclosure Timeline(模板)

```
[Day 0] 报告收到 → 确认 + 分级 CVSS
[Day 1-3] 影响评估 + 临时 workaround
[Day 7] 修复 commit + 测试
[Day 14] 发布 patch 版本 + CVE(若需)
[Day 30] 公开 advisory(给上游 90 天窗口)
```
