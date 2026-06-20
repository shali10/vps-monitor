# Changelog

所有版本变更记录。遵循 [Semantic Versioning](https://semver.org/)。

## [3.3.0] - 2026-06-20

### 🐛 Bug Fixes
- **site_c 静默 5+ 小时**：service 启动后 site_c 块 0 变化静默，无法验证主循环真在跑。加 `总是 log` (Pitfall 18 套路，跟 site_d 一致)
- **遗留监控源 CLI NameError**：`--once --site b` 调用未定义变量（其实是 site_a 的）。删 3 行 CLI 块
- **monitor.py 头部 docstring 过期**：写 "3 个独立 source"（site_a/b/c），实际是 4 个（site_a/c/d/e）。已改

### 📝 Documentation
- **ONBOARDING.md 新增**：接入新站 SOP（项目一句话 / 关键词库 / 判定层 / 接入流程 / 已硬编码配置 / "你只需要说的" / Q&A / 代码位置）。README §8 引用此文件

### ⚠️ 注意事项
- **README.md 未变更**：OSS 公开版（badge + LICENSE + CI 描述）与 LXC 实战版（含内部数字）分开维护
- 完整 release notes 见 GitHub: https://github.com/shali10/vps-monitor/releases/tag/v3.3.0

## [3.2.0] - 2026-06-20

### 新增
- 🚀 **Site E 适配器**: vps-monitor.czl.net 公开 API (`/api/public/filter`), 池规则 (池1 廉价 / 池2 主力), 58 条匹配
- 🔧 **3 个 site-e 修复** (per user 2026-06-20):
  - USD 数字价格比较 + 1% 容忍 (避免币种换算/格式化噪音)
  - 异常返回 `None` + Round 2 retry (失败页自动恢复)
  - `ThreadPoolExecutor` 8 worker 并发 (抓取耗时 26s → 14s, 提速 46%)
- 📝 `docs/sites/site-e-vps-monitor-czl.md` 适配笔记 (含 fetch/compare/池规则/部署/限制)
- 🧪 `tests/test_site_e.py` 池规则 + 价格解析 + USD 比较 (~30 个测试)
- 📄 `.env.example` 加 `SITE_E_API_URL` / `SITE_E_POLL_INTERVAL` / `SITE_E_DEPLOY_URL`

### 部署
- LXC 容器部署 (`/opt/vps-monitor/monitor.py`)
- systemd: `vps-monitor.service` 自动 restart
- 2 小时轮询间隔 (`SITE_E_POLL_INTERVAL=7200`)
- TG 推送: 2 个 chat_id (user TG + QQ bot 转发)

### 已知限制
- 池规则硬编码 → 改需改代码 (env var 化是 v3.3.0 优化项)
- 价格 USD 换算汇率硬编码 (1 USD = 0.139 CNY = 1.08 EUR)
- 依赖 czl.net 公开 API 持续可用 (down 则 site-e 静默, 不影响其他 site)
- LXC 488MB RAM 下 8 worker 完全够 (内存压力 < 10MB)

## [3.0.0] - 2026-06-19

### 重大变更
- 🎉 **首次开源发布**:从内部运维脚本升级为公开 OSS 项目
- 目录结构重组:`monitor.py` + `vpsmonctl` + `.service` + `docs/` + `scripts/` + `tests/` + `examples/`
- 新增 `.gitignore` / `.env.example` / `LICENSE` / `requirements.txt` / `CHANGELOG.md`
- 16 份本地备份移出生产目录 → `ARCHIVE_YYYYMMDD_HHMMSS/`(数据零丢失)
- README 重写为 OSS 版(脱敏 + 架构图 + 商家适配模板)

### 从 v2.x 继承的功能
- 多 site adapter 架构(`fetch_site_X` / `compare_site_X` / `notify_site_X` / `monitor_site_X`)
- 事件驱动 diff(只推新套餐 + 补货,不刷屏)
- systemd 集成(`EnvironmentFile=` + `Restart=always`)
- `vpsmonctl` 控制器(10+ 命令封装 backup / restart / set-config / manual-push)
- `FlushFileHandler` 解决 Python `logging.FileHandler` buffer 不 flush 的丢日志问题
- per-site try/except:一个站抛异常不阻塞其他站
- 业务规则三重过滤:关键词 + 价格区间 + 库存 > 0

### 已适配的商家模式
| 模式 | 代表商家 | 鉴权 | 解析方式 |
|---|---|---|---|
| WHMCS Bearer | Site A (dartnode/fuckip.me) | `Authorization: Bearer eyJ...` | JSON 分页 + Bearer |
| 公开 WHMCS | Site B | 无 | JSON 分页 |
| 资源模板 | Site C (incudal) | `Authorization: Bearer eyJ...` | package 自身当 1 个伪 plan |
| HTML 解析 | Site D (DediRock) | 无 | `requests + BeautifulSoup` 或正则 |

## [2.x] - 2026-06

内部迭代版本,具体变更见 `ARCHIVE_*/` 中的 `monitor.py.bak.*` 历史备份。
