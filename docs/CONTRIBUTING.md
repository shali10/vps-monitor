# 贡献指南

欢迎提交新来源、规则修复、文档和测试。

## 开发流程

```bash
git clone https://github.com/shali10/vps-monitor.git
cd vps-monitor
python3 -m venv .venv
. .venv/bin/activate
pip install -e . pytest
python3 -m pytest -q
```

## 提交前检查

| 检查 | 命令 |
|---|---|
| 语法 | `python3 -m py_compile $(find vpsmon tests -name '*.py' | sort)` |
| 测试 | `python3 -m pytest -q` |
| dry-run | `python3 -m vpsmon.cli --config config.example.json --source czl --notify-first-run --dry-run` |
| 敏感文件 | `git status --short`，确认没有 `.env`、`config.json`、SQLite、日志 |

## 新来源 PR 要求

| 项 | 要求 |
|---|---|
| Source adapter | 放在 `vpsmon/sources/<name>.py` |
| 标准模型 | 输出 `Offer`，不要绕过模型直接发消息 |
| 配置 | 更新 `config.example.json` |
| 文档 | 更新 `docs/CONFIGURATION.md` 或新增来源说明 |
| 测试 | 至少覆盖 normalize 和消息格式 |

## 风格约定

| 项 | 约定 |
|---|---|
| Python | 类型清晰，函数尽量小 |
| 网络请求 | 设置 timeout |
| 错误处理 | 来源失败要明确报错，不吞异常 |
| 文档 | 中文优先，命令可直接复制 |
| 敏感信息 | 不在代码、测试、文档里放真实 token/chat id |

## 发布流程

| 步骤 | 动作 |
|---|---|
| 1 | 更新版本号：`vpsmon/__init__.py` 和 `pyproject.toml` |
| 2 | 更新 `CHANGELOG.md` |
| 3 | 跑测试和 dry-run |
| 4 | 确认 `git status --short` 没有敏感文件 |
| 5 | 打 tag 并推送 |
