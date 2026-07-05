# 常见坑

这些坑来自生产部署和公开化整理过程。

## oneshot service 不是常驻进程

| 现象 | 正确判断 |
|---|---|
| `systemctl status xxx.service` 显示 `inactive (dead)` | 正常，oneshot 跑完就退出 |
| 想看是否成功 | 看 `Result=success` 和 `ExecMainStatus=0` |
| 想看下一次运行 | 看对应 `.timer` |

```bash
systemctl show vps-monitor-v4-czl.service -p Result -p ExecMainStatus -p ActiveEnterTimestamp
systemctl list-timers 'vps-monitor-v4-*'
```

## 不要提交真实配置

| 不该提交 | 原因 |
|---|---|
| `.env` | 有 Telegram bot token 和商家 token |
| `config.json` | 通常是生产配置，容易含真实路径/策略 |
| `state/*.sqlite3` | 运行状态，不属于源码 |
| `*.log` | 日志可能包含接口响应和请求信息 |

公开仓库只保留 `config.example.json`。

## 首轮推送要谨慎

第一次运行没有历史状态。如果带 `--notify-first-run --send`，可能把当前所有有货套餐都推一遍。

| 目标 | 推荐命令 |
|---|---|
| 只看输出 | `--notify-first-run --dry-run` |
| 建立状态但不推送 | 不带 `--notify-first-run`，也不带 `--send` |
| 少量测试推送 | `--notify-first-run --summary --send` |

## Telegram 消息太多

默认有 `--max-send-messages` 保护，超过会拒绝发送。

| 处理方式 | 命令 |
|---|---|
| 限制数量 | `--limit-events 10` |
| 改排序 | `--sort-events pool_price` |
| 发摘要 | `--summary` |
| 提高上限 | `--max-send-messages 50` |

## token 环境变量没加载

systemd 下要确认 unit 使用了 `EnvironmentFile=/opt/vps-monitor/.env`。手动运行时要先加载：

```bash
set -a
. /opt/vps-monitor/.env
set +a
```

## 来源接口字段会变

商家接口不是稳定公共 API，字段变动时通常会表现为 normalize 结果为空或测试失败。修复顺序：

| 步骤 | 动作 |
|---|---|
| 1 | 保存一份脱敏原始响应 |
| 2 | 修 `vpsmon/sources/<source>.py` normalize |
| 3 | 补一条回归测试 |
| 4 | dry-run 看消息格式 |

## README 不是生产 SOP

公开 README 面向陌生使用者。真实服务器路径、chat id、token、内部回滚包不要写进去。生产细节可以写成可替换示例。
