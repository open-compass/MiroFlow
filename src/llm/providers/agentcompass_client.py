# SPDX-FileCopyrightText: 2025 MiromindAI
#
# SPDX-License-Identifier: Apache-2.0

"""AgentCompass Gateway Client for MiroFlow.

This client sends requests directly to AgentCompass Gateway via HTTP,
including model_infer_params for parameter control by AgentCompass.
"""

import dataclasses
import json
import os
from typing import Any, Dict, List

import httpx
from omegaconf import DictConfig
from tenacity import retry, stop_after_attempt, wait_exponential
from types import SimpleNamespace

from src.llm.providers.gpt_openai_client import GPTOpenAIClient
from src.logging.logger import bootstrap_logger

LOGGER_LEVEL = os.getenv("LOGGER_LEVEL", "INFO")
logger = bootstrap_logger(level=LOGGER_LEVEL)


@dataclasses.dataclass
class AgentCompassClient(GPTOpenAIClient):
    """Client that sends requests to AgentCompass Gateway with model_infer_params."""

    def __post_init__(self):
        super().__post_init__()
        # Extract model_infer_params from config (JSON string or dict)
        raw = getattr(self.cfg.llm, "model_infer_params", None)
        if isinstance(raw, str):
            try:
                self.model_infer_params = json.loads(raw)
            except json.JSONDecodeError:
                self.model_infer_params = {}
        elif isinstance(raw, dict):
            self.model_infer_params = raw
        else:
            self.model_infer_params = {}

    def _create_client(self, config: DictConfig):
        """Create httpx client for AgentCompass Gateway with connection pooling."""
        self.base_url = getattr(self.cfg.llm, "base_url", "")
        self.api_key = getattr(self.cfg.llm, "api_key", "")
        timeout = getattr(self.cfg.llm, "timeout", 3600)

        logger.info(f"AgentCompassClient using base_url: {self.base_url}")
        logger.info(f"AgentCompassClient using model_name: {self.model_name}")

        # Configure connection pooling for better performance
        return httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            )
        )

    def _build_messages(self, system_prompt: str, messages: List[Dict]) -> List[Dict]:
        """Build message list with system prompt."""
        result = []
        if system_prompt:
            if messages and messages[0].get("role") in ["system", "developer"]:
                result.append({"role": "system", "content": system_prompt})
                result.extend(messages[1:])
            else:
                result.append({"role": "system", "content": system_prompt})
                result.extend(messages)
        else:
            result.extend(messages)
        return result

    def _build_tools(self, tools_definitions: List[Dict]) -> List[Dict]:
        """Build OpenAI-format tool list."""
        tool_list = []
        for server in tools_definitions:
            if "tools" in server and server["tools"]:
                for tool in server["tools"]:
                    tool_list.append({
                        "type": "function",
                        "function": {
                            "name": f"{server['name']}-{tool['name']}",
                            "description": tool["description"],
                            "parameters": tool["schema"],
                        },
                    })
        return tool_list

    @retry(
        wait=wait_exponential(multiplier=5),
        stop=stop_after_attempt(5),
    )
    async def _create_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools_definitions,
        keep_tool_result: int = -1,
    ):
        """Send request to AgentCompass Gateway."""
        logger.debug("Calling AgentCompass Gateway")

        messages_copy = self._remove_tool_result_from_messages(messages, keep_tool_result)
        final_messages = self._build_messages(system_prompt, messages_copy)
        tool_list = self._build_tools(tools_definitions)

        # Build payload with model_infer_params at top level
        payload = {
            "model": self.model_name,
            "messages": final_messages,
            "tools": tool_list if tool_list else None,
            "stream": False,
            "model_infer_params": self.model_infer_params,
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except Exception as e:
            logger.exception(f"AgentCompass Gateway call failed: {e}")
            raise

    def _parse_response(self, data: Dict) -> Any:
        """Parse Gateway response to OpenAI-compatible object."""
        response = SimpleNamespace()
        response.id = data.get("id", "")
        response.object = data.get("object", "chat.completion")
        response.created = data.get("created", 0)
        response.model = data.get("model", "")

        # Parse usage
        usage_data = data.get("usage", {})
        usage = SimpleNamespace()
        usage.prompt_tokens = usage_data.get("prompt_tokens", 0)
        usage.completion_tokens = usage_data.get("completion_tokens", 0)
        usage.total_tokens = usage_data.get("total_tokens", 0)
        response.usage = usage

        # Parse choices
        choices = []
        for choice_data in data.get("choices", []):
            choice = SimpleNamespace()
            choice.index = choice_data.get("index", 0)
            choice.finish_reason = choice_data.get("finish_reason", "stop")

            msg_data = choice_data.get("message", {})
            message = SimpleNamespace()
            message.role = msg_data.get("role", "assistant")
            message.content = msg_data.get("content")

            # Parse tool_calls
            tc_data = msg_data.get("tool_calls")
            if tc_data:
                tool_calls = []
                for tc in tc_data:
                    tool_call = SimpleNamespace()
                    tool_call.id = tc.get("id", "")
                    tool_call.type = tc.get("type", "function")
                    fn_data = tc.get("function", {})
                    tool_call.function = SimpleNamespace(
                        name=fn_data.get("name", ""),
                        arguments=fn_data.get("arguments", "{}"),
                    )
                    tool_calls.append(tool_call)
                message.tool_calls = tool_calls
            else:
                message.tool_calls = None

            choice.message = message
            choices.append(choice)

        response.choices = choices
        return response

    def close(self):
        """Close httpx client."""
        if hasattr(self, "client") and self.client:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(self.client.aclose())
            except Exception:
                pass
