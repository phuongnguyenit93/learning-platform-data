# Dead-Letter Queues and Recovering Failed Events

## Lesson Objectives

In event-driven serverless architectures, an event is typically sent from a producer to a queue, event bus, or trigger service that invokes a function. The function may fail due to temporarily unavailable dependencies, invalid input data, timeouts, concurrency limits, or code bugs. Retrying indefinitely lets a single failing event consume resources, grow the backlog, and impact healthy events. Dropping the event after the first failure risks losing valid work.

A dead-letter queue (DLQ) provides a place to quarantine events that have exceeded processing policies or cannot proceed through the normal flow. A DLQ retains data for investigation and controlled recovery. It does not automatically fix errors, nor does it guarantee that events will succeed upon reprocessing.

After this lesson, you will be able to:

- Describe the event processing flow in serverless architectures and its potential failure points.
- Classify transient errors, data errors, and configuration errors.
- Design retries, backoff, jitter, timeouts, and attempt limits.
- Distinguish DLQs, retry queues, failure destinations, and event archives.
- Configure policies for routing failed events to a DLQ.
- Design idempotency to handle duplicate events safely.
- Investigate poison messages and recover events via redrives.
- Monitor backlogs, message age, failure rates, and operational costs.
- Build runbooks and test recovery without causing secondary incidents.

## 1. Event Processing Flow in Serverless

A serverless application typically receives events from queues, event buses, object storage, database streams, schedulers, or other services. The platform invokes the function directly or delivers events to the function via an event source mapping/poller.

General flow:

1. A producer creates an event and sends it to the event source.
2. The event source stores or routes the event according to the service's mechanism.
3. The function is invoked or a poller fetches a batch of events.
4. The handler validates, executes business logic, and writes results.
5. Upon success, the event is acknowledged, deleted from the queue, or its offset is committed per source semantics.
6. Upon failure, the platform retries, retains, routes to a DLQ, or writes to a failure destination depending on configuration.

~~~mermaid
flowchart LR
    P["Producer"] --> S["Queue / Event bus / Stream"]
    S --> F["Serverless function"]
    F --> D["Dependency / Database"]
    F -->|Success / ack| C["Complete event"]
    F -->|Failure| R["Retry policy"]
    R -->|Retry succeeds| C
    R -->|Attempts exhausted| Q["Dead-letter queue"]
    Q --> O["Observe and investigate"]
    O --> X["Repair and redrive"]
    X --> S
~~~

Each service has distinct delivery, retry, and acknowledgment rules. A function invoked asynchronously directly may use the platform's retry policy; a function polling a queue may rely on visibility timeouts and receive counts; stream consumers may be governed by offsets and checkpoints. Never apply a one-size-fits-all DLQ configuration across all event sources.

## 2. Why Do Events Fail Processing?

Errors must be classified before choosing an action. Retrying every error identically can make matters worse.

| Error Category | Examples | Typically Appropriate Action |
|---|---|---|
| Transient | Network timeout, database failover, throttling, dependency returning 503 | Retry with backoff and limits |
| Invalid data | Missing required field, schema mismatch, malformed payload | Quarantine or DLQ early; do not retry blindly |
| Unrecoverable business error | Account does not exist, invalid order state | Record clear business outcome; DLQ/quarantine if investigation needed |
| Configuration or permission error | Expired credentials, IAM deny, wrong endpoint | Stop or curb retries, alert operations, and fix config |
| Resource error | Out of memory, concurrency, quota, or load-induced timeout | Reduce concurrency, adjust capacity reasonably, retry with control |
| Code bug | Null reference, unhandled event variant | DLQ after attempt limit; fix code and test replay |

An HTTP 429 may signal temporary throttling and should respect `Retry-After` if present. A `401`/`403` authentication/authorization error usually cannot be resolved by continuous retries until credentials or policies are fixed. A schema-invalid payload will typically continue failing on every attempt until the data or code is corrected.

### 2.1. Distinguishing Retryable vs. Non-Retryable

The handler or orchestration layer should classify errors:

- Retryable: errors likely to resolve on their own after some time.
- Non-retryable: data errors or business rule violations that waiting cannot fix.
- Unknown: unclassified errors; apply bounded retries and log enough context for investigation.

Do not swallow exceptions and return success simply to avoid retries. When a handler reports success without completing the work, the platform may delete/acknowledge the event and the work is lost.

### 2.2. Timeouts and Processing Duration

Function timeouts, queue visibility timeouts, retry durations, and message retention periods must work in harmony.

If the visibility timeout is shorter than actual processing time, a message can become visible again while the previous execution is still running. Two workers may process the same event concurrently, causing duplicate side effects.

Set timeouts based on p95/p99 processing time distributions plus an adequate buffer. For batches, account for total batch processing time and result persistence. Investigate timeout occurrences instead of raising timeouts indefinitely.

## 3. Delivery Semantics and Handling Duplicates

Many queues and event sources provide **at-least-once** delivery: an event may be redelivered if acknowledgment is lost, the consumer times out, or the platform cannot confirm completion. Some streams use dedicated checkpoint/offset mechanisms. Certain services offer near exactly-once options within specific scopes, but you should never assume application-wide side effects are automatically exactly-once.

Scenarios that produce duplicates:

- The function writes to the database but times out before acknowledging.
- The consumer finishes processing but loses connectivity before committing the offset.
- Queue visibility timeout expires while the original worker is still running.
- The producer resends because it received no confirmation.
- A redrive reintroduces partially processed events into the flow.
- The platform retries an invocation after a transient error.

Therefore, handlers must be idempotent: processing the same event multiple times produces no extra unintended side effects.

### 3.1. Idempotency Keys

Each event should carry a stable identifier, such as `eventId`, `transactionId`, or a business key. Persist processing state under that key.

A pattern:

1. Receive the event and extract the idempotency key.
2. Check the deduplication/inbox table.
3. If the key is already completed, return success without repeating side effects.
4. If absent, process inside a transaction or consistency-preserving mechanism.
5. Record the outcome and mark the key completed.
6. Acknowledge only after state is durably persisted.

Never use a fresh invocation ID generated per retry as the idempotency key, because each attempt can receive a different ID even for the same business event.

### 3.2. Transactional Inbox and Outbox

When a consumer must write to a database and emit a subsequent event, the inbox/outbox pattern can be used:

- Inbox stores received event IDs and processing status in the same transaction as business updates.
- Outbox writes outgoing events in the same transaction as business data.
- A separate publisher reads the outbox and emits events; duplicate emissions are still handled idempotently downstream.

This reduces the risk of updating the database successfully while failing to emit the event, or emitting the event while the business transaction rolls back.

### 3.3. Idempotent Handler Example

Illustrative Java snippet:

~~~java
public ProcessingResult handle(Event event) {
    String key = event.eventId();

    if (inbox.isCompleted(key)) {
        return ProcessingResult.success();
    }

    try {
        transaction.execute(() -> {
            if (inbox.isCompleted(key)) {
                return;
            }

            validate(event);
            applyBusinessChange(event);
            inbox.markCompleted(key);
        });

        return ProcessingResult.success();
    } catch (TransientDependencyException e) {
        return ProcessingResult.retry(e.getMessage());
    } catch (InvalidEventException e) {
        return ProcessingResult.permanentFailure(e.getMessage());
    }
}
~~~

This is conceptual code. In a real implementation, checking the inbox, applying business changes, and marking completion must share the same transaction or use locking/unique constraints to prevent race conditions between two concurrent consumers.

## 4. Retry Policies

A retry policy specifies when to retry, how many times, and the spacing between attempts.

A policy typically defines:

- Maximum attempts or maximum receives.
- Initial delay.
- Backoff multiplier.
- Maximum delay.
- Jitter.
- Maximum event age or retention.
- Per-invocation timeout.
- Action when retries are exhausted.

### 4.1. Exponential Backoff

Exponential backoff increases the wait interval after each failure:

~~~text
delay(n) = min(maxDelay, initialDelay * 2^n)
~~~

Example with initial delay 1 second, max delay 60 seconds:

| Retry Attempt | Illustrative Delay |
|---:|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |
| 6 | 32 seconds |
| 7 onward | Up to 60 seconds |

Actual formulas may index attempts differently. This is an illustrative schedule, not a universal platform default.

### 4.2. Jitter

If many functions fail together due to one dependency, they may retry simultaneously and trigger a fresh load spike. Jitter adds randomness to delays to spread out retries.

A common formula:

~~~text
delay = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Several jitter variants exist; select one suited to your system. Maintain both a max delay and maximum attempts so retries do not drag on indefinitely.

### 4.3. Bounded Retries

Retries must be bounded by both attempt count and event age. An overly stale event may no longer be valid for business logic, such as updating an order status after a payment window has closed.

Decisions to make:

- Retry all errors or only transient ones?
- What is the maximum number of attempts?
- How long may an event stay in the queue?
- After exhausting retries, which DLQ or failure destination receives it?
- During widespread dependency outages, is there a circuit breaker or consumer pause?
- Can producers be slowed down or backpressured?

Retries do not replace backpressure. If producers emit events faster than consumers process them, queue backlogs still grow even with well-tuned retries.

## 5. What Is a Dead-Letter Queue?

A dead-letter queue is a dedicated queue or storage target that receives messages that could not be processed successfully under the source's policy. Messages routed to a DLQ usually include the payload and enough metadata to investigate, recover, or discard them.

A DLQ helps:

- Isolate poison messages so they do not block the main pipeline.
- Preserve payloads and metadata for investigation.
- Allow healthy events to continue processing.
- Measure failure rates and trigger alerts.
- Recover work after fixing code, data, or dependencies.
- Separate error handling workflows from normal business flows.

A DLQ does not automatically process or fix events. Without monitoring, retention, ownership, and runbooks, a DLQ becomes a graveyard of forgotten data.

### 5.1. DLQs, Retry Queues, and Failure Destinations

| Mechanism | Purpose | When to Use |
|---|---|---|
| Retry queue | Hold events waiting for retry after a delay | Transient errors needing custom delay/backoff |
| Dead-letter queue | Quarantine messages that exhausted retry policies or cannot be processed | Poison messages, sustained errors, investigation required |
| Failure destination | Record failed invocation outcomes, potentially with request/response context | Certain asynchronous function platforms |
| Event archive | Store event history for auditing or time-based replay | Event buses needing retention and replay |
| Quarantine store | Store malformed or suspicious payloads outside the main flow | Invalid data, security risk, or manual review needed |

Naming and structures vary by service. Failure destinations may store richer records than message-only DLQs. Event archives typically retain events long-term and are not exclusively for failed events.

### 5.2. Queue DLQs vs. Asynchronous Function DLQs

Distinguish two cases:

**Queues with redrive policies:** a message is received by consumers multiple times without being acknowledged/deleted. Once the receive count exceeds the threshold, the queue service moves the message to the DLQ.

**Asynchronous function invocations:** the platform stores the invocation event and retries automatically per policy. Upon exceeding max age or max attempts, it can route to a DLQ or failure destination depending on the product.

With a function polling a queue, handler errors prevent message deletion and trigger redelivery after visibility timeout. With async function invocations, retries are controlled by the platform. The DLQ concept is similar, but location and metadata differ.

## 6. Poison Messages and Failure Loops

A poison message is an event that repeatedly causes consumers to fail. Causes may include:

- Malformed payload or missing required fields.
- Incompatible schema version.
- Edge-case values triggering a bug.
- Payload size exceeding processing limits.
- A dependency consistently rejecting a certain request type.
- Event referencing a deleted resource.
- Consumer incompatible with data emitted by a newer producer version.

If a poison message sits at the head of a FIFO queue or stream partition, it can block subsequent messages depending on source semantics. Even in unordered queues, it wastes worker capacity and drives up retry costs.

### 6.1. Identifying Poison Messages

Symptoms:

- The same event ID or message group repeatedly fails.
- Receive counts climb rapidly.
- One payload produces the exact same exception on every attempt.
- DLQ depth grows while the main queue stops draining.
- One partition/ordering key shows abnormally high lag.
- Errors cluster around a single schema version or producer.

Log the event ID, source, event type, schema version, attempt count, error class, and correlation ID. Do not log full payloads if they contain sensitive data.

### 6.2. Do Not Retry Permanent Errors Infinitely

If a payload is invalid, retrying 30 seconds later rarely makes the data valid. Route directly to quarantine/DLQ after validation. If failures stem from newly deployed code, pausing consumers or rolling back the release may be better than letting every message churn through full retry cycles.

Avoid overly broad rules that send transient errors to the DLQ prematurely. Classify by exception, error code, and dependency context.

## 7. Configuring Queue Redrive Policies

A queue can define a redrive policy to move messages to a DLQ after a maximum receive count. Common fields include:

- Target DLQ.
- Maximum receive count.
- Retention periods for both source queue and DLQ.
- Permissions allowing the source queue to send messages to the DLQ.
- Encryption and key policies.
- Redrive allow policies if the service restricts which source queues may use a DLQ.

Conceptual configuration example, not bound to a specific API schema:

~~~yaml
queue:
  name: orders-events
  visibilityTimeout: 120s
  messageRetention: 4d

  redrive:
    deadLetterQueue: orders-events-dlq
    maxReceiveCount: 5

deadLetterQueue:
  name: orders-events-dlq
  messageRetention: 14d
  encryption: enabled
  alertWhenVisibleMessagesAbove: 0
~~~

These fields only illustrate the concepts. Exact property names, units, limits, and semantics depend on the actual queue service. In particular, verify that the visibility timeout exceeds reasonable maximum processing time and that queues have enough retention for recovery.

### 7.1. Choosing Maximum Receive Count

Too low a threshold sends valid messages to the DLQ during brief dependency blips. Too high a threshold keeps poison messages looping, burning compute and building backlogs.

Base the threshold on:

- Frequency of transient errors.
- Dependency recovery time.
- Per-attempt processing duration.
- Visibility timeout and backoff.
- Maximum meaningful event age.
- Retry cost and error detection speed.

If a queue does not support per-message increasing delays, use tiered retry queues with different delays or separate orchestration. Avoid creating unbounded retry loops across multiple queues.

### 7.2. Retention and Recovery Window

The DLQ must retain messages long enough for operations teams to detect, investigate, and fix bugs. Retention must exceed realistic response times, including weekends or waiting on business teams.

Verify how the service calculates message age after moving to a DLQ. Some services preserve the original timestamp or apply separate retention rules; never assume moving to a DLQ automatically resets message age.

Alert before messages approach retention expiration. For events with business deadlines, store both `occurredAt` and `expiresAt` so redrives do not reprocess expired events.

## 8. Metadata to Preserve in the DLQ

During investigation, the payload alone is insufficient. Preserve traceable metadata:

| Field | Purpose |
|---|---|
| `eventId`/`messageId` | Stable identifier for deduplication |
| `source` | Producer or originating source |
| `eventType` | Business event type |
| `schemaVersion` | Payload structure version |
| `occurredAt` | Timestamp when the event occurred |
| `enqueuedAt` | Timestamp when enqueued |
| `correlationId`/`traceId` | Links logs and traces |
| `attemptCount` | Attempts made if provided by source |
| `firstFailureAt`/`lastFailureAt` | Failure time span |
| `errorCode`/`errorClass` | Root cause classification |
| `consumerVersion` | Processing code version |
| `tenantId`/`partitionKey` | Business scope or ordering key |
| `expiresAt` | Timestamp after which the event is no longer valid |

Not every provider automatically attaches all these fields. You may need an event envelope at the producer or additional metadata in the failure destination.

Never overwrite the original payload when routing to a DLQ. If transformation is needed for recovery, retain the original and store the transformed version alongside mapping/version info for auditability.

## 9. DLQ Investigation Workflow

When messages land in the DLQ, assess impact before redriving.

Workflow:

1. Confirm the alert and scope of queue/function/target.
2. Measure message count, oldest message age, and inflow rate.
3. Group by event type, error code, schema version, and consumer version.
4. Select representative messages for inspection.
5. Check logs, traces, deployment history, and dependency health.
6. Determine whether the cause is bad data, a code bug, misconfiguration, or a dependency outage.
7. Decide whether to fix the producer, fix the consumer, transform payloads, or discard events per business rules.
8. Test the fix against failing messages in a safe environment.
9. Select the recoverable subset of messages.
10. Redrive with rate limits and monitor results.

### 9.1. Action Classification

| Investigation Finding | Action |
|---|---|
| Dependency recovered, payload valid | Redrive in batches with rate limiting |
| Consumer bug fixed | Test new version, then redrive |
| Old schema can be transformed | Run versioned migration/reprocessor, preserve original |
| Invalid payload | Quarantine, ask producer to fix, or handle manually |
| Duplicate event already completed | Deduplicate and mark resolved |
| Event expired for business purposes | Do not redrive; record decision and audit |
| Security issue or sensitive data | Restrict access, follow security incident process |

Never redrive the entire DLQ simply because the main queue is empty. First confirm the root cause is resolved and the DLQ messages are still valid.

## 10. Redriving and Event Recovery

Redriving is the process of moving messages from a DLQ back to the source queue or a recovery pipeline for reprocessing.

Safe redrives require:

- Selecting the right messages and event types.
- Verifying the root cause has been fixed.
- Checking that events remain within their valid business window.
- Ensuring idempotency and deduplication.
- Rate-limiting to avoid overloading systems.
- Starting with small batches and monitoring outcomes.
- Recording audit logs of who, when, and why.
- Stopping immediately if errors recur.

### 10.1. Batched Redrives

Do not push thousands of messages back into the main queue all at once if consumers and dependencies have not been validated.

Approach:

1. Test one representative message first.
2. Observe processing, outcomes, and duplicates.
3. Redrive a small batch.
4. Monitor source queue depth, DLQ depth, age, errors, and downstream load.
5. Increase batch size/rate gradually once stable.
6. Halt the redrive if messages return to the DLQ or SLOs degrade.

If the provider supports rate-limited redrive tasks, configure an appropriate limit. Otherwise, build a dedicated recovery consumer to read from the DLQ and publish back to the source queue in a controlled manner.

### 10.2. Avoid DLQ Loops

Avoid configuring queue A to send failures to DLQ B while B's consumer blindly pushes everything back to A. Redrives should be deliberate, bounded, and stoppable.

Attach replay metadata such as `replayRunId`, `replayedAt`, and `replaySource`. Preserve the original event ID so idempotency continues working. Never alter the event ID just to bypass deduplication.

### 10.3. Event Ordering

In FIFO queues or streams with ordering keys, redrives can alter relative ordering. If later events depend on earlier ones, do not randomly replay messages within the same group.

Requirements:

- Preserve partition keys or message groups.
- Identify sequence/version numbers.
- Recover in order or per aggregate.
- Stop replay if a critical predecessor is missing.
- Verify consumers can detect stale or late-arriving events.

Independent events can be parallelized more aggressively; ordered events prioritize correctness over speed.

## 11. Batch Processing and Partial Failures

Some event sources deliver multiple records in one invocation. If one record fails and the handler fails the entire batch, the whole batch may be retried. Records that already succeeded may execute again and create duplicates.

Two handling strategies:

- **Batch-level failure:** any failed record retries the whole batch. Simple, but may reprocess many records.
- **Partial batch response:** the handler returns the list of failed records so the platform retries only those needed, if supported by the event source and integration.

Conceptual response example:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "message-id-17" },
    { "itemIdentifier": "message-id-22" }
  ]
}
~~~

This illustrates one specific partial batch response shape, not a universal schema for all queues/streams. Verify whether your event source mapping supports it and what identifier format is expected.

For partitioned streams, one failing record can block checkpoints and subsequent records in the partition. Understand batch bisection, retry, and checkpoint semantics before enabling partial responses.

### 11.1. Batch Bisection

Some platforms support splitting failed batches into smaller halves to isolate the offending record. This is useful when a single poison record sits inside a large batch, though it increases invocation counts and does not replace idempotency.

Monitor batch size, retry counts, record age, and checkpoint lag. Pick a batch size balancing throughput, timeouts, and fault isolation.

## 12. DLQs Across Event Source Types

Each source type stores and confirms events differently.

| Event Source | Failure Mechanisms to Understand |
|---|---|
| Queue polling | Visibility timeout, receive count, ack/delete, and redrive policy |
| Async function invocation | Platform retries, maximum event age, maximum attempts, and failure destination/DLQ |
| Event bus | Delivery retries to targets, event age, retry policy, and target DLQ |
| Stream/partition | Offsets/checkpoints, shard/partition lag, batch retries, and poison records |
| Object event | Event notifications may duplicate or arrive late; object key/version requires idempotency |
| Database change stream | Checkpoints, resume tokens, log retention, and change ordering |
| Scheduler/timer | Missed invocations, retry windows, and idempotency by scheduled time |

### 12.1. Queue Polling

With queue polling, consumers typically receive messages under a visibility lease. Upon success, the consumer deletes/acks the message. Upon failure, the message becomes available again once the visibility timeout expires or when explicitly released via API.

Receive count increments across deliveries. Once it exceeds the maximum receive count, the service moves the message to the DLQ per the redrive policy. Exact count increment timing and timeout handling depend on the provider.

### 12.2. Async Function Invocation

With asynchronous invocations, the platform retains the event and retries automatically when the function errors or times out. Policies can bound attempt counts or maximum age. Once exhausted, events can be sent to a DLQ or failure destination.

A failure destination may include richer invocation metadata and response context than the original payload. Protect that data just like sensitive logs.

### 12.3. Event Bus

An event bus can retry delivering events to targets when targets are unreachable or return errors. Retry policies and DLQs are usually attached to target rules. One event may succeed for one target and fail for another; monitor failures per target rather than only aggregate event bus totals.

### 12.4. Streams and Partitions

With streams, consumers maintain checkpoints/offsets to resume reading. A single failing record can stall the checkpoint and increase lag. A DLQ can divert failed records to a separate path so the checkpoint advances, if supported by the integration.

When skipping a failing record to advance a checkpoint, ensure the record is durably persisted elsewhere with a replay process. Otherwise, data loss occurs.

## 13. Securing DLQs and Event Data

DLQs often hold failed payloads, stack/error metadata, and business details. This data can be more sensitive than standard logs because it contains original requests or unprocessed content.

Principles:

- Encrypt at rest and in transit.
- Restrict DLQ read permissions to the authorized operations group.
- Use IAM/workload identities and least privilege.
- Separate payload inspection permissions from redrive/purge permissions if supported.
- Never log full payloads or secrets during investigations.
- Mask personal data and tokens in dashboards/logs.
- Configure retention and lifecycle policies.
- Audit receives, purges, redrives, and policy changes.
- Verify encryption key permissions and send permissions from the source queue.
- Prevent producers from arbitrarily writing directly to the DLQ unnecessarily.

DLQs may contain stale data or malicious events. Before redriving, verify the origin and schema; never execute payloads as code or commands.

## 14. DLQ Monitoring and Alerting

A DLQ requires continuous monitoring. Knowing the queue exists is not enough.

Key metrics:

| Metric | Meaning |
|---|---|
| `dlq_visible_messages` | Number of messages waiting in the DLQ |
| `dlq_oldest_message_age_seconds` | Age of the oldest message |
| `dlq_incoming_rate` | Rate of messages entering the DLQ |
| `source_queue_depth` | Backlog in the source queue |
| `source_oldest_message_age` | Age of the oldest message at the source |
| `event_processing_success_rate` | Processing success rate |
| `event_retry_count` | Number of retries |
| `event_processing_duration` | Processing duration |
| `redrive_count` | Number of recovered messages |
| `redrive_success_rate` | Redrive success rate |
| `duplicate_detection_count` | Number of deduplicated events |
| `stream_consumer_lag` | Stream consumer lag |

Track by source, event type, consumer version, and tenant at reasonable cardinality. Never use raw payloads or message IDs as unbounded metric labels; keep fine-grained identifiers in logs/traces.

### 14.1. Alerting

Common alerts:

- New messages appear in the DLQ, especially for critical business flows.
- DLQ visible count increases continuously.
- Oldest message age approaches retention limit.
- Source queue backlog or age breaches SLO.
- Retry rate spikes anomalously.
- A new consumer version generates more errors than the previous version.
- Redriving causes the DLQ to grow again.
- Consumer lag fails to decrease despite added capacity.
- DLQ access permissions or encryption fail.

For flows where occasional failed messages are tolerable, alert on thresholds and event types. For payments, identity, or critical data, even a single message entering the DLQ may warrant immediate alerting.

### 14.2. Lifecycle Dashboards

Dashboards should visualize the end-to-end chain:

Producer rate → source queue depth/age → invocation rate → success/failure → retry → DLQ → redrive → successful completion.

Viewing the entire chain distinguishes producer traffic spikes, under-provisioned consumers, dependency outages, and poison messages. Looking only at the DLQ can miss a growing backlog in the source queue.

## 15. DLQ Recovery Runbook

A runbook should specify ownership, stop conditions, and completion verification.

### When DLQ Growth Is Detected

1. Confirm the queue/function/target name and blast radius.
2. Check source queue depth, oldest age, and consumer health.
3. Group errors by event type, schema version, and error code.
4. Determine if there is a widespread dependency outage.
5. If widespread, throttle concurrency or pause consumers per runbook to avoid overloading the dependency.
6. If bad data, quarantine the failing payload group and notify the producer owner.
7. If a code bug, roll back or deploy a tested fix.
8. Verify permissions, keys, and networking if misconfiguration is suspected.

### When Preparing a Redrive

1. Confirm the root cause is resolved.
2. Verify events are within business validity and schema-compatible.
3. Verify idempotency and duplicate protection.
4. Pick one representative event to replay.
5. Test in a safe environment if possible.
6. Start with a small batch, rate limit, and time window.
7. Monitor source queue, DLQ, downstream load, and SLOs.
8. Stop immediately if events continue failing or dependencies overload.
9. Record audit logs of count, scope, operator, and outcome.

### When Deciding Not to Redrive

Some messages should be closed by business decision rather than replayed:

- Expired events.
- Duplicate events already processed.
- Invalid payloads that cannot be repaired safely.
- Producer confirms the event is no longer valid.
- Events retained for security or forensic investigation.

Purging a DLQ is a potentially destructive operation. Perform it only with retention/audit policies, required backups, and proper approvals. Never purge merely to zero out dashboards without resolving the root cause.

## 16. Order Processing Flow Design Example

A service consumes `OrderCreated` from a queue and updates the fulfillment system.

Design:

- Producer emits events containing `eventId`, `orderId`, `schemaVersion`, and `occurredAt`.
- Main queue holds events for serverless workers.
- Worker validates schema and checks the idempotency key.
- Worker reads order state and writes fulfillment in a transaction.
- On dependency timeout, worker returns a retryable error.
- On schema error, worker classifies it as a permanent failure.
- After max receives, the queue routes messages to the DLQ.
- Dashboard alerts when the DLQ receives messages or oldest age crosses a threshold.
- After fixing the bug, an operator redrives a batch.
- Inbox/deduplication prevents duplicate fulfillment if the event was previously processed.

~~~mermaid
sequenceDiagram
    participant P as Order service
    participant Q as Orders queue
    participant W as Serverless worker
    participant DB as Fulfillment DB
    participant DLQ as Orders DLQ
    P->>Q: OrderCreated(eventId)
    Q->>W: Deliver event
    W->>DB: Validate and apply
    alt Processing succeeds
        DB-->>W: Commit
        W-->>Q: Acknowledge
    else Transient failure
        W-->>Q: Retry later
        Q->>W: Redeliver
    else Attempts exhausted
        Q->>DLQ: Move message
        DLQ-->>DLQ: Retain for investigation
    end
~~~

If an event already wrote fulfillment yet acknowledgment was lost, the queue may redeliver it. The idempotency key lets the worker detect completion and acknowledge safely.

## 17. Testing Retries and DLQs

Do not wait for a production incident to test your DLQ. Test key failure modes beforehand:

| Scenario | Expectation |
|---|---|
| Single dependency timeout | Retries and succeeds once dependency recovers |
| Prolonged dependency outage | Retries up to limit, then moves to DLQ |
| Schema-invalid payload | Does not retry endlessly; quarantined with metadata preserved |
| Duplicate event | Side effects happen only once via idempotency |
| Worker timeout after commit | Redelivery creates no duplicate outcomes |
| Batch with one failing record | Retries only failing record if integration supports partial response |
| Misconfigured DLQ permissions | Clear alert; messages are not silently lost |
| DLQ retention nearing expiry | Alert fires before messages expire |
| High-speed redrive | Rate limit protects dependencies and main queue |
| Stale event replay | Expiry/business validation prevents outdated side effects |

After testing, verify business data, queue depth, DLQ, logs, and audit records. Do not only check whether messages left the DLQ; prove the event completed accurately with zero duplicate side effects.

## 18. Common Operational Pitfalls

**Infinite retries:** poison messages consume compute and inflate backlogs. Bound attempts and event age.

**Unmonitored DLQs:** failed messages sit until retention expires. Alert on count and oldest age.

**No error classification:** schema errors get retried like timeouts. Separate transient from permanent failures.

**Returning success before commit:** events are acknowledged and work is lost. Acknowledge only after durable state persistence.

**No idempotency:** redeliveries or redrives produce duplicate side effects. Use stable event IDs and inbox/deduplication.

**Visibility timeout too short:** messages redeliver while original workers are still running. Set timeouts based on duration plus buffer.

**DLQ retention too short:** messages expire before operations can investigate. Set retention to cover response time and audit needs.

**Redriving everything simultaneously:** consumers and dependencies overload. Run small batches with rate limits and monitoring.

**Replaying without preserving order:** later events execute before earlier ones and corrupt aggregate state. Preserve partitions/message groups and sequences.

**Confusing DLQs with failure destinations:** missing metadata or misrouted failure records. Verify trigger semantics.

**Logging entire payloads:** exposes personal data or tokens. Mask and restrict access.

**Purging to silence alerts:** destroys evidence and loses work. Investigate, redrive, or close events properly.

**Ownerless DLQs:** nobody takes responsibility for failed messages. Assign owners, SLAs, and runbooks per pipeline.

## 19. DLQ Design and Operations Checklist

- [ ] Identified event sources and delivery semantics of each service.
- [ ] Classified transient, permanent, configuration, and code failures.
- [ ] Retries have appropriate maximum attempts, maximum age, backoff, and jitter.
- [ ] Timeouts, visibility timeouts, and batch processing durations are aligned.
- [ ] DLQ/failure destination is configured with proper write permissions.
- [ ] Retention covers investigation and recovery windows.
- [ ] Payloads and metadata include event ID, source, schema version, and correlation ID.
- [ ] Handlers are idempotent; deduplication state is durably persisted.
- [ ] Side effects and acknowledgments occur in a safe order.
- [ ] Poison messages are quarantined without blocking the entire stream.
- [ ] Partial batch failure is enabled where supported and needed by the event source.
- [ ] Replays validate event expiration, schema, and business state.
- [ ] Redrives enforce batch size, rate limits, auditing, and stop conditions.
- [ ] Ordering keys/partitions are preserved when replaying ordered events.
- [ ] DLQs are encrypted, access-controlled, and governed by retention policies.
- [ ] Dashboards track counts, oldest age, retries, success rates, and redrives.
- [ ] Alerts have assigned owners and response SLAs.
- [ ] Tested dependency failures, poison events, duplicates, and worker crashes.
- [ ] Runbooks exist for investigation, recovery, and decisions not to redrive.

A DLQ is a mechanism for quarantining events that failed after retry policies; its value lies in preserving evidence, detecting failures, and enabling controlled recovery. Classify errors before retrying, bound backoff and event age, build idempotent handlers, and redrive in batches once root causes are fixed. Combining monitoring, retention, access controls, and owned runbooks keeps serverless systems processing healthy events while failed messages are safely investigated and recovered.
