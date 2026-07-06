# 更新记录

这个文件记录项目的重要变更。

## v4.4.1 - 2026-07-06

### Changed

- 将公开展示文案统一为中文，包括 README 演示图 alt、Telegram 预览 SVG 文案、项目描述和更新记录。
- 保留代码 API 名称、GitHub 标准字段、Python trove classifiers 等必要英文元数据。

## v4.4.0 - 2026-07-06

### Added

- 新增 `czl` 和 `dujiaojing` 的脱敏 API 响应 fixture，放在 `tests/fixtures/`。
- 新增 source 级 fetch 测试，覆盖分页、请求参数、认证 header、normalize、库存状态、流量格式和部署 URL 渲染，全程不访问外网。
- 新增独角鲸云缺少 token 时的报错覆盖。

### Changed

- 更新 README 成熟度评分，体现 fixture 驱动的 source adapter 覆盖。
- 版本升到 `4.4.0`。

## v4.3.0 - 2026-07-06

### Added

- 新增 GitHub 可直接渲染的 Telegram 推送预览图 `assets/telegram-preview.svg`，并展示在 README。
- 新增 SQLite diff 生命周期测试，覆盖首轮建状态、首轮显式通知、补货、降价和事件落库。
- 新增套餐池筛选回归测试，覆盖低价池命中和缺失规格拒绝。

### Changed

- 更新 README 成熟度评分，体现扩展后的状态和 diff 测试覆盖。
- 版本升到 `4.3.0`。

## v4.2.1 - 2026-07-06

### Fixed

- 修复 `make check` 的敏感形态扫描，避免扫描规则匹配到 Makefile 自己，同时继续扫描项目内容。

## v4.2.0 - 2026-07-06

### Added

- README 新增徽章、目录、来源矩阵和 OSS 成熟度评分。
- 新增 `Makefile`，提供 install、syntax、test、check、dry-run、clean 等命令。
- 新增 `SECURITY.md`，说明支持版本、报告方式和敏感数据边界。
- 新增 GitHub Bug / Feature Issue 模板。
- 新增 Dependabot 配置，覆盖 pip 和 GitHub Actions。
- 新增 `docs/sites/` 下的 `czl` 和 `dujiaojing` 来源文档。
- 新增示例：`examples/minimal-czl.json` 和 `examples/offer.example.json`。

### Changed

- 版本升到 `4.2.0`。
- README 从可用的公开说明扩展成更完整的 OSS 项目首页。
- 收紧公开 placeholder 示例，避免长得像真实 token。

## v4.1.0 - 2026-07-06

### Added

- 新增中文公开 README，包含快速开始、命令表、systemd 说明、安全边界和来源适配指南。
- 新增 MIT `LICENSE`。
- 新增 `pyproject.toml` 包元数据和 `vpsmon-v4` console script。
- 新增 `.env.example`，用于 Telegram 和来源 token 模板。
- 新增 `docs/` 文档：安装、配置、架构、排错、贡献指南和发布检查表。
- 新增 GitHub Actions workflow，覆盖 Python 3.10-3.12 测试。
- 新增包版本 `vpsmon.__version__ = "4.1.0"`。

### Changed

- 移除已提交的 `config.json` 和 `config.production.json`；公开仓库只保留 `config.example.json`。
- 扩展 `.gitignore`，排除本地配置、构建产物、覆盖率文件和包元数据。
- 将项目定位从内部生产快照调整为公开 OSS 工具。

## v4.0.0 - 2026-07-05

### Added

- 将监控器重构为 typed package，包含 source adapter、标准 offer 模型、SQLite 状态和统一 Telegram formatter。
- 新增内置适配器：`dujiaojing` 和 `czl`。
- 新增事件 diff，统一处理首轮行为、补货检测和售罄状态更新。
- 新增来源级筛选和套餐池规则。
- 新增 systemd timer 示例，用于周期检查。
- 新增解析、筛选、消息渲染、摘要渲染和 Telegram 发送链路测试。

### Changed

- 用 SQLite 状态存储替换单脚本状态处理。
- 统一不同来源的 Telegram 输出格式。
