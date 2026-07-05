# czl.net 来源

`czl` 来源用于监控 `vps-monitor.czl.net` 的公开筛选接口。

## 配置

```json
{
  "enabled": true,
  "api_url": "https://vps-monitor.czl.net/api/public/filter",
  "deploy_url": "https://vps-monitor.czl.net/buy/{item_id}",
  "page_size": 12,
  "max_pages": 100,
  "max_workers": 8
}
```

## 字段映射

| 原始字段 | Offer 字段 | 说明 |
|---|---|---|
| `id` | `external_id` | 购买链接参数 |
| `title` | `name` | 套餐标题 |
| `provider` | `provider` | 商家/来源标签 |
| `location` | `region` | 地区 |
| `cpu` | `cpu_cores` | 通过文本解析 |
| `ram` | `ram_gb` | 支持 MB/GB |
| `disk` | `disk` | 原样保留 |
| `bandwidth` | `traffic` | 原样保留 |
| `price` | `price.usd_year` | 支持年付/月付/人民币换算 |
| `isAvailable` | `available` | 是否有货 |

## 推荐规则

| 规则 | 推荐值 | 说明 |
|---|---:|---|
| `price_min_usd_year` | `1` | 排除异常低价脏数据 |
| `price_max_usd_year` | `70` | 保留低价 VPS 主范围 |
| `monthly_price_max_usd` | `10` | 排除月付过高套餐 |
| `sort_events` | `pool_price` | 命中池优先，再按价格排序 |

## 常见池

```json
{
  "name": "池1(廉价)",
  "ram_min_gb": 0.4,
  "ram_max_gb": 1.0,
  "usd_year_min": 0,
  "usd_year_max": 10
}
```

```json
{
  "name": "池2(主力)",
  "cpu_min_cores": 2,
  "ram_min_gb": 2.0
}
```

## dry-run

```bash
vpsmon-v4 --config config.local.json --source czl --notify-first-run --dry-run
```

## 排错

| 现象 | 处理 |
|---|---|
| raw 很多但 filtered 为 0 | 放宽价格/内存规则 |
| 消息里标题太长 | formatter 会自动截断，必要时调 `format_offer` |
| 购买链接打不开 | 检查 `deploy_url` 是否仍符合站点路径 |
| 重复推送 | 删除测试 SQLite 后会重新首轮，请确认 `state_db` 路径 |
