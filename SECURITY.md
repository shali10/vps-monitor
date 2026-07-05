# Security Policy

## 支持版本

| 版本 | 状态 |
|---|---|
| v4.x | 支持安全修复 |
| v3.x 及更早 | 不再维护 |

## 报告安全问题

如果你发现 token 泄露、未授权推送、敏感日志、命令注入或其他安全问题，请通过 GitHub Security Advisory 或私下渠道报告，不要先发公开 Issue。

报告时请包含：

| 信息 | 说明 |
|---|---|
| 影响版本 | 例如 `v4.2.0` |
| 复现步骤 | 尽量给最小复现配置，移除真实 token |
| 影响范围 | 是否会泄露 Telegram token、商家 token、chat id、库存状态库 |
| 建议修复 | 如果已有思路可以一起提供 |

## 敏感信息边界

| 类型 | 项目约定 |
|---|---|
| Telegram token | 只放 `.env`，不提交 |
| 商家 token | 通过环境变量读取 |
| SQLite state | 不提交 |
| 生产配置 | 不提交 `config.json` / `config.production.json` |
| 日志 | 不提交 |

## 本地自查

```bash
make check
git status --short
git ls-files | grep -E '(^|/)(\.env|config\.json|.*\.sqlite3|.*\.log)$' && exit 1 || true
```
