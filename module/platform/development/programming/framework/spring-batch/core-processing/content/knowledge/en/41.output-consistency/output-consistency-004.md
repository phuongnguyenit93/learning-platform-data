# Message output and duplicate delivery

In Spring Batch, a Step can read data from a database or file, process it in chunks, and publish messages to Kafka, RabbitMQ, JMS, or another messaging system. A critical problem is that a message may already have been accepted by the broker while the chunk has not yet committed. If the Job retries or restarts, the same message may be published again.

Duplicate delivery is not necessarily a broker bug. It typically arises from the window between two independent operations: sending a message externally and committing the chunk or JobRepository transaction. If the application cannot perform both operations in one atomic transaction, a crash in between creates an uncertain state.

Output consistency design should target two goals: never losing output when a Job fails or restarts; and if output is resent, ensuring consumers do not apply business effects multiple times.

## 1. Message output in a chunk-oriented Step

A Job typically transforms data into events after processing:

~~~text
Database / File Reader
        |
        v
ItemProcessor
        |
        v
Chunk of output events
        |
        v
Message ItemWriter
        |
        v
Kafka / RabbitMQ / JMS
~~~

For example, an order transitions from PAID to SHIPPED. The processor builds an OrderShipped event and the writer publishes that event so other services update their data.

A chunk can contain many events. The writer may send each event individually, via a batch API, or inside a producer transaction. Either way, Spring Batch needs to know whether the writer succeeded or failed in order to commit or roll back the chunk.

The key distinction is between the Step's transaction and the broker's transaction. If they are independent, a successful publish does not mean the chunk committed; a chunk commit also does not mean all consumers have processed the event.

## 2. Why does duplicate delivery happen?

Suppose a writer publishes event E-100 successfully, but the process stops before the chunk transaction commits:

~~~text
1. Reader fetches order 100
2. Processor creates event E-100
3. Writer publishes E-100
4. Broker confirms receipt of E-100
5. Process crashes before chunk commit
6. Spring Batch restarts chunk
7. Writer republishes E-100
~~~

The broker may end up holding two copies of E-100. From the writer's viewpoint, the first publish succeeded. From Spring Batch's viewpoint, the chunk never finished and must be reprocessed.

Another failure window is a network timeout after the broker receives the message but before the client receives confirmation. The client does not know whether the message arrived. Retrying is reasonable, yet the first message may already exist.

Duplicates can also occur when a writer sends part of a chunk and fails on a subsequent event. When Spring Batch retries the chunk, events sent in the previous attempt can be sent again.

## 3. Publish success differs from chunk commit

A producer call returning normally usually proves only that the broker accepted or acknowledged the publish according to the API's guarantees. It does not prove the Step's database transaction committed.

~~~text
Spring Batch chunk transaction
       |
       +--> Writer publish event E1
       |         |
       |         +--> Broker confirm
       |
       +--> Writer publish event E2
       |         |
       |         +--> Broker confirm
       |
       +--> Chunk commit
~~~

If commit fails after E1 and E2 were confirmed by the broker, Spring Batch may re-run the chunk. If the broker does not participate in the chunk transaction, E1 and E2 can be delivered again.

Conversely, if the writer returns normally before the broker actually confirms the message, the chunk may commit while the publish is failing in the background. For important business messages, the writer must wait for publish results under appropriate semantics or write to a durable outbox.

Do not treat "send started" logs or constructing a producer record as proof that output was persisted.

## 4. Key failure windows

| Crash/failure timing | Possible state | Consequence |
|---|---|---|
| Before publish | Broker has not received event | Chunk can re-run and send for the first time |
| During publish, outcome unknown | Broker may or may not have received | Retry may produce duplicates |
| Broker confirmed, before chunk commit | Event is on broker, chunk uncommitted | Restart may republish |
| After chunk commit | Chunk completed | Events from that chunk should not replay |
| Consumer receives event, before consumer DB write | Event may be redelivered | Consumer must handle idempotently |
| Consumer DB commit, before ACK | DB updated, message may redeliver | Inbox/deduplication prevents repeated effect |

The design must account for uncertain windows, especially when the broker received a message unknown to the caller, and when a database committed before acknowledgement finished.

## 5. At-least-once output is the practical choice

When publishing critical messages, systems usually prefer at-least-once:

- Retry if publish success is unknown.
- Keep output durable until proper confirmation arrives.
- Accept that the broker or consumer may see the same event multiple times.
- Use event IDs and deduplication to avoid repeating business effects.

At-most-once can avoid duplicates by not retrying after ambiguous failures, at the risk of losing events.

Exactly-once delivery is a very strong claim and generally cannot be guaranteed across multiple independent systems. A more pragmatic goal is exactly-once effect: a message may be delivered multiple times, yet the consumer applies it only once per event ID.

## 6. Stable event IDs

Each business message should have a stable ID derived from the source event or operation identity. The ID must remain unchanged across retries, restarts, and republishes.

Example event:

~~~json
{
  "eventId": "evt-order-100-ship-1",
  "eventType": "OrderShipped",
  "aggregateId": "order-100",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-15T10:30:00Z",
  "schemaVersion": 1,
  "payload": {
    "orderId": 100,
    "trackingNumber": "TRK-9001"
  }
}
~~~

If a writer generates a new UUID on every retry, consumers cannot tell that two messages represent the same operation. Event IDs must be created ahead of time or deterministically computed from business keys and sequence/version.

Do not use orderId alone as the event ID if one order can emit multiple valid events. OrderPaid and OrderShipped must have distinct IDs.

## 7. Distinguishing message ID, business key, and correlation ID

Different IDs serve different purposes:

| Identifier | Role |
|---|---|
| eventId/messageId | Uniquely identifies one logical event; used for deduplication |
| aggregateId/business key | Identifies the business entity, e.g., orderId |
| aggregateVersion/sequence | Defines change ordering for an aggregate |
| correlationId | Links messages belonging to the same workflow/request |
| causationId | Points to the event or command that caused the current event |
| batchId/jobExecutionId | Tracks which batch run produced the event |

Do not use JobExecution ID as the event ID if a restart creates a new JobExecution for the same logical event. Event IDs must stay stable across restarts.

Correlation ID also does not replace event ID: many events can share the same correlation ID while remaining distinct events.

## 8. Writer publishing item by item

A custom ItemWriter can send each event in a chunk:

~~~java
public class OrderEventWriter implements ItemWriter<OrderEvent> {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventWriter(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "order-events",
                    event.aggregateId(),
                    event);
        }
    }
}
~~~

This snippet does not wait for send results. Some producer APIs return a future; if the writer returns immediately, the Step may commit before learning that sends failed.

For outputs that must be confirmed before the writer completes, await publish results via client APIs or use transactions/outbox. Avoid waiting synchronously per message sequentially if safe parallel sends are possible, while still observing all results before returning.

Never ignore exceptions in asynchronous callbacks. Failures must propagate as writer errors or be stored durably for reprocessing.

## 9. Waiting for producer acknowledgement

With KafkaTemplate, send typically returns CompletableFuture in modern Spring Kafka versions. The writer can await futures:

~~~java
@Override
public void write(Chunk<? extends OrderEvent> chunk) {
    List<CompletableFuture<SendResult<String, OrderEvent>>> sends =
            new ArrayList<>();

    for (OrderEvent event : chunk) {
        sends.add(kafkaTemplate.send(
                "order-events",
                event.aggregateId(),
                event));
    }

    for (CompletableFuture<?> send : sends) {
        send.join();
    }
}
~~~

Adapt future types and exception handling to your Spring Kafka version. If a future fails, join may throw CompletionException; the writer must preserve the cause so retry classifiers categorize it accurately.

Waiting for broker acknowledgement prevents the writer from returning success while sends remain pending. However, it does not close the window where the broker confirms yet chunk commit fails. In that case, events can still be republished.

Producer acknowledgement is one layer of assurance; idempotency/outbox handles consistency across execution attempts.

## 10. Kafka producer idempotence

Kafka producers support idempotence to reduce duplicates from retries at the producer protocol layer. When enabled and properly configured, the producer uses a producer ID and sequence numbers so the broker recognizes retries of the same batch request.

Common configuration:

~~~properties
enable.idempotence=true
acks=all
retries=2147483647
max.in.flight.requests.per.connection=5
~~~

Exact values and constraints depend on Kafka client versions. With modern clients, idempotence may be enabled by default when compatible settings apply. Verify effective producer configuration.

Producer idempotence does not equal business idempotency:

- It handles producer protocol retries within one producer session.
- It does not automatically recognize the same event resent by a new JobExecution or a new producer instance.
- It does not prevent consumers from processing the same event multiple times due to offsets/acks/restarts.
- It does not make Spring Batch's database transaction atomic with Kafka.

Therefore, stable event IDs and consumer deduplication remain necessary.

## 11. Kafka transactions for output

Kafka transactions can group multiple published records into a single transaction. Consumers configured with matching isolation can read only records from committed transactions.

Configuring producer transactions in Spring Kafka typically sets transactionIdPrefix on ProducerFactory/KafkaTransactionManager. The Step must be configured so the transaction manager manages the Kafka transaction at the right boundary.

Conceptual flow:

~~~text
Begin Kafka transaction
        |
        v
Publish E1, E2, E3
        |
        v
All sends succeed
        |
        v
Commit Kafka transaction
~~~

If an error occurs before commit, the Kafka transaction can abort, and consumers using read_committed will not see aborted records.

This helps when all output lives in Kafka transactions. Yet if the chunk also writes to a database using a different transaction, the two resources are still not atomic with each other.

## 12. Kafka transactions do not automatically commit databases

Suppose a Step both updates a database and publishes a Kafka event:

~~~text
Database transaction T1
   +--> UPDATE orders

Kafka transaction T2
   +--> publish OrderShipped
~~~

If T1 commits while T2 aborts, the database changes without the event appearing. If T2 commits while T1 rolls back, the event may describe a change that never existed.

True transaction coordination is needed to achieve atomicity across two resources, such as JTA/XA when database, broker, drivers, and coordinator all support it. That brings significant operational and recovery complexity.

In many systems, transactional outbox is simpler: update the database and insert an outbox row in the same transaction, then let a separate publisher send the event.

Do not call Kafka's exactly-once semantics "exactly-once" for both database and broker if the database does not participate in that transaction.

## 13. RabbitMQ publisher confirms

RabbitMQ publisher confirms let the producer know the broker took responsibility for a publish per broker semantics. Producers should enable confirm mode and handle nacks/returns.

Distinguish:

- Publisher confirm: the broker confirms the publish was processed at the broker.
- Mandatory return: unroutable messages can be returned if mandatory publishing and return callbacks are configured.
- Consumer acknowledgement: the consumer confirms it finished processing the message.
- Durable queues/message persistence: durability configuration for queues/messages and broker storage.

Confirm does not prove a consumer processed the message. Nor does it create a shared transaction with a database chunk.

If a confirm times out, the producer does not know whether the message was received. Retries can create duplicates. Use stable message IDs and consumer deduplication.

## 14. RabbitMQ transactions and confirms are not the same

RabbitMQ has transacted channels and publisher confirm mode; these are two distinct mechanisms and should not be treated as the same guarantee.

Publisher confirms generally suit high throughput and confirming broker receipt. Channel transactions carry their own cost and semantics; they are not automatically atomic with Spring Batch's database transaction.

When using Spring AMQP, configure RabbitTemplate/connection factory and confirm callbacks per version. The writer must handle ack, nack, return, and timeout per contract.

If the broker accepted the publish yet the confirm was lost on the network, producer retries can resend. Consumers still need idempotency.

## 15. JMS persistent delivery and transactions

JMS supports persistent/non-persistent delivery modes and transacted sessions. Persistent delivery instructs the broker to store messages per configuration and implementation; it does not make a database commit atomically with the message.

A JMS transacted session can commit or roll back message sends within that session. When used with Spring Batch, determine which transaction manager controls the session and the chunk.

If the database and JMS session are independent, a failure window exists between the two commits. JTA/XA can coordinate them when fully supported and configured; otherwise, outbox/inbox is the common choice.

Persistent delivery aids broker durability after receiving a message. It does not replace consumer-side idempotency.

## 16. Partial publishes within a chunk

Suppose a chunk contains four events:

~~~text
Chunk = [E1, E2, E3, E4]

Publish E1 -> broker confirm
Publish E2 -> broker confirm
Publish E3 -> timeout
Publish E4 -> not yet sent
~~~

The writer throws an exception. Spring Batch rolls back the chunk and may retry. On retry, E1 and E2 may be sent again; E3 may already have reached the broker despite the confirm timeout; E4 is sent for the first time.

Hence, one write(chunk) call is not automatically atomic just because it is a single method call.

Ways to handle this:

- Use Kafka transactions to commit/abort all Kafka outputs in the chunk when suitable.
- Use an outbox to persist event lists durably and relay later.
- Use stable event IDs and consumer deduplication.
- Track per-event publish status when reconciliation is needed.
- Never assume writer retries resend only the failed item.

## 17. Transactional outbox

An outbox saves events in the database within the same transaction as business updates. A separate publisher reads the outbox and sends events to the broker.

~~~text
Spring Batch chunk
       |
       +--> Update business table
       |
       +--> Insert outbox event rows
       |
       v
Database COMMIT
       |
       v
Outbox publisher
       |
       +--> Publish event
       |
       +--> Receive broker confirm
       |
       +--> Mark event SENT
~~~

If the chunk rolls back, both business updates and outbox rows roll back. If the chunk commits and the process stops, events remain in the outbox for the publisher to process later.

This decouples database consistency from broker availability. The Step's writer does not need to call the broker directly; it writes only within a database transaction.

## 18. Designing the outbox table

An outbox table can include:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at TIMESTAMP
);
~~~

Key fields:

- event_id: stable idempotency key.
- aggregate_id: business entity key.
- aggregate_version: change sequence.
- event_type/schema_version: payload contract.
- payload: event body or reference to payload.
- status: relay status.
- created_at/published_at: creation and publish timestamps.

You can add retry_count, next_attempt_at, lease_owner, lease_until, and last_error. Do not store secrets or unnecessary sensitive data in the payload.

Add appropriate indexes for pending-event queries, such as status and created_at. For large tables, establish retention/archiving for sent events.

## 19. Writing the outbox in the same chunk transaction

A writer can save business entities and outbox events using the same transaction/database:

~~~java
public class OrderAndOutboxWriter implements ItemWriter<OrderResult> {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    @Override
    public void write(Chunk<? extends OrderResult> chunk) {
        for (OrderResult result : chunk) {
            orderRepository.save(result.toOrder());

            OutboxEvent event = OutboxEvent.from(
                    result.eventId(),
                    result.orderId(),
                    result.toEventPayload());

            outboxRepository.save(event);
        }
    }
}
~~~

If both repositories participate in the same Step transaction, business updates and outbox rows commit or roll back together.

Avoid having one repository accidentally use REQUIRES_NEW or a different transaction manager. Verify the actual DataSource, propagation, and transaction manager.

If using CompositeItemWriter with two database delegates, order can be business writer then outbox writer; both must share the same transaction. If the outbox writer fails, the business write rolls back too.

## 20. Outbox publishers and claiming events

Multiple publisher instances may read PENDING events simultaneously. Claim events to prevent two publishers from sending concurrently.

Strategies include:

- SELECT ... FOR UPDATE SKIP LOCKED in a short transaction.
- Updating status to IN_PROGRESS with lease owner and lease expiry.
- Claiming by partition/key.
- Using a queue or CDC to detect outbox rows.

Conceptual SQL example for databases supporting SKIP LOCKED:

~~~sql
SELECT event_id, payload
FROM outbox_event
WHERE status = 'PENDING'
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

LIMIT/FOR UPDATE syntax varies by database. Keep claim transactions short; do not hold row locks while waiting on slow network publishes.

Another design updates the lease in a transaction, commits the claim, publishes outside the transaction, and updates SENT after confirmation. If the publisher crashes, the lease expires so the event can be claimed again.

## 21. An outbox can still publish duplicates

A publisher may encounter this scenario:

~~~text
1. Claim event E-100
2. Publish E-100
3. Broker confirm
4. Process crashes before updating status to SENT
5. Lease expires
6. Another publisher claims E-100
7. Publish E-100 again
~~~

This is the at-least-once behavior of an outbox relay. Do not mark SENT before publishing because a crash between marking and sending loses the event.

Because you cannot always tell whether the broker received a message when the client loses connection, duplicates are safer than lost messages. Consumers must deduplicate by event_id.

Even when broker transactions/producer idempotence reduce duplicates in some windows, retain consumer deduplication for recovery across process restarts.

## 22. Consumer inbox/deduplication

Consumers store processed event IDs in the same transaction as business updates.

~~~sql
CREATE TABLE inbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    received_at TIMESTAMP NOT NULL
);
~~~

Pseudo-code:

~~~java
@Transactional
public void consume(OrderShipped event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjection.apply(event);
}
~~~

Inserting the inbox row and updating the projection must share the same transaction. If the projection update fails, the inbox row rolls back so the message can be redelivered and retried.

If the inbox insert commits before the business update, an event could be marked processed while the projection never updated.

With manual broker acknowledgement, ACK only after transaction commit. If commit succeeds yet ACK fails, redelivery is caught as a duplicate by the inbox and can be ACKed safely.

## 23. Idempotent upserts and deduplication

Not every consumer needs a separate inbox table. You can use a unique event ID in the result table or upsert by business key if the operation is genuinely idempotent.

Example of a projection recording state by aggregate version:

~~~sql
INSERT INTO order_projection(order_id, status, version)
VALUES (:orderId, :status, :version)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    version = EXCLUDED.version
WHERE order_projection.version < EXCLUDED.version;
~~~

This syntax is PostgreSQL-specific. The idea is to apply only events with a newer version.

Idempotent upserts do not suit every event type. For instance, adding 10 reward points is not idempotent if repeated. For delta events, deduplicate by event ID before adding.

Classify events:

- State-setting event: sets state to a value; can be idempotent with versioning.
- Delta event: adds/subtracts or records a transaction; usually needs event ID deduplication.
- Command: requests a side effect; needs an idempotency key and command state.

## 24. Ordering of message outputs

Duplicates are not the only risk. Messages can arrive out of order, especially when multiple workers publish concurrently or when an older event retries after a newer event.

Example:

~~~text
Order 100:
  version 6: OrderPaid
  version 7: OrderShipped

Consumer receives:
  version 7 first
  version 6 afterward
~~~

If the consumer applies version 6 after version 7, state can regress.

Solutions:

- Use aggregateId as the partition key so events for the same aggregate go to the same partition when the broker supports per-partition ordering.
- Attach aggregateVersion or sequence.
- Have consumers check versions before applying.
- Avoid parallel publishing of events requiring global order.
- Design retries/DLQs so old events cannot sneak in behind newer ones undetected.

Kafka guarantees ordering only within a single partition. RabbitMQ ordering can be affected by multiple consumers, redeliveries, and requeues. Never assume global ordering if the broker does not provide that guarantee.

## 25. Spring Batch partitioning and message order

If a Job runs multiple partitions or workers, each worker can publish events concurrently. Order across partitions is not guaranteed simply because the Job orders Steps.

If events for the same aggregate must stay ordered, the partition key should keep the entire aggregate in the same worker or broker partition. If data is split by ID range where the same aggregate can span ranges, adjust the partitioning strategy.

You can serialize per aggregate or use consumer version checks. Avoid a global lock if throughput is high and only per-aggregate order matters.

If order is only needed within each file/batch, preserve source sequence numbers and ensure consumers can detect gaps.

## 26. Retries and duplicates in Spring Batch

When a writer throws an exception, Spring Batch can roll back the chunk and retry per policy. A retry normally calls the writer for the chunk per framework semantics, unaware of which events the producer already sent successfully in the previous attempt.

Example:

~~~text
Attempt 1:
  E1 publish success
  E2 publish success
  E3 publish timeout
  writer throws

Attempt 2:
  E1 publish again
  E2 publish again
  E3 publish again
~~~

Therefore:

- Event IDs must not change between attempts.
- The writer must propagate errors outward if the chunk cannot finish.
- Do not generate new event IDs inside each write call.
- Consumers need deduplication.
- With an outbox, chunk retries simply rewrite the same event ID in the transaction; unique constraints prevent duplicate outbox rows.

Retries should have limits and backoff. Validation or schema errors should not be retried like transient network errors.

## 27. Write skip and message output

Skipping writer exceptions can leave some items unpublished. This is valid only if business rules permit it and skipped items are persisted durably for later handling.

Do not configure broad skips for all exceptions when message output is mandatory.

If an item cannot be published:

1. Determine whether the error is permanent or transient.
2. Retry per policy if transient.
3. If permanent and permitted to discard, write the event to a rejected/outbox-failed store.
4. Save event ID, payload/reference, and reason.
5. Mark the item complete only under explicit business rules.
6. Maintain a replay process to republish after fixing the issue.

Do not treat logs or listener callbacks as a rejected-event store. If writing to the rejected store fails, the chunk should fail so reprocessing remains possible.

## 28. DLQ for outbound messages

DLQs are commonly discussed on the consumer side, yet publishers also need a place for events that cannot be sent after retry exhaustion.

With an outbox, you can move events to FAILED/DEAD after the retry limit, along with last_error and next action. Never delete events immediately from the outbox when the publisher exhausts retries.

~~~text
PENDING
   |
   v
IN_PROGRESS
   |
   +--> confirm --> SENT
   |
   +--> transient failure --> PENDING (retry later)
   |
   +--> permanent / exhausted --> DEAD
                                  |
                                  v
                             Manual replay
~~~

An event in DEAD still needs to be inspectable and replayable. Mark SENT only when the broker confirms and routing policies are satisfied.

If the broker confirms publish yet the message is unroutable, confirms alone may not suffice; with RabbitMQ, handle mandatory returns or proper topology/route validation.

## 29. Transaction synchronization and after-commit callbacks

You can register a callback to publish after the chunk transaction commits:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                publisher.publish(event);
            }
        });
~~~

This avoids sending messages before the transaction commits. However, callbacks run in process memory. If the database commits and the process crashes before the callback executes, the event may never be published with no durable record to recover.

The callback may also run and fail to publish after commit; the database transaction can no longer roll back.

Use afterCommit for secondary signals that are regenerable or optional. For critical business messages, transactional outbox is safer because the event is durably saved within the transaction.

## 30. Spring Batch ItemWriter with an outbox

A Step can use a writer that writes to an outbox instead of publishing directly:

~~~java
@Bean
public ItemWriter<OrderResult> outboxWriter(
        OrderRepository orderRepository,
        OutboxRepository outboxRepository) {

    return chunk -> {
        for (OrderResult result : chunk) {
            orderRepository.save(result.toOrder());

            OutboxEvent event = OutboxEvent.from(
                    result.eventId(),
                    result.orderId(),
                    result.toPayload());

            outboxRepository.save(event);
        }
    };
}
~~~

Step configuration:

~~~java
@Bean
public Step createOrderEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderResult> reader,
        ItemWriter<OrderResult> outboxWriter) {

    return new StepBuilder("createOrderEventsStep", jobRepository)
            .<OrderResult, OrderResult>chunk(100, transactionManager)
            .reader(reader)
            .writer(outboxWriter)
            .build();
}
~~~

Both business writes and outbox writes must use the same transaction manager/resource. When the chunk rolls back, both roll back; when it commits, events are persisted for relay.

The outbox publisher usually runs as a separate service/Step with its own retries and monitoring. It does not need to share the event-creation Step's transaction.

## 31. Batch Jobs publishing only to Kafka

If a Job produces only Kafka output and writes no database tables, you can use a Kafka transaction manager for chunks if your Spring Batch/Spring Kafka versions and configuration support it.

Verify:

- ProducerFactory has transactionIdPrefix.
- KafkaTransactionManager is wired into the Step.
- Writer uses a KafkaTemplate bound to the matching ProducerFactory.
- Chunk transaction commit/rollback drives the Kafka transaction.
- Consumers read with matching isolation when they must see only committed records.
- Restarts and offset/reader state do not produce duplicate out-of-transaction output.

This is a different pattern from outbox. A Kafka transaction can make Kafka outputs atomic within that transaction, yet does not cover an external database unless the database joins the same distributed transaction.

Tests must prove records in aborted transactions are invisible to read_committed consumers.

## 32. Kafka output and consumer isolation

With Kafka transactions, consumers can set isolation.level=read_committed to read only records from committed transactions. With read_uncommitted, consumers can see records from aborted transactions before completion.

Example configuration:

~~~properties
isolation.level=read_committed
~~~

This is a consumer setting, not a producer setting. It applies strictly within Kafka transaction semantics.

If a producer sends non-transactional records, they are still read normally. Across multiple topics/partitions, verify transaction commit markers and consumer behavior against your Kafka version.

Read committed does not deduplicate events republished across two separate transactions. If a Job restart starts a new transaction and republishes the same event ID, consumers can still receive both; business deduplication is needed.

## 33. RabbitMQ publisher reliability

With RabbitMQ, the writer must distinguish confirms, returns, and routing:

- Confirm ACK: broker confirms the publish per protocol.
- Confirm NACK: broker rejects/cannot confirm success.
- Return: message is unroutable when mandatory is set.
- Timeout/connection loss: outcome may be unknown.
- Persistent messages and durable queues: support durability across restarts per broker configuration.

Do not mark output SENT merely because basicPublish threw no exception. Await confirms and handle unroutable returns if messages must enter queues.

If confirm times out, retry with the same message ID; consumer deduplication handles the case where the previous publish reached the broker.

## 34. Message schemas and versioning

Duplicate deliveries must preserve the same logical content. If the same event ID carries a changed payload across retries, consumers can receive two different versions with the same ID and not know which is right.

Construct event payloads deterministically or persist payloads in the outbox before publishing. Do not regenerate events from mutable entities after restart under the old event ID if contents might have changed.

Include:

- eventType.
- schemaVersion.
- occurredAt.
- eventId.
- aggregateId.
- aggregateVersion.
- payload.

Schema evolution requires compatibility rules. Consumers may still receive older events after deploying a new version; keep deserializers backward-compatible and define migration/replay policies.

## 35. Retention and replay

Broker retention or queue TTL affects replay capability. Published events may expire under retention before a consumer recovers.

With an outbox, keep events long enough for publisher retries and reconciliation. After SENT, archive per policy rather than deleting too early if audit/replay is needed.

Define:

- How long the broker retains messages.
- How long the outbox retains events.
- How long the inbox retains deduplication keys.
- Replay procedures after DLQ.
- Handling old events arriving after newer events.
- Restoring from archives once retention expires.

If inbox records are deleted before old messages replay, consumers may reapply events. Deduplication retention must exceed the maximum replay window, or version/sequence guards must protect state.

## 36. Monitoring duplicates and output consistency

Monitor both batch and broker sides:

| Metric | Meaning |
|---|---|
| events_created | Number of logical events created |
| outbox_pending | Number of events awaiting publish |
| outbox_oldest_age | Age of the oldest pending event |
| publish_attempts | Number of publish attempts |
| publish_confirmed | Number of publishes confirmed by broker |
| publish_nacks | Number of rejected publishes |
| publish_timeouts | Number of unknown-outcome timeouts |
| duplicate_publish_detected | Number of event IDs republished |
| consumer_duplicate_count | Number of events deduplicated by inbox |
| consumer_lag | Consumer lag |
| dead_event_count | Number of events moved to DEAD |
| chunk_rollback_count | Number of chunk rollbacks |

Logs should include eventId, aggregateId, aggregateVersion, batchId, JobExecution ID, and outbox row ID. Do not log sensitive payloads.

A key metric is the age of the oldest PENDING outbox record. It reveals a stalled publisher or unavailable broker before the backlog grows too large.

## 37. Testing duplicates when the writer fails

An integration test should reproduce the window where broker publish succeeds yet chunk rollback occurs:

1. Create a chunk containing E1 and E2.
2. Writer publishes E1 and E2, and the broker confirms both.
3. Deliberately throw an exception before the chunk commits.
4. Verify the Step rolls back.
5. Restart the same JobInstance or retry the chunk.
6. Verify event IDs remain E1/E2.
7. Consumer receives the duplicates.
8. Inbox/unique keys apply each event only once.

If using Kafka transactions, test that aborted transactions leave no visible output for read_committed consumers. If using an outbox, test that rollbacks create no outbox rows and commits create the exact event rows.

## 38. Testing crash after confirm before marking SENT

For an outbox publisher:

~~~text
1. Claim E-100
2. Publish E-100
3. Broker confirm
4. Kill publisher before SENT update
5. Lease expires
6. New publisher claims E-100
7. Publish E-100 again
8. Consumer deduplicates eventId
~~~

The test must prove:

- Outbox rows are not lost.
- Events can be republished.
- Event IDs remain unchanged.
- Consumer business effects occur only once.
- Final SENT status is persisted.
- Retries and leases prevent two publishers from sending uncontrollably at once.

This test matters far more than mocking a producer and asserting send() was called once.

## 39. Testing ordering

Create two events for the same aggregate with versions 1 and 2. Introduce latency in publisher/consumer processing so version 2 deliberately arrives first.

Verify the consumer:

- Recognizes the older version.
- Does not overwrite newer state with the older event.
- Can buffer/retry out-of-order missing versions if business rules require.
- Records gaps for reconciliation.
- Does not apply duplicate versions twice.

If the system requires strict ordering, test with real partition keys or serialization mechanisms. Unit testing list ordering does not prove broker delivery order under multiple workers.

## 40. Common mistakes

### Assuming send() returning means the chunk committed

Broker confirm and transaction commit are two separate milestones. Crashes between them can create duplicates.

### Not waiting for producer futures/confirms

The Step may commit before publish failures surface. The writer must observe results or use an outbox.

### Generating a fresh event ID on every retry

Consumers fail to recognize the same event. IDs must stay stable across retries and restarts.

### Enabling only Kafka producer idempotence and skipping deduplication

Idempotence does not prevent resends from Job restarts or new producer instances. Consumers still need idempotency.

### Using Kafka transactions to claim database atomicity

Kafka transactions govern only Kafka resources unless proper coordination exists. Use outbox or XA when needed.

### Marking outbox SENT before publishing

Crashing between update and send loses events. Publish/confirm first, then mark SENT; accept duplicates if a crash occurs in between.

### Deleting outbox events immediately after confirm

Audit/replay capability can be lost. Use proper retention/archiving.

### Ignoring RabbitMQ returns or nacks

Confirms do not guarantee messages routed to the right queues. Check returns/nacks/timeouts.

### Partially publishing a chunk then retrying the whole chunk

Earlier events can be resent. Use stable event IDs and consumer deduplication.

### Publishing in an afterCommit callback and treating it as durable

The process can crash before the callback or publishing can fail post-commit. Use an outbox for important events.

### Not preserving per-aggregate ordering

Old events can arrive after newer events. Use partition keys, versions, and consumer guards.

### Deleting inbox deduplication records too early

Replaying old messages can produce duplicate business effects. Retain dedup keys long enough or use version/sequence checks.

## 41. Process for designing consistent message output

Before implementing a message-publishing writer, establish:

1. Is output going to Kafka, RabbitMQ, JMS, or another broker?
2. Does the writer await confirms/acks from the broker or only enqueue asynchronously?
3. Does chunk commit share a transaction with the broker?
4. If the broker confirms yet chunk commit fails, how are events resent?
5. If confirms time out, how are unknown outcomes handled?
6. Are event IDs stable across retries and restarts?
7. Is producer idempotence enabled and what are its boundaries?
8. Is a transactional outbox needed?
9. How does the outbox publisher handle claim/lease and retries?
10. Do consumers store inbox/dedup keys alongside business updates?
11. Do events include aggregate version and partition key for ordering?
12. Are retries/skips bounded with a DLQ/rejected store?
13. Are broker, outbox, and inbox retentions long enough for replay?
14. Do metrics track pending age, publish confirms, timeouts, and duplicates?
15. Do integration tests simulate crashes after confirm, chunk rollbacks, restarts, and duplicate deliveries?

Message output in Spring Batch can be duplicated when the broker accepts an event before the chunk commits, or when a producer misses a confirm and must retry. Do not try to eliminate all duplicates by disabling retries, as that risks losing output. Use stable event IDs, confirm publishes per broker semantics, keep output durable via transactional outbox when database and broker are independent, and deduplicate on the consumer via inbox or unique business operation keys. When using Kafka transactions alone, confine guarantees to Kafka and test read_committed. Combine ordering/versioning, bounded retries, retention, and crash-window integration tests so every event produces its business effect exactly once even when messages may be delivered multiple times.
