# Handling Late, Out-of-Order, and Missing Events

## Objectives

In an event-processing system, the time an event occurs, the time a producer sends it, and the time a consumer receives it can differ significantly. A message can arrive after messages created later, arrive after an aggregation window has already closed, or fail to appear at the consumer even though the source business event occurred. These situations are commonly referred to as **late events**, **out-of-order events**, and **missing events**.

Spring Cloud Stream provides bindings and binders to connect applications with Kafka, RabbitMQ, or Pulsar. These abstractions organize processing flows, but do not automatically guarantee global ordering, detect every lost event, or repair business state when a message arrives late. The application must define the scope where ordering matters, identify events with stable identifiers, and establish recovery procedures when gaps are detected.

After this lesson, you will be able to:

- Distinguish event time, processing time, and broker ingestion time.
- Identify causes of late or out-of-order message arrivals.
- Design ordering per aggregate/key instead of assuming global ordering.
- Detect gaps using sequence numbers, event IDs, and data reconciliation.
- Choose policies to accept, defer, correct, or quarantine late events.
- Use watermarks and grace periods when processing time windows with Kafka Streams.
- Test and monitor latency, duplicates, out-of-order arrivals, and missing events.

## 1. Three Distinct Problems

These concepts are often lumped together but must be distinguished:

| Situation | Meaning | Example |
|---|---|---|
| Late event | Message is processed after the business timestamp or after the cutoff expected by the processing flow | Transaction occurred at 10:00, but consumer receives it at 10:08 |
| Out-of-order event | Consumer receives events in a different order than the business order to preserve | Receiving `OrderShipped` before `OrderPaid` |
| Missing event | An expected event has not been observed yet or is no longer found in the stream | Aggregate has sequences 10 and 12, but 11 has not been seen |

An event can be both late and out-of-order. A missing sequence might simply be a delayed message, or it might be a lost, dropped, or never-successfully-published message. You cannot conclude a message is lost merely because it has not appeared for a few seconds; a defined SLA or gap-detection timeout is required.

### Event Time, Processing Time, and Broker Time

- **Event time / occurredAt:** when the event occurred in the business domain, recorded by the producer.
- **Processing time:** when the consumer actually processes the message.
- **Ingestion/record time:** when the broker receives or writes the message, depending on broker and timestamp configuration.

Example: a device records a temperature at 10:00 while offline. It sends the data at 10:07 and the consumer processes it at 10:07:01. Event time is 10:00; ingestion time is near 10:07; processing time is 10:07:01.

If processing time is used to compute hourly business reports, data can be placed into the wrong window. If event time is used, the system needs a policy for messages arriving after a window has already been considered complete.

## 2. Why Do Messages Arrive Late or Out of Order?

Common causes include:

- Multiple producers emitting events for the same aggregate without serialization.
- Producer retries when uncertain whether the broker received a message; the resend may arrive after a newer message.
- Concurrent consumer processing, causing operations to finish in a different order than received.
- Retries or redeliveries bringing an older message back after a newer message has already been processed.
- Rebalances, restarts, or failovers causing consumers to re-read uncommitted data.
- Multiple partitions or queues lacking a shared global order.
- Unstable networks, offline devices, or batch uploads introducing high latency.
- Skewed producer clocks or producers writing incorrect timestamps.
- Retention policies, subscription settings, or producer failures causing a message to no longer be stored/received as expected.

Distinguish broker delivery order from business order. A broker can deliver records in the exact order written to a partition, yet two producers can still write events in the wrong business order. Conversely, the broker may receive events in order while the consumer runs asynchronous processing so side effects complete out of order.

## 3. Ordering Guarantees by Broker

Spring Cloud Stream unifies how functions and bindings are declared, but ordering semantics depend on the broker and binder.

| Broker | Typical ordering scope | Causes of observed order changes |
|---|---|---|
| Kafka | Within a single partition of a topic | Multiple partitions have no global order; concurrent consumer processing; retries/replays and multiple producers |
| RabbitMQ | Within a single queue in enqueue order under normal conditions | Multiple consumers, prefetch, requeue, priority, redelivery, and asynchronous processing |
| Pulsar | Per topic/partition and chosen key/subscription mechanism | Shared subscription, multiple producers, redelivery, and concurrent processing |

### Kafka

Kafka guarantees record order within a single partition. If events for the same `orderId` are sent with the same record key and stable partition mapping, they can be written to the same partition. A consumer group reads that partition in log order.

However, Kafka does not guarantee ordering across partitions. If two events for the same aggregate are sent to two different partitions, consumers have no global order to rely on. Multiple consumers or asynchronous processing in the application can also cause side effects to finish in a different order than the records.

### RabbitMQ

A RabbitMQ queue has delivery ordering determined by topology and operating conditions, but FIFO should not be treated as an absolute business-order guarantee. Multiple consumers reading the same queue can finish processing out of order. Nacked/requeued or redelivered messages can reappear in a different position. Priority queues also alter delivery order.

If per-aggregate ordering matters, design routing/queues and consumer concurrency accordingly, and test requeue behavior. A single queue with a single consumer simplifies ordering at the cost of limiting throughput.

### Pulsar

Pulsar offers regular or partitioned topics, message keys, and multiple subscription types. Shared subscriptions optimize distribution across many consumers without overall processing order. `Key_Shared` can deliver messages with the same key to the same consumer per broker semantics, preserving key locality; verify key-based batching and ordering settings for your Pulsar version. Failover and Exclusive have different active-consumer models than Shared.

Choose the subscription type based on ordering and throughput needs. Do not assume the same `group` setting in Spring Cloud Stream produces identical semantics across Kafka, RabbitMQ, and Pulsar.

## 4. Designing an Event Envelope That Detects Order

To detect out-of-order arrivals or gaps, messages must carry sufficient metadata. An event envelope might include:

```java
public record OrderEvent(
        String eventId,
        String aggregateId,
        long sequence,
        String eventType,
        Instant occurredAt,
        Instant producedAt,
        int schemaVersion,
        OrderPayload payload
) {}
```

Meaning:

- `eventId`: unique identifier, stable across retries and replays.
- `aggregateId`: identifier of the entity whose order must be preserved, e.g., order ID.
- `sequence`: monotonically increasing sequence number within the aggregate scope.
- `eventType`: event type.
- `occurredAt`: business timestamp when the event occurred.
- `producedAt`: timestamp when the producer created/emitted the message.
- `schemaVersion`: contract version.
- `payload`: business data.

Sequences should be assigned by the authority responsible for the aggregate's ordering. If multiple independent producers increment sequences without coordination, they can create duplicate or conflicting sequences. Assign the sequence in the same transaction that updates the aggregate and writes the outbox so business state and event order stay consistent.

Do not use timestamps as a unique sequence. Two events can share the same timestamp, clocks can skew, and timestamps can be recorded inaccurately. Monotonically increasing sequences or versions are generally better suited to detecting gaps within an aggregate.

### Example Producer Writing Outbox in the Same Transaction

A business transaction can update the aggregate, increment the version, and write the outbox:

```java
@Transactional
public void markOrderPaid(String orderId) {
    Order order = orderRepository.findForUpdate(orderId);
    order.markPaid();

    long sequence = order.nextEventSequence();
    orderRepository.save(order);

    outboxRepository.append(new OrderEvent(
            eventIdGenerator.next(),
            orderId,
            sequence,
            "order.paid",
            clock.instant(),
            clock.instant(),
            1,
            OrderPayload.from(order)
    ));
}
```

This example illustrates transaction boundaries; sequence assignment must fit the application's aggregate model and database schema. An outbox relay may republish the same event on failure, so the event ID must stay unchanged across sends.

## 5. Key-Based Routing to Preserve Order in the Required Scope

If per-aggregate order is needed, choose an appropriate partition key rather than trying to enforce global order across an entire topic.

With the Kafka binder, producer bindings can use `partitionKeyExpression`:

```yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-key-expression: payload.aggregateId
            partition-count: 12
```

Events with the same `aggregateId` route by the same key within the same partition topology. The consumer group reads each partition in record order. `partition-count` must match the provisioned topic and binder configuration; changing the partition count alters key-to-partition mapping.

For RabbitMQ, routing keys and queue topology can be designed so the same aggregate travels through a suitable processing stream. Limit concurrency if strict ordering is required; requeue/redelivery can still affect observed order.

For Pulsar, message keys and `Key_Shared` subscriptions help messages with the same key go to the same consumer in the subscription. Check key-based batching and subscription configuration to verify desired ordering.

### Keys Do Not Automatically Guarantee In-Order Side Effect Completion

Even when records with the same key enter one partition, consumer code might call `flatMap` to process multiple events concurrently. Sequence 12 could update the database before sequence 11. When side effects must be serialized, process sequentially per partition/key or enforce sequence checks inside the transaction.

With Reactor, `concatMap` serializes inner publishers:

```java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> applyOrderEvents(
        OrderEventService service) {
    return events -> events
            .concatMap(service::apply)
            .then();
}
```

`flatMap` can increase concurrency but does not guarantee completion order. Choose the operator based on business requirements and the reactive binder in use.

## 6. Handling Out-of-Order Events with Sequence Numbers

A consumer can track the last applied sequence for each aggregate.

Suppose aggregate `order-42` has applied sequence 10:

- Receive sequence 11: in order, can be applied.
- Receive sequence 10: old or duplicate event; check event ID/processed state.
- Receive sequence 12: missing sequence 11; do not apply blindly if sequence 11 affects the outcome.
- Receive sequence 11 after sequence 12 was already applied: may be a late event; apply a state-correction or ignore policy.

A basic decision rule:

```text
incoming.sequence == lastSequence + 1  -> apply
incoming.sequence <= lastSequence      -> duplicate/stale; deduplicate or reconcile
incoming.sequence > lastSequence + 1   -> gap; buffer and recover missing sequence
```

This rule is per aggregate. Another flow might allow skipping sequences if events are independent; do not apply strict gap checks indiscriminately to every event type.

### Inbox and Pending-Event Store

A consumer can use two storage areas:

- **Inbox/processed event store:** records received event IDs to prevent duplicate processing.
- **Pending event store:** holds events arriving before prior sequences have been processed.

Illustrative data model:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(120) PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    received_at TIMESTAMP NOT NULL
);

CREATE TABLE pending_order_event (
    aggregate_id VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_id VARCHAR(120) NOT NULL UNIQUE,
    payload JSON NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (aggregate_id, sequence_no)
);
```

When receiving sequence 12 while the current sequence is 10, the consumer can save sequence 12 into the pending store within a transaction and complete message reception. A recovery process fetches sequence 11 from the source of truth or waits for it to arrive. Once sequence 11 is applied, the process continues applying sequence 12.

If the message is durably stored in the pending store, the broker can be acknowledged because recovery responsibility has shifted to the internal store. Without durable storage, do not acknowledge the message and hold it only in RAM; a process restart would lose the acknowledged event.

### Transactional Updates and Race Condition Protection

Reading the last sequence and updating it must be protected by a transaction, appropriate locking, or optimistic locking. If two consumers process events for the same aggregate concurrently, both must not apply sequences against the same stale state.

A conditional version update can be used:

```sql
UPDATE orders
SET status = :new_status,
    version = :incoming_sequence
WHERE order_id = :order_id
  AND version = :incoming_sequence - 1;
```

If 0 rows are updated, the current state already changed or the sequence is non-contiguous. The application must re-read and classify the case as duplicate, stale event, or gap. Do not treat every 0-row update as the same error.

## 7. Handling Late Events by Event Time

A message with a valid sequence can still arrive late in business time. For example, a transaction event from 10:00 arrives only at 10:12. Handling depends on the business domain:

- **Accept and recompute:** if reports can be revised, update the affected aggregate/window.
- **Emit a correction event:** keep the old result and emit an adjustment event with an audit trail.
- **Route to a late-event stream:** quarantine for separate handling if the main window has closed.
- **Reject per SLA:** if business rules reject data past a cutoff, record the reason and enable reconciliation.
- **Wait longer before finalizing:** increase wait time/watermark if delay is a normal characteristic of the source.

Do not automatically discard every event whose timestamp is older than the current time. A late event can carry important information and represent a valid source of truth.

### Event Time and Clock Skew

Producer-generated timestamps can be wrong due to device clock skew, unclear timezones, or recording send time instead of occurrence time. Before enforcing a late-event policy, determine:

- Who is the authoritative source generating `occurredAt`.
- Whether timestamps carry timezone/UTC consistently.
- Maximum tolerable clock skew.
- Whether both `occurredAt` and `producedAt` are needed for diagnostics.
- Whether events have a sequence/version to verify order independently of timestamps.

## 8. Watermarks and Grace Periods in Kafka Streams

When processing event-time windows, a system needs a marker to decide when a window can be considered nearly complete. A **watermark** represents event-time progress indicating the system believes most events before that timestamp have arrived. A watermark does not prove absolutely that no older events will arrive.

Kafka Streams uses record timestamps and a window's grace period to decide whether a late record may still update window results. A window with a grace period can be configured using the DSL:

```java
KStream<String, PaymentEvent> payments = ...;

KTable<Windowed<String>, Long> countByAccount = payments
        .groupByKey()
        .windowedBy(
                TimeWindows.ofSizeAndGrace(
                        Duration.ofMinutes(5),
                        Duration.ofMinutes(2)
                )
        )
        .count();
```

Example: a 5-minute window with a 2-minute grace period permits late records within the grace interval under Kafka Streams event-time semantics. Records arriving after the window closes per stream-time/grace policy will not update that window's result. The timestamp extractor policy determines which record timestamp Kafka Streams uses.

Distinguish clearly:

- Window size defines the event-time interval being grouped.
- Grace period defines how long late records are accepted after the window's end in stream-time.
- Stream-time advances according to record timestamps observed by the topology; it is not simply wall-clock time.
- Records arriving after grace can be dropped from the window computation; Kafka Streams does not automatically send them to a DLQ unless the application designs a dedicated handling path.

If late events must be investigated or applied as corrections, design an appropriate processor/branch or side stream to persist and observe them. Check the exact Kafka Streams and Kafka Streams binder APIs for your version, as timestamp extractor, window, and error-handling configuration may differ.

## 9. Detecting Missing Events

A message that has not appeared yet might merely be delayed. Detecting missing events requires a verifiable expectation signal.

### Sequence Gaps

If each aggregate has a contiguous increasing sequence, receiving sequence 15 after sequence 13 indicates sequence 14 is missing. The consumer can:

1. Record the gap with the aggregate ID and missing sequence.
2. Set a wait deadline based on the SLA.
3. Look up the missing event in the broker/source of truth or request a producer replay.
4. Hold later arrivals in the pending store if ordering is required.
5. Trigger an alert when the gap exceeds the timeout.
6. Resume processing once the gap is recovered or a business decision is made.

### Reconciliation with the Source of Truth

If the producer does not provide a sequence, it is difficult for the consumer to prove a specific event was lost. Perform periodic reconciliation against the authoritative data source:

- Compare the number of issued orders with the number of events recorded by the consumer.
- Compare aggregate state between the source database and the read model.
- Check for unpublished outbox records.
- Reconcile batch IDs or high-watermarks across systems.
- Check event IDs in archival/replay logs.

Consumer lag only indicates the consumer is behind the log/queue; it does not prove a business event was lost. Similarly, equal message counts do not prove the exact same set of events was processed; reconcile by event ID or sequence.

### Heartbeats and Expected Events

Some sources emit periodic heartbeats or watermarks. If a heartbeat fails to arrive on schedule, the system can detect a silent source or stalled stream. This is stream-level anomaly detection and does not necessarily pinpoint which specific message is missing. Combine heartbeats with sequences and reconciliation for stronger evidence.

## 10. Recovering Missing or Late Messages

When a gap is detected, do not fabricate a synthetic business event merely to plug a sequence number. Recover from a trustworthy source:

1. Locate the event by event ID or aggregate sequence in the outbox, event store, or source log.
2. Verify the event has not already been applied at the consumer.
3. Replay while preserving the original event ID, aggregate ID, and sequence.
4. Ensure the consumer deduplicates by event ID.
5. Reprocess pending events once the gap is filled.
6. Reconcile the aggregate's final state.
7. Record an audit trail of the replay and outcome.

If the original event cannot be retrieved, the business may need a snapshot/read-model rebuild or a clearly defined correction event. Never pretend a correction is the original event; preserve causation links and change history.

### Replay and Offsets

With Kafka, replays can re-read offsets or republish events from an event store/outbox to a replay topic. Resetting a consumer group's offset affects the entire partition/group and requires careful operational procedures. Do not reset production offsets just to retry one message without evaluating the impact on all subsequent records.

With RabbitMQ, replays can be executed from a DLQ or archive by republishing messages to the appropriate exchange/queue. With Pulsar, subscription cursors, seek operations, or replaying from archived topics can be used depending on client/binder capabilities. Always check permissions and broker semantics for specific operations.

## 11. Designing Consumers Resilient to Late, Duplicate, and Out-of-Order Events

A resilient consumer typically combines these mechanisms:

- **Idempotency:** stable event ID and inbox/unique constraint so the same message causes no duplicate side effects.
- **Sequence validation:** checking per-aggregate version/sequence when ordering is a business requirement.
- **Pending gap store:** durably storing messages arriving before prior sequences are present.
- **Late-event policy:** defining whether old events are accepted, trigger corrections, are quarantined, or are rejected.
- **Reconciliation:** periodic checks against the source of truth to find missing events.
- **Producer outbox:** writing business change and event in the same transaction to reduce missing-publish risk.
- **Retry/DLQ:** distinguishing transient errors, poison messages, and gaps needing wait/recovery.
- **Bounded state:** bounding pending event count, wait duration, and reorder buffer capacity.

Not every stream needs every mechanism. Telemetry may tolerate sample loss and aggregate by event time; payments or order state generally require strict event IDs, sequences, idempotency, and reconciliation.

## 12. Example Aggregate Processing Strategy

A service can apply a policy like:

```java
@Transactional
public void accept(OrderEvent event) {
    if (inboxRepository.exists(event.eventId())) {
        return; // Duplicate already processed.
    }

    long current = orderRepository.currentSequence(event.aggregateId());
    long expected = current + 1;

    if (event.sequence() > expected) {
        pendingRepository.storeIfAbsent(event);
        inboxRepository.markPending(event.eventId());
        return; // Durably saved for gap recovery.
    }

    if (event.sequence() < expected) {
        inboxRepository.markStale(event.eventId());
        return; // Old event; requires reconciliation policy if prior application is uncertain.
    }

    applyAndAdvance(event);
    drainNextPendingEvents(event.aggregateId());
}
```

This is illustrative pseudocode. Real implementations must protect sequence updates with transactions/locks or optimistic concurrency, and distinguish an already-applied old event from one never recorded. If the sequence is less than expected but the event ID is not in the inbox, do not silently drop it without verification; it could be a valid late event while the aggregate was updated via a snapshot or another path.

When saving an event to the pending store, writing to the inbox and pending store must share the same transaction so the system never marks an event as received without retaining its payload. Once the gap is filled, a recovery worker reads pending events in sequence order, applies them sequentially, and updates their status. Bound pending age and count so a broken aggregate cannot fill up the database.

## 13. Production Observability and Alerting

Track these metrics:

| Metric | Meaning | When to alert |
|---|---|---|
| Event-time lag | Gap between current/processing time and event time | Sudden spike or SLA breach |
| Late-event count/rate | Count/rate of events arriving past expected cutoff | Exceeds business threshold |
| Out-of-order count | Events with sequence > expected or invalid order | Increasing per aggregate/partition |
| Missing-sequence gap | Number of unfilled gaps | Gap persists beyond timeout |
| Pending-event age/depth | Age and count of events waiting on gaps | Continuously growing or hitting capacity |
| Duplicate/stale rate | Seen event IDs or stale sequences | Abnormal increase after retry/replay |
| Reconciliation mismatch | Discrepancy between source of truth and consumer state | Unresolved mismatch exists |
| Consumer lag | Consumer progress relative to broker | Exceeds processing SLA, though not synonymous with missing events |

Logs should include event ID, aggregate ID, sequence, `occurredAt`, `producedAt`, destination, and partition/offset or message ID when available. Avoid logging full payloads containing sensitive data.

When alerting, provide enough context for investigation: which aggregate, which sequence is missing, the most recently applied event, event-time lag, and where to locate the original event. A generic "consumer is slow" alert is insufficient for deciding on a replay or data repair.

## 14. Testing Late, Out-of-Order, and Missing Events

Tests must construct deterministic sequences rather than relying on random timing.

### Unit Tests for Sequence and Idempotency

Create an event sequence 10, 12, 11 and verify:

- 10 is applied.
- 12 is stored as pending because 11 is missing.
- 11 is applied and then 12 is drained in order.
- Resending 11's event ID causes no duplicate side effects.
- Stale sequences are not reapplied outside policy.
- Gaps unfilled within the deadline trigger an alert or reconciliation request.

### Testing Event Time and Windows

With Kafka Streams, verify:

- The timestamp extractor extracts the right event time.
- Events falling inside the window are counted accurately.
- Events arriving within the grace period can update results per window semantics.
- Events arriving after grace are handled according to the designed late-event policy.
- Watermark/stream-time progression in tests does not depend on wall-clock time.

### Integration Tests with Binders/Brokers

- Kafka: send records with the same key, verify partition and order; restart/rebalance and observe duplicates/replays; test offsets and window grace.
- RabbitMQ: test multiple consumers, prefetch, nack/requeue, and redelivery order on a queue.
- Pulsar: test `Key_Shared`/`Shared` subscriptions, key ordering, and policy-driven redelivery.
- Verify the producer outbox does not drop events when database commits or broker publishes fail.
- Verify reconciliation and replay preserve original event IDs and sequences.

Test Binder is useful for wiring and function logic, but does not replace broker integration tests for partitioning, queue ordering, subscription types, redelivery, and cursors.

## 15. Production Runbook for Handling a Gap

When the system detects an aggregate has sequence 20 without 19:

1. Record a gap entry with aggregate ID, expected sequence, observed sequence, and detection time.
2. Check if message 19 is waiting in the broker, retry queue, DLQ, or pending store.
3. Query the producer's outbox/event store to verify whether event 19 was created and published.
4. If the original event exists, replay it with its original event ID and sequence into a controlled recovery path.
5. If the original event does not exist, reconcile aggregate state with the source of truth and decide on a snapshot/correction per business rules.
6. Once sequence 19 is processed, drain pending event 20 and subsequent events in order.
7. Close the gap record, write an audit trail, and verify final state.
8. If the gap cannot be recovered, escalate to the business owner instead of fabricating fake data.

Do not replay an entire topic or reset an entire consumer group just because one aggregate has a gap. Scope recovery by event ID/aggregate/partition and choose the least disruptive method.

## Conclusion

Late events involve event time versus processing time; out-of-order events involve arrival order versus business order; missing events must be detected using sequences, expectation signals, or reconciliation against the source of truth. Kafka preserves order within a partition, RabbitMQ depends on queues and consumer handling, and Pulsar depends on partitions, keys, and subscription types.

In Spring Cloud Stream, partition by the aggregate key that needs ordering, use event IDs for idempotency, and use sequences to detect gaps. For windowed processing, define timestamps, watermarks, and grace periods; for recoverable workflows, persist pending events, use outboxes, and run reconciliation. Explicitly test late and out-of-order sequences and verify behavior on the actual binder/broker before committing to SLAs.
