# 发布检查清单

## 版本文件

| 文件 | 检查 |
|---|---|
| `vpsmon/__init__.py` | `__version__` 已更新 |
| `pyproject.toml` | `project.version` 已更新 |
| `CHANGELOG.md` | 有对应版本条目 |
| `README.md` | 当前版本描述正确 |

## 本地验证

```bash
python3 -m py_compile $(find vpsmon tests -name '*.py' | sort)
python3 -m pytest -q
python3 -m vpsmon.cli --config config.example.json --source czl --notify-first-run --dry-run
```

## Git 安全检查

```bash
git status --short
git ls-files | grep -E '(^|/)(\.env|config\.json|config\.production\.json|.*\.sqlite3|.*\.log)$' && exit 1 || true
git grep -nE 'TELEGRAM_BOT_TOKEN=.*[0-9]{6,}:|ghp_|github_pat_' -- . ':!docs/RELEASE_CHECKLIST.md'
```

## GitHub 发布

```bash
git add .
git commit -m "chore(release): v4.1.0"
git tag v4.1.0
git push origin main --tags
```

如果使用 PAT 推送，推送后确认 `.git/config` 没有 token：

```bash
grep -nE 'x-access-token|ghp_|github_pat_' .git/config && exit 1 || true
```
