"""
斗地主理论考试 - 自动评测脚本
通过 DashScope OpenAI 兼容接口调用不同大模型作答，并自动判分。
"""
import json
import os
import re
import time
import argparse
from datetime import datetime

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EXAM_PAPER_PATH = os.path.join(os.path.dirname(__file__), "exam_paper.json")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

MODEL_REGISTRY = {
    "kimi-k2.5": {
        "name": "Kimi K2.5",
        "model_id": "kimi-k2.5",
        "api_key_env": "KIMI_API_KEY",
    },
    "glm-5": {
        "name": "GLM-5",
        "model_id": "glm-5",
        "api_key_env": "GLM_API_KEY",
    },
    "qwen3.5": {
        "name": "Qwen3.5",
        "model_id": "qwen3.5-397b-a17b",
        "api_key_env": "QWEN_API_KEY",
    },
    "minimax-m2.5": {
        "name": "MiniMax M2.5",
        "model_id": "MiniMax-M2.5",
        "api_key_env": "MINIMAX_API_KEY",
    },
    "deepseek-v3.2": {
        "name": "DeepSeek V3.2",
        "model_id": "deepseek-v3.2",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
}

SYSTEM_PROMPT = (
    "你是一位斗地主职业选手。请仔细审题并回答以下选择题。\n"
    "你只需要回答选项字母（A、B、C 或 D），不要输出任何额外内容。\n"
    "格式示例：A"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load API keys from config.json."""
    if not os.path.exists(CONFIG_PATH):
        # Fallback: try doudizhu-arena config
        arena_config = os.path.join(os.path.dirname(__file__), "..", "doudizhu-arena", "config.json")
        if os.path.exists(arena_config):
            with open(arena_config, "r", encoding="utf-8") as f:
                return json.load(f).get("api_keys", {})
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("api_keys", {})


def load_exam_paper() -> dict:
    """Load exam paper from JSON."""
    with open(EXAM_PAPER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_question(q: dict) -> str:
    """Format a question dict into a prompt string."""
    lines = [f"第{q['id']}题：{q['question']}"]
    for key in ("A", "B", "C", "D"):
        lines.append(f"  {key}. {q['options'][key]}")
    return "\n".join(lines)


def parse_answer(response: str) -> str:
    """Extract the answer letter from LLM response."""
    if not response:
        return ""
    text = response.strip()
    # Direct single letter
    if text.upper() in ("A", "B", "C", "D"):
        return text.upper()
    # Match patterns like "A" "A." "答案是A" "选A" etc.
    patterns = [
        r"^([A-D])\s*[.。\)）]",          # A. or A。 or A)
        r"答案[是为：:]\s*([A-D])",         # 答案是A
        r"选[择]?\s*([A-D])",              # 选A / 选择A
        r"(?:correct|answer)[:\s]*([A-D])", # answer: A
        r"\b([A-D])\b",                    # any standalone A-D
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return ""


# ---------------------------------------------------------------------------
# LLM caller
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(multiplier=1, min=2, max=30))
def call_llm(client: OpenAI, model_id: str, question_text: str, enable_thinking: bool = False) -> tuple[str, dict]:
    """Call the LLM and return (response_text, token_usage)."""
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question_text},
        ],
        temperature=0.0,
        max_tokens=1024,
        stream=False,
        extra_body={"enable_thinking": enable_thinking},
    )
    content = resp.choices[0].message.content or ""
    usage = {}
    if resp.usage:
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens or 0,
            "completion_tokens": resp.usage.completion_tokens or 0,
            "total_tokens": resp.usage.total_tokens or 0,
        }
    return content.strip(), usage


# ---------------------------------------------------------------------------
# Main exam runner
# ---------------------------------------------------------------------------

def run_exam_for_model(model_key: str, api_keys: dict, paper: dict, enable_thinking: bool = False) -> dict:
    """Run the full exam for one model, return results dict."""
    cfg = MODEL_REGISTRY[model_key]
    api_key = api_keys.get(cfg["api_key_env"], "")
    if not api_key:
        print(f"  [SKIP] No API key for {cfg['name']} ({cfg['api_key_env']})")
        return {}

    client = OpenAI(base_url=DEFAULT_BASE_URL, api_key=api_key)
    questions = paper["questions"]

    thinking_label = "thinking" if enable_thinking else "no-thinking"
    results = {
        "model_key": model_key,
        "model_name": cfg["name"],
        "model_id": cfg["model_id"],
        "enable_thinking": enable_thinking,
        "thinking_mode": thinking_label,
        "timestamp": datetime.now().isoformat(),
        "total_questions": len(questions),
        "points_per_question": paper["points_per_question"],
        "answers": [],
        "score": 0,
        "correct_count": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
    }

    for i, q in enumerate(questions):
        q_text = format_question(q)
        print(f"  [{i+1}/{len(questions)}] Q{q['id']} ({q['difficulty']})...", end=" ", flush=True)

        try:
            raw_resp, usage = call_llm(client, cfg["model_id"], q_text, enable_thinking)
            model_answer = parse_answer(raw_resp)
            correct = model_answer == q["answer"]
        except Exception as e:
            raw_resp = f"ERROR: {e}"
            usage = {}
            model_answer = ""
            correct = False

        results["answers"].append({
            "question_id": q["id"],
            "difficulty": q["difficulty"],
            "category": q["category"],
            "correct_answer": q["answer"],
            "model_answer": model_answer,
            "correct": correct,
            "raw_response": raw_resp,
            "token_usage": usage,
        })

        if correct:
            results["correct_count"] += 1
            results["score"] += paper["points_per_question"]

        results["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        results["total_completion_tokens"] += usage.get("completion_tokens", 0)

        status = "✓" if correct else f"✗ (answered {model_answer or '?'}, correct {q['answer']})"
        print(status)

        # Small delay to avoid rate limits
        time.sleep(0.3)

    return results


def save_results(results: dict):
    """Save results to a JSON file."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    thinking_tag = "thinking" if results.get("enable_thinking") else "no-thinking"
    filename = f"{results['model_key']}_{thinking_tag}_{ts}.json"
    filepath = os.path.join(RESULTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  Results saved to: {filepath}")
    return filepath


def print_summary(results: dict):
    """Print a quick summary of results."""
    total = results["total_questions"]
    correct = results["correct_count"]
    score = results["score"]
    total_pts = total * results["points_per_question"]
    mode = results.get("thinking_mode", "unknown")
    print(f"\n  === {results['model_name']} [{mode}] ===")
    print(f"  Score: {score}/{total_pts} ({correct}/{total} correct, {correct/total*100:.1f}%)")

    # By difficulty
    for diff in ("easy", "medium", "hard"):
        diff_answers = [a for a in results["answers"] if a["difficulty"] == diff]
        if diff_answers:
            diff_correct = sum(1 for a in diff_answers if a["correct"])
            print(f"    {diff:8s}: {diff_correct}/{len(diff_answers)} correct")

    # Token usage
    pt = results["total_prompt_tokens"]
    ct = results["total_completion_tokens"]
    if pt or ct:
        print(f"  Tokens: prompt={pt}, completion={ct}, total={pt+ct}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="斗地主理论考试 - LLM 评测")
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODEL_REGISTRY.keys()),
        choices=list(MODEL_REGISTRY.keys()),
        help="Models to test (default: all)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        default=False,
        help="Enable thinking mode (enable_thinking=True)",
    )
    parser.add_argument(
        "--no-thinking",
        action="store_true",
        default=False,
        help="Disable thinking mode (enable_thinking=False)",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        default=False,
        help="Run both thinking and no-thinking modes",
    )
    args = parser.parse_args()

    # Determine thinking modes to run
    if args.both:
        thinking_modes = [True, False]
    elif args.thinking:
        thinking_modes = [True]
    elif args.no_thinking:
        thinking_modes = [False]
    else:
        thinking_modes = [False]  # default: no-thinking

    print("=" * 60)
    print("斗地主理论考试卷（选择题50题）- LLM 自动评测")
    print("=" * 60)

    api_keys = load_config()
    paper = load_exam_paper()

    modes_str = ", ".join("thinking" if m else "no-thinking" for m in thinking_modes)
    print(f"\nLoaded {paper['total_questions']} questions, {paper['total_points']} points total")
    print(f"Models to test: {', '.join(args.models)}")
    print(f"Thinking modes: {modes_str}\n")

    all_results = []

    for enable_thinking in thinking_modes:
        mode_label = "thinking" if enable_thinking else "no-thinking"
        for model_key in args.models:
            print(f"\n--- Testing: {MODEL_REGISTRY[model_key]['name']} [{mode_label}] ---")
            results = run_exam_for_model(model_key, api_keys, paper, enable_thinking)
            if results:
                save_results(results)
                print_summary(results)
                all_results.append(results)

    # Final comparison
    if len(all_results) > 1:
        print("\n" + "=" * 60)
        print("COMPARISON")
        print("=" * 60)
        header = f"{'Model':<20} {'Mode':<12} {'Score':>8} {'Easy':>8} {'Medium':>8} {'Hard':>8}"
        print(header)
        print("-" * len(header))
        for r in all_results:
            easy_c = sum(1 for a in r["answers"] if a["difficulty"] == "easy" and a["correct"])
            med_c = sum(1 for a in r["answers"] if a["difficulty"] == "medium" and a["correct"])
            hard_c = sum(1 for a in r["answers"] if a["difficulty"] == "hard" and a["correct"])
            easy_t = sum(1 for a in r["answers"] if a["difficulty"] == "easy")
            med_t = sum(1 for a in r["answers"] if a["difficulty"] == "medium")
            hard_t = sum(1 for a in r["answers"] if a["difficulty"] == "hard")
            total_pts = r["total_questions"] * r["points_per_question"]
            mode = r.get('thinking_mode', 'unknown')
            print(
                f"{r['model_name']:<20} "
                f"{mode:<12} "
                f"{r['score']:>3}/{total_pts:<3} "
                f"{easy_c:>2}/{easy_t:<2}    "
                f"{med_c:>2}/{med_t:<2}    "
                f"{hard_c:>2}/{hard_t:<2}"
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
