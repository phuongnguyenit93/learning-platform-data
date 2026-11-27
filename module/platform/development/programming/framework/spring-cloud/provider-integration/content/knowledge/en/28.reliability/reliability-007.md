# Dead-Lettering, Controlled Replay, and Incident Recovery

A message landing in a dead-letter queue (DLQ) usually signals that processing exceeded its retry policy or could not proceed along the normal path. A DLQ isolates failed messages for investigation and recovery, yet by itself it does not repair data, confirm whether side effects occurred, or guarantee safe replay.

In a Spring Boot system integrating Azure Service Bus, Event Hubs, AWS SQS, Kinesis, or Google Cloud Pub/Sub, design the full lifecycle of failed messages: classifying the root cause, preserving evidence, deciding between retry or dead-lettering, fixing the cause, verifying business state, replaying within limits, and validating post-recovery outcomes.

**Dead-lettering** isolates a message from the normal processing stream. **Redriving** moves messages from a DLQ back into the processing flow. **Replaying** re-emits an event/message to reprocess it or rebuild projections. **Recovery** restores both the system and business state after an incident. These operations are related but carry distinct goals and risks.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish transient errors, permanent errors, poison messages, and unknown outcomes.
2. Define retry exhaustion conditions and when to route messages to a DLQ.
3. Compare DLQs, retry queues, quarantine, archives, and event replays.
4. Preserve message identity, payload, headers, schema version, and failure metadata for investigation.
5. Design a triage workflow and verify side effects before redriving/replaying.
6. Perform controlled replays with batching, rate limits, ordering, and retry budgets.
7. Understand DLQ/redrive behavior in Azure Service Bus, AWS SQS, Google Cloud Pub/Sub, and limitations in Event Hubs/Kinesis.
8. Integrate dead-letter handling with Spring Cloud Stream binders and native SDKs.
9. Recover from incidents without creating duplicate side effects or regressing state.
10. Build metrics, audit trails, runbooks, and failure-injection tests for DLQs/replays.

## 2. What Problem Does a DLQ Solve?

A consumer can fail due to a temporarily unavailable service, invalid data, incompatible schemas, or software bugs. If the broker keeps redelivering the same failing message, it can tie up workers, cause a retry storm, or block messages behind it.

A DLQ separates messages needing investigation from the normal flow so other messages keep moving.

~~~mermaid
flowchart TD
    A[Broker delivers message] --> B[Spring Boot consumer]
    B --> C{Handler succeeded?}
    C -->|Yes| D[Commit business state]
    D --> E[ACK / Complete]
    C -->|Transient error| F[Bounded retry]
    F -->|Succeeded| D
    F -->|Retry budget exhausted| G[Dead-letter / DLQ]
    C -->|Permanent error| G
    G --> H[Triage and classify]
    H --> I{Root cause fixed and safety verified?}
    I -->|Yes| J[Controlled redrive / replay]
    I -->|No| K[Quarantine / pending investigation]
    J --> B
~~~

A DLQ provides three core values:

- **Isolation:** failing messages stop clogging normal processing.
- **Evidence preservation:** keeps the message and metadata for investigation.
- **Controlled recovery:** enables fixing the root cause and reprocessing under a controlled workflow.

A DLQ is not a long-term backup, not an immutable event store, and not proof that a message produced no side effects. The message may have updated a database or called an external API before failing.

## 3. Distinguishing Error Types Before Dead-Lettering

Do not send every exception straight to a DLQ, nor retry every exception until delivery limits run out.

| Error Type | Examples | Initial Action |
| --- | --- | --- |
| **Transient failure** | Network reset, service unavailable, throttling | Retry with backoff/jitter within budget |
| **Permanent technical failure** | Unparseable payload, unsupported schema | Dead-letter/quarantine |
| **Business rejection** | Order already canceled, disallowed state | Record business outcome; do not blindly retry |
| **Configuration/authorization** | Wrong endpoint, missing RBAC, invalid credentials | Fix config/permissions; retry after verification |
| **Unknown outcome** | Timeout after payment provider may have processed | Reconcile before retrying side effects |
| **Poison message** | Message repeatedly crashes handler or violates invariants | Isolate, investigate, and fix handler/data |
| **Prolonged dependency outage** | Dependent database or broker is down | Circuit breaker/queue buffering; avoid dumping entire backlog into DLQ too early |

### Poison Messages

A poison message repeatedly fails the consumer. The root cause may lie in the payload, schema, reference data, or a handler bug.

Examples:

- JSON missing a required field, causing deserialization to throw.
- A newer event version unsupported by the consumer.
- A message containing a negative amount on a command forbidding it.
- Handler assumes an order exists, yet the event arrived before OrderCreated.
- A specific value repeatedly triggers the same mapping or business rule failure.
- Handler hits a deterministic code bug so any number of retries will fail.

### Unknown Outcome Is Not a Permanent Failure

If a consumer calls an external API and times out, the side effect may already have occurred. Moving the message to a DLQ does not resolve the uncertainty. Before redriving, look up the operation reference/idempotency key or run reconciliation.

## 4. Retries, Retry Queues, DLQs, Quarantine, and Archives

These mechanisms do not replace one another:

| Mechanism | Goal | When to Use |
| --- | --- | --- |
| **Immediate retry** | Quickly re-attempt temporary blips | Short-lived errors with remaining budget |
| **Delayed retry queue/topic** | Wait longer before re-attempting | Dependency needs time to recover |
| **DLQ** | Isolate messages past policy or unprocessable | Poison/permanent/exhausted messages |
| **Quarantine** | Hold messages needing investigation or barred from auto-replay | Security issues, schema conflicts, unknown outcomes |
| **Archive** | Retain history for audit/rebuild | Long-term retention or analytics |
| **Replay stream** | Re-read history to rebuild consumers/projections | Intentional rebuilds or reprocessing |

Never use a DLQ as an infinite retry queue. Immediately redriving messages before fixing the root cause sends them right back to the DLQ, creating a costly loop and obscuring the incident.

### Pre-DLQ Retry Policy

A policy should define:

- Retryable exception categories.
- Maximum attempts and whether the initial attempt counts.
- Backoff, jitter, and Retry-After handling.
- Deadline/retry budget.
- Maximum time a message may stay in retry loops.
- Conditions for moving to the DLQ.
- Recorded error codes/reasons.
- Handling for unknown outcomes and authorization failures.

Broker delivery count does not always equal handler execution count. A delivery can fail before the handler starts; internal SDK retries can issue multiple requests during one delivery. Distinguish broker delivery count, handler attempts, and SDK request attempts.

## 5. When to Dead-Letter Immediately

Some failures should be isolated immediately because retries cannot self-heal them:

- Invalid or undeserializable payload.
- Unsupported schema version with no compatible upcaster.
- Missing required business identity.
- Same event ID with a different payload fingerprint.
- Security policy violation or unauthorized data.
- Violated business invariant requiring human or source-data verification.
- Expired command no longer valid in business terms.

Some failures require configuration fixes before redrive:

- 401/403 from wrong identity/role/scope.
- Unprovisioned resource.
- Wrong endpoint/namespace.
- Expired certificate or secret.

Avoid dumping messages into a DLQ during a brief dependency outage. For longer outages, pause consumers, trip a circuit breaker, or hold messages in queues/retry queues per broker capabilities. Choose DLQ thresholds around operational goals rather than arbitrary retry counts.

## 6. Message Metadata to Preserve When Dead-Lettering

For safe investigation and replay, preserve both the original data and processing context.

| Field | Purpose |
| --- | --- |
| message_id / event_id | Stable identifier of the message/event |
| correlation_id | Links workflow steps |
| causation_id | Event/command that triggered the current message |
| aggregate_id / aggregate_version | Identifies business entity and sequence |
| schema_version / content_type | Selects deserializer/upcaster |
| original_enqueued_at | When the message originally entered the stream, if provided by broker |
| dead_lettered_at | Timestamp when moved to DLQ |
| delivery_count | Broker delivery count per broker semantics |
| handler_attempt | Number of times the application actually ran the handler |
| failure_category | transient/permanent/unknown/business |
| failure_code | Stable error code for grouping/metrics |
| failure_stage | Deserialize, validation, DB, external API, ACK |
| consumer_name / subscription | Component processing the message |
| replay_count / replay_batch_id | Tracks replay runs |
| payload_hash | Detects message ID reuse with different payloads |

Never store access tokens, passwords, connection strings, or secrets in metadata. Do not copy sensitive payloads into logs solely for debugging. Keep payloads in an access-controlled broker DLQ and log only a fingerprint/reference.

### Failure Reasons Should Be Structured

Avoid stuffing long stack traces alone as the dead-letter reason. Store stable classification codes, for example:

~~~json
{
  "failureCategory": "SCHEMA_INCOMPATIBLE",
  "failureCode": "ORDER_EVENT_VERSION_UNSUPPORTED",
  "failureStage": "DESERIALIZATION",
  "consumer": "order-projection",
  "schemaVersion": 4,
  "firstFailedAt": "2026-11-24T10:15:00Z",
  "lastFailedAt": "2026-11-24T10:17:30Z"
}
~~~

Stack traces can live in log/trace backends with separate retention and masking. Broker reason/description fields often have length caps; never cram entire exceptions into them.

## 7. A DLQ Is Evidence About a Message, Not Business State

Before redriving, answer:

1. Was the message partially processed by a consumer?
2. Did the database transaction commit?
3. Might an external API have executed a side effect?
4. Is there an idempotency key/provider reference to query?
5. Was the message already processed by another consumer?
6. Did a newer event supersede this older message?
7. Can the same event ID be replayed without causing a second side effect?

A message in the DLQ may sit in one of several business states:

| Business State | Meaning | Decision |
| --- | --- | --- |
| No side effects | Handler failed before commit | Safe to redrive after fixing root cause |
| Fully committed, ACK failed | Business work done, broker still dead-lettered/redelivered | Do not repeat side effects; deduplicate and settle |
| Partially committed across systems | Workflow incomplete | Reconcile/compensate before continuing |
| Unknown outcome | Uncertain whether external side effect occurred | Query/reconcile; keep quarantined if needed |
| Stale event | Superseded by newer state | Ignore/audit or issue domain correction |

Never treat DLQ presence as the source of truth for payment/order status. The source of truth is persisted business state and reconcilable provider references.

## 8. DLQ Triage Workflow

A solid triage workflow classifies root causes before replaying:

~~~mermaid
flowchart TD
    A[DLQ alert] --> B[Snapshot metadata and messages]
    B --> C[Group by failure code/consumer]
    C --> D{Did side effects occur?}
    D -->|No| E[Classify root cause]
    D -->|Yes or unclear| F[Reconcile business/provider state]
    F --> G{Outcome resolved?}
    G -->|No| H[Quarantine / escalate]
    G -->|Yes| E
    E --> I{Root cause fixed?}
    I -->|No| H
    I -->|Yes| J[Dry-run replay and verify sample]
    J --> K[Throttled redrive]
    K --> L[Monitor outcomes and reconcile]
~~~

### Step 1 — Preserve Evidence

- Record queue/subscription, DLQ depth, and start time.
- Snapshot message ID, event ID, correlation ID, delivery count, and failure reason.
- Retain payloads under proper access controls and retention.
- Record consumer, binder, SDK, and schema versions.
- Do not mutate original payloads in place if audits require immutability.

### Step 2 — Group Failures

Group messages by failure code, schema version, consumer, dependency, and time window. A thousand messages sharing a 403 error usually represent one configuration incident, not a thousand independent business failures.

### Step 3 — Determine Side Effects

Query inbox/outbox tables, database state, provider operation references, Blob metadata, or ledgers. Classify messages as unprocessed, processed, partially processed, or unknown outcome.

### Step 4 — Fix the Root Cause

For example: deploy a consumer supporting the new schema, fix RBAC, provision resources, repair reference data, or fix a bug. Never redrive an entire DLQ before testing the fix.

### Step 5 — Dry-Run

Pick a representative sample, run validation/deserialization, and check business preconditions without creating side effects. If possible, test in staging or validate-only mode.

### Step 6 — Batched Redrive

Start with small batches, rate/concurrency limits, and active monitoring. Scale up gradually only while error rates, duplicate rates, and downstream load stay healthy.

### Step 7 — Post-Recovery Reconciliation

Verify succeeded counts, remaining DLQ counts, business effects, duplicates, event ordering, and backlogs. Close the incident only when both broker state and business state are consistent.

## 9. How Does Redrive Differ from Replay?

**Redrive** usually moves messages sitting in a DLQ back to the source queue/topic/subscription for normal consumer processing. **Replay** usually re-emits events from an archive/log or historical store to rebuild a consumer/projection or rerun a workflow.

| Criterion | Redrive | Replay |
| --- | --- | --- |
| Source | DLQ | Event archive, stream retention, event store, or backup |
| Goal | Resume processing failed messages | Reprocess history or rebuild projections |
| Identity | Preserve original message/event ID | Preserve original event ID; add replay metadata |
| Scope | Typically failed messages | Can span a time range/partition/aggregate |
| Risks | Repeated side effects, DLQ loops | Large-scale repeated side effects, out-of-order writes, load spikes |
| Controls | Batching, rate, retry budget, DLQ policy | Dedicated consumer, offset/version, dry-run, rate limit |
| Outcome | Messages re-enter processing flow | Projection/workflow rebuilt or updated |

Never alter the message ID to bypass deduplication when redriving the same event. Doing so tricks the consumer into treating an old message as a brand-new business intent.

If you need to execute a new business action based on old data, issue a **new command/event** with a new identity and explicit causation link. Do not disguise a new action as a replay of an old event.

## 10. Designing a Controlled Redrive

A redrive tool/job should support explicit parameters and guardrails:

- Source DLQ and target destination.
- Filters by failure code, timestamp, schema version, or message ID.
- Maximum messages per batch.
- Maximum publish/receive rate.
- Maximum concurrency.
- Delay between batches.
- Retry budget and maximum redrive count.
- Dry-run/validate-only mode.
- Preservation of original message ID/event ID and payload.
- Recording replay batch ID, operator/service identity, and audit entries.
- Emergency stop switch if error rates or downstream load spike.

### Do Not Redrive an Entire DLQ at Once

Suppose a DLQ holds 500,000 messages after an outage. Pushing them all back into the queue within seconds can slam the database, Blob, Service Bus, or payment provider. The outage can recur immediately upon recovery.

A structured plan:

1. Select 100 messages from one fixed failure category.
2. Run a dry-run and verify prior side effects.
3. Redrive the first 10–20 messages with low concurrency.
4. Observe success rate, latency, 429s, DB pool usage, and duplicates.
5. Increase batch size/rate incrementally if stable.
6. Pause immediately if errors spike or downstream backlogs cross thresholds.

Numbers are illustrative. Size rates and batches around actual capacity, SLOs, and dependency quotas.

### Replay Rate Must Account for Live Traffic

Total downstream load includes:

~~~text
total_rate = live_traffic + retry_traffic + redrive_rate + replay_rate
~~~

If downstream services are serving live traffic, replays must receive a bounded slice of capacity. Use separate worker pools, rate limiters, or dedicated queues so replays never starve live requests.

## 11. Idempotency During Redrives and Replays

Redrives cause messages to be delivered again. Consumers must rely on the same event identity for deduplication to work.

Principles:

- Preserve original event ID/message ID when re-emitting the same event.
- Preserve aggregate ID and aggregate version.
- Inbox/processed-message retention must span long enough.
- Enforce unique business constraints before creating side effects.
- External APIs must receive the same provider idempotency key when retrying the same operation.
- If the inbox record expired, query business state before replaying.
- If an event was already applied and a later workflow step failed, resume from the state machine rather than re-running everything.
- Projection replays must stay isolated from consumers that charge payments, send emails, or trigger unneeded external effects.

### Inbox Retention Must Cover the Replay Window

If the inbox retains records for only 7 days while the DLQ allows redrives after 30 days, old events may look brand new once inbox records vanish. Align:

- Broker retention.
- DLQ retention.
- Archive retention.
- Inbox/idempotency retention.
- Unique business references.
- Allowed operational replay window.

For ledgers/payments, unique business references must typically outlive technical deduplication caches.

## 12. Ordering and Old Events During Replay

A replay may feed event version 12 into a consumer that already applied version 20.

Before replaying:

1. Read current aggregate state/version.
2. Classify the event as duplicate, stale, missing gap, or correction.
3. If duplicate, settle without repeating side effects.
4. If stale, apply domain policy: ignore/audit or issue correction.
5. If a gap, locate the missing event or valid snapshot.
6. For projection rebuilds, use a fresh projection or controlled reset.
7. For external side effects, use separate idempotency/reconciliation.

Never sort an entire DLQ solely by timestamp and replay sequentially. Timestamps can skew or fail to reflect business sequence. Prefer authoritative aggregate versions/sequences and ordering scopes.

### Per-Aggregate Replay

If events for one order must run sequentially:

- Group by aggregate ID.
- Sort by authoritative aggregate version.
- Do not run events for the same aggregate concurrently unless handlers enforce version guards.
- Different aggregates can run concurrently.
- If a version is missing, pause that aggregate for reconciliation rather than skipping the gap.

## 13. Schema Evolution and Bad Data

A large DLQ can form if producers deploy a new schema before consumers upgrade.

Handling options:

- **Backward-compatible schema:** older consumers read newer payloads per compatibility rules.
- **Upcaster/adapter:** translates old or new events into the canonical model expected by handlers.
- **Versioned handlers:** dispatch by schema version.
- **Data repair:** fix reference records or payloads via an audited process.
- **Quarantine:** hold messages that cannot be safely interpreted.

Never edit payloads in a DLQ without keeping originals and an audit log. When transforming, record transform version, input hash, output hash, and rationale.

### Schema Dispatch Example in Java

~~~java
public interface EventUpcaster {
    boolean supports(int schemaVersion);
    CanonicalOrderEvent upcast(byte[] payload);
}

public final class OrderEventDecoder {

    private final List<EventUpcaster> upcasters;

    public OrderEventDecoder(List<EventUpcaster> upcasters) {
        this.upcasters = List.copyOf(upcasters);
    }

    public CanonicalOrderEvent decode(
            int schemaVersion,
            byte[] payload) {

        return upcasters.stream()
                .filter(candidate -> candidate.supports(schemaVersion))
                .findFirst()
                .orElseThrow(() ->
                        new UnsupportedSchemaException(schemaVersion))
                .upcast(payload);
    }
}
~~~

This is a structural example. Define a canonical schema, test against historical data, and ensure upcasters do not alter event semantics.

## 14. Incident Recovery Lifecycle

DLQ recovery is part of incident response. An incident can grow backlogs, halt consumers, throttle dependencies, or leave business data in uncertain states.

### Phase 1 — Contain

- Stop or scale down consumers if handlers are causing bad side effects.
- Open circuit breakers or lower concurrency when dependencies overload.
- Pause automated redrives/replays.
- Retain messages in the broker/queue or DLQ within retention limits.
- Protect data and audit trails.
- Avoid purging messages solely to shrink backlogs before diagnosing root causes.

### Phase 2 — Diagnose

- Pinpoint incident start/end times.
- Compare deployments/versions, schemas, identity, RBAC, and dependency health.
- Group failures by failure code, consumer, and partition.
- Determine whether side effects are committed, uncommitted, or unknown.
- Check retry amplification, lock expiry, visibility timeouts, and checkpoints.
- Identify any lost, duplicate, or out-of-order messages.

### Phase 3 — Correct

- Fix bugs/configs/permissions/schemas.
- Add migrations or upcasters if needed.
- Test against masked DLQ samples.
- Verify idempotency and transaction boundaries.
- Verify the new consumer handles old messages cleanly.

### Phase 4 — Recover

- Start consumers with low concurrency.
- Redrive by failure category/batch.
- Monitor downstream quotas, latency, DB pools, and duplicates.
- Halt if error rates or anomalous side effects rise.
- Ramp up speed only after capacity stabilizes.

### Phase 5 — Reconcile and Close

- Reconcile message counts across queues, DLQs, and archives.
- Reconcile committed business operations.
- Verify payments/ledgers/provider references and external side effects.
- Check event ordering and projection versions.
- Confirm no unresolved unknown outcomes remain.
- Document incident timeline, root cause, remediation, and follow-up actions.

~~~mermaid
stateDiagram-v2
    [*] --> Contain
    Contain --> Diagnose
    Diagnose --> Correct
    Correct --> Validate
    Validate --> Recover
    Recover --> Reconcile
    Recover --> Contain: Error rate / load spikes again
    Reconcile --> Closed
    Closed --> [*]
~~~

## 15. DLQ Runbook: Operational Checklist

A runbook should specify who is authorized to inspect, redrive, replay, or purge a DLQ. These actions can trigger side effects and require auditing.

### When DLQ Depth Spikes

1. Check alerts and when growth started.
2. Identify affected queues/subscriptions/consumers.
3. Check recent deployments, schema versions, and dependency health.
4. Group failure reasons.
5. Pause automated redrive until the root cause is known.
6. Determine whether any messages caused partial side effects.
7. Open an incident if SLOs or business invariants are impacted.
8. Record message counts, oldest message age, and growth rate.

### Before Redriving

1. Root cause is fixed and verified by tests.
2. Consumer version supports the message schemas.
3. Side effects have been queried/reconciled.
4. Idempotency/inbox retention is still valid.
5. Event ID, aggregate version, and correlation metadata are preserved.
6. Batch size/rate/concurrency caps are set.
7. Dry-run and sample checks completed.
8. Stop conditions and an owner are assigned.
9. Audit records will be captured.
10. Rollback/pause plan is ready if failures return.

### After Redriving

1. Monitor DLQ depth and queue backlog.
2. Track success/failure/duplicate rates.
3. Reconcile business state and provider references.
4. Check per-aggregate ordering/gaps.
5. Confirm retries are not looping endlessly.
6. Save batch outcomes and audit logs.
7. Close the incident once broker and business states align.

## 16. Azure Service Bus: Dead-Letter Subqueue

Azure Service Bus provides a dead-letter subqueue attached to each queue or subscription. Messages can be dead-lettered by the broker or the application.

### Common Causes

- Delivery count exceeds MaxDeliveryCount after repeated abandons/lock expirations.
- Message TTL expires when dead-letter-on-expiration is enabled.
- Filter/rule or forwarding failures in certain pipelines.
- Consumer explicitly calls dead-letter for payload/business errors.
- Application attaches dead-letter reason/description for diagnosis.

### Dead-Letter Reason and Description

When an application dead-letters a message, use a stable reason/code and concise description containing no secrets or sensitive payloads. Add application properties for failure category, consumer version, and correlation reference.

### Redriving from Service Bus DLQ

The DLQ is a separate subqueue; applications/tools must receive messages from the DLQ, verify them, and re-send to the target entity per workflow. When re-sending, preserve MessageId/event identity per business rules and attach replay metadata if needed.

Points to check:

- Duplicate detection windows can affect messages resent with the same MessageId.
- Preserve SessionId/partition/session semantics if ordering is needed.
- TTL, scheduled enqueue time, and application properties may need resetting for the redrive target.
- DLQs have their own retention/quotas and lifecycle; do not treat them as infinite archives.
- Messages may have already created side effects before dead-lettering; consumers still need inbox/idempotency.

Service Bus also has transfer dead-letter scenarios for forwarding/transfer failures; distinguish them from consumer/application dead-letters to pinpoint root causes.

## 17. AWS SQS: Redrive Policy and DLQ

SQS uses a **redrive policy** to move messages from a source queue to a dead-letter queue after receive counts exceed MaxReceiveCount.

### Key Concepts

- **Source queue:** original queue.
- **DLQ:** queue receiving messages past the threshold.
- **maxReceiveCount:** allowed receives per policy before moving to DLQ.
- **Redrive allow policy:** controls which source queues may target a DLQ.
- **Visibility timeout:** duration a message stays hidden after being received.
- **Redrive task:** service capability to move messages from a DLQ back to a source queue.

### Operational Notes

- SQS Standard has at-least-once delivery; duplicates can still happen.
- SQS FIFO has per-message-group ordering and its own deduplication window.
- MaxReceiveCount reflects broker receives, not completed business handler runs.
- Too short a visibility timeout can cause redelivery while a handler is still running.
- Configure DLQ retention long enough for investigation and recovery; retention semantics differ between Standard and FIFO.
- Rate-limit redrives to avoid spiking load on the source queue and downstream systems.
- Redrives do not guarantee prior side effects did not occur.

### FIFO and Ordering on Redrive

With FIFO, message groups and sequence/order can affect subsequent processing. Batch-redriving messages requires understanding the order in which the service re-inserts them into the source queue. Do not assume a bulk DLQ redrive automatically restores exact business order across every group.

Check message group IDs, deduplication IDs, and business aggregate versions before redriving.

## 18. Google Cloud Pub/Sub: Dead-Letter Topics

Pub/Sub supports dead-letter topics via a subscription's dead-letter policy when configured.

### How It Works

- A subscription can configure a dead-letter topic and maximum delivery attempts.
- Messages exceeding delivery attempts per service semantics may be forwarded to the dead-letter topic.
- Delivery attempt counts can be approximate and depend on ACK/nack/client behavior; do not treat them as an exact count of handler executions.
- Configure IAM/service agents so Pub/Sub has permission to publish to the dead-letter topic and the DLQ subscription has proper permissions.
- The dead-letter topic needs a subscription so messages are retained/readable for investigation within retention limits.

### Redrive/Replay

Do not view Pub/Sub as offering an automatic reverse-move from a dead-letter topic back to the original subscription in all cases. Typically a consumer/tool reads the dead-letter subscription and republishes to the target topic via a controlled replay.

Keep the original event ID in payload/attributes, add separate replay metadata, and ensure consumers are idempotent. Verify region, topic/subscription retention, IAM, and delivery-attempt behavior before operating.

## 19. Event Hubs and Kinesis: When Native Queue-Style DLQs Do Not Exist

Event Hubs and Kinesis are streaming services. They do not provide the same dead-letter subqueue semantics as Service Bus or SQS queues. Consumer applications typically must design their own failure store/quarantine.

### Azure Event Hubs

Unprocessable events can be stored in:

- Another Event Hub acting as a quarantine stream.
- Blob Storage/Data Lake as an archive.
- A database storing failure state and metadata.
- A separate managed queue/DLQ.

Record partition ID, offset/sequence number, event ID, schema version, and failure reason. Advance the checkpoint past an event only after it is processed or durably saved to the failure store per policy. Checkpointing before saving to quarantine risks skipping the event.

### Amazon Kinesis Data Streams

Kinesis consumers typically checkpoint per shard. When a handler fails:

- Retry the record within bounds.
- Write the failed record to SQS/S3/DynamoDB or a failure stream.
- Checkpoint past the record only once the business effect or failure record is durable.
- Manage shard ordering and contiguous completion.
- Use event ID/sequence to deduplicate when records are re-read.

Never checkpoint past a failing record before persisting evidence and following an explicit policy. One bad record can stall a shard; decide explicitly between bounded retry, durable quarantine, or audited skip.

### Failure Stores Must Be Durable

If a consumer merely logs a payload and checkpoints, log retention is inadequate for guaranteed replay. Persist payloads/references and metadata somewhere with proper retention, access control, encryption, and a replay workflow.

## 20. Spring Boot/Spring Cloud Stream: Dead-Letter Behavior Depends on the Binder

Spring Cloud Stream provides the function programming model, while DLQ, retry, and settlement are specific to the binder/provider.

Illustrative consumer:

~~~java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderEventHandler handler) {
    return message -> handler.handle(message.getPayload());
}
~~~

You cannot infer from this function alone that a message automatically routes to a DLQ when the handler throws an exception.

### What to Verify in the Binder

- Does the binder support DLQs/dead-letter topics?
- How are DLQ names and provisioning configured?
- Do retries happen in the binder, SDK, or application layer?
- Does max attempts include the initial attempt?
- Which exceptions are retried and which are ignored?
- When retries exhaust, does the binder dead-letter or reject/nack the message?
- Are original headers, partition keys, session IDs, and message IDs preserved?
- Is manual acknowledgment required?
- For batch consumers, does one failing record affect the whole batch or only that record?
- Are redrive/replay tools built into the binder or do they require the native SDK?

### Avoid Stacked Retry Layers

If the binder retries 3 times, the Azure/AWS/GCP SDK also retries internally, and the application service adds more retries, total requests can grow multiplicatively. A DLQ should receive a message only after the designated retry owner exhausts its assigned budget.

### Exception Classification

Do not let every exception be retryable. Define internal exception types:

~~~java
public class PermanentMessageException extends RuntimeException {
    public PermanentMessageException(String message) {
        super(message);
    }
}

public class RetryableDependencyException extends RuntimeException {
    public RetryableDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Binder configuration must map these exceptions as supported by your version. If the binder does not support the classification you need, handle it in the application layer and invoke native settlement APIs per contract.

## 21. Replay Tool/Job: Designing for Safe Operations

A replay tool should not be a bare loop reading a DLQ and re-sending everything. It needs selective filtering, dry-run, auditing, load throttling, and emergency stop controls.

### Components

| Component | Responsibility |
| --- | --- |
| **Selector** | Selects messages by ID, failure code, time range, tenant, or schema |
| **Validator** | Checks payloads, schemas, business preconditions, and prior side effects |
| **Planner** | Computes batch sizes, rates, and ordering |
| **Executor** | Redrives/replays in batches |
| **Rate controller** | Caps throughput/concurrency |
| **Audit writer** | Records who ran it, reason, batch, and outcomes |
| **Monitor** | Tracks errors, duplicates, backlogs, and downstream load |
| **Stop controller** | Halts when thresholds breach or the incident commander orders a stop |

### Dry-Run Mode

Dry-run can check:

- Whether the message deserializes.
- Whether the schema version is supported.
- Whether the event ID already exists in the inbox.
- Whether aggregate version is stale/gapped.
- Whether a provider operation reference already recorded a side effect.
- Whether the target queue/topic is correct.
- Whether required metadata is present.

Dry-run must never trigger side effects. If a validation step queries an external provider, use controlled read/lookup APIs only.

### Audit Record

A replay batch record might look like:

~~~json
{
  "replayBatchId": "replay-2026-11-24-001",
  "source": "orders-dlq",
  "target": "orders",
  "selector": {
    "failureCode": "ORDER_EVENT_VERSION_UNSUPPORTED",
    "schemaVersion": 3
  },
  "requestedBy": "recovery-service",
  "reason": "Consumer upgraded to support schema v3",
  "dryRun": false,
  "startedAt": "2026-11-24T11:00:00Z"
}
~~~

Never put sensitive payloads into audit records. Store message IDs/hashes and references to secured data stores.

## 22. Recovery with Partial Side Effects

A workflow may execute multiple steps:

~~~text
1. Write order to database
2. Upload document Blob
3. Publish DocumentCreated
4. Send notification
~~~

If step 3 fails, the message may enter the DLQ even though steps 1 and 2 succeeded. Redriving the whole workflow could duplicate the order/blob or send duplicate notifications.

### Using a State Machine to Resume from Incomplete Steps

Persist per-operation state:

| Step | State |
| --- | --- |
| Order persisted | SUCCEEDED |
| Blob uploaded | SUCCEEDED |
| Event published | PENDING |
| Notification sent | NOT_STARTED |

A recovery worker reads state and runs only the remaining steps. Each step still needs its own idempotency key or conditional write.

### Compensation

If the workflow cannot continue, compensation may be required:

- Delete orphaned Blobs if unreferenced and allowed by policy.
- Release reservations.
- Issue reversals/refunds instead of deleting ledger rows.
- Emit cancellation/correction events.
- Mark the operation FAILED_FINAL after reconciliation.

Compensation is a new audited business action, not an automatic rollback across external systems.

## 23. Keep Projection Replays and Side-Effect Replays Separate

Replaying full event history to build a read model differs completely from replaying commands that charge payments or send emails.

| Replay Type | Goal | Rules |
| --- | --- | --- |
| **Projection rebuild** | Rebuild read models/search indexes/caches | Use a dedicated projection version/consumer; allow controlled target resets |
| **Operational redrive** | Reprocess failed messages | Preserve identity, inbox, and business state; resume only incomplete steps |
| **External side-effect replay** | Retry payments/emails/APIs | Requires provider idempotency, reconciliation, or business approval |
| **Historical backfill** | Ingest historical data | Separate pipeline, rate limits, and duplicate checks |
| **Correction/reprocessing** | Fix incorrect data | Emit correction events/audits; never pretend it is a brand-new original event |

Never use the production email/payment-sending consumer to rebuild a projection. Create a projection-only consumer lacking permissions for external side effects.

## 24. Metrics and Alerts for DLQ/Recovery

| Metric | Meaning |
| --- | --- |
| dlq_message_count | Current messages sitting in the DLQ |
| dlq_oldest_message_age_seconds | Age of the oldest message in the DLQ |
| dlq_ingress_rate | Rate of messages entering the DLQ |
| dlq_failure_category_total | Distribution of dead-letter causes |
| redrive_attempts_total | Redrive attempts |
| redrive_success_total | Redriven messages accepted |
| redrive_failed_total | Failed redrives |
| replay_batch_rate | Replay throughput |
| replay_duplicate_total | Replayed messages caught by deduplication |
| business_effect_reconciled_total | Operations reconciled |
| unknown_outcome_backlog | Operations with unresolved outcomes |
| quarantine_count | Messages requiring manual handling |
| consumer_retry_exhausted_total | Operations exhausting retry budgets |
| downstream_throttle_total | Throttling errors during recovery |

### Alerts to Have

- Sudden spike in DLQ depth.
- Oldest message age exceeds handling SLA.
- One failure code dominates volume.
- Redrive is running while error rates rise.
- Duplicates/business conflicts rise during replay.
- Downstream 429/503s rise under recovery load.
- Unknown outcome backlog grows.
- DLQ nears retention/quota limits.
- Replay batch runs too long or makes no progress.

Never use message ID, aggregate ID, or tenant ID as high-cardinality metric labels. Use masked logs/traces and audit references.

## 25. Lab Exercise: Recovering an Order Consumer After an Incident

**Context:** A Spring Boot Order consumer reads messages from Azure Service Bus or AWS SQS. After deploying a new schema, 12,000 messages landed in the DLQ. Some messages may have updated the database before ACK/Complete failed. Some could not deserialize. A patched consumer now supports both old and new schemas.

### Part A — Investigate

1. Record DLQ depth, oldest age, queue backlog, and deployment timestamp.
2. Group messages by failure code, schema version, and consumer version.
3. Inspect a sample and check payloads/hashes.
4. Query inbox/business state to determine which messages committed.
5. Query provider references for external side effects.
6. Classify messages as unprocessed, processed, partial, or unknown outcome.

### Part B — Fix Root Cause

1. Deploy the schema-compatible consumer.
2. Verify RBAC/identity and dependency health.
3. Verify the handler has proper transactions/inbox handling.
4. Test duplicate delivery and crash-after-commit-before-ACK.
5. Verify message ID/event ID stays intact across redrives.
6. Run dry-run on a DLQ sample.

### Part C — Controlled Redrive

1. Select 100 messages from one fixed schema/failure category.
2. Redrive a small batch with a low rate limit.
3. Monitor success, duplicates, 429/503s, and downstream latency.
4. Reconcile committed business operations.
5. Increase batch size/rate per real capacity.
6. Halt immediately if errors/duplicates/unknown outcomes spike.
7. Keep ineligible messages in quarantine.

### Part D — Close the Incident

1. Reconcile queue, DLQ, archive, and business database.
2. Verify no lost events and no duplicate ledgers/orders.
3. Resolve unknown outcomes via reconciliation.
4. Check ordering by aggregate version.
5. Store replay audit logs and incident timeline.
6. Add alerts/runbooks and tests to prevent recurrence.

### Deliverables

- Error classification table and retry/dead-letter policy.
- Schemas for failure metadata and replay audits.
- Runbook covering triage, dry-run, redrive, and reconciliation.
- Broker-specific DLQ/redrive configuration.
- Test results for crash windows, duplicates, schema incompatibility, and replays.
- Metrics for DLQ depth, oldest age, redrive rate, duplicates, and unknown outcomes.

### Self-Check Questions

1. Why does a DLQ not prove a message produced no side effects?
2. How does a poison message differ from a transient failure?
3. When should you use a retry queue vs. dead-lettering?
4. Why do unknown outcomes need reconciliation before redriving?
5. How does redriving differ from replaying projections?
6. Why must you keep the original event ID when replaying the same event?
7. Why can replaying an entire DLQ at once trigger a second incident?
8. Why must inbox retention cover the DLQ/replay window?
9. How do Azure Service Bus DLQs, SQS DLQs, and Pub/Sub dead-letter topics differ?
10. Why do Event Hubs/Kinesis require an application-designed failure store?
11. Does MaxReceiveCount/delivery attempt equal the number of times the business handler ran?
12. Why must Spring Cloud Stream DLQ behavior be verified per binder?
13. How do you resume a workflow when database and Blob succeeded but publishing failed?
14. When does a projection rebuild need a dedicated consumer?
15. Which conditions must be met before closing a DLQ incident?

## 26. Takeaways

- A DLQ isolates failing messages for investigation and recovery; it does not fix business state, prove no side effects happened, and is not an infinite archive.
- Distinguish transient, permanent, business rejection, poison messages, and unknown outcomes before retrying/dead-lettering.
- Preserve message/event identity, payload, schema, aggregate version, delivery metadata, and structured failure reasons; never put secrets into DLQ metadata/logs.
- Before redriving, verify prior side effects, idempotency/inbox state, schema compatibility, ordering, and that the root cause is fixed.
- Redrives/replays need dry-runs, small batches, rate/concurrency limits, audits, stop conditions, and post-processing reconciliation.
- Keep the original event ID when replaying the same event; use a new identity for a new business command/event.
- Service Bus, SQS, and Pub/Sub have distinct DLQ/redrive semantics; Event Hubs/Kinesis require application-designed failure stores/quarantines.
- Spring Cloud Stream DLQ, retry, and ACK behavior depends on binder/version; avoid stacked retries without an overall budget.
- Partial side effects require state machines, provider idempotency, reconciliation, or compensation; never blindly rerun the entire workflow.
- Close an incident only after reconciling broker backlogs, DLQs, business state, external providers, and unknown outcomes.

## References

- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Event Hubs features and consumer groups](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS redrive to source queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [AWS Prescriptive Guidance — Retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
