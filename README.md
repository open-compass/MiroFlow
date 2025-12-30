# MiroFlow Service for AgentCompass

MiroFlow FastAPI service for integration with AgentCompass service-type benchmarks.

## Introduction

`miroflow_service_fastapi.py` is a FastAPI-based HTTP service that wraps the MiroFlow Agent framework as a RESTful API, enabling integration with the AgentCompass system. The service receives task requests, processes them using MiroFlow's asynchronous execution engine, and returns structured results.

## Features

- ✅ Fully compatible with AgentCompass service-type interface specification
- ✅ Supports asynchronous execution and multi-worker concurrent processing
- ✅ Automatic extraction of execution trajectory
- ✅ Token usage statistics for the main tested model
- ✅ Model invocation through AgentCompass llm_gateway
- ✅ Supports multiple benchmarks including GAIA, HLE, etc.

## Quick Start

### 1. Install Dependencies

```bash
cd MiroFlow

# Install FastAPI and uvicorn
pip install fastapi uvicorn

# Install MiroFlow and its dependencies (from pyproject.toml)
pip install -e .
```

> **Note**: `uv` is a Python package management tool required by the `markitdown-mcp` server to manage dependencies for file reading tools. If `uv` is missing, file reading functionality will fail with the error: `[Errno 2] No such file or directory: 'uv'`

### 2. Configure Environment Variables (Optional)

If you need to configure proxy or log level, create a `.env` file:

```bash
# Log level (optional, default: INFO)
LOGGER_LEVEL=INFO

# HTTP proxy (optional)
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# Data directory (optional, default: data/)
DATA_DIR=data/
```

> **Note**: Tool API configurations (such as OPENROUTER_API_KEY, SERPER_API_KEY, etc.) should NOT be configured in `.env`. They are passed through the `service_env_params` parameter in requests.

### 3. Start the Service

`miroflow_service_fastapi.py` supports two startup methods:

#### Method 1: Run Script Directly (Recommended)

```bash
# Single worker mode (development/debugging)
python miroflow_service_fastapi.py --host 0.0.0.0 --port 8082 --workers 1

# Multi-worker mode (production, recommended)
python miroflow_service_fastapi.py --host 0.0.0.0 --port 8082 --workers 4
```

**Command-line Arguments:**
- `--host`: Host address to bind (default: 0.0.0.0)
- `--port`: Port to listen on (default: 8082)
- `--workers`: Number of worker processes (default: 1)

#### Method 2: Start with uvicorn

```bash
# Single worker
uvicorn miroflow_service_fastapi:app --host 0.0.0.0 --port 8082

# Multi-worker
uvicorn miroflow_service_fastapi:app --host 0.0.0.0 --port 8082 --workers 4
```

### 4. Verify Service is Running

```bash
curl http://localhost:8082/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "miroflow"
}
```

## API Reference

### POST /api/tasks

The main interface for executing MiroFlow tasks. This endpoint receives task descriptions and configurations, executes tasks using the MiroFlow Agent, and returns results.

#### Request Example

```bash
curl -X POST "http://localhost:8082/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "task_id": "task_001",
      "question": "What is the capital of France?"
    },
    "llm_config": {
      "model_name": "gpt-4o",
      "url": "http://localhost:8001/v1",
      "api_key": "sk-ac-noauth",
      "request_timeout": 3600
    },
    "service_env_params": {
      "OPENROUTER_API_KEY": "your-api-key",
      "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
      "SERPER_API_KEY": "your-serper-key",
      "JINA_API_KEY": "your-jina-key",
      "E2B_API_KEY": "your-e2b-key"
    }
  }'
```

#### Request Body Structure

```json
{
  "params": {
    "task_id": "task_001",
    "question": "What is the capital of France?",
    "metadata": {
      "file_name": "optional_file.txt"
    }
  },
  "llm_config": {
    "model_name": "gpt-4o",
    "url": "http://localhost:8001/v1",
    "api_key": "sk-ac-noauth",
    "model_infer_params": {
      "temperature": 0.6,
      "top_p": 0.95
    },
    "request_timeout": 3600
  },
  "service_env_params": {
    "OPENROUTER_API_KEY": "your-api-key",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "SERPER_API_KEY": "your-serper-key",
    "JINA_API_KEY": "your-jina-key",
    "E2B_API_KEY": "your-e2b-key"
  }
}
```

#### Request Parameters

**1. params (Task Parameters)**

| Parameter | Type | Required | Description |
|------|------|------|------|
| `params.question` | string | Yes | Task question/description |
| `params.task_id` | string | No | Task ID, auto-generated if not provided (format: task_YYYYMMDD_HHMMSS_microseconds) |
| `params.metadata.file_name` | string | No | Associated data file name (relative to DATA_DIR directory) |

**2. llm_config (Main Model Configuration)**

| Parameter | Type | Required | Description |
|------|------|------|------|
| `llm_config.model_name` | string | Yes | Model name (e.g., gpt-4o, claude-3-5-sonnet-20241022) |
| `llm_config.url` | string | Yes | AgentCompass Gateway URL (e.g., http://localhost:8001/v1) |
| `llm_config.api_key` | string | Yes | Gateway API key |
| `llm_config.model_infer_params` | object | No | Inference parameters (temperature, top_p, etc.) |
| `llm_config.request_timeout` | int | No | Request timeout in seconds (default: 1800) |

**3. service_env_params (Tool API Configuration)**

These parameters configure the various tool APIs used by MiroFlow. See the "Tool API Environment Variables" section below for details.

#### Response Format

**Success Response Example:**

```json
{
  "final_answer": "Paris",
  "trajectory": {
    "main_agent_message_history": {
      "messages": [
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "Let me search for this information..."}
      ]
    },
    "sub_agent_message_history_sessions": {},
    "step_logs": [
      {
        "step_name": "search",
        "message": "Searching for capital of France",
        "timestamp": "2025-01-01T12:00:00",
        "status": "completed",
        "metadata": {}
      }
    ],
    "tool_models": {
      "vision_model": "gpt-4o",
      "audio_model": "gpt-4o-audio-preview",
      "reasoning_model": "gpt-5",
      "hint_llm_model": "gpt-5",
      "final_answer_llm_model": "gpt-5"
    }
  },
  "call_stat": {
    "input_tokens": 1500,
    "input_cached_tokens": 200,
    "output_tokens": 800,
    "output_reasoning_tokens": 0,
    "total_tokens": 2300
  },
  "status": "completed",
  "error": null
}
```

**Failure Response Example:**

```json
{
  "final_answer": "",
  "trajectory": null,
  "call_stat": null,
  "status": "failed",
  "error": "Missing required service_env_params: SERPER_API_KEY, JINA_API_KEY"
}
```

#### Response Fields

**Top-level Fields:**

| Field | Type | Description |
|------|------|------|
| `final_answer` | string | Final answer (returns boxed_answer if available, otherwise final_answer) |
| `trajectory` | object/null | Execution trajectory object containing complete execution history |
| `call_stat` | object/null | Token usage statistics (main model only) |
| `status` | string | Task status: "completed" or "failed" |
| `error` | string/null | Error message (returned on failure) |

**trajectory Object Structure:**

| Field | Type | Description |
|------|------|------|
| `main_agent_message_history` | object | Main agent's message history |
| `sub_agent_message_history_sessions` | object | Sub-agent message history sessions |
| `step_logs` | array | Detailed step execution logs |
| `tool_models` | object | Tool model configuration information |

**call_stat Object Structure:**

| Field | Type | Description |
|------|------|------|
| `input_tokens` | int | Total input tokens |
| `input_cached_tokens` | int | Cached input tokens |
| `output_tokens` | int | Total output tokens |
| `output_reasoning_tokens` | int | Reasoning tokens (e.g., o1 models) |
| `total_tokens` | int | Total tokens |

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "miroflow"
}
```

## Configuration

### Tool API Environment Variables

`service_env_params` are tool API configuration parameters passed to the MiroFlow service through AgentCompass requests. These parameters are set as environment variables on the service side and used by MiroFlow's various tools (search, code execution, file reading, reasoning, etc.).

> **Important Notes**:
> - These parameters are passed by **AgentCompass** through the `service_env_params` field when calling the MiroFlow service
> - MiroFlow service sets these parameters as environment variables for tool usage
> - Do NOT configure these parameters in the `.env` file (`.env` is only for service-level configurations like proxy, logging, etc.)

#### Required Parameters

The following parameters must be provided in `service_env_params`, otherwise the service will return an error:

| Parameter | Purpose | Use Case | Example |
|------|------|----------|------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Used for reasoning tools, hint generation, final answer extraction, and other auxiliary models | `sk-or-v1-xxx` |
| `OPENROUTER_BASE_URL` | OpenRouter API address | Used with API key | `https://openrouter.ai/api/v1` |
| `SERPER_API_KEY` | Serper search engine API key | Used for web search tool (tool-searching) | `xxx` |
| `JINA_API_KEY` | Jina Reader API key | Used for web content reading and parsing (tool-reading) | `jina_xxx` |
| `E2B_API_KEY` | E2B code sandbox API key | Used for safe Python code execution (tool-python) | `e2b_xxx` |

#### Required Parameters (with Defaults)

The following parameters will use default values if not provided:

| Parameter | Default Value | Purpose | Use Case |
|------|--------|------|----------|
| `OPENROUTER_MODEL_NAME` | `gpt-5` | OpenRouter default model name | Used for reasoning tools, hint generation, final answer extraction, and other auxiliary tasks |

#### Optional Parameters (with Defaults)

The following parameters will use default values or reference other parameters if not provided (`$ENV_VAR` indicates referencing another parameter's value):

**Reasoning Tool Related (tool-reasoning):**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `ANTHROPIC_API_KEY` | `dummy-key` | Anthropic API key for calling Claude models for reasoning |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Anthropic API address |
| `ANTHROPIC_MODEL_NAME` | `claude-3-7-sonnet-20250219` | Anthropic default model name |

**Video Analysis Related (tool-image-video):**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `GEMINI_API_KEY` | `dummy-key` | Google Gemini API key for YouTube video analysis |

**Vision Tool Related (tool-image-video):**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `VISION_API_KEY` | `$OPENROUTER_API_KEY` | Vision model API key for image analysis |
| `VISION_BASE_URL` | `$OPENROUTER_BASE_URL` | Vision model API address |
| `VISION_MODEL_NAME` | `gpt-4o` | Vision model name |

**Audio Tool Related (tool-audio):**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `AUDIO_API_KEY` | `$OPENROUTER_API_KEY` | Audio model API key for audio transcription and analysis |
| `AUDIO_BASE_URL` | `$OPENROUTER_BASE_URL` | Audio model API address |
| `AUDIO_TRANSCRIPTION_MODEL_NAME` | `gpt-4o-mini-transcribe` | Audio transcription model name |
| `AUDIO_MODEL_NAME` | `gpt-4o-audio-preview` | Audio analysis model name |

**Hint Generation Related:**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `OPENAI_API_KEY` | `$OPENROUTER_API_KEY` | OpenAI API key for general LLM calls |
| `OPENAI_BASE_URL` | `$OPENROUTER_BASE_URL` | OpenAI API address |
| `HINT_LLM_API_KEY` | `$OPENROUTER_API_KEY` | Hint generation model API key for generating task hints |
| `HINT_LLM_BASE_URL` | `$OPENROUTER_BASE_URL` | Hint generation model API address |
| `HINT_LLM_MODEL_NAME` | `$OPENROUTER_MODEL_NAME` | Hint generation model name |

**Final Answer Extraction Related:**

| Parameter | Default Value | Purpose |
|------|--------|------|
| `FINAL_ANSWER_LLM_API_KEY` | `$OPENROUTER_API_KEY` | Final answer extraction model API key for extracting answers from execution results |
| `FINAL_ANSWER_LLM_BASE_URL` | `$OPENROUTER_BASE_URL` | Final answer extraction model API address |
| `FINAL_ANSWER_LLM_MODEL_NAME` | `$OPENROUTER_MODEL_NAME` | Final answer extraction model name |

## Integration with AgentCompass

### Integration Architecture

```
AgentCompass Gateway (8001)
    ↓ (Task Scheduling)
MiroFlow Service (8082)
    ↓ (Main Model Calls)
AgentCompass Gateway (8001)
    ↓ (Tool Model Calls)
Various APIs (OpenRouter, Serper, Jina, E2B, etc.)
```

### Integration Steps

#### 1. Start MiroFlow Service

```bash
python miroflow_service_fastapi.py --host 0.0.0.0 --port 8082 --workers 4
```

#### 2. Call via AgentCompass

Use AgentCompass batch API to call MiroFlow service:

```bash
curl -X POST "http://localhost:8001/api/tasks/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "benchmark": "gaia",
    "models": ["gpt-4o"],
    "params": {
      "benchmark_params": {
        "judge_model": "gpt-4o-mini",
        "category": "1",
        "max_concurrency": 4,
        "k": 1,
        "avgk": false,
        "service_url": "http://localhost:8082/api/tasks",
        "service_protocol": "wait",
        "request_timeout": 3600,
        "service_env_params": {
          "OPENROUTER_API_KEY": "your-key",
          "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
          "SERPER_API_KEY": "your-key",
          "JINA_API_KEY": "your-key",
          "E2B_API_KEY": "your-key"
        }
      },
      "model_infer_params": {
        "temperature": 0.6,
        "top_p": 0.95
      }
    }
  }'
```

**Key Parameters:**
- `service_url`: MiroFlow service address
- `service_protocol`: Use "wait" protocol (synchronous waiting for results)
- `service_env_params`: Tool API configuration passed to MiroFlow

## Performance Optimization

### 1. Worker Configuration

Adjust worker count based on server CPU cores and concurrency requirements:

```bash
# 4-core server: recommend 4-8 workers
python miroflow_service_fastapi.py --host 0.0.0.0 --port 8082 --workers 4

# 8-core server: recommend 8-16 workers
python miroflow_service_fastapi.py --host 0.0.0.0 --port 8082 --workers 8
```

**Recommendations:**
- Development/debugging: Use 1 worker for easier log viewing
- Production: Use 1-2x the number of CPU cores

### 2. Timeout Configuration

For complex tasks, increase timeout appropriately:

```json
{
  "llm_config": {
    "request_timeout": 7200
  }
}
```

**Recommendations:**
- Simple tasks: 1800 seconds (30 minutes)
- Complex tasks: 3600-7200 seconds (1-2 hours)

## Technical Architecture

### Model Configuration

**Main Model (Main Agent):**
- Configured via `llm_config`
- Uses `AgentCompassClient` to call AgentCompass Gateway
- Supports `model_infer_params` (temperature, top_p, etc.)
- Token usage statistics returned in `call_stat`

**Tool Models:**
- Configured via `service_env_params`
- Includes: Hint generation, final answer extraction, reasoning tools, vision tools, audio tools, etc.
- Not included in `call_stat` statistics

### Execution Flow

1. Receive task request (`POST /api/tasks`)
2. Validate `llm_config` and `service_env_params`
3. Build Hydra configuration overrides
4. Initialize MiroFlow Pipeline
5. Execute task (asynchronously)
6. Extract trajectory and token statistics
7. Return results

## License

Apache-2.0 License
