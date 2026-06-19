# Contributing

欢迎 PR!无论是加新站 / 修 bug / 改文档 / 加测试,都感谢你的贡献。

## 开发流程

### 1. Fork + Clone

```bash
git clone https://github.com/<your-user>/vps-monitor.git
cd vps-monitor
pip3 install -r requirements.txt
pip3 install pytest   # 跑测试用
```

### 2. 加新站点(最常见贡献)

5 步 recipe(详见 `README.md`):

1. 顶部加常量(SITE_E_API_URL / TOKEN / POLL_INTERVAL / DEPLOY_URL)
2. 复制现有 site 的 4 个函数(`fetch` / `compare` / `notify` / `monitor`)改名为 `*_site_e`
3. `load_state()` 加 `site_e` key
4. `main()` 加轮询调度
5. `--once` 加 site_e case

完成后:
- 加 `docs/sites/site-e-<your-merchant>.md` 说明适配笔记
- 跑 `tests/test_monitor_smoke.py` 确认语法 OK
- 加 `.env.example` 段
- CHANGELOG 加一行

### 3. 修 Bug

- 写 `tests/test_<scenario>.py` 复现 bug(应该 fail)
- 改 `monitor.py` 修复
- 跑测试确认通过
- 提交 PR,标题写清楚"Fix: <症状>"
- 如果是 Pitfall 类型,**强烈建议** 加到 `docs/PITFALLS.md`

### 4. 改文档

直接编辑 `.md` 文件,提交 PR。**拼写 / 格式 / 链接** 都欢迎改。

### 5. 加测试

`tests/` 用 pytest。每个测试文件独立:
- `test_monitor_smoke.py` — 语法 / import / 启动 smoke
- `test_state_diff.py` — state.json diff 逻辑(纯函数,易测)

加新测试:模仿 `test_state_diff.py` 模式,纯函数 + 临时 state 文件 + assert。

## 提交前 Checklist

- [ ] 代码通过 `python3 -m py_compile monitor.py`(语法检查)
- [ ] 新功能加测试
- [ ] `.env.example` 同步更新(如有新 KEY)
- [ ] `CHANGELOG.md` 加一行
- [ ] 跑 `vpsmonctl status` + `vpsmonctl check` 真验证(在自己部署上)
- [ ] 不提交 `.env` / `state.json` / `*.log` / `*.bak`(`.gitignore` 已排除,谨慎确认)

## 风格约定

- Python 3.9+ 兼容(不用 walrus operator 复杂特性)
- 函数命名 `snake_case`,类 `PascalCase`,常量 `UPPER_SNAKE_CASE`
- 字符串优先双引号
- 注释中文 OK(本项目面向中文用户)
- 错误处理:每个 site 独立 try/except,主循环不 catch 所有
- 日志用 `log.info` / `log.exception`,不要 `print`

## Commit 风格

[Conventional Commits](https://www.conventionalcommits.org/) 风格:

```
feat(site-e): add Site E (新商家 WHMCS)
fix(monitor): flush log handler every emit
docs(pitfalls): add Pitfall 27 (新坑)
test(state-diff): add test for empty state
chore: bump version to 3.1.0
```

## Release 流程

1. 合并 PR 到 main
2. 更新 `CHANGELOG.md`(把 `[Unreleased]` 改成具体版本号 + 日期)
3. `git tag v3.x.y`
4. `git push --tags`
5. GitHub release(用 `gh release create v3.x.y --notes "..."`)

## 不接受的 PR

- ❌ 加 .env 真值(任何凭据都不进 git)
- ❌ 大改架构而不讨论(先开 issue)
- ❌ 加新依赖到 `requirements.txt` 而不说明理由(本项目尽量 0 依赖,只 `requests`)

## 联系

有问题开 [Issue](https://github.com/<your-user>/vps-monitor/issues) 或 PR 讨论。
