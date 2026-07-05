# 配置说明

`vps-monitor` 使用 JSON 配置，敏感值通过环境变量传入。

## 文件约定

| 文件 | 是否提交 | 用途 |
|---|---|---|
| `config.example.json` | 是 | 公开示例配置 |
| `config.local.json` | 否 | 本地调试配置 |
| `/opt/vps-monitor/config.json` | 否 | 生产配置 |
| `.env.example` | 是 | 环境变量模板 |
| `.env` | 否 | 真实 token |

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `state_db` | string | SQLite 状态库路径，相对配置文件所在目录解析 |
| `sources` | object | 来源配置 |
| `rules` | object | 筛选规则 |
| `notify_policy` | object | 推送排序和数量限制 |
| `telegram` | object | Telegram 发送配置 |

## sources

每个来源一个配置块。

| 字段 | 说明 |
|---|---|
| `enabled` | 是否启用来源 |
| `api_url` | 来源 API 地址 |
| `deploy_url` | 购买链接模板 |
| `token_env` | 读取 token 的环境变量名 |
| `page_size` | 分页大小 |
| `max_pages` | 最大页数 |
| `max_workers` | 并发抓取数量，当前主要用于 czl |

`dujiaojing` 需要 `SITE_A_TOKEN`。`czl` 当前使用公开接口。

## rules.global

全局规则会应用到所有来源。

| 字段 | 说明 |
|---|---|
| `exclude_keywords` | 命中这些关键词的套餐会被排除 |

常见排除词包括 dedicated、dedi、独立服务器。

## rules.<source>

来源级规则可按需要扩展。

| 字段 | 说明 |
|---|---|
| `price_min_usd_year` | 年付最低价 |
| `price_max_usd_year` | 年付最高价 |
| `monthly_price_max_usd` | 月付最高价 |
| `price_max_usd_month` | 月均最高价 |
| `pools` | 套餐池，用于排序和标记重点套餐 |

## pools

套餐池是命名筛选条件。命中后消息里会显示池名，并可通过 `pool_price` 优先排序。

| 字段 | 说明 |
|---|---|
| `name` | 池名称 |
| `cpu_min_cores` | CPU 最小核心数 |
| `ram_min_gb` | 内存下限 |
| `ram_max_gb` | 内存上限 |
| `usd_year_min` | 年付价格下限 |
| `usd_year_max` | 年付价格上限 |

## notify_policy

| 字段 | 说明 |
|---|---|
| `limit_events` | 最多渲染多少条有货事件 |
| `sort_events` | 排序方式：`source`、`price`、`pool_price`、`stock` |

如果某来源没有单独配置，会使用 `default`。

## telegram

| 字段 | 说明 |
|---|---|
| `enabled` | 是否启用 Telegram 配置 |
| `bot_token_env` | Bot token 环境变量名 |
| `chat_ids_env` | Chat id 列表环境变量名，逗号分隔 |
| `disable_web_page_preview` | 是否禁用网页预览 |

真实 token 不要写入 JSON。推荐放 `.env`，systemd 用 `EnvironmentFile=` 注入。
