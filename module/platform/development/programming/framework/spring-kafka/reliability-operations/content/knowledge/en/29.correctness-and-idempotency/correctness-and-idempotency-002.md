# Idempotent consumer

## 1. What is an idempotent consumer?

An **idempotent consumer** is a consumer designed so that when it receives the same message multiple times, the final business outcome remains equivalent to the message being applied only once.

In Kafka, a consumer can receive a record again due to retries, rebalances, process crashes, or uncommitted offsets. This is normal behavior in the **at-least-once delivery** model. Therefore, a reliable listener must account for duplicate delivery even when the producer and broker are operating properly.

For example, the topic orders.paid contains an event:

~~~json
{
  "eventId": "evt-8f21",
  "orderId": "order-1042",
  "amount": 125000,
  "currency": "VND"
}
~~~

If the listener increments the order's collected amount by 125,000 VND every time it receives the event, a duplicate will record the amount twice. If the listener uses eventId to ensure the event is applied only once in the database, redelivery can be recognized and skipped.

~~~text
Kafka record evt-8f21
        |
        v
Consumer receives record
        |
        v
Check idempotency / inbox
        |
    +---+----------------------+
    |                          |
 First processing          Duplicate
    |                          |
    v                          v
Apply business effect       Skip effect
    |                          |
    v                          |
Commit DB transaction          |
    |                          |
    +-------------+------------+
                  |
                  v
       Listener completes
                  |
                  v
       Kafka offset advances
~~~

Idempotency does not mean Kafka will never deliver duplicates. It means the application handles duplicates safely.

## 2. Why can Kafka redeliver a record?

Kafka stores offsets per consumer group and partition. A consumer can only resume from the committed position after a process restart or when a partition is assigned to another consumer.

A common failure window:

~~~text
1. Consumer reads offset 120
2. Listener writes to database successfully
3. Process crashes before Kafka offset 121 is committed
4. New consumer receives the partition
5. Kafka redelivers offset 120
~~~

The database already has the side effect from the first attempt. Kafka does not yet know that work finished, so the record can be redelivered.

Other causes:

- Listener throws an exception and the error handler retries.
- Consumer exceeds max.poll.interval.ms and triggers a group rebalance.
- Pod is killed or node restarts.
- Network interruption leaves the consumer uncertain whether the commit completed.
- Manual acknowledgment was not called.
- A batch is partially processed and then fails.
- Operator replays offsets or republishes messages.
- DLT records are routed back to the main topic.

Duplicate delivery is not necessarily a bug. It is a scenario that must be handled by design.

## 3. Idempotency from a business perspective

An idempotent operation has the property:

~~~text
f(f(state, event), event) = f(state, event)
~~~

In other words, applying the same event a second time does not change the final outcome a second time.

Examples of idempotent operations:

- Setting order status to PAID if the event confirms the right order.
- Setting the shipping address to a new versioned value.
- Recording a processed eventId with a unique constraint.
- Upserting a projection by entity ID and version.

Examples that are non-idempotent if executed repeatedly:

- Increasing a balance by 100,000 VND.
- Decrementing inventory by 1 unit.
- Sending a confirmation email on every record receipt.
- Creating a new shipment on each invocation.
- Adding loyalty points every time the event is processed.

You cannot look solely at a function name like updateOrder() and conclude it is idempotent. You must inspect the actual side effects and the before/after state when the event is applied.

## 4. Distinguishing message ID, key, and offset

To recognize duplicates, the consumer needs a **stable idempotency key** representing a single business emission.

| Value | Role | Should it be the idempotency key? |
|---|---|---|
| eventId/messageId | Unique ID of the event per producer contract | Usually a good choice |
| Kafka key | Partitioning or entity routing key | Only when semantics guarantee suitability |
| Topic + partition + offset | Physical position of the record | Can identify the same Kafka record, insufficient for republishing |
| correlationId | Links a business flow | Usually no, because one flow has multiple events |
| orderId | Identifies a business entity | No if an order has multiple valid events |
| requestId | Identifies a request | Only if each request produces exactly one logical effect |

**Offset is not event identity.** When the same event is republished to a topic, it may receive a new offset. If you deduplicate by topic-partition-offset, the republished record will still be treated as a new record.

**Correlation ID is not event ID.** An order flow may emit OrderCreated, PaymentAuthorized, and OrderShipped with the same correlation ID. Deduplicating everything by correlation ID would drop valid events.

### 4.1. Event ID must remain stable across retries

The producer should generate eventId once when creating the logical event, and preserve that ID across publish retries or republishes of the same event.

If the producer generates a new UUID each time it resends the same business event, the consumer cannot tell that the two records are the same logical event using eventId alone.

## 5. Idempotent producer does not replace idempotent consumer

Kafka producer has an idempotence mechanism, enabled via enable.idempotence=true in corresponding configurations. This helps the broker detect and eliminate certain duplicate sends caused by producer retries in the protocol, based on producer identity and sequence numbers.

It does not automatically solve all business duplicates:

- The application calls send twice for the same event creating two separate records.
- Two independent producer instances emit the same logical event.
- An outbox relay republishes after an uncertain outcome.
- A consumer processes a record and crashes before committing the offset.
- An operator replays or a DLT republishes an event.

| Mechanism | What does it protect? |
|---|---|
| Producer idempotence | Duplicates from producer protocol retries within Kafka's supported scope |
| Consumer deduplication | Same logical event does not repeat side effects in the consumer |
| Kafka transactions | Atomicity for Kafka operations included in the transaction |
| Database transaction | Atomicity between inbox/dedup marker and DB business changes |
| API idempotency key | External service recognizes repeated requests |

A reliable pipeline may require multiple layers from this table.

## 6. Common pattern: Inbox table

The **Inbox pattern** stores a record of processed events within the same database transaction as the business side effect.

The inbox table has a unique constraint scoped to the consumer/handler and event ID:

~~~sql
CREATE TABLE processed_message (
    handler_name  VARCHAR(120) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    payload_hash  VARCHAR(64),
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (handler_name, event_id)
);
~~~

handler_name separates independent consumer effects. The same event can be processed once by the order projection and once by the analytics projection; you should not deduplicate system-wide by a single event ID without defining scope.

If eventId is guaranteed globally unique, the schema can be simpler. If the ID is only unique within a tenant or producer, include producer/tenant identity in the unique key.

### 6.1. Why is a unique constraint needed?

Two consumer invocations can simultaneously receive the same event due to retry/rebalance or a replay flow. A SELECT followed by an INSERT is not safe enough:

~~~text
Thread A: SELECT -> no row
Thread B: SELECT -> no row
Thread A: INSERT
Thread B: INSERT
~~~

Both threads can pass the check. A database unique constraint is the final synchronization arbiter ensuring only one transaction wins the right to process the event within that scope.

Do not use a boolean or set in JVM memory as a dedup store. It is lost on process restart and is not shared across replicas.

## 7. Processing inbox and business update in the same transaction

The most important rule:

**Recording that the event was received and applying the business side effect must happen in the same database transaction.**

If the inbox marker commits first and then the business update fails, subsequent retries may treat the event as a duplicate and skip it even though the business operation never completed.

If the business update commits first and then the inbox marker fails, redelivery can apply the side effect a second time.

~~~text
BEGIN DB TRANSACTION
      |
      v
Insert inbox key (handler, eventId)
      |
      +-- Unique conflict --> Duplicate: do not apply effect
      |
      +-- Inserted
              |
              v
       Apply business update
              |
              v
          COMMIT
~~~

If the business update errors, the transaction rolls back both the inbox row and the business changes. Redelivery can retry the whole operation.

### 7.1. PostgreSQL example

Idempotent insert statement:

~~~sql
INSERT INTO processed_message (
    handler_name,
    event_id,
    payload_hash
)
VALUES (
    :handlerName,
    :eventId,
    :payloadHash
)
ON CONFLICT (handler_name, event_id) DO NOTHING;
~~~

PostgreSQL returns the number of affected rows:

- 1: this transaction just claimed the event key.
- 0: the key already existed, so the event is treated as a duplicate in that scope.

This is PostgreSQL syntax. For MySQL, SQL Server, or Oracle, use the corresponding upsert/insert-if-absent syntax and verify the concurrency/row-count semantics of that specific database.

### 7.2. Spring Data JPA repository example

~~~java
public interface ProcessedMessageRepository
        extends Repository<ProcessedMessage, ProcessedMessageId> {

    @Modifying
    @Query(value = """
        INSERT INTO processed_message (
            handler_name,
            event_id,
            payload_hash
        )
        VALUES (
            :handlerName,
            :eventId,
            :payloadHash
        )
        ON CONFLICT (handler_name, event_id) DO NOTHING
        """, nativeQuery = true)
    int insertIfAbsent(
        @Param("handlerName") String handlerName,
        @Param("eventId") String eventId,
        @Param("payloadHash") String payloadHash
    );
}
~~~

This example assumes Spring Data JPA and PostgreSQL. The repository method must run within the transaction wrapping the business update.

### 7.3. Idempotent processing service

~~~java
@Service
public class OrderPaidHandler {

    private static final String HANDLER = "order-paid-projection-v1";

    private final ProcessedMessageRepository processedMessages;
    private final OrderRepository orders;

    public OrderPaidHandler(
            ProcessedMessageRepository processedMessages,
            OrderRepository orders) {
        this.processedMessages = processedMessages;
        this.orders = orders;
    }

    @Transactional
    public ProcessingResult handle(OrderPaid event) {
        int inserted = processedMessages.insertIfAbsent(
            HANDLER,
            event.eventId(),
            event.payloadHash()
        );

        if (inserted == 0) {
            return ProcessingResult.DUPLICATE;
        }

        orders.markPaid(
            event.orderId(),
            event.paymentId(),
            event.amount()
        );

        return ProcessingResult.PROCESSED;
    }
}
~~~

The listener simply calls the service:

~~~java
@KafkaListener(
    topics = "orders.paid",
    groupId = "order-fulfillment"
)
public void consume(OrderPaid event) {
    ProcessingResult result = orderPaidHandler.handle(event);
    log.debug("OrderPaid outcome={}", result);
}
~~~

Calling the service through the Spring bean proxy allows the transaction interceptor to operate. Avoid self-invocation within the same bean while assuming @Transactional will always apply.

When the service returns, the DB transaction has either committed or thrown an exception. Only then does the container proceed to complete the listener invocation per the configured acknowledgment mode.

## 8. Failure window: DB committed but Kafka offset uncommitted

This is the scenario the inbox pattern handles:

~~~text
Consumer reads event evt-8f21
          |
          v
DB transaction:
  insert processed_message(evt-8f21)
  update order -> PAID
  COMMIT
          |
          v
Process crashes
          |
          X Kafka offset not committed
          |
          v
Kafka redelivers evt-8f21
          |
          v
INSERT conflicts with inbox key
          |
          v
Skip business update
          |
          v
Listener completes; offset advances
~~~

The side effect is applied only once in the database, even though the listener is invoked multiple times.

This is why **the inbox marker must commit together with the business update**. Otherwise, a crash between the two steps leaves an inconsistent state.

### 8.1. Can the listener return before DB commit?

If @Transactional is placed on a separate service and the transaction commits before the service method returns through the proxy, the listener only continues after the DB transaction ends.

If a transaction is opened at a different boundary, you must verify the actual execution order. Never allow the container to commit the Kafka offset before the DB side effect has successfully committed.

## 9. Why not just use SELECT then INSERT?

The following code pattern has a race condition:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedMessage(event.eventId()));
    orderRepository.markPaid(event.orderId());
}
~~~

Two concurrent invocations can both observe that the event does not yet exist and both execute the side effect.

The right approach is an insert-if-absent operation backed by a unique constraint, letting the database decide which transaction wins the key.

If the database raises a unique violation instead of returning a row count, you can catch the exception per the database's semantics, keeping in mind that many ORMs mark the transaction rollback-only after a constraint violation. An ON CONFLICT DO NOTHING or equivalent upsert statement is usually easier to control.

Do not catch every DataIntegrityViolationException and assume it is a duplicate: other constraint errors may indicate data corruption that must be surfaced.

## 10. Duplicate event with different payload

If the same eventId appears with a different payload, it may indicate a producer bug or ID reuse.

~~~text
eventId=evt-8f21, orderId=1042, amount=125000
eventId=evt-8f21, orderId=2099, amount=990000
~~~

The inbox unique key will detect the second copy as a duplicate and may skip it. However, this is not a normal duplicate: the same ID represents two different contents.

Store payload_hash or a canonical checksum of the business payload for comparison. On duplicate:

- Matching hash: likely a valid redelivery.
- Different hash: record a conflict, alert, and handle per safety policy.

Do not place raw payloads or hashes that could reverse-expose sensitive data into metric labels. A hash is suitable for comparison in controlled storage, though input data sensitivity must still be considered.

## 11. Choosing the scope of the idempotency key

The idempotency key must be unique within the exact **scope of the side effect**.

For example, an OrderPaid event may be consumed by order-paid-projection, accounting-ledger, and customer-notification. Each handler performs a different side effect. If the inbox table is unique solely by eventId system-wide, the first consumer could wrongly block the other consumers.

Composite key schema:

~~~text
PRIMARY KEY (handler_name, event_id)
~~~

If the same handler runs multiple projection versions with independent purposes, you can include projection generation/version in the scope.

For event IDs that are not globally unique:

~~~text
PRIMARY KEY (consumer_name, producer_name, tenant_id, event_id)
~~~

Do not add dimensions to the key arbitrarily. The scope must reflect the logical effect, not a pod ID or thread ID.

## 12. Idempotent business updates do not always need an inbox

Some operations can be naturally idempotent by designing the state update.

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :orderId
  AND status <> 'PAID';
~~~

Re-running the statement does not change the PAID status a second time.

However, if the business update also inserts a new ledger row, increments a balance, sends an email, fires a webhook, or creates a shipment, those side effects can still repeat.

You must evaluate the entire transaction, not just the first SQL statement. The inbox pattern is useful when one logical event triggers multiple business changes that must be protected together.

### 12.1. Setting state vs incrementing state

| Operation | Idempotent when repeated? |
|---|---|
| Set order.status = PAID | Usually yes, if the state transition is valid |
| Set customer.address = new value | Possibly, if version/order is handled |
| Increment account.balance by amount | No |
| Decrement inventory by quantity | No |
| Insert ledger entry with unique eventId | Yes |
| Send email on every invocation | No if the provider does not deduplicate |

Do not treat an increment operation as an idempotent update simply by adding a status condition when other side-effect tables are involved.

## 13. Idempotency with account balances and inventory

Unsafe example:

~~~sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

If the record is redelivered, the balance increases again.

It can be protected using an inbox and ledger entry in the same transaction:

~~~text
BEGIN
  insert inbox key
  if duplicate:
      skip
  else:
      insert ledger entry with unique event_id
      update account balance
COMMIT
~~~

A ledger entry with a unique event ID aids auditing and prevents duplicates. The balance update and ledger insert must be atomic within the same database transaction.

For inventory decrements, use a unique reservation ID or allocation event ID with explicit state transitions. Do not rely solely on the current quantity because duplicates could subtract multiple times.

## 14. Concurrency: two consumers receive the same logical event simultaneously

In a normal consumer group, one partition is assigned to only one member at a time. Yet the same logical event can still arrive concurrently via:

- Two publishes with the same event ID to different partitions.
- Two topics/routes carrying the same event.
- A manual replay running in parallel with the live consumer.
- Two handler instances processing the same data source.
- Application code calling the event handler concurrently.

A database unique constraint coordinates across replicas.

~~~text
Consumer A                         Consumer B
    |                                  |
    v                                  v
INSERT inbox(evt-8f21)             INSERT inbox(evt-8f21)
    |                                  |
    v                                  v
Wins unique key                    Wait / conflict
    |                                  |
    v                                  v
Apply business update              No business update
    |                                  |
    v                                  v
COMMIT                              Observe duplicate
~~~

Transaction B may have to wait for transaction A to finish. If A commits, B sees a conflict/no-op; if A rolls back, B can win the insert and process it. Exact behavior depends on the isolation level and database.

Do not use a local cache as a synchronization mechanism across consumer replicas.

## 15. Event ordering and idempotency are two different problems

Idempotency prevents an event from being applied multiple times. It does not guarantee events are applied in the right order.

Example:

~~~text
OrderUpdated(version=5)
OrderUpdated(version=4)
~~~

If version 4 arrives after version 5 and the consumer applies it blindly, newer state can be overwritten by older data.

An optimistic version check can be used:

~~~sql
UPDATE order_projection
SET status = :status,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version < :incomingVersion;
~~~

Cases to handle include equal version with different payload, skipped versions, or out-of-order arrivals. Partitioning by entity key preserves order within a partition, but does not guarantee ordering across multiple topics or multiple producer paths.

**Idempotency and ordering must be designed separately.**

## 16. External API: using an idempotency key

The consumer's database transaction cannot automatically be atomic with an external HTTP service without a shared distributed transaction protocol.

Example of a listener calling a payment provider:

~~~text
1. Consumer calls POST /charges
2. Provider creates charge successfully
3. Response is lost due to network timeout
4. Listener does not know whether the charge was created
5. Kafka redelivers event
6. Consumer calls POST /charges again
~~~

If the provider supports an idempotency key, send a stable event ID:

~~~http
POST /charges
Idempotency-Key: evt-8f21
Content-Type: application/json
~~~

The provider must guarantee that repeated requests with the same key in the proper scope return the same result or do not repeat the side effect.

Simply adding a header named Idempotency-Key is not enough. You must verify the API provider actually supports those semantics, its retention window, key scope, and how it handles the same key with a different payload.

### 16.1. No API idempotency support

If downstream does not support idempotency keys, options include:

- Creating an adapter service with a durable request ledger and reconciliation mechanism.
- Writing the intent into a DB outbox and having a worker execute the side effect.
- Using workflow state that can query the outcome before retrying.
- Designing the business operation to be naturally idempotent.
- Having manual reconciliation for indeterminate outcomes.

Do not blindly retry a non-idempotent charge/transfer command after a timeout without knowing whether the first request succeeded.

## 17. Combining Inbox and Outbox

**Inbox** protects consumer side effects from duplicate delivery. **Outbox** protects event publishing after a database transaction commits.

If a consumer updates the DB and then sends an event directly using KafkaTemplate, the following can happen:

- DB commits but publish fails: state changes yet downstream never receives the event.
- Publish succeeds but DB rolls back: downstream receives an event for uncommitted state.

Outbox pattern:

~~~text
BEGIN DB TRANSACTION
  update business tables
  insert outbox event with stable eventId
COMMIT
       |
       v
Outbox relay reads unpublished rows
       |
       v
Publish to Kafka
       |
       v
Mark outbox row published
~~~

If the relay crashes after publishing but before marking the row published, the event can be published again. Downstream consumers still need idempotency.

| Pattern | Location | Problem solved |
|---|---|---|
| Inbox | Consumer database | Duplicate inputs do not repeat side effects |
| Outbox | Producer database | Business commit and event intent are persisted atomically |
| Kafka transaction | Kafka resources | Atomic Kafka writes and consumed offsets within a transaction |

No single pattern automatically makes all side effects across multiple systems exactly-once.

## 18. Kafka transactions and exactly-once semantics

Kafka transactions can provide **exactly-once semantics within Kafka's boundary** for consume-process-produce flows when configured properly: output records and consumed offsets are committed in the same Kafka transaction.

Spring Kafka supports transactional listener containers and KafkaTransactionManager under corresponding configurations.

~~~text
Kafka input records
        |
        v
Listener processing
        |
        v
KafkaTemplate sends output
        |
        v
Transaction commits:
  output records + consumed offsets
        |
        v
Downstream read_committed consumer
~~~

If the transaction aborts, output records are not considered committed for consumers using isolation.level=read_committed, and input offsets are not committed in that transaction.

### 18.1. Exactly-once does not automatically include databases and HTTP

If the listener writes to PostgreSQL or calls a payment API outside Kafka, a Kafka transaction does not automatically roll back those side effects.

~~~text
Kafka transaction begins
  |
  +--> update external database
  |
  +--> send Kafka output
  |
  X Kafka transaction aborts
~~~

The Kafka output/offset may abort while the out-of-transaction database update may still have committed.

You need inbox/idempotent database operations, outbox, API idempotency keys, or a workflow with reconciliation to protect systems outside Kafka.

### 18.2. Producer idempotence and transactions are different

Producer idempotence reduces duplicates from protocol retries. Transactions bundle multiple Kafka operations and offsets into an atomic outcome. Neither replaces event IDs and consumer-side business deduplication when a logical event is re-emitted as a new record.

## 19. Retention of the inbox table

The inbox table must retain keys long enough to block any possible redelivery/replay.

If inbox rows are deleted after 24 hours while operators can replay the topic from 30 days ago, an old event can trigger its side effect again.

Retention must consider:

- Kafka topic retention.
- DLT retention.
- Retry-topic delay.
- Backup/restore and disaster recovery.
- Operator replay window.
- Consumer group reset policy.
- Event archiving and reprocessing procedures.
- Business/audit data retention regulations.

Do not delete markers based solely on a period shorter than average processing. An explicit, auditable policy is required.

### 19.1. Intentional projection rebuild

When rebuilding a projection from scratch, the old inbox may cause the consumer to skip all previously processed events.

You can use a new projection generation in the handler scope or create a separate inbox namespace for the rebuild. After verifying the new projection, switch traffic through a controlled procedure.

Do not arbitrarily delete the production inbox to let the consumer re-run; doing so can trigger unintended side effects.

## 20. Payload hash and schema evolution

If storing payload_hash to detect the same event ID with different payloads, canonicalize the payload before hashing.

JSON can represent identical data with different field orderings or whitespace. Hashing raw serialized bytes may produce different results despite equivalent business content.

Options:

- Hash canonical JSON per schema.
- Hash a stable subset of business fields.
- Store the producer event version and compare key fields.
- Use an immutable event envelope with canonical serialization.

If the schema version changes while eventId remains the same, clearly define whether that change counts as the same logical event.

Do not use payload hash as a substitute for event ID. Two distinct events can have identical payloads and still need to be processed separately.

## 21. DLT replay and idempotency keys

When replaying a DLT, preserve the original event ID if the goal is to resume processing the same logical event. The inbox can recognize an already-processed event and skip it.

If the event previously failed before the business transaction committed, the inbox row rolled back, so replay can process it normally.

If an operator intentionally wants to reapply a business operation after it already completed, a new workflow/command with explicit identity and authorization is needed. Do not arbitrarily change eventId to bypass deduplication because that can duplicate ledgers/charges/shipments.

### 21.1. DLT headers

Spring Kafka recoverers may add metadata about original topic, partition, offset, exception, and timestamp. Preserve original correlation ID and event ID per policy, but do not copy sensitive exception payloads/stack traces into unprotected locations.

When a DLT consumer republishes an event, distinguish between:

- eventId: identity of the original business event.
- recoveryId/attemptId: identity of the recovery attempt.
- correlationId: identity of the business flow.
- Kafka offset: position of the record on the DLT.

## 22. Batch listeners and idempotency

A batch listener processes multiple records in a single invocation. You must decide on the transaction boundary.

**One transaction for the entire batch:** if one record fails, inbox markers and business updates for all records in the batch may roll back. On retry, previously processed records may be reprocessed; the inbox protects them if a prior transaction committed, but if the batch transaction rolls back, all changes in that transaction roll back.

**One transaction per record:** each event can commit independently, but container acknowledgment/offset semantics must align so you do not commit past unprocessed records.

~~~text
Batch: [E1, E2, E3]

Per-record transaction:
  E1 -> DB commit
  E2 -> DB commit
  E3 -> failure
  redelivery may include uncommitted offsets

Inbox:
  E1 duplicate -> skip
  E2 duplicate -> skip
  E3 -> retry
~~~

Actual configuration depends on listener type, AckMode, transaction manager, and error handler. Do not assume one batch method invocation always maps to one atomic database transaction.

## 23. Idempotent consumer with a state machine

Another protection mechanism is designing conditional state transitions:

~~~sql
UPDATE orders
SET status = 'SHIPPED',
    shipped_at = :shippedAt
WHERE order_id = :orderId
  AND status = 'PAID';
~~~

The first run transitions PAID to SHIPPED. Redelivery when status is already SHIPPED updates no rows.

However, you must distinguish:

- Zero rows updated because the event is a valid duplicate.
- Zero rows updated because the order is not yet in PAID status.
- Zero rows updated because the order ID does not exist.
- An older event arriving after a newer event.

Do not lump all cases together as duplicates. Check state and version to classify the outcome accurately.

### 23.1. Monotonic version

If the event carries aggregateVersion, apply only newer events:

~~~sql
UPDATE order_projection
SET status = :status,
    aggregate_version = :incomingVersion
WHERE order_id = :orderId
  AND aggregate_version < :incomingVersion;
~~~

An event with the same version may be a redelivery; a lower version is stale; a higher version might indicate a missed event if the domain requires a contiguous sequence.

Idempotency keys and aggregate versions serve two different controls: one guards against the same event, while the other protects ordering/state freshness.

## 24. Idempotency for emails and notifications

Email/SMS/push notifications are side effects that are hard to roll back. If a consumer calls a provider successfully but times out before receiving the response, retries may send again.

Options:

- Provider supports an idempotency key based on the event ID.
- Persist notification intent with a unique event ID in the DB, then let a worker send it.
- Store the provider request ID and delivery status for reconciliation.
- Design the notification service to deduplicate at the receiving layer.
- Accept at-least-once delivery if the business allows it, and clarify duplicate handling.

Do not mark the inbox event complete before the notification intent is durably stored. If you send directly and then insert into the inbox, a crash can cause duplicate sends.

## 25. Failure matrix: inbox and business transaction

| Failure point | Inbox row | Business effect | Kafka offset | Behavior on redelivery |
|---|---|---|---|---|
| Before DB transaction | Absent | Absent | Uncommitted | Process from scratch |
| After inbox insert, before update | Rolled back | Rolled back | Uncommitted | Re-insert and process |
| Business update fails | Rolled back | Rolled back | Uncommitted | Retry everything |
| DB commit succeeds, before Kafka commit | Present | Present | Uncommitted | Inbox detects duplicate, skips effect |
| Kafka offset commits after DB commit | Present | Present | Committed | No redelivery needed in normal flow |
| Inbox commits separately before business update | Present | May be absent | Uncommitted | Risk of skipping event and losing effect |

The last row explains why **the inbox marker must never commit in a separate transaction** before the business update.

## 26. Testing idempotency

A test suite should prove both correctness and failure windows.

### 26.1. Same event sent twice

1. Send eventId=evt-1.
2. Verify the business effect is applied.
3. Resend the same eventId and same payload.
4. Verify the inbox recognizes the duplicate.
5. Verify the business effect appears only once.

### 26.2. Business failure rolls back inbox

1. Send a new event.
2. Make the business update throw an exception.
3. Verify the inbox row did not commit.
4. Resend the event.
5. Verify the next attempt can claim the inbox key and succeed.

### 26.3. DB commit before Kafka offset commit

Simulate a crash or processing interruption after the DB transaction commits but before the offset is acknowledged.

1. DB already has the inbox row and business update.
2. Kafka record is redelivered.
3. Consumer invokes the service again.
4. Inbox insert is a no-op.
5. No repeated side effect.
6. Listener completes and offset advances.

### 26.4. Concurrent duplicate

Run two parallel invocations with the same handler/eventId. Verify the unique constraint allows only one transaction to apply the business effect.

### 26.5. Additional cases

- Same eventId with different payload hash.
- Same eventId across two different handler scopes.
- DLT replay.
- Projection rebuild generation.
- Batch partial failure.
- API timeout after the provider already executed the side effect.
- Older event version arriving after newer version.
- Inbox retention and replay outside the retention window.

## 27. Metrics and logs for idempotent consumers

Track outcomes using low-cardinality metrics:

~~~text
app.kafka.consumer.events
  handler=order-paid
  outcome=processed|duplicate|failed|conflict
~~~

Useful metrics:

- Number of events processed for the first time.
- Number of duplicates skipped.
- Number of event ID/payload conflicts.
- Business transaction failures.
- Retry count and DLT count.
- Inbox insert latency.
- Database lock/unique conflict latency.
- Consumer lag and processing latency.

Do not attach eventId, orderId, customerId, or correlationId to metric labels. These IDs belong in controlled logs/traces.

Structured logs can record:

~~~text
event=consumer_message_outcome
handler=order-paid
eventId=evt-8f21
outcome=duplicate
topic=orders.paid
partition=2
offset=1842
~~~

If eventId or business IDs are considered sensitive data, use redacted values or appropriate internal references.

## 28. Runbook when repeated side effects are detected

1. Identify the repeated business effect: ledger, inventory, email, payment, or state update.
2. Locate the event ID and related Kafka records.
3. Check whether the producer keeps eventId stable across publish retries.
4. Check whether the consumer has an inbox/deduplication key.
5. Verify the unique constraint exists in the database.
6. Verify the inbox marker and business update share the same DB transaction.
7. Correlate DB commit timestamps with the Kafka offset commit/rebalance timeline.
8. Inspect retry topics, DLT replays, and operator offset resets.
9. Verify consumer replicas share the same handler scope.
10. Check payload hash if the same eventId had differing contents.
11. For external APIs, verify provider idempotency key support and retention.
12. Pause retries/replays causing further side effects per incident policy.
13. Reconcile duplicated business data.
14. Fix the transaction boundary or idempotency implementation.
15. Add a test for that exact failure window.
16. Monitor duplicate/conflict metrics after deployment.

Do not delete inbox rows or change eventId to mask duplicates. First determine which effects occurred and which data needs reconciliation.

## 29. Common mistakes

**Kafka delivers each record only once.** False; at-least-once can redeliver after crashes/rebalances.

**enable.idempotence=true makes the consumer idempotent.** False; it protects producer protocol retries within supported scope.

**Using Kafka offset as event identity.** Fails when a logical event is republished with a new offset.

**Using correlationId as the dedup key for all events.** Can drop valid events belonging to the same business flow.

**SELECT then INSERT is enough.** False; prone to race conditions under concurrent invocations.

**Write inbox and commit, then update the business table.** Risks marking an event done even when the side effect failed.

**Update business table then write inbox in a separate transaction.** Risks repeating side effects on crash.

**Unique key on eventId alone system-wide.** Can mistakenly block independent handlers.

**Duplicate eventId is always a valid duplicate.** Same ID with different payload may indicate a producer bug.

**Delete inbox markers after a few hours.** Can allow older replays to repeat side effects.

**Kafka EOS covers all database/HTTP calls.** Incorrect; Kafka transactions are not automatically atomic with external systems.

**Async task submitted means record is processed.** Incorrect; acknowledgment must tie to business completion.

**DLT replay must create a new eventId.** Usually wrong if the goal is to resume processing the same logical event.

**Idempotency solves ordering.** No; separate version/state transition controls are needed.

## 30. Implementation checklist

- [ ] Producer creates stable eventId per logical event.
- [ ] Consumer selects idempotency key with the right scope.
- [ ] Database has a unique constraint for the inbox key.
- [ ] Inbox insert and business changes are in the same DB transaction.
- [ ] Duplicate path skips side effect while still completing listener per policy.
- [ ] Business failure rolls back both inbox marker and business update.
- [ ] Same eventId with different payload is detected.
- [ ] Retention policy matches retry/DLT/replay windows.
- [ ] Idempotency keys are used for external APIs when supported by provider.
- [ ] Outbox is used when events must be published after DB commit.
- [ ] Clearly understood that Kafka transactions cover only Kafka resources.
- [ ] Batch transaction/ack semantics are handled explicitly.
- [ ] Idempotency is separated from ordering/version checks.
- [ ] Metrics exist for processed/duplicate/failed/conflict.
- [ ] Event ID is not used as a metric label.
- [ ] Tests cover duplicates, rollback, crash window, concurrency, and DLT replay.
- [ ] Reconciliation runbook exists for repeated side effects.

## 31. References

- Apache Kafka Documentation — Design: https://kafka.apache.org/documentation/#design
- Apache Kafka Documentation — Producer Configs (enable.idempotence): https://kafka.apache.org/documentation/#producerconfigs_enable.idempotence
- Spring for Apache Kafka Reference — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html
- Spring for Apache Kafka Reference — Exactly Once Semantics: https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html
- Spring for Apache Kafka Reference — Error Handling: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html

Verify your exact Spring Kafka/Kafka client version and database dialect before applying sample code, especially around transaction managers, acknowledgments, batch listeners, and SQL upserts.

## 32. Key takeaways

An **idempotent consumer** guarantees that the same logical event can be delivered multiple times without repeatedly applying business side effects. Kafka at-least-once can redeliver after a database commit but before an offset commit, so consumers must have a stable event ID and a durable deduplication mechanism.

For database side effects, the **Inbox pattern** uses a unique constraint on handler scope and event ID; the inbox marker and business update must commit in **the same DB transaction**. When a transaction rolls back, both roll back; when the DB commits and Kafka redelivers, the inbox detects the duplicate and the consumer skips the side effect.

For external HTTP/payment/email calls, use provider-supported idempotency keys or an appropriate workflow/outbox/reconciliation design. Kafka producer idempotence and Kafka transactions are valuable, but do not automatically cover databases or external APIs. A reliable design also requires ordering/version checks, retention policies, concurrency safety, DLT replay handling, metrics, and tests for failure windows.

