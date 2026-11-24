# Limits of exactly once outside Kafka in Spring Kafka

In Spring Kafka, **exactly-once semantics (EOS)** is a scoped guarantee, not a promise that an event executes strictly once across every system. Kafka can coordinate producer transactions, output records, and input offsets to avoid duplicate or partially published Kafka results in supported flows. However, **databases, HTTP APIs, payment gateways, emails, and object storage do not automatically participate in Kafka transactions**.

A Kafka record can be delivered to the same listener multiple times after crashes, rebalances, timeouts, seeks, or DLT replays. If a listener already executed a side effect outside Kafka and then failed before committing the offset, that effect can repeat. Therefore, the crucial business-layer guarantee is usually an **effectively-once effect**: permitting multiple deliveries/invocations while ensuring each logical operation changes target state only once according to business rules.

This lesson focuses on the boundary between Kafka EOS and external side effects, dual-write failure points, and how to use **transactional inbox, transactional outbox, idempotency keys, sagas, state machines, and reconciliation** in Spring Kafka Reliability Operations.

## 1. Clearly defining the target of exactly once

Before evaluating an "exactly once" system, identify what is being guaranteed:

- **Delivery:** a Kafka record may be re-received by a consumer when the offset has not committed.
- **Listener execution:** a `@KafkaListener` method can run again for the same record; Kafka EOS does not forbid it.
- **Kafka output visibility:** transactional outputs and input offsets can commit together; `read_committed` consumers do not observe outputs from aborted transactions.
- **Database effect:** how many times a row is inserted/updated; governed by DB transactions, unique constraints, and domain rules.
- **External API effect:** whether an amount is charged twice; depends on the payment provider's idempotency contract.
- **Physical effect:** a sent email or triggered device cannot be pulled back by a Kafka abort.

~~~text
orders.created
      |
      v
Spring Kafka listener  <--- Can re-receive the same record
      |
      +--> KafkaTemplate.send(output)
      |         |
      |         +--> Can be covered by a Kafka transaction
      |
      +--> Database INSERT/UPDATE
      |         |
      |         +--> Separate database transaction
      |
      +--> HTTP POST /payments
      |         |
      |         +--> Separate payment provider
      |
      +--> Email / Object storage
                |
                +--> System outside Kafka
~~~

To say "exactly once", you must answer: once for **sending a request**, once for **invoking a method**, once for **committing Kafka output**, or once for **changing a balance**? These are different goals.

## 2. Kafka EOS protects Kafka → Kafka flows

In a transactional listener container, the container can open a Kafka transaction before invoking the listener. The listener emits Kafka output records via a producer participating in that transaction. Upon success, the container sends consumer offsets into the same Kafka transaction before committing.

~~~text
Input Kafka record
        |
        v
Transactional listener
        |
        +--> Send Kafka output
        |
        +--> Send input offset into transaction
        |
        +--------------+---------------+
        |                              |
        v                              v
    COMMIT TX                       ABORT TX
        |                              |
        +--> Output visible             +--> Output invisible
        |    to read_committed          |    to read_committed
        +--> Input offset commits       +--> Input offset uncommitted
~~~

A downstream consumer wanting to read only committed Kafka outputs must set:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

The transactional producer needs matching configuration, for example:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-node-1-
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      isolation-level: read_committed
~~~

These settings are illustrative examples. The producer factory and listener container factory must genuinely be configured with `KafkaTransactionManager` or a Kafka-aware transaction manager matching your Spring Kafka/Spring Boot version. Setting a single property does not guarantee custom factories automatically use the transaction manager.

Kafka EOS resolves atomic commits for **operations inside the Kafka transaction**, without automatically covering every Java statement in the listener. A `read_uncommitted` consumer can still observe aborted transactional outputs; thus downstream isolation level is a critical part of the contract.

## 3. Kafka transactions do not mean the listener runs once

Suppose a listener sends Kafka output and then fails before the transaction commits. The container aborts the transaction and the input record can be redelivered.

~~~text
Attempt 1:
  Input event E
      |
      +--> Listener runs
      +--> Uncommitted Kafka output
      +--> Exception
      +--> Abort transaction

Attempt 2:
  Input event E is redelivered
      |
      +--> Listener runs again
      +--> Kafka output
      +--> Commit transaction
~~~

The listener was invoked twice, yet the transactional output from the aborted attempt is not observed by `read_committed` consumers. That is the difference between **at-least-once execution** and EOS for Kafka outputs.

If during attempt 1 the listener sent an email or updated a database, a Kafka abort does not undo those operations. Therefore, counting listener invocations neither proves Kafka transaction guarantees nor proves single business effects.

## 4. Producer idempotence differs from business idempotency

Kafka producer idempotence prevents certain duplicate records when the **same `ProduceRequest`** is retried by the Kafka protocol. It does not recognize new business calls issued across two separate consumer executions.

| Mechanism | Protection scope | Does NOT protect |
|---|---|---|
| Producer idempotence | Producer retries within protocol and producer session bounds | Two distinct business logic calls using the same event |
| Kafka transaction | Kafka output records and input offsets in the transaction | Databases, payments, emails |
| DB unique constraint | Duplicate records of one table by key | External APIs not backed by that DB |
| Consumer inbox | Reprocessing of the same logical event | Kafka outputs if lacking an outbox |
| API idempotency key | Same logical API request at supporting providers | New requests with different keys |
| Aggregate version | Old events overwriting newer state | Missing events or other side effects |

For example, the same `eventId` is replayed from a DLT. The application calls `KafkaTemplate.send` once per execution. If each execution is a separate valid Kafka transaction, producer idempotence has no way of knowing that `eventId` was already processed business-wise.

Generate a stable **eventId** or **operationId** at the source and preserve it across retries/replays. Never generate a fresh UUID on every attempt if those attempts must be treated as one operation.

## 5. The dual-write problem

A service writing to both a database and Kafka updates **two independent resources**. Regardless of commit order, a point exists where one resource has committed while the other has not.

~~~java
@KafkaListener(topics = "orders.created", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.processed", event.orderId(), event);
}
~~~

Short code hides which transaction—if any—binds both steps. Failure windows:

| Crash point | Database | Kafka output/offset | Risk |
|---|---|---|---|
| Before DB commit | Unchanged | Uncommitted | Can redeliver and retry |
| After DB commit, before input offset commit | Mutated | Offset uncommitted | Database side effect may repeat |
| After Kafka output commit, before DB commit | Unchanged | Output exists | Downstream sees event with no matching DB state |
| After DB commit, before Kafka output publish | Mutated | Missing output | Downstream event can be lost without an outbox |
| Both committed, caller lost response | Both succeeded | Caller unaware | Caller retry can duplicate request |

Swapping DB-before-Kafka vs. Kafka-before-DB only shifts the failure window. `try/catch` does not turn two resources into a distributed atomic transaction.

## 6. Why isn't @Transactional enough to guarantee DB + Kafka atomicity?

Example:

~~~java
@Transactional
public void saveAndPublish(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.processed", event.orderId(), event);
}
~~~

If `@Transactional` uses `JpaTransactionManager`, that transaction manages the database. `KafkaTemplate` may join a Kafka transaction or behave differently depending on `ProducerFactory` and transaction synchronization config. Yet there is no XA/2PC guarantee merely because both calls sit in one Java method.

Even when Spring synchronizes two transaction managers, a point remains:

~~~text
Database COMMIT succeeds
           |
           v
Kafka COMMIT fails
           |
           v
Database mutated, Kafka output incomplete
~~~

Or in reverse order, Kafka commits first and the database fails.

A Spring transaction annotation does not automatically make Kafka and a database commit/roll back atomically across all failure scenarios. For critical workflows, design a durable source of truth (usually the database) and a recovery mechanism for the remaining steps.

## 7. Kafka → Database: transactional inbox

A consumer reading events and updating a database must tolerate redelivery. A **transactional inbox** or processed-events table records applied events alongside the database side effect in a single transaction.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

In Java:

~~~java
@Service
public class OrderProjectionService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderProjectionService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void apply(OrderCreated event) {
        boolean firstTime = processedEvents.insertIfAbsent(
                "order-projection",
                event.eventId()
        );

        if (!firstTime) {
            return;
        }

        orders.insertOrderIfAbsent(
                event.orderId(),
                event.amount(),
                event.currency()
        );
    }
}
~~~

`insertIfAbsent` is an atomic operation enforced by a database unique constraint, not merely a `SELECT` followed by an `INSERT` without concurrency control.

Record the processed marker and update the order **in the same database transaction**. If the order update fails, the processed marker must roll back too. If the marker commits first and business work fails afterward, redelivery gets skipped and causes lost processing.

### Crash window solved by the inbox

~~~text
Kafka input E
       |
       v
BEGIN DB TRANSACTION
       |
       +--> INSERT processed_events(E)
       +--> UPDATE orders
       |
       v
COMMIT DB
       |
       +--> Process crashes before Kafka offset commit
       |
       v
Kafka redelivery E
       |
       v
INSERT processed_events(E) hits unique conflict
       |
       v
No repeated database side effect
       |
       v
Listener returns; Kafka offset can commit
~~~

Thus, the listener runs again while the **database effect** is applied only once per `eventId` and defined unique constraint.

## 8. Atomic deduplication in the database

One approach in PostgreSQL:

~~~sql
INSERT INTO processed_events (
    consumer_name, event_id
)
VALUES (
    :consumer_name, :event_id
)
ON CONFLICT (consumer_name, event_id)
DO NOTHING
RETURNING event_id;
~~~

If `INSERT` returns a row, the event was newly claimed in that transaction; otherwise, the event already existed.

Never use this logic without a shared transaction:

~~~java
if (!processedEvents.exists(event.eventId())) {
    orders.insert(event);
    processedEvents.markProcessed(event.eventId());
}
~~~

Two consumers or a worker and a replay job can both pass the existence check and both execute the side effect before racing on writing the processed marker. Unique constraints are the real concurrency gate.

If an event spans steps outside the database, the processed marker here reflects only **the step committed in the database**. It does not prove a payment or email also completed.

## 9. Database → Kafka: transactional outbox

When an application updates a database and emits a Kafka event, a **transactional outbox** ensures event-publishing intent is never lost after DB commit.

~~~text
HTTP command
    |
    v
Database transaction
    |
    +--> INSERT orders
    +--> INSERT outbox_events
    |
    v
COMMIT DATABASE
    |
    v
Outbox publisher or CDC
    |
    v
Kafka topic orders.created
~~~

Illustrative schema:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(150) PRIMARY KEY,
    aggregate_id VARCHAR(150) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);
~~~

Write the domain change and outbox row in one DB transaction:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.insert(command);

    outboxRepository.insert(
            OutboxEvent.orderCreated(
                    command.requestId(),
                    order.id(),
                    order.toCreatedEvent()
            )
    );
}
~~~

If the transaction rolls back, neither an order nor an outbox row exists. If the DB commits successfully, the outbox row remains available to publish to Kafka after a restart.

Publishers can poll the table periodically or use Change Data Capture like Debezium. However, **outbox does not eliminate Kafka duplicates by itself**: publishing to Kafka and crashing before marking sent causes the publisher to resend. Downstream still needs `eventId` and an idempotent consumer.

## 10. Combining inbox + outbox for Kafka → DB → Kafka

This is a key pattern when an input event both updates a database and produces an output event.

~~~text
Kafka input
     |
     v
@KafkaListener
     |
     v
Database transaction
     |
     +--> INSERT inbox(eventId) if absent
     +--> UPDATE orders
     +--> INSERT outbox(outputEventId)
     |
     v
COMMIT DATABASE
     |
     +--> Listener returns, Kafka input offset commits
     |
     +--> Outbox publisher sends Kafka output
~~~

Failure window table:

| Scenario | Recovery |
|---|---|
| Crash before DB commit | DB rolls back, Kafka redelivers |
| Crash after DB commit before offset commit | Inbox prevents duplicates |
| Crash before outbox publish | Outbox row still exists |
| Kafka unavailable during publish | Publisher retries |
| Published yet not marked sent | May publish duplicate; downstream inbox prevents duplicate effect |
| Output received twice | Idempotent consumer downstream |

Illustrative service code:

~~~java
@Service
public class OrderProjector {

    private final InboxRepository inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderProjector(
            InboxRepository inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void apply(OrderCreated event) {

        boolean firstTime = inbox.insertIfAbsent(
                "order-projector",
                event.eventId()
        );

        if (!firstTime) {
            return;
        }

        OrderValidated validated = orders.applyCreated(event);

        outbox.insertIfAbsent(
                OutboxEvent.from(event.eventId(), validated)
        );
    }
}
~~~

Here, repository methods represent real database implementations requiring a shared transaction and unique keys. When duplicate input is re-read, the method can return normally so the container commits the Kafka offset without creating extra domain updates or outbox rows.

## 11. HTTP APIs and ambiguous timeout outcomes

An HTTP timeout does not prove the request was never processed. For payments:

~~~text
Consumer                 Payment Provider
   |                            |
   |---- POST /charge --------->|
   |                            +--> Charge succeeds
   |<---- Response lost --------X |
   |
   +--> Timeout exception
   |
   +--> Retry POST /charge
                                |
                                +--> May charge a second time
~~~

A Kafka abort cannot reverse the first charge. If the provider supports an **idempotency key**, send the same `operationId` across every retry of the same logical payment:

~~~java
paymentClient.charge(
        event.paymentId(),
        event.amount(),
        event.paymentOperationId()
);
~~~

`operationId` must stay stable across consumer restarts, retry topics, and DLT replays. Never use attempt numbers or a fresh random UUID per retry as the idempotency key.

Understand the provider's contract:

- How long is the idempotency key retained?
- Is the same key with a different payload rejected?
- Does it return the previous request's result or just a duplicate error?
- What happens to a second request while the first is still in flight?
- Is there a status lookup API by `operationId`?
- Can settlements or webhooks be reconciled later?

After a timeout, **query status** whenever possible before creating a new operation. For payment/financial operations, never assume HTTP 500 or a timeout always means the target transaction rolled back.

## 12. Target APIs lacking idempotency: an unavoidable limit

If an external API has no idempotency key, no status lookup, and responses can be lost, the caller cannot know for sure whether a request executed.

Both options carry trade-offs:

- **Retry to avoid missing an action:** may create duplicate effects.
- **Do not retry to avoid duplicates:** may drop an effect if the request never finished.

`KafkaTransactionManager` cannot resolve this because Kafka does not control external API commits.

Improvements:

1. Evolve the API contract to support an idempotent `operationId`.
2. Add status lookups or reconciliation with the target system.
3. Persist request state durably on the calling side.
4. Implement compensation to reverse duplicate effects where the business permits.
5. Explicitly document delivery-guarantee trade-offs when duplicates/missing effects cannot be fully eliminated.

This is a fundamental distributed-systems limit, not a missing annotation in Spring Kafka.

## 13. Emails and SMS cannot be rolled back by Kafka

A consumer that sends an email successfully and crashes before committing the Kafka offset can resend the email upon record redelivery. A Kafka abort does not recall an email already delivered to a mailbox.

~~~text
Kafka listener
     |
     +--> Email provider accepted message
     |
     +--> Process crashes
     |
     +--> Kafka offset uncommitted
     |
     v
Retry/replay --> Email sent again
~~~

Ways to reduce duplication:

- Stable notification ID and durable delivery state.
- Transactional outbox for send requests.
- Idempotency keys or message status lookups if supported by the provider.
- Rate limits and cooldowns for sensitive notifications.
- Idempotent webhook handling.
- Explicit policy on accepting duplicate vs. missing notifications.

If the provider cannot confirm delivery and lacks deduplication, never promise **strictly zero duplicates and zero drops** under every scenario.

## 14. Object storage and file side effects

Writing objects/files also occurs outside Kafka transactions.

~~~text
Kafka E
   |
   +--> putObject("reports/order-1.pdf") succeeds
   |
   +--> Crash before committing Kafka offset
   |
   +--> Redelivery E
   |
   +--> putObject a second time
~~~

To improve idempotency, use deterministic object keys derived from logical operations, verify checksums, and use conditional writes (such as ETag or object-does-not-exist conditions) per the storage API.

However, if database metadata must also commit, a dual-write reappears between storage and the database. Use workflow states `PENDING`/`UPLOADING`/`UPLOADED`/`VERIFIED`, an outbox for upload requests, and reconciliation for orphan objects.

Do not generate a new random filename per attempt when the goal is one object per logical operation. Conversely, never overwrite another operation's object due to key collisions. Validate key design and tenant access permissions.

## 15. A single processed boolean is insufficient for multi-step workflows

A business process may require:

~~~text
1. Reserve inventory
2. Charge payment
3. Send confirmation
4. Publish fulfilled event
~~~

If you only store `processed(eventId)=true/false`:

- Marking `true` at the start: a crash afterward can skip unfinished steps.
- Marking `true` at the end: a crash mid-flow can repeat already-finished steps.
- Lacking intermediate states: makes ambiguous timeouts hard to handle.

Replace it with a durable state machine:

~~~text
RECEIVED
   |
   v
INVENTORY_RESERVED
   |
   v
PAYMENT_CONFIRMED
   |
   v
NOTIFICATION_REQUESTED
   |
   v
COMPLETED
~~~

Each step should have:

- A stable step ID / operation ID.
- Idempotency on the target resource.
- Persisted state and attempt counts.
- Deadlines, timeouts, and backoff.
- Retries or compensation if a later step fails.
- Audit trails identifying which steps actually completed.

Across multiple independent resources, this usually calls for a **saga** or workflow orchestration model, not one long-running Kafka transaction wrapping everything.

## 16. Sagas and compensating actions

A saga splits a business process into multiple local transactions. If one step fails, the system executes compensating actions:

~~~text
Create order
     |
     v
Reserve stock
     |
     v
Charge payment
     |
     +--> Success --> Confirm order
     |
     +--> Failure --> Release stock
~~~

Releasing stock is not like rolling back a single database transaction. It is a **new business action** that can itself fail or be retried. Therefore, compensations also need idempotency keys such as `reservationId` or `paymentOperationId`.

If a payment occurred while local state did not update due to a timeout, never issue a blind refund; query and reconcile state before deciding on compensation.

Sagas require ownership, state machines, auditing, error routing, manual intervention, and reconciliation for steps that cannot self-heal.

## 17. Consumer offsets are not certificates of external effects

A consumer's committed offset is the consumer group's read position. It does not certify that a database committed or a payment was captured successfully.

~~~text
Consumer A processes event E
       |
       +--> Database COMMITS
       |
       +--> Kafka offset NOT committed yet
       |
       +--> Rebalance or crash
                   |
                   v
Consumer B receives partition
       |
       +--> Re-reads E
       |
       +--> Inbox prevents duplicate database effect
~~~

For Kafka → DB, the practical order should usually be:

1. Begin database transaction.
2. Claim `eventId` via unique constraint.
3. Perform domain update in the same transaction.
4. Commit database transaction.
5. Listener returns successfully.
6. Kafka container commits input offset.

If a crash happens between steps 4 and 6, the record may be re-read while the inbox prevents duplicate side effects. If the Kafka offset commits before step 4, business updates risk being lost on process crash.

This is a deliberate choice: **accept redeliveries, prevent duplicates with durable data**.

## 18. Retry topics, DLTs, and replays can still create duplicates

Spring Kafka's `DefaultErrorHandler`, `RetryTopicConfiguration`, or `@RetryableTopic` assist with retry/recovery, yet do not automatically guarantee exactly-once external effects.

~~~text
Source topic
    |
    +--> Error, routed to retry topic
    |           |
    |           +--> Reprocessed
    |
    +--> Attempts exhausted
                |
                v
               DLT
                |
                v
             Replay
                |
                v
         Listener re-runs
~~~

Windows worth noting:

- Retry topic publish succeeds while source offset is uncommitted.
- DLT publish succeeds while crashing before source offset commits.
- Operator replays a record that already applied some side effects.
- Retry topics let a later record overtake a failing record on the same business aggregate.
- An external API accepted a request even though the listener threw an error.

A DLT does not prove business logic produced zero side effects. Before replaying, inspect `eventId`, `operationId`, external dependency states, ordering rules, and audit logs.

## 19. Kafka Streams exactly_once_v2 and external calls

Kafka Streams provides `exactly_once_v2` processing guarantees for framework-managed Kafka operations, including state stores/changelogs and transactional outputs/offsets. Example:

~~~properties
processing.guarantee=exactly_once_v2
~~~

This does not mean a Kafka Streams processor calling a non-idempotent REST API yields an exactly-once HTTP effect.

A transformer may call a payment provider successfully, and then the Kafka transaction aborts. When input is reprocessed, the transformer may call the payment provider again. State stores and Kafka changelogs do not roll back payment providers.

Thus, even with Kafka Streams EOS, all external I/O needs idempotency, outboxes, durable workflow state, or reconciliation.

## 20. Ordering and aggregate versions

Deduplicating by `eventId` stops the same event from running twice, yet does not solve **two different events processed out of order**.

~~~text
OrderStatusChanged(version=5) --> retry topic
OrderStatusChanged(version=6) --> succeeds on source topic
OrderStatusChanged(version=5) --> replayed late
~~~

Both events have distinct `eventId`s. An inbox does not block version 5 if it was never processed before, even though version 6 already applied.

Use optimistic/version checks:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :new_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

If affected rows equal 0, determine whether the event is stale, arrived out of order, or the aggregate is in an unexpected state. Never blindly retry every version conflict forever.

Kafka partition keys preserve order within each topic/partition, while retry topics, async processing, and external APIs can break **side-effect completion order**. Combine `eventId`, aggregate versions, and state transition rules when the domain requires both duplicate prevention and strict ordering.

## 21. Idempotency identifiers and dedup state retention

Different keys serve different purposes:

| Key | Meaning |
|---|---|
| `eventId` | A domain event |
| `commandId` | A business request from a caller |
| `operationId` | A specific side effect, such as a payment charge |
| `aggregateId + version` | Event position within an aggregate's lifecycle |
| `consumerName + eventId` | Deduplication scope for a logical consumer |

Never use an offset alone as a business `eventId`: offsets are unique only within one partition of one topic. Records can be copied to retry topics, DLTs, or replayed under new offsets.

If `processed_events` is purged after a short TTL, old replays can be treated as new events. Size dedup retention based on the **replay horizon**, audit requirements, and business unique constraints.

For payments, idempotency keys may have a TTL at the provider. When replaying past the TTL, query status or reconcile via business transaction ID rather than assuming the provider still remembers the key.

## 22. Guarantee selection table by side-effect type

| Flow | Achievable guarantee scope | Primary solution |
|---|---|---|
| Kafka input → Kafka output | Kafka EOS for supported transactions | Transactional producer/container, `read_committed` |
| Kafka input → Database | Effectively-once DB effect | Transactional inbox + unique constraint |
| Database → Kafka | No lost event intent after DB commit | Transactional outbox + publisher/CDC |
| Kafka → DB → Kafka | Idempotent DB effect, output eventually published | Inbox + outbox in same DB transaction |
| Kafka → Payment API | Effectively-once if provider supports it | Stable idempotency key, status lookup |
| Kafka → Email/SMS | Cannot strictly promise if provider lacks support | Delivery state, outbox, best-effort policy |
| Kafka → Object storage | Effectively-once object effect per key | Deterministic key, conditional write |
| Kafka → multiple external systems | Distributed workflow | Saga, per-step idempotency, compensation |

The term **effectively-once** reflects that attempts/deliveries can occur multiple times, while the final side effect is guarded against duplication per the defined contract.

## 23. Common mistakes

**Enabling `transaction-id-prefix` and assuming the database also rolls back**

No. Databases and Kafka have separate transaction managers. Spring transaction synchronization is not a distributed XA transaction by default.

**Enabling `enable.idempotence=true` and assuming the same `eventId` is never sent twice**

Producer idempotence is not business deduplication across independent executions.

**Sending Kafka output inside `@Transactional`(database) and treating both commits as atomic**

No such guarantee exists without true distributed transactions. An outbox is usually far easier to operate to avoid losing events.

**Writing the processed marker before the domain update**

If the marker commits while the update fails, retries skip the event. Write both in the same DB transaction.

**Using `SELECT` then `INSERT` to prevent duplicates**

Two workers can both pass the `SELECT`. Use unique constraints and atomic inserts.

**Generating a new UUID on every retry**

Breaks deduplication. Keep the `operationId` from the first logical execution.

**Using an overly short inbox TTL**

Old records replayed after TTL expiration can trigger side effects again.

**Assuming DLT means no side effects occurred**

The record may already have triggered payments/emails before failing at a later step.

**Assuming an HTTP timeout means the request was never processed**

The payment provider may have committed and lost the response. Status lookups/idempotency are required.

**Claiming end-to-end exactly-once from Kafka metrics alone**

You must also check database state, external APIs, and workflow steps.

## 24. Testing crash windows

Unit tests calling the listener directly cannot prove distributed reliability. You need integration tests and fault injection at commit boundaries.

| Crash/failure point | What to verify |
|---|---|
| Before DB commit | DB rolls back, Kafka redelivers |
| After DB commit, before Kafka offset commit | Redelivery does not update DB twice |
| After outbox insert, before DB commit | Outbox rolls back with domain state |
| After DB commit, before outbox publish | Outbox publisher recovers |
| After Kafka publish, before mark-sent | Duplicate output is handled by downstream |
| After payment accepted, before HTTP response | Retry with same `operationId` does not double-charge |
| After email accepted, before local delivery status | Explicit duplicate/missing policy exists |
| After DLT publish, before offset commit | Duplicate DLT does not corrupt replay |
| Rebalance while listener is processing | New consumer does not repeat side effects |
| Retry topic reorders events | Version/state guard handles late events |
| Replay after dedup TTL expires | Business constraints or status checks protect state |

With Spring Kafka, use Testcontainers Kafka and database integration to construct these scenarios, paired with stubbed external APIs implementing idempotency semantics. Verify the **final business outcome**, not merely listener invocation counts.

## 25. Monitoring and reconciliation

Even an idempotent system needs observability for errors and inconsistencies.

| Signal | Purpose |
|---|---|
| Consumer redelivery count | How often records are redelivered |
| Duplicate rejected count | How many duplicate runs inbox/unique constraints blocked |
| Unique business events applied | How many logical events completed |
| Outbox pending count and oldest age | Whether events are waiting too long to publish |
| Outbox publish failures | Whether Kafka or serializers are failing |
| Payment unknown outcomes | Requests that timed out with unclear results |
| API idempotency conflicts | Same key with differing parameters |
| DLT backlog/age | Accumulated failing records |
| Consumer lag | Whether the group keeps up with the source topic |
| Reconciliation mismatch | Discrepancies between DB state and external providers |
| Saga compensation failures | Workflows with incomplete compensations |
| Kafka transaction abort/fencing | Kafka transaction errors |

Avoid using `eventId`, `paymentId`, or `operationId` as metric labels due to unbounded cardinality. Record them in structured logs under sensitive-data protection policies.

**Reconciliation** means comparing actual state rather than trusting sent messages alone. For example, querying the payment provider to reconcile orders stuck in `PAYMENT_PENDING` too long, or inspecting outbox rows pending past SLA.

## 26. Spring Kafka system design checklist

- Define the exact scope of "exactly once": Kafka output vs. business effect.
- Understand listeners can be re-invoked on crashes/rebalances/retries.
- Do not confuse Kafka producer idempotence with business idempotency.
- Ensure Kafka transactions cover both Kafka outputs and input offsets when Kafka-to-Kafka EOS is needed.
- Ensure downstream needing `read_committed` is configured properly.
- Do not treat databases and external APIs as automatically participating in Kafka transactions.
- For Kafka → DB, use inbox/unique constraints in the same DB transaction.
- For DB → Kafka, use a transactional outbox or equivalent mechanism.
- Expect outbox publishers can send duplicates; ensure downstream deduplicates.
- Keep `eventId`, `commandId`, and `operationId` stable across retries, restarts, and replays.
- Equip payments/APIs with idempotency keys and status lookups when available.
- Define policies for ambiguous HTTP timeouts.
- Track delivery state for Email/SMS and respect provider limitations.
- Use deterministic keys / conditional writes for object storage.
- Use sagas and durable state for multi-resource workflows.
- Guard per-aggregate ordering with versions and state transitions.
- Keep dedup retention longer than the replay horizon.
- Never treat DLT/retries as proof that no side effects occurred.
- Fault-injection tests cover crashing after DB commit but before Kafka offset commit.
- Monitor duplicates, outbox lag, unknown outcomes, and reconciliation.
- Assign owners and procedures for resolving inconsistent states.

**Conclusion:** Kafka EOS is a strong guarantee for **Kafka records and offsets participating in the same Kafka transaction**, yet is not a default distributed transaction across databases, HTTP, emails, or storage. In Spring Kafka, safe operation means accepting that redeliveries can occur and designing each side effect so replays never corrupt final state. Transactional inbox/outbox, operation IDs, idempotency, sagas, and reconciliation are the decisive building blocks whenever a system steps outside Kafka's boundaries.

