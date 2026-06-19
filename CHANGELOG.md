# Changelog

所有版本变更记录。遵循 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

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
