# vps-monitor 接入新站 — Onboarding 文档

**最后更新**: 2026-06-20
**目标**: 给你一个新网站 URL,5 分钟内决定放**池 1 / 池 2 / 价格白名单**,下次轮询自动按关键词监控 + 推送到 Telegram。

---

## 1. 项目一句话

**vps-monitor** = czl.net 公开 API 全量拉取 + 池规则过滤 + 关键词匹配 + TG/QQ 推送。
现在 458 个监控 item,156 个真货,2 小时轮询一次。

---

## 2. 关键词库(已硬编码,不要再加)

`/opt/vps-monitor/monitor.py` L1178:

```python
CN_KEYWORDS = ["优化", "CN2", "GIA", "CMI", "9929", "4837", "精品", "三网", "BGP", "回国", "直连", "低延迟"]
```

**触发场景**: 商品 `title` / `location` / `remark` 任一字段**包含**任一关键词 → 标记为"线路:CN2/GIA..."(具体命中哪些会显示)。

**不需要**再加 `CN优选` 这种笼统词 —— **宝贝一等信号,必须显示具体命中**。

---

## 3. 三个判定层(OR 关系)

| 层 | 判定 | 标签 | 说明 |
|---|---|---|---|
| **池 1** | `0.4 ≤ RAM ≤ 2.0GB` 且 `0 < USD/年 ≤ 10` | `池1(廉价)` | 廉价低规格 |
| **池 2** | `1.0 ≤ RAM ≤ 16GB` 且 `10 ≤ USD/年 ≤ 20` | `池2(主力)` | 主力推荐 |
| **价格白名单** | 月付字面 `$1-10` OR 年付 USD 折算 `$1-70` | `线路:{命中关键词}` 或 `价格` | **没 id 白名单**了 |

**判定逻辑**(L1296 附近):
```python
if pool_label or _site_e_price_in_whitelist(item):
    # 进监控
```

> ⚠️ **历史教训(2026-06-20)**: 早期有 210 个 id 白名单,导致 DMIT $59-$239 假货被推送。**已删除**,只留价格白名单。

---

## 4. 新网站接入流程(5 步)

### 步骤 1: 你给我网站 URL

**我需要的**:
- 网站 URL(如 `https://racknerd.com` / `https://bandwagonhost.com`)
- 放哪个池:**池 1 / 池 2 / 不指定(我根据价格自动判定)**
- 是否要"三网优化关键词"过滤:**要 / 不要**(默认要)

### 步骤 2: 我先 curl API 试拉(不改动代码)

```bash
ssh LXC
curl -s "<API_URL>?page=1&pageSize=12" | python3 -m json.tool | head -50
```

**目标**: 看返回 JSON 是不是 czl.net 同款形状(`data: [{id, title, price, ram, ...}]`)。
**99% 情况**: 网站本身就是 czl.net 收录的 → **直接走价格白名单,不用改代码**。
**1% 情况**: 网站是新的,API 形状不一样 → 改 `fetch_site_e` 解析函数。

### 步骤 3: 决定进哪个池(我推荐,你拍板)

**判定方法**:
- 网站套餐 RAM 都在 0.5-2GB + 价格 $5-10/年 → **池 1**
- 网站套餐 RAM 都在 2-8GB + 价格 $15-25/年 → **池 2**
- 都有 → **两个都进**(OR 关系,池 1 套餐也走池 2 判定)

**宝贝说"放池 1" 我就直接调**:
```python
# 例: 网站是 racknerd, 套餐 $9.89/年 1GB → 放池 1
# 改 monitor.py 的池规则 (如果需要):
# 0.4 ≤ RAM ≤ 2.0GB + USD/年 ≤ 10  →  池 1
```

**不一定要改代码**。如果网站套餐自然命中现有池规则 → **0 改动**。

### 步骤 4: 关键词覆盖检查

我看新网站的商品标题,逐个检查 12 个关键词能不能命中。

| 网站 | 关键词覆盖率 | 操作 |
|---|---|---|
| ≥ 50% 商品命中 | 保留 | 0 改动 |
| < 50% | 加词 | 改 `CN_KEYWORDS` |
| 0% | 不监控 | 直接说"该网站不监控" |

### 步骤 5: 真验证 + 推送预览

**绝不靠 grep 看**,真跑一次:

```bash
ssh LXC
cd /opt/vps-monitor
systemctl stop vps-monitor
python3 monitor.py --once --site e
# 看输出: 多少个 item 命中, 多少个有货
systemctl start vps-monitor
```

**如果 0 new 触发**(因为 state.json 已 populate), 我会跑**单次快照推送**给你看长啥样:
```bash
python3 /tmp/snapshot_e_v2.py  # 临时脚本, 推所有 156 真货给你确认
```

---

## 5. 我已经做好的所有配置(不需要再改)

| 项 | 值 | 位置 |
|---|---|---|
| TG BOT TOKEN | `880185...B-oQ` | `/opt/vps-monitor/.env` |
| TG chat_id | `1658239957` | `/opt/vps-monitor/.env` |
| QQ chat_id | `8536501146` | `/opt/vps-monitor/.env` (双通道) |
| 间隔 | `7200s` (2 小时) | `.env` `SITE_E_POLL_INTERVAL` |
| 推送分段 | 每 12 个一段,带 [X/Y] 标 | `notify_site_e_*` 函数 |
| 状态行 | `📊 状态: ✅有货 / ❌没货` | `_site_e_format_item` L1390 |
| 备份策略 | 每次改动前 `.bak.YYYYMMDD_HHMMSS` | `/opt/vps-monitor/*.bak.*` |
| 货币 | 2026 汇率 `1 USD = 6.8 CNY` | `fx = {"$": 1, "€": 1.08, "¥": 0.147}` |

---

## 6. 你给我网站 URL 后我做的事(checklist)

- [ ] SSH 登 LXC
- [ ] curl API 试拉,看 JSON 形状
- [ ] 抽样 5-10 个商品,看池规则自然命中
- [ ] 抽样 5-10 个商品,看 12 关键词覆盖率
- [ ] **真验证**:`python3 monitor.py --once --site e`
- [ ] **真推送**:`snapshot_e_v2.py` 推 1-2 段给你看长啥样
- [ ] **备份**: 改动前 `cp monitor.py monitor.py.bak.YYYYMMDD_HHMMSS`
- [ ] **重启 service**: `systemctl restart vps-monitor`
- [ ] **汇报**: 几个监控 / 几个真货 / 推送长啥样

---

## 7. 常见 Q&A

### Q: 网站不在 czl.net 收录怎么办?
A: 改 `fetch_site_e` 函数的 API URL + 解析逻辑。**这是 1% 情况**,需要约 30-60 分钟。

### Q: 商品价格是 € 欧元怎么办?
A: 已处理,`fx["€"] = 1.08`,折算 USD。

### Q: 商品价格是 ¥ 人民币,但月付 ¥50/月能进吗?
A: **不能**。月付判定**字面值 1-10**,¥50 → val=50,1≤50≤10 → False。**不折算 USD**。这是你的明确要求,2026-06-20 立。

### Q: 商品是年付 ¥480/年(约 $70)能进吗?
A: **能**。年付走 USD 折算,¥480 × 0.147 ≈ $70.6,1≤70.6≤70 → True(临界)。

### Q: 推送长啥样?
A: 你已经见过。形如:
```
🔔 #vps-monitor #补货 (3 个)
• CloudCone KVM 1GB
  🏷️ CloudCone · 池1(廉价)
  💵 $5.99/月 (年付 $71.88)
  🔧 1C/1GB/20GB SSD/1TB
  📍 Los Angeles, US
  🛣️ BGP · 直连
  📊 状态: ✅ 有货
  🛍️ 直达
```

### Q: 关键词没命中但价格命中,标签显示什么?
A: `价格`(没有具体关键词)。

### Q: 不想要"价格"这个笼统词怎么办?
A: 改 `_site_e_format_item` 的 fallback,改成 `线路:未标明` 或类似。我可以随时改。

---

## 8. 关键代码位置(我改的时候找这些)

| 函数 | 行号(2026-06-20) | 作用 |
|---|---|---|
| `SITE_E_API_URL` | L1137 | czl.net API URL(默认就是它) |
| `_parse_ram_gb_e` | L1141 | "1GB" → 1.0 |
| `_parse_usd_year_e` | L1154 | "$5.99/月" → 71.88 (USD/年) |
| `CN_KEYWORDS` | L1178 | **12 个关键词** |
| `_site_e_get_keywords` | L1183 | 提取 item 命中关键词 |
| `_site_e_price_in_whitelist` | L1192 | 价格白名单判定 |
| `_site_e_pool_match` | L1212 | 池规则判定 |
| `_site_e_is_vps` | L1228 | 排除 DEDI |
| `fetch_site_e` | L1237 | 8 worker 并发拉 + retry |
| `compare_site_e` | L1320 | 新/补/降 三事件检测 |
| `_site_e_format_item` | L1366 | **推送格式** |
| `notify_site_e_new` | L1397 | 🆕 新套餐推送(分段) |
| `notify_site_e_restock` | L1424 | 🔔 补货推送(分段) |
| `notify_site_e_price_drops` | L1450 | 💰 降价推送(分段) |
| `monitor_site_e` | L1476 | 主循环调用 |

---

## 9. 你只需要说的(下次我直接干)

> "宝贝,这个网站 `https://xxx.com`,放**池 1/池 2/自动**,要/不要三网关键词过滤。"

我就会:
1. curl 试拉
2. 判定池归属
3. 检查关键词
4. 真验证 + 推一段给你看
5. 重启 service
6. 汇报

**不需要**再问 API 形状、要不要 id 白名单、价格区间、推送格式 —— 全部硬编码默认了。

---

## 10. 风险/已知 trade-off

| 项 | 状态 | 备注 |
|---|---|---|
| 池 1+2 OR 关系 | ✅ 正常 | 商品可同时打 2 个标签(但只会显示先匹配的) |
| 月付不折算 USD | ⚠️ 已知 | ¥50/月 不进,2026-06-20 你定的 |
| 关键词覆盖率 | ⚠️ 已知 | 没命中的标"价格" |
| czl.net API 限速 | ✅ 解决 | 8 worker + retry, ~5s 拉完全量 |
| 重复推送 | ✅ 解决 | NOTIFY_ONLY_CHANGES=true, 只推变化 |
| 改前备份 | ✅ 铁律 | 34 个 .bak 全保留 |

---

**收口**: 宝贝,下次你只发我网站 URL + 池 1/池 2/自动 + 要/不要关键词,**5 步我全干完**。

最后更新: 2026-06-20 06:33 (项目第 13 次迭代收官)
