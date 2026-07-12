import os
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv("../.env")
key1 = os.getenv("NVIDIA_API_KEY_1")

class TestSchema(BaseModel):
    name: str
    age: int

async def main():
    llm = ChatOpenAI(
        model="meta/llama-3.1-70b-instruct",
        api_key=key1,
        base_url="https://integrate.api.nvidia.com/v1",
        max_retries=0
    )
    
    sllm = llm.with_structured_output(TestSchema)
    
    print("Invoking structured llm...")
    try:
        res = await sllm.ainvoke("My name is John and I am 30 years old.")
        print(res)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
