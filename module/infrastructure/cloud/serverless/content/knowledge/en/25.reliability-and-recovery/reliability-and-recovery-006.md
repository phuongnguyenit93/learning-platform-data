# Quarantining, Redriving, and Replaying Events After Incidents

In the **Reliability and Recovery** chapter, quarantining, redriving, and replaying are techniques for preserving failed work, investigating root causes, and reprocessing in a controlled manner. In a serverless system, an event may traverse an API, queue, event bus, stream, and multiple functions. When a consumer fails, you must preserve the original data, pinpoint where the failure happened, avoid infinite retries, and recover without producing duplicate side effects.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications under the serverless model, especially Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to decide when to use FaaS. Quarantining, redriving, and replaying enable systems to recover from incidents while maintaining control over load, ordering, state, and data consistency.

## 1. What are quarantine, redrive, and replay?

These three concepts are related yet represent distinct stages:

- **Quarantine:** Isolating an event or message that cannot be safely processed so it stops breaking the primary pipeline. The data is retained alongside metadata for investigation.
- **Redrive:** Moving messages that landed in a dead-letter queue (DLQ) back to a queue or processing pipeline for another attempt.
- **Replay:** Re-emitting events from an archive or event log over a selected time window or scope.

For example, a Lambda consumer receives a message containing a new schema version that current code does not yet understand. The message repeatedly fails. After the configured retry attempts, it moves to the DLQ. The operations team investigates, deploys a fixed consumer version, and redrives a subset of messages from the DLQ at a throttled rate.

Another case: EventBridge archived events in an archive. A consumer was broken for 30 minutes while the event bus kept receiving events. After fixing the consumer, the operations team replays the affected time window from the archive so the consumer receives those events again.

Quarantine isolates and preserves faulty data; redrive/replay reintroduces data into processing. Not every failed event needs replay, and not every event source offers the same replay mechanism.

## 2. Why are recovery mechanisms needed?

A distributed system can encounter many failure modes:

- Invalid payloads or missing required fields.
- Consumer not yet supporting a new schema version.
- Transient dependency timeouts or throttling.
- Expired credentials or altered IAM policies.
- Overloaded database or exhausted connections.
- Function hitting timeout or running out of memory.
- A bug triggered only by a specific subset of data.
- Events delivered multiple times or out of order.
- A new deployment causing the consumer to fail on previously valid events.

With retries alone, a poison or malformed message can be redelivered repeatedly without ever succeeding. Deleting failed messages risks losing business data. Replaying all events unboundedly can trigger a massive load spike and duplicate side effects.

A sound recovery process must answer:

1. Which events failed?
2. Was the failure caused by a transient issue or bad data?
3. Was the original payload preserved intact?
4. How many attempts occurred and why did retries stop?
5. Can code or configuration be fixed to reprocess them?
6. Which data or services will be impacted by replay?
7. How do we rate-limit replay and prevent duplicates?
8. How do we verify every recoverable event was processed?

## 3. Distinguishing retry, DLQ, quarantine, and archive

| Mechanism | Purpose | Data lifecycle |
|---|---|---|
| Retry | Reattempt potentially transient errors | Governed by source retry policy |
| DLQ | Hold unprocessable messages after retry threshold | Governed by queue retention |
| Quarantine store | Isolate events needing investigation or manual handling | Governed by custom system retention and policies |
| Event archive | Store events for lookup or replay over a time window | Governed by archive retention |
| Event log/stream | Retain event history within platform retention | Replayable by offset/time while data remains |

A DLQ is not automatically a long-term archive. Messages can expire once retention elapses. Likewise, an archive does not necessarily store everything needed to rebuild business state; it only retains events matching its capture configuration.

A quarantine store can be a dedicated queue, object storage, or a stateful database. The choice depends on searchability, payload size, retention, access controls, and redrive mechanics.

## 4. Poison messages and recoverable errors

A poison message is one that consistently causes a consumer to fail. Common causes:

- Malformed schema or unparseable payload.
- A value that repeatedly throws an exception in code.
- An event referencing a deleted resource.
- A business invariant that no longer holds.
- A dependency consistently rejecting operations on that data.
- An oversized message exceeding processing limits.
- A consumer bug triggered only in a rare edge case.

Distinguish clearly:

| Error type | Examples | Action |
|---|---|---|
| Transient | HTTP 503, throttling, network timeout | Retry with backoff |
| Permanent data error | Corrupted JSON, missing event type | Quarantine/DLQ and investigate |
| Compatibility error | Consumer does not understand schema version | Upgrade consumer or transform event |
| Authorization/configuration | AccessDenied, wrong role | Fix policy/config; do not retry indefinitely |
| Business rejection | Order already canceled, invalid state | Record business outcome; typically do not retry |
| Unknown | Unclassified error | Bounded retry, then route to DLQ |

Never treat every exception as transient. When the error is `AccessDenied` or an invalid payload, continuous retries only generate extra invocations, logs, and load on dependencies.

## 5. Retry policies before routing to a DLQ

A retry policy should define:

- Maximum attempt count.
- Total time an event may live before expiring.
- Delay intervals between attempts.
- Backoff and jitter.
- Which errors qualify for retry.
- Which errors must go straight to quarantine.
- Where messages go once retries are exhausted.
- How DLQs are alerted on and triaged.

Exponential backoff slows down retries while a dependency recovers:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Jitter prevents multiple workers from retrying simultaneously. Set a max delay and retry budget so a single event cannot consume resources indefinitely.

Multi-layer retries can multiply call volume. For example, 3 SDK retries, 3 in-handler retries, and 5 event-source retries can produce far more calls than intended. Clearly assign retry ownership to a specific layer and cap total attempts.

## 6. Quarantine and recovery architecture

A foundational architecture:

~~~mermaid
flowchart TD
    SRC["HTTP / Queue / Event / Stream"] --> CON["Java consumer"]
    CON --> DEC{"Process result"}
    DEC -->|"Success"| ACK["Acknowledge / checkpoint"]
    DEC -->|"Transient failure"| RET["Retry with backoff"]
    RET --> CON
    DEC -->|"Permanent or max attempts"| Q["DLQ / quarantine"]
    Q --> TRIAGE["Inspect and classify"]
    TRIAGE --> FIX["Fix code, data or configuration"]
    FIX --> CONTROL["Approve replay scope and rate"]
    CONTROL --> REPLAY["Redrive / replay"]
    REPLAY --> CON
~~~

Key components:

- Consumer processes events and classifies errors.
- Retry policy keeps transient failures bounded.
- DLQ/quarantine retains events requiring investigation.
- Metadata supports tracing origin, attempt count, and last error.
- Runbook guides root-cause remediation and replay scoping.
- Replay controller throttles rate and volume of replayed events.
- Idempotency protects side effects when events are redelivered.

Never let a replay controller bypass the consumer and write straight into the business database if the goal is to re-run the same business logic. Replaying through the tested processing path keeps validation, authorization, and observability consistent.

## 7. Designing quarantine records

Quarantine records must preserve enough detail for reprocessing without creating new data-leakage vectors.

A reference structure:

~~~json
{
  "quarantineId": "q-01J9EXAMPLE",
  "source": {
    "service": "orders-queue",
    "messageId": "msg-123",
    "eventSourceArn": "arn:aws:sqs:region:account:orders"
  },
  "event": {
    "eventId": "evt-456",
    "eventType": "OrderPlaced",
    "schemaVersion": 2,
    "occurredAt": "2026-11-17T10:00:00Z"
  },
  "failure": {
    "category": "SCHEMA_INCOMPATIBLE",
    "errorCode": "UNSUPPORTED_VERSION",
    "attempts": 5,
    "failedAt": "2026-11-17T10:02:00Z"
  },
  "recovery": {
    "status": "QUARANTINED",
    "replayCount": 0
  }
}
~~~

This is an illustrative example. Depending on the source, message ID, event source ARN, receive count, or timestamps may not be available. Never fabricate placeholder values to fill fields; record real fields and explicitly represent missing values.

Recommended fields to store:

- Original payload or an immutable reference to it.
- Event ID and message ID if supplied by the source.
- Origin source, queue, stream, partition, or event bus.
- Event type and schema version.
- Occurrence timestamp and receipt timestamp.
- Delivery/attempt count if available.
- Sanitized error category and error code.
- Correlation ID/trace ID.
- Quarantine status and replay history.
- Person or system approving recovery actions.

You do not need to copy full payloads into logs. Large payloads or those containing PII should be encrypted in object storage with access controls; the quarantine record only stores a reference, checksum, and necessary metadata.

## 8. Managing the quarantine lifecycle

A state machine prevents ad-hoc replays:

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED
    QUARANTINED --> TRIAGING
    TRIAGING --> READY
    TRIAGING --> DISCARDED
    READY --> REPLAYING
    REPLAYING --> COMPLETED
    REPLAYING --> QUARANTINED: Failed again
    COMPLETED --> [*]
    DISCARDED --> [*]
~~~

State meanings:

- **QUARANTINED:** Event has been isolated.
- **TRIAGING:** Root cause and impact are under investigation.
- **READY:** Root cause resolved; event is eligible for replay.
- **REPLAYING:** Event is currently being replayed.
- **COMPLETED:** Replay succeeded and outcome verified.
- **DISCARDED:** Decided not to reprocess the event, with documented reason and audit record.

Never jump straight from QUARANTINED to replay merely because messages exist in a queue. Confirm the root cause has been fixed first; otherwise events bounce straight back into the DLQ and add unnecessary load.

## 9. AWS SQS DLQ and redrive

In SQS, a redrive policy on the source queue specifies how many times a message can be received before moving to the DLQ. The receive count attribute increments each time a message is delivered to a consumer; once it exceeds the configured threshold, SQS moves the message to the DLQ.

Key points to remember:

- The DLQ must match the source queue type: Standard with Standard, FIFO with FIFO.
- The DLQ has its own retention period; messages should not sit indefinitely without an appropriate policy.
- For Standard queues, the original enqueue timestamp is preserved when a message moves to the DLQ; therefore, DLQ retention must exceed source queue retention to allow sufficient investigation time. FIFO queues have different timestamp semantics, so check documentation for your queue type.
- Source queue and DLQ must reside in the same Region with appropriate permissions configured.
- Verify the redrive allow policy to control which queues are permitted to use the DLQ.
- Redriving does not fix payload or consumer bugs.
- Redriven messages can still be delivered more than once; consumers must remain idempotent.

### 9.1. Configuring a redrive policy

Abbreviated CloudFormation example:

~~~yaml
Resources:
  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      MessageRetentionPeriod: 1209600

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
        maxReceiveCount: 5
~~~

The retention, visibility timeout, and `maxReceiveCount` values are examples only. Choose them based on processing duration, retry policy, source retention, and expected operational window. Too short a visibility timeout risks concurrent redelivery while an existing worker is still running; too long delays recovery.

For SQS FIFO, moving a message to a DLQ can alter processing sequence within a `MessageGroupId`. If strict ordering is a business requirement, assess DLQ impact and per-message-group recovery procedures.

### 9.2. Controlled redrive with the AWS CLI

The AWS CLI can initiate a message move task from a DLQ:

~~~bash
aws sqs start-message-move-task \
  --source-arn arn:aws:sqs:ap-southeast-1:123456789012:orders-dlq \
  --destination-arn arn:aws:sqs:ap-southeast-1:123456789012:orders-replay \
  --max-number-of-messages-per-second 25
~~~

This is an illustrative command with fictional ARNs and rate. When running it, confirm the destination queue matches the type and Region and has a controlled consumer. You can omit the destination to redrive back to the original source queue per API capabilities, though a dedicated replay queue often helps isolate recovery load from live traffic.

A rate of 25 messages/second is not a universal recommendation. Select the rate based on downstream quotas, worker concurrency, queue age, and current production traffic.

Monitor move task status via the corresponding API/CLI and cancel the task if the system shows signs of overload. Never run overlapping redrive tasks without understanding their effect on ordering and aggregate emission rate.

## 10. Distinguishing SQS DLQ from Lambda asynchronous failure destinations

These two mechanisms are frequently confused.

### 10.1. Lambda asynchronous invocation

When Lambda is invoked asynchronously, the Lambda service manages an internal queue and retries according to the async invocation configuration. You can configure:

- Maximum retry attempts.
- Maximum event age.
- A dead-letter queue for failed events.
- An on-failure destination to send invocation records to SQS, SNS, Lambda, or EventBridge as supported by Lambda.

Destinations can include invocation metadata, request payloads, and response context helpful for debugging. Traditional DLQs primarily capture the original event. Choose based on observability and post-incident handling needs.

### 10.2. Lambda event source mapping

For SQS, Kinesis, or DynamoDB Streams, Lambda polls the event source via an event source mapping. Retries and checkpoints depend on the source type.

- For SQS, messages stay in the queue and can move to a DLQ per the queue's redrive policy.
- For Kinesis/DynamoDB Streams, batch failures can affect checkpoints and record re-reads; configure retry limits, record age, and on-failure destinations accordingly.
- For Kafka, consumer offsets and topic retention govern replayability.

Never configure a Lambda asynchronous DLQ expecting it to capture messages from an SQS event source mapping. Configure retries and failure targets where the trigger manages them.

## 11. EventBridge archive and replay

An EventBridge archive captures events from an event bus according to configured filters and retention. When a consumer or rule fails, archived events from a chosen time window can be replayed back onto the target event bus.

General workflow:

1. Create the archive and configure an appropriate event pattern before an incident occurs.
2. Set retention long enough to cover operational needs.
3. When an error is detected, identify the affected time window and event types.
4. Fix the consumer, rule, or permissions.
5. Verify the replay filter and destination.
6. Start the replay within the approved scope.
7. Monitor consumers, duplicates, and downstream load.
8. Reconcile replayed event counts against successfully processed events.

An archive only stores events matching its filter within its retention window. If archiving was not enabled beforehand or events did not match the pattern, the archive cannot recover those events.

Replaying sends events back to the event bus, where active rules and targets process them under current configuration. That means a replay can trigger multiple consumers, not just the one you fixed. Use specific event patterns, target buses, or rule routing to avoid unintended side effects.

EventBridge replay does not automatically guarantee exactly-once consumer processing. Events processed prior to the incident can be redelivered. Consumers require idempotency and side-effect protection.

## 12. Replaying from Kinesis and DynamoDB Streams

Streams store events by shard/partition and allow consumers to re-read within the retention window.

With Kinesis Data Streams, consumers can start reading from supported positions such as `TRIM_HORIZON`, `LATEST`, or a timestamp. Once records age past retention, the stream no longer holds them for replay. Kinesis retention can be configured within service limits.

DynamoDB Streams have a fixed 24-hour retention; therefore, never treat the stream as a long-term store. If long-term replay is needed, persist events to an archive or dedicated event store.

When using Lambda event source mapping:

- Starting position only sets the initial read point for a new or recreated mapping per supported behavior.
- Batch retries and checkpoints can cause certain records to be re-read.
- Bisect batch on function error splits failing batches to isolate poison records where supported.
- Partial batch responses can report specific failed records when supported by the source.
- On-failure destinations can store failed batch metadata per source configuration and capabilities.

Stream replays must preserve partition keys and sequence context when business rules require ordering. If launching a new consumer or mapping, prevent two consumers from concurrently executing side effects on the same records without coordination.

## 13. Replaying from Kafka and other sources

With Kafka, replayability depends on topic retention and consumer group offsets. You can spin up a new consumer group to read from the beginning within retention, or reset offsets on an existing group under a controlled procedure. Shifting offsets on an active production consumer risks replaying huge volumes or skipping unprocessed events.

For S3 notifications, do not assume a built-in archive/replay mechanism like EventBridge. For recovery, rely on object inventory, object metadata, a separate event log, or batch reprocessing workflows. Design ahead of time how to distinguish already-processed objects from missing ones.

For HTTP webhooks, if the provider retains no history or lacks redelivery, consumers must durably persist incoming event envelopes immediately upon receipt. If the provider has a finite retry window, know that window and do not depend on the webhook provider as storage.

## 14. Preserving original events and metadata

When quarantining, keep the original payload immutable so it can be verified and compared later. If schema transformation is needed, store the transformed output as a new artifact instead of overwriting the original payload.

An event envelope might include:

~~~java
import java.time.Instant;
import java.util.Map;

public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String aggregateId,
        long sequence,
        String correlationId,
        Map<String, String> metadata,
        T payload) {

    public EventEnvelope {
        metadata = Map.copyOf(metadata);
    }
}
~~~

This envelope is an internal example. Not every source supplies an aggregate ID or sequence; those fields must come from the producer's contract. `eventId` must remain stable across retries and replays of the same event.

Never overwrite `occurredAt` with a new timestamp during replay. To record when replay happened, attach `replayedAt` or `replayRunId` in operational metadata so the original business timestamp stays intact.

## 15. Idempotency during redrive and replay

Replays can resend events that a consumer already processed successfully before failing to ACK due to a timeout or connection drop. If a handler generates invoices, deducts inventory, or charges cards, duplicate processing causes severe harm.

Use a stable idempotency key, typically derived from `eventId` and operation/version. Example:

~~~java
public record ProcessingKey(
        String eventId,
        String operationName,
        int operationVersion) {

    public String value() {
        return eventId + ":" + operationName + ":" + operationVersion;
    }
}
~~~

Processing steps:

1. Check the idempotency record.
2. If already `COMPLETED`, return the stored result without repeating side effects.
3. If absent, claim processing via a conditional write or lease.
4. Execute side effects via transaction/outbox or an idempotent API.
5. Durably persist completion status.
6. ACK/checkpoint only after state has been persisted.

Checking the key and applying side effects in two separate non-atomic steps creates a race condition: two workers can both see the key absent and execute the side effect. Use atomic claims, transactions, or deduplication at the system of record.

If intentionally replaying to run a new calculation or rebuild a projection, increment `operationVersion`. Never alter the original event's `eventId` just to bypass idempotency; clearly distinguish which operations may re-run and which side effects must remain protected.

## 16. Event ordering during recovery

Not all events are independent. For instance, `OrderCreated`, `PaymentAuthorized`, and `OrderCancelled` may require processing in business order.

Replaying events strictly by replay arrival time can alter the original order. Many distributed systems also do not guarantee global ordering across partitions or message groups.

Ensure you:

- Identify the aggregate ID or partition key.
- Record producer sequence/version numbers when business ordering is required.
- Validate sequence before applying events.
- Replay per aggregate/partition whenever possible.
- Avoid mixing live traffic and replay traffic if consumers cannot handle out-of-order late events.
- Define policies for stale events and out-of-order arrivals.
- For FIFO queues, preserve `MessageGroupId` and understand the ordering impact when messages move to a DLQ.

If event version 12 has already been applied, replaying event version 10 must not overwrite newer state. Consumers can ignore older events, rebuild projections from snapshots, or run domain-specific reconciliation.

## 17. Schema evolution and transformation before replay

An event failure may stem from an unsupported schema version in the consumer. Before replaying, decide whether to:

- Upgrade the consumer to handle both old and new schemas.
- Transform older events into the current internal schema.
- Run a compatibility adapter/upcaster.
- Keep the original event and route it to a matching consumer version.
- Discard the event if the producer violated the contract and safe recovery is impossible.

Never manually edit raw payloads inside a DLQ and redrive without an audit trail. If transformation is needed, emit a new replay artifact linked to the original event, recording transformer version, checksum, and validation results.

Durable consumers should maintain backward compatibility across the full replay retention horizon. If events can be replayed months later, contracts and schema registries must retain enough metadata to interpret older payloads.

## 18. Throttling replay rates

Replaying a million events at once can cause a call storm similar to an unbounded fan-out. Before replaying, estimate:

- Number of events to replay.
- Safe consumer throughput.
- Downstream quotas.
- Capacity currently consumed by live traffic.
- Desired completion time.
- Invocation, queue, storage, and downstream costs.
- Ability to pause or roll back the replay.

Control measures:

- Replay in small batches or narrow time windows.
- Use a dedicated replay queue isolated from live traffic.
- Cap SQS redrive rates where supported by the API.
- Cap event source mapping concurrency.
- Use a shared rate limiter aligned with downstream quotas.
- Start with a small canary batch, verify results, then scale up.
- Pause immediately if error rates, queue age, 429s, or p99 latency breach guardrails.
- Enforce replay budgets per tenant or event type.

Not every replay service includes built-in rate controls. For EventBridge archive replays, control load at the target consumer, queue, or downstream rate limiter; do not assume the replay API can throttle RPS to an arbitrary limit.

### 18.1. Separating replays from live traffic

A dedicated replay queue helps:

- Allocate separate concurrency for recovery.
- Protect live traffic from being starved by replay backlogs.
- Track recovery throughput independently.
- Pause replay without halting live consumers.
- Tune rates according to business priority.

Even with separate queues, share the same validation and business rules in consumer code while adjusting concurrency and priority. Never bypass security checks just because an event arrived from a replay queue.

## 19. Post-incident recovery runbook

A runbook should consist of actionable, verifiable steps:

1. **Detect:** Alerts triggered by DLQ depth, event age, failure rate, or consumer lag.
2. **Scope:** Identify source, event type, schema version, time range, and affected tenants.
3. **Stop amplification:** Lower concurrency, pause consumers, or halt producers if needed.
4. **Preserve data:** Confirm DLQ/archive/quarantine retains events and metadata.
5. **Classify:** Distinguish transient, permanent, schema, authorization, and business errors.
6. **Remediate root cause:** Fix code, policies, dependencies, data, or configuration.
7. **Verify:** Test against a representative sample of events and inspect side effects.
8. **Plan replay:** Define event IDs/time window, rate, concurrency, owner, and rollback plan.
9. **Canary replay:** Replay a small batch and verify results.
10. **Scale up:** Ramp gradually within guardrails while watching queue age and downstream health.
11. **Reconcile:** Compare eligible events, succeeded, duplicates, remaining errors, and discarded records.
12. **Close incident:** Record audit trail, root cause, discard decisions, and operational takeaways.

Never perform bulk redrives before confirming the consumer fix is live. If the root cause persists, the DLQ will simply refill rapidly.

## 20. Java consumer: classifying errors and recording quarantine state

An error classifier helps handlers decide between retrying and quarantining:

~~~java
public enum FailureCategory {
    TRANSIENT,
    INVALID_PAYLOAD,
    UNSUPPORTED_SCHEMA,
    AUTHORIZATION,
    BUSINESS_REJECTION,
    UNKNOWN
}

public record ProcessingFailure(
        FailureCategory category,
        String errorCode,
        String safeMessage) {
}

public final class FailureClassifier {
    private FailureClassifier() {
    }

    public static boolean shouldRetry(
            ProcessingFailure failure,
            int attemptsSoFar,
            int maxAttempts) {

        if (attemptsSoFar >= maxAttempts) {
            return false;
        }

        return failure.category() == FailureCategory.TRANSIENT
                || failure.category() == FailureCategory.UNKNOWN;
    }
}
~~~

This example illustrates only the basic decision logic. Production code must classify exceptions by dependency type, status code, error code, and business semantics. `UNKNOWN` failures may retry a bounded number of times and then go to quarantine—never retry infinitely.

When writing quarantine records, store only sanitized error codes and safe messages. Never store stack traces or raw payloads containing tokens, passwords, or personal data in broadly accessible stores.

With SQS partial batch responses, the handler reports failed message IDs so only those messages are redelivered. With streams, use the exact response format expected by the event source mapping and enable the feature in configuration. Never assume the same response contract applies across all triggers.

## 21. Security and access control for quarantine data

DLQs and archives often contain original payloads, making them more sensitive than standard logs. Protect them like production data:

- Encrypt at rest and in transit.
- Restrict IAM policies so only authorized operators can read/quarantine/redrive.
- Separate permission to view payloads from permission to trigger replays.
- Audit who viewed, exported, edited metadata, or triggered redrives.
- Never make buckets or queues public.
- Exclude raw payloads from logs and alerts.
- Set appropriate retention and lifecycle rules.
- Control exporting data to local environments.
- Scope KMS key policies and secret references tightly.

Anyone authorized to redrive can re-trigger thousands of side effects. Replay permissions are therefore high-impact operational privileges. Production replays may require peer approval, change tickets, or role-based restrictions.

## 22. Observing and reconciling recovery

Maintain dedicated metrics for the recovery path:

- DLQ message count and oldest message age.
- Quarantine count by failure category.
- Counts of events in `READY`, `REPLAYING`, `COMPLETED`, and `FAILED` states.
- Replay throughput and remaining backlog.
- Retry counts and redrive counts.
- Duplicate/idempotency hit rate.
- Event age from `occurredAt` to `processedAt`.
- Downstream 429/5xx responses, latency, and connection counts.
- Discarded event counts and reasons.
- Cost per successfully recovered event.

Use `replayRunId` or `recoveryBatchId` to correlate logs and traces across a recovery run. Do not use unique per-event IDs as high-cardinality metric dimensions; keep IDs inside logs or traces.

Reconciliation must distinguish:

- Events selected for replay.
- Events actually emitted for replay.
- Events received by consumers.
- Events processed successfully.
- Events skipped as duplicates.
- Events still failing or returned to quarantine.

Never treat a completed replay task as proof that all business side effects succeeded. Verify final state in target systems or business projections.

## 23. Common mistakes

**Infinitely retrying poison messages:** A bad payload causes workers to fail forever. Enforce max attempts and a DLQ.

**Treating a DLQ as a long-term archive:** Messages can age out past retention. Use an archive or event store for long-term history.

**Redriving immediately upon seeing DLQ items:** The underlying bug is unfixed, so messages bounce right back. Triage and test first.

**Replaying the entire archive:** Generates huge load and triggers unrelated consumers. Specify exact time ranges, event patterns, and destinations.

**Confusing Lambda async DLQs with SQS DLQs:** Misconfigures where retries are managed. Identify your trigger and its semantics first.

**Lacking idempotency:** Replays generate duplicate invoices, inventory deductions, or emails. Enforce idempotency keys and atomic claims.

**Failing to preserve original events:** Impossible to verify payloads or audit transformations. Store immutable payloads and checksums.

**Changing `eventId` during replay:** Bypasses deduplication and risks duplicate side effects. Keep the original `eventId`; use a separate `replayRunId`.

**Ignoring ordering:** Older events overwrite newer state. Validate aggregate sequence/version and partition alignment.

**Redriving too fast:** Overloads downstream systems again. Rate-limit, canary, and use a dedicated replay queue.

**Leaving quarantine data unprotected:** Payloads may contain PII or credentials. Enforce encryption, strict IAM, and auditing.

**Skipping reconciliation:** Replay reports success while business state remains incomplete. Compare event counts against actual business state.

## 24. Pre-redrive and pre-replay checklist

- [ ] Identified the exact trigger type and where retries are managed.
- [ ] DLQ/archive/quarantine was configured before the incident and still holds the data.
- [ ] Original payloads and source metadata are preserved immutably.
- [ ] Failures are classified into transient, permanent, schema, and authorization categories.
- [ ] Root cause has been fixed and verified.
- [ ] Scope defined by event IDs, time window, partition, or tenant.
- [ ] Consumer enforces idempotency and handles duplicates safely.
- [ ] Policies cover ordering, sequences, and late-arriving events.
- [ ] Legacy schemas are supported or validated transformers/upcasters are in place.
- [ ] Replay rate and worker concurrency fit within downstream capacity.
- [ ] Canary batch, pause/stop controls, and guardrails on errors, latency, and queue age are ready.
- [ ] Replay is isolated from live traffic where needed.
- [ ] Payload viewing and replay execution permissions are restricted and audited.
- [ ] `replayRunId`/`recoveryBatchId` is attached for traceability.
- [ ] Reconciliation tracks selected, replayed, succeeded, duplicated, and still-failing events.
- [ ] Runbook and accountable owner are assigned to close out recovery.

## Conclusion

Quarantining isolates events that cannot be processed safely; DLQs and retries bound failures across queues and consumers; redriving returns messages to processing; archives or stream retention enable scoped, time-bounded replay. Each service has distinct semantics: SQS DLQs, Lambda asynchronous destinations, EventBridge archives, and Kinesis/Kafka offsets are not interchangeable.

Before replaying, fix the root cause, preserve original events, determine ordering, schema, and blast radius, and throttle throughput using queues, concurrency caps, and rate limiters. Java consumers require stable idempotency keys, atomic state transitions, and safe logging. Finally, reconcile business outcomes and retain audit records to prove recovery is complete.
