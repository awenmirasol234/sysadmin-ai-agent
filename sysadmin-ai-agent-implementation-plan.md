# SysAdmin AI Agent --- Complete Implementation Plan

> **Project:** SysAdmin AI Agent\
> **Type:** Agentic AI / DevOps\
> **Target platform:** Ubuntu Server 24.04 LTS\
> **Evaluation format:** Live presentation & walkthrough\
> **Primary stack:** Python, LangGraph, Multi-Provider LLM (OpenAI,
> Anthropic, Gemini, Ollama, OpenAI-compatible), FastAPI, Streamlit,
> Docker SDK, psutil

------------------------------------------------------------------------

## 1. Project Definition

### 1.1 Project Objective

Develop an AI-powered system administration assistant capable of
monitoring an Ubuntu server, identifying system problems, investigating
their causes, recommending solutions, and performing approved
maintenance operations.

The application uses a Large Language Model (LLM) as its reasoning
engine and connects to actual server management tools.

Instead of manually running commands and interpreting their output,
administrators can communicate with the AI using natural language.

### 1.2 Problem Statement

Traditional server administration requires administrators to:

-   Manually check CPU, memory, and disk usage.
-   Monitor running services and Docker containers.
-   Inspect logs to identify errors.
-   Troubleshoot unexpected service failures.
-   Execute maintenance commands.
-   Verify whether a solution worked.

This can be time-consuming, especially when managing multiple services.

The proposed system simplifies these activities through an AI agent that
can independently investigate issues and execute controlled operations
with human authorization.

### 1.3 Project Objectives

1.  Monitor Ubuntu server health using actual system information.
2.  Monitor Docker containers and their resource usage.
3.  Analyze system and container logs.
4.  Detect common server and container problems.
5.  Use an LLM to reason about collected information.
6.  Dynamically select tools based on the investigation.
7.  Require human approval before executing changes.
8.  Verify whether executed actions resolved the issue.
9.  Maintain an activity and incident history.
10. Provide a simple dashboard for interacting with the agent.

### 1.4 Project Scope

**Included in the first version:**

-   Single Ubuntu server.
-   CPU, RAM, disk, and uptime monitoring.
-   Docker container monitoring.
-   Basic log analysis.
-   AI-based troubleshooting.
-   Container start, stop, and restart.
-   Selected system service restart.
-   Human approval.
-   Action verification.
-   Incident and activity history.

**Not included in the first version:**

-   Multi-server management.
-   Automatic security patching.
-   Firewall configuration changes.
-   Automatic OS upgrades.
-   Kubernetes management.
-   Unrestricted terminal access.
-   Autonomous destructive maintenance.

These can be future extensions, but they should not distract from the
first working release.

------------------------------------------------------------------------

## 2. System Architecture

### 2.1 High-Level Architecture

The system consists of four main layers, containerized into modular Docker images orchestrated via Docker Compose:

1.  **Presentation layer:** Streamlit dashboard container (`sysadmin-dashboard`).
2.  **Application & Agent layer:** FastAPI backend container (`sysadmin-backend`) packaging LangGraph, Multi-LLM Factory, and SQLite storage.
3.  **Local LLM layer (Optional):** Ollama container (`sysadmin-ollama`) for 100% offline, private model execution.
4.  **Infrastructure & Target layer:** Host Ubuntu server (monitored via mounted `/proc` and `/sys`), host Docker engine (connected via `/var/run/docker.sock`), and target workload containers.

``` mermaid
flowchart TB
    USER[Administrator Browser]

    subgraph COMPOSE[Docker Compose Stack]
        subgraph PRESENTATION["Presentation Container (:8501)"]
            UI[Streamlit Dashboard]
            SETTINGS_UI[Provider & Plugin UI]
        end

        subgraph APPLICATION["Backend Agent Container (:8000)"]
            API[FastAPI REST API]
            DB[(SQLite Database)]
            LG[LangGraph Workflow]
            FACTORY[LLM Provider Factory]
            STATE[Agent State]
            APPROVAL[Human Approval Gate]
            PLUGINS[Plugin Loader /app/plugins]
        end

        subgraph LOCAL_LLM["Optional Local LLM Container (:11434)"]
            OLLAMA[Ollama Llama 3.1 / Qwen 2.5]
        end
    end

    subgraph CLOUD_MODELS[Cloud LLM Providers]
        CLOUD[OpenAI / Anthropic / Gemini / Groq]
    end

    subgraph HOST_INFRA[Host Server Infrastructure]
        UBUNTU[Host Server Filesystem /proc, /sys]
        DOCKER_ENGINE[Host Docker Daemon /var/run/docker.sock]
        WORKLOADS[Monitored Workload Containers]
        SERVICES[System Services]
    end

    USER <-->|HTTP :8501| UI
    UI <-->|Internal Network| API
    API <--> DB
    API --> LG
    LG <--> FACTORY
    FACTORY -.->|Local Network| OLLAMA
    FACTORY -.->|HTTPS API| CLOUD
    LG <--> STATE
    LG --> APPROVAL
    APPROVAL --> API
    LG --> PLUGINS

    APPLICATION -->|Mount /var/run/docker.sock| DOCKER_ENGINE
    APPLICATION -->|Mount /proc, /sys :ro| UBUNTU
    DOCKER_ENGINE -.-> WORKLOADS
```

### 2.2 Component Responsibilities

  Component            Responsibility
  -------------------- -------------------------------------------------------------------
  Streamlit            Dashboard, chat, approval, model provider & plugin interface
  FastAPI              API endpoints, background task queue, and application coordination
  LangGraph            Agent workflow, state machine, and investigation control flow
  LLM Factory          Provider-agnostic LLM reasoning & tool calls (Cloud & Local)
  Plugin Engine        Dynamic hot-mounting of custom system management tools
  System tools         Collect host metrics via mounted procfs (`/host/proc`)
  Docker SDK           Inspect, monitor, and manage containers via host Docker socket
  Log analyzer         Retrieve and interpret container & system logs
  Approval manager     Validate human authorization tokens and prevent replay attacks
  SQLite               Store incidents, tasks, executions, and audit history

### 2.3 Agent Execution Cycle

The agent must follow this cycle:

1.  **Receive task:** Understand the administrator's request.
2.  **Plan investigation:** Identify what information is needed.
3.  **Select tools:** Choose monitoring, Docker, or log tools.
4.  **Collect observations:** Execute tools and receive real results.
5.  **Analyze findings:** Identify problems and possible causes.
6.  **Decide next step:** Investigate further, finish, or propose an
    action.
7.  **Request approval:** Wait for human authorization before changes.
8.  **Execute action:** Run the approved predefined operation.
9.  **Verify result:** Check whether the operation succeeded.

The workflow should support returning to investigation when verification
fails, subject to a limited retry count. It must never repeatedly
execute an action without authorization.

------------------------------------------------------------------------

## 3. Technology Stack and Dependencies

### 3.1 Backend

  Technology     Purpose
  -------------- ---------------------------
  Python 3.12+   Main programming language
  FastAPI        REST API
  Uvicorn        ASGI server
  Pydantic       Data validation
  SQLAlchemy     Database access
  SQLite         Local database

### 3.2 AI and Agent Framework

  Technology               Purpose
  ------------------------ ----------------------------------------
  LangGraph                Agent workflow orchestration & state machine
  LangChain Core           Tool definitions and unified model interfaces
  LangGraph Checkpointer   Save and resume agent state
  Multi-Provider LLMs:     
  - langchain-openai       OpenAI (GPT-4o, GPT-4o-mini)
  - langchain-anthropic    Anthropic (Claude 3.5 Sonnet, Haiku)
  - langchain-google-genai Google Gemini (Gemini 2.5 Flash, 1.5 Pro)
  - langchain-community    Ollama (Llama 3.1, Qwen 2.5, Mistral)
  - OpenAI-compatible      Groq, DeepSeek, Together AI, vLLM, OpenRouter

Any model capable of function/tool calling can be used. Local models
via Ollama (v0.3+) or cloud models via API keys are supported
interchangeably through the unified factory.

### 3.3 System Integration

  Library      Purpose
  ------------ --------------------------------------
  psutil       CPU, RAM, disk, and uptime
  docker       Docker Engine API
  subprocess   Carefully controlled system commands
  pathlib      File and path management
  logging      Application logs

### 3.4 Frontend

  Technology   Purpose
  ------------ --------------------------------
  Streamlit    Interactive dashboard & model controls
  Plotly       Resource usage charts
  Pandas       Display monitoring information
  Requests     Communicate with FastAPI

### 3.5 Development Environment

-   Visual Studio Code or PyCharm.
-   Ubuntu Server 24.04 LTS (or cross-platform host with Docker).
-   Docker Engine and Docker Compose.
-   Git and GitHub.
-   Postman or Swagger UI.
-   LLM API credentials (OpenAI, Anthropic, Google, or local Ollama).

**Recommended development approach:** Run the application on your
development machine or a dedicated management VM and connect it to a
dedicated Ubuntu test VM. Keep the evaluation server separate from
important production services.

### 3.6 Containerized Deployment & Docker Compose Architecture

The entire technology stack is containerized for seamless deployment and zero-configuration environment setup:

- **`sysadmin-backend` Image (`Dockerfile.backend`):**
  Packages Python 3.12, FastAPI, LangGraph, and the multi-provider LLM factory.
  Mounts `/var/run/docker.sock` to manage containers, and `/proc:/host/proc:ro` to inspect host metrics.
- **`sysadmin-dashboard` Image (`Dockerfile.dashboard`):**
  Packages Streamlit, Plotly, and pandas for UI interaction.
- **`ollama` Service (Optional Profile `local-llm`):**
  Runs an Ollama container (`ollama/ollama:latest`) for local model execution without requiring cloud API keys.

The complete system boots with a single command:
``` bash
docker compose up -d
```
Or with local Ollama LLM:
``` bash
docker compose --profile local-llm up -d
```

------------------------------------------------------------------------

## 4. Detailed Functional Requirements

The application is divided into seven functional modules.

### Module 1 --- Server Monitoring

**Purpose:** Collect real-time information about the Ubuntu server.

Required functions:

  Function                 Description
  ------------------------ -----------------------------------
  `get_system_metrics()`   CPU and memory utilization
  `get_disk_usage()`       Disk capacity and available space
  `get_system_info()`      Hostname, OS, and architecture
  `get_uptime()`           Server uptime
  `get_network_info()`     Network interfaces and traffic
  `get_load_average()`     System load averages

Example output:

``` json
{
  "hostname": "ubuntu-server-01",
  "cpu_usage": 34.5,
  "memory_usage": 68.2,
  "disk_usage": 72.4,
  "uptime": "5 days, 4 hours",
  "status": "healthy"
}
```

All values must come from actual system measurements, not AI-generated
estimates.

**Acceptance criteria:**

-   Metrics are retrieved successfully.
-   Failed measurements return useful errors.
-   CPU readings use a sampling interval.
-   Dashboard displays the latest readings.
-   The agent can call the monitoring tools.

### Module 2 --- Docker Monitoring

**Purpose:** Inspect and manage Docker containers.

Required functions:

``` python
list_docker_containers()
get_container_details(container_name)
get_container_stats(container_name)
get_container_logs(container_name)
get_container_status(container_name)
```

Container information should include:

-   Container name.
-   Container ID.
-   Image.
-   Status.
-   Created time.
-   CPU usage.
-   Memory usage.
-   Restart count.
-   Exit code where available.

Example:

``` text
Container: nginx
Image: nginx:latest
Status: Exited
Exit Code: 0
Restart Count: 0
```

**Acceptance criteria:**

-   The application can list containers.
-   It identifies running and stopped containers.
-   It retrieves container logs.
-   It handles missing containers.
-   It never invents container information.

### Module 3 --- Log Analysis

**Purpose:** Help the AI investigate system and application errors.

Supported sources:

-   Docker container logs.
-   `journalctl` for system services.
-   Selected application log files.

Required functions:

``` python
get_container_logs(container_name, tail=100)
get_service_logs(service_name, tail=100)
get_system_errors()
```

The log analyzer should:

1.  Retrieve recent logs.
2.  Filter relevant errors and warnings.
3.  Remove sensitive information where appropriate.
4.  Send a limited, sanitized log excerpt to the LLM.
5.  Ask the LLM to explain the findings.

Example:

``` text
[ERROR] Database connection refused
[WARNING] Application retry attempt 3
[ERROR] Failed to initialize application
```

The agent should distinguish between an observed error and a possible
explanation. A log message alone does not prove the root cause.

### Module 4 --- AI Diagnosis

**Purpose:** Turn collected server information into useful findings.

The agent should detect:

  Condition            Example detection
  -------------------- ------------------------------------
  High CPU             CPU above configured threshold
  High memory          Memory above configured threshold
  Low disk space       Disk above configured threshold
  Stopped container    Container not running
  Repeated restarts    Container restart count increasing
  Service failure      Selected service inactive
  Application errors   Relevant error messages in logs

Suggested initial thresholds:

  Metric     Warning   Critical
  -------- --------- ----------
  CPU            70%        90%
  Memory         80%        95%
  Disk           80%        95%

These are configurable baseline thresholds, not universal
production standards.

The agent should produce structured findings:

``` json
{
  "severity": "warning",
  "component": "docker",
  "title": "Container stopped",
  "observation": "nginx is not running",
  "possible_cause": "The container was stopped",
  "recommendation": "Inspect logs and restart if appropriate"
}
```

### Module 5 --- AI Action Management

**Purpose:** Allow the AI to perform controlled operations.

Implement these functions:

``` python
start_container(container_name)
stop_container(container_name)
restart_container(container_name)
restart_service(service_name)
```

Each function must:

1.  Validate the target.
2.  Check its allowlist.
3.  Validate the requested operation.
4.  Require an approved action record.
5.  Execute the operation.
6.  Record the result.

Enforce strict allowlists and permanently protect critical SysAdmin
agent containers (`sysadmin-backend`, `sysadmin-dashboard`, `sysadmin-ollama`).

**Human approval workflow:**

``` mermaid
flowchart TD
    A[AI proposes an action] --> B[Create action request]
    B --> C[Display in dashboard]
    C --> D{User decision}
    D -->|Reject| E[Record rejection]
    D -->|Approve| F[Validate approval token]
    F --> G{Still valid?}
    G -->|No| H[Reject execution]
    G -->|Yes| I[Execute allowlisted tool]
    I --> J[Record execution result]
    J --> K[Verify server state]
    K --> L[Report outcome]
```

Important implementation details:

-   Approval must be tied to a unique action ID.
-   Approval must expire.
-   Changing the proposed action invalidates its previous approval.
-   A user must not be able to approve an arbitrary command.
-   Rejecting an action must leave the server unchanged.

### Module 6 --- Verification

**Purpose:** Ensure the requested action actually worked.

Example:

``` text
Requested action:
Restart nginx

Execution result:
Restart command accepted.

Verification:
Container status checked again.

Actual status:
Running

Final result:
Successfully restarted.
```

Do not equate a successful API response with successful recovery. Verify
the actual state afterward.

For application-level health, optionally add an HTTP health check to
monitored web containers.

### Module 7 --- Activity and Incident History

**Purpose:** Keep a record of what the agent investigated and did.

Store:

-   User request.
-   Agent investigation steps.
-   Tool calls.
-   Tool outputs or sanitized summaries.
-   Detected incidents.
-   Proposed actions.
-   Approval decisions.
-   Execution results.
-   Verification results.
-   Timestamps.

Example:

  Time    Activity                 Result
  ------- ------------------------ ------------------
  20:30   System health check      Completed
  20:31   Docker inspection        Completed
  20:32   Nginx failure detected   Warning
  20:33   Restart requested        Pending approval
  20:34   Restart approved         Executed
  20:35   Recovery verification    Successful

------------------------------------------------------------------------

## 5. AI Agent Design and Implementation

This is the core of the project.

### 5.1 Agent Responsibilities

The LLM should be responsible for:

-   Understanding natural-language requests.
-   Determining what information is needed.
-   Selecting appropriate tools.
-   Interpreting tool results.
-   Deciding whether additional investigation is needed.
-   Preparing recommended actions.
-   Summarizing results.

The LLM should **not** directly execute unrestricted operating system
commands.

### 5.2 LangGraph State Design

Define a shared state object for each investigation.

``` python
class AgentState(TypedDict):
    user_request: str
    messages: list
    observations: list
    findings: list
    proposed_actions: list
    approval_status: str
    execution_results: list
    verification_results: list
    final_report: str
```

This state allows the agent to maintain its investigation context
between steps.

### 5.3 LangGraph Nodes

Implement the following nodes:

  Node                   Responsibility
  ---------------------- ----------------------------------------
  `understand_request`   Understand user intent
  `plan_investigation`   Create an investigation plan
  `execute_tools`        Invoke read-only tools
  `analyze_results`      Interpret observations
  `decide_next_step`     Continue, finish, or propose an action
  `request_approval`     Pause for human approval
  `execute_action`       Run an approved operation
  `verify_action`        Confirm the outcome
  `generate_report`      Create final response

The graph should use conditional edges so the AI can choose different
investigation paths.

### 5.4 Agent Workflow Examples

**Scenario A: General health check**

``` text
User Request
    ↓
Understand Request
    ↓
Collect System Metrics
    ↓
Inspect Docker Containers
    ↓
Analyze Findings
    ↓
Generate Health Report
    ↓
Completed
```

**Scenario B: Troubleshooting**

``` text
User Request
    ↓
Identify Target
    ↓
Inspect Container Status
    ↓
Inspect Logs
    ↓
Analyze Problem
    ↓
Propose Action
    ↓
Wait for Approval
    ↓
Execute Action
    ↓
Verify Result
    ↓
Generate Report
```

### 5.5 Agent Instructions

Create a dedicated system prompt.

``` text
You are SysAdmin AI, an AI-powered Ubuntu server
administration assistant.

Your responsibilities:
1. Monitor server health.
2. Investigate Docker containers.
3. Analyze system and application logs.
4. Identify possible problems.
5. Recommend appropriate solutions.
6. Execute approved maintenance actions.
7. Verify the results.

Rules:
- Always use actual system tools to collect information.
- Never invent server metrics or tool results.
- Investigate before recommending a solution.
- Clearly distinguish observed facts from possible causes.
- Use read-only tools freely within their permissions.
- Never execute an action without explicit approval.
- Only use predefined and allowlisted action tools.
- Never execute arbitrary shell commands.
- Never bypass security restrictions.
- Verify every executed action.
- Report failures honestly.
- Stop when the task is completed or cannot safely proceed.

Communicate using clear and simple language.

When reporting a problem, include:
- What happened
- What evidence was found
- Possible cause
- Recommended solution
- Whether user approval is required
- Verification result
```

### 5.6 LLM Provider Factory Pattern

To prevent provider lock-in and enable deployment on any cloud or
air-gapped local server, the agent relies on a unified LLM Factory
(`backend/agent/llm.py`).

``` python
def get_chat_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    ...
```

The factory:
1. Dynamically selects between `ChatOpenAI`, `ChatAnthropic`,
   `ChatGoogleGenerativeAI`, `ChatOllama`, or standard OpenAI-compatible
   endpoints based on configuration (`LLM_PROVIDER`).
2. Configures strict zero-temperature execution by default to ensure
   factual, deterministic system administration decisions.
3. Automatically binds read-only monitoring and action-proposal tools
   using LangChain's uniform `.bind_tools()` interface.
4. Validates model tool-calling capabilities during startup or provider
   switching.

### 5.7 Plugin & Technology Integration Architecture

To allow seamless addition of new technologies (databases, caches, web
servers, custom monitoring sidecars) without modifying core agent code,
the system implements a container-centric **Plugin Architecture**:

1. **Dockerized Target Technologies:**
   Any technology running as a Docker container (e.g. MySQL, MongoDB,
   RabbitMQ, Kafka, Kubernetes kind node) automatically becomes
   discoverable and manageable through the agent's Docker SDK tools by
   adding its container name to `ALLOWED_CONTAINERS`.

2. **Hot-Mountable Tool Plugins (`backend/plugins/`):**
   Custom Python inspection tools can be dropped into the
   `backend/plugins/` directory (mounted into the container at
   `/app/plugins`). On startup, the backend automatically imports any
   tool decorated with `@sysadmin_plugin` and registers it in the
   LangGraph agent's tool catalog.

3. **Decoupled Architecture:**
   Core agent reasoning remains decoupled from specific technology
   implementations, allowing sysadmins to plug in enterprise-specific
   monitoring probes with zero code changes to the agent workflow.

------------------------------------------------------------------------

## 6. API Design

FastAPI will connect the frontend to the agent and its supporting
services.

### 6.1 API Endpoints

  Method   Endpoint                               Purpose
  -------- -------------------------------------- ---------------------------
  GET      `/api/health`                          Backend health
  GET      `/api/system/metrics`                  Server metrics
  GET      `/api/system/info`                     Server information
  GET      `/api/docker/containers`               List containers
  GET      `/api/docker/containers/{name}`        Container details
  GET      `/api/docker/containers/{name}/logs`   Container logs
  POST     `/api/agent/chat`                      Submit an agent task
  GET      `/api/agent/tasks/{id}`                Retrieve task status
  GET      `/api/agent/tasks/{id}/events`         Retrieve agent activity
  GET      `/api/approvals`                       List pending approvals
  POST     `/api/approvals/{id}/approve`          Approve action
  POST     `/api/approvals/{id}/reject`           Reject action
  GET      `/api/history`                         Retrieve activity history

### 6.2 Example Request

`POST /api/agent/chat`

``` json
{
  "message": "Check my server and find stopped containers"
}
```

Example response:

``` json
{
  "task_id": "task-001",
  "status": "running",
  "message": "Starting server investigation"
}
```

### 6.3 Example Approval Request

`POST /api/approvals/{id}/approve`

``` json
{
  "decision": "approve"
}
```

The backend must verify that the action is still valid and pending
before executing it.

For the initial release, implement task polling first. Add Server-Sent Events
(SSE) for real-time activity updates after the main workflow works.

------------------------------------------------------------------------

## 7. Database Design

SQLite is sufficient for this single-server deployment.

### Proposed Tables

**1. `agent_tasks`**

  Field          Description
  -------------- ----------------------------
  id             Task ID
  user_request   Original instruction
  status         Running, completed, failed
  started_at     Start time
  completed_at   Completion time
  final_report   Agent report

**2. `agent_events`**

  Field         Description
  ------------- ----------------------------------
  id            Event ID
  task_id       Associated task
  event_type    Tool call, observation, decision
  description   Event summary
  created_at    Event timestamp

**3. `incidents`**

  Field         Description
  ------------- ---------------------------
  id            Incident ID
  task_id       Related task
  severity      Info, warning, critical
  component     System, Docker, service
  title         Problem title
  description   Evidence and details
  status        Open, resolved, dismissed

**4. `action_approvals`**

  Field            Description
  ---------------- --------------------------------------
  id               Action ID
  task_id          Related task
  action_type      Restart, start, stop
  target           Container or service
  arguments_hash   Approved action fingerprint
  status           Pending, approved, rejected, expired
  approved_at      Approval timestamp

**5. `action_executions`**

  Field          Description
  -------------- ---------------------
  id             Execution ID
  approval_id    Related approval
  result         Execution result
  success        Boolean
  executed_at    Execution timestamp
  verification   Verification result

Keep sensitive credentials and raw secrets out of database logs and LLM
prompts.

------------------------------------------------------------------------

## 8. Frontend Implementation Plan

The dashboard should be clean, minimalist, and focused on operational
information.

### 8.1 Dashboard Pages

**Page 1 --- Overview**

-   Server health.
-   CPU, memory, and disk usage.
-   Uptime.
-   Recent incidents.

**Page 2 --- Containers**

-   Container inventory.
-   Status.
-   Resource consumption.
-   Logs.
-   Available actions.

**Page 3 --- AI Assistant**

-   Natural-language requests.
-   Investigation progress.
-   Findings.
-   Final reports.

**Page 4 --- Approvals**

-   Pending actions.
-   Proposed operations.
-   Reasons.
-   Approval and rejection controls.

**Page 5 --- Activity History**

-   Investigation history.
-   Tool executions.
-   Incidents.
-   Verification results.

**Page 6 --- Settings & Model Provider**

-   Active LLM provider & model display.
-   Provider connection testing & validation.
-   In-UI model switching (OpenAI, Anthropic, Gemini, Ollama, Custom URL).
-   Threshold configuration review.

### 8.2 Frontend Requirements

-   Use consistent status indicators.
-   Keep metric cards simple.
-   Display actual server data.
-   Show loading and error states.
-   Display agent activity in chronological order.
-   Highlight pending approval requests.
-   Prevent duplicate approval submissions.
-   Show execution and verification results separately.

------------------------------------------------------------------------

## 9. Security and Permission Architecture

This deserves special attention because an AI system administrator can
potentially affect an entire server.

### 9.1 Permission Levels

  -----------------------------------------------------------------------
  Level                   Permissions             Approval
  ----------------------- ----------------------- -----------------------
  Level 1                 Read server information No

  Level 2                 Inspect logs and        No
                          containers              

  Level 3                 Start, stop, restart    Yes
                          containers              

  Level 4                 Restart selected        Yes
                          services                

  Level 5                 Delete files, modify    Disabled in MVP
                          firewall, upgrade OS    
  -----------------------------------------------------------------------

### 9.2 Security Requirements

1.  Do not expose the Docker socket to an untrusted public-facing
    application.
2.  Do not run the application as root by default.
3.  Understand that membership in the Docker group effectively grants
    root-level privileges on a conventional Docker installation.
4.  Use a dedicated disposable VM for evaluation.
5.  Use an allowlist for every management operation.
6.  Never expose unrestricted shell execution to the LLM.
7.  Validate container names and service names.
8.  Require authentication for dashboard access.
9.  Protect API endpoints against unauthorized approval requests.
10. Store all LLM credentials and API keys in environment variables
    (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`,
    `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).
11. Never send private keys, passwords, or unnecessary sensitive logs to
    the LLM.
12. Record every privileged operation.
13. Mount host filesystems (`/proc`, `/sys`) strictly with read-only
    (`:ro`) flags to prevent containerized processes from modifying host
    kernel state.
14. Isolate internal backend communications via Docker bridge network
    (`sysadmin-net`), exposing only required ports.

**Recommended setup:** Use a dedicated Ubuntu test VM with only
disposable Docker workloads. Run the backend with the minimum
permissions required, and isolate the privileged action executor behind
a narrow, authenticated interface.

For initial testing, do not connect this system to a school server or a
production machine.

------------------------------------------------------------------------

## 10. Development Phases and Task Breakdown

Each phase has a specific deliverable and completion criteria.

### Phase 0 --- Environment Preparation & Containerization

-   [ ] Create Ubuntu 24.04 test VM (or development environment with Docker).
-   [ ] Install Python and Git.
-   [ ] Install Docker Engine and Docker Compose.
-   [ ] Create root Docker build definitions (`Dockerfile.backend`, `Dockerfile.dashboard`).
-   [ ] Create master `docker-compose.yml` (with core and local-llm profiles).
-   [ ] Configure LLM provider credentials (`.env`).
-   [ ] Create GitHub repository.
-   [ ] Set up Python virtual environment.

**Completion:** Development environment and container definitions are ready.

### Phase 1 --- System Monitoring

-   [ ] Implement host-aware CPU & memory monitoring (`backend/tools/system.py`).
-   [ ] Implement disk usage & uptime monitoring.
-   [ ] Implement Docker container listing (`backend/tools/docker_tools.py`).
-   [ ] Implement container details, statistics, and log retrieval.
-   [ ] Add unit tests (`tests/test_system.py`, `tests/test_docker.py`).

**Completion:** Python can retrieve actual Ubuntu and Docker information without AI.

### Phase 2 --- AI Agent Development & Multi-LLM Factory

-   [ ] Implement multi-provider LLM Factory (`backend/agent/llm.py`).
-   [ ] Support OpenAI, Anthropic, Gemini, Ollama, and OpenAI-compatible endpoints.
-   [ ] Define agent state (`backend/agent/state.py`).
-   [ ] Create system prompt (`backend/agent/prompts.py`).
-   [ ] Register read-only tools with `.bind_tools()`.
-   [ ] Create LangGraph nodes (`backend/agent/nodes.py`).
-   [ ] Configure conditional routing & compiled graph (`backend/agent/graph.py`).
-   [ ] Implement tool calling & provider probe tests (`tests/test_llm.py`).
-   [ ] Implement terminal agent CLI runner (`backend/cli.py`).

**Completion:** AI can independently choose tools and investigate server
conditions across any configured LLM provider.

### Phase 3 --- Diagnosis and Reporting

-   [ ] Implement static threshold helpers in `backend/tools/system.py`.
-   [ ] Detect stopped containers and increasing restart counts.
-   [ ] Identify relevant log error excerpts.
-   [ ] Generate structured incidents via LLM `analyze_results` node.
-   [ ] Add severity classification and concise evidence reporting.

**Completion:** AI can identify problems using actual evidence and explain its findings.

### Phase 4 --- Human Approval and Actions

-   [ ] Implement cohesive action & security module (`backend/tools/actions.py`).
-   [ ] Implement target allowlist verification.
-   [ ] Implement approval record creation and token hashing.
-   [ ] Implement approval expiration & single-use replay prevention.
-   [ ] Implement container restart, start, and stop.
-   [ ] Verify operation results post-execution.
-   [ ] Add action & security tests (`tests/test_actions.py`).

**Completion:** AI can execute authorized operations and verify their results safely.

### Phase 5 --- FastAPI Backend & SQLite

-   [ ] Consolidate database schema & audit queries in `backend/db.py`.
-   [ ] Implement FastAPI endpoints (`backend/main.py`).
-   [ ] Implement system metrics and Docker routes.
-   [ ] Implement agent task background worker and polling endpoints.
-   [ ] Implement approval endpoints (`/api/approvals/{id}/approve`, `/reject`).
-   [ ] Implement activity & audit history endpoints.
-   [ ] Add API error handling and input validation.

**Completion:** All backend modules communicate through REST APIs.

### Phase 6 --- Streamlit Dashboard

-   [ ] Implement API client wrapper (`dashboard/api_client.py`).
-   [ ] Implement multi-tab dashboard (`dashboard/app.py`).
-   [ ] Tab 1: Overview (system health cards, gauges, recent incidents).
-   [ ] Tab 2: Containers (container inventory, resource stats, logs).
-   [ ] Tab 3: AI Assistant (chat interface & live investigation trace).
-   [ ] Tab 4: Approvals (pending action cards with Approve/Reject).
-   [ ] Tab 5: Activity History (searchable audit trail).
-   [ ] Tab 6: Settings & Model Management (active provider & connection test).

**Completion:** User can monitor, investigate, approve actions, and configure models through the dashboard.

### Phase 7 --- Testing and Refinement

-   [ ] Test normal server operation.
-   [ ] Test stopped containers.
-   [ ] Test high disk usage in a controlled environment.
-   [ ] Test missing containers.
-   [ ] Test Docker connection failure.
-   [ ] Test approval rejection.
-   [ ] Test expired approval.
-   [ ] Test action execution failure.
-   [ ] Test successful recovery.
-   [ ] Test verification failure.
-   [ ] Check activity and audit records.

**Completion:** Main workflows pass their tests and failure conditions
are handled safely.

### Phase 8 --- Deployment and Presentation

-   [ ] Configure environment variables.
-   [ ] Prepare application startup.
-   [ ] Prepare Docker test environment.
-   [ ] Create evaluation scenarios.
-   [ ] Prepare presentation slides.
-   [ ] Write README documentation.
-   [ ] Rehearse 10--15-minute presentation.
-   [ ] Prepare fallback walkthrough screenshots and recorded output.

**Completion:** Working application is ready for a live classroom
presentation.

------------------------------------------------------------------------

## 11. Testing Strategy

Do not just test whether the AI responds correctly. Test whether the
entire system behaves correctly.

### 11.1 Functional Test Cases

  Test                            Expected result
  ------------------------------- ------------------------------
  Request server health check     Actual metrics returned
  Request container list          Actual containers displayed
  Stop Nginx container            Agent detects stopped state
  Request log investigation       Relevant logs retrieved
  Request restart                 Approval requested
  Reject restart                  Container remains stopped
  Approve restart                 Container restart attempted
  Verify restart                  Actual running state checked
  Restart nonexistent container   Error handled safely
  Docker unavailable              Agent reports tool failure

### 11.2 Important Security Tests

-   Attempt to pass an unapproved container name.
-   Attempt to approve an expired request.
-   Attempt to execute the same approval twice.
-   Attempt to modify an action after approval.
-   Attempt to request arbitrary shell execution.
-   Attempt to approve another user's action.

All these tests should either reject the operation or handle it safely.

### 11.3 Definition of Done

The MVP is complete when:

-   [ ] The dashboard retrieves live server metrics.
-   [ ] The agent can use at least three different read-only tools.
-   [ ] The agent can investigate a stopped container.
-   [ ] The agent provides evidence-based findings.
-   [ ] The agent proposes an appropriate action.
-   [ ] The user can approve or reject the action.
-   [ ] The system executes only an approved action.
-   [ ] The agent verifies the result.
-   [ ] The operation is recorded in history.
-   [ ] No unrestricted command execution is possible.

------------------------------------------------------------------------

## 12. Suggested Development Timeline

For a focused solo development project, allocate approximately three
weeks.

  Phase                              Estimated effort
  ------------------------- -------------------------
  Environment preparation                       1 day
  Monitoring tools                             2 days
  AI agent                                     3 days
  Diagnosis                                    2 days
  Approval and actions                         2 days
  API and database                             2 days
  Dashboard                                    2 days
  Testing and evaluation                        1 day
  **Total**                   **15 development days**

  -----------------------------------------------------------------------
  Week                    Main focus              Expected result
  ----------------------- ----------------------- -----------------------
  Week 1                  Environment,            Working terminal agent
                          monitoring, AI agent    

  Week 2                  Diagnosis, approval,    Working troubleshooting
                          actions, API            workflow

  Week 3                  Dashboard, testing,     Presentation-ready
                          documentation           application
  -----------------------------------------------------------------------

This is a target schedule, not a guarantee. Allow extra time if you are
new to LangGraph or Docker permissions.

------------------------------------------------------------------------

## 13. Live Presentation Script

Prepare the following presentation sequence.

  -----------------------------------------------------------------------
  Time                    Activity                What to present
  ----------------------- ----------------------- -----------------------
  0:00--1:00              Introduction            Explain the problem and
                                                  project

  1:00--3:00              Health check            Live metrics and Docker
                                                  inspection

  3:00--4:00              Introduce failure       Stop Nginx test
                                                  container

  4:00--7:00              Investigation           AI identifies and
                                                  investigates the
                                                  problem

  7:00--9:00              Approval                Show proposed action
                                                  and approval

  9:00--11:00             Recovery                Restart and verify the
                                                  container

  11:00--13:00            Technical explanation   Explain LLM, tools, and
                                                  LangGraph

  13:00--15:00            Conclusion              Discuss benefits and
                                                  limitations
  -----------------------------------------------------------------------

### 13.1 Environment Preparation

Prepare three disposable Docker containers:

-   `nginx` --- web server.
-   `redis` --- cache server.
-   `postgres` --- database server.

Use test data only. Before the presentation, stop the Nginx container:

``` bash
docker stop nginx
```

### 13.2 Presentation Sequence

**Act 1 --- Introduce the AI (1 minute)**

Explain:

> This is an AI-powered system administrator. Instead of manually
> checking every server component, I can give it a task and it will
> investigate the server using actual system tools.

**Act 2 --- Health Check (2 minutes)**

Ask:

> Perform a complete health check of my Ubuntu server. Check CPU,
> memory, disk usage, and Docker containers.

Show the agent:

-   Planning its investigation.
-   Calling monitoring tools.
-   Collecting actual system metrics.
-   Generating a health report.

**Act 3 --- Introduce a Problem (1 minute)**

Stop the disposable Nginx container.

Explain:

> I intentionally introduced a problem. Let's see whether the AI can
> identify it.

**Act 4 --- AI Investigation (3 minutes)**

Ask:

> Investigate my Docker containers. Find the problem, inspect the logs,
> identify the cause, and recommend a solution.

The agent should:

1.  List all containers.
2.  Detect the stopped Nginx container.
3.  Inspect its available logs and state.
4.  Explain that it is stopped.
5.  Recommend restarting it.

**Act 5 --- Human Approval (2 minutes)**

The agent asks:

> I found that nginx is stopped. Would you like me to restart it?

Click **Approve**.

The agent executes the predefined restart operation.

You can also reject an action to show that the agent
respects human decisions.

**Act 6 --- Verify Recovery (2 minutes)**

Ask the agent to verify the result.

Expected result:

``` text
Investigation completed.

Problem:
nginx was stopped.

Action:
Restart approved by user.

Verification:
Container is now running.

Result:
Recovery successful.
```

**Act 7 --- Explain the Technology (1--2 minutes)**

Explain how the LLM, LangGraph, Python tools, Docker API, and human
approval work together.

*Timing: approximately 12--13 minutes, including the introduction and
closing explanation.*

------------------------------------------------------------------------

## 14. What Makes This Genuinely Agentic AI?

This is an important distinction to explain during your presentation.

  Traditional AI chatbot          Agentic AI System Administrator
  ------------------------------- -----------------------------------------------------
  Answers questions               Works toward a goal
  Waits for every instruction     Plans multiple steps
  Provides suggested commands     Calls actual tools
  Cannot verify execution         Checks the results
  Relies on user for every step   Can execute approved tasks
  Responds once                   Can repeat investigation until the task is complete

The core agent cycle is:

1.  **Perceive:** Collect server information.
2.  **Reason:** Analyze and diagnose problems.
3.  **Plan:** Select the appropriate tools and actions.
4.  **Act:** Execute approved operations.
5.  **Verify:** Check results and complete the task.

Repeat the cycle if the problem remains unresolved, within configured
limits.

------------------------------------------------------------------------

## 15. Project Structure

Keep the code modular so each component is easy to understand, test, and
explain.

``` text
sysadmin-ai-agent/
│
├── backend/
│   ├── main.py                   # FastAPI REST API & route definitions
│   ├── config.py                 # Settings (env vars, thresholds, allowlist)
│   ├── db.py                     # SQLite engine, models & audit persistence
│   ├── cli.py                    # Milestone 1 terminal-based agent runner
│   │
│   ├── agent/                    # Core Agentic Reasoning
│   │   ├── llm.py                # Multi-provider LLM factory (OpenAI, Claude, Gemini, Ollama)
│   │   ├── state.py              # TypedDict AgentState definition
│   │   ├── prompts.py            # System prompts & diagnosis guidance
│   │   ├── nodes.py              # LangGraph workflow nodes
│   │   └── graph.py              # Compiled StateGraph with checkpointer
│   │
│   ├── tools/                    # Cohesive System Tools
│   │   ├── system.py             # Host-aware psutil metrics & threshold checks
│   │   ├── docker_tools.py       # Docker SDK container inspect, stats, logs
│   │   └── actions.py            # Allowlist security, approval tokens & action executions
│   │
│   └── plugins/                  # Dynamic custom tool plugins (hot-mountable)
│       └── __init__.py
│
├── dashboard/
│   ├── app.py                    # Streamlit app (Overview, Containers, Chat, Approvals, History, Settings)
│   └── api_client.py             # Clean HTTP client wrapper for backend API
│
├── tests/
│   ├── test_llm.py               # Multi-provider instantiation tests
│   ├── test_system.py            # psutil & host procfs tests
│   ├── test_docker.py            # Docker inspection tests
│   ├── test_actions.py           # Allowlist security & single-use token tests
│   └── test_graph.py             # LangGraph routing & approval gate tests
│
├── Dockerfile.backend            # Lightweight backend container image
├── Dockerfile.dashboard          # Streamlit UI container image
├── docker-compose.yml            # Compose orchestration (core, local-llm)
├── requirements.txt
├── .env.example
├── .gitignore
├── sysadmin-ai-agent-implementation-plan.md
└── README.md
```

------------------------------------------------------------------------

## 16. Expected Project Deliverables

At the end, the project should include:

-   [ ] GitHub source code repository.
-   [ ] Working Streamlit dashboard.
-   [ ] LangGraph-powered AI agent.
-   [ ] Ubuntu monitoring and Docker integration.
-   [ ] Human approval and security controls.
-   [ ] SQLite incident and action history.
-   [ ] README, architecture, and setup documentation.
-   [ ] 10--15-minute presentation and walkthrough script.

------------------------------------------------------------------------

## 17. Recommended Implementation Order

Build the project in this order without skipping ahead:

1.  Make the Python monitoring tools work on Ubuntu.
2.  Connect those tools to an LLM through LangGraph.
3.  Make the agent investigate a stopped Docker container.
4.  Implement human approval and controlled recovery.
5.  Build the FastAPI backend.
6.  Build the Streamlit dashboard.
7.  Test the complete workflow.
8.  Prepare the live presentation and walkthrough.

**The first milestone should be a working terminal-based agent.** Once
it can successfully inspect, diagnose, and recover a test container,
build the dashboard around it.

### First Development Milestone

Your first successful interaction should look like this:

``` text
$ python main.py

SysAdmin AI is ready.

You: Check my Ubuntu server.

Agent: I will investigate your server.

[TOOL] get_system_metrics()
[TOOL] get_disk_usage()
[TOOL] list_docker_containers()

Agent: Investigation completed.

Server Status: HEALTHY

CPU Usage:    34.5%
Memory Usage: 68.2%
Disk Usage:   72.4%

Docker Containers:
Running: 2
Stopped: 1

Finding:
nginx is currently stopped.

Recommendation:
Investigate the container and consider
restarting it if appropriate.
```

*The values above are illustrative expected output, not actual server
measurements.*

### Project Success Criteria

The most important thing is not how many features you build. It is
whether you can verify this complete sequence:

**Natural language → AI reasoning → Tool execution → Problem diagnosis →
Human approval → Action execution → Verification.**

That is the core of the Agentic AI value proposition.

------------------------------------------------------------------------

## 18. Useful Documentation and Resources

-   [LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/overview)
-   [LangChain Models & Tool Calling](https://python.langchain.com/docs/concepts/chat_models/)
-   [OpenAI API Documentation](https://platform.openai.com/docs)
-   [Anthropic Claude API Documentation](https://docs.anthropic.com/)
-   [Google Gemini API Documentation](https://ai.google.dev/docs)
-   [Ollama Local Models Documentation](https://ollama.com/)
-   [FastAPI Documentation](https://fastapi.tiangolo.com/)
-   [Streamlit Documentation](https://docs.streamlit.io/)
-   [Docker SDK for Python](https://docker-py.readthedocs.io/)
-   [psutil Documentation](https://psutil.readthedocs.io/)

------------------------------------------------------------------------

## Final Recommendation

Focus on delivering one complete, reliable agent workflow rather than
many unfinished features.

The most compelling proof is an AI agent that receives a
natural-language request, investigates a real Ubuntu server, detects a
stopped Docker container, proposes a solution, waits for approval,
restarts the container, and verifies that it is running again.

This clearly highlights the difference between a traditional chatbot
and an Agentic AI system.
