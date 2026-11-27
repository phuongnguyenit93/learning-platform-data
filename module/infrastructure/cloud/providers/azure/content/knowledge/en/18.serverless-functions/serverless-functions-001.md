# Function App and Azure Functions Execution Model

> **Chapter:** Serverless with Azure Functions  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control the costs of an application architecture on Azure.

## Lesson Objectives

After this lesson, you will be able to:

1. Distinguish between **Azure Functions**, **Function App**, **function**, **Functions host**, **language worker**, **trigger**, and **binding**.
2. Describe the lifecycle of an invocation from the event source to code execution, output, logging, and retries.
3. Compare hosting plans (**Flex Consumption, Consumption, Premium, Dedicated/App Service Plan**) based on real-world requirements.
4. Explain **scale-out, concurrency, scale-to-zero, cold start, timeout**, and their impact on cost and performance.
5. Write a **Python v2 programming model** project containing HTTP, Queue Storage, and Timer triggers, run it locally, and deploy it following a controlled workflow.
6. Distinguish between `host.json`, `local.settings.json`, application settings, Key Vault, and managed identity.
7. Design **stateless, idempotent** processing with timeouts, retries, and observability.
8. Diagnose triggers not firing, Storage permission errors, HTTP timeouts, duplicate message processing, and missing telemetry.

## 1. What Problem Does Serverless Solve?

An e-commerce application needs to do three things: respond to the `GET /api/hello` API, process new orders in a queue, and generate a scheduled report every hour.

If you manage a web server yourself to continuously poll the queue and run a scheduler, the operations team must manage processes, uptime, and custom scaling logic. **Azure Functions** is a service that runs code in response to **events/triggers**, with the runtime, bindings, and hosting options provided by Azure.

~~~mermaid
flowchart LR
    C["HTTP client"]
    Q["Azure Queue Storage\norders"]
    T["Timer schedule"]
    H["Functions host\ntrigger listeners"]
    A["HTTP function\nhello"]
    B["Queue function\nprocess_order"]
    D["Timer function\nhourly_cleanup"]
    DB["Database / Storage"]
    M["Application Insights"]
    C --> H
    Q --> H
    T --> H
    H --> A
    H --> B
    H --> D
    B --> DB
    D --> DB
    A -.-> M
    B -.-> M
    D -.-> M
~~~

This is a logical flow; it does not mean every trigger receives events through a shared queue. Each trigger type has its own **mechanism for receiving, acknowledging, retrying, and scaling**.

| Requirement | Can use Functions? | Notes |
| --- | --- | --- |
| Small HTTP API or webhook | Yes | Pay attention to authentication, cold start, timeout |
| File/event processing | Yes | Choose the appropriate trigger and event mechanism |
| Async order processing | Yes | Queue + idempotency |
| Periodic aggregation | Yes | Timer trigger and UTC schedule |
| Long-running, multi-step workflow | Consider Durable Functions | Provides state/checkpointing instead of holding an HTTP request open |
| Long-lived stateful WebSocket server | Not by default | Requires a different connection and state architecture |
| Long batch/GPU/highly customized runtime | Evaluate other services | Check host/plan limits |

Serverless **does not mean no servers, no cost, or no operations**. You still have to manage code, access permissions, data, SLOs, and budgets.

## 2. Function, Function App, and Related Resources

### 2.1. A Function Is the Unit of Execution

A **function** is an entrypoint that executes logic when its trigger condition is met. For example, `hello` handles HTTP, `process_order` receives a Queue Storage message, and `hourly_cleanup` runs on a schedule.

**Each function has exactly one trigger**, though it can also use additional input/output bindings or the Azure SDK.

### 2.2. A Function App Is the Application Boundary

A **Function App** is an Azure resource containing multiple functions that share certain configurations and a deployment lifecycle:

~~~text
Resource group: rg-func-lab
Function App:   fn-orders-lab
  - hello
  - process_order
  - hourly_cleanup

Related:
  Storage Account: stfunctionslab001
  Application Insights: appi-func-lab
  Hosting plan: chosen based on requirements
~~~

A Function App typically shares:

- Language/runtime configuration and Functions host version.
- App settings, identity, and connections configured at the app level.
- Deployment package, logging/instrumentation.
- Hosting plan and scaling characteristics by plan/triggers.

If an HTTP API requires tight latency while a queue consumer is CPU-intensive, consider **separate Function Apps** to isolate deployment lifecycles, scaling, permissions, and monitoring. Conversely, grouping functions with similar characteristics reduces the number of resources to operate.

### 2.3. Commonly Confused Terms

| Concept | Meaning |
| --- | --- |
| Function | Code/entrypoint invoked by a trigger |
| Function App | Application resource and unit of deployment/configuration |
| Azure Functions host/runtime | Loads function metadata, manages triggers and bindings, dispatches invocations |
| Language worker | Process running Python/Node.js/.NET isolated code according to the programming model |
| Host instance | A running unit of the Functions host |
| Invocation | A single execution call of a function |
| Hosting plan | How compute, scaling, networking, and billing are provisioned |
| App Service Plan | A compute model for apps; does not mean every Function App uses a Dedicated plan |
| Application Insights | Collects telemetry; not the runtime executing functions |

### 2.4. A Function App Is Not Automatically an Independent Single Function

Publishing a Function App project typically affects **multiple functions** within it. A failing dependency at startup can prevent the entire app from indexing any functions. Split Function Apps when they differ in criticality, deployment velocity, workload, or IAM/egress requirements; avoid over-splitting when there is no benefit.

## 3. How Do the Azure Functions Host and Language Worker Work?

~~~mermaid
flowchart TD
    E["HTTP / Queue / Timer\nevent source"]
    X["Trigger listener / extension"]
    H["Functions host\nmetadata, binding, dispatch"]
    W["Language worker\nPython, .NET, JavaScript..."]
    F["Function code"]
    S["Azure SDK / output binding"]
    O["Logs, metrics, traces"]
    E --> X --> H --> W --> F --> S
    H -.-> O
    F -.-> O
~~~

**High-level lifecycle:**

1. The hosting platform initializes a Functions host instance.
2. The host reads `host.json`, app settings, metadata, and binding extensions.
3. A trigger listener or event source mechanism supplies an eligible event.
4. The host creates an invocation and passes data to the corresponding language worker or execution model.
5. Code executes, calls dependencies, and produces a result.
6. The runtime/extension completes or handles errors according to trigger semantics.
7. Telemetry is recorded when observability is configured.
8. The platform can add or remove host instances based on the plan and load.

### 3.1. Language Worker and Programming Model

Python code typically runs in a **language worker** separate from the host. .NET has different worker/in-process models; you must choose a supported model and runtime. This affects function indexing, dependency loading, concurrency, and how bindings are written.

If package upload succeeds but the portal lists no functions:

- Incorrect folder layout or missing `host.json`.
- Mismatched `FUNCTIONS_WORKER_RUNTIME`.
- Python import or dependency error.
- Missing or incompatible trigger extension.
- Mixing Python programming model v1 and v2 improperly.
- Incompatible runtime/language version.

**A successful deployment does not prove that triggers have been indexed and are actively listening.** Check host startup logs and the function list.

### 3.2. One Instance Can Run Multiple Invocations

~~~text
Function App fn-orders-lab
  Host instance A:
    Invocation #101, #102
  Host instance B:
    Invocation #103, #104
~~~

Each invocation is **not** a new VM. One instance can process multiple invocations concurrently depending on the trigger, language runtime, concurrency settings, and resources. Multiple instances can serve a single Function App at the same time.

Because host instances can be recycled or replaced, **global variables, in-memory state, or temporary directories are not reliable sources of transactional state**.

### 3.3. Execution Varies by Trigger Type

HTTP returns a response to a client. Queue Storage uses visibility timeouts and poison messages. Event Hubs uses partitions and checkpoints. Timer uses a schedule monitor. **Retry, completion, scaling, and ordering guarantees depend on the trigger**; there is no single uniform policy across all of Azure Functions.


## 4. Triggers and Bindings: When Does It Run, What Does It Receive and Write?

### 4.1. A Function Has Only One Trigger

| Trigger | Event source | Scenario |
| --- | --- | --- |
| HTTP | HTTP request | API/webhook |
| Timer | NCRONTAB schedule | Cleanup/reporting |
| Azure Queue Storage | Queue message | Order processing |
| Azure Service Bus | Queue/subscription message | Enterprise messaging |
| Blob Storage | Blob event/change as supported | Thumbnail/OCR |
| Event Grid | Event publisher | Event-driven workflow |
| Event Hubs | Partitioned event stream | Telemetry ingestion |
| Cosmos DB | Change feed | Sync/projection |

Each trigger has its own **retry, completion, payload, and scaling semantics**. Do not attach both an HTTP trigger and a Queue trigger to the same function. You can create two separate functions that share common business logic.

### 4.2. Input/Output Bindings

An **input binding** lets the runtime supply data from a supported service; an **output binding** lets you write results to an extension-supported destination. For complex logic, calling the Azure SDK directly remains an appropriate choice.

~~~mermaid
flowchart LR
    H["create_order\nHTTP trigger"]
    Q["Storage Queue\norders"]
    F["process_order\nQueue trigger"]
    D["SQL / Cosmos DB\nSDK"]
    O["Optional output binding\nStorage / queue"]
    H -->|enqueue| Q --> F --> D
    F --> O
~~~

Bindings do not automatically guarantee an **atomic distributed transaction** between a queue and a database. If the database write succeeds but the function crashes before the message completes, the invocation may repeat; idempotency is required.

### 4.3. Binding Extensions and Connection Names

In Python code, `connection="OrdersStorage"` is a **configuration setting name**, not a secret string. The runtime looks up the `OrdersStorage` application setting or corresponding prefixed settings when using identity-based connections.

You can have:

- `AzureWebJobsStorage`: the host storage connection used for runtime operational needs.
- `OrdersStorage`: a separate connection to the business Queue Storage.

Do not confuse these two roles, nor force the same account across all environments. Always check the extension version, data permissions, and networking.

## 5. HTTP, Queue, and Timer Lifecycles

### 5.1. HTTP

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant P as Functions Frontend
    participant H as Host
    participant W as Worker
    C->>P: GET /api/hello
    P->>H: Route + auth
    H->>W: Invocation
    W-->>H: HttpResponse
    H-->>P: status, headers, body
    P-->>C: HTTP 200
~~~

An HTTP trigger requires input validation, proper HTTP status codes, authentication/authorization, timeouts, logging, and dependency handling. HTTP requests **do not have automatic retry mechanisms like Queue triggers**; clients or gateways may retry depending on configuration, so you must protect idempotency.

Authorization levels typically include:

- `anonymous`: the runtime does not require a function key; the endpoint is not automatically secured.
- `function`: may require a valid function key, which is a shared secret.
- `admin`: broader permissions, unsuitable as a public client key.

Function keys do not replace OAuth/JWT, Microsoft Entra ID, App Service Authentication, or business-level API authorization. Never put function/admin keys in public URLs or client source code.

### 5.2. Queue Trigger and Redelivery

For message `order-123`:

1. The Queue trigger listener retrieves the message.
2. The runtime dispatches an invocation.
3. Code processes the message and updates state.
4. On success, the extension completes/deletes the message per queue semantics.
5. On failure, the message can become visible again after the visibility timeout/retry.
6. After repeated failures, the Storage Queue trigger can move the message to a **poison queue** according to extension/host settings.

Design to be **at-least-once safe**: use `orderId`/message ID as an idempotency key, unique constraint, or state machine; enforce bounded retries and have a process for handling poison messages. Avoid charging payments or sending duplicate notifications when the same message is redelivered.

### 5.3. Timer Trigger

Azure Functions Timer uses a **six-field NCRONTAB** expression:

~~~text
{second} {minute} {hour} {day} {month} {day-of-week}
~~~

| Schedule | Meaning |
| --- | --- |
| `0 */5 * * * *` | Every 5 minutes |
| `0 0 * * * *` | At the top of every hour |
| `0 0 2 * * *` | 02:00 daily in the configured timezone |
| `0 0 9 * * 1-5` | 09:00 Monday–Friday |

The timezone defaults to UTC. Some Linux/serverless plans **do not support changing timezone via `WEBSITE_TIME_ZONE`** the same way some other environments do; prefer keeping UTC, converting schedules, and testing. Timers do not guarantee millisecond-exact execution if the host restarts.

### 5.4. Behavior Comparison

| Aspect | HTTP | Queue | Timer |
| --- | --- | --- | --- |
| Does client wait? | Usually yes | No | No |
| Outcome | HTTP response | Message completion/retry | No HTTP response |
| Retry | Decided by client/app | Extension, visibility/poison | Separate timer/host schedule monitor |
| Input data | Method, headers, body | Message/metadata | Timer info |
| Key design focus | Auth, status, latency | Idempotency, poison handling | Timezone, overlap, monitoring |

### 5.5. Long-Running HTTP Jobs

If processing 10,000 images takes 30 minutes, do not hold an HTTP request open for 30 minutes. **Function timeout and HTTP frontend timeout are two separate limits**; even if `functionTimeout` allows long execution under a plan, the frontend or client may time out earlier.

Asynchronous pattern:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP function
    participant Q as Queue
    participant W as Queue function
    participant DB as Job state store
    C->>H: POST /api/jobs
    H->>DB: Create jobId, status=pending
    H->>Q: Enqueue jobId
    H-->>C: 202 Accepted + status URL
    Q->>W: Dispatch jobId
    W->>DB: Update processing/done/failed
    C->>H: GET /api/jobs/{id}
    H->>DB: Read job status
    H-->>C: Status + result
~~~

You can use the **Durable Functions async HTTP pattern** if you need orchestration, persistence, and replay, though that is a separate workflow you must configure.

## 6. Hosting Plans for Function Apps

Azure Functions supports multiple compute provisioning models. **Regions, runtimes, OSes, versions, quotas, and pricing policies change**, so always verify compatibility before choosing.

| Hosting | Focus | Trade-offs |
| --- | --- | --- |
| **Flex Consumption** | Serverless, flexible scaling and configurable memory/always-ready as supported | Cold start, region/trigger support, billed on execution/always-ready |
| Classic **Consumption** | Serverless capable of scale-to-zero where supported | Runtime/OS/network limits, cold start, superseded by newer options |
| **Elastic Premium** | Prewarmed/always-ready compute, suited for latency and network requirements | Baseline cost, instance/SKU quotas |
| **Dedicated (App Service Plan)** | Provisioned compute for always-running workloads or plans with headroom | Idle cost, tier/Always On and scaling plan |
| **Azure Container Apps hosting** | Functions running on supported container app infrastructure/model | Need to evaluate triggers, ingress, revisions, scaling, and billing |

Do not assume all plans support every language and network configuration equally.

### 6.1. Flex Consumption

This is the serverless option to evaluate for new projects when the region and language are compatible:

- Scales based on trigger load; certain triggers have per-function or grouped scaling capabilities.
- Allows selecting memory/instance capabilities within supported limits.
- **Always-ready instances** when cold starts must be reduced and baseline cost is acceptable.
- VNet integration per plan requirements and conditions.
- Billing follows the Flex model, which can include execution and always-ready resources.

Do not assume Flex runs at "0 instances at all times" if always-ready is configured. Check the specific pricing model.

### 6.2. Classic Consumption

Capable of scale-to-zero and suitable for many existing event-driven workloads. However, you must review feature limits, cold start, timeouts, OS/runtime support, and support lifecycle at the time of selection. Do not copy old tutorials straight into production without checking Flex options.

### 6.3. Elastic Premium

Keeping prewarmed compute in the plan reduces initialization time, which helps APIs needing consistent latency or specific VNet/network configurations. However, it typically carries a **baseline compute cost**, quotas, and instance limits. Premium does not replace dependency optimization.

### 6.4. Dedicated App Service Plan

Compute follows a provisioned plan, suitable when workloads have sustained high load or an existing plan has spare headroom. Review `Always On`, SKU/tier, and sharing compute across multiple apps. Manual/autoscale in this plan differs from serverless scale-to-zero.

### 6.5. Choosing by SLO

- Low HTTP traffic where cold start is acceptable → consider Flex/Consumption depending on support.
- Latency-sensitive API with bursty traffic → compare Flex always-ready with Premium.
- High-peak queue consumer → evaluate event-driven scaling, max instances, and backend quotas.
- Continuously running app with an existing Dedicated plan → compare total cost against serverless.
- Containerized services in a Container Apps architecture → evaluate Functions on ACA where supported.

## 7. Scaling, Concurrency, and Cold Start

### 7.1. Scale-Out Is Not Concurrency

**Scale-out** adds host instances. **Concurrency** is the number of invocations running simultaneously within a single instance/worker depending on the trigger and plan.

~~~text
Low load:
  Host A → 2 invocations

High load:
  Host A → 5 invocations
  Host B → 5 invocations
  Host C → 5 invocations
~~~

Numbers are illustrative only. Concurrency is influenced by CPU, memory, Python async/thread workers, queue batch size, prefetch, and trigger/plan configuration. **There is no guarantee that one invocation requires its own dedicated host instance.**

### 7.2. Estimating with Little's Law

If an application receives 100 invocations/second and each invocation takes an average of 0.2 seconds:

\[
L=\lambda W=100\times0.2=20
\]

There are roughly 20 in-flight invocations in steady state. If one instance safely handles 5 concurrent invocations, the minimum estimate is 4 instances before headroom. This is **not Azure's exact scaling algorithm**; tail latency, bursts, cold starts, and backend behavior also matter.

### 7.3. Cold Start

**Scale-to-zero** reduces compute during idle periods depending on the plan. **Cold start** is the time spent initializing the host, loading the runtime and dependencies, indexing functions, and becoming ready to serve an invocation.

Contributors:

- Oversized packages/dependencies.
- Heavy SDK imports and network connections made at module import time.
- Trigger extensions and host initialization.
- Provisioning resources, secret resolution, and private endpoints.
- Sudden bursts requiring additional instances to spin up.

Evaluate p95/p99 latency including the **first request**. Optimize imports and startup; consider always-ready or Premium when SLOs require it. Do not treat continuous endpoint pinging as a cost-controlled substitute.

### 7.4. Timeouts

`functionTimeout` in `host.json` controls invocation duration within plan limits. Plans have different defaults, maximums, and exceptions; **do not assume a single fixed minute limit across all environments**.

HTTP also has limits at the frontend, load balancer, and client. For long jobs, use queues, Durable Functions, or a batch solution instead of keeping synchronous requests open.

### 7.5. Downstream Bottlenecks

Scaling from 2 to 20 instances can simultaneously multiply SQL connections, Cosmos DB RU/s, Storage requests, and API rate limits. Do not raise max instances before reviewing:

- Backend throughput and latency.
- Connection pooling, retries, and backoff.
- Idempotency when events are retried.
- Compute, networking, and logging costs.

**Scaling out Functions does not automatically increase backend quotas.**


## 8. Self-Contained Example: One Function App with Three Triggers (Python v2)

We will build the `orders-functions` app containing:

- `hello`: HTTP GET `/api/hello`.
- `process_order`: processes messages from Storage Queue `orders`.
- `hourly_cleanup`: logs a periodic check at the top of every hour.

**Purpose:** illustrate the programming model, runtime discovery, and how three triggers coexist in one Function App. The order processing is simulated: it does not perform real payments or database writes.

### 8.1. Project Structure

~~~text
orders-functions/
  function_app.py
  host.json
  requirements.txt
  local.settings.json      # Do not commit secrets/credentials
  .funcignore              # Optional exclusions when publishing
~~~

In the Python **v2 programming model**, decorators in `function_app.py` describe functions and bindings; you do not need to hand-write a `function.json` file for each function like in the older model.

### 8.2. `function_app.py`

~~~python
import json
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="hello", methods=["GET"])
def hello(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger: respond quickly, do not run long jobs."""
    name = req.params.get("name", "there")
    return func.HttpResponse(
        f"Hello, {name}!",
        status_code=200,
        mimetype="text/plain; charset=utf-8",
    )


@app.queue_trigger(
    arg_name="msg",
    queue_name="orders",
    connection="OrdersStorage",
)
def process_order(msg: func.QueueMessage) -> None:
    """Queue trigger: demonstrates reading orderId and logging."""
    try:
        payload = json.loads(msg.get_body().decode("utf-8"))
        order_id = payload["orderId"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        logging.error("Invalid order message")
        raise ValueError("Invalid order message") from exc

    logging.info("Processing order %s", order_id)

    # Real application:
    # 1) Check orderId using a database/unique constraint
    # 2) Only trigger side effects if the order has not been processed yet
    # 3) Write state and telemetry in a controlled manner
    # Do not assume this logging example already implements idempotency.


@app.timer_trigger(
    schedule="0 0 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def hourly_cleanup(timer: func.TimerRequest) -> None:
    """Timer trigger: runs at the top of every hour according to the host timezone."""
    if timer.past_due:
        logging.warning("Hourly task is running late")
    logging.info("Hourly cleanup tick")
~~~

**Explanation:**

- `FunctionApp` is the object used to register functions in Python v2.
- `@app.route` creates an HTTP trigger with the `hello` route.
- `@app.queue_trigger` attaches a Queue Storage trigger; `OrdersStorage` is the **connection setting name**.
- `@app.timer_trigger` runs on a schedule and can inspect `past_due`.
- No HTTP request automatically creates a queue message in this example; they are **three independent trigger sources**.
- The app only calls `logging.info` when a message arrives in the queue; it does not write to a database or implement real idempotency yet.

For production, address input validation, security, data contracts, exception classification, and idempotency before going live.

### 8.3. `requirements.txt`

~~~text
azure-functions
azure-storage-queue
~~~

`azure-functions` powers the runtime programming model; `azure-storage-queue` is used for the test message sender script in section 9. In production projects, **pin versions** according to your lock/dependency policy and test runtime compatibility; do not let dependencies float unpinned.

### 8.4. `host.json`

~~~json
{
  "version": "2.0",
  "functionTimeout": "00:05:00",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  },
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  }
}
~~~

Illustrated fields:

- `version: "2.0"` is the **host.json schema version**, not "Azure Functions runtime v2"; the common runtime for the Python v2 model is Functions v4 as supported.
- `extensionBundle` provides the runtime with compatible binding extensions such as Queue Storage.
- `functionTimeout` must stay within **hosting plan** limits; 5 minutes here is for testing only.
- `samplingSettings` reduces certain telemetry according to configuration. When debugging rare errors, account for sampling so you do not conclude requests are missing from a sampled log set.

### 8.5. `local.settings.json` for Azurite

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "OrdersStorage": "UseDevelopmentStorage=true"
  }
}
~~~

**This is local configuration only**, using the Azure Storage emulator **Azurite**. Before running, start Azurite with the Blob/Queue/Table endpoints required by the host and extensions. Never deploy `UseDevelopmentStorage=true` to Azure production; Azurite is not real Azure Storage.

`local.settings.json` can contain credentials in other projects and is usually excluded from publishing; **do not commit this file to a repository containing secrets**. In Azure, use Function App application settings, Key Vault, and managed identity as appropriate.

### 8.6. Safe Changes to Extend the Example

If you want `hello` to enqueue real work:

1. Create a separate POST endpoint, validate the payload and identity.
2. Generate a `jobId` with an idempotency key; persist initial state.
3. Send a message to the queue using the SDK with appropriate write permissions.
4. Return HTTP `202 Accepted` with the `jobId` and status URL.
5. Have the queue-triggered function process, retry, and update state.

Do not turn `GET /api/hello` into a payment charge or data-mutating action; GET should remain a read operation per HTTP semantics.

## 9. Running Locally: Functions Core Tools and Azurite

### 9.1. Prerequisites

- A Python version supported by the Functions runtime and local Core Tools.
- Compatible **Azure Functions Core Tools v4**.
- A virtual environment with dependencies installed.
- Azurite running so host storage and queue triggers can connect.
- Internet connectivity for the first download of the extension bundle/packages if needed.

Example commands in **Bash/Linux/macOS** once the tools above are installed:

~~~bash
# Inside the orders-functions project directory:
python -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt

# Ensure Azurite is running in another terminal/process.
func start
~~~

On Windows PowerShell, the virtual environment activation command differs from Bash; use the command for your OS. If Core Tools reports a Storage emulator error, check the Azurite endpoint, ports, firewall, and `AzureWebJobsStorage`.

### 9.2. Initialize a New Project Instead of Copying Structure Manually

If starting from scratch, Core Tools supports initializing a Python v2 project depending on your version:

~~~bash
func init orders-functions --worker-runtime python --model V2
~~~

Then add `function_app.py` and sample settings. **Do not run init inside a project directory with files you want to keep** without verifying it will not overwrite them. Use `func init --help` if your Core Tools version expects different syntax.

### 9.3. Testing HTTP

By default, the route prefix is `/api` when unmodified in `host.json`:

~~~bash
curl -i "http://localhost:7071/api/hello?name=Mai"
~~~

Expected HTTP 200 and body:

~~~text
Hello, Mai!
~~~

**The local host may not enforce authorization checks the same way an Azure endpoint does**, depending on Core Tools and configuration. Do not use local test results to conclude a production endpoint is secured.

### 9.4. Sending a Queue Message with the Python SDK

After installing `azure-storage-queue` and starting Azurite, you can run this **demonstration snippet on your lab machine**:

~~~python
import json
from azure.storage.queue import QueueClient

queue = QueueClient.from_connection_string(
    conn_str="UseDevelopmentStorage=true",
    queue_name="orders",
)

queue.create_queue()
queue.send_message(json.dumps({"orderId": "order-123"}))

print("Sent sample message to queue orders")
~~~

If the queue already exists, `create_queue()` may raise a conflict error; handle that case explicitly or create the queue once beforehand. **Do not run scripts that send messages to production queues** without proper authorization and approval workflows.

When the listener picks up the message, `process_order` logs `Processing order order-123`. If the message is not valid JSON or lacks `orderId`, the function raises an error and can be retried by the trigger per queue semantics.

### 9.5. Testing Timer

`hourly_cleanup` runs at the top of every hour on schedule. To test quickly in a **lab**, you can temporarily change the schedule to `0 */1 * * * *` (every minute), restart the host, and watch the logs. Restore the production schedule before deploying. Do not set `run_on_startup=True` to "force" a production job to run on every host recycle, as that can cause unscheduled executions.

### 9.6. Signs the Local Host Started Properly

You should see:

- Host startup with no Storage configuration errors.
- The function list includes `hello`, `process_order`, and `hourly_cleanup`.
- The HTTP route `/api/hello` responds to requests.
- Queue messages are processed when Azurite receives a message.
- The Timer is recognized by the host with its schedule.
- Clear logs without leaking secrets.

If the host only displays one function, inspect decorators, imports, and the binding extension rather than assuming the queue is empty.

## 10. Three Configuration Layers: host.json, App Settings, and Code

### 10.1. `host.json`

Applies configuration at the Functions host level, such as:

- Log levels/sampling/telemetry within supported options.
- `functionTimeout` within plan limits.
- Extension bundle and certain trigger/concurrency settings.
- Host-wide settings, not per-customer business data.

Do not store passwords or connection strings directly in `host.json`.

### 10.2. `local.settings.json`

- Used for **local development**.
- Contains `Values` for environment/app settings.
- Can contain secrets and generally must be excluded from version control.
- Is not automatically synced to Azure during deployment by default.

### 10.3. Azure Function App Application Settings

When running in Azure, app settings are exposed to the runtime/application as environment variables (exposure mechanism depends on the platform). For example:

~~~text
FUNCTIONS_WORKER_RUNTIME=python
AzureWebJobsStorage=<valid host storage configuration>
OrdersStorage__queueServiceUri=https://<account>.queue.core.windows.net
APPLICATIONINSIGHTS_CONNECTION_STRING=<Application Insights connection string>
~~~

This is an **illustrative sample, not a complete configuration to paste verbatim across every plan**. With identity-based connections, check extension versions and data-plane RBAC for the identity; host storage may also require additional URI/service settings depending on configuration.

**Do not print secret values** to terminal logs and never share production connection strings in chat.

### 10.4. Configuration Scope and Deployment

Changing an app setting can restart the Function App/host and affect in-flight invocations. Changing `host.json` requires publishing a new package. Changing code or requirements can cause a cold start or indexing failures.

Distinguish the effects:

| Change | Potential consequence |
| --- | --- |
| Edit function code | Build/deploy and host reload |
| Add dependency | Dependency install, larger image/package size |
| Change `FUNCTIONS_WORKER_RUNTIME` | Code may fail to index if mismatched |
| Change Storage connection | Trigger listeners may fail with permission/connectivity errors |
| Change `functionTimeout` | Plan-dependent, requires deploying host configuration |
| Change app setting | May restart and affect concurrent invocations |
| Change identity/RBAC | Requires propagation; code cannot grant its own permissions |

## 11. Storage Access, Identity, and Secrets

### 11.1. Host Storage and Workload Storage Need Not Be Identical

**AzureWebJobsStorage** is the host storage configuration used for operational needs of the Functions runtime and extensions where applicable. Certain triggers and hosting behaviors use storage for leases, coordination, or tracking. **OrdersStorage** is the connection to the business queue.

Do not assume "setting `FUNCTIONS_WORKER_RUNTIME=python` alone is enough" for Queue/Timer triggers to work in every environment. Valid Storage connections and host configuration are required.

### 11.2. Managed Identity and Data-Plane RBAC

In Azure, prefer system-assigned or user-assigned managed identities to access Storage and Key Vault where supported. Example permissions:

| Need | Permission/mechanism to evaluate |
| --- | --- |
| Host storage | Data actions/roles required by the trigger and hosting model |
| Read messages from Storage Queue | `Storage Queue Data Message Processor` or equivalent data-plane permission |
| Send messages to queue | `Storage Queue Data Message Sender` or equivalent role |
| Read Blobs | `Storage Blob Data Reader` where appropriate |
| Read Key Vault secrets | `Key Vault Secrets User` role or appropriate access policy |
| Deploy Functions | Appropriate control-plane permissions, distinct from data-plane |

**Attaching an identity does not automatically grant Storage Queue permissions.** RBAC at the storage account/queue scope, networking, and firewalls must all allow the flow. For a Queue trigger, the role must allow both processing and completing/deleting messages as required by the extension.

### 11.3. Identity-Based Connections

For Storage Queue extensions that support identity-based connections, settings such as:

~~~text
OrdersStorage__queueServiceUri=https://mystorage.queue.core.windows.net
~~~

let the runtime resolve the endpoint without an account key string. Ensure that:

1. The Function App has a managed identity enabled.
2. The identity holds the proper data-plane role.
3. Storage network/firewall/Private Endpoint rules allow traffic.
4. The trigger extension supports identity-based connections.
5. Host storage `AzureWebJobsStorage` is also properly configured (it may differ).
6. Permissions propagation has been verified.

If only the HTTP function works while the Queue trigger stays silent, do not disable the firewall or fall back to broad account keys as a temporary fix. Read the logs to determine whether it is a missing connection setting, missing role, network block, or missing queue.

### 11.4. Key Vault and Secret Protection

- Never commit `local.settings.json` containing secrets.
- Use Key Vault references or the SDK with managed identity when appropriate.
- Never include function keys, access tokens, or passwords in responses or logs.
- When rotating secrets, verify the app has picked up the new version; a restart may be required depending on how the app/runtime caches config.
- Limit permissions of CI/CD principals and function identities; do not grant subscription Owner just to read a Queue.

**Network security and RBAC are separate checks:** having Azure RBAC permissions while Private Endpoint/DNS is broken still causes trigger connection errors; conversely, an open network without data-plane rights still results in authorization denial.


## 12. Deploying a Function App to Azure in a Controlled Way

### 12.1. Choose the Architecture Before Provisioning

Before creating a Function App, define:

- Subscription, resource group, and region.
- Supported runtime/language version and Functions host version.
- Hosting plan suited for SLO, cold start, and networking.
- Storage Account and host storage connection type.
- Application Insights/Log Analytics destination.
- Managed identity and data-plane permissions to Storage/SQL/Key Vault.
- Inbound authentication and outbound networking (VNet/Private Endpoint if needed).
- Environment variables, secrets, and CI/CD method.
- Cost policy, quotas, alerts, and rollback plan.

**Do not copy classic Consumption `az functionapp create` commands directly for Flex Consumption** when CLI/hosting options differ. For new projects, verify the provisioning workflow for your current hosting plan in the portal/CLI instead of guessing `az functionapp create` parameters.

### 12.2. Provisioning via Azure Portal (Workflow Outline)

1. Open the Azure portal and select **Function App → Create**.
2. Choose the subscription, resource group, globally unique app name, region, and supported runtime/language.
3. Select the hosting option/tier based on workload and regional availability.
4. Configure storage, networking, logging, and Application Insights.
5. Enable managed identity if needed; assign RBAC **at the right resource scope**.
6. Define required application settings and Key Vault references, avoiding local credentials.
7. Create the app, wait for provisioning, and verify endpoints/configuration.
8. Deploy code using a method supported for that **specific plan**; confirm functions are indexed.
9. Run smoke tests, inspect logs and metrics.
10. Set up alerts, budgets, and deployment/rollback procedures before opening production traffic.

**Note:** Creating a Function App, Storage, and Insights can incur charges. Even an empty Function App without deployed functions can carry billable resources under certain plans.

### 12.3. Using Azure CLI to Inspect Without Exposing Settings

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-func-lab"
APP="fn-orders-lab"

# Read resource metadata.
az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name, state:state, location:location, kind:kind, serverFarmId:serverFarmId}" \
  --output json

# Verify functions indexed by the runtime.
az functionapp function list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table

# List ONLY setting names to avoid printing connection string values.
az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].name" \
  --output table
~~~

Running `az functionapp config appsettings list` **without filtering via `--query`** can expose secrets. Never paste full settings JSON into tickets or chat. Even an account with control-plane read access should not automatically view all business secrets.

### 12.4. Publishing a Project with Core Tools

For an existing Function App whose environment/plan is supported by your Core Tools version, from the project root directory:

~~~bash
func azure functionapp publish "$APP"
~~~

**This command replaces running code**, can restart workers, and affects all functions in the app. Check which deployment method is supported for **Flex Consumption and your specific plan**; many production workflows use CI/CD, deployment packages, container builds, or other deployment mechanisms.

Before publishing:

- Run unit/integration tests and evaluate dependency security.
- Confirm the target subscription and resource name.
- Ensure the package includes `host.json`, code, and required dependencies.
- Exclude `local.settings.json` containing credentials from the artifact.
- Choose a version/digest or deployment artifact that supports rollback.
- Check slot/revision support for your plan rather than assuming every plan supports deployment slots.

### 12.5. Post-Deployment Verification

- Function list contains `hello`, `process_order`, and `hourly_cleanup`.
- HTTP endpoints are accessible only per the designed authentication rules.
- Queue trigger has a healthy listener pointing to the right queue.
- Timer schedule matches the intended timezone.
- No import errors or host startup errors.
- Application Insights receives invocation telemetry/logs.
- Identity/RBAC is applied and firewall/Private Endpoint rules do not block traffic.
- SLO/latency and error rates meet expectations.

Do not mark a deployment successful just because the publish command returned exit code 0; **actual execution capability** must be verified.

## 13. Observing Functions: Logs, Metrics, and Tracing

### 13.1. Why Is Logging Mandatory?

In serverless, host instances can be created or deleted at any time, and failed invocations may be retried on a different instance. You cannot investigate by SSHing into "the current server." Centralize telemetry through **Application Insights/Azure Monitor/Log Analytics** as configured.

Useful signals:

| Signal | Question |
| --- | --- |
| Invocation count/success/failure | What is the failure rate? |
| Execution duration p50/p95/p99 | Are there cold starts or slow dependencies? |
| HTTP status/latency | Which 4xx/5xx responses are clients seeing? |
| Queue backlog and poison queue | Are workers lagging or retrying indefinitely? |
| Timer schedule/past due | Are scheduled jobs running on time? |
| Host instance count/concurrency | Is scaling keeping up? |
| CPU/memory | Are workers resource-starved? |
| Dependency failures/latency | Are SQL/Storage/external APIs bottlenecked? |
| Logs/traces by operation | Which invocation failed, and at which dependency? |
| Cost and ingestion volume | Is excessive logging inflating cost? |

### 13.2. Application Insights

When instrumentation is enabled, you can observe requests, dependencies, traces, exceptions, and other telemetry categories depending on the SDK/integration. KQL table names depend on whether you use **classic Application Insights or workspace-based Log Analytics schemas**.

Example in a resource/query context that has the `requests` table:

~~~kusto
requests
| where timestamp >= ago(2h)
| summarize
    Count = count(),
    FailureCount = countif(success == false),
    P95Duration = percentile(duration, 95)
    by bin(timestamp, 5m)
| order by timestamp asc
~~~

If the workspace uses resource-specific tables instead of `requests`, check the actual schema and use the equivalent table and columns. Do not fix queries by guessing nonexistent column names.

### 13.3. Tracking Exceptions

~~~kusto
exceptions
| where timestamp >= ago(24h)
| summarize Failures = count() by type, outerMessage
| order by Failures desc
~~~

This is an example for an **Application Insights context that has an `exceptions` table**. Sampling or ingestion settings can cause record counts to differ from total invocations. To measure exact failure rates, combine metrics and telemetry while accounting for sampling.

### 13.4. Correlation IDs and Structured Logs

An HTTP request sends a message to a queue; the Queue trigger processes it a few seconds later. To link both invocations:

~~~text
HTTP function:
  traceId=abc, jobId=job-123, action=enqueue

Queue function:
  traceId=abc, jobId=job-123, action=process

Database operation:
  traceId=abc, jobId=job-123, duration=45ms
~~~

Do not assume trace context automatically propagates across every queue or SDK; if auto-instrumentation does not propagate it, explicitly **pass correlation context** in message payloads/headers per standards and policy. Never log bearer tokens, passwords, or unnecessary PII.

### 13.5. Operational Alerts

Examples:

- HTTP 5xx exceeds threshold alongside rising p95 latency.
- Queue backlog grows continuously even as messages are published.
- New messages appear in the poison queue.
- Sudden spike in function invocation failures.
- Timer past-due or missed scheduled runs.
- Throttling in SQL/Storage/APIs or rising dependency latency.
- Function App host restarts or indexing errors.
- Compute or telemetry ingestion cost exceeding budget.

Every alert needs an **owner, SLO, severity, and runbook**. A single failed Queue message might succeed on retry, but a high failure rate still requires investigation.

## 14. Reliability: Idempotency, Retries, and Eventual Consistency

### 14.1. At-Least-Once Guarantee Instead of "Exactly Once"

Flow pattern:

~~~text
Receive order-123
    |
    v
Write database SUCCESS
    |
    v
Worker crashes BEFORE queue ACK
    |
    v
Message becomes visible again
    |
    v
Another invocation receives order-123
~~~

Without checking `orderId`, the application may create a duplicate order. One solution:

1. Use `orderId` as a unique key in the DB.
2. Start a transaction as supported by the database.
3. Check whether it has already been processed; only apply side effects when needed.
4. Persist `Processed` status along with the outcome.
5. When the message is redelivered, return safely without creating duplicates.

**Preventing duplicate side effects** such as emails or payments may require the outbox pattern, deduplication, and additional business controls; a flag in RAM is never sufficient.

### 14.2. Classified Retries

| Error | Should retry? | Recommendation |
| --- | --- | --- |
| Transient Storage/SQL timeout | Yes, bounded | Exponential backoff + jitter |
| HTTP 429 rate limit | Yes, honoring `Retry-After` when applicable | Limit concurrency and retry budget |
| Message missing required fields | Do not retry infinitely | Poison/dead-letter/investigate publisher |
| Unauthorized 403 due to missing RBAC | Will not self-heal via retries | Fix identity/permissions |
| Database unique conflict from duplicate message | Return idempotent status | Do not insert a second record |
| Host OOM | Retries do not fix root cause | Optimize memory, adjust plan |

Triggers and extensions have different retry rules; do not assume HTTP retry policies match Service Bus Queues or Event Hubs. Excessive retries can trigger a **retry storm** when downstream systems are already overloaded.

### 14.3. Message Ordering

With multiple instances and high concurrency, **do not assume Queue Storage messages are processed in exact send order in all scenarios**. If business logic requires ordering by `accountId` or `orderId`, design partitions, sessions, or serialization with a messaging service that supports ordering.

### 14.4. Durable Functions

**Durable Functions** provides an orchestration model for stateful functions including:

- **Orchestrator** coordinating activity functions.
- **Activity** executing a unit of work.
- **Entity** storing state in a supported model.

A flow can wait for external events, retry activities, persist state, and resume after host recycles. However, orchestrators have **replay semantics**: orchestration code must remain deterministic and must not make unmanaged API calls with side effects directly inside the orchestrator.

Use Durable Functions for multi-step or long-waiting workflows; not every small queue function needs Durable.

## 15. Security and Networking

### 15.1. Public HTTP Is Not Secure by Default

HTTP triggers with public routes need:

- HTTPS and proper hostnames/certificates.
- Authentication and authorization (Entra ID, JWT, Easy Auth, or API Management as appropriate).
- Request validation, payload size limits, and rate limiting.
- Browser CORS configuration; **CORS is not an authorization mechanism**.
- No function/admin keys in source code or easily logged URLs.
- Least-privilege secrets/identity and data-plane permissions.

### 15.2. VNet, Private Endpoints, and DNS

When Functions access private Azure SQL/Storage/Key Vault:

1. Verify the hosting plan supports the required VNet integration.
2. Choose subnets/network routes per plan requirements.
3. Configure Private Endpoints for target services if required.
4. Link Private DNS Zones/forwarding properly to the VNet.
5. Check Storage/SQL firewalls and data-plane RBAC.
6. Ensure host storage and trigger sources are also reachable under the network configuration.

**VNet integration does not automatically make all services private.** When Functions triggers fail after locking down Storage networking, verify DNS and routing for host storage separately from business connections.

### 15.3. Permissions and Trust Boundaries

Do not grant subscription Owner to a Function App just to read a queue. Separate:

- Deployment identity: permitted to update the Function App and app settings.
- Runtime managed identity: scoped to specific Queue/Blob/SQL/Key Vault resources.
- Monitoring roles: read logs/metrics without viewing secrets.
- Network team: manages private connectivity.
- Security team: policy, certificate, and secret rotation.

Assign RBAC at the minimum required scope. For storage identities, **management-plane Contributor** does not automatically grant all **data-plane** rights.

### 15.4. Dependency Package Risks

Serverless still runs code packaged by the development team. Pin dependencies, scan for vulnerabilities, review licenses, and run security tests. Never import packages from untrusted sources or embed secrets in code. Local secrets must stay out of build artifacts and Git.

## 16. Cost and Sizing

### 16.1. Cost Drivers

Plans have different billing models: provisioned compute, execution count, execution duration/memory, or always-ready resources, depending on the plan. Beyond Functions itself, costs may include:

| Component | Cost source |
| --- | --- |
| Functions hosting | Plan/instances/vCPU-memory duration/executions per pricing model |
| Storage Account | Transactions, stored data, queues, egress |
| Application Insights/Log Analytics | Log ingestion, retention, alerts |
| Key Vault | Operations per pricing model |
| Private Endpoint/NAT/network | Network resources and data processing |
| Database/Cosmos DB | RU/s, DTU/vCore, storage |
| Service Bus/Event Hubs | Messaging tier/throughput |
| API Management/Front Door | Gateway, requests, WAF, data transfer |

Never say "if a Function isn't running, it definitely costs nothing" across all plans: Premium, Dedicated, always-ready instances, and supporting resources can continue incurring charges.

### 16.2. Execution Workload Math Example

Suppose 1 million invocations/month, averaging 0.2 seconds each with 512 MiB memory allocated:

~~~text
1,000,000 invocations × 0.2 s = 200,000 execution-seconds

512 MiB = 0.5 GiB
200,000 × 0.5 GiB = 100,000 GiB-seconds
~~~

This is a **workload volume calculation**, not an Azure invoice: billing applies minimum execution durations, free grants, plan-specific pricing models, always-ready charges, and other rules. Use the **Pricing Calculator** and current pricing for your exact region and plan to estimate actual costs.

### 16.3. Reducing Cost Without Breaking SLOs

- Reduce dependency latency and optimize memory/CPU usage.
- Set concurrency/scale limits aligned with backend quotas.
- Use queues to smooth spikes and avoid long-running HTTP requests.
- Use always-ready only when cold start genuinely threatens the SLO.
- Trim noisy logs, tune sampling and retention without losing critical signals.
- Evaluate plan cost over realistic load cycles, not just a single peak minute.
- Consider splitting Function Apps if one workload drives up scaling/cost for another.

## 17. Diagnosing Common Failures

| Symptom | Possible cause | Verification steps |
| --- | --- | --- |
| No functions visible after deploy | Wrong folder, missing `host.json`, import/index error | Startup logs, deployment artifact, `az functionapp function list` |
| HTTP 404 | Wrong route prefix, route not indexed | `func start`, function list, route |
| HTTP 401/403 | Function key/auth, Easy Auth, RBAC/policy | Endpoint auth config, identity |
| HTTP 500 | Unhandled code exception or dependency failure | Invocation logs and tracing |
| HTTP 502/504 | Frontend timeout or slow upstream | HTTP duration, dependency logs |
| Slow first request | Cold start, heavy imports/dependency startup | p95/p99 after idle, host cold start logs |
| Queue trigger not firing | Wrong queue/connection, host storage, missing extension, RBAC/network | Setting names, Azurite/Storage logs, host startup |
| Duplicate queue execution | Redelivery/retry after error or crash | Dequeue count, idempotency key |
| Messages in poison queue | Message failed multiple times | Inspect message safely, validate schema |
| Timer running at wrong time | UTC/timezone, schedule format, host monitor | NCRONTAB, plan support, logs |
| Functions slow despite scaling | SQL/API quota or concurrency bottleneck | Dependency latency, pool limits |
| Missing telemetry | App Insights config, sampling, wrong workspace | Connection string, schema, ingestion |
| Azure RBAC valid but Storage times out | Private DNS/VNet/firewall | DNS, network path, endpoint |
| Cost rises while idle | Premium/always-ready/Dedicated, logs, and Storage | Billing breakdown, min instances |

### 17.1. From Symptom to Root Cause Workflow

1. Identify the **Function App, function, trigger, subscription, plan, and timeframe**.
2. Read host startup logs to confirm the function was indexed.
3. Verify the trigger source: HTTP path, queue name, Timer schedule, or event subscription.
4. Inspect app settings, identity, storage connectivity, and extensions.
5. Correlate invocation logs/traces with downstream failures or latency.
6. Check plan scaling, concurrency, timeouts, and instance health.
7. Fix the root cause, preserving evidence before restarting or redeploying.
8. Retest with representative inputs, monitoring both failure rate and SLO.

## 18. Comprehensive Lab Exercise Without Provisioning Azure Resources

### 18.1. Simulated Scenario Data

A Function App `fn-orders-prod` has:

- An HTTP function accepting orders and pushing messages to a queue.
- A Queue function processing orders.
- A Timer function generating hourly reports.
- Host storage and queue configured.
- Typical daily load of 10 msg/s, peaking at 150 msg/s.

Operational metrics:

| UTC | Message backlog | Successful queue invocations | Failed invocations | HTTP p95 |
| --- | ---: | ---: | ---: | ---: |
| 08:00 | 20 | 600/min | 0 | 180 ms |
| 09:00 | 2,000 | 700/min | 15 | 240 ms |
| 09:05 | 8,000 | 800/min | 90 | 270 ms |
| 09:15 | 12,000 | 820/min | 120 | 290 ms |

**Question A:** Is simply increasing max instances enough?

*Answer:* Not yet. Backlog is rising and failures are increasing too; you must find the root cause: queue scaler/plan limit, DB throttling, malformed messages, or permissions. If the DB is the bottleneck, adding instances can drive the failure rate even higher.

**Question B:** A message `order-123` is invoked twice after the first invocation wrote to the DB successfully but crashed before acknowledgment. What should you do?

*Answer:* Design idempotency around `orderId` using transactions/unique constraints so duplicates do not trigger extra side effects. Never assume queues execute exactly-once.

**Question C:** Timer `0 0 9 * * *` runs at 09:00 UTC, but the operations team in Vietnam wants 09:00 local time. What must change?

*Answer:* Convert properly to UTC and account for Daylight Saving Time if in a DST region; Vietnam is UTC+7 with no DST. With UTC default, 09:00 Vietnam time corresponds to 02:00 UTC, so you can use schedule `0 0 2 * * *`. Do not rely blindly on `WEBSITE_TIME_ZONE` when the plan/OS may not support it.

**Question D:** An HTTP function runs a 12-minute workflow, and the client times out earlier even though `functionTimeout` is longer than 12 minutes. Why?

*Answer:* The HTTP frontend, load balancer, or client enforces its own timeout; use a queue + `202 Accepted` or the Durable Functions async pattern instead.

**Question E:** The Queue trigger does not run, yet the HTTP function still returns 200. What should you check?

*Answer:* `OrdersStorage` connection, queue name, extension bundle, storage firewall/private DNS, identity/data-plane RBAC, and host startup logs. A healthy HTTP endpoint does not prove the queue listener is healthy.

### 18.2. Pre-Production Checklist

- Choose the hosting plan based on SLO, region/runtime/network support, and cost.
- App indexes all functions and logs/telemetry are flowing.
- HTTP endpoints enforce authentication/authorization and input validation.
- Queue consumers are idempotent with clear retry/poison handling.
- Timers use the right timezone and schedule.
- Managed identity has required RBAC, with zero secrets in source code.
- Host storage and trigger connections work over the real network topology.
- Concurrency, cold start, timeout, CPU/memory, and downstream capacity are tested.
- CI/CD, versioning/rollback plan, monitoring alerts, and budgets are in place.

## 19. Self-Check Questions

**Question 1.** A Function App has three functions. Do those three functions necessarily run on three separate VMs?

**Answer:** No. The number of host instances and concurrency depend on the hosting plan and load; they belong to the same application unit rather than getting one VM per function.

**Question 2.** Can a single function have both an HTTP trigger and a Queue trigger?

**Answer:** Each function defines a single trigger. Use two separate functions, which can share reusable business logic.

**Question 3.** What is the difference between `host.json` and `local.settings.json`?

**Answer:** `host.json` holds runtime/host-level configuration; `local.settings.json` holds settings for local development, may contain secrets, and is not published to Azure by default.

**Question 4.** Can changing a connection string in Azure stop triggers from running even when the code has not changed?

**Answer:** Yes. Listeners depend on valid settings, permissions, and connectivity; config changes can restart the host or break Storage access.

**Question 5.** Why does Storage Queue processing require idempotency?

**Answer:** Messages can be redelivered after failures or crashes, risking duplicate side effects.

**Question 6.** How do scale-out and concurrency differ?

**Answer:** Scale-out increases the number of host instances; concurrency increases the number of invocations processed simultaneously on a single instance within configured limits.

**Question 7.** Can Flex always-ready and Premium incur charges even when there are no requests?

**Answer:** Yes, because of pre-allocated/always-ready compute, plan billing, and supporting resources. Review the actual pricing model.

**Question 8.** When an HTTP request requires long-running processing, why are queue/`202` or Durable Functions more suitable?

**Answer:** They avoid holding connections past frontend/client timeout limits and enable state persistence, retries, and progress tracking.

**Question 9.** Does a function key replace OAuth user authentication?

**Answer:** No. A function key is a shared secret and does not represent user identity or business-level authorization.

**Question 10.** Why shouldn't you assume `WEBSITE_TIME_ZONE` works across every hosting plan?

**Answer:** Support varies by OS and hosting plan; verify platform support and prefer UTC when needed.

## Key Takeaways

- A **Function** is logic triggered by a single **trigger**; a **Function App** is the configuration and deployment boundary containing multiple functions.
- The **Functions host** loads metadata, triggers, and bindings; the **language worker** executes code per the supported runtime and programming model.
- **HTTP, Queue, and Timer** triggers differ in inputs, responses, retries, and scaling; each function has only one trigger.
- **Flex Consumption, Consumption, Premium, and Dedicated** differ in compute provisioning, cold starts, networking, and billing.
- **Scale-out does not mean concurrency**; always evaluate latency, downstream quotas, and duplicate delivery handling.
- **Stateless design, idempotency, bounded timeouts/retries, managed identity, and monitoring** form the foundation of reliable Functions systems.
- Always verify **Function App runtime, host storage, trigger connections, RBAC, networking, and observability** before declaring a deployment complete.
