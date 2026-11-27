# Building a Workflow for Fixing, Replaying, and Reconciling Messages

In an event-driven system, not every message succeeds on the first attempt. A dependent service may go down temporarily, a new schema may be incompatible with an older consumer, or incoming data may violate a business rule. Retries help handle transient errors; a Dead Letter Queue (DLQ) retains messages that cannot be processed under the current policy. However, routing a message to the DLQ is only the isolation step. To recover the system, operations teams must identify the root cause, fix the error, perform controlled replay, and reconcile outcomes.

Spring Cloud Stream provides bindings, binders, retries, and broker-specific DLQ integrations. Applications must add operational workflows to manage the lifecycle of failed messages: retaining traces, classifying errors, deciding on replay, preventing duplicate side effects, and verifying state after recovery. This lesson covers that workflow for Kafka, RabbitMQ, and Pulsar.

## 1. Distinguishing Retry, DLQ, Replay, and Reconciliation

These four operations often work together, yet solve different problems:

| Concept | Purpose | Example |
|---|---|---|
| Retry | Re-attempt an operation likely to succeed after a pause | Brief payment API timeout |
| DLQ | Isolate messages that exceeded processing policy or cannot be processed automatically | Invalid payload, repeated failures beyond limit |
| Replay | Re-emit stored messages for consumer reprocessing after the cause is fixed | Resending orders after fixing a mapping bug |
| Reconciliation | Compare actual state against an authoritative source of truth to detect and repair discrepancies | Reconciling paid orders against the ledger |

Retry typically happens close to the failure time and is bounded. DLQ stores messages for human or recovery-process review. Replay puts messages back onto a processing path. Reconciliation checks business outcomes and identifies missed, duplicated, or inconsistent states.

Not every message in the DLQ should be replayed immediately. If the cause is permanently bad data, replaying the same payload repeats the error. If the cause is a software bug, deploy and test the fix first. If the business action already completed but the response was lost, replay can cause duplicate side effects unless the consumer is idempotent.

## 2. End-to-End Recovery Workflow

A clear operational workflow can be divided into states:

~~~text
DETECTED
   |
   v
TRIAGED -----> REJECTED / MANUAL_REVIEW
   |
   v
ROOT_CAUSE_FIXED
   |
   v
REPLAY_VALIDATED
   |
   v
REPLAYING
   |
   v
RECONCILING
   |
   v
VERIFIED
   |
   v
CLOSED
~~~

Meaning of each step:

1. **Detected:** alerts indicate DLQ growth, error rates exceeding thresholds, or abnormal consumer lag.
2. **Triaged:** identify error type, affected message scope, destination, group, and time window.
3. **Root cause fixed:** fix the failing configuration, data, schema, or code; verify the updated version is ready.
4. **Replay validated:** dry-run on a small subset or staging environment, confirming outcomes and duplicate behavior.
5. **Replaying:** re-emit in batches with rate limiting and checkpoints.
6. **Reconciling:** compare processing results against an authoritative source of truth.
7. **Verified:** confirm no in-scope messages remain unprocessed, no unresolved discrepancies remain, and metrics return to normal thresholds.
8. **Closed:** archive report, operator, root cause, message counts, and outcomes.

Each recovery run should have a batch ID, an owner, stopping conditions, and a bounded message scope. Never run a broad replay across the entire DLQ if only a specific subset of messages was affected.

## 3. Retaining Sufficient Metadata for Investigation

When placing messages into a DLQ or quarantine store, retain the original data alongside metadata identifying its origin and processing history. A recovery record should include:

- Original payload or a secure reference to the payload.
- Event ID and correlation ID if supplied by the producer.
- Destination, binding, consumer group, or subscription name.
- Broker metadata such as topic, partition, offset, routing key, or message ID if available.
- Ingestion timestamp, failure timestamp, and attempt count.
- Exception type, sanitized error message, and consumer version.
- Content type, schema version, or schema ID when schema formats are used.
- Replay batch ID, processing status, and recovery timestamp.

Never write tokens, passwords, credentials, or unnecessary personal data into logs and DLQ tables. If payloads contain sensitive data, enforce corresponding access control, encryption, retention periods, and audit workflows.

Example application-managed recovery envelope:

~~~java
import java.time.Instant;

record FailedEvent(
        String eventId,
        String destination,
        String consumerGroup,
        String contentType,
        String payload,
        String errorCode,
        String errorMessage,
        int attempts,
        Instant firstFailedAt,
        Instant lastFailedAt) {}
~~~

This is an illustrative data model, not a mandatory DLQ structure for all binders. Actual metadata may reside in broker headers, the original message, or a separate operational table. When storing payloads, ensure you can restore the exact bytes and schema required; do not store only a converted string if doing so loses wire details needed for decoding.

## 4. Classifying Root Causes Before Replaying

Before replaying, identify which category the failure belongs to:

| Error Category | Signs | Action |
|---|---|---|
| Transient | Timeouts, intermittent broker or dependent-service disconnects | Retry with backoff; replay once dependency stabilizes |
| Configuration | Wrong credentials, destination, routing, or permissions | Fix configuration, verify connectivity, then replay |
| Schema/serialization | Unable to decode, missing field, or incompatible schema | Fix consumer/schema or deploy compatible reader |
| Business data | Missing identifier, out-of-range value | Quarantine, repair data via approved process, or reject |
| Code bug | `NullPointerException`, mapping or logic error | Fix and deploy code, run tests, then replay |
| Ambiguous state | Timeout after side effect may already have completed | Reconcile against source of truth before deciding to replay |

Transient errors can be retried after a pause. Permanent data errors should not enter continuous retry loops. Ambiguous-state errors must be reconciled first because the system may already have executed the business operation even though the consumer never recorded success.

## 5. Configuring Retry and DLQ in Spring Cloud Stream

Spring Cloud Stream can configure attempt counts at the binding level. With the Kafka binder, DLQ is enabled via binder-specific configuration. Illustrative example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

In the example, the binding attempts processing up to three times under the framework retry policy before applying the configured error/DLQ handling. The DLQ name is explicitly specified for clear operations and alerting. Specific properties, DLQ creation behavior, DLQ partition counts, and support conditions depend on the Kafka binder version.

Do not treat the configuration above as universal for RabbitMQ or Pulsar. The Rabbit binder has its own dead-letter exchange/queue properties; the Pulsar binder has its own dead-letter topic and redelivery settings. Consult the documentation for your exact binder version before deploying to production.

Retries need backoff and limits. Retrying too rapidly can add load to a struggling dependency. If waiting cannot resolve the failure, move the message to the DLQ for investigation instead of retrying forever.

## 6. Replaying Messages in Kafka

Kafka stores records by topic, partition, and offset. When a consumer group reads records, progress is normally tracked via committed offsets. Distinguish two recovery approaches:

1. **Re-reading from the source topic:** adjusting the consumer group's offset or using a new group to re-read a record range.
2. **Replaying from the DLQ:** a replay publisher reads records from the DLQ and publishes payloads to the target topic or a replay topic.

Re-reading from the source topic can cause the consumer to reprocess already-succeeded records within the rewound offset range. Altering offsets affects group progress and can duplicate side effects. Only do this once partition, offset, group, and consumer stop/start plans are clear.

Replaying from the DLQ creates new records with new offsets. You cannot restore the original offset by republishing. If provenance tracing is required, preserve original topic, original partition, original offset, and event ID as business metadata or allowed forwarded headers.

Example output binding configuration dedicated to replay:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderReplay-out-0:
          destination: orders.replay
          content-type: application/json
~~~

The `orders.replay` destination is merely an output target for new messages; the order-processing consumer must be configured to read this replay stream, or an intermediary component must route it into the same business logic. Publishing directly back to `orders.created` may deliver copies to every consumer group subscribed to the source topic, not just the failed group. Choose the replay path based on recovery scope and document the target group/destination.

A replay publisher can use `StreamBridge` to emit verified messages:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalMinorUnits) {}

record ReplayMetadata(
        String replayBatchId,
        String originalEventId,
        String originalTopic,
        int originalPartition,
        long originalOffset,
        Instant replayedAt) {}

@Component
class OrderReplayPublisher {

    private final StreamBridge streamBridge;

    OrderReplayPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean replay(OrderCreated event, ReplayMetadata metadata) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", metadata.originalEventId())
                .setHeader("replayBatchId", metadata.replayBatchId())
                .setHeader("originalTopic", metadata.originalTopic())
                .setHeader("originalPartition", metadata.originalPartition())
                .setHeader("originalOffset", metadata.originalOffset())
                .setHeader("replayedAt", metadata.replayedAt().toString())
                .build();

        return streamBridge.send("orderReplay-out-0", message);
    }
}
~~~

The example builds a new message for replay; it does not restore the original offset and does not automatically guarantee the record lands in the same partition. If partitioning by `orderId` must be preserved, the output binding needs an appropriate partition key and the replay topic must be configured compatibly. Do not blindly copy all broker headers from the DLQ onto the new topic; some headers only make sense for the prior delivery.

The `OrderCreated` payload in the example still carries the original `eventId`. The `eventId` header is set to the same value to aid observability; the consumer must use the same stable identifier in its inbox/idempotency check regardless of whether it reads it from payload or header.

The boolean return value of `StreamBridge.send` indicates the message was accepted by the binding/channel; do not treat that value alone as confirmation of durable broker persistence. A replay publisher needs binder-appropriate send confirmation (such as RabbitMQ publisher confirms or Kafka/Pulsar producer send results) before marking the DLQ source item complete. If the binder/API lacks the required confirmation on the send path in use, design checkpointing and duplicate emission handling for at-least-once delivery.

## 7. Replaying from RabbitMQ

RabbitMQ commonly uses a dead-letter exchange (DLX) to route rejected, TTL-expired, or queue-limit-exceeded messages to a dead-letter queue. Replay can be performed by:

- Fixing the cause that led the consumer to reject the message.
- Reading a batch from the DLQ via a tool or recovery publisher.
- Publishing the message to the target exchange with the designated routing key.
- Marking or acknowledging the DLQ message only after the publisher has sent it according to the chosen delivery policy.

If the replay publisher acknowledges the DLQ message before publishing succeeds, messages can be lost. If publishing succeeds but the publisher stops before acknowledging the DLQ message, the message may be re-sent and create duplicates. Publisher confirms, proper acknowledgments, event IDs, and idempotent consumers are required to manage this gap.

Do not enable infinite requeuing for permanently failing messages. A continuously requeued message creates a hot loop, spikes CPU, and starves valid messages. DLX/DLQ should hold failing messages for classification and controlled processing.

## 8. Replaying from Pulsar

Pulsar can route unprocessable messages to a dead-letter topic according to subscription settings and redelivery policy. A consumer can read the dead-letter topic and replay messages to the processing topic after the root cause is resolved.

When replaying, distinguish:

- Redelivery within the current subscription: the broker redelivers unacknowledged messages per subscription rules.
- Reconsume or seek: the consumer re-reads data from a cursor/subscription at a specific position.
- Republish: the application creates a new message from the DLQ and sends it to the target or replay topic.

These approaches have different semantics regarding message IDs, cursors, and ordering. When creating a new subscription to replay history, manage subscriptions and retention carefully. With `Key_Shared` or partitioned topics, verify keys, batching, redelivery, and acknowledgments so key-based ordering requirements are not violated.

Do not assume Kafka or RabbitMQ DLQ configurations apply to Pulsar. Use the exact dead-letter topic, subscription type, and redelivery policy settings of the deployed Pulsar binder/client.

## 9. Designing Safe and Resumable Replay

A replay job must be stoppable, resumable, and able to prove what scope was processed. Before running:

1. Select the DLQ/topic/queue and time window or list of event IDs to recover.
2. Record the selection query, expected count, and replay batch ID.
3. Run a dry-run to count messages, validate schemas, and detect out-of-scope records.
4. Confirm the root cause is fixed and the updated consumer can process the payload.
5. Run small batches with rate limiting and monitor errors/lag.
6. Save a checkpoint after each batch; never mark complete before confirming send results.
7. Pause if error rates exceed thresholds, backlogs spike, or duplicate side effects appear.
8. Reconcile results before closing the recovery run.

A replay tracking table may include:

| Field | Meaning |
|---|---|
| `replayBatchId` | Unique identifier of the replay batch |
| `eventId` | Original event identifier |
| `sourceLocation` | DLQ, topic/partition/offset, or queue |
| `targetDestination` | Replay destination |
| `status` | `PENDING`, `SENT`, `VERIFIED`, or `FAILED` |
| `attempts` | Number of publisher send attempts |
| `lastError` | Most recent error if sending failed |
| `updatedAt` | Last update timestamp |

Checkpoints must be durable enough for the job to resume after a restart. Even if `SENT` is recorded after a successful publish, a window remains where the publisher can crash between those two steps. Replays can emit duplicates; designs must assume at-least-once delivery and rely on consumer idempotency.

## 10. Idempotency to Prevent Duplicate Side Effects

Replays commonly cause redelivered messages. Therefore, consumers must distinguish an already-processed event from a new event. A common pattern is using `eventId` as an idempotency key and persisting processing state in the same transaction as data side effects.

Example inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Processing pseudocode:

~~~java
import java.time.Instant;

import org.springframework.transaction.annotation.Transactional;

@Transactional
void handle(OrderCreated event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderRepository.apply(event);
    processedEventRepository.save(
            new ProcessedEvent(event.eventId(), Instant.now()));
}
~~~

The example illustrates the principle; to avoid race conditions, rely on a unique constraint on `event_id` and handle insert conflicts safely. Checking existence before inserting is insufficient when two consumers can process the same event concurrently. The side effect and processed marker must share one transaction if within the same database.

If the side effect calls an external service or payment gateway, a database transaction cannot make that external call atomic by itself. Use an idempotency key supported by the external service, an outbox/inbox pattern, or a state-reconciliation check before retrying. Do not treat `eventId` in a header as sufficient unless the system actually stores and checks it.

## 11. Repairing Data and Schemas Before Replay

Some messages fail because the data no longer conforms to newer schemas or rules. Distinguish:

- **Consumer fix:** deploy a compatible reader or fix mapping without altering the original payload.
- **Data normalization:** transform the payload through a controlled migration step while retaining both original and repaired versions.
- **Business rejection:** mark the message unprocessable, request the upstream producer to fix and emit a new event per contract.
- **Data enrichment:** look up missing data from an authoritative source by key, explicitly recording which fields were enriched and from which reference.

Never modify payloads inside the DLQ in place without auditing. If transformation is required, create a repaired-event record linked to the original event, capturing transform version, operator, and reason. Upon replay, consumers must recognize the original event ID or a stable processing identifier to avoid treating repaired records as brand-new business events.

If a schema ID or original writer schema is required for decoding, preserve that metadata. Do not alter content type or schema version merely to make the converter accept the payload if the actual body was not converted to match.

## 12. Reconciling After Replay

Successful broker-level replay does not prove business state is accurate. Reconciliation compares processing outcomes against an authoritative source of truth, such as the business database, ledger, payment processor, or a verified snapshot.

Reconciliation workflow:

1. Identify the source of truth and reconciliation keys, such as `orderId`, `paymentId`, or `eventId`.
2. Choose a time window and data scope matching the replay batch.
3. Compare expected, emitted, and processed event counts alongside business states.
4. Classify missing, duplicate, out-of-order, or mismatched values.
5. Produce a reproducible discrepancy list with owners.
6. Repair using idempotent operations or approved compensating workflows.
7. Re-run reconciliation and store the final result.

Order reconciliation example:

| Source-of-Truth State | Projection State | Conclusion |
|---|---|---|
| PAID | PAID | Match |
| PAID | PENDING | Possibly missing `PaymentCompleted` event |
| PENDING | PAID | Possibly duplicate emission or out-of-order |
| Nonexistent | PAID | Orphaned data requiring investigation |

Do not automatically overwrite projections from the source of truth for every discrepancy if the projection enforces its own rules or the source lacks full history. For financial ledgers, prefer audited adjustment entries/compensating events over directly mutating transaction history.

## 13. Checkpointed and Rate-Limited Reconciliation

Reconciling large datasets requires pagination or time windowing. Each batch should record:

- Start and end key bounds.
- Snapshot or timestamp at which the source of truth was read.
- Records checked, records matched, and discrepancy count.
- Batch ID, execution timestamp, and checkpoint.
- Resolution status of each discrepancy.

If the source of truth mutates during reconciliation, results can become inconsistent. Use snapshot isolation, watermarks, or finalized time windows as supported by your datastore. When calling external APIs, cap concurrency and rate to avoid triggering a new outage during recovery.

Reconciliation should not run continuously without circuit-breaking thresholds. If discrepancies spike unexpectedly, halt the batch and investigate the root cause rather than automatically emitting bulk compensating events.

## 14. Monitoring and Reporting a Recovery Run

A replay/reconciliation run needs traceable metrics and logs:

- DLQ message count by destination, group, and error type.
- Age of the oldest message in the DLQ.
- Counts of triaged, replay-approved, re-sent, and verified messages.
- Replay success rate, new error count, and retry counts.
- Consumer lag, throughput, and latency after replay.
- Events skipped due to idempotency.
- Reconciliation discrepancies by type and backlog age.

Logs should include `replayBatchId`, `eventId`, original location, target destination, and status. Avoid logging entire payloads if they contain sensitive data. The final report should summarize total messages in scope, count replayed, count excluded with reasons, count pending, and discrepancies resolved.

## 15. Testing the Recovery Workflow

Tests must verify more than a consumer handling one valid message. Test operational scenarios:

1. Failing messages exceed `max-attempts` and land in the right DLQ destination.
2. DLQ messages retain event ID and metadata needed for tracing.
3. The replay publisher emits only approved messages within the batch scope.
4. Publisher crashes mid-send and checkpoint update; restarting loses no messages.
5. Consumer receives the same event ID twice while the side effect runs only once.
6. Schema-incompatible messages are quarantined and not retried infinitely.
7. Reconciliation detects a missing or duplicated projection.
8. Replay halts when new errors exceed threshold and resumes from checkpoint.
9. Real-broker tests verify DLQ, redelivery, acknowledgment, and routing semantics.

Spring Cloud Stream's test binder is helpful for testing function logic and application-level bindings. It does not replace integration tests for Kafka offsets, RabbitMQ DLX/acknowledgments, or Pulsar dead-letter topics/subscriptions. Replay and reconciliation operations should be tested against matching brokers and datastores.

## 16. Operational Checklist

- Alerts exist for DLQ growth, aging backlogged messages, or repeated consumer failures.
- Every failed message retains its event ID and required source metadata.
- Root causes are classified and fixed before replaying.
- Replays have a batch ID, defined scope, dry-run, rate limits, and checkpoints.
- Never alter consumer offsets or bulk-republish without understanding the blast radius.
- Replays assume at-least-once delivery and consumers enforce idempotency.
- Modified payloads have an audit trail linking back to the original message.
- Reconciliation uses a clear source of truth, matching keys, and checkpoints.
- Business discrepancies are repaired via safe operations or compensating events.
- Final reports capture counts, outcomes, root causes, and remaining open cases.

A DLQ is a place to isolate messages for intentional handling, not the end of the workflow. A reliable recovery process classifies root causes, fixes errors, replays in small resumable scopes, prevents duplicate side effects with idempotency, and reconciles against an authoritative source of truth. By pairing Kafka, RabbitMQ, or Pulsar mechanics with Spring Cloud Stream bindings and binders, operations teams can recover failed messages while keeping business state under control.
