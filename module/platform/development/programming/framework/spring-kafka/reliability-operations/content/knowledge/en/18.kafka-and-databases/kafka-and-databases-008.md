# Compensation After Primary Commit

In **Spring Kafka combined with a database**, **compensation after primary commit** is how business state is recovered when one transaction has **committed successfully on the primary resource** while another transaction or dependent step **fails to complete**. For instance, the database has saved an order, yet the Kafka transaction publishing the corresponding event fails; or Kafka has committed an event, yet the subsequent database transaction rolls back.

Because **the primary transaction has already committed**, the application cannot call rollback to erase that commit decision. Two different directions exist: **forward recovery**, meaning continuing to complete the missing secondary step; or **compensation**, meaning executing a new business action to bring the system to an acceptable state. When the secondary commit merely times out and it is unclear whether it succeeded, **reconciliation** is required before choosing.

Spring can synchronize a Kafka transaction's lifecycle with another transaction manager, but this **does not automatically create an atomic distributed transaction between Kafka and the database**. This is why transactional outbox, idempotency, and saga state machines are especially critical in operations.

## 1. Primary commit and secondary commit

A business operation may affect two systems:

- **Database**: stores orders, payments, inventory reservations, or workflow state.
- **Kafka**: emits domain events, sends commands, or commits output records and input offsets inside a Kafka transaction.

In a model with an ordered commit sequence:

~~~text
First transaction COMMIT    -> primary commit
Second transaction COMMIT   -> secondary commit
~~~

The names primary/secondary describe **commit order**, not that Kafka or the database always holds a fixed role.

**Database-first** example:

~~~text
T0: Begin database transaction
T1: INSERT order and RESERVED status
T2: Prepare to send OrderReserved via Kafka
T3: DATABASE COMMIT succeeds           <- PRIMARY
T4: KAFKA TRANSACTION COMMIT fails     <- SECONDARY
~~~

After T3, the order is already committed data. An exception at T4 cannot make T3 disappear.

**Kafka-first** example:

~~~text
T0: Begin Kafka transaction
T1: Send OrderCreated
T2: Prepare database insert
T3: KAFKA COMMIT succeeds               <- PRIMARY
T4: DATABASE COMMIT fails             <- SECONDARY
~~~

The Kafka event may already have been read by `read_committed` consumers that executed side effects. Rolling back the database at T4 does not retract the committed event.

## 2. Why can't the primary be rolled back after commit?

Transaction rollback only affects **uncommitted** changes. Once the database commits successfully, the new rows may already have been read by other queries, observed by triggers/CDC, or acted upon by other workflows.

With Kafka, committing a transaction makes transactional records visible to consumers using `isolation.level=read_committed`. **Aborting another transaction** cannot delete records already committed in an earlier transaction.

Scenario diagram:

~~~mermaid
flowchart TD
    A["Primary transaction"] --> B{"Primary commit"}
    B -->|Failed| C["Rollback/retry while still valid"]
    B -->|Succeeded| D["Primary state committed"]
    D --> E["Secondary transaction"]
    E --> F{"Secondary outcome"}
    F -->|Succeeded| G["Business flow completed"]
    F -->|Confirmed failure| H["Forward recovery or compensation"]
    F -->|Unknown| I["Reconciliation before deciding"]
    H --> J["New transaction / workflow recovery"]
    I --> J
~~~

Never write code like:

~~~java
try {
    commitPrimary();
    commitSecondary();
} catch (Exception e) {
    rollbackPrimary(); // Cannot roll back an already-completed commit.
}
~~~

This is only pseudocode illustrating an **anti-pattern**. After the primary commit, you need a new transaction and business rules to compensate, if compensation is appropriate.

## 3. Rollback, forward recovery, compensation, and reconciliation

These four concepts must be distinguished:

| Concept | When it occurs | Effect |
|---|---|---|
| **Rollback** | Transaction has not committed | Discards uncommitted changes of that transaction |
| **Forward recovery** | Primary committed, secondary incomplete | Re-executes/completes the secondary action |
| **Compensation** | Primary committed, business effect must be reversed | Executes a new action: cancel, release, refund |
| **Reconciliation** | Commit outcome or business state is unclear | Cross-checks state and decides the next step |

For example, the order database committed and Kafka was unavailable for five seconds. If the order is still valid, **forward recovery to publish OrderCreated** is the sensible choice. Deleting the order merely because of a brief network glitch usually causes business data loss.

Conversely, if payment capture committed yet fulfillment cannot proceed past its deadline, the application may need to **refund** and **cancel the order**. A refund is a new transaction, not a rollback of the capture transaction.

## 4. Spring Kafka transaction synchronization is not 2PC

In Spring, multiple transaction managers can coexist:

- **JpaTransactionManager** or **DataSourceTransactionManager** for the database.
- **KafkaTransactionManager** for the transactional Kafka producer.

Some configurations allow `KafkaTemplate` to join a Kafka transaction synchronized with a Spring-managed database transaction. Spring coordinates begin/commit/rollback in the expected order, yet does not turn the two systems into an atomic **two-phase commit (2PC)** with a shared prepare/commit decision.

~~~text
DB transaction: BEGIN ... COMMIT OK
Kafka transaction: BEGIN ... COMMIT ERROR
~~~

An error in the secondary commit may be surfaced to the caller depending on the Spring Kafka version's behavior, but the database **has already committed**. Never conclude the DB rolled back just because the Java method ultimately threw an exception.

Across Spring Kafka versions, how secondary commit exceptions propagate and how transaction managers are configured can vary. In operations, verify the **effective commit order** and **actual state of each resource** rather than guessing from annotation names.

## 5. Failure windows in database-first

Suppose a service creates an order in the DB and publishes `OrderCreated` to Kafka:

~~~mermaid
sequenceDiagram
    participant U as API client
    participant S as OrderService
    participant DB as Database
    participant K as Kafka
    participant R as Recovery worker

    U->>S: Create order
    S->>DB: BEGIN, insert order
    DB-->>S: Prepared business data
    S->>DB: COMMIT
    DB-->>S: COMMIT OK
    S->>K: Send/commit OrderCreated
    K--xS: Timeout or failure
    Note over DB,K: DB commit is not rolled back
    R->>DB: Read durable operation/outbox state
    R->>K: Retry publish or reconcile
~~~

Multiple failure windows exist:

1. **Process crashes after DB commit, before Kafka send**: an in-memory callback alone is lost. Without durably storing publish intent, the event can be lost.
2. **Kafka send fails**: the DB remains committed.
3. **Kafka send is ACKed, yet Kafka transaction commit fails**: transactional output cannot be treated as committed.
4. **Kafka commit succeeds, yet response is lost**: the application receives a timeout while the actual result may have succeeded.
5. **Kafka publish succeeds, application crashes before saving completion state**: a retry can produce duplicate records.

No simple catch/rollback block handles every case. You need durable intent, idempotency, and reconciliation.

## 6. Failure windows in Kafka-first

When Kafka is primary:

~~~text
Kafka OrderCreated COMMITTED
Database INSERT order fails
~~~

Downstream consumers may already have:

- Reserved inventory.
- Started fulfillment.
- Sent notifications.
- Created a payment authorization.

You cannot delete the committed event. Options to consider:

1. **Forward recovery of the database** when the order can be recreated with the exact identifier, version, and without violating invariants.
2. **Compensating event**, such as `OrderCreationCancelled` with the same correlation/operation ID.
3. **Saga recovery**, asking services that executed side effects to undo them sequentially per business semantics.
4. **Manual review** if an action cannot be safely compensated.

Do not send a compensating event immediately when a Kafka commit response times out before knowing whether the Kafka commit succeeded. Emitting a cancellation for a creation event that never committed can corrupt downstream state machines.

## 7. Decision matrix after primary commit

| Primary | Secondary | Certainty | Action |
|---|---|---|---|
| Uncommitted | Not executed | Clear | Roll back/retry original transaction |
| Committed | Not started | Clear | Forward recovery from durable intent |
| Committed | Confirmed failure, retryable | Clear | Retry secondary with `BackOff` |
| Committed | Permanent failure | Clear | Business compensation if domain requires |
| Committed | Committed | Clear | COMPLETED; no compensation |
| Committed | Commit timeout | **UNKNOWN** | Reconcile; do not compensate blindly |
| Primary timeout | Secondary not run | **UNKNOWN** | Verify primary first |
| Compensation started | Compensation failing | Clear/unknown | Retry compensation idempotently or escalate |

**UNKNOWN does not equal FAILED.** A timeout only states the caller did not receive a reliable answer, not that the transaction did not commit.

## 8. When is forward recovery better than compensation?

If primary state remains valid and the secondary step is an operation that can complete late, **forward recovery** is usually preferred.

Examples:

- Database order created, Kafka outage lasts 20 seconds: continue publishing `OrderCreated` once the broker recovers.
- Outbox row is `PENDING`, producer lacks ACL: fix the ACL and let the relay publish.
- Kafka event committed, DB projection service was down: replay the event or wait for projection recovery.
- Inventory reserved, billing service returns temporary HTTP 503: retry per policy before deciding to cancel.

Compensation should be a **business decision**, not an automatic reflex to a technical error. Some systems enforce deadlines; once the secondary step cannot complete within the deadline, forward recovery no longer preserves invariants and compensation becomes appropriate.

~~~mermaid
flowchart TD
    A["Primary committed"] --> B{"Secondary outcome confirmed?"}
    B -->|Not yet| C["RECONCILING"]
    C --> B
    B -->|COMMITTED| D["COMPLETED"]
    B -->|FAILED or NOT_STARTED| E{"Secondary retryable and within deadline?"}
    E -->|Yes| F["RETRY_PENDING -> forward recovery"]
    F --> B
    E -->|No| G{"Compensation valid?"}
    G -->|Yes| H["COMPENSATING"]
    H --> I["New compensating transaction"]
    I --> J["COMPENSATED once confirmed"]
    G -->|No| K["MANUAL_REVIEW"]
~~~

## 9. Transactional outbox: usually preferred for DB-first

**Transactional outbox** addresses the core problem: **the database has committed, yet the information to publish is not yet durable**.

Within the same DB transaction, the service writes:

1. Domain state, such as a new order.
2. An outbox event describing **the intent to publish a Kafka message**.

After commit, a separate relay reads the outbox and publishes to Kafka.

~~~mermaid
flowchart LR
    API["Create order"] --> TX["Database transaction"]
    TX --> O["orders"]
    TX --> E["outbox_events"]
    O --> COMMIT["DB COMMIT"]
    E --> COMMIT
    COMMIT --> W["Outbox relay / CDC"]
    W --> K["Kafka"]
    W --> RETRY["Retry / checkpoint publish"]
~~~

If the DB commit succeeds, both the order and event intent exist together. If the DB rolls back, both roll back. A process crash before publishing does not erase the outbox row.

Outbox does not create an atomic distributed commit with Kafka. After a successful Kafka publish, the relay can crash before marking `PUBLISHED`, leading to **duplicate publishes on retry**. Downstream consumers require idempotency.

## 10. Example outbox schema

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(128) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload TEXT NOT NULL,
    publish_state VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    last_error TEXT NULL
);

CREATE INDEX idx_outbox_publish_state
    ON outbox_events (publish_state, next_attempt_at, created_at);
~~~

This schema is illustrative; timestamp types, JSON types, and indexing strategies depend on the database. With multiple relay instances, add **claim/lease** fields or row-level locking to stop two workers from publishing the same row concurrently by mistake.

Example states:

| State | Meaning |
|---|---|
| PENDING | DB committed intent, publish not yet processed |
| IN_FLIGHT | Worker claimed the event and is sending it |
| RETRY_PENDING | Publish failed or response uncertain |
| PUBLISHED | Confirmed published per producer/transaction policy |
| QUARANTINED | Config/schema error or policy exhausted; needs investigation |

Do not let `IN_FLIGHT` linger forever if a worker crashes. Claims should carry a timeout/lease, and recovery workers must reclaim expired leases.

## 11. Writing domain state and outbox in the same transaction

Spring service example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCreationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional("transactionManager")
    public void createOrder(CreateOrderCommand command) {

        Order order = orders.insert(
                command.orderId(),
                command.items()
        );

        OutboxEvent event = OutboxEvent.pending(
                command.eventId(),
                "OrderCreated",
                String.valueOf(order.id()),
                serialize(order)
        );

        outbox.insert(event);
    }
}
~~~

In this example, `OrderRepository`, `OutboxRepository`, `Order`, `OutboxEvent`, `CreateOrderCommand`, and `serialize` are application-defined domain APIs. The transaction manager named **transactionManager** must govern the database transaction containing both repository writes.

If inserting the outbox fails, the order insert also rolls back. If the commit succeeds, both persist together. Never replace the outbox insert with an in-memory Kafka send callback if events must survive crashes.

## 12. Outbox relay and publish acknowledgement

A relay executes a cycle:

1. Claim an eligible `PENDING`/`RETRY_PENDING` row.
2. Resolve topic, key, payload, and event ID.
3. Publish with an appropriate `KafkaTemplate`.
4. Verify send result or Kafka transaction commit if using a transactional producer.
5. Mark `PUBLISHED` in a new DB transaction.
6. If publishing fails, update `attempts`/`next_attempt_at` and schedule retry.

Java pseudocode:

~~~java
public void publish(OutboxEvent event) {

    kafkaTemplate.send(
            event.destinationTopic(),
            event.aggregateId(),
            event.payload()
    ).join();

    outboxStateService.markPublishedInNewTransaction(
            event.eventId()
    );
}
~~~

The snippet illustrates a **non-transactional** producer send and modern Spring Kafka's future API. If using a Kafka transaction, treat **transaction commit** as the committed output boundary; a completed send future does not replace commit.

If the relay dies **after a successful Kafka publish but before DB `markPublished`**, the event is resent. To stay safe, keep the event ID unchanged across retries and ensure downstream consumers handle events idempotently.

Never mark `PUBLISHED` before Kafka send/commit is confirmed per policy. A flag set too early can leave an event stranded permanently.

## 13. Idempotent consumer with an inbox table

Outbox provides reliable publishing; **inbox** prevents duplicate side effects when records are redelivered.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer service:

~~~java
@Transactional("transactionManager")
public void reserveInventory(OrderCreated event) {

    boolean firstTime =
            processedEvents.insertIfAbsent(
                    "inventory-service",
                    event.eventId()
            );

    if (!firstTime) {
        return;
    }

    inventory.reserve(
            event.orderId(),
            event.items()
    );
}
~~~

`insertIfAbsent` must be **atomic** using a unique constraint or equivalent database statement. The marker and inventory changes must live in **the same DB transaction**. If the transaction rolls back, the marker also rolls back so the next retry remains valid. If the DB commits while the Kafka offset stays uncommitted, redelivery does not reserve inventory a second time.

## 14. When is actual compensation needed?

Some workflows cannot wait forever for the secondary step:

- A reservation expires before downstream confirms.
- Payment is captured, yet fulfillment cannot proceed.
- A workflow must complete within an agreed SLA.
- A committed action makes the next step impossible.
- An external API returns a final rejection rather than a transient error.

In these cases, you need a **business-level compensating transaction**. Examples:

| Primary action | Compensation |
|---|---|
| OrderCreated | OrderCancelled with audit trail |
| InventoryReserved | ReleaseInventory |
| PaymentCaptured | RefundPayment referencing original capture |
| ShippingRequested | CancelShipment if provider supports it |
| AccessGranted | RevokeAccess |
| EmailSent | Send correction; cannot unsend |
| Kafka event committed | Publish a new compensating event |

Compensation is not always a perfect undo. Refunds can take time or incur fees; sent emails cannot be recalled; consumed inventory may no longer be safely releasable.

## 15. Designing a saga state machine

A durable workflow can use:

~~~text
PENDING
  |
  v
PRIMARY_COMMITTED
  |
  +--> SECONDARY_PENDING
           |
           +--> COMPLETED
           |
           +--> RETRY_PENDING
           |
           +--> COMMIT_OUTCOME_UNKNOWN --> RECONCILING
           |
           +--> COMPENSATING
                    |
                    +--> COMPENSATED
                    |
                    +--> COMPENSATION_RETRY
                    |
                    +--> MANUAL_REVIEW
~~~

This is an **application-defined** state machine, not a default Spring Kafka enum.

An operation row should store:

| Field | Purpose |
|---|---|
| operation_id | Logical identifier across the entire workflow |
| aggregate_id | Order or business entity |
| primary_resource | Database/Kafka or service that committed |
| primary_status | COMMITTED/UNKNOWN/etc. |
| secondary_status | PENDING/COMMITTED/FAILED/UNKNOWN |
| compensation_status | NONE/REQUESTED/IN_PROGRESS/COMPLETED/FAILED |
| event_id | Stable message identifier |
| version | Optimistic concurrency/fencing for state transitions |
| attempts | Retry count |
| next_attempt_at | Durable retry schedule |
| deadline_at | Business deadline |
| last_error | Sanitized last error excluding sensitive data |

Never keep state solely in RAM or rely on an in-memory scheduled task: a crash will wipe out all recovery intent.

## 16. Compensation example: releasing a reservation

After the primary commit, the workflow can transition to `COMPENSATING` and run a new database transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationCompensationService {

    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    public ReservationCompensationService(
            ReservationRepository reservations,
            OutboxRepository outbox) {
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional("transactionManager")
    public void compensate(
            String operationId,
            long orderId) {

        Reservation reservation =
                reservations.lockByOrderId(orderId)
                        .orElseThrow();

        if (reservation.isReleased()) {
            return;
        }

        if (!reservation.mayRelease()) {
            throw new IllegalStateException(
                    "Reservation requires manual review"
            );
        }

        reservation.release();

        outbox.insertIfAbsent(
                operationId + ":inventory-released",
                "InventoryReleased",
                String.valueOf(orderId),
                toPayload(reservation)
        );
    }
}
~~~

This code is domain-illustrative. `lockByOrderId`, `mayRelease`, `insertIfAbsent`, and `toPayload` must be implemented per your database/application. Core points:

- Never call rollback on the already-committed primary transaction.
- Open a **new transaction** for the compensation state.
- Preserve idempotency: calling twice does not release twice.
- Write the compensation event to the outbox **in the same transaction**.
- Use a stable operation ID across retries.

If releasing requires calling an external service, this transaction should record `ReleaseInventoryRequested` and await acknowledgement from that service, rather than marking released the moment the command is sent.

## 17. A compensating event does not delete a committed event

If `OrderCreated` has already been committed to Kafka, the system cannot erase it with a Kafka rollback in a new transaction. Instead, publish an event:

~~~json
{
  "eventId": "order-42-cancelled-v1",
  "operationId": "order-42-create",
  "orderId": 42,
  "type": "OrderCancelled",
  "reason": "PAYMENT_REJECTED",
  "originalEventId": "order-42-created-v1"
}
~~~

Downstream consumers must understand the sequence:

~~~text
OrderCreated -> InventoryReserved -> OrderCancelled -> InventoryReleased
~~~

Not every consumer observes and processes events at the exact same moment. Therefore, maintain state/versioning, deduplication, and handling for late-arriving events.

In particular, a tombstone in a compacted topic is not a general rollback mechanism for Kafka events. A tombstone is a new record with specific semantics for log compaction and consumers.

## 18. Unknown secondary commit outcome

A difficult scenario:

~~~text
T0: Database primary COMMIT OK
T1: Producer sends Kafka commitTransaction()
T2: Broker processes commit
T3: Network timeout before client receives response
~~~

The application knows the DB committed and the Kafka commit **may** have succeeded. It cannot be sure from a timeout exception alone.

Actions **not to take immediately**:

- Permanently marking the secondary step `FAILED`.
- Deleting the order or initiating a refund.
- Emitting `OrderCancelled` without inspecting domain state.
- Sending a fresh event with a different event ID and treating it as a new task.
- Calling abort locally and declaring the broker never committed.

Reconcile using available sources of truth: operation state, outbox event ID, producer transaction outcome where observable, Kafka audit/consumer state, downstream inbox, and business state.

If you cannot read back the exact commit outcome of a send, the robust path is typically **retrying with the same logical event ID** paired with idempotent downstream consumers. For a Kafka transactional producer in a fatal/fenced state, close and recreate producers per client contract instead of blindly reusing it.

## 19. Kafka send ACK differs from Kafka transaction commit

Three distinct milestones:

| Milestone | What can be concluded? |
|---|---|
| `KafkaTemplate.send()` called | Producer was asked to send |
| Send future succeeds | Broker ACKed writing the record per producer config |
| Kafka transaction commit succeeds | Transactional record is in committed state |
| Downstream business ack | Another service confirmed business processing |

With a transactional `KafkaTemplate`, a successful send future **does not mean the transaction committed**. Without a Kafka transaction, a producer ACK still does not prove a downstream business action succeeded.

A compensation workflow must be driven by **business outcomes**, not by waiting on a Kafka send future and immediately marking the saga `COMPLETED`.

## 20. Spring transaction proxies and where to catch exceptions

With `@Transactional`, Spring normally commits the transaction when the method returns and the transaction interceptor exits scope. Thus, a `catch` **inside the `@Transactional` method** may miss exceptions raised at the commit boundary after the method body returns.

If you need to handle exceptions from the call, place the caller outside the transaction proxy:

~~~java
@Component
public class CreateOrderCommandHandler {

    private final PrimaryOrderService primary;
    private final RecoveryCoordinator recovery;

    public CreateOrderCommandHandler(
            PrimaryOrderService primary,
            RecoveryCoordinator recovery) {
        this.primary = primary;
        this.recovery = recovery;
    }

    public void execute(CreateOrderCommand cmd) {
        try {
            primary.create(cmd);
        } catch (RuntimeException failure) {
            // Do not guess whether DB rolled back or committed.
            recovery.reconcile(
                    cmd.operationId(),
                    failure
            );
            throw failure;
        }
    }
}
~~~

`RecoveryCoordinator` must read **durable status** to determine primary commit, secondary outcome, and policy—never relying on catching an exception as proof.

If a Spring `@Transactional` method is called internally within the same bean, self-invocation can bypass the transaction proxy. Separate service beans cleanly or use `TransactionTemplate` to define explicit transaction boundaries.

## 21. Synchronized Kafka transaction in DB-first

A commonly seen structure:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final KafkaTemplate<String, OrderCreated> kafka;

    public OrderApplicationService(
            OrderRepository orders,
            KafkaTemplate<String, OrderCreated> kafka) {
        this.orders = orders;
        this.kafka = kafka;
    }

    @Transactional("dataSourceTransactionManager")
    public void create(CreateOrderCommand cmd) {

        Order order = orders.insert(cmd);

        kafka.send(
                "orders.created",
                String.valueOf(order.id()),
                new OrderCreated(order.id(), cmd.eventId())
        );
    }
}
~~~

This is an **illustrative pattern**, not something to copy directly as a production reliability solution. Depending on `KafkaTemplate`'s transactional `ProducerFactory`, Spring transaction synchronization, Boot, and Kafka versions, the Kafka transaction can synchronize with the DB transaction. In DB-first ordering, if the DB commits and the Kafka commit fails, the primary state persists.

Do not try to fix this by adding `@Transactional` to the same method and claiming 2PC. When the requirement is **a DB commit must always leave durable publish intent**, choose **insert outbox** rather than a synchronized Kafka send alone.

## 22. Claim/lease and preventing duplicate compensation across workers

After failover or scale-out, multiple recovery workers may scan the same operation:

~~~text
Worker A sees COMPENSATION_RETRY
Worker B also sees COMPENSATION_RETRY
Both send refund/release
~~~

Controlled ownership is needed:

- SQL transactions combined with row locks or `SKIP LOCKED` if supported by the DB.
- Atomic compare-and-set transitions by state and version.
- Leases with `claimed_until` and `claimed_by` to recover when a worker dies.
- Unique constraint on `operation_id + compensation_step`.
- Idempotency keys on downstream APIs.

Example guarded update:

~~~sql
UPDATE saga_operations
SET status = 'COMPENSATING',
    version = version + 1
WHERE operation_id = ?
  AND status = 'COMPENSATION_RETRY'
  AND version = ?;
~~~

If updated rows equals 0, the worker must not proceed with compensation. Another worker may have claimed the operation or its state may have changed.

Never rely solely on an in-process Java `synchronized` lock: it does not protect across pods and disappears on restart.

## 23. Late events and races between forward recovery and compensation

A classic race condition:

1. Forward recovery worker retries `OrderCreated`.
2. Deadline expires; saga transitions to `COMPENSATING`.
3. Forward recovery response arrives late and marks `COMPLETED`.
4. Compensation worker also emits `OrderCancelled`.

Without a state machine and fencing, the system can enter two contradictory states.

Key principles:

- Tie claims/leases to **operation version**.
- Allow transitions only if the current state permits them.
- Once compensation starts, do not let an old forward worker unconditionally commit a success state.
- Late acknowledgements are audited without automatically overturning terminal states.
- Domain events carry versions/sequences so downstream can handle out-of-order arrivals when possible.
- Authority over saga state is the DB row or durable store, not an in-memory variable.

Before cancelling an action that might have succeeded, verify its state and ensure the compensating operation is idempotent.

## 24. Retry budget, deadlines, and manual review

A transient failure should not trigger compensation immediately, yet retrying forever is also inappropriate.

| Policy | Meaning |
|---|---|
| Secondary max attempts | Number of attempts for the secondary step |
| Retry `BackOff` | Wait interval between attempts |
| Secondary deadline | Beyond this point a late secondary completion may no longer be valid |
| Compensation max attempts | Number of compensation retries |
| Compensation deadline | When to alert/escalate |
| Manual review threshold | When an operator must intervene |
| Outbox retention | How long unpublished intent is kept |
| DLT retention | How long failed messages are kept for replay |

For example, a reservation has a 15-minute TTL. If Kafka is unavailable for 5 seconds, retrying publish is sensible. Once the workflow passes its deadline and stock reservation can be released, the saga can start compensation.

Deadlines must be persisted durably in operation state. Never rely solely on `setTimeout`/scheduled callbacks in one instance's memory.

## 25. DLT is not automatic compensation

A DLT holds Kafka records that exhausted retries or could not be processed per policy. It has no knowledge of which side effects business logic already committed in the DB or external APIs.

A DLT record may represent:

- A malformed event with nothing processed yet.
- A DB action that committed while the Kafka offset failed to commit.
- A downstream step permanently rejected.
- A failed outbox relay publish.
- An unexecuted compensation command.
- A completed compensation whose acknowledgement was lost.

Therefore, **never configure every DLT record to cancel an order automatically**. Recovery services must inspect operation state, original event ID, and confirmed side effects.

Replays must preserve event IDs/idempotency keys. When compensation is needed, create a dedicated compensation operation guarded by proper state checks.

## 26. When compensation also fails

Compensation is not guaranteed to succeed on the first try:

- Refund API timeout.
- Inventory service unavailable.
- Database deadlock.
- Serialization/ACL error on the compensation topic.
- Shipment already too late to cancel.

Persist `COMPENSATION_RETRY` state and retry safely. If an API processed a refund but lost the response, reconcile using an idempotency key or provider transaction ID before issuing another refund.

After exhausting retries, route to `MANUAL_REVIEW` with full evidence. Never swallow exceptions and mark `COMPENSATED` just to bring consumer lag down.

Compensation is **a workflow that can fail**, not a cleanup function guaranteed to succeed.

## 27. Kafka-first and saga-based downstream compensation

Suppose the steps are:

~~~text
A. OrderCreated event committed
B. InventoryReserved committed
C. PaymentCaptured succeeded
D. ShipmentCreation FAILED permanently
~~~

Steps A, B, and C already produced side effects. The saga can compensate in dependency order:

~~~text
D failed
   |
   v
Refund payment (compensate C)
   |
   v
Release inventory (compensate B)
   |
   v
OrderCancelled (compensate A)
~~~

This is only one illustrative order; actual ordering depends on the domain. Refunds and releases are typically asynchronous actions. A saga should not report `COMPENSATED` when it has only **requested a refund** before the provider confirms completion.

For multi-step workflows, store state for **each compensating step** instead of a single shared `compensationDone` boolean.

## 28. Observability and metrics

A dashboard tracking only consumer lag will miss partial commits across Kafka + DB.

| Metric | Question |
|---|---|
| `primary_commit_success` | Are primary commits healthy? |
| `secondary_commit_failure` | Are new partial commits occurring? |
| `secondary_outcome_unknown` | How many operations need reconciliation? |
| `outbox_pending_count` | How many events remain unpublished? |
| `outbox_oldest_age` | How long has the oldest event been waiting? |
| `outbox_publish_retry` | Is there a retry storm? |
| `saga_compensating_count` | How many workflows are currently compensating? |
| `compensation_failure_rate` | Are compensation steps failing? |
| `compensation_duration` | How long does compensation take to reach terminal state? |
| `manual_review_backlog` | How many cases require human intervention? |
| `dlt_oldest_age` | Is the DLT aging beyond SLA? |

Example structured log:

~~~text
event=secondary_commit_outcome_unknown
service=order-service
operation_id=create-order-42
aggregate_id=order-42
primary_resource=database
primary_commit=CONFIRMED
secondary_resource=kafka
secondary_outcome=UNKNOWN
outbox_event_id=order-42-created-v1
saga_state=RECONCILING
exception=TimeoutException
~~~

Do not log `secondary_outcome=FAILED` when only a timeout occurred. Never put `operation_id` or `event_id` into high-cardinality metric labels; keep those identifiers in controlled logs/traces.

## 29. Runbook when primary committed and secondary failed

1. Identify operation ID, aggregate ID, event ID, and service.
2. Confirm which resource was primary and verify evidence of primary commit success.
3. Classify secondary state: `NOT_STARTED`, `FAILED_CONFIRMED`, `COMMITTED`, or `UNKNOWN`.
4. If `UNKNOWN`, reconcile before retrying or compensating.
5. Inspect the durable outbox row or saga operation state.
6. Inspect Kafka publish results and Kafka transaction commits if applicable.
7. Inspect external side effects and downstream inboxes.
8. Check deadlines and retry budgets.
9. If forward recovery is valid, claim the operation and retry the secondary step.
10. If no longer valid, transition to `COMPENSATING` using a state guard.
11. Write compensation intent to the outbox in a new transaction.
12. Await and verify business acknowledgement for each compensating step.
13. If compensation fails, retry idempotently or escalate to `MANUAL_REVIEW`.
14. Reconcile final DB/Kafka/downstream states.
15. Audit who decided on compensation and why.
16. Add a test for the failure window that occurred.

Never resolve an incident by manually resetting consumer offsets, deleting records, or deleting database rows without analyzing data loss or duplicate side-effect risks.

## 30. Fault injection and integration testing

Test realistic failure windows:

| Test scenario | Expectation |
|---|---|
| DB rollback before commit | Both order and outbox roll back |
| DB commits then app crashes before Kafka publish | Outbox relay recovers the event |
| Kafka producer timeout | Operation is not blindly marked `FAILED` |
| Kafka send succeeds then relay crashes before `markPublished` | Event may be resent; inbox blocks duplicate side effects |
| Kafka transaction commit outcome unknown | Reconciliation runs; no unconditional compensation |
| Kafka-first commit succeeds, DB rolls back | Saga forward-recovers/compensates per domain rules |
| Compensation transaction commits then Kafka publish fails | Compensation intent remains in outbox |
| Compensation command redelivered | No duplicate refund/release |
| Two workers claim simultaneously | Only one transition takes effect or idempotency protects |
| DLT contains partially processed event | Recovery checks saga state before acting |
| Late retry response arrives while saga is `COMPENSATING` | State guards prevent invalid transitions |
| Compensation API times out after server success | Reconcile via idempotency key |
| Recovery worker restarts after lease timeout | Pending operations are reclaimed |

### Order + outbox + compensation integration test

1. Start database and Kafka via Testcontainers or an equivalent environment.
2. Create an order in a DB transaction containing both the order and outbox row.
3. Assert both commit together.
4. Make Kafka unavailable before relay publish.
5. Verify `PENDING` outbox row persists.
6. Restore Kafka and let the relay send `OrderCreated`.
7. Crash after Kafka ACK before `markPublished`.
8. Restart the relay and confirm the idempotent consumer creates no duplicate side effects.
9. Simulate permanent downstream business failure.
10. Transition saga to `COMPENSATING` and create an outbox compensation event.
11. Confirm downstream applies compensation exactly once.
12. Replay the compensation command and verify idempotency.
13. Reconcile final state and audit trail.
14. Confirm dashboards/alerts reflect both failure and recovery.

Unit testing the `compensate` method cannot prove Kafka transaction outcomes or DB transaction commits; integration tests with fault injection are needed to verify commit boundaries.

## 31. Common implementation mistakes

**Calling rollback after primary commit.** An already-committed transaction cannot be rolled back via that same old transaction.

**Confusing transaction synchronization with an atomic distributed transaction.** DB commit and Kafka commit still leave a failure window.

**Catching an exception and concluding the DB did not commit.** Secondary commit exceptions can arise after the DB committed.

**Sending to Kafka only from an in-memory callback after DB commit.** A process crash loses publish intent.

**Marking an event `PUBLISHED` before producer ACK/transaction commit.** Risks losing events.

**Not keeping event IDs stable across retries.** Downstream cannot deduplicate.

**Compensating immediately on timeout.** The secondary commit may have succeeded while its response was lost.

**Deleting primary data to compensate.** Loses audit history and breaks references already observed by other systems.

**Not guarding against late successes.** Forward retries and compensation can concurrently leave the workflow in contradictory states.

**Assuming DLT means cancel.** DLT only indicates a failed processing path; domain context is required.

**Retrying compensation with a new ID.** Refunds or releases may execute multiple times.

**Holding DB transactions open during slow remote API calls.** Increases lock contention and deadlocks.

**Not persisting compensation progress.** Worker crashes leave the saga unaware of which steps completed.

**Not verifying business acknowledgements.** Sending a command successfully does not mean compensation completed.

## 32. Pre-production checklist

**Transaction boundaries**

- [ ] Commit order and primary/secondary resources are clearly known.
- [ ] Rollback, forward recovery, compensation, and reconciliation are distinguished.
- [ ] `UNKNOWN` secondary outcomes are explicitly recognized.
- [ ] `@Transactional` DB+Kafka is not treated as 2PC.
- [ ] Durable publish intent exists for DB-first when event loss is unacceptable.

**Reliability**

- [ ] Outbox and domain state commit in the same DB transaction.
- [ ] Outbox relay has claims/leases and crash recovery.
- [ ] Event IDs and operation IDs stay stable across retries/replays.
- [ ] Downstream consumers are idempotent via inbox/unique constraints.
- [ ] Compensation actions have dedicated idempotency keys.

**Business logic**

- [ ] State machine and deadlines are defined.
- [ ] Irreversible actions are identified.
- [ ] Compensation requested is distinguished from compensation completed.
- [ ] Manual review path exists for non-compensable workflows.
- [ ] Guards prevent late events from corrupting terminal states.

**Operations**

- [ ] Metrics exist for primary commits, secondary failures, and unknown outcomes.
- [ ] Dashboards track outbox age, retries, saga compensation, and DLT.
- [ ] Alerts exist for stuck compensations and manual review backlogs.
- [ ] Reconciliation runbook defines operator ownership.
- [ ] Fault-injection tests cover failure points after primary commit.
- [ ] Audit trail exists for all compensation and replay steps.

## 33. Design principles

**Compensation after primary commit** means **resolving the consequences of an already-committed change**, not rolling back that transaction. Before acting, confirm the primary commit, classify the secondary outcome, and identify the business goal. If the secondary step can still complete, prefer **forward recovery**; if business rules mandate cancellation, execute a **new compensating transaction** with idempotency, state guards, auditing, and retryability.

With Spring Kafka and a database, a reliable architecture typically uses a **transactional outbox** to retain durable publish intent, an **inbox** to prevent duplicate consumption, and a **saga** for cross-service compensation steps. Never treat a Kafka commit timeout as a confirmed failure. Use reconciliation, stable event/operation IDs, crash tests across every failure window, and state monitoring until each operation reaches a verified **COMPLETED** or **COMPENSATED** state.

This is the practical path to **controlled eventual consistency** between Kafka and a database without assuming two resources share an atomic commit.
