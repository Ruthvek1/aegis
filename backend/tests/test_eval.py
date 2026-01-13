import pytest
import os
from unittest.mock import patch


# We test the eval harness scripts logic
def test_eval_component_fails_on_broken_planner():
    # If we patch supervisor_node to return a bad next step, eval_component should raise Exception
    with patch("aegis.graph.supervisor_node") as mock_supervisor:
        # Mock it to return an empty plan / bad routing
        mock_supervisor.return_value = {"next": "unknown"}

        from evals.run_eval import eval_component

        with pytest.raises(Exception, match="Broken Planner Router!"):
            eval_component()


@pytest.mark.asyncio
async def test_eval_trajectory_catches_hallucination():
    from evals.run_eval import eval_trajectory

    # We will patch the `get_llm` inside eval_trajectory so that it uses our CassetteChatModel
    # and retrieves the planted bad plan cassette.
    # Actually, eval_trajectory already uses CassetteChatModel via get_llm(0.0) which defaults to cassette
    # because LIVE_API_CASSETTE is set to "replay" in run_eval.py or by test environment.

    # Let's ensure LIVE_API_CASSETTE is 'replay'
    os.environ["LIVE_API_CASSETTE"] = "replay"

    # If the cassette says "INVALID: Hallucinated file reference.", then it passes without exception
    # We just run eval_trajectory and ensure it doesn't raise an exception
    # (Because the planted cassette is configured to catch the hallucination).
    await eval_trajectory()


def test_eval_baseline_regression_fails():
    from evals.run_eval import main

    # We can mock eval_outcome to return a bad pass@1
    async def mock_eval_outcome(*args):
        return {
            "pass_at_1": 0.5,
            "avg_cost": 0.1,
            "p95_latency": 1.0,
            "tool_error_rate": 0.0,
        }

    with patch("evals.run_eval.eval_outcome", new=mock_eval_outcome):
        with patch("evals.run_eval.eval_component", return_value=None):
            with patch("evals.run_eval.eval_trajectory", return_value=None):
                with patch("sys.exit") as mock_exit:
                    with patch(
                        "evals.run_eval.get_dataset", return_value=[{"id": "issue_1"}]
                    ):
                        import asyncio

                        asyncio.run(main())

                        # Since baseline has pass_at_1 = 1.0, and mock is 0.5, it should sys.exit(1)
                        mock_exit.assert_called_with(1)
