# 统一检索输入与结果证据格式 —— 落地完成状态

- **状态**：✅ 已完成
- **计划日期**：2026-05-21 · **完成日期**：2026-05-22
- **分支**：`feat/unified-retrieval-protocol`（已本地提交，**未 push**）
- **设计来源**：仓库根 `task.md`《统一检索输入与结果证据格式》
- **范围**：协议库 + §7 校验器 + §6 映射适配器 + 接入唯一已落地 skill `network-traffic-analysis`

---

## 1. 背景

`task.md` 是协议设计文档，定义统一 Input Envelope（§3）、统一 SkillResult /
`evidence_unit`（§4）、十条校验规则（§7）与四个已落地实现的兼容映射（§6）。
探查仓库后确认：

- 仅 `skills/custom/network-traffic-analysis` 在本仓库；citybench / road-traffic /
  policy 三个 skill 不在本仓库。
- 仓库内**没有**任何既有 `SkillResult` / `evidence_unit` schema —— `rag_search.py`
  原本输出扁平 `{query, hits[], ...}`。
- 因此「完成 task.md」= 从零实现该协议。

## 2. 交付物

新建 stdlib-only 包 `skills/_shared/retrieval_protocol/`：

| 文件 | 对应 task.md | 说明 |
|---|---|---|
| `schema.py` | §2 / §4.4 | `data_type` 登记表（10 类）、`FEATURES_REGISTRY`、各类枚举 |
| `envelope.py` | §3 | Input Envelope 构造器（绝对 / 相对时间语义） |
| `evidence.py` | §4 | `evidence_unit` / evidence wrapper / SkillResult 构造器 |
| `validate.py` | §7 | 融合前十条校验规则 validator |
| `adapters.py` | §6 | citybench / network-traffic / road-traffic / policy 兼容映射 |
| `__init__.py` | —— | 公共 API 再导出 |
| `README.md` | —— | 用法文档 |
| `tests/` | §7 测试清单 | 6 个 unittest 文件，零依赖运行 |

接入唯一已落地 skill：`network-traffic-analysis/scripts/rag_search.py` 增加**可选**
`--format skillresult` 输出（不破坏现有 `text` / `json`），经 `adapters` 映射；
同步更新该 skill 的 `SKILL.md`。

## 3. 任务清单（全部完成）

| # | 任务 | 状态 |
|---|---|---|
| 1 | 建包骨架 + 计划文档 + 特性分支 | ✅ |
| 2 | `schema.py` + `test_schema.py` | ✅ 15 用例 |
| 3 | `envelope.py` + `test_envelope.py` | ✅ 16 用例 |
| 4 | `evidence.py` + `test_evidence.py` | ✅ 18 用例 |
| 5 | `validate.py` + `test_validate.py`（§7 十条规则正反例） | ✅ 48 用例 |
| 6 | `adapters.py` + `test_adapters.py`（§6 四适配器，断言适配输出过校验） | ✅ 26 用例 |
| 7 | 接入 `rag_search.py` `--format skillresult` + 更新 SKILL.md | ✅ 集成 5 用例 |
| 8 | `README.md` + 全量测试全绿 + 分步 commit | ✅ |

## 4. 测试结果

**128 个 `unittest` 用例全部通过。**

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_schema.py` | 15 | §2 的 10 类登记取值、分组、§4.4 features 注册表 |
| `test_envelope.py` | 16 | §3 Input Envelope、绝对 / 相对时间 |
| `test_evidence.py` | 18 | §4 evidence_unit / wrapper / SkillResult，复刻 §4.2 示例 |
| `test_validate.py` | 48 | §7 十条规则逐条正反例 |
| `test_adapters.py` | 26 | §6 四适配器，断言适配输出通过 §7 校验 |
| `test_rag_search_integration.py` | 5 | 加载真实 `rag_search.py`，验证 `--format skillresult` 接入 |

复跑命令：

```bash
cd skills/_shared && python3 -m unittest discover -s retrieval_protocol/tests -t . -v
```

## 5. 验证证据

- ✅ 全量 128 用例全绿（`unittest discover`）。
- ✅ 5 个协议模块 `py_compile` 通过；`rag_search.py` `py_compile` 通过。
- ✅ `rag_search.py --help` 正常运行，显示 `--format {text,json,skillresult}`。
- ✅ 集成测试加载真实 `rag_search.py`，断言 `_build_skill_result_output` 产出
  通过 §7 `validate_skill_result` 校验。

## 6. 端到端跑通限制（重要）

`rag_search.py --format skillresult` 的**完整链路**
（`query → 本地嵌入 → ES 检索 → 命中融合 → result → SkillResult`）在本环境**跑不通**，
缺失项实测如下：

| 依赖 | 状态 | 用途 |
|---|---|---|
| `elasticsearch` Python 包 | ❌ 未安装 | 连 ES、发检索请求 |
| `sentence-transformers` 包 | ❌ 未安装 | config 里 embedding provider = `sentence-transformers`（本地模型 `BAAI/bge-m3`），把 query 转向量 |
| ES 服务 `localhost:9200` | ❌ 无服务（`http_code=000`） | 存索引、做检索 |
| 索引 `network-traffic-rag` | ❌ 未灌数据 | 需先跑 pcap→flow.csv→build_rag_docs→embed→index；原始数据集 `datasets/network-traffic/raw/**` 被 .gitignore 忽略，不在仓库 |

**关键区分**：以上 4 项全属 `rag_search.py` 中**未改动的「上游检索」部分**。本次新增的
`_build_skill_result_output(result)` 只消费 `result` 字典、**不碰 ES**，已由集成测试
实跑验证。即「新增逻辑已验证；跑不通的是上游检索基础设施，不是新增代码」。

如需完整端到端演示：Docker 起本地 ES → 用现成 `flow.csv` 灌一个小索引 → 安装
`elasticsearch` + `sentence-transformers` + 下载 bge-m3 模型。此项属 task.md 之外的额外工作。

## 7. 提交记录

特性分支 `feat/unified-retrieval-protocol`，**未 push**（按规范等用户确认）：

| commit | 说明 |
|---|---|
| `434c70a` | feat: 新增统一检索协议库 retrieval_protocol |
| `b9e0613` | feat: network-traffic rag_search 支持统一 SkillResult 输出 |
| `0ce2e39` | docs: 更新统一检索协议落地计划为完成状态 |
| `e7455d1` | test: 集成测试加载 rag_search.py 时禁止写入 .pyc |

> 本文档（完成状态版）的更新另记一次 docs commit。

## 8. 关键设计决策

- **位置**：`skills/_shared/retrieval_protocol/`。`skills/custom/*` 被 gitignore
  （仅 network-traffic 例外），`skills/public/` 是真 skill 目录；`_shared/` 受版本
  管理、不被 skill loader 扫描、沙箱内可经 `/mnt/skills/_shared/` 访问。
- **零第三方依赖**：仅用标准库，便于任意 skill 直接 import 或拷贝。
- **不污染已实现**（task.md §1）：协议以独立适配层接入，`rag_search.py` 新增
  `--format skillresult` 而非改写既有输出。
- **校验器范围**：rule 1–8 对 wrapper + payload 机械可校；rule 9 为 SkillResult
  结构校验；rule 10 是路由设计约束、无逐条数据校验（README 注明）。rule 6 / 7
  依赖语义判断，采用「字段给出即从严」策略。
- **构造器 ↔ 校验器闭环**：测试断言所有构造器产出与所有适配器输出都直接通过 §7 校验。

## 9. 说明与待办

- **`task.md` 未提交**：它是用户交付的源文档（只读、原本就未被 git 跟踪），归用户
  管理；如需纳入版本管理需用户确认。
- **未 push**：4 个 commit 仅在本地分支，按规范 3.4 等用户明确指示再推送。
- **可选后续**：第 6 节的完整端到端演示（起本地 ES + 灌索引），属额外工作。
