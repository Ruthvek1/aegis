import os
import asyncio
from dotenv import load_dotenv

load_dotenv("../.env")

# Mock the current API key since we're not running in FastAPI context
import aegis.api_key
aegis.api_key.current_api_key.set(os.getenv("NVIDIA_API_KEY_1"))

from aegis.agents import planner_node
from langchain_core.messages import HumanMessage

async def main():
    state = {
        "messages": [HumanMessage(content="print hello")],
        "next": "",
        "task_plan": "",
        "code_files": {}
    }
    print("Invoking planner_node...")
    try:
        res = await planner_node(state)
        print("Result:", res)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
