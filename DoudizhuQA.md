# DoudizhuQA：用50道斗地主选择题，系统测试大模型

> 一个“可复现、可对比、可扩展”的斗地主理论考试框架，用来衡量不同 LLM 对 **规则、牌型、策略、计算** 的掌握情况，并支持 **thinking / no-thinking** 两种推理模式对照。

## 1. 背景：为什么要做一套“斗地主理论考试”

**可作为准入门槛**：量化大模型自身对斗地主的了解程度，用来判断其是否有资格参加后续的大模型斗地主对战，直接淘汰“人工智障”，或者根据资格赛结果进行分组别对抗。

斗地主也同时是一个非常适合测试大模型“结构化知识 + 推理”的领域：

- **规则与例外多**：牌型、比较规则、特殊牌型（炸弹/火箭）对压制关系的改变。
- **组合与边界条件多**：顺子不含 2、飞机必须连续、连对至少 3 连等。
- **策略题可分层**：既能做基础题（识记），也能做拆牌/控牌/残局的综合题。

相比开放式问答，选择题具备更好的：

- **可量化**：准确率、分项得分、最难题统计。
- **可复现**：同一套题对不同模型、不同参数重复跑。
- **可对比**：同模型在 thinking vs no-thinking 下是否真的更稳。

因此这个项目做了三件事：

- **出题**：`exam_paper.json` 固化 50 道题（含答案与解析）。
- **考试**：`run_exam.py` 批量调用多个模型答题并判分。
- **出报告**：`report.py` 自动聚合结果并输出对比报告（支持保存为 Markdown）。

## 2. 项目结构一览

目录 `DoudizhuQA/` 主要包含：

```
DoudizhuQA/
├── exam_paper.json        # 50 道选择题：题目/选项/答案/解析/难度/类别
├── run_exam.py            # 调用 LLM 答题 + 自动判分 + 保存 results/*.json
├── report.py              # 读取 results/*.json 生成对比报告，并保存为 results/report_*.md
├── config.json.example    # API Key 模板
├── config.json            # 本地配置（不要提交）
├── requirements.txt       # 依赖：openai + tenacity
└── results/               # 结果输出目录
```

## 3. 试卷设计：50 题如何覆盖“规则到策略”

`exam_paper.json` 的顶层结构：

- `total_questions`: 50
- `points_per_question`: 2
- `difficulty_distribution`: easy/medium/hard
- `questions`: 每题包含：
  - `id`
  - `difficulty`: `easy` / `medium` / `hard`
  - `category`: `rules` / `card_types` / `strategy` / `calculation`
  - `question` / `options` / `answer` / `explanation`

### 3.1 难度分布

- **Easy（15）**：规则、基本牌型识记、常见边界条件。
- **Medium（25）**：牌型判断 + 应用题（例如“能不能这样出”“拆法是否合理”）。
- **Hard（10）**：更贴近实战的拆牌、读牌、残局推理、博弈取舍。

### 3.2 解析（explanation）为什么要写

解析的价值不仅在“给人看”，更在：

- **校验题目是否严谨**：能不能把正确性说清楚。
- **发现歧义**：若解析必须“强行解释”，往往题干或选项有问题。
- **后续扩展自动诊断**：未来可以让模型输出理由，再与解析对齐，做更细粒度评测。

## 4. 考试引擎：run_exam.py 的核心实现

### 4.1 统一调用接口

项目通过 DashScope 的 OpenAI 兼容接口进行调用：

- `DEFAULT_BASE_URL = https://dashscope.aliyuncs.com/compatible-mode/v1`
- 使用 `OpenAI(base_url=..., api_key=...)`

`MODEL_REGISTRY` 统一登记模型信息：

- `model_key`：脚本参数用的 key
- `model_id`：实际请求时的 model 名称
- `api_key_env`：从 `config.json` 读取的 key 名

这样你可以很容易增减模型：只改一处注册表即可。

### 4.2 Prompt 约束：只允许输出 A/B/C/D

为了减少“废话答案”导致的解析失败：

- `SYSTEM_PROMPT` 明确要求：
  - 只输出选项字母
  - 不要额外内容

题目格式由 `format_question()` 生成：

- `第{id}题：{question}`
- A/B/C/D 四行选项

### 4.3 判分：parse_answer() 的鲁棒性

真实情况里，模型仍可能输出：

- `答案是A`
- `选A`
- `A.` / `A）`

因此 `parse_answer()` 用一组 regex 做容错提取，最终归一化到 `A-D`。

### 4.4 失败重试

`call_llm()` 使用 `tenacity`：

- 最多重试 3 次
- 指数退避等待

这在批量跑题时能显著减少偶发网络/限流导致的中断。

## 5. thinking / no-thinking：同一模型两种模式怎么对照

很多推理模型/接口支持“思考模式”。本项目通过请求参数：

```python
extra_body={"enable_thinking": True/False}
```

来控制是否启用 thinking。

### 5.1 为什么要做双模式

- **准确率是否提升**：thinking 是否能减少规则题/边界题的误判。
- **代价是否值得**：thinking 往往带来更高的 token 消耗。
- **不同题型的收益不同**：策略/计算题可能更依赖显式推理。

### 5.2 运行方式

`run_exam.py` 支持：

- `--thinking`：只跑 thinking
- `--no-thinking`：只跑 no-thinking（默认）
- `--both`：两种都跑（每个模型跑两遍）

示例：

```bash
# 默认 no-thinking
python run_exam.py

# thinking 模式
python run_exam.py --thinking

# 两种都跑
python run_exam.py --both

# 只跑某几个模型，并且两种模式都跑
python run_exam.py --models qwen3.5 glm-5 --both
```

### 5.3 结果文件命名与元信息

每次运行会产出 `results/*.json`，文件名包含模式：

- `qwen3.5_thinking_YYYYMMDD_HHMMSS.json`
- `qwen3.5_no-thinking_YYYYMMDD_HHMMSS.json`

同时在结果 JSON 中写入：

- `enable_thinking`: `true/false`
- `thinking_mode`: `thinking` / `no-thinking`

确保后续聚合时不会把两种模式混在一起。

## 6. 报告系统：report.py（并保存为 Markdown）

`report.py` 做两件事：

1. **读取结果**：默认从 `results/` 自动挑选每个 `(model_key, thinking_mode)` 的最新一份结果。
2. **输出报告**：按多个维度生成对比分析。

本项目已将报告输出改造成 Markdown，并在运行时自动保存：

- 输出路径：`results/report_YYYYMMDD_HHMMSS.md`

### 6.1 报告包含哪些维度

- **总分对比**：得分、正确率、Prompt/Completion tokens
- **按难度**：easy/medium/hard 分项得分
- **按知识点**：rules/card_types/strategy/calculation 分项
- **逐题矩阵**：每题每个模型（含模式）对错
- **最难题目**：多数模型答错的题目排行

### 6.2 报告筛选：只看 thinking 或只看 no-thinking

```bash
# 全部结果
python report.py

# 只看 thinking
python report.py --thinking-only

# 只看 no-thinking
python report.py --no-thinking-only

# 不输出逐题矩阵
python report.py --no-matrix
```

## 7. 配置与安全：API Key 怎么放

`config.json.example` 给出格式：

```json
{
  "api_keys": {
    "KIMI_API_KEY": "...",
    "GLM_API_KEY": "...",
    "QWEN_API_KEY": "...",
    "MINIMAX_API_KEY": "...",
    "DEEPSEEK_API_KEY": "..."
  }
}
```

建议：

- **永远不要提交 `config.json`**（项目已通过 `.gitignore` 忽略）。
- 如果你有统一的配置文件，也可以把脚本调整为读取环境变量或密钥管理系统。

## 8. 如何解读结果：不仅看总分

总分只是一个入口，建议进一步看：

- **难度分项**：
  - easy 低意味着基础规则不稳
  - hard 低但 easy 高，通常是策略推理不足
- **知识点分项**：
  - card_types 低常见于“飞机/连对/顺子边界”
  - calculation 低常见于“张数/手数/拆解计数”
- **逐题矩阵**：
  - 能快速定位“模型系统性误解”的题目
- **thinking 对照**：
  - 若 thinking 模式提升不明显但 token 激增，可能不值得默认开启

## 9. 可扩展方向（如果你想把它做成一个长期基准）

- **多套试卷**：加入 A/B 卷，避免模型记忆或过拟合。
- **解释对齐评测**：让模型输出理由，与 `explanation` 做一致性评分。
- **成本评估**：将 token × 单价换算成“每提升 1 分需要多少钱”。
- **策略题更贴近实战**：加入“对手剩余牌数/已出牌信息”等状态描述。
- **更细的标签**：将 `category` 拆成更细颗粒（例如“压制规则”“拆牌手数”“连招控牌”）。

## 10. 小结

`DoudizhuQA` 的核心价值是：

- 用 **固定题库** 让模型评测可复现
- 用 **自动判分** 降低人力成本
- 用 **thinking/no-thinking 双模式** 让“推理开关”可量化对比
- 用 **Markdown 报告** 方便沉淀与分享

这套结构也能很容易迁移到其它牌类/桌游（例如桥牌、升级、掼蛋）的理论题评测。
