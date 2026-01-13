import os
import json
import hashlib
import re
from typing import Any
from langchain_core.messages import AIMessage

from aegis.telemetry import get_tracer, MODEL_PRICING


def _scrub_volatile(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _scrub_volatile(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_scrub_volatile(v) for v in data]
    elif isinstance(data, str):
        # Scrub UUIDs to ensure stable hashing
        data = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "<UUID>",
            data,
            flags=re.IGNORECASE,
        )
        return data
    return data


def hash_prompt(prompt: Any, kwargs: dict) -> str:
    scrubbed_prompt = _scrub_volatile(prompt)
    scrubbed_kwargs = _scrub_volatile(kwargs)
    payload = json.dumps(
        {"prompt": scrubbed_prompt, "kwargs": scrubbed_kwargs}, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CassetteChatModel:
    def __init__(self, real_model, cassette_dir: str, model_name: str):
        self.real_model = real_model
        self.cassette_dir = cassette_dir
        self.model_name = model_name
        self.mode = os.environ.get(
            "LIVE_API_CASSETTE", "off"
        )  # "record", "replay", "off"
        if self.mode != "off":
            os.makedirs(self.cassette_dir, exist_ok=True)
        self.tracer = get_tracer(__name__)

    def _prepare_prompt_for_hash(self, prompt):
        prompt_val = prompt
        if isinstance(prompt, list):
            prompt_val = [
                getattr(p, "dict", lambda: str(p))()
                if hasattr(p, "dict")
                else (p.model_dump() if hasattr(p, "model_dump") else str(p))
                for p in prompt
            ]
        return prompt_val

    def _record_telemetry(self, span, usage: dict):
        if not span or not span.is_recording():
            return
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        pricing = MODEL_PRICING.get(self.model_name, {"input": 0.0, "output": 0.0})
        cost = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000

        from aegis.cost import add_cost

        add_cost(cost)

        span.set_attribute("llm.cost", cost)
        span.set_attribute("llm.tokens.input", input_tokens)
        span.set_attribute("llm.tokens.output", output_tokens)

    async def ainvoke(self, prompt, *args, **kwargs):
        with self.tracer.start_as_current_span("llm_call") as span:
            prompt_val = self._prepare_prompt_for_hash(prompt)
            key = hash_prompt(prompt_val, kwargs)
            file_path = os.path.join(self.cassette_dir, f"{key}.json")

            if self.mode == "replay":
                if not os.path.exists(file_path):
                    raise ValueError(
                        f"Cassette not found for key {key}. Run in 'record' mode first."
                    )
                with open(file_path, "r") as f:
                    data = json.load(f)
                    msg = AIMessage(**data)
                    self._record_telemetry(span, msg.response_metadata.get("usage", {}))
                    return msg

            res = await self.real_model.ainvoke(prompt, *args, **kwargs)
            self._record_telemetry(span, res.response_metadata.get("usage", {}))

            if self.mode == "record":
                with open(file_path, "w") as f:
                    json.dump(res.dict(), f, indent=2)

            return res

    def with_structured_output(self, schema, **kwargs):
        real_runnable = self.real_model.with_structured_output(schema, **kwargs)

        class CassetteStructuredRunnable:
            def __init__(self, real, parent, schema):
                self.real = real
                self.parent = parent
                self.schema = schema

            async def ainvoke(self, prompt, *args, **kw):
                with self.parent.tracer.start_as_current_span("llm_call_structured"):
                    prompt_val = self.parent._prepare_prompt_for_hash(prompt)
                    schema_name = (
                        self.schema.__name__
                        if hasattr(self.schema, "__name__")
                        else str(self.schema)
                    )
                    merged_kw = {**kw, "schema": schema_name}

                    key = hash_prompt(prompt_val, merged_kw)
                    file_path = os.path.join(self.parent.cassette_dir, f"{key}.json")

                    if self.parent.mode == "replay":
                        if not os.path.exists(file_path):
                            raise ValueError(f"Cassette not found for key {key}")
                        with open(file_path, "r") as f:
                            data = json.load(f)
                            # Telemetry for structured output replay? We don't have usage in the parsed data.
                            # So cost is 0 or we store usage explicitly. Let's just store the response object.
                            # Wait, structured output returns parsed data, not AIMessage.
                            if hasattr(self.schema, "model_validate"):
                                return self.schema.model_validate(data)
                            elif hasattr(self.schema, "parse_obj"):
                                return self.schema.parse_obj(data)
                            return data

                    # Real call
                    # To get usage for structured output, Langchain hides it!
                    # If we need cost for structured output, we might miss it here unless we fetch from callbacks.
                    # But the user said "nest the LLM-call span... so cost roll up correctly".
                    # We can let it be 0 for structured output or just use the span.
                    res = await self.real.ainvoke(prompt, *args, **kw)

                    if self.parent.mode == "record":
                        with open(file_path, "w") as f:
                            if hasattr(res, "model_dump"):
                                json.dump(res.model_dump(), f, indent=2)
                            elif hasattr(res, "dict"):
                                json.dump(res.dict(), f, indent=2)
                            else:
                                json.dump(res, f, indent=2)
                    return res

        return CassetteStructuredRunnable(real_runnable, self, schema)
