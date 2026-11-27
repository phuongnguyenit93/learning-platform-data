# Choosing Pub/Sub, Cloud Tasks, Scheduler, or Workflows on Google Cloud

A retail system uses **Cloud Run** for its orders API, **GKE** for workers, **Cloud SQL** to store transactions, and **Cloud Storage** to hold reports. When an order is created, the system must broadcast an event to multiple departments; after 15 minutes it must remind unpaid customers; every night it must aggregate revenue; and a refund flow must sequentially verify the order, call the payment gateway, and update status. All four requirements involve asynchrony, yet **none should be forced into the same service**.

Google Cloud offers four complementary options: **Pub/Sub** distributes events, **Cloud Tasks** queues explicit task invocations, **Cloud Scheduler** triggers on recurring schedules, and **Workflows** orchestrates stateful multi-step processes. This lesson belongs to the **Application Orchestration and Integration** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting service selection with IAM, VPC, deployment, reliability, and cost. The material is self-contained, focusing on how to **make decisions, configure, and operate**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose the right service for **event fan-out, HTTP tasks, cron**, or **multi-step processes**.
2. Distinguish publisher/subscriber, task producer/handler, scheduler/target, and workflow/execution.
3. Understand **at-least-once** semantics, retries, deduplication, idempotency, rate limits, and ordering capabilities of each service.
4. Write `gcloud` examples to create topics/subscriptions, task queues, cron jobs, and deploy Workflows.
5. Separate identities for **the initiator, the delivery service, and the application runtime service account**.
6. Design architectures combining these services, set SLOs, and measure backlog, errors, latency, and cost.

## 2. Four Services Answering Four Different Questions

| Service | Primary Question | Unit of Work | Model |
| --- | --- | --- | --- |
| **Pub/Sub** | "An event happened—whoever cares, process it?" | Message on a topic, delivered to subscriptions. | **Event distribution**, one-to-many, asynchronous. |
| **Cloud Tasks** | "Invoke this endpoint, controlling timing/rate/retries." | Task in a queue, with an HTTP target or supported target. | **Explicit task invocation**, producer knows target. |
| **Cloud Scheduler** | "At this time / every day, trigger the job." | Cron job and a single dispatch to a target. | **Recurring trigger**; does not run business logic itself. |
| **Workflows** | "Call A, read the result, decide whether to call B, then await C." | Workflow definition and execution composed of steps. | **Stateful orchestration**, sequential/branching/parallel. |

Visualization:

~~~mermaid
flowchart LR
    E["Order created"] --> PUB["Pub/Sub topic"]
    PUB --> BILL["Subscription: invoicing"]
    PUB --> ANALYTICS["Subscription: analytics"]
    E --> TASKS["Cloud Tasks queue"]
    TASKS --> REMIND["Cloud Run: send payment reminder"]
    CRON["Cloud Scheduler: 02:00 daily"] --> FLOW["Workflows: reconciliation"]
    FLOW --> FETCH["Cloud Run: fetch data"]
    FETCH --> REPORT["Cloud Run/BigQuery: build report"]
~~~

One product can appear in **multiple branches** of the same system. There is no rule saying "a system may pick only one of the four".

## 3. Decision Matrix

### 3.1. Choosing by Dominant Requirement

| Requirement | First Candidate to Evaluate | Why |
| --- | --- | --- |
| One event must reach 3–10 independent consumers. | **Pub/Sub** | Each subscription has its own backlog, acks, and independent scaling. |
| Send HTTP commands to one worker, capped at 20 requests/second. | **Cloud Tasks** | Queue throttles dispatch rate and concurrent in-flight tasks. |
| Run nightly backup/aggregation on a cron schedule. | **Cloud Scheduler** | Triggers at configured hours and timezones. |
| Call an API back at a unique time per individual order. | **Cloud Tasks** with `scheduleTime`. | **Per-task one-time** schedule, unlike recurring cron. |
| Verify payment → allocate stock → notify; needs branching and error handling. | **Workflows** | Persists execution state and step outcomes. |
| Sync millions of records with many consumers processing in parallel. | **Pub/Sub** or suitable batch solution. | Workflows is not an ultra-high-throughput per-record engine. |
| Launch a multi-step process every day. | **Scheduler → Workflows** | Scheduler owns the schedule; Workflows owns execution sequence. |
| An event must trigger a multi-step process. | **Pub/Sub/Eventarc → Workflows** | Event emission layer separated from orchestration layer. |
| Partner API accepts at most 5 concurrent requests. | **Cloud Tasks → HTTP handler** | Throttles before the call site with configurable retries. |

### 3.2. Quick Decision Tree

~~~mermaid
flowchart TD
    A["What triggers the work?"] --> B{"Fixed recurring time?"}
    B -- "Yes" --> SCH["Cloud Scheduler"]
    B -- "No" --> C{"Multiple dependent steps,\n needing state/branching?"}
    C -- "Yes" --> WF["Workflows"]
    C -- "No" --> D{"Event has multiple independent\n consumers?"}
    D -- "Yes" --> PS["Pub/Sub"]
    D -- "No" --> E{"Call a specific endpoint,\n needing rate limits or delay?"}
    E -- "Yes" --> CT["Cloud Tasks"]
    E -- "No" --> F["Consider Pub/Sub or direct call\n per durability and coupling needs"]
    SCH -. "Can trigger" .-> WF
    SCH -. "Can publish" .-> PS
    PS -. "Can start" .-> WF
~~~

This is a **heuristic**, not an absolute feature matrix. For instance, Pub/Sub also has HTTP **push subscriptions**, and Cloud Tasks also has retries. The core distinction is **event distribution with self-subscribing consumers** versus **explicit invocation of a producer-chosen endpoint**.

## 4. Pub/Sub: "One Event, Many Interested Parties"

### 4.1. Publishers Do Not Need to Know Subscribers

~~~text
Cloud Run orders-api → topic orders-events
   ├── invoices-sub   → GKE invoice worker
   ├── inventory-sub  → Cloud Run inventory handler
   └── analytics-sub  → analytics pipeline
~~~

Each subscription receives and acknowledges messages **independently**. If `analytics-sub` slows down, it builds its own backlog; acks on `invoices-sub` never cause analytics to lose pending messages. You can use **pull/StreamingPull**, **push**, or export subscriptions as supported by the product.

**Good fit when:** event-driven integration, fan-out, decoupled consumer deployment lifecycles, high throughput needs. **Not the first choice when:** the publisher must target a specific HTTP endpoint, delay individual calls, or enforce strict dispatch caps on a single downstream.

### 4.2. Delivery Semantics and Errors

- By default Pub/Sub is **at-least-once**; subscribers must handle duplicate messages.
- Messages not acknowledged within the **ack deadline** may be redelivered; client libraries support lease extension.
- **Ordering keys** can preserve order per key under supported conditions, without creating a global total order across all messages.
- **Exactly-once delivery** is conditionally supported on pull subscriptions and does not equal *exactly-once database writes*.
- Subscriptions offer **retention**, retry policies, dead-letter topics, and metrics for backlog/oldest unacked age.

Pub/Sub cannot know whether a Cloud SQL transaction committed. Handlers should **commit durably before acking**, combining unique constraints and idempotency.

### 4.3. `gcloud` Example: Fan-Out

Commands below use Bash and must **only run in an authorized lab project**. `create`/`publish` commands mutate resources or data and may incur charges.

~~~bash
PROJECT_ID="retail-lab"
TOPIC="orders-events-lab"

# WRITE: create event source.
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID"

# WRITE: each consumer gets its own subscription.
gcloud pubsub subscriptions create invoices-sub-lab \
  --topic="$TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions create analytics-sub-lab \
  --topic="$TOPIC" --project="$PROJECT_ID"

# WRITE: publish a hypothetical event.
gcloud pubsub topics publish "$TOPIC" \
  --message='{"eventId":"evt-101","orderId":"O-1001"}' \
  --attribute=type=order.created \
  --project="$PROJECT_ID"

# READ-ONLY: inspect metadata for each subscription.
gcloud pubsub subscriptions describe invoices-sub-lab \
  --project="$PROJECT_ID"
~~~

To read messages you can use `gcloud pubsub subscriptions pull`; **never use `--auto-ack` on a production subscription** before business processing completes. Design Publisher/Subscriber IAM, retention, and DLQs before handling real data.

## 5. Cloud Tasks: "Call This Endpoint at a Controlled Pace"

### 5.1. Tasks Differ from Event Messages

A Cloud Tasks **HTTP task** specifies a **URL**, HTTP method, body/headers, earliest first-attempt time, and optional authentication. A queue enforces **dispatches/second**, **concurrent dispatches**, and a retry policy.

Example job "send confirmation email for order `O-1001`":

~~~text
orders-api → Cloud Tasks queue: send-email
                      |
                 rate limit + retries
                      |
                      v
             Cloud Run /tasks/send-email
                      |
                Email provider API
~~~

**Difference from Pub/Sub:** the producer targets **one specific handler** rather than broadcasting to self-registered consumers. Cloud Tasks **does not guarantee strict ordering**; tasks in a queue do not become a FIFO business workflow simply by being enqueued in order.

### 5.2. Three Load-Management Controls

| Property | Effect | What to Avoid |
| --- | --- | --- |
| `max-dispatches-per-second` | Throttles dispatch rate to the handler. | Do not mistake it for a global cap across calls outside Cloud Tasks. |
| `max-concurrent-dispatches` | Caps simultaneous in-flight tasks from the queue. | Do not ignore Cloud Run concurrency and DB/API capacity. |
| Retry/backoff | Retries failed HTTP responses/timeouts per config. | Retries cannot make non-idempotent business logic safe. |

A task can be scheduled for an **individual execution time** using `scheduleTime`. This **is not recurring cron**: once the task completes, Cloud Tasks does not automatically spawn a new task the next day.

### 5.3. `gcloud` Example: Queue → Cloud Run

Assume an authenticated Cloud Run service `send-email`, its real service URL, and a service account holding `roles/run.invoker` already exist. Use the service's default `run.app` hostname as the HTTP target per Cloud Tasks guidance; replace placeholders before running.

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
QUEUE="email-queue-lab"
RUN_URL="https://REPLACE_WITH_DEFAULT_RUN_APP_URL"
CALLER_SA="tasks-invoker@retail-lab.iam.gserviceaccount.com"

# WRITE: create a queue with low dispatch limits for the lab.
gcloud tasks queues create "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --max-dispatches-per-second=5 \
  --max-concurrent-dispatches=3 \
  --max-attempts=5

# WRITE: create an HTTP task calling Cloud Run using OIDC service identity.
gcloud tasks create-http-task email-O-1001-lab \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE" \
  --url="${RUN_URL}/tasks/send-email" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"orderId":"O-1001"}' \
  --oidc-service-account-email="$CALLER_SA" \
  --oidc-token-audience="$RUN_URL"

# READ-ONLY: verify queue config and any still-pending tasks.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
gcloud tasks tasks list --queue="$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Prerequisites:** Cloud Tasks API is enabled; the task creator holds required permissions including `iam.serviceAccounts.actAs` on the token-signing service account; Cloud Run permits that service account to invoke it. Queues can dispatch very quickly, so a newly created task **may already be gone** from `tasks list`. `--oidc-token-audience` should be the **root URL of the Cloud Run service** (without paths) if the backend uses default audience validation.

### 5.4. Dedup Is Not Exactly-Once

If you assign a fixed **task ID**, Cloud Tasks can reject duplicate task creation while the task exists or was recently completed/deleted within the service's supported **deduplication window**. However:

- Task ID dedup is **task-creation dedup**; it does not prevent all HTTP delivery retries.
- The handler can still receive the request multiple times after timeouts or network errors.
- Fixed task IDs carry lookup overhead and affect task-creation latency; pick naming conventions intentionally.
- Never rely on Cloud Tasks to guarantee a financial transaction "charges only once" if the backend lacks idempotency.

HTTP handlers should validate IAM/OIDC, validate payloads, commit results idempotently, and **return HTTP 2xx only after durable completion**. Transient errors return retryable statuses; permanent errors need persistence/quarantine management to avoid futile loops.

## 6. Cloud Scheduler: "On Schedule, Trigger the Work"

### 6.1. Cron Does Not Execute Work Inside Scheduler

Cloud Scheduler takes a **cron schedule**, timezone, and target:

- **HTTP(S) endpoint**, e.g. Cloud Run or Workflows Executions API.
- **Pub/Sub topic** to publish a trigger message.
- **App Engine HTTP target** in applicable environments.

Scheduler only sends a **scheduled request/message**, while the target executes business logic. Scheduler provides **at-least-once delivery**; the same cron interval can produce multiple attempts, so targets still require **idempotency**.

~~~text
02:00 UTC daily
  → Scheduler job
      → Pub/Sub topic daily-reports
          → report workers
~~~

### 6.2. Cron, Timezones, and Daylight Saving

Cron `0 2 * * *` means **02:00 daily in the configured timezone**, not Vietnam time by default. For instance, `--time-zone="Asia/Ho_Chi_Minh"` runs in Vietnam time; in DST regions, clock shifts can cause certain hours to repeat or skip. For schedules demanding strict temporal consistency, consider **UTC**.

Several common schedules:

| Expression | Meaning in Job's Timezone |
| --- | --- |
| `0 2 * * *` | Daily at 02:00. |
| `0 9 * * 1` | Mondays at 09:00. |
| `0 0 1 * *` | Monthly at 00:00 on the 1st. |
| `0 0 * * 0` | Sundays at 00:00. |

If a run is slow or retries run long, the next scheduled interval can be affected under Scheduler semantics; **never design assuming every cron fires at exact wall-clock precision**.

### 6.3. `gcloud` Example: Cron → Pub/Sub

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
TOPIC="daily-reports-lab"

# WRITE: the test topic must exist before creating the Scheduler job.
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID"

# WRITE: daily at 02:00 Vietnam time, publish an aggregation command.
gcloud scheduler jobs create pubsub daily-report-lab \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --schedule="0 2 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --topic="$TOPIC" \
  --message-body='{"job":"daily-report","schemaVersion":1}'

# READ-ONLY: inspect schedule and target.
gcloud scheduler jobs describe daily-report-lab \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Required APIs, IAM/service agents, and regions must be prepared. **Never try creating a job directly targeting a Cloud Tasks queue assuming "Scheduler has a Cloud Tasks target"**; typical patterns are Scheduler → Pub/Sub/HTTP endpoint → producer creates tasks, or Scheduler → Workflows. When creating an HTTP job calling Cloud Run, use an **OIDC service account** and grant `roles/run.invoker` on the target service.

### 6.4. Preventing Re-Runs for the Same Cron Interval

For HTTP targets using unix-cron, Cloud Scheduler sends headers like `X-CloudScheduler-JobName` and `X-CloudScheduler-ScheduleTime`; combine them as a business key to prevent duplicates for a scheduled interval. For Pub/Sub targets, derive the interval key reliably from **payload and business date**, never a static string shared across all days.

For example, the report for 2026-11-19 needs key `daily-report:2026-11-19`. On retries or manual runs, the handler checks the key in durable storage to avoid sending reports or posting ledger entries twice.

## 7. Workflows: "One Execution Traversing Multiple Steps"

### 7.1. Stateful Orchestration

**Workflows** describes flows in YAML/JSON: each step can call an HTTP endpoint/Google Cloud API, read results, assign variables, branch, loop, catch exceptions, or run in parallel. An **execution** has an ID and state; Workflows can **wait** without keeping a VM or container running continuously. Per Google Cloud docs, Workflows can wait/poll/callback for **up to one year**, subject to quotas and limits.

~~~mermaid
flowchart LR
    START["Start refund"] --> CHECK["Check order"]
    CHECK --> VALID{"Valid?"}
    VALID -- "No" --> STOP["End / report error"]
    VALID -- "Yes" --> PAY["Call payment gateway"]
    PAY --> DB["Update order status"]
    DB --> NOTI["Send notification"]
~~~

**Workflows fits when:** step order and individual results matter, intentional retries are needed, waiting on systems is required, or multiple APIs are coordinated. **Poor fit when:** simply broadcasting a basic event or iterating over millions of tiny records in one giant execution loop.

### 7.2. Workflows YAML Example Calling Two Cloud Run Services

Example file `order-fulfillment.yaml` in a lab directory (not created in this lesson's workspace). Replace placeholder URLs with **real Cloud Run HTTPS URLs**, deploy the services beforehand, and grant `roles/run.invoker` to the **workflow runtime service account**.

~~~yaml
main:
  params: [args]
  steps:
    - reserveInventory:
        call: http.post
        args:
          url: https://REPLACE_WITH_INVENTORY_RUN_URL/reserve
          auth:
            type: OIDC
            audience: https://REPLACE_WITH_INVENTORY_RUN_URL
          body:
            orderId: ${args.orderId}
        result: reservation

    - confirmOrder:
        call: http.post
        args:
          url: https://REPLACE_WITH_ORDERS_RUN_URL/confirm
          auth:
            type: OIDC
            audience: https://REPLACE_WITH_ORDERS_RUN_URL
          body:
            orderId: ${args.orderId}
            reservationId: ${reservation.body.reservationId}
        result: confirmation

    - done:
        return:
          orderId: ${args.orderId}
          status: ${confirmation.body.status}
~~~

This YAML illustrates the **happy path**, assuming Cloud Run `reserve` returns JSON containing `reservationId` and `confirm` returns `status`. It **does not yet** include error validation, retries, timeouts, compensation, or business authorization; add those before production. When Workflows calls Cloud Run, `auth: {type: OIDC}` mints an identity token using the workflow SA; `audience` must match the accepted backend Cloud Run service URL without appending paths.

### 7.3. Deploying and Testing

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
WORKFLOW="order-fulfillment-lab"
WORKFLOW_SA="workflow-orders@retail-lab.iam.gserviceaccount.com"

# WRITE: create/update workflow from file in lab directory.
gcloud workflows deploy "$WORKFLOW" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --source=order-fulfillment.yaml \
  --service-account="$WORKFLOW_SA"

# WRITE: an execution actually invokes downstream services.
gcloud workflows execute "$WORKFLOW" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --data='{"orderId":"O-1001"}'

# READ-ONLY: inspect workflow definition/metadata.
gcloud workflows describe "$WORKFLOW" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Note:** the deployer needs Workflows permissions and `actAs` permission on the workflow SA when applicable; the SA needs Invoker on the Cloud Run services. `execute` **triggers real downstream side effects** if URLs are configured, so run only against lab data and idempotent endpoints. Workflows **does not create a distributed database transaction** across services.

### 7.4. Retries and Compensation Are Not the Same Thing

If `reserveInventory` succeeds but `confirmOrder` fails:

- **Retry** makes sense for transient 503/timeout errors when `confirm` is **idempotent**.
- **Compensation** (e.g. `releaseReservation`) may be needed when the business flow cannot proceed.
- **Never blindly retry every HTTP POST**: payment/fulfillment calls can produce duplicate side effects.
- Workflows supports `try`/`retry`/`except`, callbacks, branching, and parallelism; design around real failure modes.

For long processes, record `workflowExecutionId`, `orderId`, and business state in durable storage as needed. If a workflow is cancelled or fails, inspect external system states before replaying.

## 8. Combining Services: Four Architectural Patterns

### 8.1. Event Fan-Out Followed by Rate-Limited Partner Calls

~~~mermaid
flowchart LR
    API["Cloud Run: create order"] --> P["Pub/Sub: order.created"]
    P --> INV["Subscription: invoice"]
    P --> M["Subscription: marketing"]
    M --> PRODUCER["Enqueue task per partner"]
    PRODUCER --> Q["Cloud Tasks: partner-queue"]
    Q --> HANDLER["Cloud Run: send partner request"]
~~~

Pub/Sub fans out to multiple consumers; one consumer places rate-limited work into Cloud Tasks. **Do not create separate Cloud Tasks queues to replace every Pub/Sub subscription** when the goal is purely event fan-out.

### 8.2. Scheduled Reporting → Multi-Step Process

~~~text
Scheduler: 02:00 daily
  → Workflows execution
      → call Cloud Run to fetch data
      → start BigQuery job / approved data step
      → await result
      → save report to Cloud Storage
      → send outcome notification
~~~

**Scheduler does not track per-step state.** Workflows manages step results and workflow failures; use a dedicated identity for Scheduler calling the **Workflows Executions API** (typically with an OAuth access token and `roles/workflows.invoker`), while the workflow SA holds permissions to each downstream target.

### 8.3. One-Time Payment Reminder

~~~text
Customer creates order O-1001 at 14:00
    → create Cloud Task scheduleTime = 14:15
    → 14:15 calls /check-and-remind
    → handler reads order status:
         already paid → return 2xx, send nothing
         unpaid → send idempotent reminder
~~~

This is a **per-order one-off schedule**, not a recurring 15-minute cron. Never create a Cloud Scheduler job per order. If the customer pays early, the task may still dispatch; the handler **must re-check status** rather than relying solely on trying to delete the task.

### 8.4. Refund Flow with Compensatable Failures

~~~text
HTTP request / refund.requested event
    → Workflows:
         validate order
         reserve refund operation ID
         call payment provider (idempotency key)
         update Cloud SQL
         notify customer
         if needed: compensate / manual review
~~~

Choose Workflows because you must know **which step succeeded and which failed**. You can use Pub/Sub to emit refund events after transaction state commits, or Cloud Tasks to rate-limit a partner endpoint. **Never claim "Workflows makes every step exactly-once"**; transactions and compensation remain application responsibilities.

## 9. What the Four Services Do Not Guarantee Automatically

### 9.1. At-Least-Once Delivery and Idempotency

Pub/Sub, Cloud Tasks, and Cloud Scheduler can all produce **multiple deliveries/attempts** for the same work. Workflows can also re-invoke steps on retry, or a single business event can trigger multiple executions. Therefore:

1. Generate a **business operation ID** before publishing or enqueuing.
2. In the consumer/handler, check the operation ID in **durable** storage.
3. Commit side effects and idempotency state via transactions/unique constraints whenever possible.
4. Ack Pub/Sub or return HTTP 2xx **after committing**.
5. For external APIs, pass an idempotency key if supported by the partner; otherwise design reconciliation.

Example:

~~~sql
CREATE TABLE processed_operations (
  operation_id TEXT PRIMARY KEY,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Within the transaction, attempt inserting operation_id first.
INSERT INTO processed_operations(operation_id)
VALUES ('send-receipt:O-1001')
ON CONFLICT DO NOTHING;
~~~

The application executes the side effect only when the transaction **genuinely inserted a new row**, and business writes commit **in the same transaction** when targeting the same database. When calling APIs outside that database transaction, the SQL pattern alone **is insufficient** to ensure single execution; add **outbox/reconciliation** or partner-side idempotency.

### 9.2. Ordering and Rate Limits

| Desire | What Actually Needs to Happen |
| --- | --- |
| Events for the same order processed in order | Pub/Sub ordering keys where supported + sequential per-key consumption; business version checks. |
| Task queue runs strictly in enqueue order | Cloud Tasks offers no strict FIFO guarantee; enforce keys/versions in the app. |
| No more than 10 calls/s per partner | Cloud Tasks queue dispatch limits + review concurrency, retries, and partner limits. |
| Only one report per cron interval | Scheduler is at-least-once, so handlers enforce interval keys in the DB. |
| Refund executes one unique business flow | Workflows + operation IDs, transactions, and concurrent-execution controls. |

### 9.3. Quotas and Backlog Retention

Pub/Sub retains messages according to **topic/subscription retention**; unacked messages can expire. Cloud Tasks holds tasks up to product-supported age/schedule limits; queued tasks are not an infinite historical ledger. Scheduler stores only **job schedule/attempt metadata**, not an unbounded per-interval queue. Workflows retains **execution state/history** per product retention rules, not replacing a business database.

For long-term data retention, use Cloud Storage, Cloud SQL, BigQuery, or a dedicated datastore. **Never pick a queuing service thinking it replaces backups.**

## 10. IAM, Networking, and Security Across Hops

### 10.1. Never Collapse Identities Together

| Hop | Principal Typically Needing Permission | Example Role / Permission |
| --- | --- | --- |
| API publishing events | Cloud Run runtime SA | `roles/pubsub.publisher` on the topic. |
| GKE reading Pub/Sub | Configured GKE workload identity/SA | `roles/pubsub.subscriber` on the subscription. |
| API creating Cloud Tasks | Producer SA | Task creation on queue, typically `roles/cloudtasks.enqueuer`. |
| Tasks calling Cloud Run | OIDC task SA | `roles/run.invoker` on service; creator has `iam.serviceAccounts.actAs` as needed. |
| Scheduler sending to Pub/Sub | Scheduler service agent/workflow identity | Permissions required to publish to target topic. |
| Scheduler calling Workflows | SA using OAuth to Executions API | `roles/workflows.invoker` at appropriate scope. |
| Workflows calling Cloud Run | Workflow runtime SA | `roles/run.invoker` on each Cloud Run service. |
| Cloud Run/GKE processing data | Dedicated runtime SA | Least-privilege Cloud SQL/Storage/Secret Manager permissions. |

**OIDC** fits calling a Cloud Run HTTPS endpoint expecting an ID token; **Google APIs** like Workflows Executions API normally use an **OAuth 2.0 access token**. An IAM role on a queue/topic **never automatically grants permission to call Cloud Run** or update Cloud SQL.

### 10.2. Network Boundaries Still Apply

- Cloud Run/GKE subscribers need routes, DNS, and permissions to Pub/Sub/Google APIs.
- Cloud Tasks HTTP targets need a reachable URL per service capabilities; Cloud Run ingress may block unsupported paths.
- Scheduler HTTP jobs need an allowed target, matching OIDC/OAuth, and proper timeouts.
- Workflows calls Cloud Run via HTTPS/OIDC per supported architecture; when calling private endpoints, check **IAP, Service Directory, or product-supported connectivity**, never assuming Workflows lives inside GKE's VPC.
- Configure VPC connectors/Direct VPC egress, Cloud NAT, Private Google Access/PSC, or firewalls per real traffic path.

Never fix DNS/network timeouts by granting project Owner. Never fix `401/403` by opening Cloud Run unauthenticated in production.

## 11. Observability, SLOs, and Incident Response

| Service | Metrics / Issues to Watch | Appropriate Response |
| --- | --- | --- |
| Pub/Sub | Unacked messages, oldest unacked age, ack rate, DLQ. | Scale subscribers to match downstream capacity; handle poison messages. |
| Cloud Tasks | Queue depth, oldest task age, dispatch rate, attempts/errors, throttling. | Tune queue limits and handlers; inspect HTTP/timeout errors. |
| Scheduler | Last run, success/failure, retries, schedule lag. | Check cron/timezone, target permissions, and idempotency. |
| Workflows | Execution state, failed step, retries, execution duration, step usage. | Inspect steps, correlation IDs, compensation/replay. |
| Downstream | Cloud Run 5xx/p95, Cloud SQL connections, partner API 429s. | Protect capacity and curb fan-out/retry storms. |

### 11.1. A Simple Calculation for Setting Limits

Suppose a publisher generates **120 orders/minute**; each order needs an email via Cloud Tasks, averaging **2 seconds/task** processing time. To keep up under steady load:

~~~text
Arrival rate = 120 / 60 = 2 tasks/second
Minimum concurrency via Little's Law ≈ 2 × 2 = 4 tasks
~~~

Choosing `max-concurrent-dispatches=4` is a **steady-load theoretical estimate**, not a production recommendation. For longer p95 latency, retries, or bursts, add headroom, respect partner API limits, and load test. Setting `max-dispatches-per-second=1` **will build a backlog** when sustained arrivals are 2 tasks/second.

### 11.2. Integration Incident Runbook

1. **Identify the layer**: did the job fail to trigger, message remain undelivered, task sit in queue, workflow step fail, or backend receive and error?
2. **Inspect identities**: producer/trigger SA, OIDC/OAuth audience, and destination IAM.
3. **Inspect networking**: hostname, DNS, ingress/egress, timeouts, and connectivity.
4. **Inspect throughput capacity**: queue depth, rate, concurrency, Cloud Run scale, Cloud SQL limits.
5. **Inspect business logic**: payload/schema, idempotency, transactions, and downstream state.
6. **Recover safely**: replay, retry, re-enqueue, or compensate per error class; avoid duplicate side effects.
7. **Verify SLOs**: backlog drains, jobs finish, and no hidden errors or cost spikes remain.

**Never use "delete the queue/topic/subscription" as a first response** to a backlog. Doing so can wipe data or destroy retry/recovery opportunities.

## 12. Cost: Choose Based on Actual Work Performed

| Component | Primary Cost Drivers | What to Control |
| --- | --- | --- |
| Pub/Sub | Data throughput, delivery/storage, retention, and add-on features. | Subscription/fan-out count, payload size, backlog age. |
| Cloud Tasks | Operations/task count per pricing, logs, and handler compute. | Retry storms, task volume, queue rates. |
| Cloud Scheduler | Cron job count under current pricing, target usage. | Avoid creating millions of per-record cron jobs. |
| Workflows | Internal/external steps, executions, logging/connector calls. | Overly granular micro-steps, tight polling, unbounded retries. |
| Cloud Run/GKE/SQL | CPU/RAM/instances, database connections, and data transfer. | Concurrency, max instances, downstream limits. |

No single option is always cheapest. **Scheduler → Workflows** can make sense for daily reports; running Workflows for every tiny high-throughput event inflates step counts and cost. **Pub/Sub** fits one event with many consumers, yet each consumer adds delivery/storage and operational overhead.

Evaluate **cost per completed business outcome**, not just price per message or API call. Measure with Cloud Billing/Monitoring while considering quotas and deployment regions.

## 13. Common Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using Scheduler to schedule individual emails for millions of orders. | Too many jobs and lifecycle management pain. | Cloud Tasks `scheduleTime` per order. |
| Using Pub/Sub to call one endpoint requiring a hard QPS cap. | Lacks publisher-side queue dispatch throttling. | Cloud Tasks or subscriber-side flow control by design. |
| Using Cloud Tasks as a broadcast topic. | Producer must enqueue per handler, increasing coupling. | Pub/Sub with independent subscriptions. |
| Using Workflows to iterate over tiny high-throughput events sequentially. | Step count, latency, and cost spike. | Pub/Sub/batch workers; orchestrate only stateful parts. |
| Believing retries guarantee exactly-once. | Duplicate emails or double charges. | Idempotency keys, transactions, outbox. |
| Believing Cloud Scheduler runs "exactly once per hour". | Missed retries or duplicate execution. | Use scheduled-run IDs and deduplication. |
| Believing Cloud Tasks dispatches in strict FIFO order. | Out-of-order entity state. | App-level version checks/serialization. |
| Acking / returning 2xx before committing. | Loses retry protection when writes fail. | Commit durably before acknowledging. |
| Making every SA an Editor. | Amplifies blast radius if credentials leak. | Least-privilege IAM per hop. |
| Watching only queue depth without oldest age. | Old/poison work gets stuck even in a small queue. | Monitor both backlog size and age. |

## 14. Exercises

### Exercise 1 — Product Selection

For each requirement, pick the primary service and explain in one sentence: (a) broadcast `order.created` to accounting and analytics; (b) call a partner webhook at most 10 times/second; (c) aggregate reports daily at 02:00; (d) process a three-step branching refund; (e) send a payment reminder exactly 15 minutes after each order is created.

**Hint:** Pub/Sub, Cloud Tasks, Scheduler, Workflows, and Cloud Tasks respectively.

### Exercise 2 — Distinguishing HTTP Push

Both Pub/Sub push subscriptions and Cloud Tasks HTTP targets can call Cloud Run. What differs between **a publisher unaware of consumers** and **a producer naming an endpoint**, and between retention/backlog and queue dispatch control?

### Exercise 3 — Designing Fan-Out

A website emits `order.created` and three teams need independent processing. Diagram the topic/subscriptions, Publisher/Subscriber IAM roles, and each team's backlog metric. What happens if analytics stops for 30 minutes?

### Exercise 4 — Slow Tasks and Rate Limits

A partner API allows at most 6 requests/second and 3 concurrent requests. Pick initial Cloud Tasks queue settings, explain why retries/backoff and idempotency are needed, and describe how to measure for tuning. If the producer generates 9 tasks/second on average for 20 minutes, roughly how much does the backlog grow at a steady 6/second dispatch rate, ignoring retries?

**Hint:** grows by roughly `(9 − 6) × 1,200 = 3,600` tasks.

### Exercise 5 — Cron and Timezones

Explain `0 9 * * 1` in `Asia/Ho_Chi_Minh`. If switched to `Etc/UTC`, how does the Vietnam-time schedule shift? Why is deduplication needed for the same report interval?

### Exercise 6 — Workflows and Compensation

The flow `reserve inventory → charge card → update order` fails at step three. State what Workflows must persist, when retries are safe, when reconciliation/compensation is required, and why you must never auto-re-charge without idempotency.

### Exercise 7 — Two-Hop IAM

A Cloud Run API creates a Cloud Task; the task invokes an authenticated Cloud Run `send-email` service. Distinguish the producer SA's permissions, the task's OIDC SA, `iam.serviceAccounts.actAs`, `roles/run.invoker`, and `send-email`'s runtime SA.

### Exercise 8 — Detection and Remediation

A Cloud Scheduler job succeeded, yet no report appears in Cloud Storage. Inspect the Scheduler target, Pub/Sub subscription or Workflows execution, Cloud Run logs, Cloud Storage IAM, and idempotency logic in order. What does "Scheduler succeeded" prove, and what does it **not** prove?

### Exercise 9 — Cost Trade-Offs

A system receives 1 million events/day, each with 3 subscribers; an aggregation report runs once nightly. Propose a cost-effective architecture and state what conditions would lead you to add Cloud Tasks or Workflows rather than forcing everything into a single service.

## 15. Production Checklist and Official Documentation

| Item | Verification Question |
| --- | --- |
| **Right pattern** | Event fan-out, explicit task, cron, or multi-step orchestration? |
| **Trigger and target** | Right topic/subscription, URL, service, cron/timezone, or workflow execution? |
| **Delivery** | Is idempotency ready for at-least-once, retries, timeouts, and re-execution? |
| **Rate and backlog** | Do dispatch/concurrency, publish/ack rates, oldest age, and worker capacity align? |
| **State and recovery** | Workflows execution state, DB transactions, compensation, and DLQ/replay as needed? |
| **IAM** | Separated producer, delivery identity, workflow SA, and runtime SA with least privilege? |
| **Networking** | Ingress/egress, audience, OIDC/OAuth, DNS, and private access tested for real? |
| **CI/CD** | IaC/review, versioning, staging tests, rollback without dropping queued data? |
| **Observability** | Correlation IDs, logs, errors, backlog/age, SLOs, and cost alerts? |
| **Economics** | Accounted for publishes/deliveries/tasks/jobs/steps and downstream costs? |

Official documentation for verifying version-specific limits and CLI flags:

- [Google Cloud: Choosing Pub/Sub or Cloud Tasks](https://cloud.google.com/pubsub/docs/choosing-pubsub-or-cloud-tasks)
- [Pub/Sub subscriptions and delivery semantics](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Cloud Tasks: HTTP target quickstart](https://cloud.google.com/tasks/docs/add-task-queue)
- [Cloud Tasks: Configure queues and retries](https://cloud.google.com/tasks/docs/configuring-queues)
- [Cloud Scheduler overview](https://cloud.google.com/scheduler/docs/overview)
- [Cloud Scheduler cron format and time zones](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules)
- [Workflows overview](https://cloud.google.com/workflows/docs/overview)
- [Workflows: Authenticate requests](https://cloud.google.com/workflows/docs/authenticate-from-workflow)
- [Workflows: Schedule using Cloud Scheduler](https://cloud.google.com/workflows/docs/schedule-workflow)
- [gcloud tasks create-http-task](https://cloud.google.com/sdk/gcloud/reference/tasks/create-http-task)
- [gcloud scheduler jobs create pubsub](https://cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/pubsub)
- [gcloud workflows deploy](https://cloud.google.com/sdk/gcloud/reference/workflows/deploy)

**Key takeaway:** **Pub/Sub** is an event broadcast channel for independent consumers; **Cloud Tasks** is a queue throttling calls to a specific handler; **Cloud Scheduler** is a scheduled trigger clock; **Workflows** is a stateful multi-step orchestrator. Choose them by **how the work needs to be executed**, then layer on authentication, retries, idempotency, rate limits, metrics, and cost controls. A sound architecture usually **combines the right roles** rather than forcing one product to fit every requirement.
