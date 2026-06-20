# v3.3.0 路线图 (Planned)

**制定时间**: 2026-06-20  
**当前版本**: v3.2.0 (czl.net 适配器完整发布)  
**目标评分**: 89.5 → **92+**

---

## 🎯 核心目标

| 维度 | 当前 (v3.2.0) | 目标 (v3.3.0) | 增量 |
|------|--------------|--------------|------|
| 代码质量 | 90 | 92 | +2 |
| 功能完整度 | 95 | 96 | +1 |
| 文档完整度 | 94 | 96 | +2 |
| 可维护性 | 90 | **94** | +4 |
| 测试覆盖 | 14/14 | **30+** | +16 |
| 活跃度 | 88 | 90 | +2 |
| **总分** | **89.5** | **~92** | **+2.5** |

---

## 🚀 优先级路线(按 ROI 排序)

### 🥇 P0:池规则 env var 化 (代码质量 + 可维护性)

**当前痛点**: 池规则硬编码在 `_site_e_pool_match()`,改要改代码。

**目标**:
```bash
# .env.example 加
SITE_E_POOL_RULES='[
  {"name": "池1(廉价)", "ram_min": 0.4, "ram_max": 1.1, "usd_max": 9},
  {"name": "池2(主力)", "ram_min": 2.0, "ram_max": 16, "usd_min": 10, "usd_max": 20}
]'
```

**影响**:
- 改池规则不用动代码
- 不同环境(dev/staging/prod)用不同池
- 测试可以注入临时池规则

**预估**: ~30 行代码 + 5 个测试 + 1 个 env var

---

### 🥈 P0:utils 抽象 (代码质量)

**当前痛点**: `_parse_ram_gb_e` / `_parse_usd_year_e` 跟 site-a/c/d 重复。

**目标**:
```python
# monitor.py 顶层
def parse_ram_gb(s):     # 统一所有 site
    ...

def parse_usd_year(p):   # 统一所有 site (币种 + 周期)
    ...
```

**影响**:
- 4 个 site 共用工具,减少重复 ~100 行
- 新 site 加适配器更快(已有 utils)
- 修复一处 bug 4 个 site 都受益

**预估**: ~50 行 refactor + 确保 site-a/c/d 不回归 (回归测试)

---

### 🥉 P1:CI/CD (活跃度 + 可维护性)

**当前痛点**: 没有 GH Actions,合并前不能跑测试。

**目标**:
```yaml
# .github/workflows/test.yml
name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
      - run: pip install -r requirements.txt
      - run: python3 -m pytest tests/
      - run: python3 -m py_compile monitor.py
```

**影响**:
- 每个 PR 自动跑 30+ 测试
- dependabot 已经有动作基础(actions/checkout@v7 / setup-python@v6)
- 测试从"可选"变"必须"

**预估**: 1 个 yaml 文件 + 5 行 GH workflow

---

### 🥉 P1:更多商家适配 (功能完整度)

**当前**: 4 个 site (a WHMCS / c public / d HTML / e czl.net 聚合站)

**目标**: 加 2-3 个重点商家:
- **BuyVM** (WHMCS 公开 API) — 卢森堡/拉斯维加斯
- **V.PS** (公开 API) — Tokyo/Amsterdam/Frankfurt 三网
- **Spartan** (公开 API) — Dallas/Seattle 便宜

**影响**:
- 监控覆盖更多 VPS 类型
- 池规则可针对每商家优化

**预估**: 每个 site ~150 行代码 + 测试 + 文档

---

### 🥈 P1:README 加 site-e 章节 (文档)

**当前**: README 没提 site-e

**目标**:
```markdown
## Site 适配器列表
| Site | 商家模式 | 池/过滤 | 状态 |
|------|---------|---------|------|
| a | WHMCS Bearer Auth | 关键词 + 价格 | ✅ |
| b | 公开 API (disabled) | - | ⏸️ |
| c | 公开 API | 全部 | ✅ |
| d | HTML scrape | 全部 | ✅ |
| **e** | **czl.net 聚合 API** | **池1/池2** | **✅ v3.2.0+** |
```

**影响**:
- 潜在 contributor 知道有哪些适配器
- site-e 是新模式(聚合站),值得突出

**预估**: README +20 行

---

## 📊 P2 (可选, 不影响 92 目标)

### P2:metrics / health endpoint (可观测性)

```python
# /metrics 返回 Prometheus 格式
site_e_fetch_duration_seconds
site_e_pool_match_total
site_e_pushed_notifications_total
```

**影响**: 接入监控告警系统 (但单实例暂时不需要)

### P2:metrics_dashboard.py (辅助脚本)

类似 vps-monitor 项目本身的 8 维度评分脚本,给 vps-monitor 加项目自己的 metrics dashboard。

---

## ⚠️ 不做的 (0 实质影响)

按 0 风险偏好,以下**明确不做**:

| 项 | 不做理由 |
|---|---|
| 重写为 type hints 全覆盖 | 动态脚本,无 type hints 不影响功能 |
| 切换到 PostgreSQL/SQLite | 单一 state.json 够用,无性能瓶颈 |
| 加 Docker / docker-compose | 单实例 systemd 部署已经稳定 |
| 加 Web UI | CLI + TG 推送已覆盖使用场景 |
| 切换到 async/await | ThreadPoolExecutor 已经够用 |
| 重写 README 全英文 | 项目面向中文用户,双语增加维护成本 |

---

## 📅 预期时间线

| 阶段 | 内容 | 估时 |
|------|------|------|
| v3.3.0-alpha | 池规则 env var + utils 抽象 + 回归测试 | 半天 |
| v3.3.0-beta | CI/CD + site-f (BuyVM) | 半天 |
| v3.3.0-rc | site-g (V.PS) + site-h (Spartan) + README 更新 | 1 天 |
| **v3.3.0 release** | 全部完成 + GH Release | 1 天总 |

---

## 🎯 完成定义 (Definition of Done)

- [ ] 池规则可通过 env var 配置(改不动代码)
- [ ] utils 抽象完成,4 个 site 共用
- [ ] GH Actions 跑通 30+ 测试(成功率 100%)
- [ ] 至少 2 个新商家适配 (BuyVM + V.PS 或 Spartan)
- [ ] README 有 site-e 章节
- [ ] CHANGELOG [3.3.0] 段完整
- [ ] v3.3.0 GH Release 发布
- [ ] LXC 部署 + systemd 跑通
- [ ] TG 推送验证
- [ ] **总分 92+**

---

## 🤝 协作

如果你(contributor)想认领某个 P0/P1 任务:
1. 在 GitHub Issues 提个 RFC
2. 标注 estimate + design
3. PR + 测试
4. 合并后自动加进 CHANGELOG

---

**维护者**: shali10  
**License**: MIT  
**当前活跃分支**: main
