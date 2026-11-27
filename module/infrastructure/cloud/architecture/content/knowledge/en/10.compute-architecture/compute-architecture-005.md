# Designing Background Processing, Scheduled Tasks, and Batch Jobs

## Learning Objectives

In **Cloud Architecture**, not every task should run directly inside an HTTP request while the user waits. Sending emails, generating reports, syncing ERPs, processing images, reconciling payments, and importing millions of records often take too long or depend on external systems. Offloading this work to **background processing** keeps APIs responsive, smooths load, and enables recovery after failures.

This lesson distinguishes three primary patterns: *event-driven/queue-based background processing*, *scheduled jobs*, and *batch processing*. These patterns can work together, yet differ in trigger mechanisms, data volume, state management, and recovery.

After this lesson, you will be able to select queues, workers, schedulers, managed jobs, or batch frameworks; design retries, timeouts, idempotency, DLQs, and checkpoints; estimate concurrency, throughput, backlog, completion times, and cost; monitor job state; and evaluate reliability, security, scalability, and operations under **Well-Architected** principles.

## 1. Why Background Processing?

An order-creation API might need to send an email, update inventory, generate a PDF invoice, and forward data to an analytics platform after persisting the order. Doing everything before returning the HTTP response ties response time to every external system. A slow email provider can time out the request even though the order was saved successfully.

A sound architecture separates the **critical synchronous path** (authentication, inventory/price validation, order persistence, and confirmation) from **work that can finish asynchronously** (notifications, report generation, analytics sync).

~~~mermaid
flowchart LR
    U["Client"] --> API["Order API"]
    API --> DB[("Order database")]
    DB --> OUTBOX["Outbox / event record"]
    OUTBOX --> Q[("Message queue")]
    Q --> W["Background workers"]
    W --> EMAIL["Email provider"]
    W --> ERP["ERP / Inventory"]
    W --> REPORT["Report storage"]
~~~

Events can be emitted via transactional outbox, CDC, managed event buses, or other mechanisms. The core rule is that authoritative business state must be durably persisted before the request is considered accepted; downstream work must have processing and reconciliation mechanisms.

### 1.1. When Not to Move Work to the Background

Not every operation can reply "done" before core work finishes. When reserving the last available slot, the API must verify the hold succeeded under concurrency rules. Simply dropping a reservation command onto a queue and returning success without confirmation risks making false commitments to users.

Distinguish three states:

- **Accepted:** work is saved for later processing with a tracking ID; does not mean business completion.
- **Processed:** a worker completed the task per technical criteria.
- **Business-confirmed:** the system satisfied the conditions the user or contract considers successful.

An API can return HTTP `202 Accepted` with a `jobId` for long-running unfinished work. For transactions requiring immediate confirmation, complete the core invariants before returning success.

## 2. Distinguishing Background, Scheduled, and Batch Work

| Type | Trigger | Characteristics | Example |
| --- | --- | --- | --- |
| Background / event-driven | Event, message, or recorded request | Asynchronous processing, usually per task | Sending email when an order is placed |
| Scheduled job | Time/schedule | One-off or recurring | Closing daily reports at 02:00 |
| Batch job | Schedule, operator request, or event | Processes large datasets, split into chunks/checkpoints | Reconciling 5 million transactions |
| Stream processing | Continuous incoming events | Computes over event-time/windows or state | Aggregating clicks per minute |

A nightly scheduled job may launch a batch run; the batch run splits a file into chunks and pushes each chunk onto a queue. Batch does not necessarily mean a single monolithic process, and a scheduled job is not necessarily batch. Classify by trigger, data volume, latency, and state management.

## 3. Components in a Background Processing Architecture

### 3.1. Producers, Queues, and Consumers

- **Producer:** component generating work items or messages.
- **Queue/broker:** stores messages and distributes them to consumers.
- **Consumer/worker:** pulls and executes work.
- **Retry policy:** governs retries on transient errors.
- **Dead-letter queue (DLQ):** holds messages exceeding retry limits or unable to proceed per policy.
- **Job store/status store:** persists business state, progress, and long-lived results.

~~~mermaid
flowchart LR
    P["Producer"] --> Q[("Queue")]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    W1 --> S[("Job status / DB")]
    W2 --> S
    W1 -->|Exceeds retry policy| DLQ[("DLQ")]
    W2 -->|Bounded retry| Q
    DLQ --> OPS["Investigate / Controlled replay"]
~~~

Queues decouple producer and consumer speeds, absorbing bursts within retention and capacity limits. However, queues **do not guarantee work executes exactly once** and do not replace business state. Messages can be redelivered after timeouts, worker crashes, or lost acknowledgements.

### 3.2. Schedulers and Job Runners

The scheduler decides **when** work is triggered. It can live in an orchestration platform, managed scheduler, cron service, or dedicated app. Responsibilities include computing the next run, triggering jobs/events, preventing overlapping schedules, logging runs, and handling timezones, holidays, DST, and business calendars.

Schedulers typically only **launch the job**; the job runner reads data, splits chunks, processes records, writes outputs, and checkpoints progress.

A batch runner may track job instances (a logical run for a parameter set), job executions (a specific run attempt), steps (stages), chunks (committed record batches), and checkpoints (last committed position). Metadata should record records read, written, skipped, failed, and timings.

## 4. Choosing a Work Distribution Mechanism

### 4.1. Synchronous Call or Queue + Worker?

| Criterion | Synchronous Call | Queue + Worker |
| --- | --- | --- |
| Response | Immediate result or timeout | Usually returns accepted acknowledgement |
| Coupling | Caller depends on downstream availability/latency | Producer and consumer are temporally decoupled |
| Burst traffic | Pressures downstream directly | Absorbs bursts within capacity limits |
| Retries | Caller handles retries | Worker/broker supports retry patterns |
| Observability | Request trace along the call path | Needs correlation IDs, job status, queue age |
| Consistency | Can share a transaction within data boundaries | Typically requires eventual consistency and reconciliation |
| Use when | Immediate result is required | Task can complete after the request returns |

Never push a mandatory transaction-confirmation step onto a queue and pretend it is already complete. Conversely, sending emails or building reports rarely needs to block the primary request.

### 4.2. Queues, Event Buses, and Workflows

- **Work queue:** multiple workers compete to process individual tasks.
- **Pub/sub or event bus:** multiple subscribers react independently to the same event.
- **Workflow orchestration:** manages multi-step flows, branching, timeouts, callbacks, or compensations.
- **Stream processing:** processes continuous data with event-time/windows and state.

A single broker may support multiple modes, yet semantics differ. Compare retention, ordering, throughput, message size limits, delivery guarantees, retry/DLQ support, integrations, cost, and operational effort.

### 4.3. Keep Messages Lean

Messages should carry IDs and routing metadata; place large payloads in object storage or a database.

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "report.export.requested",
  "jobId": "job-2026-0418",
  "tenantId": "tenant-42",
  "objectKey": "exports/source/2026-04-18.csv",
  "correlationId": "corr-9af2"
}
~~~

This example is illustrative. Workers must still verify authorization and validate the object/job. Never place tokens, passwords, unnecessary PII, or secrets inside messages.

## 5. Job Lifecycle and State

A long-running job needs explicit states instead of merely logging "started" and "finished."

~~~mermaid
stateDiagram-v2
    [*] --> Accepted
    Accepted --> Queued
    Queued --> Running
    Running --> Succeeded
    Running --> RetryScheduled
    RetryScheduled --> Running
    Running --> Failed
    Running --> CancelRequested
    CancelRequested --> Cancelled
    Running --> PartiallySucceeded
~~~

States can include `PENDING`, `QUEUED`, `RUNNING`, `RETRYING`, `SUCCEEDED`, `FAILED`, `CANCEL_REQUESTED`, `CANCELLED`, or `PARTIALLY_SUCCEEDED`.

Define valid transitions, who is authorized to cancel/retry/replay, how running jobs behave during deployments, whether timeouts can occur after side effects succeed, and how long results are retained.

For large jobs, store `jobId`, `tenantId`, job type, normalized parameters, creation time, attempts, progress, success/failure counts, and completion details. Never store full sensitive payloads in the status table when a reference to a protected data store suffices.

## 6. Idempotency: Safe Reprocessing

### 6.1. How Duplicates Happen

A worker pulls a message, sends an invoice successfully, and crashes before acknowledging. The broker redelivers the message; another worker could send the invoice a second time. Many queues provide at-least-once delivery or may redeliver—always read the actual service semantics.

Never promise business-wide exactly-once execution solely because a broker advertises a special delivery mode. Client retries, replays, and external system timeouts can still produce duplicate side effects.

### 6.2. Idempotent Consumers

An idempotent operation executed multiple times for the same business key leaves the final state identical to running once.

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Inside the consumer transaction:

1. Insert `consumer_name` + `message_id` enforced by a unique constraint.
2. If the key already exists, treat the message as already processed and skip duplicate side effects.
3. If the insert succeeds, update business state or generate outputs.
4. Commit the database before acknowledging per broker flow.

This pattern only protects side effects within the same DB transaction. For external payments or emails, you need downstream-supported idempotency keys, a delivery status table, an outbox, or reconciliation jobs. If the external system does not support idempotency, an internal table alone cannot prevent duplicate external side effects.

### 6.3. Distinguishing Key Types

- **`messageId`:** identifies a specific message instance.
- **`jobId`:** identifies a job execution run.
- **`businessKey`:** identifies the unique business operation, such as an invoice for an order.
- **`idempotencyKey`:** identifies retries of a logical request/command.

One event might emit multiple messages yet target issuing an invoice for the same order. Deduplicating by `messageId` alone will not stop business-level duplicates; choose the key matching the side effect you must protect.

## 7. Retries, Timeouts, Backoff, and DLQs

### 7.1. Classify Errors Before Retrying

| Error Class | Examples | Recommended Behavior |
| --- | --- | --- |
| Transient | Network timeout, HTTP 503, temporary rate limit | Retry with backoff, jitter, and caps |
| Permanent / bad data | Invalid schema, missing fields, non-existent tenant | Mark failed or route to DLQ for investigation |
| Business error | Order already cancelled, invoice already issued | Do not retry; return result or deduplicate |
| Auth failure | Expired or revoked credentials | Alert and fix permissions; avoid hammering retries |
| Overload | Exhausted DB pool, downstream throttling | Reduce concurrency, space out retries, apply backpressure |

Blindly retrying every error indefinitely causes retry storms, backlog buildup, higher bills, and cascading overload on struggling dependencies.

### 7.2. Exponential Backoff and Jitter

~~~text
delay(n) = min(maxDelay, baseDelay × 2^n) + randomJitter
~~~

For example, `baseDelay` of 1 second, `maxDelay` of 60 seconds, and random jitter between 0 and 1 second. Values must align with SLAs, queue retention, and downstream recovery times. Jitter reduces the risk of many workers retrying in lockstep.

Cap both attempt counts and total retry duration; afterward, move messages to a DLQ or mark the job failed for operator handling.

### 7.3. Dead-Letter Queues

A DLQ holds messages that exceed retry limits or cannot be processed. Operational procedures require alarms when message count or age climbs; visibility into failure reason, attempt count, `jobId`, `correlationId`, and consumer version; masking sensitive data; fixing data/configuration before controlled replay; and auditing who replayed what and the outcome.

A DLQ is not a bottomless trash bin: enforce retention, data classification, access controls, and investigation SLAs.

## 8. Schedulers and Recurring Tasks

### 8.1. A Schedule Does Not Guarantee Running Once

If three Spring Boot replicas each enable `@Scheduled` for 02:00, all three can run the job simultaneously. Scaling the app out scales duplicate cron executions.

Mitigations: run a dedicated scheduler; use a distributed lock with proper leases and fencing; use a managed scheduler to trigger targets; enforce a unique execution key in the DB on `jobType + businessDate + tenant`; or use a job orchestration service.

Distributed locks are not a silver bullet. A paused worker can resume after its lease expires while a new worker acquires the lock and runs concurrently. For critical writes, pair locks with fencing tokens, optimistic versioning, or idempotent write transactions.

### 8.2. Cron, Timezones, and Business Calendars

Cron examples below are illustrative; syntax varies across Unix cron, Spring, Quartz, and cloud services:

~~~text
0 0 2 * * *    # 02:00 daily, depending on scheduler syntax
0 */15 * * * * # every 15 minutes, depending on scheduler syntax
~~~

Clarify whether schedules use UTC or a business timezone such as `Asia/Ho_Chi_Minh`; DST rules where applicable; holidays/weekends; whether missed runs catch up; how overlapping runs behave; and whether execution windows follow event time or trigger time.

For "yesterday's report," lock the date boundary in the business timezone and convert it into consistent absolute timestamps. Never rely on individual workers' local clock settings if configs can differ.

### 8.3. Catch-Up and Preventing Missed Runs

If the scheduler is down from 01:50 to 02:20, the 02:00 run may need catch-up execution. An expected-run schedule table lets a reconciler detect periods missing an execution.

~~~sql
CREATE TABLE scheduled_job_runs (
    job_type VARCHAR(100) NOT NULL,
    business_date DATE NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (job_type, business_date, tenant_id)
);
~~~

On duplicate triggers, the unique constraint identifies already-registered periods. Define which periods qualify for catch-up, which are obsolete from a business standpoint, and who is authorized to trigger manual runs.

## 9. Batch Processing for Large Datasets

### 9.1. Splitting Data into Chunks

Loading millions of records into one in-memory list stresses the heap, triggers heavy GC, and causes OOMs. Batch jobs typically split data into chunks, processing and committing group by group.

~~~mermaid
flowchart LR
    SOURCE[("Source")] --> READER["Reader / Paging"]
    READER --> CHUNK["Chunk buffer"]
    CHUNK --> PROCESSOR["Validate / Transform"]
    PROCESSOR --> WRITER["Writer"]
    WRITER --> TARGET[("Target")]
    WRITER --> CHECK["Checkpoint"]
    CHECK -. resume .-> READER
~~~

A chunk size of 500 records is only a starting point; benchmark it. Too small increases commit and network overhead; too large increases memory pressure, lock duration, and rework cost on failure.

### 9.2. Offset, Keyset, and Cursor Paging

- **Offset paging:** `LIMIT 500 OFFSET 1000000`; simple, but large offsets force the DB to scan and discard huge row counts, and live writes during the batch shift result sets.
- **Keyset paging:** fetch rows beyond the last key read, e.g., `WHERE id > lastId ORDER BY id LIMIT 500`; efficient when keys are stable and indexed.
- **Cursor/streaming:** holds an open read cursor; watch transaction/connection duration and database/driver limits.

~~~sql
SELECT id, status, amount
FROM transactions
WHERE id > :last_seen_id
  AND created_at < :cutoff
ORDER BY id
LIMIT 500;
~~~

Stabilize the input set using a cutoff, snapshot, watermark, or ID list. If late-arriving data exists, querying solely by timestamps can skip or double-count records.

### 9.3. Checkpointing and Resuming

Checkpoints should record `jobRunId`, parameters/snapshot/cutoff, completed partitions/chunks, last committed key or watermark, read/write/skip/fail counts, timestamps, and schema version.

Update the checkpoint **only after** the chunk's output commits successfully. Checkpointing before writing risks data loss on crashes. If the writer commits before the checkpoint updates, the chunk may replay—so writers must be idempotent or upsert by business key.

### 9.4. Partitioning and Parallelism

~~~mermaid
flowchart TB
    JOB["Batch run"] --> P1["Partition 1"]
    JOB --> P2["Partition 2"]
    JOB --> P3["Partition 3"]
    P1 --> W1["Worker A"]
    P2 --> W2["Worker B"]
    P3 --> W3["Worker C"]
    W1 --> R[("Result / checkpoint")]
    W2 --> R
    W3 --> R
~~~

Every record must belong to exactly one partition with no overlaps or gaps; keys should distribute evenly; the same aggregate must not be updated concurrently if ordering matters; total concurrency must stay within DB/API limits; and failed partitions must be independently rerunnable.

Higher parallelism is not always faster. If many workers update hot tables or call an ERP capped at 100 req/s, adding workers only increases lock contention, throttling, and retries.

## 10. Choosing Compute for Workers

| Model | Best Suited When | Limits and Operations |
| --- | --- | --- |
| Long-lived worker | Steady throughput, continuous consumer loops, tight concurrency control | Graceful shutdown, memory leaks, zero-job-loss deploys |
| Function/serverless | Irregular traffic, short jobs, event-driven scaling | Timeouts, cold starts, quotas, concurrency, payload and invocation costs |
| Container job | Longer than function limits; needs specific runtime/libs/resources | Scheduler/orchestrator, retries, deadlines, resource requests/limits |
| Managed batch service | Large datasets, multi-step jobs, or specialized compute | Execution metadata, quotas, platform costs, operational skill |

A function timeout does not prove side effects never occurred; messages may still be redelivered. A function's or container's local filesystem should rarely be treated as durable state.

If an API and scheduler share one process, scaling the API duplicates the scheduler. Separate worker deployments even when sharing a codebase so lifecycles and scaling remain independent.

### 10.1. Graceful Shutdown and Deployments

During deployments, workers must stop pulling new work, finish or release held work per policy, persist checkpoints/state, and close connections. Visibility timeouts/leases must be long enough or properly renewed. Test `SIGTERM`, process kills, node restarts, and rolling deployments.

For multi-hour jobs, store execution state outside RAM and design for resume. Never rely on a single pod or VM staying alive uninterrupted until the job finishes.

## 11. Autoscaling, Backlogs, and Backpressure

Worker autoscaling should not look solely at CPU. Useful signals include queue depth, oldest message age, arrival rate, completion rate, processing latency, retry/DLQ rates, and downstream saturation such as connection pools, API quotas, and DB throughput.

### 11.1. Estimating Worker Count

Suppose 12,000 jobs are queued, each worker averages 4 jobs/second, and the target drain time is 100 seconds (ignoring new arrivals and overhead):

~~~text
worker_count = backlog / (throughput_per_worker × target_seconds)
             = 12,000 / (4 × 100)
             = 30 workers
~~~

This is theoretical. If downstream permits only 60 requests/second, 30 workers × 4 req/s generates 120 req/s and overloads it. Enforce concurrency caps, rate limits, and size around the **narrowest bottleneck** end to end.

### 11.2. Backpressure

Queues absorb bounded bursts—they do not create infinite capacity. You can throttle producers, cap worker concurrency, reserve downstream quotas, prioritize critical jobs, defer low-priority batches, or reject new requests when capacity is exhausted.

Set backlog/retention thresholds and alert before queue age breaches SLOs. If messages sit longer than queue retention, data can expire before processing.

## 12. Multi-Step Workflows

A reconciliation process might gather transactions, fetch payment gateway reports, match records, classify discrepancies, generate reports, and await sign-off. When flows involve hours/days of waiting, conditional branches, timeouts, and compensations, a workflow orchestrator/state machine is often easier to maintain than one giant function.

| Pattern | When Suitable | Caveats |
| --- | --- | --- |
| Self-orchestrated worker | A few simple, short steps | State/recovery gets brittle as code grows |
| Queue chain | Independent, event-driven stages | Harder to track dependencies, ordering, and mid-chain failures |
| Workflow orchestration | Many steps, long waits, branching, timeouts, compensation | Service cost, learning curve, workflow versioning |
| Batch framework | Bulk reads/writes with steps/chunks/checkpoints | Execution metadata and job store management |

Match tool complexity to the problem; you do not need a workflow engine merely to send one email after an order.

## 13. Security for Background Processing

Workers typically operate without an interactive user present, making service accounts prone to over-privileging.

1. **Least privilege:** each worker type accesses only the queues, tables, buckets, and APIs it requires.
2. **Identity separation:** notification workers should not write to payment ledgers; report workers should not modify user profiles.
3. **Secret management:** fetch credentials from a secret manager with rotation and revocation; never embed them in messages or images.
4. **Tenant isolation:** preserve tenant context, validate sources and permissions; never blindly trust `tenantId` inside payloads.
5. **Data protection:** encrypt messages/storage, minimize PII in logs, restrict DLQ and export access.
6. **Auditing:** log who requested, who replayed/cancelled, which service identity executed, and what data changed.
7. **Network controls:** allow only required ingress/egress.

Large-scale data batches should support dry runs or confirmation gates before irreversible actions. Bounding record counts, tenant scope, and date ranges limits blast radius if parameters are wrong.

## 14. Observability: Measuring Actual Work

A successful API call only proves intake, not job completion.

**Intake API:** rate of valid job-creation requests, enqueue/job-store latency, validation/authorization/capacity errors.

**Processing pipeline:** queue depth, oldest age, end-to-end job duration, success/failure rates, attempts, retries and DLQ counts, batch records read/written/skipped/failed, checkpoint age, worker saturation, downstream latency, and cost.

### 14.1. Correlation and Audit Trail

Every long-running job needs a `jobId`; messages carry `eventId`/`messageId`; traces carry `correlationId`. When a job spawns child messages, preserve parent/child links for tracing.

Logs must answer: who requested it, for which tenant, with what input/version, which attempt, which worker/version executed, how many records were read/written/skipped, why it failed, and who replayed it. Avoid logging raw sensitive payloads; use reference IDs, retention policies, and access controls.

### 14.2. Impact-Based Alerts

- Payment queue oldest message age crosses threshold.
- Reconciliation batch incomplete before financial close.
- Unusual spike in DLQ volume.
- Job stuck in `RUNNING` past expected timeout.
- Scheduled report missing for its expected window.
- Workers continuously throttled or downstream quotas breached.

A silent job does not mean success. For critical recurring jobs, use an **expected-run monitor/heartbeat** to alert when a scheduled run fails to appear on time.

## 15. Illustrative Quality Scenarios and SLOs

Thresholds below are learning examples requiring business validation.

| ID | Stimulus / Context | Expected Response | Measure |
| --- | --- | --- | --- |
| QA-BG-01 | Order confirmed | Notification job created and processed asynchronously | 99% of valid jobs start within 60s without blocking order response |
| QA-SCH-01 | 02:00 in business timezone | Prior day's report generated once per period | Job created within a 5-min window; one valid output per business key |
| QA-BAT-01 | 5 million transactions to reconcile | Partitioned/chunked with checkpoints and resume | Completes within 90 min; read/write/skip counts reconcile |
| QA-REL-01 | Worker dies after side effect before ACK | Redelivered message causes no duplicate side effects | Zero duplicate invoices in retry test suite |
| QA-COST-01 | Queue surges 5× | Autoscales within downstream limits | Oldest message age returns below threshold; cost/job stays within budget |
| QA-SEC-01 | Staging or tenant A requests tenant B data | Denied and audited | 100% of unauthorized test cases blocked with zero data leaks |

Define start/end measurement points, eligible job sets, observation windows, and exclusions. "Job starts within 60 seconds" differs from "job completes within 60 seconds." Batches must measure until valid business results are persisted.

## 16. TCO and Cost Example

Suppose a system processes 100,000 notification jobs daily. Two options: always-on container workers or event-driven functions running only per message. TCO must cover compute/memory/duration, queues, logging, networking, retries, minimum capacity, cold starts, and operational effort.

Hypothetical example, in million VND/month:

| Line Item | A: Container Workers | B: Event-Driven Functions |
| --- | ---: | ---: |
| Compute/runtime | 18 | 12 |
| Queue/broker | 5 | 5 |
| Network and egress | 3 | 4 |
| Logs/metrics/tracing | 4 | 5 |
| Allocated operations | 10 | 7 |
| Retries/DLQ and state store | 2 | 2 |
| **Total** | **42** | **35** |

These figures are illustrative, not a price quote. Real decisions depend on volume, average/tail duration, memory, concurrency, quotas, and current pricing.

~~~text
Cost per successful job
    = Total processing cost in period
      / Number of successful business jobs

Cost per million records
    = Total batch compute + storage + network cost
      / (Successfully processed records / 1,000,000)
~~~

Include retries, failed jobs, manual interventions, and backlog costs—not just the final successful run.

## 17. Case Study: Revenue Reporting and Order Notifications

A booking platform uses Spring Boot and PostgreSQL. When a booking is confirmed, it sends an email; daily at 02:00 Vietnam time it generates a report; at month-end it reconciles several million records.

Hypothetical requirements: email delivery attempted within 2 minutes; daily report finished before 03:00; monthly batch under 90 minutes; zero duplicate emails or invoices; data discrepancies reconciled.

### 17.1. Three Work Streams

**A. Event-driven email:** Once the booking transaction commits, a `BookingConfirmed` event is reliably emitted (e.g., via an outbox). Consumers read the queue and send emails using an idempotency key built from booking + template type. Transient failures retry; malformed data goes to a DLQ.

**B. Scheduled reporting:** The scheduler generates a `jobRunId` for each `businessDate`. A unique key prevents duplicate period runs. The batch reads the prior day's snapshot/watermark, aggregates, writes to object storage, updates status, and sends alerts. A reconciler detects missed runs and triggers catch-up executions.

**C. Batch reconciliation:** The job reads a closed record set, partitions by ID ranges, processes chunks, commits outputs, and checkpoints. Failed partitions rerun independently; outputs use business-key upserts to avoid duplicates.

~~~mermaid
flowchart TB
  DB[("Booking DB")] --> OUTBOX["Transactional outbox"]
  OUTBOX --> Q[("Notification queue")]
  Q --> EMAIL["Email worker"]
  SCHED["Daily scheduler"] --> DAILY["Daily report job"]
  DB --> DAILY
  SCHED2["Month-end scheduler"] --> BATCH["Reconciliation batch"]
  DB --> BATCH
  BATCH --> CHUNKS["Partition / chunk workers"]
  CHUNKS --> RESULT[("Reconciliation results")]
  DAILY --> STORE[("Object storage")]
~~~

### 17.2. Operations and Recovery

- Dashboards track queue age, email attempts, DLQ counts, on-time reports, chunks/partitions, and job duration.
- If the email provider goes down for 15 minutes, the booking API stays healthy; workers hold messages and retry.
- If batch partition 8/20 fails, resume from committed checkpoints and rerun the failed partition.
- If the scheduler stops, the expected-run monitor alerts on missing jobs; operators trigger an idempotent catch-up.
- If source data changes after batch close, use snapshots/reconciliation or publish a new report version rather than silently overwriting results.

## 18. Design and Implementation Workflow

1. **Classify work:** event-driven, scheduled, batch, or stream; isolate synchronous response needs.
2. **Define outcomes:** accepted, running, succeeded, failed, or partially succeeded; what the API returns and how clients track progress.
3. **Select mechanisms:** queues, event buses, workflow engines, schedulers, or batch frameworks matching required semantics.
4. **Identity and idempotency:** job IDs, event IDs, business keys, tenant keys, and deduplication.
5. **Failure handling:** timeouts, retries, backoff, DLQs, cancellation, replay, and reconciliation.
6. **Choose compute:** worker services, container jobs, serverless functions, or managed batch.
7. **Capacity:** arrival/service rates, retention, downstream limits, backpressure, and autoscaling.
8. **Schedule/batch:** timezones, missed runs, overlap, chunking, partitioning, and checkpointing.
9. **Security:** service identities, least privilege, tenant isolation, secrets, encryption, and auditing.
10. **Testing:** duplicate delivery, crashes, timeouts, scheduler outages, DLQs, replays, and heavy load.
11. **Operational handover:** runbooks, dashboards, alerts, owners, budgets, and drills.

### 18.1. Sample Job Definition

~~~yaml
job_type: monthly_reconciliation
owner: finance-platform
trigger:
  type: schedule
  expression: "0 0 2 1 *"
  timezone: "Asia/Ho_Chi_Minh"
input:
  business_period: previous_month
  source_snapshot_required: true
execution:
  mode: batch
  chunk_size: 1000
  max_concurrency: 8
  checkpoint_enabled: true
reliability:
  idempotency_key: "job_type+business_period+tenant_id"
  max_attempts: 5
  backoff: exponential_with_jitter
  dead_letter_enabled: true
limits:
  timeout_minutes: 90
  downstream_requests_per_second: 50
observability:
  publish_progress: true
  alert_on_late_start: true
  alert_on_dead_letter: true
status: proposed
~~~

This is illustrative metadata, not a schema for a specific scheduler. Always define explicit timezones, business periods, and missed-run policies.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning "completed" upon enqueuing | False commitment to users | Separate accepted from completed |
| Assuming queues guarantee exactly-once | Duplicate side effects on crashes/retries | Enforce business-key idempotency |
| Infinite retries | Retry storms, backlogs, and high cost | Classify errors, backoff, cap attempts, use DLQs |
| Every replica running cron locally | Recurring jobs run multiple times | Dedicated scheduler, unique run key, or lock |
| Keeping progress only in RAM | Restarts lose checkpoints | Persist state/checkpoints |
| Batch loading everything into memory | OOMs and GC stalls | Chunking/keyset/cursors |
| Unbounded worker scaling | Downstream overload | Concurrency caps and backpressure |
| Replaying entire DLQ at once | Traffic spikes and duplicate side effects | Batched, audited, throttled replay |
| Omitting timezones | Wrong date cutoffs, missed periods | Record explicit timezones and business dates |
| Ignoring missed schedules | Silent missing reports | Expected-run monitors and catch-up |
| Skipping tenant checks in workers | Cross-tenant data leaks | Enforce authorization and scope checks |

## 20. Practice Exercise

A Java/Spring Boot e-commerce system needs to send emails, update inventory, and feed analytics after payment; aggregate revenue daily at 01:30; and reconcile 8 million transactions at month-end. The operations team has 6 engineers. Emails must be attempted within 2 minutes, daily reports finished before 02:30, and monthly batches within 90 minutes with zero duplicate processing.

1. Classify each stream into synchronous/background/scheduled/batch/stream.
2. Diagram the API, DB transactions, outbox/queues, workers, schedulers, batch partitions, and report storage.
3. Design job states, `202 Accepted` API responses, and status tracking endpoints.
4. Select `messageId` and `businessKey` for invoice issuance; prevent duplicates when crashing before ACK.
5. Propose retry/backoff/DLQ policies for timeouts, invalid schemas, rate limits, and expired credentials.
6. Calculate theoretical worker count for a 240,000-record backlog at 20 records/sec per worker to finish in 10 minutes; then adjust for a 300-record/sec DB cap.
7. Design chunking/partitioning/checkpointing and resume without writing duplicate results.
8. Schedule 01:30 in `Asia/Ho_Chi_Minh`; prevent overlap and catch up after scheduler downtime.
9. Define a dashboard and at least four alerts covering queue age, DLQ, job duration, batch progress, and missed schedules.
10. Draft a hypothetical TCO comparing container workers vs. serverless.

**Self-assessment tip:** A strong answer details business states, delivery semantics, deduplication, recovery, resource caps, and completion evidence—merely naming technologies is not enough.

## 21. Pre-Production Checklist

- [ ] Immediate-response paths are separated from deferred work.
- [ ] APIs distinguish acceptance from business completion.
- [ ] Every job/message carries identifiers, business keys, and tenant scope.
- [ ] Consumers handle duplicate messages safely; external side effects enforce idempotency/reconciliation.
- [ ] Retries enforce timeouts, backoff/jitter, attempt caps, and DLQs.
- [ ] Dashboards/runbooks exist for DLQs, retries, replays, cancellations, and stuck jobs.
- [ ] Scheduled jobs define timezones, unique execution keys, overlap rules, and catch-up.
- [ ] Batches use chunking/partitioning/checkpointing; checkpoints advance only after commit.
- [ ] Concurrency/autoscaling respects downstream database/API limits.
- [ ] Backpressure and backlog/retention bounds are configured.
- [ ] Workers enforce least privilege, secret management, tenant isolation, and auditing.
- [ ] Job statuses, correlation IDs, logs/metrics/traces, and expected-run monitors are active.
- [ ] Crashes, timeouts, restarts, duplicate deliveries, missed schedules, and replays have been tested.
- [ ] TCO includes retries, storage, networking, observability, and staffing.

## 22. Well-Architected Evaluation

| Pillar | Background Processing Design Questions |
| --- | --- |
| **Operational Excellence** | Do jobs have owners, runbooks, dashboards, replay/cancel tools, and expected-run alerts? |
| **Security** | Do workers have least privilege, tenant isolation, secret management, and auditing? |
| **Reliability** | Have retries, idempotency, checkpoints, DLQs, catch-up, and recovery been tested? |
| **Performance Efficiency** | Do chunks, partitions, concurrency, and autoscaling fit real loads and downstream limits? |
| **Cost Optimization** | Is always-on compute or event-driven cheaper; what is the cost per job and per million records? |
| **Sustainability** | Are redundant processing, unnecessary data scans, and excessive idle workers avoided? |

**Conclusion:** Background processing, scheduled jobs, and batches decouple long-running work from request paths, control load, and enable failure recovery. However, queues, schedulers, and batch engines do not guarantee correctness by themselves: systems still require durable state, idempotency, bounded retries, checkpointing, observability, and reconciliation. Choose patterns based on business requirements and measurable trade-offs across reliability, security, scalability, cost, and operations in the spirit of Well-Architected.
