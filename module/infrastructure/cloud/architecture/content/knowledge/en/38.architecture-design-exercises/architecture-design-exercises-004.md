# Adding Asynchronous Processing and Spike Load Control

## 1. Exercise Objectives

A cloud application can run smoothly on ordinary days yet degrade severely during promotions, media events, or simultaneous traffic surges. A common culprit is **running every operation synchronously inside the HTTP request path**, including tasks customers do not need to wait on immediately—such as sending emails, generating reports, building PDFs, or syncing external systems. As load climbs, slow downstream calls form hidden queues across threads, connection pools, and the database; timeouts and retries can overload the system further.

The lesson **"Adding Asynchronous Processing and Spike Load Control"** belongs to the **Design Exercises** chapter of **CLOUD_ARCHITECTURE**. Learners practice turning business requirements into decisions on **networking, compute, data, and deployment models**, while explaining trade-offs across **Well-Architected** pillars: reliability, security, performance, cost, operations, and sustainability.

After this lesson, you will be able to:

1. Identify which tasks should remain **synchronous** and which can move **asynchronously**.
2. Design the **API → durable persistence → queue → worker → target system** flow.
3. Choose **rate limiting, admission control, backpressure, autoscaling**, and concurrency limits to protect resources during bursts.
4. Approximate **throughput, backlog, wait times, and worker capacity** from a concrete load scenario.
5. Handle **retries, duplicates, idempotency, poison messages, dead-letter queues (DLQ), event ordering**, and failure scenarios.
6. Produce an architecture diagram, acceptance criteria, runbook, and trade-off analysis defensible before a design review board.

**Guiding principle:** Asynchrony **decouples when work is accepted from when work is executed**; a queue itself **creates zero extra processing capacity**. If arrival rate consistently exceeds processing rate, backlog still grows to unacceptable levels.

## 2. Problem Statement: A Retail System Hit by Peak Traffic

### Assumed Context

An e-commerce company operates an API serving its website and mobile app. Once an order is confirmed, the system must generate a PDF invoice, send a notification email, award customer loyalty points, and sync data to an analytics platform. Today, all of these tasks execute inline during the order-confirmation call.

**All figures below are pedagogical assumptions**, not default capacities of any cloud service:

| Parameter | Assumed value |
|---|---:|
| Application-wide normal traffic | 400 requests/second |
| Peak promotional traffic | 4,000 requests/second for 5 minutes |
| Share of requests resulting in a confirmed order | 5% |
| Generated background events | ~20 events/second normal; 200 events/second at peak |
| Single-worker throughput from initial benchmark | 5 events/second |
| Planned initial worker cap | 24 workers |
| Business expectation for notifications/invoices | Mostly completed within 10 minutes of order confirmation |

Customers must **know their exact order and payment status**. Slow email delivery or PDF generation must never turn a validly paid order into a "failed" order or trigger duplicate charges. Conversely, never reply "payment succeeded" merely because a request was pushed onto a queue.

### Current State: Synchronous Dependencies Stretch the Hot Path

~~~mermaid
flowchart LR
    U["Customers"] --> L["Load balancer"]
    L --> A["Order API"]
    A --> DB[("Order database")]
    A --> PDF["PDF invoice generator"]
    A --> MAIL["Email provider"]
    A --> CRM["Loyalty / analytics sync"]
    PDF --> A
    MAIL --> A
    CRM --> A
    A --> U
~~~

Suppose the email provider's latency suddenly jumps from a few hundred milliseconds to tens of seconds. HTTP connections and threads stay pinned; client and gateway retries multiply real work beyond incoming traffic. Adding API instances without bounding downstream connections simply **shifts the bottleneck** onto the email provider or the database.

**Problem to solve:** decouple the critical path from background tasks, accept burst traffic within safe limits, allow gradual draining while preserving order correctness, and control errors, cost, and operations.

## 3. Step One: Classifying Synchronous vs. Asynchronous Operations

Before drawing queues, determine what must be true **at the exact moment the HTTP response is returned**.

| Operation | Direction | Rationale |
|---|---|---|
| Authentication and order authorization | **Synchronous** | Never accept unauthorized requests |
| Schema, idempotency key, and basic input validation | **Synchronous** | Avoid persisting obviously invalid requests |
| Durably recording the order request | **Synchronous at acceptance boundary** | Never acknowledge receipt if state lives only in RAM |
| Payment processing/finalization | **Depends on business contract** | If immediate outcome is required, keep confirmation accurate; if deferred, return a pending status |
| Generating invoice PDFs | **Usually asynchronous** | Files can become available within an agreed timeframe |
| Sending email/SMS notifications | **Usually asynchronous** | Can retry when providers slow down without holding HTTP requests |
| Loyalty points, CRM sync, analytics writes | **Can be asynchronous** | Define update SLAs and reconciliation rules |
| Inventory reservation or anti-oversell guarantees | **Must preserve correctness** | Can be asynchronous if designed with states, reservation/compensation, and explicit contracts |

**Never arbitrarily push payments, inventory holds, or legally binding actions onto a queue and return success before business conditions are met.** When accepting work for deferred processing, the API should accurately state "request received, processing" and provide a way to query the final result.

### Distinguishing Three Milestones

1. **Accepted:** the request passed baseline validation and is durably persisted per API contract.
2. **Business completed:** the core business action finished—for instance, the order is confirmed paid.
3. **Side effects completed:** invoices, emails, loyalty points, or analytics have finished processing.

A system can be accepted without being business completed; or an order can be confirmed while notifications remain pending. Do not use a single `success=true` boolean for all three milestones.

## 4. Step Two: Designing a Reliable Asynchronous Flow

### Reference Target Architecture

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> EDGE["CDN / WAF / API Gateway<br/>auth, rate limit, admission"]
    EDGE --> API["Order API<br/>idempotency + business state"]
    API <--> DB[("Order DB<br/>Orders + Outbox")]
    DB --> RELAY["Outbox relay<br/>publish with retries"]
    RELAY --> Q["Durable queue / topic<br/>bounded backlog"]
    Q --> W["Worker pool<br/>bounded concurrency"]
    W --> PDF["PDF service / storage"]
    W --> MSG["Email / loyalty / analytics"]
    W --> DLQ["Dead-letter queue"]
    API --> STATUS["Status lookup API"]
    STATUS --> U
    OBS["Metrics / logs / traces / alerts"] -.-> API
    OBS -.-> RELAY
    OBS -.-> Q
    OBS -.-> W
    OBS -.-> DLQ
~~~

This diagram is a **logical architecture**. The queue may be a managed service or a self-hosted broker; workers may run on serverless functions, container jobs, Kubernetes, or VMs. Not every project needs every block; keep only the pieces that solve real requirements and have clear operational owners.

### Component Responsibilities

**Edge/API Gateway:** handles authentication, per-user/tenant rate limits, and shields the API from request storms. A WAF filters some malicious traffic, but does not replace application-level admission control.

**Order API:** enforces synchronous business rules, accepts or rejects requests, creates or reads idempotency records, and returns truthful status. On order confirmation, the API or payment-result handler atomically records both the business update and the outbound event.

**Transactional outbox:** an event table written in **the same database transaction** as the business state update, avoiding the "DB committed but process crashed before publishing" gap. A relay reads unpublished events, publishes them, and marks them sent. If the relay loses connectivity after the broker ACKs but before updating the outbox, the event may be sent **more than once**.

**Durable queue:** persists published work, decouples intake pace from processing pace, and supports retries/visibility timeouts or equivalents. Queues must enforce quotas, retention limits, and full-queue policies—never treat a queue as infinite storage.

**Worker:** executes tasks independently, bounds concurrency and downstream connections, and records progress/outcomes. Consumers must tolerate duplicate messages and classify errors properly.

**DLQ:** captures messages exceeding retry limits or hitting non-retryable errors for investigation and controlled replay. A DLQ requires alerts, an owner, and retention policies—it is not a "forget-about-it trash bin."

**Observability:** instruments HTTP, outbox, queue, and downstream calls; correlates events via `order_id`, `event_id`, `correlation_id`, and `trace_id` in line with security policies.

### Flow After Order Confirmation

~~~mermaid
sequenceDiagram
    participant C as Customer
    participant A as Order API
    participant D as Order DB
    participant R as Outbox relay
    participant Q as Queue
    participant W as Worker
    participant E as Email/PDF
    C->>A: Confirm / look up order
    A->>D: Transaction: CONFIRMED state + outbox event
    D-->>A: COMMIT succeeds
    A-->>C: Return accurate order status
    R->>D: Poll unpublished events
    R->>Q: Publish OrderConfirmed
    Q-->>R: Broker ACK
    R->>D: Mark outbox event sent
    Q->>W: Deliver event (may redeliver)
    W->>W: Check event_id / idempotency
    W->>E: Generate PDF / send notification
    E-->>W: Result
    W->>Q: ACK after successful completion
~~~

This is not an atomic transaction spanning the database and the email provider. If a worker drops right after the email sends, the event can be redelivered; downstream idempotency, transaction receipts, or reconciliation are required.

## 5. Step Three: Defining the API Contract and States

For asynchronously processed commands, the contract must specify **when data is durably persisted** and how clients learn the outcome.

### Example API Accepting Work for Later Processing

~~~http
POST /orders
Idempotency-Key: 74d29db0-94e7-4c1e-9667-2a2189a3d82d
Content-Type: application/json

{"cart_id":"cart-715","delivery_address_id":"addr-20"}
~~~

If **only accepted for deferred processing** without confirming payment/order yet:

~~~http
HTTP/1.1 202 Accepted
Location: /orders/ord-913
Retry-After: 2
Content-Type: application/json

{"order_id":"ord-913","status":"PENDING","message":"Request accepted"}
~~~

~~~http
GET /orders/ord-913
~~~

~~~json
{"order_id":"ord-913","status":"CONFIRMED","invoice_status":"PROCESSING","notification_status":"PENDING"}
~~~

Illustrative statuses include `PENDING`, `PROCESSING`, `CONFIRMED`, `REJECTED`, and `CANCELLED`; terminal states and allowed transitions must be defined per business domain. If the API already confirmed the order at response time, `201 Created` or `200 OK` fits by convention—returning `202` is not mandatory for every queue-backed system.

Bind **Idempotency-Key** to the caller, operation type, and payload fingerprint (or equivalent) so one key cannot be reused for a different request. Define key retention TTLs and retry responses. When the same key and payload arrive again, return the recorded outcome instead of creating a new order. This control **does not replace payment idempotency** at the partner gateway.

### When the System Cannot Accept More Work

- **429 Too Many Requests:** caller exceeded published rate limits or resource-protection quotas; include `Retry-After` when a reasonable estimate exists.
- **503 Service Unavailable:** system is temporarily unable to accept work safely due to capacity exhaustion or critical dependency outage; consider `Retry-After` and client backoff.
- **Never return `202` or `2xx` if the request was not durably stored** with a reliable path to execute it.

The API must distinguish **request acceptance** from **work completion** so frontends never display misleading business states.

## 6. Step Four: Controlling Spike Loads Across Layers

Adding a queue offloads background work, yet the intake tier still relies on databases, connection pools, CPU, and partner quotas. A resilient design combines several layers of protection:

| Mechanism | Placement | Role | Limitation to watch |
|---|---|---|---|
| **Rate limiting** | Edge/API by user, API key, tenant, endpoint | Caps request arrival rate | Does not drain tasks already in backlog |
| **Burst allowance (token bucket)** | Gateway or API | Permits short bursts within budget | Oversized bursts still overwhelm downstream tiers |
| **Admission control** | API before commit point | Rejects or sheds intake when DB, outbox, queue, or budgets near limits | Requires reliable health signals and clear thresholds |
| **Bounded concurrency** | API, relay, and workers | Respects connection pools, quotas, and downstream capacity | Too-low concurrency delays SLAs |
| **Backpressure** | Workers, queues, producers | Propagates overload signals upstream; slows or pauses intake | Requires deciding which work gets prioritized or rejected |
| **Autoscaling** | API and workers | Adjusts compute to measured demand | Subject to startup lag, quotas, cost, and other bottlenecks |
| **Timeout + circuit breaker** | Callers to downstream | Prevents tying up resources waiting on broken partners | Hair-trigger thresholds can reject healthy traffic |
| **Load shedding / degrade** | API and application | Temporarily drops non-essential features to protect core transactions | Must pre-define which features may degrade |

### Illustrative Token Bucket

Suppose a bucket has **capacity of 200 tokens**, refills at **80 tokens/second**, and each request consumes one token. When full, it permits a burst of up to 200 requests, then settles to a sustained intake rate near 80 requests/second (ignoring other limits).

This is **one example bucket for a single class/target**; you cannot apply an 80 requests/second cap blindly across an application serving hundreds of requests/second. Design separate **per-client**, **per-tenant**, **per-endpoint**, and **global safety limits** aligned with capacity budgets to ensure fairness and stop one tenant from starving others.

### Ordered Protection Flow

~~~mermaid
flowchart TD
    R["Request arrives at API"] --> AUTH{"Valid auth / permissions?"}
    AUTH -- "No" --> D1["401/403 or appropriate error"]
    AUTH -- "Yes" --> RATE{"Within rate limit?"}
    RATE -- "No" --> D2["429 + retry guidance"]
    RATE -- "Yes" --> CAP{"Durable intake capacity available?"}
    CAP -- "No" --> D3["503 / 429 per reason, no false ack"]
    CAP -- "Yes" --> COMMIT["Persist state + idempotency/outbox"]
    COMMIT --> OK["Return accurate status"]
~~~

No magic limit fits every system. Thresholds come from load testing, DB capacity, downstream quotas, SLOs, and resource allocation policies.

### Preventing a "Retry Storm"

When a service slows down, clients, gateways, services, and workers **may all retry the same operation**, multiplying each initial request into many new ones. Retry policies should enforce:

- Explicit per-layer timeouts within an end-to-end time budget.
- **Finite** retry counts, only on transient errors.
- Exponential backoff with **jitter** to prevent synchronized retry waves.
- Respecting downstream `Retry-After` headers and quotas when provided.
- Idempotency on any operation with side effects.
- Not retrying immediately at every layer; designate **which layer owns retries** for a given operation.

A **circuit breaker** cuts calls to failing downstreams, though it must probe carefully to reopen; it does not shrink existing queue backlogs.

## 7. Step Five: Calculating Capacity, Backlog, and Recovery Time

To decide how many workers are enough, model arrival and drain rates:

- \(\lambda(t)\): new jobs arriving in the queue per second.
- \(\mu(t)\): jobs completed per second by the entire worker pool.
- \(B(t)\): outstanding uncompleted jobs, measured consistently with queue metrics.

Approximated over interval \(\Delta t\), assuming no other limits:

\[
B(t+\Delta t)\approx\max\left(0,\, B(t)+[\lambda(t)-\mu(t)]\Delta t\right).
\]

**Exercise assumptions:** one event = one job, each worker processes **5 jobs/second** on average, all 24 workers are active immediately as the peak starts, queue capacity is sufficient, downstreams do not throttle, and jobs have roughly uniform cost.

Then:

| Phase | Arrival rate \(\lambda\) | Capacity \(\mu\) | Backlog change |
|---|---:|---:|---:|
| Normal | 20 jobs/s | 24 × 5 = 120 jobs/s (if workers active) | Queue stays drained |
| Peak for 300 seconds | 200 jobs/s | 120 jobs/s | Grows by \(80 \times 300 = 24,000\) jobs |
| Post-peak | 20 jobs/s | 120 jobs/s | Net drain of 100 jobs/s |

Estimated **post-peak backlog drain time**:

\[
t_{\text{drain}}=\frac{24,000}{120-20}=240\text{ seconds}=4\text{ minutes}.
\]

Under FIFO and steady throughput, a job arriving near the end of the peak may wait nearly **\(24,000/120=200\) seconds** before starting, excluding task execution time. Total elapsed time from peak start until backlog returns near zero is roughly **9 minutes** in the ideal model.

**Important distinction:** 4 minutes is the post-peak drain duration; 9 minutes is the time from peak onset until cleared, not the wait time of every job. These are **estimates**, excluding autoscaling lag, task failures, retries, queue delivery overhead, email/PDF provider latency, and execution-time variance.

### Practical Sizing Formula

If each worker has a measured sustainable throughput of \(r\) jobs/s and target pool throughput is \(\mu_{\text{target}}\) jobs/s:

\[
N_{\text{worker}}=\left\lceil\frac{\mu_{\text{target}}}{r}\right\rceil.
\]

For instance, to **match the 200 jobs/s peak directly** at 5 jobs/s/worker without buffering:

\[
N=\left\lceil\frac{200}{5}\right\rceil=40\text{ workers}.
\]

If budget or quotas keep you at 24 workers, you must accept a bounded backlog and **prove wait times remain within the SLO**. If downstream accepts only 60 jobs/s, even 40 workers cannot exceed that ceiling; use controlled throttling or negotiate higher downstream quotas.

### Reality Cannot Rely on One Average Number

Benchmark **p50/p95 job duration**, error rates, retry multipliers, cold start times, slow outliers, API quotas, disk/network throughput, and payload size skew. If a job uses 1 second of CPU yet spends 5 seconds waiting on an external API, concurrency and CPU sizing change drastically. Overloading workers with too many concurrent tasks can cause OOM crashes or exhaust connection pools.

Alongside **queue depth**, monitor **age of oldest unprocessed message** and **end-to-end completion latency**; two queues both holding 10,000 messages can differ wildly in SLO risk.

## 8. Step Six: Ensuring Correctness Under Queue Redelivery

### At-Least-Once Does Not Equal Exactly-Once

Most practical designs must expect a message to be delivered **more than once**. For example:

1. Worker receives `OrderConfirmed`.
2. Worker generates the PDF and calls the email provider successfully.
3. Worker crashes before sending ACK to the broker.
4. After the visibility timeout expires, the broker redelivers the message to another worker.

Without consumer safeguards, the customer may receive two emails, get double loyalty points, or generate two distinct invoices. Queue FIFO or deduplication features **do not automatically guarantee once-only effects across external systems**.

### Event Design and Idempotency Keys

A sample event should include a schema version and stable identifier:

~~~json
{
  "event_id": "order-913-confirmed-v1",
  "event_type": "OrderConfirmed",
  "schema_version": 1,
  "order_id": "ord-913",
  "occurred_at": "2026-01-01T10:00:00Z",
  "correlation_id": "trace-7f3b",
  "payload_ref": "orders/ord-913"
}
~~~

The example uses an illustrative timestamp; production data must reflect actual event times. `event_id` must never change when the relay republishes the same event. Keep payloads compact and prefer **references** to source records where appropriate, avoiding PII inside queues.

A **consumer idempotency key** can be `(consumer_name, event_id)`; when the same event must be reprocessed due to a data fix or algorithm update, introduce a managed **processing version**. For "credit 100 points", enforce the key directly inside the ledger/points transaction to prevent double-crediting rather than checking an in-memory flag.

### Transactional Outbox: Closing the DB–Broker Gap

~~~sql
-- SQL pseudocode; column names and syntax depend on the database engine.
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'PENDING';

-- Emit event only when the business transition succeeds.
INSERT INTO outbox(event_id, aggregate_id, event_type, payload, status)
VALUES (:stable_event_id, :order_id, 'OrderConfirmed', :payload, 'NEW')
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

This snippet is **pseudocode**. Implementation must check affected row counts, already-confirmed orders, transaction isolation levels, and payment-result handling. **The order update and its corresponding event** must commit in the same transaction. That transaction cannot span the external payment gateway call itself.

The relay **marks the outbox row published only after the broker acknowledges receipt**. If the relay crashes between broker ACK and the DB update, the event may be republished—which is why consumers must remain idempotent.

### Safe Consumer Execution

~~~text
on_message(event):
    validate_schema_and_authorization(event)
    if already_completed(consumer_name, event.event_id):
        ack_message()
        return

    order = fetch_order(event.order_id)
    verify_expected_business_state(order)
    result = perform_side_effect_with_idempotency_key(
        key = consumer_name + ":" + event.event_id
    )
    persist_completion_or_reconcile(result, event.event_id)
    ack_message_only_after_safe_completion()
~~~

This pseudocode does not claim a distributed transaction across **database + broker + email provider**. If the email provider lacks idempotency keys, accept potential duplicates in rare failure windows or add lookup/reconciliation—never label it "exactly once" without proof.

### Event Ordering Across Multiple Workers

Parallel queues generally **do not guarantee global ordering**. For transitions like `OrderCreated`, `OrderPaid`, and `OrderCancelled`, decide whether ordering **per `order_id`** is required; if so, use partition/ordering keys, version checks, or per-aggregate serialization.

A defensive safeguard is storing a **state version** and processing events only when state transition preconditions hold. Never let a late `OrderCreated` overwrite an order already in `CONFIRMED`.

## 9. Step Seven: Retries, Timeouts, and Dead-Letter Queues

### Classify Errors Before Retrying

| Error class | Examples | Action |
|---|---|---|
| **Transient** | Provider 429, network timeout, brief target outage | Bounded retries, backoff + jitter, respect quotas |
| **Permanent data error** | Missing required field, incompatible schema, malformed email | Do not retry endlessly; mark business error / quarantine |
| **Code or config bug** | Every message throws due to bad deploy | Pause or throttle consumers, roll back, fix, and replay safely |
| **Resource exhaustion** | OOM, connection starvation, worker eviction | Adjust concurrency/sizing; reprocess once capacity recovers |
| **Uncertain side-effect outcome** | Provider sent email but client missed response | Query via idempotency/transaction key or reconcile before re-running |

A reference policy: **max 5 attempts**, exponentially increasing wait times with jitter, then route to DLQ once recovery options exhaust. These numbers are illustrative; actual policies must account for **total retry duration**, retention, SLOs, and downstream recovery speed.

### Visibility Timeout, Leases, and ACKs

On brokers using visibility timeouts, if processing can take up to 120 seconds while visibility timeout is only 30 seconds, the message may be redelivered to another worker **before the first finishes**. Base timeouts on observed processing times or use **heartbeats/lease extensions** if supported. Even then, consumers must stay idempotent because duplicates arise from other causes.

After a transient failure, **never ACK as succeeded**. Yet do not hot-loop retries without backoff either. When a poison message lands in the DLQ, ensure someone monitors it and a clear business workflow exists for missed notifications.

### DLQ Handling Workflow

1. Alert when DLQ depth grows, messages age, or error rates breach thresholds; assign an owner.
2. Investigate by `event_id`, failure reason, schema version, consumer version, and customer impact.
3. Fix the root cause: data, code, config, permissions, quotas, or provider issue.
4. Replay a **small sample** after fixing and reconcile to confirm no duplicate side effects.
5. Replay in rate-limited batches while watching queue lag and downstream health.
6. Record counts of succeeded, pending, intentionally discarded (with justification), and SLO impact.

Avoid storing secrets or excessive sensitive data inside DLQs. Align DLQ retention with data policies and recovery windows.

## 10. Step Eight: Bounded Autoscaling and Job Prioritization

### Choosing Scaling Signals

Scaling workers purely on CPU fails for I/O-bound workloads. Useful signals include:

- **Queue backlog per worker** and real arrival vs. completion rates.
- **Age of oldest message** relative to the wait SLO.
- **Throughput per worker**, p95 processing duration, and retry counts.
- **Downstream 429s/quotas**, connection pool saturation, and DB CPU/memory.
- **Cost**, max instance quotas, and allowed worker limits.

A starting formula to estimate workers from backlog and target drain time:

\[
N_{\text{estimated}}=
\left\lceil
\frac{\lambda_{\text{expected}}+B/T_{\text{target drain}}}
{r_{\text{effective worker}}}
\right\rceil.
\]

For example, with a 24,000-job backlog to drain in 240 seconds while arrivals continue at 20 jobs/s and each worker sustains 5 jobs/s:

\[
N=\left\lceil\frac{20+24,000/240}{5}\right\rceil
=\lceil24\rceil=24.
\]

**Preconditions:** throughput must be empirically measured and the target system must not be saturated. Set **min/max workers**, cooldowns, step caps, and monitor provisioning latency. If the email provider returns 429 above 60 jobs/s, scaling to 100 workers only increases errors and spend.

### Priority Queuing

When one queue mixes job types, critical work can get stuck behind thousands of low-urgency tasks. Options include:

- **Separate queues** for customer-impacting events vs. analytics/backfills.
- **Dedicated worker pools/concurrency quotas** per priority tier to guarantee capacity for critical tasks.
- **Weighted fair scheduling** when balancing fairness across tenants or job types.
- **Per-provider rate limits** so email, CRM, or PDF quotas are never breached.

Never let high-priority queues starve low-priority queues indefinitely; define SLOs and capacity floors for every class of work.

### When Should Service Be Degraded?

Suppose 24,000 jobs are backed up and the email provider slows down: pause marketing emails and lower analytics sync frequency while preserving legally required notifications and order correctness. If backlog threatens new transaction intake, activate admission control and communicate accurate status. **Controlled early rejection** beats accepting everything only to lose data or delay fulfillment by hours unnoticed.

## 11. Step Nine: Choosing Infrastructure and Operational Boundaries

### Compute, Queues, and Data

| Component | Typical options considered | Decision questions |
|---|---|---|
| API | Managed containers, PaaS, VMs, or serverless | Is it stateless? DB connection count? Cold-start impact? |
| Durable queue | Managed queue, broker with retention/ACK, or event service | Need fan-out, ordering, latency bounds, DLQ, replay, retention? |
| Outbox/metadata | Table inside the order relational DB | Atomic with business data? How does polling/CDC affect DB load? |
| Worker | Serverless functions, container workers, batch jobs, VMs | Job runtime, memory footprint, persistent connections, concurrency caps? |
| Output files | Object storage or document service | Publishing method, access permissions, retention, checksums? |
| Observability | Managed metrics/logs/tracing and alerts | Tracks end-to-end flows, queue age, DLQ, and cost per run? |

**Queue or stream?** A standard work queue fits when each task goes to one consumer. Pub/sub or event streaming fits when multiple independent consumer groups, historical replay, or high-throughput event logs are needed. Decide based on delivery semantics, retention, ordering, and ops cost—do not add event streaming just because "we might need it later."

### Networking, Access Control, and Security

- Place workers and databases in private networks/access zones, restricting public inbound access. Route third-party egress through controlled paths with visibility into network/NAT failures.
- Use dedicated **service identities/IAM**: API writes business/outbox rows; relay reads outbox and publishes to queue; workers read queues and touch only required storage/APIs; consumers do not get blanket write access to all orders.
- Encrypt data in transit and at rest; manage and rotate keys/secrets and audit access.
- Minimize personal data in queue payloads; pass `order_id` or scoped references instead. Scrub or mask PII in logs.
- Define retention windows for queues, DLQs, PDFs, logs, and idempotency records per business/legal policy.
- Assign clear owners for API, queue, workers, outbox, DR, dashboards, and cloud spend; managed services do not absolve the team of configuration and operational ownership.

### Avoid Creating Another Critical Single Point of Failure

If the queue temporarily refuses messages while the order DB stays up, **the outbox buffers events** for the relay to retry once the queue recovers, within system storage and age limits. Monitor **outbox age/backlog**; if growth risks filling the database, admission control must intervene. If producers publish straight to the queue without an outbox, explicitly document the failure contract when DB commit succeeds and queue publish fails.

If a queue requires multi-AZ availability, verify actual service guarantees, fault boundaries, retention, and recovery behavior—never assume every "managed" service automatically delivers your application's RTO/RPO.

## 12. Step Ten: Observability and Operational Procedures

### Core Metrics

| Group | Metrics | Purpose |
|---|---|---|
| **API** | RPS, accepted/rejected, 429/503, p50/p95/p99 latency, in-flight requests | Confirms intake control and accurate status responses |
| **Outbox** | Unpublished events, oldest event age, publish errors/latency | Detects risk of delayed or stalled event emission |
| **Queue** | Arrival rate, completion rate, depth, oldest age, redelivery count | Spots growing backlog, SLO breaches, or retry loops |
| **Worker** | Active/concurrency, job p95 latency, success/failure, CPU/RAM, timeouts | Reveals real throughput and bottlenecks |
| **Downstream** | 429s, timeouts, open circuit breakers, pool usage, quota headroom | Checks whether overload is spilling onto partners |
| **DLQ** | Message count, message age, failure reasons, replay throughput | Tracks abandoned or failed work |
| **Business** | Confirmed orders, missing invoices, delayed emails, failed loyalty credits | Measures actual customer impact |
| **Cost** | Worker-hours, queue requests/storage, egress, logs, cost per 1,000 jobs | Keeps spending aligned with budget and business value |

An alert like `"queue depth > 10,000"` can help, but is insufficient alone. Under huge throughput draining in a minute, 10,000 may be normal; a tiny backlog with messages sitting over 30 minutes is an active incident. Prioritize alerts on **message age, business latency, backlog growth rate, error rate, and projected drain time vs. deadline**.

### Backlog Surge Runbook

1. **Verify impact:** are orders still recording properly, what are 429/503 rates, and how delayed are invoices/notifications?
2. **Read signals:** compare arrival rate \(\lambda\), processing rate \(\mu\), queue age, retries, DLQ, outbox age, and downstream quotas.
3. **Isolate cause:** worker compute starvation, bad deploy, slow provider, exhausted DB connections, queue limit, or hot partition?
4. **Mitigate safely:** lower concurrency if throttled by a provider; scale workers if headroom exists; pause low-priority jobs; engage backpressure/admission caps per policy.
5. **Prevent duplicate damage:** never bulk-replay a DLQ without verifying idempotency, never purge a queue just to quiet a dashboard, and never raise limits blindly.
6. **Confirm recovery:** backlog drains as projected, oldest age returns within SLO, missing/duplicate events are reconciled, and spend normalizes.
7. **Follow up:** record timeline, root cause, alert thresholds, and action owners; update benchmarks or capacity plans.

### Express SLOs from the User's Perspective

Example SLO set to align on:

- **Intake API:** p95 latency under 300 ms **within the committed load envelope** for clearly defined endpoints/SLIs; payment processing carries its own SLA.
- **Notifications/invoices:** 95% of eligible events complete within 10 minutes of order confirmation.
- **Correctness:** financial and loyalty updates have reconciliation, idempotency, and remediation workflows; never claim "zero duplicates ever" unless every target guarantees it.
- **Recovery:** losing a worker never drops durably stored events and allows safe retries; define and drill RTO/RPO for broader outages.

Never treat a retry succeeding after 20 minutes as "meeting the 10-minute SLO" just because the email eventually arrived.

## 13. Well-Architected Trade-Offs

| Pillar | How the architecture helps | Trade-offs to evaluate |
|---|---|---|
| **Operational Excellence** | Separates API/workers; adds dashboards, runbooks, CI/CD, and on-call | More components needing owners, schemas, logging, and replay tools |
| **Security** | Role-scoped IAM, private queues, encryption, minimal payloads | More identities and data paths to configure and audit |
| **Reliability** | Durable queue + outbox + retries + DLQ; isolates provider outages | At-least-once introduces duplicates; huge backlogs still risk deadlines |
| **Performance Efficiency** | API skips waiting on side effects; queue-driven worker scaling, bounded concurrency | Cold starts and async latency; DB and downstreams can still bottleneck |
| **Cost Optimization** | Workers scale down when idle; demand-driven execution | Queues, storage, logs, retries, egress, and headroom add cost |
| **Sustainability** | Shuts down idle background compute; avoids sustained over-provisioning | Retry storms, duplicate data, and idle workers waste resources |

**Key nuance:** end-to-end reliability and performance do not improve automatically by adding a queue. Asynchrony shifts how failures manifest: HTTP timeouts turn into **queue latency or unfinished background work**. The design must keep those states **observable and owned**.

### Quick Cost Illustration

Assume effective worker compute costs **0.20 currency units/hour**, with **24 workers running for 15 minutes** to absorb a burst and drain backlog:

\[
C_{\text{compute}} = 24\times 0.25\times0.20=1.20
\]

currency units. This illustrates only the burst compute slice, **not total cost**. To compare against keeping 24 workers running all day, add queue/broker fees, retention, DB I/O, file storage, logs/tracing, egress, support, staffing, and retry overhead. Configure minimum workers and autoscaling to match real demand rather than running 24 workers 24/7 by default.

## 14. Phased Implementation Plan

Moving from synchronous to asynchronous changes API behavior and data contracts. Avoid flipping the whole system at once.

| Phase | Change | Verification before proceeding |
|---|---|---|
| **1. Measure baseline** | Capture API p95, RPS, provider durations, connection pools, errors, and cost | Clear view of bottlenecks and load profile |
| **2. Extract one low-risk side effect** | E.g., move order email to outbox + queue + worker | Durable events, lossless retries, duplicates handled safely |
| **3. Add load protection** | Per-tenant rate limits, admission control, bounded concurrency | Enforces committed caps without crashing DB/providers |
| **4. Migrate remaining side effects** | PDFs, loyalty, analytics by priority and ownership | Per-flow SLOs, reconciled records, owned DLQs |
| **5. Autoscale and observe** | Scale on queue age/backlog; add alerts and budgets | Peak drills meet SLOs |
| **6. Controlled go-live** | Canary/feature flags, phased rollout, runbooks | Compare against baseline; monitor errors and user behavior |

### Rollback Considerations

Code rollback is not trivial once events have been emitted. Before enabling the new flow, verify:

- The queue may still hold unprocessed events after disabling a feature flag.
- Re-enabling the synchronous handler while workers still drain can trigger **duplicate side effects**.
- Are old and new event schema versions mutually compatible?
- Can workers **drain** remaining messages, stop producers, and resume cleanly from a known point?
- If business errors occur, is a reconciliation job or compensating entry ready?

A risk-reduction option is deploying **consumers in shadow/dry-run mode** or on a small percentage where side effects permit, expanding only after reconciliation checks pass. For payment or customer-facing side effects, shadow runs must never leak uncontrolled real-world actions.

## 15. Load Testing and Failure Injection Plan

A design is complete only with test evidence:

| Scenario | Execution method | Acceptance criteria |
|---|---|---|
| **Normal load** | Hold normal-day RPS for sustained window | API, queue, DB, and downstreams stay stable with no backlog creep |
| **10x burst** | Ramp from 400 to 4,000 RPS for 5 minutes | Admission/429/503 behave per policy; accepted work durable; completion meets approved SLO |
| **Email provider failure** | Inject 429/5xx or timeouts for a test window | Workers back off without retry storms; queue/DLQ alerts fire |
| **Worker crash after side effect** | Kill worker after sending email/PDF, before ACK | Replay avoids corrupted side effects or reconciles cleanly |
| **Relay crash after publish** | Simulate broker ACK followed by relay crash before DB update | Duplicate event handled safely by idempotent consumer |
| **Slow DB / exhausted connections** | Cap connection pool or inject DB latency | Admission control avoids false acks; no transactions lost |
| **Queue temporarily unavailable** | Block publishes for a controlled period | Outbox buffers events, age alert fires, relay catches up post-recovery |
| **Malformed message schema** | Inject controlled invalid event | Quarantined/DLQ'd properly without infinite retries |
| **Out-of-order order updates** | Deliver stale event version after newer version | Newer state is never overwritten by stale event |
| **DLQ replay** | Fix bug and replay small batch | No duplicate points/emails beyond contract; full audit trail |
| **Compute/downstream quota cap** | Lower max workers or partner quota | Backpressure signals fire and recovery time matches projections |

**Go/no-go:** Proceed to broad rollout only when outbox/queue records suffer zero loss, duplicate handling is proven, core business functions behave accurately, on-call responders receive alerts, and SLOs hold across the committed load envelope. Otherwise, document safe operating caps and limit rollout scope while iterating.

## 16. Independent Design Exercise

Suppose a ticketing platform has these requirements:

- Averages **30 transactions/second**, surging to **300 transactions/second** for 8 minutes during ticket drops.
- Seat holds and payment results must be accurate; customers must never be double-charged due to client retries.
- Generating PDF tickets, sending emails, and recording analytics can complete within **15 minutes**.
- Ticket-generation workers benchmark at **3 jobs/second**, capped at **36 workers** max; the email provider enforces a **80 requests/second** quota.
- Operations has at most 3 rotating on-call engineers and wants to minimize infrastructure cost outside ticket drops.

Produce a design covering:

1. **Business boundaries:** which steps are synchronous vs. asynchronous? Which API statuses are returned while payment is unresolved?
2. **Architecture diagram:** edge/admission, hold/payment handling, database, outbox, queue, workers, DLQ, status endpoint, metrics/alerts.
3. **Sizing:** assuming one transaction creates one PDF job, compute arrival rate and 36-worker capacity; estimate backlog growth over 8 minutes assuming workers are immediately ready with zero retries, then estimate drain time once traffic drops back to average.
4. **Risk controls:** API and worker idempotency keys, retry policies, preventing duplicate credits/debits or holds, out-of-order messages, and respecting the email quota.
5. **Operations:** at least 6 metrics, 3 alerts, component owners, and a runbook when queue age exceeds 15 minutes.
6. **Well-Architected:** pick at least 3 pillars and explain trade-offs among reliability, performance, cost, and operational overhead.

### Solution Hints and Math Check

If each transaction creates **one PDF job** with zero failures:

\[
\lambda_{\text{peak}}=300\text{ jobs/s},\qquad
\mu=36\times3=108\text{ jobs/s}.
\]

Over an 8-minute peak (\(8\times60=480\) seconds):

\[
B_{\text{added}}=(300-108)\times480=92,160\text{ jobs}.
\]

Once traffic returns to 30 jobs/s, net drain capacity is \(108-30=78\) jobs/s:

\[
t_{\text{drain}}=\frac{92,160}{78}\approx1,181.5\text{ seconds}
\approx19.7\text{ minutes}.
\]

This shows **36 workers cannot drain the backlog within 15 minutes after the peak ends** under these assumptions. However, that alone **does not determine the exact fraction of jobs breaching the 15-minute SLO**, because the SLO is measured from each ticket's confirmation and depends on arrival timing, queue ordering, real latencies, and scaling speed. Measure or simulate **per-job end-to-end latency**. To create safety margin, the team can speed up PDF generation, raise the worker cap if allowed, trim work from the critical path, introduce controlled prioritization, or renegotiate the SLA with the business.

The **80 requests/s email quota** is a separate bottleneck: even if PDF generation reaches 108 jobs/s, you must throttle email-sending workers or isolate a separate queue/worker pool to prevent 429s and retry storms. Combining both steps sequentially inside one worker can lower real throughput below the simple model. Never run seat holds or payments on the same deferred async path without proving correctness and compensation.

### Self-Assessment Rubric (100 Points)

| Category | Max points | Signs of quality |
|---|---:|---|
| Accurate business contract and API states | 20 | No false acks; sound payment/hold handling; clear status model |
| Durable architecture and duplicate control | 20 | Sound outbox/queue/workers, idempotency, ACKs, and DLQ |
| Sizing and burst protection | 20 | Correct math; identifies bottlenecks and downstream quotas |
| Observability, runbooks, and ownership | 20 | Actionable metrics/alerts with clear owners |
| Security, cost, Well-Architected | 20 | Realistic trade-offs rather than one-sided optimization |

## 17. Pre-Review Design Board Checklist

- [ ] Separates **accepted / business completed / side effects completed**; HTTP responses never mislead clients.
- [ ] Mandatory synchronous steps uphold business invariants, especially payments and inventory.
- [ ] Request acceptance uses **durable persistence**, never in-process memory alone.
- [ ] Explicit decision on outbox or DB-queue consistency; acknowledges events can be redelivered.
- [ ] Consumers are idempotent or backed by side-effect reconciliation; never claims unproven exactly-once semantics.
- [ ] Rate limits, admission control, backpressure, and concurrency caps match DB/downstream quotas.
- [ ] Throughput, backlog, drain time, and **end-to-end latency** are calculated, including autoscaling lag, retries, and failures.
- [ ] Bounded retries, backoff/jitter, timeouts, DLQ, and safe replay procedures exist.
- [ ] Covers event ordering, schema versioning, poison messages, and late arrivals where needed.
- [ ] IAM, secrets, encryption, networking, sensitive-data logging, and retention are defined.
- [ ] API–outbox–queue–worker–downstream metrics, dashboards, alerts, runbooks, and owners are assigned.
- [ ] Tested against peak load, worker crashes, queue outages, provider 429s, duplicates, and rollbacks.
- [ ] Compares managed queue/worker costs, storage, egress, retries, and operational effort.
- [ ] Choices are justified against **Well-Architected** pillars and business-approved SLOs.

**Key takeaway:** Asynchronous processing is an architectural tool to **decouple processing time and absorb bursts within controllable bounds**. A solid design always pairs accurate state contracts with durable work persistence, safe duplicate handling, backpressure, capacity math, and clear operational ownership.
