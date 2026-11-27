# Fan-Out, Fan-In, and Long-Running Workflows

A standard Azure Function works well for handling an HTTP request, queue message, or event within a relatively short timeframe. However, when you must **process thousands of independent documents**, **wait two days for human approval**, or coordinate a multi-step transaction where steps can fail, writing a single Function that calls APIs sequentially while holding an HTTP request open breaks down operationally: connections time out, workers restart, progress lives only in RAM, and retries risk duplicating side effects.

**Azure Durable Functions** extends Azure Functions for **stateful workflows**. Developers define orchestration logic in an orchestrator, move external side effects into activities, await durable timers or external events, and query status by instance ID. The runtime persists history and **replays** orchestration decisions when resuming an instance after a restart. It does not prevent logic bugs, does not automatically make every side effect exactly-once, and does not replace security or cost governance.

Two central patterns:

- **Fan-out/fan-in:** split a set of inputs into independent activities that can run in parallel, then wait for and aggregate the results.
- **Long-running orchestration:** model workflows spanning minutes, hours, or days using durable wait points without holding an HTTP connection or thread open continuously.

This lesson belongs to the **Serverless with Azure Functions** chapter of the **CLOUD_PROVIDERS_AZURE** module, connecting Functions development with subscriptions, resource groups, Microsoft Entra ID, Storage, networking, Azure Monitor, security, and cost management on Azure.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the limitations of standard HTTP Functions for long-running jobs.
2. Distinguish starter/client, orchestrator, activity, orchestration instance, task hub, durable timer, and external event.
3. Implement fan-out/fan-in using the **Azure Durable Functions Python programming model v2**.
4. Handle retries, timeouts, idempotency, partial failures, and fan-in policies.
5. Design HTTP `202 Accepted`, status endpoints, and protection against duplicate jobs when callers retry.
6. Build a human approval workflow using external events or timeouts.
7. Apply monitor patterns, batching, sub-orchestrations, and continue-as-new.
8. Understand deterministic replay, versioning, storage history, and payload limits.
9. Calculate scale, concurrency, downstream quotas, costs, and task hub security.
10. Diagnose Pending/Running/Failed instances, build production checklists, and run fault tests.

Examples use Python, Azure Functions Core Tools, Azure Storage/Azurite, and the Durable Functions extension. Resource names, URLs, and payloads are illustrative; **do not provision resources or run code against a live subscription unapproved**.

## 2. When Is a Standard Function Not Enough?

### 2.1. The 1,000-Invoice Processing Problem

An HTTP endpoint receives a list of 1,000 invoices. Each invoice requires calling an analysis API, saving output to Blob Storage, and building a summary report. With a single HTTP Function:

~~~text
HTTP POST /analyze
    |
    v
Loop 1,000 files -> call API -> save result
    |
    v
Aggregate report -> HTTP 200
~~~

The risks:

- Clients, gateways, and HTTP infrastructure can time out before the loop completes.
- Function invocations face hosting plan duration limits.
- Worker restarts or scale-in wipe in-memory progress.
- Caller retries can trigger duplicate charges or duplicate data.
- If file #800 fails, identifying which files already succeeded is hard.
- Raising timeouts does not add checkpoints, retry policies, or progress queries.

**Durable Functions does not make an activity exceeding invocation limits valid.** Instead of letting one call run forever, workflows split work into activities sized within hosting plan resource and timeout bounds.

### 2.2. Returning Responses Asynchronously

~~~mermaid
sequenceDiagram
    participant U as Client
    participant H as HTTP Starter
    participant O as Orchestrator
    participant A as Activity Workers
    participant S as State Storage
    U->>H: POST /jobs
    H->>O: Start instance
    H-->>U: 202 Accepted + instanceId
    O->>S: Persist history/checkpoint
    O->>A: Schedule activities
    A-->>O: Results
    O->>S: Write status
    U->>H: GET /jobs/{id}
    H-->>U: Running/Completed/Failed
~~~

HTTP responds early so the client never waits on the entire job. The instance proceeds via durable orchestration; the system tracks and recovers state per runtime/backend capabilities.

### 2.3. Choosing the Right Tool

| Need | Design Approach | Rationale |
|---|---|---|
| Short-lived HTTP API | HTTP-trigger Function | Simple, stateless |
| Independent queue messages | Queue-trigger Function | Leverages queue/trigger retries |
| N independent tasks needing combined output | Durable fan-out/fan-in | Orchestrator tracks the result set |
| API job running tens of minutes | Async HTTP + Durable instance | Client polls status by ID |
| Waiting for human approval | External event + durable timer | Preserves state during wait |
| Polling external job status | Monitor pattern | Timer waits replace sleep |
| Multi-SaaS/connector workflows | Evaluate Logic Apps | Rich connectors and workflow fit |
| Heavy CPU/GPU batch compute | Azure Batch / AKS Jobs / Container Apps Jobs | Orchestrator coordinates rather than doing heavy CPU |

Do not adopt Durable Functions just to "run things concurrently"; if messages are completely independent and need no fan-in, simple queue consumers are often cleaner and cheaper.

## 3. Components of Durable Functions

### 3.1. Client/Starter

A client Function can:

- Start an orchestration instance.
- Query instance ID and status.
- Send an external event.
- Invoke management APIs to terminate, suspend/resume, or purge where supported by the version.
- Return management/status URLs to the HTTP caller.

The starter should not execute heavy workflow steps; it authenticates, validates input, and starts the instance.

### 3.2. Orchestrator

The orchestrator defines execution order, dependencies, and wait points:

~~~text
Activity A
   |
   +--> Activity B1 --+
   +--> Activity B2 --+--> Fan-in --> Activity C
   +--> Activity B3 --+
                         |
                         v
                    Await approval
                         |
                         v
                   Activity D
~~~

The orchestrator uses APIs such as `context.call_activity`, `task_all`, `task_any`, `create_timer`, `wait_for_external_event`, and `call_sub_orchestrator`. It **must never read Blobs directly, make HTTP calls, or execute transactions**.

### 3.3. Activity

Activities perform logic with side effects:

- Read Blobs/DBs.
- Call AI or partner APIs.
- Process and persist outputs.
- Send emails, notifications, or create transactions.
- Poll external system status.
- Aggregate large outputs.

An activity can fail or retry, so side effects require idempotency or reconciliation.

### 3.4. Instances, History, and Task Hubs

| Term | Meaning |
|---|---|
| Instance ID | Unique identifier for one orchestration run |
| Input | Orchestration input data |
| History | Recorded events/decisions/results used by runtime replay |
| Task hub | Logical grouping of Durable backend state and coordination queues |
| Task | Scheduled activity, timer, or awaited event |
| Custom status | Progress metadata updated by app code via supported APIs |
| Orchestration output | Return value upon completion |
| Continue-as-new | Continues execution with fresh input while resetting/compacting history per runtime |

Durable Functions commonly uses the Azure Storage provider or another supported backend depending on extension, hosting, and config. The task hub holds vital operational state; never delete task hub queues, tables, or containers while instances are running.

## 4. Replay and the Determinism Rule

### 4.1. What Is Replay?

The Durable runtime can re-execute orchestrator code from the beginning against recorded history, feeding saved activity/timer outcomes back from history and resuming at the pending wait point. **Orchestrator code must reproduce the exact same decision sequence** for the same input and history.

~~~mermaid
flowchart TD
    A["Schedule Activity A"] --> H["History: Activity A completed"]
    H --> W["Await timer/event/Activity B"]
    W --> R["Worker restarts"]
    R --> P["Replay orchestrator code"]
    P --> K["Reconstruct decisions from history"]
    K --> N["Resume pending step"]
~~~

Because of replay, logs inside an orchestrator can emit multiple times even when an activity never re-executed. Replay **does not** automatically make activity side effects exactly-once.

### 4.2. What Never to Do Inside an Orchestrator

- Make direct HTTP, Storage, SQL, or Key Vault calls.
- Send emails, issue invoices, or write files.
- Call non-Durable random generators or UUIDs to drive branching.
- Use `datetime.now`/`utcnow` for decision timestamps.
- Call `time.sleep` or perform blocking waits.
- Depend on unstable iteration order of data structures.
- Read app settings that can change between replays and alter workflow branches.
- Spawn threads, coroutines, or I/O outside Durable primitives.

Incorrect example:

~~~python
from datetime import datetime
import requests

def wrong_orchestrator(context):
    if datetime.utcnow().hour < 12:
        requests.post("https://example.invalid/pay", json={"order": 1})
    return "done"
~~~

During replay, the clock or network response can differ and the POST could repeat.

### 4.3. The Right Approach

- Read logical UTC via **`context.current_utc_datetime`**.
- Generate UUIDs via **`context.new_uuid()`** when supported by the SDK.
- Wait using **`context.create_timer(deadline)`**.
- Place HTTP, DB, Storage, and Key Vault calls inside activities.
- Version decision inputs cleanly; never read mutable config during replay.
- Pass small ID/URI metadata instead of bulky payloads.

In Python orchestrators, avoid duplicate logs by checking replay state (where supported by the SDK):

~~~python
if not context.is_replaying:
    logging.info("Starting fan-out stage")
~~~

## 5. Fan-Out / Fan-In Pattern

### 5.1. Fan-Out: Scheduling Many Tasks

~~~mermaid
flowchart TD
    I["Input: 4 documents"] --> O["Orchestrator"]
    O --> A1["Analyze 001"]
    O --> A2["Analyze 002"]
    O --> A3["Analyze 003"]
    O --> A4["Analyze 004"]
    A1 --> F["task_all: fan-in"]
    A2 --> F
    A3 --> F
    A4 --> F
    F --> S["Aggregate summary"]
    S --> R["Completed"]
~~~

Activities can be distributed across multiple workers. However, **N scheduled tasks do not guarantee N concurrent executions**: concurrency remains bounded by workers, hosting plan, backend queues, and downstream services.

### 5.2. Fan-In: Waiting and Aggregating

A typical orchestrator:

~~~python
tasks = [
    context.call_activity("analyze_document", item)
    for item in items
]
results = yield context.task_all(tasks)
summary = yield context.call_activity("summarize_results", results)
return summary
~~~

`task_all` expresses an **await-all** dependency, while the aggregation activity computes or persists the combined outcome. If one activity raises an exception, define retry or partial-success policies—never assume `task_all` always returns all successes.

### 5.3. Suitable Use Cases

- Processing batches of files, images, or documents.
- Collecting data from multiple endpoints and aggregating results.
- Splitting a large report into parallel calculation chunks.
- Processing small partitions or shards.
- Running parallel checks across environments and summarizing.
- Dispatching independent service requests and awaiting all responses.

Do not fan out steps requiring strict sequential transactions or mutating the same record concurrently without locking/idempotency design.

### 5.4. Timing Example

With 10 activities taking 5 seconds each:

- Sequential: roughly 50 seconds for work alone, plus overhead.
- Ample capacity: fan-out approaches the longest single task plus overhead.
- Only 2 concurrent slots: takes roughly 5 waves.

This is an ideal model, not an Azure latency guarantee. If a partner API caps at 2 requests/second, blasting thousands of activities at once triggers 429s and stretches total runtime.

## 6. Hands-On: Azure Durable Functions Python v2

### 6.1. Prerequisites and Structure

Using Azure Functions runtime v4 and compatible packages:

~~~text
durable-documents/
  function_app.py
  requirements.txt
  host.json
  local.settings.json
~~~

Illustrative `requirements.txt`:

~~~text
azure-functions
azure-functions-durable
~~~

In real projects, pin dependency versions under governance and test compatibility before release.

### 6.2. Complete Code

This example processes **simulated document metadata**, without live I/O or PDF parsing. Its purpose is demonstrating fan-out, fan-in, and status APIs.

~~~python
import logging

import azure.functions as func
import azure.durable_functions as df

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="jobs/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_batch(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    if not isinstance(payload, dict):
        return func.HttpResponse("Body must be an object", status_code=400)

    items = payload.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 20):
        return func.HttpResponse(
            "items must be an array of 1 to 20 elements",
            status_code=400,
        )

    if any(
        not isinstance(item, str) or not item.strip() or len(item) > 100
        for item in items
    ):
        return func.HttpResponse("Invalid ID", status_code=400)

    instance_id = await client.start_new(
        "fanout_orchestrator",
        None,
        {"items": items},
    )
    return client.create_check_status_response(req, instance_id)


@app.orchestration_trigger(context_name="context")
def fanout_orchestrator(context: df.DurableOrchestrationContext):
    payload = context.get_input()
    tasks = [
        context.call_activity("analyze_document", document_id)
        for document_id in payload["items"]
    ]
    results = yield context.task_all(tasks)
    summary = yield context.call_activity("summarize_results", results)
    return summary


@app.activity_trigger(input_name="document_id")
def analyze_document(document_id: str) -> dict:
    logging.info("Analyzing document ID")
    return {
        "documentId": document_id,
        "processed": True,
        "score": len(document_id),
    }


@app.activity_trigger(input_name="results")
def summarize_results(results: list) -> dict:
    return {
        "total": len(results),
        "processed": sum(1 for r in results if r["processed"]),
        "scoreSum": sum(r["score"] for r in results),
        "documentIds": [r["documentId"] for r in results],
    }
~~~

Components:

1. HTTP starter validates input and caps item count.
2. Durable client calls `start_new` and generates an instance ID.
3. `create_check_status_response` builds a `202` response with Durable Functions status/management URLs.
4. The orchestrator schedules activities and awaits `task_all`.
5. `analyze_document` performs independent work (simulated).
6. `summarize_results` is a separate activity allowing extensible aggregation logic.
7. Final output is persisted by the runtime state store.

If using the Python v1 programming model or a different package release, decorators and folder layout differ; do not copy v2 code verbatim into a v1 project.

### 6.3. Illustrative `host.json`

~~~json
{
  "version": "2.0",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  },
  "extensions": {
    "durableTask": {
      "hubName": "DocumentsHub",
      "maxConcurrentActivityFunctions": 10,
      "maxConcurrentOrchestratorFunctions": 5
    }
  }
}
~~~

These concurrency caps are illustrative only. Optimal settings depend on worker, plan, provider, and actual load. **`hubName`** must be managed per environment; prevent two independent apps from accidentally sharing the same task hub and storage state.

### 6.4. `local.settings.json`

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python"
  }
}
~~~

`UseDevelopmentStorage=true` uses Azurite locally where features are supported. Never place production account keys in `local.settings.json` inside Git and never use the emulator as production storage.

### 6.5. Sending a Test HTTP Request

With Core Tools and dependencies installed, run in a lab environment:

~~~bash
func start
~~~

Send request:

~~~bash
curl -X POST \
  http://localhost:7071/api/jobs/start \
  -H 'Content-Type: application/json' \
  -d '{"items":["invoice-001","invoice-002","invoice-003"]}'
~~~

Expect `202 Accepted`, an `instanceId`, and URLs to query or manage the instance. Those URLs can embed keys in query strings; **never paste raw responses containing management URLs into public logs or tickets**.

Illustrative final output once `Completed`:

~~~json
{
  "total": 3,
  "processed": 3,
  "scoreSum": 33,
  "documentIds": ["invoice-001", "invoice-002", "invoice-003"]
}
~~~

All three document IDs are 11 characters long; `score` simply sums string lengths to demonstrate fan-in rather than real document parsing.

### 6.6. Checks to Run

- Instance state transitions from Pending/Running to Completed.
- Output lists all 3 document IDs accurately.
- No extension or host storage errors.
- Status can be queried without leaking sensitive data.
- Verify HTTP `400` on empty/over-20 items or invalid entries.
- Inspect activity logs and instance correlation.
- When replacing mock logic with real I/O, test retries, permissions, throttling, and error handling.

## 7. Fan-In with Failures: All-or-Nothing vs. Partial Success?

### 7.1. One Activity Fails

Suppose 9 out of 10 files succeed and the 10th times out:

~~~mermaid
flowchart TD
    O["Fan-out 10 activities"] --> S["9 succeeded"]
    O --> F["1 failed"]
    S --> P{"Business policy"}
    F --> P
    P -->|Require all| X["Failed / needs handling"]
    P -->|Partial allowed| R["9 results + 1 error"]
    P -->|Transient| T["Bounded retry"]
    T --> P
~~~

Fan-in behavior must reflect business rules. A summary report may tolerate one missing file, whereas financial reconciliation must fail the whole job rather than publishing partial figures.

### 7.2. Strategies

| Policy | When to Use | Pitfalls |
|---|---|---|
| Fail all | All results mandatory | Earlier side effects may need compensation |
| Retry transient | 429/503/network timeouts | Retries multiply requests and cost |
| Partial success | Independent items; missing items acceptable | Output must explicitly flag missing items |
| Dead-letter/quarantine | Corrupt items need investigation | Requires saving metadata and selective replay |
| Batch/sub-orchestrator | Huge input sets | Must manage progress and history growth |

An activity wrapper can catch/classify failures and return `succeeded=false` instead of raising an exception. Yet if business rules forbid partial results, never falsely mark the run `Completed`.

### 7.3. Keep Large Payloads Out of Results

Example:

~~~json
{
  "documentId": "invoice-014",
  "succeeded": false,
  "attempts": 3,
  "errorCode": "PARTNER_TIMEOUT",
  "outputBlobPath": null
}
~~~

On success, write bulky results to Blob Storage and return only a reference:

~~~json
{
  "documentId": "invoice-015",
  "succeeded": true,
  "attempts": 1,
  "errorCode": null,
  "outputBlobPath": "results/job-001/invoice-015.json"
}
~~~

Avoid storing customer data, raw PDF contents, access tokens, or long-lived SAS URIs in history whenever possible.

## 8. Retries and Idempotency

### 8.1. Durable Retries

In a Python orchestrator, you can invoke activities with retry options:

~~~python
retry_options = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)

result = yield context.call_activity_with_retry(
    "analyze_document",
    retry_options,
    "invoice-001",
)
~~~

Illustrative Python Durable Functions API; verify exact SDK version, parameters, and behavior when deploying. Retries must have finite attempt counts, delays, and timeouts—never infinite loops.

### 8.2. Error Classification

- **Transient:** 429, 503, network timeouts, temporary service unavailability.
- **Permanent:** malformed payload, invalid request, nonexistent business resource ID.
- **Authorization:** 401/403 from principal/RBAC/policy issues requires fixing config; retries won't help.
- **Business conflict:** 409 or already-processed duplicates require reconciliation, not blind transient retries.
- **Operation timeout:** an HTTP timeout does not prove the partner failed to execute the operation.

### 8.3. Duplicate Side Effects

Suppose an activity POSTs an invoice creation request, the partner saves it, and the response drops. The runtime retries the activity and the partner might create a second invoice.

To reduce risk:

1. Generate a **stable operation ID** from `businessJobId + itemId + operationType`.
2. Pass `Idempotency-Key` if supported by the API.
3. Enforce unique constraints or conditional inserts in the database.
4. Check existing operation state before re-executing.
5. Emit correlation IDs in logs and audits.
6. Reconcile whenever responses drop after side effects.

Send `Idempotency-Key` only when the backend actually enforces deduplication; attaching a header nobody checks does not provide exactly-once safety.

### 8.4. Exactly-Once Is a Dangerous Assumption

Durable Functions history reconstructs **orchestration decisions**, yet activities can still re-execute on errors, retries, or redeliveries. Design every side effect to be idempotent. Never promise "runs exactly once" for payments, emails, or orders merely because a workflow uses Durable Functions.

### 8.5. Layered Timeouts

Do not confuse:

- HTTP client timeout when an activity calls an external API.
- Function invocation timeout under the hosting plan.
- Workflow durable timer deadline.
- History/retention timeout and capacity limits.
- Business SLA or approval contract deadlines.

Waiting on a durable timer can outlive a single worker invocation, yet a 4-hour CPU-heavy activity still must fit within hosting plan limits and design constraints.

## 9. Batching and Capping Fan-Out

### 9.1. Why Not Schedule 500,000 Activities at Once?

- History events explode.
- `task_all` inputs/outputs grow huge.
- Storage backend faces heavy message/transaction load.
- Replay becomes slow and memory-intensive.
- Downstream APIs return floods of 429s.
- Log and transaction costs spike.
- Pinpointing failed subsets and recovering becomes difficult.

**Fanning out N activities does not mean N run simultaneously**; runtime and quotas throttle execution. Still, huge scheduled task lists and histories put severe pressure on storage and replay.

### 9.2. Batch Pattern

~~~text
50,000 item IDs
  ├─ batch 1: 100 IDs → fan-out → fan-in → save summary
  ├─ batch 2: 100 IDs → fan-out → fan-in → save summary
  ├─ ...
  └─ batch 500: 100 IDs → fan-out → fan-in → save summary
                             |
                             v
                       Final aggregate
~~~

Pseudocode:

~~~python
# PSEUDOCODE inside orchestrator, not a complete function.
for batch in chunk(items, batch_size=100):
    tasks = [context.call_activity("process_item", x) for x in batch]
    results = yield context.task_all(tasks)
    yield context.call_activity("persist_batch_summary", results)
~~~

If 500 batches still grow one orchestration's history too large, use sub-orchestrations, `continue_as_new`, or external progress tracking.

### 9.3. Per-Worker Concurrency Is Not a Global Rate Limit

`maxConcurrentActivityFunctions` can throttle activities per worker instance depending on runtime/version. When a Function App scales out to 10 instances, total concurrency scales far above the per-worker cap.

If a partner caps traffic at 30 calls/second system-wide, you need:

- A distributed limiter/semaphore, or quota-paced batch dispatching.
- Bounded backoff/retries on 429s.
- Monitoring on request rates, queue depth, and latency.
- Capacity planning across the entire App Service Plan/Functions plan.
- Offloading heavy/long CPU stages to AKS, Azure Batch, or Container Apps Jobs.

### 9.4. Sub-Orchestrations

~~~mermaid
flowchart TD
    P["Parent Orchestrator"] --> A["Child: group A"]
    P --> B["Child: group B"]
    P --> C["Child: group C"]
    A --> A1["Activities A"]
    B --> B1["Activities B"]
    C --> C1["Activities C"]
    A1 --> F["Parent fan-in"]
    B1 --> F
    C1 --> F
    F --> O["Final result"]
~~~

Benefits: split responsibilities, track groups separately, isolate retries/timeouts, and simplify parent logic. However, sub-orchestrations still generate state/history and do not automatically cap global concurrency.

## 10. HTTP 202 and Long-Running Workflows

### 10.1. Async Request-Reply

A business API might start a job like this:

~~~http
POST /api/jobs
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
Idempotency-Key: report-001

{"documentSetId":"batch-2026-001"}
~~~

Response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/jobs/report-001
Retry-After: 10

{"jobId":"report-001","state":"Accepted"}
~~~

This is an **application-defined API contract**, not something generated automatically by Durable Functions. The client:

1. Sends a request with a business ID/idempotency key.
2. Receives `202` and a job ID.
3. Polls status with sensible intervals/backoff.
4. Receives `Completed`/`Failed`/`TimedOut`/`Terminated` per contract.
5. Downloads large/sensitive output via a separate authorized endpoint.

### 10.2. Why Does Even the Starter Need Idempotency?

If the server creates an instance but the `202` response drops on the wire, the client retries `POST`. If every `POST` spins up a fresh instance, two workflows run.

Map `business ID → orchestration ID` protected by unique constraints or conditional writes, or derive deterministic business instance IDs while handling races/duplicates per SDK semantics. Never assume calling `start_new` with the same ID eliminates every race automatically.

### 10.3. Status Payload

~~~json
{
  "jobId": "report-001",
  "state": "Running",
  "progress": {
    "total": 1000,
    "completed": 780,
    "failed": 6
  },
  "resultReference": null
}
~~~

This schema belongs to your application. The Durable runtime exposes its own states and management APIs; translate them into domain states like `AwaitingApproval`, `PartialCompleted`, or `TimedOut` in your API/UI layer.

### 10.4. Governing Management URLs

`create_check_status_response` returns `statusQueryGetUri`, `sendEventPostUri`, `terminatePostUri`, `purgeHistoryDeleteUri`, or similar URLs depending on version. Some contain keys in query parameters. Never expose raw management URLs directly to arbitrary users—especially terminate, purge, or raise-event endpoints. Wrap them behind an Entra ID–authenticated API checking tenant job ownership.

## 11. Durable Timers: Waiting Without Sleeping

### 11.1. 15-Minute Wait Example

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def delayed_check(context: df.DurableOrchestrationContext):
    task_id = context.get_input()["taskId"]
    deadline = context.current_utc_datetime + timedelta(minutes=15)

    yield context.create_timer(deadline)
    result = yield context.call_activity("check_partner_status", task_id)
    return result
~~~

`check_partner_status` must be registered separately as an activity. While awaiting the timer, workflow state is persisted without holding a Python thread in a sleep loop.

### 11.2. Avoid `time.sleep`

Wrong inside an orchestrator:

~~~python
import time

def wrong_delay(context):
    time.sleep(900)
    return "done"
~~~

`time.sleep` pins the worker and breaks durable timer semantics. Even inside an activity, waiting hours or days violates invocation timeouts and wastes worker resources.

### 11.3. UTC and Deadlines

Compute deadlines inside orchestrators using `context.current_utc_datetime`, never `datetime.now`/`utcnow`. If a business deadline uses Vietnam time, convert accurately to UTC and store deadlines in an explicit schema.

When an external event and deadline arrive near each other, define clear timestamp precedence rules. Never let network races decide critical transactions.

## 12. Human Interaction: Approvals with Deadlines

### 12.1. Workflow

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Activity: prepare
    participant U as Approver
    participant E as Event API
    O->>A: Prepare report
    A-->>O: Report ID
    O->>U: Notify via activity
    O->>O: Wait external event or timer
    U->>E: Approve/Reject
    E->>O: DecisionReceived
    O->>O: Validate decision/state
    O-->>U: Approved / Rejected / TimedOut
~~~

Sending emails or notifications must happen in an activity; the orchestrator only schedules that activity.

### 12.2. Python Orchestration

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def approval_orchestrator(context: df.DurableOrchestrationContext):
    request_id = context.get_input()["requestId"]

    review = yield context.call_activity("prepare_review", request_id)
    yield context.call_activity("notify_approver", review)

    deadline = context.current_utc_datetime + timedelta(hours=48)
    decision_task = context.wait_for_external_event("DecisionReceived")
    timer_task = context.create_timer(deadline)

    winner = yield context.task_any([decision_task, timer_task])

    if winner == timer_task:
        return {"requestId": request_id, "status": "TimedOut"}

    timer_task.cancel()
    decision = decision_task.result

    if decision.get("approved") is True:
        yield context.call_activity("finalize_approved", request_id)
        return {"requestId": request_id, "status": "Approved"}

    return {"requestId": request_id, "status": "Rejected"}
~~~

Activities must be registered separately and idempotent. This shows orchestration logic without decision-ingress code. Handle late events, cancel pending tasks per SDK support, and guard against duplicate decisions.

### 12.3. Sending External Events Safely

Inside an authenticated API verifying the user is authorized to approve that request/tenant:

~~~python
await client.raise_event(
    instance_id,
    "DecisionReceived",
    {"approved": True},
)
~~~

**Never treat an instance ID as a secret or proof of authorization.** The API must verify:

- Does the sender hold the approver role?
- Does the request ID belong to the sender's tenant/project?
- Has the workflow already expired or been decided?
- Is the event a duplicate submission?
- Does the audit log record actor, UTC timestamp, and correlation ID?
- Is the payload free of credentials or unnecessary sensitive data?

If approval arrives right around the deadline, define tie-breaking rules and reconcile if external notifications or state transitions already fired.

### 12.4. Approval Flows Are Not Atomic Transactions

Suppose an approver clicks Approve, the API returns 200, and event delivery to the orchestrator is delayed. Client retries can send multiple events. Maintain an idempotent decision store and conditional business state transitions. Durable events **wake up orchestrations**—they need not serve as the sole legal/financial source of truth.

## 13. Monitor Pattern: Polling External Jobs

### 13.1. When No Webhook Exists

A partner returns a job ID and exposes a status polling API:

~~~text
POST /exports → {"jobId":"export-4242"}
GET /exports/export-4242 → {"state":"pending"}
GET /exports/export-4242 → {"state":"completed"}
~~~

Monitor pattern:

1. Activity polls status.
2. Completed → return result.
3. Failed → mark failure.
4. Pending → create durable timer.
5. Timer fires → poll again, timing out at the deadline.

### 13.2. Python Illustration

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def monitor_export(context: df.DurableOrchestrationContext):
    job_id = context.get_input()["jobId"]
    deadline = context.current_utc_datetime + timedelta(hours=6)

    while context.current_utc_datetime < deadline:
        status = yield context.call_activity("read_export_status", job_id)

        if status == "completed":
            return {"jobId": job_id, "status": "Completed"}
        if status == "failed":
            return {"jobId": job_id, "status": "Failed"}

        next_check = context.current_utc_datetime + timedelta(minutes=10)
        yield context.create_timer(next_check)

    return {"jobId": job_id, "status": "TimedOut"}
~~~

`read_export_status` is an activity calling the external API; never call it directly from the orchestrator. When secure external webhooks are available, external events eliminate unnecessary polling calls.

### 13.3. Pitfall: Unbounded Monitor Loops

Polling every minute for months bloats history continuously. Enforce deadlines, `maxAttempts`, stuck-job alerts, and `continue_as_new` or bounded lifecycles. Simple periodic schedules often belong in a `TimerTrigger` Function rather than an eternal orchestrator.

## 14. Continue-as-New and Long Iterative Workflows

### 14.1. Why Does History Grow?

Every scheduled/completed activity, timer/event, and output appends to event history. Across hundreds of thousands of iterations, replay slows down and storage transactions mount.

**`continue_as_new`** restarts the orchestration with fresh input while compacting history per runtime behavior. Example paginated processing:

~~~text
Round 1: cursor=0    → process 100 files → continue_as_new(cursor=100)
Round 2: cursor=100  → process 100 files → continue_as_new(cursor=200)
...
Round N: no more files → Completed
~~~

### 14.2. Pseudocode

~~~python
# PSEUDOCODE: assumes load_batch/process_item are registered.
@app.orchestration_trigger(context_name="context")
def incremental_workflow(context: df.DurableOrchestrationContext):
    state = context.get_input() or {"cursor": 0}
    batch = yield context.call_activity("load_batch", state["cursor"])

    if not batch["items"]:
        return {"status": "Completed", "cursor": state["cursor"]}

    tasks = [
        context.call_activity("process_item", item_id)
        for item_id in batch["items"]
    ]
    yield context.task_all(tasks)

    context.continue_as_new({"cursor": batch["nextCursor"]})
~~~

**Note:** advancing the cursor is safe only when batch items are durably persisted or retried idempotently. `continue_as_new` does not automatically guarantee external database commits succeeded.

### 14.3. Controls Needed

- Maximum batch count and overall deadline.
- Durable progress metadata, not just final output.
- Handling permanently failing items.
- Pending external events across history rollover: behavior varies by provider/SDK—test thoroughly.
- Governed cancel/terminate mechanisms.
- Code versioning across instances spanning multiple releases.
- State storage and logging costs.

### 14.4. Eternal Orchestrations

Timers + `continue_as_new` can implement long-running periodic monitors. Never leave them running forever without an owner, stop condition, alerts, and retention plan. Purely scheduled tasks usually fit `TimerTrigger` Functions better.

## 15. Sagas and Compensation for Multiple Side Effects

### 15.1. The Order Placement Problem

An order must reserve inventory, charge payment, and create a shipment. If shipment creation fails after payment succeeds, restarting from the top risks charging the customer twice.

~~~mermaid
flowchart TD
    O["Order Created"] --> A["Reserve inventory"]
    A --> P["Charge payment"]
    P --> S["Create shipment"]
    S -->|OK| D["Order Completed"]
    S -->|Fail| R["Refund payment"]
    R --> U["Release inventory"]
    U --> X["Failed / Manual review"]
~~~

### 15.2. Compensation Is Not Atomic Rollback

Refunds can take days, incur fees, expose intermediate states, or fail themselves. Therefore:

- Persist operation IDs and audit trails.
- Make compensation activities idempotent.
- Bound retries, then escalate to manual review.
- Never report completion before compensating steps satisfy policy.
- Never erase prior transaction history.

### 15.3. Pseudocode

~~~python
# PSEUDOCODE: activities must design idempotent side effects.
reserve = yield context.call_activity("reserve_inventory", order)

try:
    payment = yield context.call_activity("charge_payment", order)
    try:
        shipment = yield context.call_activity("create_shipment", order)
    except Exception:
        yield context.call_activity("refund_payment", payment)
        raise
except Exception:
    yield context.call_activity("release_inventory", reserve)
    raise
~~~

Production designs must also handle failing compensations and prevent running compensation twice. Database transactions, financial reconciliation, and external API rules must be modeled explicitly.

## 16. Versioning While Instances Are Running

### 16.1. Changing Orchestrator Code Can Break Replay

An instance started on v1 may replay on newly deployed v2 code. If v2 inserts an activity mid-history or breaks deterministic flow, the runtime hits nondeterminism errors.

~~~text
Version 1: A → B → C
Version 2: A → NEW → B → C
~~~

If a v1 instance finished A and is awaiting B, switching directly to v2 without versioning generates a sequence mismatching saved history.

### 16.2. Strategies

1. Introduce new orchestrator names like `ProcessInvoicesV2` for breaking flow changes.
2. Keep v1 code deployed until running v1 instances finish, per deployment policy.
3. Include version fields in inputs so branching stays deterministic.
4. Keep activity input/output schemas compatible.
5. Test replay against live-like long-waiting instances in staging.
6. Tag build SHAs and deployment dates.
7. Use official Durable runtime versioning/deployment features where supported.

Never branch replay decisions off a mutable `CURRENT_VERSION` app setting that changes post-deploy and alters paths already taken in history.

### 16.3. Backward-Compatible Results

~~~json
{
  "schemaVersion": 2,
  "documentId": "invoice-001",
  "status": "processed",
  "resultRef": "results/invoice-001.json"
}
~~~

Provide defaults for new fields and drop old fields only after all older running orchestrators have drained.

## 17. Protecting State Storage and Data

### 17.1. What Can Live in History?

Depending on provider/extension, history can store:

- Orchestration inputs and outputs.
- Activity inputs and return values.
- Timer and external event payloads.
- Failure details and exception metadata.
- Custom status and runtime instance metadata.

Therefore, **never pass raw customer documents, sensitive PII/secrets, access tokens, or long-lived SAS URIs** through orchestrations. Pass IDs/Blob paths; let activities use managed identity to read real data.

### 17.2. Pass References Instead of Large Payloads

Avoid:

~~~json
{
  "documents": [
    {"id":"001","contentBase64":"<SEVERAL_MB_OF_DATA>"}
  ]
}
~~~

Prefer:

~~~json
{
  "jobId":"job-001",
  "documentRefs":[
    {"id":"001","blobPath":"incoming/job-001/001.pdf"}
  ]
}
~~~

Activities must validate input IDs and tenant ownership before reading blobs—never trust a path blindly just because it appeared in a request.

### 17.3. Task Hub Permissions

When using the Azure Storage provider:

- Configure `AzureWebJobsStorage`/provider per runtime and hosting plan.
- Grant required Blob/Queue/Table permissions for the Functions host/extension.
- Prefer managed identity where supported by provider and hosting, avoiding account keys when possible.
- Configure VNet, Private Endpoints, and DNS properly.
- Isolate task hubs so unrelated environments never share state.
- Restrict read/delete access to state stores and logs.
- Monitor usage, throttling, and retention.

Never delete Durable provider queues or tables to "clear logs" while active instances remain.

### 17.4. Purging History

Durable APIs can purge history after instances terminate or complete per supported rules. Purging is destructive and must follow retention, privacy, and audit policies. Never treat purging as a safe fix for a stuck workflow—investigate and plan recovery first.

## 18. Security for HTTP, Events, and Identities

| Surface | Risk | Control |
|---|---|---|
| HTTP starter | Callers spawn thousands of costly jobs | Entra auth, authorization, quotas/rate limits |
| Status/management URLs | Anyone holding URL/key views or controls jobs | Authenticated wrapper API; never leak keys |
| External event API | Attackers forge approvals | Identity verification, roles, tenant ownership, audit |
| Activities | Secret leaks, overly broad permissions | Managed identity, Key Vault, least-privilege RBAC |
| Task hub storage | Unauthorized history reads or deletion | Storage encryption, RBAC, networking, retention |
| CI/CD | Unapproved code deployed to production | OIDC/WIF, approvals, branch protection |
| Logs | PII, access tokens, payloads recorded | Data minimization and strict access controls |
| Retries | Duplicate transactions | Idempotency/deduplication |

**Function keys do not replace business authorization.** A management URL carrying a key in its query string never proves user job ownership. In multi-tenant apps, verify caller identity and tenant ownership on every job.

Separate identities:

- Caller starting the job.
- Function managed identity accessing Storage/Key Vault.
- Approver identity.
- CI/CD deployment identity.
- External partner APIs or service accounts.

Never grant Owner across all roles. Activities within the same Function App share its managed identity; if strict permission boundaries are required, split into separate apps or supported isolation boundaries.

## 19. Monitoring and Troubleshooting

### 19.1. Track Both Technical and Business State

| Field | Purpose |
|---|---|
| `businessJobId` | Business-level lookup |
| `durableInstanceId` | State/history lookup |
| `orchestrationVersion` | Track replay and versioning |
| `currentStage` | Fan-out, fan-in, approval, or finalize |
| `state` | Running, Completed, Failed, Terminated... |
| `total/completed/failed` | Execution progress |
| `createdAtUtc/updatedAtUtc` | SLA and job age |
| `correlationId` | Cross-service tracing |
| `outputRef` | Safe output location |
| `errorCode` | Failure classification |
| `taskHub/environment` | Separate dev, staging, prod |

Use SDK `customStatus` for high-level progress summaries; avoid storing large payloads or spamming updates purely for UI polling.

### 19.2. Telemetry Sources

- Azure Functions host logs.
- Application Insights: requests, exceptions, dependencies, traces.
- Durable instance management/status APIs.
- Storage/task hub provider metrics and queue diagnostics.
- Azure Monitor alerts.
- Key Vault, Storage, and Entra logs.
- CI/CD release records.
- Business metrics: SLAs, completed jobs, side effects, and reconciliation.

Never assume Azure Activity Log captures every Durable runtime action or Blob read; enable data-plane logging where needed and govern retention.

### 19.3. Illustrative KQL

For workspace-based Application Insights with `AppExceptions`:

~~~kusto
AppExceptions
| where TimeGenerated > ago(1h)
| summarize Failures = count()
  by bin(TimeGenerated, 5m), ProblemId
| order by TimeGenerated asc
~~~

For `AppRequests`:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize Requests = count(),
            Failed = countif(Success == false),
            P95ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

Exact table and column names depend on telemetry settings and active schemas. Empty query results do not prove zero errors if logs are not being ingested.

### 19.4. Useful Alerts

- Jobs staying `Running` past SLA or making zero progress.
- Rising failed orchestrations or activity failures.
- Unusual spikes in 429/503 responses or retries.
- Task hub queue backlogs or storage throttling.
- Overdue approvals and late external events.
- Rising p95 activity latency.
- Spikes in storage transaction, Functions, or Log Analytics costs.
- Nondeterministic errors spiking right after a deployment.
- Drops in telemetry ingestion or abnormal external events.

`Running` while legitimately awaiting approval is not stuck; alerts must account for **`currentStage` and deadlines**.

## 20. Scale and Cost

### 20.1. Sources of Bottlenecks

- Worker/instance counts under the hosting plan.
- `maxConcurrentActivityFunctions` and version-specific runtime caps.
- Task hub backend capacity, queues, and partitions.
- Activity CPU and memory.
- History and payload sizes.
- Downstream API quotas and DB connection limits.
- Cold starts and scale-out speed.
- Networking/Private Endpoints and token acquisition.

An orchestrator should strictly orchestrate. To aggregate gigabytes of data, use activities or dedicated data processing services—never stuff raw datasets into orchestration history.

### 20.2. Estimation Example

With 2,000 documents taking ~3 seconds each and an API capped at 40 concurrent calls:

- Sequential ideal time: ~6,000 seconds.
- At 40 concurrency ideal: ~50 waves × 3 seconds = 150 seconds.
- Real world adds storage, queues, networking, cold starts, retries, and aggregation.
- Firing all 2,000 requests at once causes 429s, failures, and higher cost.

This is an illustrative math model, **not an Azure benchmark or SLA**.

### 20.3. End-to-End Cost Drivers

- Functions invocations, duration, and plan resources.
- Storage/task hub messages, transactions, and retention.
- Key Vault operations, Blobs, Queues, and Service Bus.
- Application Insights/Log Analytics ingestion and retention.
- Network egress and Private Endpoints.
- Partner API per-request or token fees.
- Retries multiplying call counts.
- Always-ready or provisioned capacity charges where used.

Durable timers do not pin threads while waiting, yet **waiting does not mean zero cost**. Storage, telemetry, and plan baselines can still accrue charges.

## 21. Real-World Scenario: 10,000 Invoices Requiring Approval

### 21.1. Context

An enterprise needs to:

1. List 10,000 new invoices from Blob Storage.
2. Split into batches and analyze each file.
3. Persist per-invoice results.
4. Aggregate a summary report and list errors requiring attention.
5. Notify a manager.
6. Wait up to 48 hours for approval.
7. If Approved, publish the report; if Rejected/TimedOut, hold and mark status.

### 21.2. Architecture

~~~mermaid
flowchart TD
    U["Portal/API"] --> H["HTTP Starter 202"]
    H --> P["Parent Durable Orchestrator"]
    P --> L["List document refs"]
    L --> B["Batched sub-orchestrations"]
    B --> A1["Analyze A"]
    B --> A2["Analyze B"]
    B --> A3["Analyze C"]
    A1 --> F["Batch fan-in"]
    A2 --> F
    A3 --> F
    F --> D["Write output Blob/DB"]
    D --> G["Global summary"]
    G --> N["Notify approver"]
    N --> W["External event or 48h timer"]
    W -->|Approved| R["Publish"]
    W -->|Rejected/Timeout| X["Hold + audit"]
~~~

### 21.3. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Orchestration input | Job ID and Blob IDs | Keeps history compact |
| Fan-out | Bounded batches | Prevents activity/API storms |
| Activity output | Metadata and `resultRef` | Excludes large PDFs |
| Retries | Bounded 429/503 retries | Protects quotas |
| Deduplication | `(jobId, invoiceId, operation)` | Prevents duplicate side effects |
| Fan-in | Per-batch then global summary | Clean observability |
| Human approval | External event + 48h timer | Long waits without pinning threads |
| Business status | Approved / Rejected / TimedOut | Clear domain state |
| Versioning | Maintain v1/v2 compatibility | Replay safety |
| Security | Entra, managed identity, RBAC, private networking | Strict access control |
| Observability | App Insights + business progress | Tracks SLAs |
| Retention | Governed by data/history policy | Privacy and cost control |

### 21.4. Acceptance Tests

- Restart Function App while waiting on an activity or timer; instance resumes from runtime state.
- When one activity fails, retry and partial-failure policy behave as designed.
- Zero duplicate invoices if HTTP callers retry or activities re-run.
- Approval arriving before deadline succeeds; arrival after deadline does not auto-publish.
- Unauthorized users without the approver role cannot raise approval events.
- Zero raw PDFs or access tokens appear in history or logs.
- Deploying v2 code does not break in-flight v1 instances.
- Cost metrics, SLA alerts, and cleanup/retention policies are active.
- When downstream fails, reconciliation and manual intervention workflows work.

## 22. Common Failures Reference Table

| Symptom | Possible Cause | Inspection Steps |
|---|---|---|
| Starter returns 500 | Durable binding, host storage, or runtime error | Host logs, storage connection, packages |
| `202` returned but job never advances | Task hub/queues or workers not processing | Instance status, provider diagnostics |
| Activity runs twice | Retries, redelivery, or duplicate starter calls | Operation ID, dedup store, history |
| Orchestrator nondeterministic error | Direct time/random/I/O or unversioned code change | Replay constraints, versioning |
| Duplicate orchestrator logs | Replay | `context.is_replaying` and log design |
| Fan-in hangs forever | Activity stuck/failing or quota exhaustion | Failed tasks, queue backlogs, timeouts |
| Heavy 429s | Downstream throttling | Batch size, retries, and concurrency caps |
| Bloated state/history | Large payloads or huge fan-outs | Blob references and batching |
| Approval never received | Wrong instance/event, auth error, instance already closed | Event API logs, status, correlation |
| Wrong deadline | Local clock/timezone confusion | Logical UTC and timers |
| Code upgrade breaks older jobs | Incompatible orchestrator edits | Versioning and deployment records |
| Storage 403 | Identity lacks permissions or firewall/DNS block | Data-plane RBAC and networking |
| Management URL leaked | Keys exposed in query strings or logs | Revoke keys, wrap behind auth API |
| Terminated yet activity still mutates state | Terminate does not cancel already-running side effects | Cooperative cancellation and reconciliation |
| Cleanup wipes active instances | Deleted wrong task hub/history | Retention policies and backup/recovery |
| Sudden cost spike | Runaway retries, fan-out, or log volume | Budgets, usage metrics, backpressure |

### 22.1. Investigation Workflow

1. Verify caller, request ID, and instance ID.
2. Check host, runtime, and extension versions.
3. Inspect task hub/provider health, Storage permissions, and networking.
4. Identify which activity, timer, or event the instance awaits.
5. Review error codes, retries, and downstream quotas.
6. Inspect history/replay and deployed code version.
7. Reconcile business side effects before blindly retrying the entire job.
8. Verify outputs and data reconciliation.
9. File incident notes, rollback/change tickets, and improve alerts.

**`Terminate` does not automatically undo a payment, unsent email, or an in-flight activity.** When cancellation is needed, implement cooperative cancellation flags/state checked at checkpoints plus compensation where appropriate.

## 23. Production Checklist

### Workflow

- [ ] Confirmed stateful orchestration is genuinely needed rather than independent queue consumers.
- [ ] Mapped orchestrator, activities, sub-orchestrations, timers, and events.
- [ ] Defined all-or-nothing vs. partial fan-in policy.
- [ ] Sized fan-out batches and concurrency to downstream quotas.
- [ ] Activities implement bounded retries and idempotency.
- [ ] Timeouts/deadlines replace long sleeps inside orchestrators.
- [ ] Duplicate and late external events are handled cleanly.
- [ ] `continue_as_new` or batching bounds long histories where needed.
- [ ] Versioning protects in-flight instances across releases.
- [ ] Cancellation and compensation workflows exist.

### Security and Data

- [ ] Starter, status, and event APIs enforce authentication and authorization.
- [ ] Management URLs and keys never leak to logs or frontends.
- [ ] Orchestration inputs/outputs stay small, with no secrets or bulky PII.
- [ ] Task hub Storage has proper RBAC, networking, and retention.
- [ ] Managed identities and Key Vault protect downstream calls.
- [ ] Operation IDs and event IDs are deduplicated.
- [ ] CI/CD roles and business approver roles are separated.
- [ ] Audit logs exclude tokens and sensitive payloads.

### Testing

- [ ] Tested 1, dozens, and hundreds of activities in a lab.
- [ ] Tested partial failures, 429s, timeouts, and retries.
- [ ] Tested restarts and scale-in while awaiting timers/events.
- [ ] Tested approvals before deadline, after deadline, and duplicates.
- [ ] Tested caller retries after dropped `202` responses.
- [ ] Tested deploying v2 while v1 instances remain `Running`.
- [ ] Tested terminating while activities hold side effects.
- [ ] Measured storage transactions, history sizes, and latency.
- [ ] Prepared code rollback and data reconciliation plans.

### Operations

- [ ] Dashboards track Running/Completed/Failed/TimedOut and business stages.
- [ ] Alerts watch stalled jobs, API throttling, backlogs, and overdue approvals.
- [ ] Runbooks cover identity, storage, provider, and networking issues.
- [ ] Clear ownership exists for workflows and manual intervention.
- [ ] Costs tracked across Functions, Storage, Monitor, and downstream services.
- [ ] History purging runs only under approved retention rules.
- [ ] Capacity and rate-limit plans have been load tested.

## 24. Knowledge Self-Check

1. **Why shouldn't an HTTP Function hold a connection open for two days?** Timeouts and worker lifecycles lack durable state.
2. **What does Durable Functions add?** Stateful orchestration, history/replay, durable timers, and external events.
3. **How do orchestrators and activities differ?** Coordinating decisions vs. performing I/O and side effects.
4. **What is fan-out?** Splitting a list into multiple independent activities.
5. **What is fan-in?** Awaiting and aggregating results per policy.
6. **Does `task_all` guarantee 500 activities execute simultaneously?** No.
7. **If one activity fails, what can fan-in do?** Fail, retry, or return partial results depending on design.
8. **Why is idempotency needed?** Activities can retry or redeliver after a side effect already ran.
9. **Is exactly-once automatically guaranteed for external APIs?** No.
10. **Why does `datetime.now` break orchestrators?** It is non-deterministic across replays.
11. **What replaces `time.sleep`?** `context.create_timer` with logical UTC.
12. **What awaits human approval?** `wait_for_external_event` paired with a timer and `task_any`.
13. **Do external events automatically authenticate approvers?** No; the ingress API must enforce auth.
14. **Why return `202`?** Decouples the request from long work and lets clients poll status.
15. **Why guard against duplicate POSTs at the starter?** Dropped responses prompt caller retries that spawn duplicate instances.
16. **How does `continue_as_new` help?** Continues loops with compacted history.
17. **How does the monitor pattern work?** Activity checks status, durable timer waits, looping until a deadline.
18. **How do sub-orchestrations help?** Break workflows into smaller isolated stateful units.
19. **Is saga compensation an atomic DB rollback?** No, it is business-level compensating actions that can fail themselves.
20. **Why can deploying v2 break v1 instances?** Replay requires decision logic compatible with existing history.
21. **Should raw PDFs sit inside orchestration input?** No; pass Blob references.
22. **What must task hub storage protect?** State, history, messages, credentials, and retention.
23. **Do function keys replace business authorization?** No.
24. **Does `Terminate` undo already-executed transactions?** No.
25. **Why are global rate limits needed?** Many scaled-out workers can jointly exceed downstream quotas.
26. **Is `Running` while awaiting approval always stuck?** No—it depends on stage and deadline.
27. **Do costs come solely from execution time?** No; storage, logs, networking, retries, and downstream services add costs.
28. **Can large fan-outs be replaced by independent queues?** Yes, if no fan-in aggregation is needed.
29. **How do you investigate duplicates?** Check business/operation IDs, history, retries, and API logs.
30. **What does a reliable long-running workflow require?** Deterministic orchestration, idempotent activities, bounded retries, secured events, monitoring, versioning, and recovery plans.

## 25. References

- [Durable Functions overview](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview) — concepts and patterns.
- [Durable Functions application patterns](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview#application-patterns) — async HTTP, fan-out/fan-in, monitor, human interaction.
- [Fan-out/fan-in example](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-cloud-backup) — splitting and aggregating work.
- [Python programming model v2](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-python-v2-programming-model) — decorators, clients, orchestrators, activities.
- [Orchestrator code constraints](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-code-constraints) — determinism and replay.
- [Durable HTTP APIs](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-http-api) — instance management, events, and status.
- [Durable timers](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-timers) — durable waits.
- [External events](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-external-events) — human interaction and callbacks.
- [Error handling](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-error-handling) — retries and failures.
- [Performance and scale](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-perf-and-scale) — concurrency and partitioning.
- [Durable Functions versioning](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-versioning) — code changes and long-running instances.
- [Storage providers](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-storage-providers) — state and task hubs.
- [Durable Functions diagnostics](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-diagnostics) — logging and tracing.
- [Azure Functions hosting](https://learn.microsoft.com/azure/azure-functions/functions-scale) — hosting plans, scale, and cost.
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — runtime identity.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — cost control.

**Conclusion:** fan-out/fan-in splits work into independent activities and aggregates outcomes; Durable Functions preserves state and history to coordinate long-running workflows without holding HTTP connections open. Safe production adoption demands **deterministic orchestrators, idempotent activities, bounded retries, small payloads, authorized external events, versioning for active instances, monitoring, and compensation/recovery plans**. A successful workflow means more than a `Completed` status—it must prove zero duplicate transactions, survive restarts, and recover cleanly when dependencies fail.
