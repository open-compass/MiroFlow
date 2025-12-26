# SPDX-FileCopyrightText: 2025 MiromindAI
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import dataclasses
import json
import os
import re
from typing import Any, Dict, List

import tiktoken
from omegaconf import DictConfig
from openai import AsyncOpenAI, OpenAI
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.llm.providers.gpt_openai_client import GPTOpenAIClient
from src.logging.logger import bootstrap_logger

LOGGER_LEVEL = os.getenv("LOGGER_LEVEL", "INFO")
logger = bootstrap_logger(level=LOGGER_LEVEL)

# Configuration is loaded from environment variables (set by src.config.args_config)
# No hardcoded proxy values - use environment variables instead


@dataclasses.dataclass
class QwenClient(GPTOpenAIClient):
    def _create_client(self, config: DictConfig):
        """Create configured OpenAI client"""
        base_url = getattr(self.cfg.llm, "qwen_base_url", None)
        if not base_url:
             base_url = getattr(self.cfg.llm, "openai_base_url", None)
        
        if not base_url:
             # Fallback to environment variable
             base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        logger.info(f"QwenClient using base_url: {base_url}")
        logger.info(f"QwenClient using model_name: {self.model_name}")

        # Try to get qwen_api_key first, fallback to openai_api_key, then environment variables
        api_key = getattr(self.cfg.llm, "qwen_api_key", None)
        if not api_key or api_key == "???":
            api_key = getattr(self.cfg.llm, "openai_api_key", None)
        if not api_key or api_key == "???":
            # Fallback to environment variables
            api_key = os.environ.get("QWEN_API_KEY", os.environ.get("OPENAI_API_KEY", "EMPTY"))
        
        logger.info(f"QwenClient using api_key: {'***' + api_key[-4:] if len(api_key) > 4 else 'EMPTY'}")

        if self.async_client:
            return AsyncOpenAI(
                base_url=base_url,
                timeout=1800,
                api_key=api_key,
            )
        else:
            return OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=1800,
            )

    @retry(
        wait=wait_exponential(multiplier=5),
        stop=stop_after_attempt(5),
        retry=retry_if_not_exception_type(),
    )
    async def _create_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools_definitions,
        keep_tool_result: int = -1,
    ):
        """
        Send message to OpenAI API.
        :param system_prompt: System prompt string.
        :param messages: Message history list.
        :return: OpenAI API response object or None (if error).
        """
        logger.debug(f" Calling LLM ({'async' if self.async_client else 'sync'})")
        # put the system prompt in the first message since OpenAI API does not support system prompt in
        if system_prompt:
            target_role = "system"

            # Check if there are already system or developer messages
            if messages and messages[0]["role"] in ["system", "developer"]:
                # Replace existing message with correct role
                messages[0] = {
                    "role": target_role,
                    "content": [dict(type="text", text=system_prompt)],
                }
            else:
                # Insert new message
                messages.insert(
                    0,
                    {
                        "role": target_role,
                        "content": [dict(type="text", text=system_prompt)],
                    },
                )

        messages_copy = self._remove_tool_result_from_messages(
            messages, keep_tool_result
        )

        tool_list = await self.convert_tool_definition_to_tool_call(tools_definitions)

        try:
            extra_body = {
                "top_k": 20,
                "min_p": 0.0,
            }
            if self.repetition_penalty != 1.0:
                extra_body["repetition_penalty"] = self.repetition_penalty

            params: Dict[str, Any] = {
                "model": self.model_name,
                "temperature": 0.7,
                "max_tokens": self.max_tokens,
                "messages": messages_copy,
                "tools": tool_list,
                "stream": False,
                "top_p": 0.8,
                "extra_body": extra_body,
            }

            if self.oai_tool_thinking:
                response = await self._handle_oai_tool_thinking(
                    params, messages, self.async_client
                )
            else:
                response = await super()._create_completion(params, self.async_client)

            # Collect stats
            try:
                tool_calls_data = []
                if response and response.choices:
                    message = response.choices[0].message
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                         # Convert to dict for the collector
                         for tc in message.tool_calls:
                             tool_calls_data.append({
                                 "function": {
                                     "name": tc.function.name,
                                     "arguments": tc.function.arguments
                                 }
                             })

            except Exception as e:
                logger.warning(f"Failed to collect stats: {e}")

            logger.debug(
                f"Qwen LLM call status: {getattr(response.choices[0], 'finish_reason', 'N/A')}"
            )
            return response
        except asyncio.CancelledError:
            logger.exception("[WARNING] Qwen LLM API call was cancelled during execution")
            raise
        except Exception as e:
            # Check for context overflow
            logger.exception(f"Qwen LLM call failed: {str(e)}")
            raise e