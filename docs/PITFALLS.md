# PITFALLS — 实战踩坑全记录

26 个 pitfall,从 2026-06 起的实战踩坑沉淀。**每个坑都是 0.5-2 小时换来的**,请仔细看!

---

## Pitfall 1:systemd EnvironmentFile 空值行会注入空字符串

**症状**:`.env` 里写 `SITE_X_POLL_INTERVAL=`(空值行)→ `int("")` ValueError → service 启动失败(fail-restart 循环)。

**根因**:systemd 读 `EnvironmentFile=` 时会注入空值变量到 `os.environ`,`os.environ.get("KEY", "60")` 返回 `""` 而不是默认值 `60`。

**修复**:
```bash
# ❌ 错:留空值行
echo "SITE_X_API_URL=" >> .env

# ✅ 对:删整行(让 systemd 不注入 KEY,monitor.py 走默认值)
sed -i "/^SITE_X_/d" /opt/vps-monitor/.env
```

---

## Pitfall 2:改完 monitor.py / .env 必须 restart service

**症状**:改完文件,monitor.log 还是旧内容。

**根因**:`Type=simple` 进程在内存里跑旧代码 + 读旧 env,不重启永远不生效。

**修复**(必跑):
```bash
systemctl restart vps-monitor.service
sleep 3
systemctl is-active vps-monitor.service   # 必须 active
journalctl -u vps-monitor -n 30 --no-pager  # 必须无 ValueError
```

---

## Pitfall 3:truthy 默认值让 guard 失效

**症状**:`monitor.py` 加 `if not SITE_X_API_URL: return []` guard,但还是拉到数据。

**根因**:用 `"DISABLED"` 当默认值,`if not "DISABLED"` → 字符串 truthy → guard 失败。

**修复**:
```python
SITE_A_API_URL = _env_str("SITE_A_API_URL", "")  # falsy 默认值
```

---

## Pitfall 4:`fetch_site_X` guard 必须放在 `requests.get` 之前

**症状**:加了 `if not URL: return []` guard,日志还是显示"site-a polled N plans"。

**根因**:guard 写在函数末尾,`requests.get` 已经在 guard 之前跑过。

**修复**:guard 写在函数最开头。

---

## Pitfall 5:改 .env / monitor.py 别只看 grep 输出就当成功

**症状**:`grep SITE_C_TOKEN .env` 显示有,但 service 还是"site-c skipped"。

**根因**:systemd 注入的 env 跟 grep 看到的文件内容可能不一致。

**修复**:用 `xxd` 看真实字节:
```bash
grep "^SITE_C_TOKEN" /opt/vps-monitor/.env | xxd | head -3
```

---

## Pitfall 6:incudal 类"资源模板"商家跟 JSON 数据模型不兼容

**症状**:配好 token + URL,`state_c.items=0` + "site-c polled 0 packages"。

**根因**:incudal API 返回的 package 无 `plans` 子数组、无 `price` 字段,只有 `cpu_max` / `memory_max` / `disk_max`。

**修复**:改 `_site_c_plan_list` 加 fallback 把 package 自身当 1 个伪 plan(用 `# 注释` 而非 docstring 避免字符串嵌套):
```python
def _site_c_plan_list(pkg):
    # incudal package 自身就是 1 个资源模板(无 plans 子数组)
    for key in ("plans", "packagePlans", "package_plans", "items", "variants"):
        value = pkg.get(key)
        if isinstance(value, list):
            return value
    if isinstance(pkg, dict) and (pkg.get("id") is not None or pkg.get("name")):
        return [pkg]
    return []
```

---

## Pitfall 7:哨兵标签 hardcode 在 `health_bot.py`,不是从 state.json 推断

**症状**:state.json 显示商家已 active,但哨兵推送还显示"独角鲸(筹备中)"。

**根因**:`health_bot.py` 的 `MONITORED_SHOPS` 列表是手写的 status 标签。

**修复**:改 `health_bot.py` 同步状态。

---

## Pitfall 8:LLM 渲染吃敏感字符串

**症状**:execute_code 里写 `SITE_C_TOKEN=xxx` → 远端 bash 收到空字符串。

**根因**:LLM 渲染时主动给"看起来像 secret"的字符串加占位。

**修复**:所有敏感字符串 + 路径 base64 编码,整段 bash 也 base64 后跑。

---

## Pitfall 9:手动 hack state.json 测试推送 — 4 大坑

**坑 A**:state.json 有 2 层 soldOut 字段,只改顶层无效。  
**坑 B**:service "first run" 会从 API 重新加载,覆盖手动编辑。  
**坑 C**:改完 state.json 立即看 monitor.log 看不到推送(60s 轮询间隔)。  
**坑 D**:跑完记得恢复 state.json。

---

## Pitfall 10:TG bot 身份 — Hermes ≠ monitor.py

**症状**:用 `hermes send_message` 推 home,user 看不到。

**根因**:`monitor.py` 用独立 bot(`myjiankongshibot`),token 在 `/opt/vps-monitor/.env`。

**修复**:推送测试必须用 monitor.py 的 bot token + 同样 chat_id。

---

## Pitfall 11:`独角鲸 ≠ dartnode` —— monitor.py 注释是误标

**症状**:monitor.py 注释写 `# 独角鲸云 (site_a)`,但 `.env` 里是 `SITE_A_API_URL=https://api.fuckip.me/api/v1/plans` → 实际 site_a 是 dartnode。

**根因**:注释作者把 site_a 标错了。

**修复**:**不要相信 monitor.py 注释里的商家名** —— 看 `.env` 实际值。

---

## Pitfall 12:删监控商家 = 全栈 5-7 件套

不是一行命令。完整清单:
1. `/opt/<vendor>-monitor/` 目录
2. `state.json` `site_X` 字段
3. `monitor.py` default state `"site_X": {...}` 行
4. `monitor.py` main loop `# Site X` 整段
5. `monitor.py` 6 个 `def site_X_*` 函数
6. crontab 里相关行
7. `health_bot.py` 哨兵标签
8. `args.once` CLI 块

**反模式**:每次 user 提醒删一次(浪费 5+ 轮对话)。

---

## Pitfall 13:Python `logging.FileHandler` 不 flush

**症状**:`state.json` 更新 + service active,但 `monitor.log` mtime 卡 30+ 分钟不更新。

**根因**:`FileHandler` 默认 buffer,只写 stdout/stderr 不写 file 直到 service 死。

**修复**:用自定义 `_FlushFileHandler` 每条 log 后立即 flush。

---

## Pitfall 14:Token 失效是"刚才还能监控怎么就失效了"的真因

**症状**:service 跑、state.json 更新、log 写,但没新数据。

**根因**:**不是代码问题** — 服务端主动撤销了 Bearer token。`fetch_site_X` try/except 吃 403 → return [] → 静默 fail。

**诊断**:
```bash
cd /opt/vps-monitor
bash -c "source .env && curl -s -w "HTTP: %{http_code}\n" -H "Authorization: Bearer YOUR_TOKEN" $SITE_C_API_URL"
```

**修复**:重拿 token + 写 .env + restart + 立即看 main loop log。

---

## Pitfall 15:"删干净"必须全栈一次清

任何"删 X"需求 → 第一轮就**列全栈清单** + 一次性全删 + 一次性验证。

---

## Pitfall 16:整合独立 cron 脚本进 daemon 框架 (5 步 recipe)

从独立 cron 整合进 site_d 框架:
1. **备份双份**(必须,数据零丢失铁律)
2. **停源 cron FIRST**(关键 race condition 防护)
3. 写新 monitor.py + 改 .env(**Python 精确字符串匹配 + 5 行 anchor + py_compile 验证**)
4. state 迁移(**原子写 + first_run=False 避免误推**)
5. restart daemon + 验证 + 清理(**7 天保留窗口**)

**6 大坑**:不停 cron race / json.dumps 双转义 / 单行 anchor 撞 duplicate / first_run=True 误推 / 不停 daemon 直接 scp / 不改 health_bot 引用老路径。

---

## Pitfall 17:多 site 主循环共享 try/except — 一个 site 抛异常阻塞所有

**症状**:site_a 偶发 ReadTimeout → main loop try/except 捕获 → site_d/site_c 永远到不了。

**根因**:整个 main loop 一个 try 包所有 site。

**修复**:每个 site 独立 try/except(`try: monitor_site_X() except: log.exception(...)`)。

---

## Pitfall 18:"0 变化不 log" = 难真验证

**症状**:site_d 集成后 `--once --site=d` 跑通,daemon restart,monitor.log 0 行 site-d log(因为 0 变化不 log)。

**修复**:每个 site 末尾**总是 log**(即便 0 变化也打一行),便于实时看到"site 在主循环跑没跑"。

---

## Pitfall 19:"测试推送" vps-monitor 不自带 — 写 ad-hoc snapshot 脚本

**症状**:user 说"推送一下当前 3 家库存" → 以为能跑 `--once` → 实际 `--once` 不主动 dump。

**修复**:用 `scripts/inventory_snapshot.py`(已包含),独立 fetch + 推 TG。

---

## Pitfall 20:临时改 INTERVAL 加速验证 — "加总是 log" + "改 INTERVAL=30 临时" 双保险

加速验证步骤:
1. 备份 .env
2. `echo "SITE_D_POLL_INTERVAL=30" >> .env`
3. restart service
4. sleep 35 + grep log
5. `sed -i "/^SITE_D_POLL_INTERVAL=30$/d" .env` 改回
6. restart 再验证

---

## Pitfall 21:Incudal `?source=official` 只看 1 个 package — 漏 2 个真商品

**症状**:`inventory_snapshot.py` 看到 1 packages → 误以为 Incudal 只卖 1 个。

**根因**:`?source=official` 只返回 1 个(探針機),还有 community / shared 模式共享 2 个真商品。

**修复**:`SITE_C_API_URL` 去掉 `?source=official`(默认全 3 个)或用 `?source=community`。

---

## Pitfall 22:fuckip.me 字段名不是 `available` — 用 `remaining`

**症状**:拉 709 plans 但 `available=0` → 误以为"全没货"。

**根因**:fuckip.me 用 `remaining` 字段,不是 `available` / `stock` / `qty`。

**修复**:多查 `remaining` / `available` / `stock` / `qty` 多个字段名,任一 > 0 算 in_stock。

---

## Pitfall 23:Cron 报告"真伪验证" 4 步 recipe

user 问"看看是不是真的":
1. 找报告生成器脚本
2. 跑 `--json` 看真实返回
3. 独立查 raw data source 复现
4. 时间窗口 + 字段名 + 误报三重检查

---

## Pitfall 24:两个独立评分系统别搞混 — foreman 95 ≠ USER.md 99

`foreman_report.py` 算系统健康(0-100),`USER.md` 算文档质量(A+ 档)。**两码事,不冲突**。

---

## Pitfall 25:凭据丢失先 check access 再 ssh

3 步 ssh 前 check:
1. `ls ~/.hermes/secrets/<server>_*`
2. `nc -zv <host> 22`
3. `ssh -i ~/.ssh/id_ed25519 -o ConnectTimeout=5 ...`

凭据丢失 → 老实说"无法访问" + 让 user 重新提供。

---

## Pitfall 26:LXC vs DediRock 路径混淆

跨主机操作前 `hostname` + `pwd` 确认在哪台。state.db 等数据文件在哪台,就在哪台操作(或 ssh 进那台)。

---

## 持续更新

新坑继续加到这个文档。提交 PR 时:
- 标题:Pitfall N:一句话症状
- 内容:症状 → 根因 → 修复 + 代码示例
- 实战日期 + 来源(自己踩 / 别人报)
