# 统一检索输入与结果证据格式 —— 落地计划

- **日期**：2026-05-21
- **分支**：`feat/unified-retrieval-protocol`
- **设计来源**：仓库根 `task.md`《统一检索输入与结果证据格式》
- **范围**：协议库 + §7 校验器 + §6 映射适配器 + 接入唯一已落地 skill `network-traffic-analysis`

## 背景

`task.md` 是协议设计文档，定义统一 Input Envelope（§3）、统一 SkillResult /
`evidence_unit`（§4）、十条校验规则（§7）与四个已落地实现的兼容映射（§6）。
探查仓库后确认：

- 仅 `skills/custom/network-traffic-analysis` 在本仓库；citybench / road-traffic /
  policy 三个 skill 不在本仓库。
- 仓库内**没有**任何既有 `SkillResult` / `evidence_unit` schema —— `rag_search.py`
  当前输出扁平 `{query, hits[], ...}`。
- 因此「完成 task.md」= 从零实现该协议。

## 交付物

新建 stdlib-only 包 `skills/_shared/retrieval_protocol/`：

| 文件 | 对应 task.md | 说明 |
|---|---|---|
| `schema.py` | §2 / §4.4 | data_type 登记表（10 类）、features 注册建议、各类枚举 |
| `envelope.py` | §3 | Input Envelope 构造器 |
| `evidence.py` | §4 | evidence_unit / evidence wrapper / SkillResult 构造器 |
| `validate.py` | §7 | 融合前十条校验规则 validator |
| `adapters.py` | §6 | 四个已落地实现的兼容映射适配器 |
| `tests/` | §7 测试清单 | unittest 用例，零依赖运行 |
| `README.md` | —— | 用法文档 |

并给 `network-traffic-analysis/scripts/rag_search.py` 增加**可选** `--format
skillresult` 输出（不破坏现有 `text` / `json`），用 `adapters` 真实接入。

## 任务清单与状态

1. [完成] 建包骨架 + 计划文档 + 特性分支
2. [完成] `schema.py` + `test_schema.py`（15 用例）
3. [完成] `envelope.py` + `test_envelope.py`（16 用例）
4. [完成] `evidence.py` + `test_evidence.py`（18 用例）
5. [完成] `validate.py` + `test_validate.py`（48 用例，§7 十条规则正反例）
6. [完成] `adapters.py` + `test_adapters.py`（26 用例，§6 四适配器，断言适配输出过校验）
7. [完成] 接入 `rag_search.py` `--format skillresult` + 更新 SKILL.md（集成测试 5 用例）
8. [完成] `README.md` + 全量测试全绿 + 分步 commit

**最终状态：128 个 unittest 用例全部通过。** 分两步 commit：

- `feat: 新增统一检索协议库 retrieval_protocol`
- `feat: network-traffic rag_search 支持统一 SkillResult 输出`

## 关键设计决策

- **位置**：`skills/_shared/retrieval_protocol/`。`skills/custom/*` 被 gitignore
  （仅 network-traffic 例外），`skills/public/` 是真 skill 目录；`_shared/` 受版本
  管理、不被 skill loader 扫描、沙箱内可经 `/mnt/skills/_shared/` 访问。
- **零第三方依赖**：仅用标准库，便于任意 skill 直接 import 或拷贝。
- **不污染已实现**（task.md §1）：协议以独立适配层接入，`rag_search.py` 新增
  `--format skillresult` 而非改写既有输出。
- **校验器**：rule 1–8 对 wrapper+payload 机械可校；rule 9 为结构校验；rule 10
  是路由设计约束、无逐条数据校验（README 注明）。
- **测试**：`unittest.TestCase`，`python3 -m unittest discover` 零依赖运行。

## 验证方式

```bash
cd skills/_shared && python3 -m unittest discover -s retrieval_protocol/tests -t . -v
python3 -m py_compile skills/custom/network-traffic-analysis/scripts/rag_search.py
```

已验证：128 用例全绿；`rag_search.py --help` 正常显示
`--format {text,json,skillresult}`；集成测试加载真实 `rag_search.py` 并断言
`_build_skill_result_output` 产出通过 §7 校验。

`rag_search.py` 的 `--format skillresult` 端到端需 Elasticsearch，无法在本环境跑通；
映射逻辑下沉到 `adapters.build_network_traffic_skill_result`，由协议测试套件 +
集成测试完整覆盖。
