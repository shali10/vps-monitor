# 新增来源指南

这份文档整理自 v3 单体脚本里的接入经验，并按 v4 的 package 架构重写。目标是：拿到一个新商家 URL 后，先判断它属于哪种来源模式，再最小改动接入 `vpsmon/sources/`。

## 先判定来源类型

| 类型 | 典型形态 | 是否推荐 | 适配方式 |
|---|---|---|---|
| 公开 JSON API | 不需要 token，返回套餐列表 | 推荐 | 参考 `czl` |
| Bearer API | `Authorization: Bearer <token>`，分页返回套餐 | 推荐 | 参考 `dujiaojing` |
| 资源模板 API | 返回 package/template，不一定有 price | 可接 | normalize 时补齐缺失字段 |
| HTML 商品页 | 无 API，只能抓页面 | 谨慎 | 优先找内嵌 JSON，最后再正则/BeautifulSoup |
| JS/CF 强反爬页面 | requests 拿不到真实商品 | 不优先 | 先找 API，必要时再考虑浏览器方案 |

## 接入前检查

| 检查 | 命令/动作 | 通过标准 |
|---|---|---|
| 能否直接拉取 | `curl -s '<url>' | head` | 返回 JSON 或稳定 HTML |
| 是否需要 token | 看 401/403 和文档 | token 通过环境变量读取 |
| 分页方式 | 试 `page=1` / `limit=200` / `pageSize=12` | 能稳定取全量 |
| 商品 ID | 找 `id` / `uuid` / `slug` | 每轮稳定，不随价格变 |
| 库存字段 | 找 `remaining` / `stock` / `available` / `sold_out` | 能判断有货/无货 |
| 价格字段 | 找 `price` / `price_monthly` / `price_cents` | 能转为年付美元口径 |
| 购买链接 | 找商品页或 deploy URL 模板 | 能生成直达链接 |

## v4 接入步骤

| 步骤 | 文件 | 要做什么 |
|---|---|---|
| 1 | `vpsmon/sources/<name>.py` | 实现 `normalize(raw, deploy_url)` 和 `Source.fetch()` |
| 2 | `vpsmon/cli.py` | 在 `_build_source()` 注册来源名 |
| 3 | `config.example.json` | 添加 `sources.<name>`、`rules.<name>`、`notify_policy.<name>` |
| 4 | `tests/fixtures/` | 放脱敏后的 API 响应样例 |
| 5 | `tests/test_core.py` 或独立测试文件 | 覆盖分页、鉴权 header、normalize、库存、URL |
| 6 | `docs/sites/<name>.md` | 写来源说明、字段映射、限制和排错 |
| 7 | `README.md` | 在内置来源表里加入新来源 |

## normalize 输出要求

所有来源最终都要输出 `VpsOffer`，不要绕过模型直接发 Telegram。

| 字段 | 要求 |
|---|---|
| `source` | 固定来源名，例如 `czl` |
| `offer_id` | 稳定字符串 ID |
| `title` | 用户能看懂的套餐名 |
| `provider` | 商家或机房名，可为空但不建议 |
| `location` | 地区或机房位置 |
| `cpu_cores` | 数字，未知用 `None` |
| `ram_gb` | GB 数字，未知用 `None` |
| `disk` | 原样字符串，例如 `20GB SSD` |
| `bandwidth` / `traffic` | 带单位字符串 |
| `route` | 线路摘要，例如 `CN2 / CMI / 4837` |
| `price` | `Money(raw=原始价格, usd_year=年付美元)`，未知用 `None` |
| `available` | 有货布尔值 |
| `stock` | 库存数字，未知用 `None` |
| `url` | 直达购买或商品链接 |
| `raw` | 原始 dict，方便事件落库和后续排错 |

## 常见字段映射

| 语义 | 常见字段 | 处理建议 |
|---|---|---|
| 库存数 | `remaining` / `stock` / `qty` / `quantity` | `> 0` 视为有货 |
| 售罄状态 | `sold_out` / `soldOut` / `out_of_stock` | 取反得到 `available` |
| 月付价格 | `price_monthly` | `usd_year = price_monthly * 12` |
| 分价格式 | `price_cents` | `price_monthly = price_cents / 100` |
| 内存 MB | `ram_mb` / `memory_mb` | `/ 1024` 转 GB |
| 内存字符串 | `1GB RAM` / `2048MB` | 用 `parse_ram_gb()` |
| CPU 字符串 | `1 Core` / `2vCore` | 用 `parse_cpu_cores()` |
| 年付价格字符串 | `$10/年` / `38元/年` | 用 `parse_usd_year()` |

## 公开 JSON API 模式

适合不需要认证、可以分页取套餐的来源。`czl` 就是这个模式。

| 项 | 建议 |
|---|---|
| 超时 | `timeout=15` |
| 分页 | `page` + `pageSize` 或 API 文档指定参数 |
| 并发 | 只有页数很多时才并发；先从串行开始 |
| 失败策略 | 单页失败可以跳过或重试，但要有测试覆盖 |
| 配置 | `api_url`、`page_size`、`max_pages`、`deploy_url` |

## Bearer API 模式

适合 WHMCS 或自建面板 API。`dujiaojing` 就是这个模式。

| 项 | 建议 |
|---|---|
| token | 只从环境变量读取，不写进 config |
| header | `Authorization: Bearer <token>` |
| 缺 token | 明确抛错，不静默返回空 |
| 分页 | 优先读 `total`，没有 total 时用空页停止 |
| 测试 | fixture 里不要放真实 token，断言 header 使用 `fixture-token` |

## 资源模板 API 模式

有些 API 返回的是 package/template，不一定有 plan 子数组或价格字段。

| 情况 | 处理 |
|---|---|
| 顶层是 `packages` | 直接遍历 package |
| 没有 `plans` 子数组 | 把 package 自身当一个 offer |
| 没有 price | `price=None`，并在规则里避免强依赖价格 |
| 只有资源上限 | 映射到 CPU/RAM/Disk，标题里保留模板名 |
| source 参数会过滤结果 | 文档里写清楚默认用哪个参数 |

这类来源不要为了通过筛选伪造价格。价格未知就保持未知，规则层单独处理。

## HTML 商品页模式

HTML 来源维护成本更高，只在没有 API 时使用。

| 优先级 | 方法 | 说明 |
|---|---|---|
| 1 | 找内嵌 JSON | `__NEXT_DATA__`、`window.__INITIAL_STATE__` 等 |
| 2 | 用 BeautifulSoup | 适合稳定 class 或 data 属性 |
| 3 | 正则提取 | 只适合非常稳定的短 HTML |
| 4 | 浏览器渲染 | 成本高，作为最后选择 |

HTML 站必须加 fixture。保存脱敏 HTML 片段，测试 parser 输出 `VpsOffer`，不要让 CI 访问真实站点。

## 筛选规则

规则尽量放在 `config.example.json`，不要硬编码在 source adapter 里。

| 规则 | 说明 |
|---|---|
| `rules.global.exclude_keywords` | 全局排除独服、dedi 等关键词 |
| `rules.<source>.pools` | 按 CPU/RAM/价格划分池 |
| `price_max_usd_month` | 月付上限 |
| `price_min_usd_year` / `price_max_usd_year` | 年付范围 |
| `notify_policy.<source>.limit_events` | 限制每轮渲染事件数 |
| `notify_policy.<source>.sort_events` | 推荐 `pool_price` 或 `price` |

如果一个规则只对单个商家成立，放在 `rules.<source>`；如果所有来源都应该排除，才放 `global`。

## 测试要求

新增来源至少补这些测试。

| 测试 | 覆盖内容 |
|---|---|
| fixture fetch | 分页、请求参数、鉴权 header、停止条件 |
| normalize | 价格、CPU、内存、库存、URL、线路 |
| rules | 命中池、超价拒绝、缺字段拒绝 |
| formatter | 推送里有标题、配置、价格、直链 |
| diff | 首轮静默、补货、降价或新增事件 |

fixture 规则：

| 规则 | 原因 |
|---|---|
| 不放真实 token/chat id | 防止泄露 |
| 不放私有购买链接 | 防止把生产信息带进仓库 |
| 保留真实字段名 | 测试字段契约 |
| 保留边界样例 | 覆盖售罄、无价格、字符串数字、分页结束 |

## 验证流程

```bash
python3 -m pytest -q
make check
python3 -m vpsmon.cli --config config.example.json --source <name> --notify-first-run --dry-run
```

如果来源需要 token，dry-run 应该用本地 `config.local.json` 和 `.env`，不要把真实配置提交。

## PR 检查表

| 项 | 必须完成 |
|---|---|
| 代码 | `vpsmon/sources/<name>.py` 已实现 |
| CLI | `_build_source()` 已注册 |
| 配置 | `config.example.json` 有脱敏模板 |
| 测试 | fixture 和单元测试通过 |
| 文档 | `docs/sites/<name>.md` 已添加 |
| README | 来源表已更新 |
| 安全 | `git status --short` 没有 `.env`、SQLite、日志、真实配置 |

## 不建议做的事

| 做法 | 问题 |
|---|---|
| 在 source adapter 里直接发 Telegram | 会复制推送逻辑，破坏统一格式 |
| 把 token 写进 JSON config | 容易误提交 |
| 没有 fixture，只测 live API | CI 不稳定，也无法防字段漂移 |
| 为了过规则伪造价格 | 后续排序和推送会误导用户 |
| 一次性加多个来源 | 难排错，建议一个来源一个 PR |
