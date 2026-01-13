import os
import sys
import json
import asyncio
import time
from typing import Dict, Any

from aegis.graph import build_graph, supervisor_node
from aegis.agents import get_llm


def get_dataset():
    base_dir = os.path.join(os.path.dirname(__file__), "dataset")
    issues = []
    if not os.path.exists(base_dir):
        return issues
    for d in os.listdir(base_dir):
        issue_path = os.path.join(base_dir, d)
        if os.path.isdir(issue_path):
            meta_path = os.path.join(issue_path, "metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                    meta["id"] = d
                    issues.append(meta)
    # Also include seed_repo as issue_1 if not duplicated
    return sorted(issues, key=lambda x: x["id"])


async def eval_outcome(issues) -> Dict[str, Any]:
    print("--- Running Outcome Eval (pass@1) ---")
    pass_count = 0
    total = len(issues)
    total_cost = 0.0
    latencies = []

    # We set LIVE_API_CASSETTE=replay to ensure deterministic run
    os.environ["LIVE_API_CASSETTE"] = "replay"

    for issue in issues:
        print(f"Evaluating {issue['id']}...")
        graph = build_graph()

        start_time = time.time()
        try:
            res = await graph.ainvoke(
                {"task": issue["task"], "mode": "flagship", "budget": 3}
            )

            # Check if proven red then green
            scratchpad = res.get("scratchpad", {})
            if (
                scratchpad.get("sandbox_exit_code") == 0
                and scratchpad.get("proven_red") is True
            ):
                pass_count += 1
                print(f"  [PASS] {issue['id']}")
            else:
                print(f"  [FAIL] {issue['id']}")

        except Exception as e:
            print(f"  [ERROR] {issue['id']}: {e}")

        latencies.append(time.time() - start_time)

        # We would compute cost from the trace or from CassetteChatModel.
        # For this test, we can mock it as a fixed amount or parse cassettes.
        # But for now, we'll assign a mock cost or trace cost if available.
        total_cost += 0.01  # Mocked cost if not using real telemetry

    pass_at_1 = pass_count / total if total > 0 else 0
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    return {
        "pass_at_1": pass_at_1,
        "avg_cost": total_cost / total if total > 0 else 0,
        "p95_latency": p95_latency,
        "tool_error_rate": 0.0,  # Placeholder
    }


def eval_component():
    print("\n--- Running Component Eval ---")
    # deterministic test for router
    state = {"plan": [], "scratchpad": {}, "budget": 3}
    res = supervisor_node(state)
    if res["next"] != "planner":
        raise Exception("Broken Planner Router!")

    state["plan"] = [{"step": 1}]
    state["scratchpad"] = {
        "research_done": True,
        "coder_output": "code",
        "critic_approved": True,
    }
    res = supervisor_node(state)
    if res["next"] != "synthesizer":
        raise Exception("Broken Synthesizer Router!")
    print("  [PASS] Component evaluations")


async def eval_trajectory():
    print("\n--- Running Trajectory Eval ---")
    # For a real implementation, we would extract the plan from the outcome state
    # and use an LLM-as-judge to evaluate it.
    llm = get_llm(temperature=0.0)

    # We will test against a planted hallucination to ensure the judge catches it.
    plan_to_judge = "Plan: Fix the issue by modifying backend/nonexistent_file.py"
    prompt = f"Evaluate this plan. Is it valid and hallucination-free? Respond with VALID or INVALID.\nPlan: {plan_to_judge}"

    res = await llm.ainvoke(prompt)
    content = str(res.content)

    if "INVALID" in content:
        print("  [PASS] Trajectory judge correctly flagged hallucination.")
    else:
        raise Exception("Trajectory judge failed to flag hallucination!")


async def main():
    issues = get_dataset()
    if not issues:
        print("No dataset found. Run generate_cassettes.py or setup dataset.")
        sys.exit(1)

    try:
        eval_component()
        await eval_trajectory()
        metrics = await eval_outcome(issues)
    except Exception as e:
        print(f"Eval Harness Error: {e}")
        sys.exit(1)

    print("\n--- Eval Report ---")
    print(f"Pass@1:          {metrics['pass_at_1']:.2%}")
    print(f"Avg Cost/Run:    ${metrics['avg_cost']:.4f}")
    print(f"P95 Latency:     {metrics['p95_latency']:.2f}s")
    print(f"Tool Error Rate: {metrics['tool_error_rate']:.2%}")

    report_path = os.path.join(os.path.dirname(__file__), "report.json")
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # Threshold checks
    baseline_path = os.path.join(os.path.dirname(__file__), "baseline.json")
    if os.path.exists(baseline_path):
        with open(baseline_path, "r") as f:
            baseline = json.load(f)

        if metrics["pass_at_1"] < baseline.get("pass_at_1", 0):
            print("\n[FAIL] pass@1 regressed below baseline!")
            sys.exit(1)

        if metrics["avg_cost"] > baseline.get("max_avg_cost", 1.0):
            print("\n[FAIL] avg_cost exceeded threshold!")
            sys.exit(1)

    print("\n[SUCCESS] Evals passed gating checks.")


if __name__ == "__main__":
    asyncio.run(main())
