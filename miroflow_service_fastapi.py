#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 MiromindAI
#
# SPDX-License-Identifier: Apache-2.0

"""
FastAPI-based MiroFlow service for AgentCompass integration.

Usage:
    pip install fastapi uvicorn
    uvicorn miroflow_service_fastapi:app --host 0.0.0.0 --port 8082 --workers 4

Features:
- Asynchronous execution using MiroFlow's native async pipeline
- Multiple workers for concurrent request handling
- Compatible with AgentCompass service-type benchmark protocol
- AgentCompass llm_gateway integration via Hydra overrides

Configuration:
    Main model (tested model):
        - Configured via llm_config (model_name, url, api_key)
        - Passed to MiroFlow using Hydra overrides
        - Supports any OpenAI-compatible model (GPT, Claude, Qwen, etc.)

    Tool models (hint generation, final answer extraction, etc.):
        - Configured via service_env_params
        - Set as environment variables
        - Uses OPENAI_*, OPENROUTER_*, HINT_LLM_BASE_URL, etc.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import sys
import pathlib
import dotenv
import hydra
from datetime import datetime

# Ensure MiroFlow root is on sys.path
_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Load environment variables from .env file
dotenv.load_dotenv()

from src.logging.logger import bootstrap_logger
from src.core.pipeline import create_pipeline_components, execute_task_pipeline
from config import config_path
from hydra.core.global_hydra import GlobalHydra

# Initialize logger
LOGGER_LEVEL = os.getenv("LOGGER_LEVEL", "INFO")
logger = bootstrap_logger(level=LOGGER_LEVEL, to_console=True)

app = FastAPI(title="MiroFlow Service")

# Initialize Hydra once at service startup
_hydra_initialized = False

def _ensure_hydra_initialized():
    """Initialize Hydra configuration system once at service startup."""
    global _hydra_initialized
    if not _hydra_initialized:
        abs_config_path = os.path.abspath(config_path())
        # Clear any existing Hydra instance (in case of reload)
        if GlobalHydra.instance().is_initialized():
            GlobalHydra.instance().clear()
        hydra.initialize_config_dir(config_dir=abs_config_path, version_base=None)
        _hydra_initialized = True
        logger.info("Hydra configuration system initialized")


class TaskRequest(BaseModel):
    """AgentCompass-compatible task request."""
    params: Optional[Dict[str, Any]] = None
    benchmark: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None
    modality: Optional[str] = None
    service_env_params: Optional[Dict[str, str]] = None


class TaskResponse(BaseModel):
    """AgentCompass-compatible task response."""
    final_answer: str
    trajectory: Optional[Dict[str, Any]] = None
    call_stat: Optional[Dict[str, Any]] = None
    status: str = "completed"
    error: Optional[str] = None


def _extract_task_description(payload: dict) -> str:
    """Extract task description/question from request payload."""
    params = payload.get('params') or {}
    val = params.get('question') or params.get('query') or params.get('task_description')
    return val.strip() if isinstance(val, str) else ''


def _extract_task_id(payload: dict) -> str:
    """Extract task ID from request payload."""
    params = payload.get('params') or {}
    val = params.get('task_id')
    if val:
        return str(val).strip()
    # Generate a unique task ID if not provided
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def _extract_file_name(payload: dict) -> str:
    """Extract file name from request metadata."""
    params = payload.get('params') or {}
    meta = params.get('metadata') if isinstance(params, dict) else None
    val = meta.get('file_name') if isinstance(meta, dict) else ''
    return val.strip() if isinstance(val, str) else ''


def _resolve_data_file(file_name: str) -> str:
    """Resolve data file path relative to MiroFlow data directory."""
    if not file_name:
        return ''

    data_dir = os.getenv('DATA_DIR', 'data')
    base = os.path.join(_REPO_ROOT, data_dir)
    cand = os.path.join(base, file_name)

    if os.path.isfile(cand):
        return os.path.abspath(cand)

    # Try without data prefix (already absolute or relative to cwd)
    if os.path.isfile(file_name):
        return os.path.abspath(file_name)

    return ''


def _validate_and_set_env_params(service_env_params: dict) -> Optional[str]:
    """
    Validate and set tool API environment parameters required by MiroFlow.

    Main model configuration (QWEN_*) is NOT handled here - it's passed via Hydra overrides.

    Args:
        service_env_params: Dictionary of environment parameters from AgentCompass

    Returns:
        Error message if validation fails, None otherwise
    """
    if not service_env_params:
        service_env_params = {}

    # Required parameters
    required_params = [
        # tool-reasoning triplet
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        # search tools
        "SERPER_API_KEY",
        "JINA_API_KEY",
        # code execution
        "E2B_API_KEY",
    ]

    # Required parameters with default values
    required_params_with_defaults = {
        "OPENROUTER_MODEL_NAME": "gpt-5",
    }

    # Optional parameters with default values (use "$ENV_VAR" to reference other env vars)
    optional_params = {
        # tool-image-video triplet (defaults to OPENROUTER_* values)
        "VISION_API_KEY": "$OPENROUTER_API_KEY",
        "VISION_BASE_URL": "$OPENROUTER_BASE_URL",
        "VISION_MODEL_NAME": "gpt-4o",
        # tool-audio triplet (defaults to OPENROUTER_* values)
        "AUDIO_API_KEY": "$OPENROUTER_API_KEY",
        "AUDIO_BASE_URL": "$OPENROUTER_BASE_URL",
        "AUDIO_TRANSCRIPTION_MODEL_NAME": "gpt-4o-mini-transcribe",
        "AUDIO_MODEL_NAME": "gpt-4o-audio-preview",
        # hint generation triplet (defaults to OPENROUTER_* values)
        "HINT_LLM_API_KEY": "$OPENROUTER_API_KEY",
        "HINT_LLM_BASE_URL": "$OPENROUTER_BASE_URL",
        "HINT_LLM_MODEL_NAME": "$OPENROUTER_MODEL_NAME",
        # final answer extraction triplet (defaults to OPENROUTER_* values)
        "FINAL_ANSWER_LLM_API_KEY": "$OPENROUTER_API_KEY",
        "FINAL_ANSWER_LLM_BASE_URL": "$OPENROUTER_BASE_URL",
        "FINAL_ANSWER_LLM_MODEL_NAME": "$OPENROUTER_MODEL_NAME",
    }

    # Validate and set required parameters
    missing_params = []
    for param in required_params:
        value = service_env_params.get(param)
        if not value or not str(value).strip():
            missing_params.append(param)
        else:
            os.environ[param] = str(value).strip()

    if missing_params:
        return f"Missing required service_env_params: {', '.join(missing_params)}"

    # Set required parameters with defaults (use provided value or default)
    for param, default_value in required_params_with_defaults.items():
        value = service_env_params.get(param)
        if value and str(value).strip():
            os.environ[param] = str(value).strip()
        else:
            os.environ[param] = default_value

    # Set optional parameters (use provided value or default)
    for param, default_value in optional_params.items():
        value = service_env_params.get(param)
        if value and str(value).strip():
            os.environ[param] = str(value).strip()
        elif default_value is not None:
            # Handle $ENV_VAR references
            if isinstance(default_value, str) and default_value.startswith("$"):
                ref_var = default_value[1:]
                os.environ[param] = os.environ.get(ref_var, "")
            else:
                os.environ[param] = default_value

    logger.info("Tool API environment variables configured successfully")
    return None


def _build_llm_config_overrides(llm_config: dict) -> list:
    """
    Build Hydra config overrides for main model from AgentCompass llm_config.

    Uses AgentCompassClient which sends model_infer_params to Gateway,
    letting AgentCompass control inference parameters.

    Args:
        llm_config: LLM configuration from AgentCompass containing:
            - model_name: Model identifier
            - url: Gateway URL (e.g., "http://localhost:8001/v1")
            - api_key: Gateway API key
            - model_infer_params: (optional) Inference params (temperature, top_p, etc.)
            - request_timeout: (optional) Request timeout in seconds

    Returns:
        List of Hydra override strings
    """
    import json as _json

    overrides = []

    if not isinstance(llm_config, dict):
        logger.warning("llm_config is not a dictionary, returning empty overrides")
        return overrides

    model_name = llm_config.get("model_name", "").strip()
    url = llm_config.get("url", "").strip()
    api_key = llm_config.get("api_key", "").strip()
    model_infer_params = llm_config.get("model_infer_params", {})
    request_timeout = llm_config.get("request_timeout", 1800)

    # Validate required fields
    if not model_name:
        logger.error("llm_config.model_name is required but missing")
        return overrides
    if not url:
        logger.error("llm_config.url is required but missing")
        return overrides
    if not api_key:
        logger.error("llm_config.api_key is required but missing")
        return overrides

    # Use AgentCompassClient for both agents
    overrides.extend([
        "main_agent.llm.provider_class=AgentCompassClient",
        "sub_agents.agent-worker.llm.provider_class=AgentCompassClient",
    ])

    # Set model name
    overrides.extend([
        f"main_agent.llm.model_name={model_name}",
        f"sub_agents.agent-worker.llm.model_name={model_name}",
    ])

    # Set gateway URL
    overrides.extend([
        f"+main_agent.llm.base_url={url}",
        f"+sub_agents.agent-worker.llm.base_url={url}",
    ])

    # Set gateway API key
    overrides.extend([
        f"+main_agent.llm.api_key={api_key}",
        f"+sub_agents.agent-worker.llm.api_key={api_key}",
    ])

    # Set model_infer_params as JSON string
    if model_infer_params:
        params_json = _json.dumps(model_infer_params)
        overrides.extend([
            f"+main_agent.llm.model_infer_params='{params_json}'",
            f"+sub_agents.agent-worker.llm.model_infer_params='{params_json}'",
        ])

    # Set timeout
    overrides.extend([
        f"+main_agent.llm.timeout={request_timeout}",
        f"+sub_agents.agent-worker.llm.timeout={request_timeout}",
    ])

    logger.info(f"Built Hydra overrides for AgentCompass gateway:")
    logger.info(f"  Model: {model_name}")
    logger.info(f"  Gateway URL: {url}")
    logger.info(f"  model_infer_params: {model_infer_params}")

    return overrides


async def _run_miroflow_task(
    config_name: str,
    task_id: str,
    task_description: str,
    task_file_name: str,
    llm_config: dict,
) -> tuple[str, str, str, dict, dict, str]:
    """
    Execute a MiroFlow task with AgentCompass gateway configuration.

    Args:
        config_name: MiroFlow config name (e.g., "agent_gaia-validation-text-only")
        task_id: Task identifier
        task_description: Task description/question
        task_file_name: Optional file path for task
        llm_config: LLM configuration from AgentCompass gateway

    Returns:
        Tuple of (final_answer, boxed_answer, status, trajectory, usage_stats, error)
    """
    try:
        # Build Hydra overrides from llm_config
        overrides = _build_llm_config_overrides(llm_config)

        if not overrides:
            return "", "", "failed", [], {}, "Failed to build valid Hydra overrides from llm_config"

        # Ensure Hydra is initialized (once at service startup)
        _ensure_hydra_initialized()

        # Compose configuration with overrides
        cfg = hydra.compose(config_name=config_name, overrides=overrides)

        # Create logs directory
        logs_dir = pathlib.Path(cfg.get('output_dir', 'logs'))
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create pipeline components
        main_agent_tool_manager, sub_agent_tool_managers, output_formatter = (
            create_pipeline_components(cfg, logs_dir=str(logs_dir))
        )

        # Create log path
        log_path = logs_dir / f"{task_id}.log"

        # Execute task pipeline - now returns trajectory and usage_stats
        final_answer, boxed_answer, log_file_path, trajectory, usage_stats = await execute_task_pipeline(
            cfg=cfg,
            task_name=task_id,
            task_id=task_id,
            task_description=task_description,
            task_file_name=task_file_name,
            main_agent_tool_manager=main_agent_tool_manager,
            sub_agent_tool_managers=sub_agent_tool_managers,
            output_formatter=output_formatter,
            log_path=log_path,
            ground_truth=None,
            metadata=None,
        )

        return final_answer, boxed_answer, "completed", trajectory, usage_stats, None

    except Exception as e:
        logger.error(f"Error executing MiroFlow task {task_id}: {e}", exc_info=True)
        error_msg = f"{type(e).__name__}: {str(e)}"
        return "", "", "failed", {}, {}, error_msg


@app.post("/api/tasks", response_model=TaskResponse)
async def run_task(request: TaskRequest):
    """
    Run MiroFlow task via AgentCompass llm_gateway (WAIT protocol).

    This endpoint requires:
    - llm_config: Gateway configuration (model_name, url, api_key)
    - service_env_params: Tool API keys (OPENAI, OPENROUTER, SERPER, etc.)

    Main model configuration is passed via Hydra overrides.
    Tool APIs are configured via environment variables.
    """
    payload = request.model_dump()

    # Extract llm_config (required)
    llm_config = payload.get('llm_config') or {}
    if not llm_config.get("model_name") or not llm_config.get("url") or not llm_config.get("api_key"):
        raise HTTPException(
            status_code=400,
            detail="llm_config must contain model_name, url, and api_key"
        )

    # Validate and set tool environment parameters
    service_env_params = payload.get('service_env_params') or {}
    env_error = _validate_and_set_env_params(service_env_params)
    if env_error:
        logger.error(f"Environment parameter validation failed: {env_error}")
        raise HTTPException(status_code=400, detail=env_error)

    # Extract task information
    task_description = _extract_task_description(payload)
    if not task_description:
        raise HTTPException(status_code=400, detail="empty task description/question")

    task_id = _extract_task_id(payload)
    config_name = "agent_gaia-validation-text-only"  # Fixed config for AgentCompass integration
    file_name = _extract_file_name(payload)

    # Resolve file path if provided
    task_file_name = ""
    if file_name:
        task_file_name = _resolve_data_file(file_name)
        if not task_file_name:
            logger.warning(f"File not found: {file_name}, proceeding without file")

    logger.info(f"Starting task {task_id} with config {config_name}")
    logger.info(f"  Model: {llm_config.get('model_name')}")
    logger.info(f"  Gateway: {llm_config.get('url')}")

    # Execute MiroFlow task - now returns trajectory and usage_stats
    final_answer, boxed_answer, status, trajectory, usage_stats, error = await _run_miroflow_task(
        config_name=config_name,
        task_id=task_id,
        task_description=task_description,
        task_file_name=task_file_name,
        llm_config=llm_config,
    )

    if status == "failed":
        logger.error(f"Task {task_id} failed: {error}")
        return TaskResponse(
            final_answer="",
            status="failed",
            error=error,
            trajectory=None,
            call_stat=None,
        )

    logger.info(f"Task {task_id} completed successfully")

    # Return response (use boxed_answer if available, otherwise final_answer)
    answer = boxed_answer if boxed_answer else final_answer

    return TaskResponse(
        final_answer=answer,
        trajectory=trajectory if trajectory else None,
        call_stat=usage_stats if usage_stats else None,
        status=status,
        error=error,
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "miroflow"}


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="FastAPI server for MiroFlow")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8082, help="Port to listen on (default: 8082)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes (default: 1)")
    args = parser.parse_args()

    logger.info(f"Starting MiroFlow service on {args.host}:{args.port} with {args.workers} workers")

    # For multiple workers, use import string
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    app_target = f"{module_name}:app" if (args.workers and args.workers > 1) else app

    uvicorn.run(app_target, host=args.host, port=args.port, workers=args.workers)
