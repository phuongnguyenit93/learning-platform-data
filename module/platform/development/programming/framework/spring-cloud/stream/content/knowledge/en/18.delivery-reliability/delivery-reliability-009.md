# Data Reconciliation and Recovery After Partial Failures

In a Spring Cloud Stream system, a business flow often spans multiple components: the application updates a database, a producer sends an event to Kafka/RabbitMQ/Pulsar, a consumer updates data in another service, and it may also call an external API. These components do not participate in a single atomic transaction. Consequently, one step can succeed while the next step fails.

For example, the database saves an order but the application stops before publishing `OrderCreated`; or a consumer updates a projection but stops before acknowledging the message to the broker. These situations create **partial success** states: data across components falls out of sync, and messages may be missing or redelivered.

Data reconciliation detects discrepancies between expected state and actual state. Recovery brings the system back to a consistent state via replays, compensation, status updates, or escalating anomalies to operators. To do this safely, every event needs a stable identifier, consumers must be idempotent, and the system must persist progress trails.

## 1. Why Do Partial Failures Happen?

A distributed processing chain has many failure boundaries: processes can crash, networks can disconnect, brokers can reject publishes, databases can time out, or external services can execute work while the response is lost on the return path.

| Scenario | Possible leftover state | Risk |
|---|---|---|
| Database commit succeeds, event publish fails | Business record exists, but broker has no event | Downstream services are unaware the change occurred. |
| Broker receives event, producer stops before recording published | Event is on broker, but outbox still shows unsent | Relay may resend the event, creating duplicates. |
| Consumer updates database, ACK/offset commit fails | Business effect committed, but broker may redeliver message | Consumer processes duplicate. |
| Consumer ACKs/commits offset before database commits | Broker treats message as done, while database change rolls back | Business effect is lost even though the message will not be redelivered. |
| Payment API call succeeds, but app times out before saving result | Provider executed the transaction; app does not know the outcome | Retrying may create duplicate charges without idempotency. |
| Event sent to two destinations, only one send succeeds | Two downstream systems observe different states | Data streams diverge across systems. |

Partial failures are not necessarily broker bugs. Most arise because databases, brokers, and external services have separate commit boundaries. Increasing retries helps overcome transient glitches, but cannot by itself create atomicity across systems.

## 2. Identifying the Source of Truth and Expected State

Before reconciling, determine which system is the authoritative source of truth for each piece of information. For example, Order Service may be the source of truth for order state; Payment Service or the payment provider is the source of truth for transaction outcomes; a reporting projection is merely a query-serving replica.

Never compare two data copies without knowing which one is authoritative. If a projection lags behind the source of truth by a few seconds, that may be normal latency rather than data loss.

A reconciliation record should capture enough information to identify:

- **Event identifier:** unique `eventId`, stable across retries and replays.
- **Business identifier:** `aggregateId` such as `orderId`, `paymentId`, or `accountId`.
- **Business version:** `aggregateVersion` or sequence to detect change ordering.
- **Event type:** `eventType` and schema version.
- **Timestamps:** `occurredAt`, `createdAt`, `publishedAt`, `processedAt` when available.
- **Correlation:** `correlationId`, `causationId` to link steps across a workflow.
- **Delivery status:** pending, published, processed, failed, or the application's equivalent states.

Example event payload:

```json
{
  "eventId": "evt-01J9M7Q3",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-9001",
  "aggregateVersion": 1,
  "correlationId": "corr-checkout-77",
  "occurredAt": "2026-11-24T08:15:30Z",
  "data": {
    "customerId": "customer-42",
    "totalAmount": 125000
  }
}
```

`eventId` remains constant when the same event is retried or replayed. If a new ID is generated on each attempt, consumers cannot recognize copies of the same event. `aggregateVersion` detects missing or out-of-order events within an aggregate's scope.

## 3. Partial-Failure Matrix and Recovery Paths

Build a matrix for critical boundaries before deployment:

| Boundary | Signals to look for | Typical recovery path |
|---|---|---|
| Database → broker | Business record exists, but event missing / outbox unpublished | Transactional outbox and relay resend. |
| Broker → consumer | Message exists, but consumer has not processed it | Retry, redelivery, replay from broker or DLQ. |
| Consumer → database | Event received, but projection not updated | Inbox/idempotency and event replay. |
| Consumer → external API | Unclear whether API executed the operation | Query status via idempotency key, then retry or compensate. |
| Producer → multiple destinations | One destination received event, another did not | Per-destination delivery ledger/outbox and per-destination reconciliation. |
| Multiple events for same aggregate | Newer version present while earlier version missing | Detect gap by version, reload or replay missing part. |

No single mechanism handles every case. Outbox covers the database-producer boundary; inbox handles duplicate processing at the consumer; DLQ holds unprocessable messages; reconciliation detects remaining discrepancies; saga/compensation handles business effects that cannot roll back via local transactions.

## 4. Transactional Outbox: Never Lose Events After Database Commit

A common bug occurs when the application runs two independent operations:

```java
orderRepository.save(order);
streamBridge.send("orders-out-0", event);
```

If the database commits while publishing fails, the order is saved without an event. If publishing succeeds and the database rolls back, downstream consumers may receive an event for a nonexistent change. These two calls do not automatically become one atomic transaction merely by residing in the same Java method.

Transactional Outbox solves this by storing the business change and the event record in **the same database transaction**:

1. Update the order.
2. Insert the event into the outbox table.
3. Commit both together.
4. A separate relay reads the outbox and publishes events to the broker.
5. Upon receiving send confirmation per binder/broker semantics, the relay marks the record as published.

Example conceptual table structure:

```sql
CREATE TABLE outbox_event (
    event_id            VARCHAR(80) PRIMARY KEY,
    aggregate_id        VARCHAR(100) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    event_type          VARCHAR(150) NOT NULL,
    payload             TEXT NOT NULL,
    status              VARCHAR(20) NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    published_at        TIMESTAMP NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMP NULL,
    lease_until         TIMESTAMP NULL
);
```

Column types and SQL syntax must be adapted to the target database. `event_id` is the unique key; a unique constraint on `(aggregate_id, aggregate_version, event_type)` can be added if business rules guarantee one version emits at most one event of that type.

Example service writing order and outbox in one transaction:

```java
@Transactional
public void createOrder(CreateOrder command) {
    Order order = Order.create(command);
    orderRepository.save(order);

    OrderCreated event = OrderCreated.from(order);
    outboxRepository.insert(OutboxEvent.pending(
        event.eventId(),
        order.id(),
        order.version(),
        "OrderCreated",
        serialize(event)
    ));
}
```

If the transaction rolls back, neither the order nor the outbox row exists. If commit succeeds, the relay can still emit the event even if the web process stops.

### 4.1. Relays Must Tolerate Repeated Publishing

A relay typically reads pending rows in batches, claims them via a lease or suitable locking mechanism, publishes, and updates status. There is one failure window that cannot be eliminated solely by operation ordering:

- The broker received the event.
- The relay stops before updating `status = 'PUBLISHED'` in the database.
- After restarting, the relay sees the row is still pending and resends the event.

Therefore, an outbox typically provides **at-least-once publication**: events are not lost when designed properly, though they may be sent multiple times. Consumers must be idempotent by `eventId`. Never mark published before sending, because if the relay stops in between, the event could be lost permanently.

`StreamBridge.send(...)` returning `true` only reflects that the send operation was accepted at the API/channel layer per the implementation; do not assume it proves the broker durably persisted the data. The relay must use confirmation mechanisms supported by the binder/client and transition state only on a matching result. Publisher confirms, transactions, and timeout details differ across Kafka, RabbitMQ, and Pulsar.

### 4.2. Preserving Event Order When Relays Run Concurrently

If multiple relays read the outbox concurrently, two events for the same `aggregateId` may be published out of order. Work can be partitioned by aggregate, claimed with locks, or restricted so the next version is only emitted once the prior version is confirmed. Use `aggregateVersion` so consumers detect gaps and skip or quarantine out-of-order arrivals.

Global ordering across all events is unnecessary if the business only requires ordering per aggregate. Narrowing the ordering scope improves throughput.

## 5. Inbox and Idempotency: Handling Redeliveries Without Repeating Effects

Brokers can redeliver messages when a consumer finishes processing but ACK/offset commit is lost, when the consumer restarts, or when networks drop. This is normal behavior in an at-least-once model. Consumers must tolerate the same `eventId` appearing multiple times.

The inbox pattern persists markers for already-processed messages. An inbox table might look like:

```sql
CREATE TABLE inbox_message (
    consumer_name   VARCHAR(120) NOT NULL,
    event_id        VARCHAR(80) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    result_ref      VARCHAR(150) NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

The primary key `(consumer_name, event_id)` prevents the same consumer from applying the same event more than once. The consumer name must stay stable across deployments; changing it arbitrarily invalidates prior inbox deduplication records.

Processing algorithm:

1. Start the database transaction.
2. Attempt to insert `(consumer_name, event_id)` into the inbox.
3. If the key already exists, treat it as a redelivery and do not reapply the business effect.
4. If the insert succeeds, update the projection or business state in the same transaction.
5. Commit the transaction.
6. Let the binder/broker acknowledge the message per the configured mechanism after processing finishes.

Pseudocode example:

```java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = inboxRepository.tryInsert(
        "order-projection",
        event.eventId()
    );

    if (!firstDelivery) {
        return; // Event was already applied previously.
    }

    projectionRepository.apply(event);
}
```

`tryInsert` must rely on a unique constraint and handle conflicts according to the database in use. Do not implement a "SELECT then INSERT" pattern without a unique constraint, because two concurrent consumers can both see no row and both apply the event.

The inbox row and the business change must share the same transaction. If you write the inbox first and process business logic in another transaction, the application could mark an event processed even though the effect never committed. If you update the projection first and write the inbox afterward, a crash between the two steps could apply the effect twice.

## 6. Reconciling Between Outbox, Broker, and Inbox

Outbox shows the producer recorded an event to emit; inbox shows a consumer applied an event. The broker holds messages in topics/queues per retention, subscription, offset, and ACK policies. Reconciliation compares these trails to find gaps.

A reconciliation report can classify outcomes:

| Producer state | Consumer state | Interpretation | Action |
|---|---|---|---|
| Outbox pending overdue | Not in inbox | Relay has not emitted or publish keeps failing | Check relay, broker connectivity, and bounded retries. |
| Outbox published | Not in inbox after wait window | Consumer has not received, is lagging, or message was quarantined | Check lag, group/subscription, DLQ, and retention. |
| Outbox published | Event ID in inbox | Consumer applied it | Verify business state and close. |
| Outbox pending | Event ID in inbox | Likely published, but relay failed to update status | Verify broker; safely update relay state without deleting trail. |
| Multiple deliveries of same event | Single inbox row | Duplicate suppressed by idempotency | Record duplicate metric, do not reapply. |
| Event version N+1 present, N missing | Aggregate gap | Event missing or arrived out of order | Locate event N in outbox, broker retention, or DLQ; controlled replay. |

Do not reconcile solely by total message counts. Two systems can have identical counts while holding different events; conversely, counts can differ temporarily due to normal processing latency. Reconcile by `eventId`, aggregate/version, status, and an explicit grace period.

### 6.1. Periodic Reconciliation Workflow

A reconciliation job can run on a schedule or upon alert triggers:

1. Select a time window old enough to avoid flagging messages currently in flight.
2. Fetch expected events from the outbox or source of truth.
3. Compare against the delivery ledger/inbox of the consumer under inspection.
4. Classify missing events, duplicates, overdue events, and version mismatches.
5. Inspect broker offsets/lag, queue depth, subscription backlog, and DLQs to pinpoint where failure occurred.
6. Create recovery tasks with a unique key per event and consumer.
7. Replay or compensate after verifying root cause.
8. Record reconciliation outcomes, actor/system, and recovery results.

Reconciliation needs bounded time ranges, pagination, and its own checkpoints so it never loads entire historical datasets into memory. For large datasets, shard by date, tenant, aggregate range, or partition.

## 7. Controlled Event Replay

Replay means re-emitting an existing event so a consumer reprocesses it after a bug is fixed or the system recovers. Replay is useful when a consumer was down, a projection lost data, or messages were routed to a DLQ.

Principles for replay:

- Keep the original `eventId` so the inbox recognizes duplicates.
- Keep the original `aggregateId`, `aggregateVersion`, `occurredAt`, and schema version.
- Add separate replay metadata such as `replayId`, `replayedAt`, `replayReason`, `replayedBy`.
- Define the target consumer/group and event range before replaying.
- Rate-limit replay throughput to avoid overwhelming brokers or downstream services.
- Avoid sending replays straight back into the same failing path without preventing repeat loops.
- Log results, replay counts, and approvers if required by business policy.

Example metadata:

```json
{
  "eventId": "evt-01J9M7Q3",
  "replayId": "replay-20261124-001",
  "replayedAt": "2026-11-24T10:00:00Z",
  "replayReason": "projection-rebuild",
  "replayedBy": "reconciliation-job"
}
```

Never generate a new `eventId` just to force a replay. If a consumer already processed the event previously, its inbox will skip it. If the goal is intentionally reapplying data into a new projection, use a new consumer identity or a dedicated inbox namespace for the rebuild after explicitly identifying the target data to recreate.

Replaying an entire topic can cause unintended side effects if consumers send emails, charge cards, or call external APIs. Separate rebuild consumers that only write projections from consumers that trigger external side effects, or enforce idempotency keys at target services.

## 8. Recovering from DLQ and Parking-Lot Destinations

A DLQ stores messages that exceeded retry policies or were routed into an error stream by the broker/consumer. A DLQ does not fix data on its own and does not guarantee messages will be reprocessed. Establish an operational workflow:

1. Collect the message, exception, event ID, binding, group/subscription, and failure timestamp.
2. Classify transient errors, invalid data, incompatible schemas, configuration errors, or business errors.
3. Fix the root cause before replaying; if the payload is invalid, decide between fixing the payload or emitting an adjustment event.
4. Select the messages or range eligible for replay.
5. Replay with rate limiting while preserving the original event ID.
6. Verify the inbox/business target updated without creating duplicate side effects.
7. Record results and close the recovery task.

A parking-lot destination can hold messages that cannot self-recover or require human intervention. Never let a DLQ become an unbounded dumping ground lacking alerts, retention, and an owner.

## 9. Recovering External Service Calls

A database transaction cannot roll back an action already executed at a payment provider, email provider, or shipping system. For instance, the provider already approved a payment before the application lost connectivity prior to recording the result.

Do not immediately issue another payment call as a brand-new request. Instead:

1. Send requests with a stable idempotency key, such as `paymentId` or `commandId`.
2. On timeout, look up transaction status via the idempotency key or the provider's query API.
3. If the provider confirms success, update internal state accordingly.
4. If confirmed not executed, retry with the same idempotency key.
5. If status is indeterminate, hold in a reconciliation-required state instead of guessing success or failure.
6. If a later step cannot complete, execute a compensating action per business rules, such as a refund or releasing reserved inventory.

A Saga structures a multi-step workflow using local transactions and compensating actions. Compensation is not a physical rollback: a refund is a new business transaction, not an erasure of the payment event that already occurred.

## 10. Recovery States and Leases to Prevent Concurrent Duplicate Workers

If multiple instances run reconciliation or replay jobs, persist task state so they do not recover the same event uncontrollably at the same time.

A recovery task can use states such as:

| State | Meaning |
|---|---|
| `DETECTED` | Discrepancy has been detected. |
| `READY` | Verified and eligible for recovery. |
| `IN_PROGRESS` | A worker holds a lease and is processing. |
| `REPLAYED` | Event was re-emitted via the recovery mechanism. |
| `VERIFIED` | Target state verified as accurate. |
| `RETRY_WAIT` | Recovery failed transiently and awaits the next attempt. |
| `MANUAL_REVIEW` | Requires review by an authorized operator. |
| `COMPENSATION_REQUIRED` | Requires a business compensating action. |
| `CLOSED` | Completed with audit trail recorded. |

Workers can claim tasks using time-bounded leases. If a worker stops abruptly, the lease expires so another worker can take over. Use conditional updates/optimistic locking or appropriate database locks so two workers cannot own the same task. Leases do not replace idempotency; an old worker may still be running after its lease expires, so all external effects must still tolerate repetition.

## 11. Broker-Specific Considerations

### Kafka

Kafka stores logs per partition, and consumer groups commit offsets to record read positions. An offset is not proof that business logic committed in a database. If a consumer commits an offset before the database transaction completes, a crash can lose business effects. If it commits after database commit but crashes before the offset is recorded, the message may be redelivered; inbox/idempotency handles the duplicate.

Kafka transactions can coordinate reads and writes across Kafka topics in one Kafka transaction, depending on configuration and binder support. They do not automatically include database transactions or external APIs. For database-to-Kafka, outbox remains the standard choice for coordinating local state and events.

During reconciliation, examine consumer lag, committed offsets, log end offsets, partition assignments, rebalances, and DLQ topics. Never use offsets alone to conclude a projection updated accurately.

### RabbitMQ

RabbitMQ uses ACK/NACK and queues. Unacknowledged messages can be redelivered when a consumer/channel/connection closes. Queue depth, unacked counts, the redelivery flag, and DLX/DLQ are useful signals during investigation. Confirm whether messages are ACKed after database commit and avoid infinite requeue configurations for unrecoverable errors.

Publisher confirms and consumer ACKs are two separate confirmation directions. Confirms tell the producer the broker received the publish under RabbitMQ's confirmation semantics; consumer ACKs tell the broker the message was processed. Never mistake these two signals for a single end-to-end guarantee.

### Pulsar

Pulsar uses subscriptions and acknowledgements. Unacknowledged messages can be redelivered according to subscription type and client/broker policies. Monitor backlog, redeliveries, unacked messages, and dead-letter topics. With `Key_Shared` or `Shared`, ordering and distribution depend on the subscription type; reconcile by event ID/aggregate version rather than assuming global ordering.

Binders have distinct properties for ACKs, retries, DLQs, and transactions. Verify settings against the exact binder/client version running; do not copy Kafka configuration verbatim to RabbitMQ or Pulsar.

## 12. Why Can't You Rely on Exactly-Once Alone?

Brokers can provide delivery guarantees or transactions within a defined scope. However, a business workflow typically involves multiple independent resources: brokers, databases, caches, and external APIs. "Exactly once" inside one boundary does not automatically extend to once across the entire chain.

For example, a Kafka transaction can guarantee Kafka records commit together inside a Kafka transaction, yet cannot automatically roll back a PostgreSQL write. A RabbitMQ publisher confirm does not prove a consumer committed its database. A Pulsar acknowledgement does not automatically guarantee an external API was called only once.

Practical architectures typically combine:

- At-least-once delivery at the broker boundary.
- Outbox so events are never lost after database transactions.
- Inbox/idempotency to eliminate duplicate effects at the consumer.
- Versions/sequences to detect missing or out-of-order events.
- Reconciliation to uncover remaining discrepancies.
- Compensation for business steps that cannot be rolled back.

## 13. Testing Partial Failures and Recovery

Testing only the happy path is insufficient to prove reliability. Deliberately inject failures between steps:

| Fault injection point | Scenario | Expected outcome |
|---|---|---|
| Before database commit | Stop service after staging order/outbox | Both roll back; no orphaned event. |
| After database commit, before relay publish | Stop relay | Outbox stays pending and is sent after relay recovers. |
| After broker publish, before mark published | Stop relay | Duplicate publish may occur; consumer inbox applies only once. |
| After consumer DB commit, before ACK | Kill consumer | Broker may redeliver; inbox prevents repeated effects. |
| Before consumer DB commit | Throw exception | Transaction rolls back; message is retried/redelivered per config. |
| External API succeeds but response times out | Simulate lost response | Look up via idempotency key; no duplicate external effect. |
| One destination publish succeeds, another fails | Inject per-target error | Delivery ledger retains per-target state and retries only the failed target. |
| Replay same event multiple times | Resend old event ID | Inbox/idempotency keeps business outcome unchanged. |
| Reconciliation worker stops while holding task | Kill process | Lease expires and another worker takes over safely. |

Spring Cloud Stream Test Binder can be used to test functions/bindings and message logic inside the JVM. For real ACKs, offsets, publisher confirms, redeliveries, DLQs, and transactions, run integration tests against Kafka/RabbitMQ/Pulsar accordingly. Include recovery tests for restarts, network partitions, and temporary broker outages.

## 14. Observability and Alerting for Reconciliation

A reconciliation process needs metrics to surface discrepancies before users report errors:

- Pending outbox row count and age of the oldest pending row.
- Failed publish count, retry count, and time from event creation to publish.
- Consumer lag/backlog by destination and group/subscription.
- Counts of events detected as missing, duplicate, version-mismatched, or overdue.
- Count of inbox duplicates skipped.
- Message counts in DLQ/parking lot and age of oldest message.
- Recovery task counts by status, replay counts, and recovery success rate.
- Pending compensation counts and unresolved duration.

Metric tags should have low cardinality such as `destination`, `consumer`, `eventType`, or `result`. Put `eventId`, `aggregateId`, and `correlationId` in structured logs or traces rather than placing millions of individual IDs into metric labels.

Each recovery task should record detection reason, before/after data, action taken, timestamp, and worker identity. This enables auditing and prevents an automated job from modifying data without an explainable trail later.

## 15. End-to-End Reconciliation and Recovery Workflow

An operational workflow can be structured into these steps:

1. **Identify source of truth:** select the authoritative system for the business state under inspection.
2. **Establish trails:** ensure events carry stable IDs, aggregate versions, correlation IDs, and outbox/inbox states.
3. **Detect discrepancies:** compare expected events against the delivery ledger/inbox after a grace period.
4. **Isolate:** inspect relays, brokers, consumer lag, ACKs/offsets, DLQs, and logs by event ID.
5. **Classify:** transient error, malformed data/schema, missing event, duplicate, out-of-order, or indeterminate external effect.
6. **Choose action:** retry, replay, rebuild projection, controlled data repair, or compensation.
7. **Bound impact:** apply idempotency, leases, rate limits, and an explicit replay scope.
8. **Verify post-recovery:** verify state in both the source of truth and target system, not merely that a message was published.
9. **Close recovery task:** save results, metrics, and audit trail.
10. **Prevent recurrence:** add failure tests, alerts, or design fixes at the boundary that failed.

## 16. Reliability Design Checklist

Before promoting a Spring Cloud Stream pipeline to production, verify:

1. Do the database update and outbox event share the same transaction?
2. Can the relay resend after a crash without losing events?
3. Are event IDs stable across retries and replays?
4. Do consumers have an inbox or idempotency keys protecting business effects?
5. Do the inbox row and business changes share the same transaction?
6. Are ACKs/offsets confirmed only after business effects are durable?
7. Are aggregate versions/sequences present to detect gaps and out-of-order arrivals?
8. Does reconciliation define a source of truth and grace period?
9. Does the DLQ have an owner, retention, alerts, and a redrive procedure?
10. Are replays rate-limited, preserving event IDs, and avoiding duplicate side effects?
11. Do external APIs have idempotency keys or status-query mechanisms?
12. Do non-rollbackable steps have explicit compensating actions?
13. Are crashes tested at every commit/publish/ACK boundary?
14. Are metrics, logs, traces, and audit trails in place to detect and explain discrepancies?

Reconciliation does not replace getting delivery design right from the start; it is the detection and recovery layer for discrepancies that can still arise in distributed systems. Combining outbox, inbox, idempotency, versioning, controlled replay, and compensation enables a Spring Cloud Stream application to preserve business consistency even when only part of the processing chain succeeds.
