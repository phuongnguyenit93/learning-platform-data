# Redelivery and Duplicate Items in Spring Batch

When a job processes messages from a queue or broker, the same message may be delivered multiple times. This re-transmission is called **redelivery**. If the application has already processed a message without confirming it to the broker, or if the process stops before the acknowledgement is recorded, the broker can deliver that message again. A similar situation occurs when a chunk executes a partial side effect, and then a transaction rollback or job restart causes the item to be processed again.

Therefore, a message pipeline usually must accept the possibility of **at-least-once delivery**: a valid message will be delivered at least once, but may appear multiple times. The application must detect or safely handle duplicate occurrences. This is the foundation of **idempotent processing** design.

Spring Batch provides chunk transactions, retries, skips, `ExecutionContext`, and `JobRepository` to coordinate processing. However, those mechanisms do not automatically make the message broker and the database into a single transaction. You must understand when messages are acknowledged, when chunks commit, how the broker redelivers, and how the writer prevents a business event from being applied multiple times.

This lesson explains the causes of redelivery, distinguishes retry from redelivery, shows how to identify duplicate items, covers idempotency and inbox/outbox patterns, coordinates acknowledgement with transactions, handles poison messages and dead-letter queues, and explains how to test message pipelines in Spring Batch.

## 1. What Are Redelivery and Duplicate Items?

**Redelivery** occurs when a broker sends a message again that a consumer previously received because the broker has not recorded completion under the protocol. The redelivered message may retain the same message ID or have modified delivery metadata depending on the broker.

A **duplicate item** is an item representing the same event or the same business operation appearing more than once in the pipeline. Duplicates can arise from redelivery, retries, restarts, duplicate producer sends, or two consumers processing the same event concurrently.

Example of a message requesting payment capture:

~~~json
{
  "eventId": "evt-9001",
  "paymentId": "pay-123",
  "eventType": "PAYMENT_CAPTURED",
  "amount": 250.00
}
~~~

The consumer receives the message and updates the database, but the process stops before the acknowledgement reaches the broker. The broker does not know the update completed and redelivers the message. If the consumer updates the balance again, the same payment may be applied twice.

Redelivery is a behavior of the messaging delivery system. Duplication is a business-flow problem when an event is processed multiple times without safeguards.

## 2. Why Does a Broker Redeliver Messages?

Brokers typically remove a message from the pending state only when they receive an acknowledgement or when a transaction containing the receive commits. If the broker receives no confirmation, the message can return to the queue.

Common causes:

- The consumer process crashes after receiving the message.
- The container or host restarts before acknowledging.
- The consumer loses its connection to the broker.
- The message visibility timeout expires when processing exceeds the lease duration.
- The consumer issues a negative acknowledgement or rolls back a transaction.
- A listener throws an exception and the container is configured for redelivery.
- The broker fails to receive the acknowledgement due to a network partition.
- The consumer finishes processing, but the acknowledgement is lost in transit.
- The consumer is stopped mid-chunk.
- The message is published multiple times by the producer due to producer retries.

Some brokers use manual acknowledgement; some use transactions; some use visibility timeouts and receipt handles. Redelivery details depend on the broker, client, and consumer configuration. Never assume all brokers share the same semantics.

### Redelivery Is Not Necessarily an Error

Redelivery is the mechanism that prevents messages from being lost when a consumer has not confirmed success. It is a normal part of an at-least-once system.

What must be controlled is business side effects. If processing the same event a second time leaves the already-achieved outcome unchanged, redelivery can be tolerated safely.

## 3. At-Most-Once, At-Least-Once, and Exactly-Once

Three terms commonly describe delivery semantics:

| Semantics | Meaning | Primary Risk |
|---|---|---|
| At-most-once | Message is delivered at most once | Messages can be lost |
| At-least-once | Message is delivered one or more times | Duplicates can occur |
| Exactly-once | Business effect is applied once within a defined scope | Requires coordinating transactions, deduplication, and target systems |

At-most-once can be achieved by acknowledging early, but if the consumer crashes after acking and before processing, the message is lost.

At-least-once is usually safer for critical data because unconfirmed messages can be redelivered. In exchange, consumers must be idempotent.

Exactly-once is often misunderstood too broadly. A broker may guarantee exactly-once within a transaction or an internal stream, but that does not automatically extend to databases, HTTP APIs, file systems, or external payment systems. Define precisely whether "once" applies to message delivery, the broker log, or business side effects.

A practical design typically pairs at-least-once delivery with durable deduplication to achieve effectively-once business outcomes within the database controlled by the application.

## 4. Distinguishing Retry from Redelivery

Retry and redelivery can both cause the same item to be processed again, but they occur at different layers.

- **Retry:** the application or Spring Batch re-invokes an operation after an error considered recoverable.
- **Redelivery:** the broker re-sends a message to a consumer because completion has not been confirmed.
- **Restart:** Spring Batch creates a new execution for the same `JobInstance` and resumes from the saved checkpoint.
- **Duplicate publish:** the producer sends the same business event multiple times, often due to retries or missing sender-side idempotency.

| Mechanism | Who Initiates It? | Scope |
|---|---|---|
| Spring Retry in Step | Spring Batch | Re-invokes an operation per retry policy |
| Broker redelivery | Message broker | Re-delivers unacknowledged messages |
| Job restart | `JobOperator`/`JobLauncher` | Resumes the job from metadata and checkpoints |
| Producer retry | Producer/client | May re-publish the same event |

For example, a writer calls a payment API and hits a timeout. Spring Batch retries the write. The API may have already processed the request before timing out, so the retry could create a duplicate side effect if the API does not accept an idempotency key.

Another case: a consumer reads a message and finishes processing, but the broker never receives the ack. The broker redelivers the message, which another consumer receives. This is not a Spring Batch retry; it is a new delivery from the broker.

Track application attempts and broker delivery counts separately.

## 5. Where Can Duplicates Appear?

A message pipeline has multiple boundaries capable of producing duplicates:

~~~mermaid
flowchart LR
    A["Producer"] --> B["Broker"]
    B --> C["Consumer / ItemReader"]
    C --> D["Processor"]
    D --> E["Writer / Database"]
    E --> F["Commit"]
    F --> G["Acknowledge"]
    G --> H["Broker removes message"]
~~~

Failure windows:

1. Producer publishes successfully without receiving confirmation, then publishes again.
2. Broker delivers a message, but the consumer crashes before processing.
3. Consumer processes, but crashes before committing the database.
4. Database commits, but the consumer crashes before acknowledging.
5. Acknowledgement is sent, but a dropped connection leaves the consumer unsure whether the broker received it.
6. Chunk commits successfully, but the `JobRepository` checkpoint is not saved in the same transaction.
7. Job restart re-reads items because the checkpoint does not accurately reflect progress.
8. Two consumers receive the same logical event due to visibility/lease settings or producer duplicates.
9. A message moves from the main queue to a retry queue and is delivered multiple times.
10. An operator intentionally replays an already-processed message.

The window where the database commits successfully but acknowledgement fails is a common reason consumers must handle duplicates. You cannot rely solely on "having called ack" to assert a message will never appear again.

## 6. Defining a Duplicate Key

To detect duplicates, you need a key representing the business event. That key is commonly called an **idempotency key**, **event ID**, or **deduplication key**.

A message might contain:

~~~json
{
  "eventId": "evt-9001",
  "aggregateId": "payment-123",
  "eventVersion": 7,
  "eventType": "PAYMENT_CAPTURED",
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Key options:

- Producer-generated event ID kept stable across retries.
- Business transaction ID such as `paymentId` if each payment has only one event of that type.
- Aggregate ID combined with event version.
- Source system combined with source event ID.
- A composite key tailored to the business operation.

Do not use a delivery tag, receipt handle, or attempt number as an idempotency key. Those values typically describe a delivery attempt and can change across redeliveries.

### Event ID vs. Aggregate ID

One aggregate can emit many events. If you only use `aggregateId`, the second event for the same payment may be misclassified as a duplicate even though it is a valid state transition.

Examples:

- `payment-123` / `PAYMENT_CREATED`
- `payment-123` / `PAYMENT_CAPTURED`
- `payment-123` / `PAYMENT_REFUNDED`

You can use a dedicated `eventId`, or `aggregateId` + `eventType` + `version` depending on the contract. The key must distinguish valid distinct events while recognizing the same event when republished.

### The Key Must Be Created at the Producer

If the consumer generates a new UUID every time it receives a message, redeliveries produce different keys and cannot be deduplicated.

The producer must generate the event ID once, persist it with the business event, and reuse that ID on publish retries. Consumers use this ID to detect redeliveries.

## 7. What Is Idempotent Processing?

An idempotent operation can be executed multiple times without changing the final outcome after the first execution.

Example status update:

~~~sql
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = ?
  AND status <> 'CAPTURED';
~~~

This can be idempotent if `CAPTURED` is the final state and no secondary side effects repeat. However, if each update also inserts a ledger entry or sends a notification, the overall use case is not necessarily idempotent.

Non-idempotent example:

~~~sql
UPDATE account
SET balance = balance + 250.00
WHERE account_id = 'A-10';
~~~

Running this twice credits the amount twice.

Idempotent design must control all side effects, not just the primary SQL statement. Side effects can include:

- Updating balances.
- Creating ledger transactions.
- Sending emails or SMS.
- Publishing downstream events.
- Generating export files.
- Calling partner APIs.
- Writing audit records.

You can use the event ID to ensure the same event produces side effects only once within a database transaction.

## 8. Inbox Table for Message Deduplication

A common pattern is the **Inbox Pattern**: storing processed message IDs in the same database as business updates.

Example schema:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

`consumer_name` allows the same event to be processed by distinct logical consumers when business requirements call for it. If an event should only be processed once system-wide, `event_id` can be the primary key.

Flow:

1. Start the chunk's database transaction.
2. Attempt to insert the event ID into `processed_message`.
3. If the insert succeeds, proceed with updating business data.
4. If a unique constraint indicates the event already exists, skip business side effects.
5. Commit the inbox record and business update in the same transaction.
6. Acknowledge the message only after the transaction commits successfully per broker integration semantics.

Example service:

~~~java
@Transactional
public ProcessingResult processOnce(MessageEnvelope<OrderEvent> message) {
    int inserted = inboxRepository.tryInsert(
        "order-import",
        message.eventId()
    );

    if (inserted == 0) {
        return ProcessingResult.DUPLICATE;
    }

    orderService.apply(message.payload());

    return ProcessingResult.PROCESSED;
}
~~~

`tryInsert` must be implemented using an appropriate database statement and handle unique constraints according to your database. Do not catch every `DataIntegrityViolationException` and treat it as a duplicate; other constraint violations must still surface.

### Why Must the Inbox and Business Update Share the Same Transaction?

If the inbox insert commits before the business update, the process can crash between the two operations. Subsequent redeliveries see the event already exists and skip it, even though the business update never happened. The message is marked processed even though its side effect never completed.

If the business update commits before the inbox record, a crash in between can cause redeliveries to reapply the business update.

Putting both operations in the same database transaction ensures they commit together or roll back together.

~~~mermaid
flowchart TD
    A["Begin DB transaction"] --> B["Insert inbox event ID"]
    B --> C{"New unique key?"}
    C -->|No| D["Mark duplicate / no-op"]
    C -->|Yes| E["Apply business update"]
    D --> F["Commit"]
    E --> F
    F --> G["Acknowledge per broker integration"]
~~~

If the inbox insert and business update live in two separate databases, a local transaction does not guarantee atomicity. In that case you need a distributed transaction or a dedicated recovery/idempotency workflow.

## 9. Handling Unique Constraints Under Concurrent Consumers

Two consumers may receive the same event concurrently, or a producer may publish duplicates nearly simultaneously. Both check "event not present" before inserting. Under a `SELECT` followed by `INSERT` pattern, both can observe the row missing.

Do not do this:

~~~java
if (!repository.exists(eventId)) {
    repository.insert(eventId);
    applyBusinessUpdate();
}
~~~

Check-then-insert is not atomic. Rely on the unique constraint as the final synchronization mechanism.

A single database statement can perform insert-if-absent, such as in PostgreSQL:

~~~sql
INSERT INTO processed_message (
    consumer_name,
    event_id,
    processed_at
)
VALUES (?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

The inserted row count tells you whether the event is new or already existed. For other databases, use equivalent syntax or catch the specific unique constraint inside the transaction.

Points to maintain:

- The unique key must be enforced by the database.
- Inbox insert and business update share the same transaction.
- Duplicates must not become a generic swallowed error.
- If the transaction rolls back, the inbox row must roll back too.
- Handle lock contention and deadlock retries per policy.

## 10. Using Inbox in ItemProcessor or ItemWriter?

Deduplication can live at several layers, but choose a place with suitable transaction boundaries.

### In the Processor

A processor can check the event ID and return `null` on duplicates. This filters items, but if the processor inserts inbox records or produces side effects, those may happen outside the desired write transaction semantics. Processors can also be re-invoked on rollback/retry.

Use the processor only to read/evaluate duplicates if the check is safe and side-effect-free. A `SELECT` prior to the writer writing does not eliminate race conditions.

### In the Writer or a Service Called by the Writer

The writer executes inside the chunk transaction and is usually the right place to coordinate the inbox insert with the business update:

~~~java
public class IdempotentOrderWriter implements ItemWriter<OrderEvent> {

    private final InboxRepository inbox;
    private final OrderService orderService;

    public IdempotentOrderWriter(
            InboxRepository inbox,
            OrderService orderService) {
        this.inbox = inbox;
        this.orderService = orderService;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk.getItems()) {
            boolean firstDelivery = inbox.insertIfAbsent(
                "order-import",
                event.eventId()
            );

            if (!firstDelivery) {
                continue;
            }

            orderService.apply(event);
        }
    }
}
~~~

Ensure `repository` and `orderService` use the same `DataSource`/transaction manager or an equivalent transaction strategy. If the service opens an independent transaction or commits separately, atomicity can break.

### Deduplicating Before Creating Items

A broker adapter might check IDs and feed only unprocessed messages into the reader. However, if a marker is persisted before the chunk commits, crashes can lose messages. Use this approach only when markers and business processing are coordinated safely in a transaction.

## 11. Duplicate Items Within the Same Chunk

A single chunk may contain two messages with the same `eventId` due to duplicate producer publishing or duplicate broker delivery.

Example:

~~~text
Chunk:
  evt-9001
  evt-9002
  evt-9001
  evt-9003
~~~

If the writer deduplicates only with a chunk-local `Set`, it eliminates duplicates within that single invocation. However, a local `Set` does not guard against duplicates across chunks, `JobExecution`s, or other processes.

Durable protection requires a database unique key or a shared idempotency store.

You can optimize by collecting IDs within the chunk before processing, while still keeping the database as the uniqueness authority:

~~~java
Set<String> idsInChunk = new HashSet<>();

for (OrderEvent event : chunk) {
    if (!idsInChunk.add(event.eventId())) {
        continue;
    }

    processOnce(event);
}
~~~

This snippet only filters immediate repeats inside the same chunk. It does not replace the inbox table.

Define the behavior when two items have the same `eventId` but different payloads. This may indicate a producer bug or event ID reuse. Do not silently treat it as a valid duplicate. You can store a payload hash and fail/quarantine when the same ID carries different content.

## 12. Storing a Payload Hash to Detect Event ID Reuse

An inbox schema can store a hash:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

When the event ID already exists:

- If the payload hash matches, this is likely a valid redelivery.
- If the payload hash differs, the same event ID represents two different payloads; investigate and usually fail or quarantine.

Compute the hash from a stable representation. If JSON field ordering or whitespace can differ with identical semantics, canonicalize the payload before hashing or hash well-defined business fields.

Do not use a hash as a replacement for an event ID when a stable business key exists. Hashing primarily helps detect ID reuse or unexpected payload mutation.

## 13. Inbox Retention and Deduplication Scope

An inbox table cannot grow indefinitely without a retention policy. However, deleting event IDs too soon can allow messages replayed months later to be reprocessed.

Retention should be based on:

- Broker retention and replay capabilities.
- Maximum retry duration.
- Duration messages remain in a DLQ.
- Manual replay procedures.
- Audit or business dispute windows.
- Downstream systems' idempotency windows.

You can retain the inbox permanently for critical business events or archive by partition/date once the replay window expires.

The deduplication key also needs a clear scope. For example, `consumer_name + event_id` lets the same event be processed by two different projections. Using a global `event_id` alone could cause one consumer to accidentally block another.

## 14. Redelivery and Transaction Acknowledgement

A core rule is avoiding acknowledgement before business data is committed.

### Acknowledging Too Early

~~~text
1. Consumer receives message
2. Acknowledge broker
3. Database update
4. Process crashes before commit
~~~

The broker has deleted the message, yet the database has not recorded the change. Data is lost.

### Acknowledging After Commit

~~~text
1. Consumer receives message
2. Database transaction updates inbox + business data
3. Commit database
4. Acknowledge broker
5. Process crashes before broker receives ack
6. Broker redelivers
7. Inbox detects duplicate and skips business update
8. Acknowledge redelivered attempt
~~~

The second scenario can produce redelivery without duplicating business side effects. This is at-least-once combined with idempotency.

### Two Resources Are Not Automatically Atomic

Database commits and broker acknowledgements are usually two operations on two resources. There is a failure window between them. Without a distributed transaction supported by both systems, accept the possibility of redelivery and protect with inbox/idempotency.

Some brokers/clients support transactions or coordinated acknowledgements. Inspect the exact transaction manager, connection factory, and listener/container configuration. Never assume `@Transactional` automatically enlists both broker and database into one atomic transaction.

## 15. JMS and Acknowledgement

With JMS, the session acknowledgement mode affects when a message is confirmed.

Common modes:

- `AUTO_ACKNOWLEDGE`: the provider automatically acknowledges per session semantics after a listener receives the message successfully.
- `CLIENT_ACKNOWLEDGE`: the application calls acknowledge via API.
- `DUPS_OK_ACKNOWLEDGE`: the provider may lazily acknowledge and allow duplicates.
- Transacted session: acknowledgement is tied to JMS session commit/rollback.

Understand mode names and how the container manages sessions alongside the listener framework in use. Spring listener containers can manage acknowledgement and transactions per their own configuration.

When a listener throws an exception in a transacted session, rollback can trigger redelivery. With `AUTO_ACKNOWLEDGE`, do not draw simplistic conclusions purely from method returns or caught exceptions; verify container semantics and test against a real broker.

Do not manually call acknowledge inside a listener whose transaction is managed by the container if doing so conflicts with session ownership.

## 16. Visibility Timeout and Receipt Handles

Some brokers use visibility timeouts instead of JMS-style acknowledgements. When a consumer receives a message, the message becomes temporarily invisible to other consumers for a period. If not deleted/acked before timeout, the message reappears.

Notes:

- Processing time may exceed the visibility timeout.
- Consumers may need to extend visibility/lease during long processing.
- A receipt handle may be tied to a specific receive attempt; you must use a valid handle to delete the message.
- Messages can be redelivered if deletion fails or the handle expires.
- Two consumers may process concurrently if visibility is not extended in time.

If a Spring Batch chunk runs long, the visibility timeout must account for read, process, write, and commit times. Do not set a timeout shorter than high-percentile chunk duration.

Even when visibility extensions succeed, idempotency is still required because network failures or process crashes can create duplicates.

## 17. Integrating a Message Reader with Spring Batch

An `ItemReader` can pull messages from a broker or an adapter responsible for receiving messages. The reader must define an EOF condition for a finite batch.

Example model:

~~~java
public record MessageEnvelope<T>(
    String eventId,
    String deliveryId,
    T payload,
    int deliveryAttempt
) {
}
~~~

Conceptual reader:

~~~java
public class BrokerItemReader
        implements ItemStreamReader<MessageEnvelope<OrderEvent>> {

    private final BrokerClient brokerClient;
    private final String batchId;

    @Override
    public MessageEnvelope<OrderEvent> read() {
        BrokerMessage message =
            brokerClient.receiveForBatch(batchId);

        if (message == null) {
            return null;
        }

        return mapEnvelope(message);
    }

    @Override
    public void open(ExecutionContext context) {
        brokerClient.open();
    }

    @Override
    public void update(ExecutionContext context) {
        // Persist cursor or batch watermark if the broker supports it.
    }

    @Override
    public void close() {
        brokerClient.close();
    }
}
~~~

This is an illustrative adapter, not a universal implementation for every broker. Receive APIs may block, time out, or return empty states. Do not turn a short timeout into EOF if the batch still has messages remaining.

With unbounded queues, an `ItemReader` waiting forever will never end the step. You must define a batch boundary such as message count, batch ID, cutoff timestamp, or snapshot offset.

### The Reader Should Not Acknowledge Independently Before the Chunk Commits

If the reader acknowledges immediately after receiving, the writer may fail after the message is already deleted. A safe design defers acknowledgement until after commit or uses a transaction/adapter guaranteeing equivalent semantics.

With Spring Batch, the reader and transaction manager must be integrated explicitly. Without transaction coordination, use inbox/outbox and tolerate redelivery.

## 18. Distinguishing Broker Offsets from ExecutionContext Checkpoints

With log-based brokers or offset-based queues, two states can exist:

- Broker consumer offset or acknowledgement state.
- Spring Batch `ExecutionContext` checkpoint.

If the two states commit independently, they can drift apart.

Examples:

- `ExecutionContext` saved offset 500 while the broker offset is still 490: messages 491–500 may be redelivered; idempotency handles duplicates.
- The broker committed offset 500 while `JobRepository` only saved 490: restarting from 490 may miss messages if the broker disallows seek/replay or the offset cannot move backward.

Decide which source is authoritative for restarts. Some architectures use broker offsets as the primary checkpoint; some use `JobRepository`; some use an inbox table as a durable processing ledger.

Do not store two independent checkpoints without recovery rules. If Spring Batch manages the checkpoint, ensure the broker adapter can seek or replay from that checkpoint. If the broker manages offsets, ensure `JobRepository` does not introduce conflicting state.

## 19. Idempotency for Database Updates

A straightforward approach is recording the event ID in the same transaction as business updates.

Example service:

~~~java
@Transactional
public void applyPaymentCaptured(PaymentCaptured event) {
    if (!inboxRepository.insertIfAbsent(
            "payment-projection",
            event.eventId())) {
        return;
    }

    paymentRepository.markCaptured(
        event.paymentId(),
        event.amount()
    );

    ledgerRepository.insertCapture(
        event.eventId(),
        event.paymentId(),
        event.amount()
    );
}
~~~

If the event is redelivered, `insertIfAbsent` returns `false` and the service neither reapplies the payment nor creates a new ledger entry.

The ledger table should also have a unique key on `event_id` as database-level protection:

~~~sql
ALTER TABLE payment_ledger
ADD CONSTRAINT uq_payment_ledger_event
UNIQUE (event_id);
~~~

This is an additional safeguard. Do not rely solely on Java-level checks because multiple consumers can run concurrently.

### Conditional Updates

For certain state transitions, you can enforce state conditions:

~~~sql
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = ?
  AND status = 'AUTHORIZED';
~~~

An updated row count of 1 indicates a successful transition; 0 can mean either a duplicate or an invalid state. Additional queries/logic are needed to distinguish the two cases.

Conditional updates help avoid repeated transitions, but do not replace an event ledger if every event must be audited.

## 20. Idempotency for HTTP APIs and External Services

If a writer calls an external API, a database inbox cannot protect that API's side effects on its own unless the API supports an idempotency key or another coordination mechanism exists.

Example HTTP request:

~~~http
POST /payments/pay-123/capture
Idempotency-Key: evt-9001
Content-Type: application/json
~~~

On retry, send the same key again. The API recognizes the request was already processed and returns the prior result instead of capturing again.

Rules:

- Keys must remain stable across retries and redeliveries.
- Payloads for the same key must match per contract.
- The API's key retention must exceed the retry/replay window.
- Handling a response timeout does not prove the request failed.
- Record results or correlation IDs for investigation.

If an API does not support idempotency, you need a compensating workflow or reconciliation. You cannot guarantee exactly-once side effects merely by marking the event in a database before/after the HTTP call, because a crash window still exists between the two systems.

## 21. Outbox Pattern When Downstream Events Must Be Published

A consumer may update a database and need to publish a downstream event. If the database update commits but publishing fails, downstream misses the event. If publishing succeeds but the database transaction rolls back, downstream receives an event for an uncommitted change.

The **Outbox Pattern** solves this by writing the business update and outgoing event in the same database transaction:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Within the same transaction:

1. Insert the inbox event ID to deduplicate input.
2. Update business data.
3. Insert the outgoing event into the outbox.
4. Commit.

A separate publisher reads the outbox and publishes to the broker. If publishing succeeds but the publisher crashes before marking published, the event may be republished. Downstream consumers still need idempotency.

~~~mermaid
flowchart TD
    A["Inbound message"] --> B["DB transaction"]
    B --> C["Insert inbox ID"]
    C --> D["Update business data"]
    D --> E["Insert outbox event"]
    E --> F["Commit"]
    F --> G["Outbox publisher"]
    G --> H["Broker"]
    H --> I["Downstream idempotent consumer"]
~~~

Outbox does not itself guarantee the publisher sends only once. It guarantees the business update and intent to publish are saved atomically in the database. Delivery to the broker remains at-least-once.

## 22. Retries, Backoff, and Redelivery Limits

For transient errors, retries can help processing succeed. However, infinite retries can hold messages and resources forever.

Factors to decide:

- Maximum retry attempts.
- Fixed vs. exponential backoff.
- Jitter to prevent many consumers retrying simultaneously.
- Timeout per attempt.
- Total retry duration.
- Classification of retryable exceptions.
- When to move a message to the DLQ.
- Whether message ordering must be preserved.

Example Spring Batch fault-tolerant step:

~~~java
return new StepBuilder("messageImportStep", jobRepository)
    .<MessageEnvelope<OrderEvent>, MessageEnvelope<OrderEvent>>
        chunk(50, transactionManager)
    .reader(messageReader)
    .writer(idempotentWriter)
    .faultTolerant()
    .retry(TransientBrokerException.class)
    .retryLimit(3)
    .build();
~~~

This example illustrates step-level retries. It does not configure the broker's redelivery policy. Step retries and broker redelivery must be tuned together to avoid unexpectedly multiplying attempts.

If the step retries 3 times and the broker also redelivers up to 5 times, total execution attempts can far exceed what either side configured individually.

### Backoff

Exponential backoff typically increases wait duration after each failure:

~~~text
attempt 1: 1 second
attempt 2: 2 seconds
attempt 3: 4 seconds
attempt 4: 8 seconds
~~~

Add jitter so all consumers do not retry at the exact same instant. Actual values should match system latency and retry budgets.

Do not retry unrecoverable errors such as invalid schemas, invalid credentials, or an event ID reused with a different payload.

## 23. Poison Messages and Dead-Letter Queues

A **poison message** is a message that fails repeatedly because its content or processing condition cannot self-heal. Examples:

- Malformed JSON/XML.
- Missing required business key.
- Unsupported enum.
- Business invariant violation.
- Oversized payload.
- Schema version unsupported by the consumer.

If redelivered infinitely, it can block the queue or waste consumer resources.

A **Dead-Letter Queue (DLQ)** or dead-letter topic stores messages that exceed retry/redelivery policies.

Information to retain when moving to a DLQ:

- Original event ID.
- Original queue/topic.
- Payload or a safe reference to the payload.
- Exception class and error code.
- Delivery/attempt count.
- First and last processing timestamps.
- Consumer/job/step identifier.
- Correlation ID and trace ID.
- Schema version.

Do not write credentials or sensitive data into DLQ headers/logs unnecessarily. DLQs need proper retention and access controls.

### Replaying from a DLQ

Replaying is not always just republishing the message. Decide:

- Fix the payload or fix the code first?
- Keep the original event ID or generate a new event?
- Has the inbox already marked the event as processed?
- If the event was partially processed, is reconciliation needed?
- Is replay allowed to create new side effects?
- How is the person performing the replay audited?

If an event was already processed successfully but ended up in the DLQ due to an acknowledgement failure, replay must be deduplicated. If the event was never processed, replay must pass through the same idempotency policy.

## 24. Skip in Spring Batch Is Not the Same as a DLQ

Skip is a step decision to bypass an item or exception per a `SkipPolicy`. A DLQ is a messaging-layer mechanism for storing rejected messages.

Skipping an item in Spring Batch does not automatically move the message to a DLQ. To quarantine it, you need a reject writer or a broker/DLQ integration with clear transaction and acknowledgement semantics.

Example where the processor throws a data error:

~~~java
return new StepBuilder("messageImportStep", jobRepository)
    .<MessageEnvelope<OrderEvent>, OrderEvent>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(eventProcessor)
    .writer(idempotentWriter)
    .faultTolerant()
    .skip(InvalidEventException.class)
    .skipLimit(100)
    .listener(rejectListener)
    .build();
~~~

A reject listener can write audit logs, but should not perform non-idempotent side effects. If rejected payloads must be persisted durably, use a writer/transactional reject store or a dedicated step.

Do not skip infrastructure errors such as an unavailable database or broker connection failures merely to let the step finish. Distinguish a single message's data error from a system-wide outage.

## 25. Redelivery and Message Ordering

Redelivery can affect ordering. A message failing repeatedly may be placed at the back of the queue or moved to a retry queue; later messages may be processed first.

If the business requires per-aggregate ordering:

- Partition by aggregate ID.
- Carry sequence/version numbers on events.
- Check the version before applying.
- Do not let a newer event version overtake an unprocessed older event if doing so corrupts state.
- Configure retries/DLQs so they do not silently break ordering.
- Handle duplicate event IDs separately from out-of-order events.

Example aggregate table storing version:

~~~sql
UPDATE account_projection
SET balance = ?,
    event_version = ?
WHERE account_id = ?
  AND event_version = ?;
~~~

The statement checks the expected version and updates atomically. If the stored version is already greater than or equal to the incoming event, it may be a duplicate/stale event; if less than expected, a prior event may be missing.

This is optimistic concurrency control for event ordering. Exact rules depend on the event model.

## 26. Redelivery in Partitioned or Concurrent Steps

When multiple workers read messages concurrently, duplicates can be processed at the same time. An inbox unique constraint remains essential because an in-memory lock inside one JVM does not protect other processes.

Consider:

- Each partition has its own reader and checkpoint.
- How the message broker assigns partitions/ownership.
- Whether the visibility timeout is long enough for each worker.
- Whether two workers can receive the same event concurrently.
- Whether the idempotency key is unique across the entire consumer group.
- Whether the writer has appropriate transaction isolation.
- Whether DLQs/retry queues preserve per-key ordering.

Do not use a static `Set` in the JVM as a deduplication store. It is lost on process restart, not shared across instances, and can grow unbounded in memory.

With concurrent consumers, a database unique constraint or conditional write is the durable synchronization point.

## 27. Checkpoints and Deduplication Solve Two Different Problems

An `ExecutionContext` checkpoint answers: where should the reader resume reading?

Inbox/idempotency answers: has this business event already been applied?

The two mechanisms do not replace each other.

For example, the reader has read message 100 and the chunk commits successfully, but broker acknowledgement fails. `ExecutionContext` may have persisted the checkpoint past message 100. The broker still redelivers message 100. If the reader relied solely on a log checkpoint, it might not re-read that message; however, if the broker pushes directly, the duplicate can still arrive. The inbox handles this case.

Conversely, an inbox containing event IDs does not automatically tell the reader how to recover offsets or continuation tokens. The reader still needs a checkpoint/replay strategy.

A reliable design defines both:

- Which source determines the read position?
- When is the checkpoint committed?
- When does broker acknowledgement occur?
- Which transaction wraps the inbox marker and business update?
- What recovery rules apply when the checkpoint and broker state diverge?

## 28. Testing Redelivery and Duplicates

Unit tests should verify the same event ID is applied once:

~~~java
@Test
void duplicateEventDoesNotApplyBusinessUpdateTwice() {
    OrderEvent event = new OrderEvent(
        "evt-9001",
        "order-123",
        new BigDecimal("250.00")
    );

    when(inboxRepository.insertIfAbsent(
        "order-import",
        "evt-9001"
    )).thenReturn(true, false);

    idempotentService.process(event);
    idempotentService.process(event);

    verify(orderService, times(1)).apply(event);
}
~~~

This test verifies service behavior. It does not prove database transactions or concurrency. Integration tests against a real database or Testcontainers are needed to verify the unique constraint.

### Testing the Same Event Within One Chunk

Create a chunk with repeated event IDs:

~~~text
evt-1
evt-2
evt-1
evt-3
~~~

Verify:

- The business update for `evt-1` runs only once.
- `evt-2` and `evt-3` are processed.
- The inbox contains only one row per event.
- Write counts and reject/duplicate metrics match application conventions.

If the writer receives duplicates in the same chunk, the unique constraint must properly handle two inserts occurring within the same transaction.

## 29. Testing the Crash Window Between Database Commit and Acknowledgement

This is an essential test to validate an idempotent design.

Simulate:

1. Consumer receives event `evt-9001`.
2. Inbox and business update commit successfully.
3. Simulate a failure before the acknowledgement is recorded by the broker.
4. Broker redelivers event `evt-9001`.
5. Consumer receives the duplicate.
6. Inbox insert-if-absent creates no new row.
7. Business update does not execute a second time.
8. Consumer acknowledges the redelivered message.

Expected outcome: the message may be delivered twice, but the business side effect happens only once.

You cannot prove this window with simple service mocks alone. Run integration tests with a broker/test container when broker semantics are a critical part of the system.

## 30. Testing Transaction Rollbacks

Another test simulates a business update failing after the inbox insert:

1. Start transaction.
2. Inbox insert succeeds.
3. Business update throws an exception.
4. Transaction rolls back.
5. Verify the inbox row does not exist.
6. Resend the event.
7. Verify the next attempt inserts into the inbox and processes successfully.

If the inbox row still exists after rollback, the inbox repository may be using a different transaction or independent propagation. That can cause messages to be marked duplicate even though business updates never completed.

Tests should exercise the application's real transaction manager and `DataSource`.

## 31. Testing Broker Redelivery and DLQs

A broker integration test can verify:

- Message is delivered the first time.
- Consumer rolls back or does not acknowledge.
- Broker redelivers per configuration.
- Delivery count/attempt metadata updates accurately.
- After the failure limit, the message moves to the DLQ.
- Payload, event ID, and exception metadata are preserved.
- Replaying the message creates no duplicate side effects.

Exact steps vary across JMS brokers, Kafka, RabbitMQ, SQS, and others. Use the corresponding test broker or test container to verify real behavior.

Do not merely assert a listener method was called twice; confirm the broker actually redelivers the message according to protocol.

## 32. Observability for Duplicates and Redelivery

In production, distinguish total messages received from newly processed business events.

Useful metrics:

- `message.received.count`
- `message.redelivery.count`
- `message.duplicate.count`
- `message.processed.count`
- `message.retry.count`
- `message.deadletter.count`
- `message.processing.duration`
- `inbox.insert.conflict.count`
- `message.ack.failure.count`

Structured logs should include:

- `eventId`.
- broker message ID.
- delivery attempt/count.
- consumer name.
- `JobExecution` ID.
- `StepExecution` ID.
- aggregate ID/version.
- outcome: `processed`, `duplicate`, `skipped`, `retrying`, `dead-lettered`.
- exception type and error code.

Do not log entire payloads if they contain personal data, payment data, or secrets. Use event IDs and correlation IDs to link traces.

### Abnormal Spikes in Duplicate Rate

Duplicates are expected in at-least-once systems. However, a sharp increase may indicate:

- Consumer timeouts or crashes.
- Visibility timeout set too short.
- Unstable broker connections.
- Failing acknowledgements.
- Producer duplicate publishing.
- Consumer processing taking longer than the retry budget.
- Frequent job restarts.
- Inbox retention set too short.

Track trends to distinguish normal duplicates from system incidents.

## 33. Common Design Mistakes

### Acknowledging Before Committing Business Data

A crash after ack can lose messages. Acknowledge after commit or use appropriate transaction coordination.

### Assuming the Broker Never Delivers Duplicates

At-least-once permits redeliveries. Consumers must be idempotent.

### Using Delivery Tags as Idempotency Keys

Delivery tags/receipt handles can change across deliveries. Use a stable event ID.

### Using SELECT Before INSERT Alone

Two concurrent consumers can both see the row missing. Use a unique constraint and atomic insert-if-absent.

### Inserting Into the Inbox in a Separate Transaction

If the inbox commits before the business update, an event may be skipped even though business data was not updated. Place them in the same transaction whenever possible.

### Deduplicating with an In-JVM Set

A `Set` is lost on restart and not shared across instances. Use a durable store.

### Using an Aggregate ID as an Event ID

An aggregate has many valid events. Use an event ID or composite key distinguishing event/version.

### Treating an HTTP Timeout as a Failed Request

The server may have processed the request. Resend with the same idempotency key or reconcile.

### Infinitely Retrying Poison Messages

A single unrecoverable message can block the queue. Use a retry budget and DLQ.

### Confusing Skip with a DLQ

Skip does not automatically route messages to a broker DLQ. Design reject persistence or a broker dead-letter policy separately.

### Using ExecutionContext Instead of an Inbox

A read-position checkpoint does not prove a business event was applied. You need both checkpoints and deduplication.

### Using an Inbox Instead of a Checkpoint

An inbox does not tell the reader where to resume reading. You need a reader restart strategy.

### Ignoring Payload Differences When Event IDs Match

The same event ID with different payloads may be a producer bug. Store a hash or compare business identity per contract.

### Assuming @Transactional Covers Both Broker and Database

A transaction manager typically manages only enlisted resources. Verify integration or use inbox/outbox.

## 34. Redelivery and Duplicate Handling Design Workflow

When building a message-processing job, follow this sequence:

1. **Define delivery semantics:** does the broker use at-most-once, at-least-once, or specific transaction semantics?
2. **Choose a business event ID:** an ID stable across producer retries and broker redeliveries.
3. **Define the batch boundary:** which messages belong to the job/step, and what is the EOF condition?
4. **Design acknowledgement:** does ack happen before or after commit; who owns the session/receipt handle?
5. **Design the inbox:** unique key, consumer scope, payload hash, and retention.
6. **Set transaction boundaries:** inbox marker and business update in the same transaction if possible.
7. **Protect external side effects:** idempotency keys, outbox, or reconciliation.
8. **Configure retries:** exception classification, backoff, attempt limits, and timeouts.
9. **Configure DLQs:** poison messages, metadata, retention, and replay procedures.
10. **Design checkpoints:** define authority between broker offsets and `JobRepository` `ExecutionContext`.
11. **Check concurrency/ordering:** unique constraints, aggregate versions, and partition keys.
12. **Test crash windows:** commit before ack, rollback after inbox insert, redelivery, and replay.
13. **Monitor:** received, redelivery, duplicate, ack failure, retry, and DLQ metrics.

## 35. Key Takeaways

- Redelivery is the broker re-sending a message whose completion has not been confirmed.
- Duplicate items can arise from redelivery, producer retries, application retries, or job restarts.
- At-least-once typically permits duplicates; consumers must be idempotent.
- Spring Batch retries differ from broker redelivery and job restarts.
- Idempotency keys must stay stable across every delivery, usually as producer-generated event IDs.
- Never use a delivery tag or receipt handle as a deduplication key.
- An inbox table with a unique constraint provides durable duplicate detection.
- Inbox inserts and business updates should share the same database transaction.
- Acknowledging before commit can lose messages; committing before ack can cause redeliveries, so idempotency is required.
- Database transactions and broker acks are not automatically atomic without corresponding integration/distributed transactions.
- `ExecutionContext` checkpoints and inboxes solve two distinct problems.
- External APIs need idempotency keys or reconciliation; an internal inbox does not protect external side effects automatically.
- Outbox coordinates business updates and publishing intent in one transaction, though the publisher can still resend.
- Retries need limits, backoff, and error classification; poison messages need a DLQ.
- Skip in Spring Batch does not mean moving a message to a DLQ.
- Test the crash window between DB commit and broker acknowledgement.
- Monitor delivery counts, duplicate rates, acknowledgement failures, and DLQs.

Redelivery cannot be eliminated completely in many at-least-once messaging systems, nor does it need to be if consumers process idempotently. When event IDs are stable, inbox and business updates share a transaction, acknowledgements are timed properly, and retries/DLQs have clear bounds, Spring Batch can handle redelivered messages without repeating business side effects.

