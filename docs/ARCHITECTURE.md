# 架构说明

v4 的核心是把“不同来源的数据形态”压平为统一事件流。

```text
source adapter
  -> raw items
  -> normalize(raw) -> Offer
  -> rules.filter_offers()
  -> StateStore + diff_offers()
  -> Event[]
  -> Telegram renderer
```

## 核心模型

| 模型 | 说明 |
|---|---|
| `Offer` | 标准套餐，包含来源、ID、标题、价格、库存、链接、线路等 |
| `Price` | 标准价格，至少包含年付美元口径 |
| `Event` | 库存变化事件，例如新增、补货、售罄 |
| `StateStore` | SQLite 状态存储 |

## 目录职责

| 路径 | 职责 |
|---|---|
| `vpsmon/cli.py` | 编排一轮运行 |
| `vpsmon/sources/` | 抓取和 normalize，不做通用推送排版 |
| `vpsmon/rules/` | 解析价格/配置，并执行筛选 |
| `vpsmon/engine/diff.py` | 根据旧状态和新 Offer 生成事件 |
| `vpsmon/storage/sqlite.py` | 持久化 offer 快照和事件 |
| `vpsmon/notifiers/telegram.py` | 消息渲染、分页、发送 |

## 新增来源

新增 `example` 来源的推荐步骤：

| 步骤 | 文件 | 内容 |
|---|---|---|
| 1 | `vpsmon/sources/example.py` | 实现 Source 类和 normalize 函数 |
| 2 | `vpsmon/models.py` | 尽量复用现有模型，不轻易加字段 |
| 3 | `vpsmon/cli.py` | 在 `_build_source()` 注册名称 |
| 4 | `config.example.json` | 加来源配置和默认规则 |
| 5 | `tests/` | 覆盖 normalize、规则筛选、格式化输出 |
| 6 | `docs/CONFIGURATION.md` | 记录来源需要的 token 和规则 |

## Source 类约定

Source 类只负责抓取。normalize 函数负责把原始数据转换成 `Offer`。

| 约定 | 原因 |
|---|---|
| source adapter 不直接发 Telegram | 避免每个来源复制推送逻辑 |
| normalize 尽量保留购买链接 | 用户最终需要直达购买 |
| 线路/备注在来源层清理一部分 | 不同商家脏字段不同 |
| 共享排版放 Telegram formatter | 保证所有来源输出一致 |

## 状态与事件

SQLite 记录上一轮 offer 快照。每轮运行后会比较当前数据和历史数据。

| 情况 | 事件 |
|---|---|
| 以前没有，现在有 | 新增 |
| 以前无货，现在有货 | 补货 |
| 以前有货，现在无货 | 售罄 |
| 价格或关键信息变化 | 更新 |

当前发送层默认只渲染有货事件，避免售罄刷屏。
