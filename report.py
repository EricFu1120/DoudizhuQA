"""
斗地主理论考试 - 结果分析与对比报告
读取 results/ 目录下的 JSON 结果文件，生成多维度对比报告。
"""
import json
import os
import glob
import argparse
from collections import defaultdict


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
EXAM_PAPER_PATH = os.path.join(os.path.dirname(__file__), "exam_paper.json")

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
DIFFICULTY_CN = {"easy": "易", "medium": "中", "hard": "难"}
CATEGORY_CN = {
    "rules": "规则",
    "card_types": "牌型",
    "strategy": "策略",
    "calculation": "计算",
}


def load_results(filepaths: list[str] | None = None) -> list[dict]:
    """Load result JSON files. If filepaths is None, load the latest per model."""
    if filepaths:
        results = []
        for fp in filepaths:
            with open(fp, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        return results

    # Auto-discover: pick latest file per (model, thinking_mode)
    all_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))
    latest = {}
    for fp in all_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        model_key = data.get("model_key", os.path.basename(fp))
        thinking_mode = data.get("thinking_mode", "unknown")
        key = (model_key, thinking_mode)
        latest[key] = data
    return list(latest.values())


def load_exam_paper() -> dict:
    with open(EXAM_PAPER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Report generators (return Markdown strings)
# ---------------------------------------------------------------------------

def report_overview(results: list[dict]) -> str:
    """Generate overall score comparison as Markdown."""
    lines = ["## 总分对比", ""]
    lines.append("| 模型 | 模式 | 得分 | 正确数 | 正确率 | Prompt Tokens | Completion Tokens |")
    lines.append("|------|------|------|--------|--------|---------------|-------------------|")

    for r in results:
        total_pts = r["total_questions"] * r["points_per_question"]
        pct = r["correct_count"] / r["total_questions"] * 100
        mode = r.get("thinking_mode", "unknown")
        lines.append(
            f"| {r['model_name']} | {mode} "
            f"| {r['score']}/{total_pts} "
            f"| {r['correct_count']}/{r['total_questions']} "
            f"| {pct:.1f}% "
            f"| {r.get('total_prompt_tokens', 0):,} "
            f"| {r.get('total_completion_tokens', 0):,} |"
        )
    lines.append("")
    return "\n".join(lines)


def report_by_difficulty(results: list[dict]) -> str:
    """Generate score breakdown by difficulty as Markdown."""
    lines = ["## 按难度分项得分", ""]

    header = "| 模型 | 模式 |"
    sep = "|------|------|"
    for diff in DIFFICULTY_ORDER:
        header += f" {DIFFICULTY_CN[diff]} |"
        sep += "---|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        mode = r.get("thinking_mode", "")
        line = f"| {r['model_name']} | {mode} |"
        for diff in DIFFICULTY_ORDER:
            answers = [a for a in r["answers"] if a["difficulty"] == diff]
            correct = sum(1 for a in answers if a["correct"])
            total = len(answers)
            score = correct * r["points_per_question"]
            total_pts = total * r["points_per_question"]
            pct = correct / total * 100 if total else 0
            line += f" {score}/{total_pts} ({pct:.0f}%) |"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def report_by_category(results: list[dict]) -> str:
    """Generate score breakdown by knowledge category as Markdown."""
    lines = ["## 按知识点分项得分", ""]

    categories = sorted(set(a["category"] for r in results for a in r["answers"]))

    header = "| 模型 | 模式 |"
    sep = "|------|------|"
    for cat in categories:
        cn = CATEGORY_CN.get(cat, cat)
        header += f" {cn} |"
        sep += "---|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        mode = r.get("thinking_mode", "")
        line = f"| {r['model_name']} | {mode} |"
        for cat in categories:
            answers = [a for a in r["answers"] if a["category"] == cat]
            correct = sum(1 for a in answers if a["correct"])
            total = len(answers)
            pct = correct / total * 100 if total else 0
            line += f" {correct}/{total} ({pct:.0f}%) |"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def report_question_matrix(results: list[dict], paper: dict) -> str:
    """Generate per-question correct/wrong matrix as Markdown."""
    lines = ["## 逐题对错矩阵", "", "> ✓=正确, ✗=错误, -=未答", ""]

    questions = paper["questions"]

    header = "| 题号 | 难度 | 知识点 | 答案 |"
    sep = "|------|------|--------|------|"
    for r in results:
        mode = r.get("thinking_mode", "")
        col_name = f"{r['model_name']}<br>({mode})"
        header += f" {col_name} |"
        sep += "---|"
    lines.append(header)
    lines.append(sep)

    for q in questions:
        diff_cn = DIFFICULTY_CN.get(q["difficulty"], q["difficulty"])
        cat_cn = CATEGORY_CN.get(q["category"], q["category"])
        line = f"| Q{q['id']} | {diff_cn} | {cat_cn} | {q['answer']} |"

        for r in results:
            answer_entry = next(
                (a for a in r["answers"] if a["question_id"] == q["id"]), None
            )
            if answer_entry is None:
                line += " - |"
            elif answer_entry["correct"]:
                line += " ✓ |"
            else:
                ma = answer_entry.get("model_answer", "?")
                line += f" ✗({ma}) |"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def report_hardest_questions(results: list[dict], paper: dict) -> str:
    """Generate hardest questions report as Markdown."""
    lines = ["## 最难题目（多数模型答错）", ""]

    questions = paper["questions"]
    q_stats = []

    for q in questions:
        wrong_models = []
        for r in results:
            entry = next((a for a in r["answers"] if a["question_id"] == q["id"]), None)
            if entry and not entry["correct"]:
                mode = r.get("thinking_mode", "")
                wrong_models.append(f"{r['model_name']}[{mode}]")
        if wrong_models:
            q_stats.append((q, len(wrong_models), wrong_models))

    q_stats.sort(key=lambda x: -x[1])

    for q, wrong_count, wrong_models in q_stats[:10]:
        diff_cn = DIFFICULTY_CN.get(q["difficulty"], q["difficulty"])
        lines.append(f"- **Q{q['id']}** [{diff_cn}] {wrong_count}/{len(results)}个模型答错")
        lines.append(f"  - 题目: {q['question']}")
        lines.append(f"  - 正确答案: {q['answer']}")
        lines.append(f"  - 答错模型: {', '.join(wrong_models)}")
    lines.append("")
    return "\n".join(lines)


def save_report_md(content: str, results: list[dict]) -> str:
    """Save the Markdown report to a file and return the filepath."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(RESULTS_DIR, f"report_{ts}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="斗地主理论考试 - 结果分析报告")
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Specific result JSON files to compare. Default: latest per model.",
    )
    parser.add_argument(
        "--no-matrix",
        action="store_true",
        help="Skip the per-question matrix (can be very long).",
    )
    parser.add_argument(
        "--thinking-only",
        action="store_true",
        help="Only show thinking mode results.",
    )
    parser.add_argument(
        "--no-thinking-only",
        action="store_true",
        help="Only show no-thinking mode results.",
    )
    args = parser.parse_args()

    results = load_results(args.files)

    # Filter by thinking mode if requested
    if args.thinking_only:
        results = [r for r in results if r.get("enable_thinking") is True]
    elif args.no_thinking_only:
        results = [r for r in results if not r.get("enable_thinking")]
    if not results:
        print(f"No result files found in {RESULTS_DIR}/")
        print("Run `python run_exam.py` first to generate results.")
        return

    paper = load_exam_paper()

    # Build Markdown report
    sections = []
    sections.append("# 斗地主理论考试 - LLM 评测对比报告")
    sections.append(f"\n共 {len(results)} 组结果参与评测\n")
    sections.append(report_overview(results))
    sections.append(report_by_difficulty(results))
    sections.append(report_by_category(results))

    if not args.no_matrix:
        sections.append(report_question_matrix(results, paper))

    sections.append(report_hardest_questions(results, paper))

    md_content = "\n".join(sections)

    # Print to console
    print()
    print(md_content)

    # Save to file
    filepath = save_report_md(md_content, results)
    print(f"\n报告已保存至: {filepath}")


if __name__ == "__main__":
    main()
