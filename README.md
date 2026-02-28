# 斗地主理论考试 - LLM 评测系统

通过 50 道斗地主选择题评估不同大模型对斗地主规则、牌型、策略的理解程度。

## 试卷结构

| 难度 | 类型 | 题数 | 分值 |
|------|------|------|------|
| 易 | 识记类（规则、牌型名称、基本概念） | 15 | 30 |
| 中 | 理解+应用类（牌型判断、出牌决策、配合策略） | 25 | 50 |
| 难 | 分析综合类（手牌拆解、记牌推理、复杂博弈） | 10 | 20 |
| **合计** | | **50** | **100** |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp config.json.example config.json
# 编辑 config.json，填入你的 API Key
```

所有模型均通过 DashScope 兼容接口调用（`https://dashscope.aliyuncs.com/compatible-mode/v1`）。

> 如果已有 `doudizhu-arena/config.json`，脚本会自动回退读取该文件，无需重复配置。

### 3. 运行考试

```bash
# 测试所有模型（默认 no-thinking 模式）
python run_exam.py

# 只测试指定模型
python run_exam.py --models kimi-k2.5 qwen3.5

# 开启 thinking 模式
python run_exam.py --thinking

# 同时跑 thinking 和 no-thinking 两种模式
python run_exam.py --both

# 指定模型 + 指定模式
python run_exam.py --models qwen3.5 --both
```

### 4. 查看报告

```bash
# 自动读取 results/ 下最新结果，生成对比报告
python report.py

# 跳过逐题矩阵（输出更简洁）
python report.py --no-matrix

# 只看 thinking 模式结果
python report.py --thinking-only

# 只看 no-thinking 模式结果
python report.py --no-thinking-only

# 指定结果文件对比
python report.py --files results/kimi-k2.5_thinking_20260227.json results/qwen3.5_no-thinking_20260227.json
```

## 目录结构

```
DoudizhuQA/
├── exam_paper.json       # 50 道选择题（题目、选项、答案、难度、知识点）
├── run_exam.py           # 主脚本：调用 LLM 作答 + 自动判分
├── report.py             # 生成多维度对比报告
├── config.json.example   # API Key 配置模板
├── config.json           # API Key 配置（gitignore）
├── requirements.txt      # Python 依赖
├── results/              # 考试结果 JSON（自动生成）
└── README.md
```

## 支持的模型

| Key | 模型 | 提供商 |
|-----|------|--------|
| `kimi-k2.5` | Kimi K2.5 | Moonshot |
| `glm-5` | GLM-5 | Z.ai |
| `qwen3.5` | Qwen3.5 | Alibaba |
| `minimax-m2.5` | MiniMax M2.5 | MiniMax |
| `deepseek-v3.2` | DeepSeek V3.2 | DeepSeek |

如需添加模型，编辑 `run_exam.py` 中的 `MODEL_REGISTRY`。

## 报告维度

- **总分对比**：得分、正确率、Token 用量（按模型 × 模式）
- **按难度**：易/中/难 分项得分
- **按知识点**：规则/牌型/策略/计算 分项得分
- **逐题矩阵**：每题每个模型（含 thinking/no-thinking）的对错详情
- **最难题目**：多数模型答错的题目排行

## Thinking 模式

通过 `extra_body={"enable_thinking": True/False}` 控制模型是否启用深度思考。

- 每个模型可分别以 thinking 和 no-thinking 两种模式参加考试
- 结果文件按模式分别保存，如 `qwen3.5_thinking_20260227_183000.json`
- 报告中会同时展示两种模式的成绩，便于对比思考对答题准确率的影响
