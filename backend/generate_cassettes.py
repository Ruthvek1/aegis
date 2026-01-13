import os
import json
from aegis.cassette import hash_prompt


def save_cassette(cassette_dir, prompt, schema_name, output, usage):
    kw = {"schema": schema_name} if schema_name else {}
    h = hash_prompt(prompt, kw)
    os.makedirs(cassette_dir, exist_ok=True)
    with open(os.path.join(cassette_dir, f"{h}.json"), "w") as f:
        # Match AIMessage(**data) exactly
        json.dump({"content": output, "response_metadata": {"usage": usage}}, f)
    return h


def generate_cassettes():
    cassette_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "cassettes"))

    issues = [
        (
            "issue_1",
            "Fix the division by zero bug in math_lib.py. It should raise ValueError('Cannot divide by zero') instead of ZeroDivisionError.",
            "backend/seed_repo/math_lib.py",
            "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\ndef multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b\n",
        ),
        (
            "issue_2",
            "Fix the IndexError in get_first_char in string_utils.py. It should return None if the string is empty.",
            "backend/evals/dataset/issue_2/string_utils.py",
            "def get_first_char(s):\n    if not s:\n        return None\n    return s[0]\n",
        ),
        (
            "issue_3",
            "Fix the KeyError in get_value in dict_utils.py. It should return None if the key is missing.",
            "backend/evals/dataset/issue_3/dict_utils.py",
            "def get_value(d, key):\n    return d.get(key)\n",
        ),
        (
            "issue_4",
            "Fix the TypeError in concat_strings in concat_utils.py. It should convert both arguments to strings before concatenating.",
            "backend/evals/dataset/issue_4/concat_utils.py",
            "def concat_strings(a, b):\n    return str(a) + str(b)\n",
        ),
        (
            "issue_5",
            "Fix the logic error in multiply_list in math_utils.py. It should return the product of the numbers, not the sum. Also initialize result to 1.",
            "backend/evals/dataset/issue_5/math_utils.py",
            "def multiply_list(nums):\n    result = 1\n    for n in nums:\n        result *= n\n    return result\n",
        ),
    ]

    for issue_id, task_desc, filename, fixed_code in issues:
        # Planner
        context = f"Task: {task_desc}\nEpisodic: []\nSkills: []"
        planner_prompt = f"Create a plan for: {context}"
        planner_out = {"plan": [{"step": "1", "action": f"Fix {filename}"}]}
        save_cassette(
            cassette_dir,
            planner_prompt,
            "PlanOutput",
            json.dumps(planner_out),
            {"input_tokens": 100, "output_tokens": 20},
        )

        # Turn 1: Coder (Produce RED)
        plan_repr = str(planner_out["plan"])
        coder_prompt = f"Execute plan: {plan_repr}"

        # The run_cmd must point to the check_bug file!
        if issue_id == "issue_1":
            check_file = "seed_repo/check_bug.py"
        else:
            check_file = f"evals/dataset/{issue_id}/check_bug.py"

        coder_out_1 = f"RUN_CMD: python -B {check_file}"
        save_cassette(
            cassette_dir,
            coder_prompt,
            None,
            coder_out_1,
            {"input_tokens": 50, "output_tokens": 10},
        )

        # Turn 1: Critic (VETO because it fails)
        critic_prompt_1 = (
            f"Review this output: {coder_out_1}. Exit code: 1. Proven red: True"
        )
        critic_out_1 = {"approved": False, "feedback": "Tests failed."}
        save_cassette(
            cassette_dir,
            critic_prompt_1,
            "CriticDecision",
            json.dumps(critic_out_1),
            {"input_tokens": 30, "output_tokens": 10},
        )

        # Turn 2: Coder (Produce GREEN fix)
        # prompt includes feedback
        coder_prompt_2 = (
            f"Execute plan: {plan_repr}\nPrevious feedback: {critic_out_1['feedback']}"
        )

        # Output applies WRITE_FILE and then runs RUN_CMD
        coder_out_2 = f"WRITE_FILE: {filename}\n```python\n{fixed_code}```\nRUN_CMD: python -B {check_file}"
        save_cassette(
            cassette_dir,
            coder_prompt_2,
            None,
            coder_out_2,
            {"input_tokens": 60, "output_tokens": 100},
        )

        # Turn 2: Critic (APPROVES)
        critic_prompt_2 = (
            f"Review this output: {coder_out_2}. Exit code: 0. Proven red: True"
        )
        critic_out_2 = {"approved": True, "feedback": "Fix applied successfully."}
        save_cassette(
            cassette_dir,
            critic_prompt_2,
            "CriticDecision",
            json.dumps(critic_out_2),
            {"input_tokens": 150, "output_tokens": 10},
        )

        # Researcher Node
        research_prompt = f"Extract relations from: {task_desc}"
        research_out = f"Source -> Target (Relation) [{filename}:10]"
        save_cassette(
            cassette_dir,
            research_prompt,
            None,
            research_out,
            {"input_tokens": 50, "output_tokens": 15},
        )

    # Trajectory Judge Cassette
    plan_to_judge = "Plan: Fix the issue by modifying backend/nonexistent_file.py"
    judge_prompt = f"Evaluate this plan. Is it valid and hallucination-free? Respond with VALID or INVALID.\nPlan: {plan_to_judge}"
    save_cassette(
        cassette_dir,
        judge_prompt,
        None,
        "INVALID: Hallucinated file reference.",
        {"input_tokens": 50, "output_tokens": 10},
    )


generate_cassettes()
