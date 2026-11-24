# Do Not Equate Exactly Once with Absolute Zero Duplicates

In a Spring Kafka system, the phrase **exactly-once semantics (EOS)** describes a guarantee on processing outcomes within a defined transactional scope. It does not mean an event is never sent again, a listener never reruns, or two identical messages never appear anywhere in the system.

To design operations properly, distinguish three phenomena:

1. **Duplicate delivery:** the same record is received or reprocessed by a consumer, usually due to retries, rebalances, or uncommitted offsets.
2. **Duplicate record:** the same business event is written by a producer as multiple Kafka records, such as when an application resends a command after a timeout or during a replay.
3. **Duplicate side effect:** an action such as charging money, creating an order, or sending an email happens multiple times for the same event.

These three phenomena are related yet not synonymous. A consumer can receive a record multiple times while updating the database only once thanks to idempotency. Conversely, a producer can write two records at different offsets for the same `eventId`; Kafka still treats them as two valid records even though their contents match.

## 1. What Does Exactly-Once Actually Guarantee?

Kafka provides idempotent producer and transaction mechanisms to build processing flows with exactly-once semantics within Kafka's scope. The canonical case is **consume-process-produce**: an application reads a record from an input topic, processes it, writes output records to another topic, and commits the input offset within the same Kafka transaction.

When the transaction commits, the output records and input offset take effect together. When the transaction aborts, output records from that transaction are not visible to consumers using `read_committed`, and the input offset does not advance as a successful transaction. Thus, if the application restarts after a failure, the input record can be reprocessed in a fresh attempt while only committed transaction outcomes are exposed to consumers reading with the proper isolation level.

This is a guarantee about **committed and observable outcomes inside Kafka**, not a promise that business code executes only once. A listener can be invoked again after a transaction aborts. Side effects outside Kafka are also not automatically part of that transaction.

Example: service `order-enricher` reads `orders.raw`, enriches data, and writes to `orders.enriched`. If output and offset commit in the same transaction, `read_committed` consumers of `orders.enriched` observe only outputs from committed transactions. If the application dies before commit, that processing run can rerun; output from the aborted transaction never becomes a committed result.

### 1.1. Scope of Guarantees

| Scope | What can Kafka guarantee? | What still must be handled in the application |
|---|---|---|
| Producer retries within the same producer session with idempotence | Kafka tracks producer sequence numbers to eliminate duplicate writes from protocol retries | A client resending the same business command as a fresh send can still create a new record |
| Writing multiple Kafka records in one transaction | Records in the transaction commit or abort together | Code before/after the transaction can rerun; non-Kafka services do not automatically join the transaction |
| Consume-process-produce in a Kafka transaction | Input offset and Kafka outputs can commit atomically | Listener can be invoked again; database, HTTP, and email side effects need separate mechanisms |
| Consumers using `read_committed` | Reads only records from committed transactions, skipping aborted transaction records | Consumers can still receive the same committed record again if offsets/processing restart at an earlier position |
| Replay or backfill | Kafka allows rereading data by offset or rewriting data into topics | Replays can repeat business side effects if consumers are not idempotent |

Therefore, when stating a flow has exactly-once, specify inputs, outputs, transaction boundaries, isolation levels, and which side effects are covered. Do not use this phrase as a blanket claim for an entire distributed system.

## 2. Distinguishing Mechanisms Often Lumped Together as Exactly Once

### 2.1. Idempotent Producer

An idempotent producer prevents duplicates caused by retries at the Kafka protocol layer. Kafka attaches a producer ID and sequence numbers to batches. If the producer must resend a batch after receiving no response, the broker recognizes the already-processed sequence and avoids writing the batch a second time.

In Spring Kafka, idempotence can be enabled directly:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
```

When using Kafka transactions, idempotence is part of the transactional producer mechanism. For non-transactional producers, ensure compatible settings per your Kafka client version; `acks=all`, retries, and in-flight request limits must meet idempotent producer requirements. Modern Kafka clients may automatically enable compatible defaults when idempotence is allowed, yet production configurations should be verified explicitly.

Idempotence does not deduplicate two independent send commands. For example, an API receives an order-creation request, sends the event to Kafka successfully, and times out before returning a response. The caller does not know the first attempt succeeded and retries the request. If the application issues a new producer send for the second request, Kafka can write two records at different offsets. Use a stable `requestId`, `orderId`, or `eventId` and check duplicates at the business layer.

### 2.2. Kafka Transactions

Kafka transactions group multiple Kafka operations into a single commit/abort unit. For consume-process-produce flows, Spring Kafka can use listener container transactions to send outputs and include the input offset in the same transaction. Downstream consumers must set `isolation.level=read_committed` if they must see only committed results.

Example baseline properties in Spring Boot:

```properties
spring.kafka.producer.transaction-id-prefix=${INSTANCE_ID:local}-orders-
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.properties[isolation.level]=read_committed
```

`transaction-id-prefix` must be unique across application instances running concurrently in the same Kafka environment. The example uses `INSTANCE_ID` for illustration; in actual deployments, provide a stable, unique identifier per instance or instance group according to your deployment model. Spring Kafka uses the prefix to create transactional producers with distinct suffixes. If multiple instances share the same prefix, they can fence each other's producers and fail transactions.

When enabling transactions on a listener container, ensure the container actually uses the appropriate Kafka transaction manager and that output sends run inside the active transaction. Merely configuring a transaction-capable `KafkaTemplate` while letting the listener run without a transaction does not create consume-process-produce atomicity.

Key points to remember:

- The processed record's offset must be sent into the Kafka transaction alongside outputs.
- Downstream consumers need `read_committed` so they do not read uncommitted or aborted outputs.
- Transactions have a timeout; overly long processing can cause brokers to abort the transaction.
- Transactional IDs must be managed uniquely to prevent unintended fencing.
- A Kafka transaction covers only operations executed inside that Kafka transaction.

### 2.3. Consumer Idempotency

Consumer idempotency is the ability to apply the same event multiple times while changing the business outcome only once. This is a critical defense layer because at-least-once delivery and retries can still cause handlers to rerun.

For instance, when handling `PaymentCaptured`, the consumer inserts `eventId` into an inbox table with a unique constraint and updates payment status in the same database transaction. If the same event arrives again, the insert hits a duplicate key and the consumer skips the already-applied side effect.

```sql
BEGIN;

INSERT INTO processed_event (event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Update business data only when INSERT just created a new row.
-- Check the number of inserted rows in the application.
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = :payment_id;

COMMIT;
```

This SQL snippet illustrates the idea; the application must check the insert row count and run `UPDATE` only when the new event ID was recorded. Both operations must sit in the same database transaction. If the event ID already exists, finish the transaction without repeating side effects. If the business update fails, recording the event ID must roll back too so a later attempt can retry.

Consumer idempotency protects business outcomes even when Kafka redelivers records. It does not necessarily prevent duplicate records from appearing in a topic or prevent a listener from being invoked multiple times.

## 3. Why Do Duplicates Still Appear in Systems with Exactly-Once?

### 3.1. Timeouts Produce Uncertain Outcomes

A timeout does not prove the server-side operation failed. The producer may have sent the record and the broker may have committed it, while the response was lost on the return path. On the client side, the state is ambiguous: did the operation succeed or not?

If the application issues a new send request with a new producer sequence, the broker cannot infer that the two requests represent the same business action. An idempotent producer primarily handles retries of the same producer protocol session, whereas deduplicating business requests requires a stable idempotency key.

### 3.2. Consumer Finishes Processing Before Offset Commit

In an at-least-once model, consumers usually complete side effects before committing offsets. If the database commits yet the consumer dies before Kafka records the new offset, Kafka redelivers the record. This is proper behavior to avoid losing data, though side effects can repeat if the handler is not idempotent.

Example sequence:

```text
1. Consumer reads record at offset 120.
2. Consumer updates database successfully.
3. Process stops before committing offset 121.
4. Consumer restarts and rereads offset 120.
5. Handler runs again.
```

Without an inbox or unique business key in the database, the application could create two business transactions for the same record. With an idempotent consumer, the second run recognizes the event ID is already complete and does not repeat the effect.

### 3.3. Callers Retry Business Requests

A REST client, scheduler, or upstream service may resend the same command when it receives no response. If the producer generates a new event ID each time a request arrives, business duplicates occur even with producer idempotence enabled.

The solution is having callers supply an idempotency key or having the system generate/look up a stable business operation ID before emitting events. All retries of the same operation must share the same ID. If the system has no way to tell that two requests share the same intent, it cannot deduplicate reliably from payload content alone.

### 3.4. Retry Topics, DLTs, and Replays

Retry topics can move records to another topic to retry after a delay. When a record is moved, the original record and the retry record are distinct Kafka records. One business operation can therefore appear in multiple topics or be executed again by a listener.

A DLT holds records that remain unprocessable after the retry policy. When operating DLT replays, operators may resend records back to the main topic. If a record already produced partial side effects before failing, replaying it can repeat those partial side effects.

Replaying from an older offset, restoring a consumer group, running a backfill, or migrating clusters can also re-emit already-processed events. Clarify what a replay represents:

- **Reprocessing to rebuild state:** side effects must target an isolated destination environment or follow a state-replacement strategy.
- **Retrying an incomplete event:** keep the old event ID and rely on an idempotent consumer to finish the missing work.
- **Re-emitting as a new event:** generate a new event ID only when business logic genuinely defines a new action.

Do not automatically replace event IDs during replay just to bypass unique constraints; doing so disables deduplication.

### 3.5. Side Effects Outside Kafka

A Kafka transaction does not automatically include operations such as:

- Writing or updating a relational database.
- Calling a REST API or RPC on another service.
- Sending email, SMS, or push notifications.
- Writing files to object storage.
- Calling a payment gateway or accounting system.

If a listener calls a payment API and then the Kafka transaction aborts, the next processing attempt may call the API again. If a listener commits to a database and the offset remains uncommitted, the record can be redelivered. These are failure windows between two independent systems.

For external side effects, use idempotency keys supported by the target system, inbox/outbox, unique constraints, or an explicitly designed distributed protocol. Never infer that setting `transaction-id-prefix` makes database and Kafka commit atomically together.

## 4. Choosing Delivery Semantics by Stream Type

Three commonly cited models are at-most-once, at-least-once, and exactly-once semantics. Each has distinct trade-offs.

| Model | Characteristics | Main risk | Appropriate use cases |
|---|---|---|---|
| At-most-once | Offsets may be committed before processing completes; records are not redelivered after failures in some cases | Processing effects may be lost | Metrics or signals that can tolerate dropping samples; do not use for critical business events if data loss is unacceptable |
| At-least-once | Commit only after processing finishes; records may be redelivered | Duplicate processing may occur | Business flows with idempotent consumers, database inboxes, or downstream idempotency support |
| Kafka EOS | Input offset and Kafka outputs sit in the same transaction; `read_committed` consumers observe committed results | Listeners can still rerun; external side effects outside Kafka are not covered | Consume-transform-produce pipelines between Kafka topics |

Do not pick at-most-once merely to avoid duplicates if losing an event has serious consequences. In many business systems, at-least-once combined with an idempotent consumer delivers much safer recovery behavior: records can be redelivered while business outcomes stay consistent.

## 5. Designing Spring Kafka Flows by Transaction Boundary

### 5.1. Kafka-to-Kafka

For pipelines that only read from Kafka, transform, and write to Kafka, use listener container transactions to combine outputs with input offsets. Verify the consumer group does not auto-commit offsets independently, the output producer participates in the transaction, and target consumers use `read_committed`.

Logical diagram:

```text
Input topic
    |
    v
Spring Kafka listener
    |
    +---- transform / validate
    |
    v
Kafka transaction
    |                 |
    |                 +---- commit input offset
    +---- write output topic
    |
    v
Commit transaction
    |
    v
Downstream read_committed consumer
```

If processing fails, the transaction aborts and the input offset is not committed alongside outputs. When the container retries or a consumer rereads the record, the application can rerun the logic. Transformation functions should avoid side effects outside the transaction; if side effects exist, provide separate idempotency.

### 5.2. Kafka-to-database

When a consumer updates a database, Kafka offsets and database commits are two separate operations unless a specialized distributed solution is used. The standard pattern is at-least-once plus inbox:

```text
Kafka record
    |
    v
Spring Kafka listener
    |
    v
Database transaction
    |-- insert eventId into inbox (unique)
    |-- apply business update if eventId is new
    |
    v
Database commit
    |
    v
Kafka offset commit
```

If the database commit succeeds yet the offset commit fails, the record is redelivered; the inbox sees the event ID already exists and skips applying the update again. If the database transaction rolls back, both the inbox row and business update roll back together; redelivery can process normally.

Never insert the event ID into the inbox in an independent transaction before updating business data. If the process stops between the two operations, the inbox claims the event was processed while business data never changed; subsequent retries could then skip it erroneously.

### 5.3. Database-to-Kafka

When an application updates a database and emits events, the transactional outbox pattern closes the gap between the two operations:

1. In one database transaction, update business data and insert an outbox row with a stable event ID.
2. A relay reads the outbox and publishes to Kafka.
3. The relay marks the outbox row sent after receiving proper acknowledgement.
4. Downstream consumers use an inbox or idempotency key to prevent duplicate processing.

If the relay publishes successfully yet stops before marking the outbox, the relay may publish the same event again. Thus outbox prevents losing events across the database-write and publish window, while Kafka records can still repeat. Idempotent consumers complete the end-to-end design.

## 6. Event Identity and Deduplication Strategies

A system that handles duplicates safely needs stable event identifiers, unique within the business scope. Example:

```json
{
  "eventId": "evt-8f2a...",
  "eventType": "PaymentCaptured",
  "aggregateId": "payment-2048",
  "occurredAt": "2026-11-15T10:20:30Z",
  "schemaVersion": 2
}
```

`eventId` uniquely identifies one event; `aggregateId` is commonly used as the Kafka key to keep ordering for the same aggregate; `schemaVersion` helps consumers handle schema changes. Do not rely solely on payload hashes as identifiers if two independent events can share identical payloads or the same event can be serialized differently.

Options for storing deduplication state:

- **Inbox table in the database:** fits when primary side effects live in the same database. Use a unique constraint on event ID and write the inbox in the business transaction.
- **Idempotency key at the target service:** fits when calling payment gateways or APIs supporting keys. Pass the same key on every retry of the same action.
- **Unique business constraint:** fits when the data model inherently has a unique key such as `orderId` or `invoiceNumber`.
- **State store or cache with TTL:** usable for short-term deduplication or streams with strict time bounds; evaluate eviction, restarts, consistency, and retention windows.

Deduplication state must be retained at least as long as retries, replays, recoveries, or event redeliveries can occur. If you purge the inbox after one day while DLTs can replay after one week, old duplicates can cause fresh side effects. For financial workflows or auditable data, event ID history may need long-term retention per data policy.

## 7. Processing Order and Duplicates

Kafka preserves order within a single partition, without creating a global order across multiple partitions. The same key typically maps to the same partition, helping maintain event ordering for an aggregate when partitioning stays stable.

Duplicates and ordering are two separate concerns:

- Deduplication can drop an already-applied event, but cannot by itself fix the order of two distinct events.
- Retry topics can cause a failed record to be processed after a subsequent record, changing business order.
- Adding partitions or changing partitioners can redistribute keys differently over time, affecting ordering.
- A consumer group can process partitions concurrently; order is guaranteed only within each partition.

If business logic demands strict ordering per order or account, use an appropriate key, keep state transitions in the same partition, and design retries so later events cannot jump ahead of earlier ones when that violates business rules. Deduplication must be paired with aggregate version/sequence checks if events can arrive out of order.

## 8. Operating and Observing Duplicates

No single metric proves a system has zero duplicates. Measure at each layer:

| Layer | Signals to collect | What to investigate |
|---|---|---|
| Producer | Retry rate, timeouts, delivery failures, duplicate event IDs in request logs | Caller retries, ambiguous timeouts, producer restarts |
| Kafka | Transaction abort rate, producer fencing, request errors, consumer lag | Transaction timeouts, conflicting transactional IDs, broker errors |
| Consumer | Records received, new event IDs, seen event IDs, handler retries, commit failures | Redeliveries, rebalances, stalled offsets |
| Database | Unique constraint conflicts, inbox duplicate counts, updates skipped by idempotency | Duplicate deliveries or replays; verify whether behavior is expected |
| Business | Duplicate transactions, side effect counts per business ID, reconciliation results | Deduplication bugs, unstable event IDs, side effects outside transactions |

Logs should include `eventId`, `correlationId`, topic, partition, offset, consumer group, and attempt number where available. Avoid logging full sensitive payloads merely to investigate duplicates. Duplicate metrics should distinguish redelivered records safely skipped from actual duplicated business effects.

Useful alerts:

- Spikes in transaction aborts or producer fencing.
- Sustained increases in consumer commit failures or rebalances.
- Abnormal increases in inbox unique conflicts after deployments or replays.
- Spikes in DLT/retry topic volume.
- Multiple side effects recorded for a single business ID in target systems.

Duplicate delivery can be a normal part of at-least-once. Alerts should focus on abnormal rates, business impact, and signs that idempotency is failing.

## 9. Testing Failure Windows

Testing exactly-once and idempotency requires intentionally stopping the application at points that create ambiguous states. Practical scenarios include:

1. Stop the producer after the broker receives the record but before the application receives the response.
2. Resend the same request ID from a caller after a timeout.
3. Stop the consumer after the database commit but before the Kafka offset commit.
4. Make the listener throw an exception after sending output inside a Kafka transaction, and verify the transaction aborts.
5. Stop the outbox relay after publishing to Kafka but before marking the outbox entry sent.
6. Replay the same event ID from a DLT or older offset.
7. Trigger a rebalance while the consumer is processing a batch.
8. Start two instances with overlapping transactional ID prefixes to verify fencing alerts and proper configuration procedures.

For each scenario, inspect all three layers: Kafka record count, handler invocation count, and final business side-effect count. A test that only counts how many times the listener ran would wrongly conclude the system is not exactly-once if the handler retried after an aborted transaction while the final outcome committed only once.

Reconcile using event IDs and business keys. Verify each event ID produces only one business outcome, while independent events are not mistakenly merged merely because their payloads match. Record results across process restarts, retries, replays, and failovers.

## 10. Precise Phrasing in Design and Operations

When describing a flow, use specific, scoped statements:

- "The flow reads topic A, writes topic B, and commits the input offset in the same Kafka transaction; consumers of B use `read_committed`."
- "The producer enables idempotence to eliminate duplicates from protocol retries within a producer session."
- "The consumer processes at-least-once and uses an inbox table with a unique event ID to keep database effects idempotent."
- "The outbox relay may publish duplicates if stopped after publishing; target consumers deduplicate by event ID."
- "DLT replays preserve original event IDs and run through a reconciled procedure."

Avoid absolute statements such as "Kafka guarantees zero duplicates ever", "listeners execute only once", or "enabling exactly-once protects the database and external APIs too". Those claims ignore retries, timeouts, redeliveries, replays, and transaction boundaries.

A reliable design typically combines layers: an idempotent producer reduces protocol-retry duplicates; Kafka transactions protect atomicity of Kafka offsets and outputs; consumer inboxes or idempotency keys protect side effects; outbox protects emitting events from databases; replay and reconciliation workflows govern redeliveries. Each layer closes a specific failure window.

## 11. Selection and Operational Criteria

Before claiming a Spring Kafka flow has exactly-once semantics, the team should answer:

1. Which operation does exactly-once apply to: producer retries, Kafka transactions, or final business effects?
2. Are input offsets and Kafka outputs inside the same transaction?
3. Do downstream consumers use `read_committed`?
4. Is the transactional ID prefix unique across instances, and is the transaction timeout compatible with processing duration?
5. Are there external side effects outside Kafka in the listener? How do they use idempotency keys, inbox, or outbox?
6. Can callers retry the same request? Does the operation ID stay stable across retries?
7. Do DLT, retry topics, replays, and backfills preserve event IDs and have a reconciliation workflow?
8. Does deduplication state retention cover topic retention and recovery/replay windows?
9. Have crash points between side effects and offset commits been tested?
10. Do dashboards distinguish duplicate deliveries, duplicate records, and duplicate side effects?

Exactly-once is a valuable guarantee when placed within its true boundaries. The practical operational goal is keeping business outcomes accurate across retries, restarts, rebalances, timeouts, replays, and failovers. That requires clearly defining which transactions Kafka protects, which side effects require idempotency, and how the system detects and handles remaining duplicates.
