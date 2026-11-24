# Second Transaction Commit Failure

In a Spring Kafka service, many business flows must **both modify data in a database and write or confirm data in Kafka**. For example: saving an order in PostgreSQL and then emitting `OrderCreated`, or reading `PaymentCaptured`, updating a ledger, and committing the consumer offset. It is tempting to feel that simply using `@Transactional` and configuring Kafka transactions will make both operations either succeed together or fail together.

In reality, **the database transaction and the Kafka transaction are two separate transactions**. Spring can coordinate their completion order via transaction synchronization or nested `@Transactional` methods. However, coordination **does not equal an atomic distributed transaction** between the database and Kafka. If the first transaction commits successfully and then the second transaction fails to commit, the first transaction **cannot be rolled back retroactively just by an exception**.

This is one of the most important failure windows in Kafka + database architectures. This lesson explains how the failure occurs, its consequences under each commit order, how to recognize uncertain outcomes, and recovery architectures such as transactional outbox, idempotent consumers, reconciliation, and compensating actions.

## 1. Two transactions are two atomicity boundaries

Suppose a service processes an order creation command:

```text
Client -> OrderService
            |
            +--> Database transaction
            |       INSERT orders
            |       COMMIT DB
            |
            +--> Kafka transaction
                    SEND OrderCreated
                    COMMIT KAFKA
```

The database has its own transaction log and commit/rollback mechanism. Kafka has its own transaction coordinator, transactional producer ID, and commit/abort markers. A database transaction manager cannot revoke a completed Kafka commit; likewise, a Kafka transaction manager cannot automatically undo a confirmed PostgreSQL commit.

| Component | Actual atomicity provided |
|---|---|
| Database transaction | Changes belonging to that database transaction |
| Kafka producer transaction | Kafka records and, in the right setup, consumer group offsets included in the same Kafka transaction |
| Spring transaction synchronization | Coordinates lifecycle and completion order of separate transactions |
| Two `@Transactional` with two managers | Two local transactions executing in order; does not create an atomic distributed commit |
| Transactional outbox | Keeps business change and publish intent **in a single DB transaction**; Kafka publishing is a separate step with retries and deduplication |

**Foundational principle:** a successful commit has already created a durable effect in the first resource. An exception during the second commit only signals that the overall *cross-resource process* did not achieve its goal; it does not automatically revert the first resource.

## 2. Two commit orders and two types of inconsistency

No commit order eliminates the failure window. Changing the order only changes **which side can get ahead of the other**.

### 2.1. Database-first: database commits first, Kafka commits second

```text
BEGIN DB
   |
   +--> INSERT orders
   |
   +--> KafkaTemplate.send(OrderCreated) in Kafka transaction
   |
COMMIT DB                           [SUCCEEDED]
   |
COMMIT KAFKA                        [FAILED]
   |
   v
Database has Order; event may not appear as committed
```

In this state, an order can exist in the database without an `OrderCreated` visible to `read_committed` consumers. If downstream relies solely on the event, it never learns the order was created; caches, search indexes, shipping, or billing may miss information.

If the Kafka commit times out or loses connectivity, the outcome may even be **indeterminate** when the application catches the exception: the broker may have committed with the response lost, or the commit may not have succeeded. Never assume every `commitTransaction()` exception proves the event is completely absent.

### 2.2. Kafka-first: Kafka commits first, database commits second

```text
BEGIN DB
   |
   +--> Modify orders (uncommitted)
   |
BEGIN KAFKA
   |
   +--> SEND OrderCreated
   |
COMMIT KAFKA                        [SUCCEEDED]
   |
COMMIT DB                           [FAILED]
   |
   v
Consumer may see OrderCreated; database may not have Order
```

This is the state where **an event is published while source state has not committed**. A downstream listener may receive the event quickly and query an order ID that does not exist, or trigger business logic based on a DB change that never happened. Kafka-first is not a way to guarantee atomicity; it simply picks the opposite direction of inconsistency.

### Comparison table

| Order | First transaction | Second transaction fails | Danger sign |
|---|---|---|---|
| DB → Kafka | Database committed | Kafka commit errors/uncertain | DB has data, event may be missing |
| Kafka → DB | Kafka committed | Database commit errors/uncertain | Event may be published, DB data missing |

Choosing an order can optimize recovery for a particular business flow, but if requirements prohibit losing events or emitting events without source state, consider **outbox** instead of relying on commit order.

## 3. Spring Kafka synchronizing a Kafka transaction with a DB transaction

Spring Kafka can synchronize a Kafka transaction with a transaction managed by `DataSourceTransactionManager` or another DB transaction manager. When a `@Transactional` method uses the DB as the primary transaction and `KafkaTemplate` uses a transactional producer, normally **the DB commits first and Kafka commits second**.

Foundational configuration example:

```properties
# Producer needs a transactional.id prefix to create Kafka transactions.
# Each concurrently running instance must have its own ID range.
spring.kafka.producer.transaction-id-prefix=order-service-instance-a-

spring.kafka.producer.acks=all
spring.kafka.consumer.enable-auto-commit=false
```

For multi-replica applications, `order-service-instance-a-` is only an illustrative placeholder. Each concurrent instance must be assigned a non-colliding prefix/transactional ID; otherwise producers can be fenced. In addition, the Kafka producer factory, serializers, brokers, and topics must support transactions under the active configuration.

Example service using a DB transaction as the primary transaction:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {

        Order order = orderRepository.save(
                Order.fromCommand(command));

        OrderCreated event = new OrderCreated(
                command.eventId(), order.getId(), order.getStatus());

        // Transactional KafkaTemplate participates in synchronization.
        kafkaTemplate.send("orders-events", order.getId(), event);
    }
}
```

The code assumes `dataSourceTransactionManager` is the DB transaction manager bean, `KafkaTemplate` uses a transactional `ProducerFactory`, and domain classes are defined by the application. Under proper transaction synchronization configuration, `send()` executes inside a Kafka transaction and the Kafka transaction commits after the DB transaction.

**Crucial point:** `send()` returning a future does not mean the Kafka transaction committed. Even if the broker receives the record in an open transaction, `read_committed` consumers only see it after commit. If the Kafka commit fails after the DB already committed, the DB retains the change.

In modern Spring Kafka releases, commit errors from a synchronized transaction after the primary transaction committed are reported to the caller. In some older releases, synchronized commit error reporting differed. Always verify your dependency version and never treat an exception seen by the caller as proof that the DB rolled back.

## 4. Second commit failure: actual state has more than one possibility

Operations teams often say simply "Kafka commit failed," yet three distinct observable situations exist:

1. **Definitely not committed:** the transaction aborted or returned a definitive result that the commit was rejected.
2. **Commit succeeded:** Kafka persisted the commit marker and the producer/client received confirmation.
3. **Outcome uncertain:** the commit request or response was interrupted; the client received a timeout/network exception without enough evidence to confirm whether the transaction committed or not.

The same can happen with a database: the connection drops right at `COMMIT`, leaving the caller unsure whether the DB accepted the commit. Therefore, never inspect only the exception class to decide whether to repeat the entire operation.

```text
Application                  Kafka coordinator
     |                             |
     |------ commitTransaction --> |
     |                             |  may process commit
     |         X network           |
     |<---- no response received -- |
     |
     v
Application reports error; actual state requires reconciliation
```

With a transactional Kafka producer, do not attempt to keep reusing a producer in a fatal error state contrary to client rules. Let the transaction manager run proper abort/close/fencing recovery. A new producer using the next transactional ID can fence the old producer, **but it cannot infer or repair** a prior inconsistency between Kafka and the database.

## 5. Why can't `try/catch` roll back an already-completed commit?

Code like the following often causes misconceptions:

```java
try {
    orderRepository.save(order);
    kafkaTemplate.send("orders-events", order.getId(), event);
}
catch (Exception ex) {
    // Wrong if assuming the DB definitely rolled back.
    throw ex;
}
```

`throw ex` can trigger rollback while **the DB transaction is still open**. However, when the Kafka commit is synchronized **after the DB commit**, the exception can occur once the database has already finished committing. There is no open DB transaction left to roll back.

Calling `orderRepository.delete(order)` as automatic compensation does not guarantee returning the system to its prior state either. Other tasks may already have observed the order, foreign keys or audits may have been written, and the delete itself could fail. If compensation is needed, it must be **an explicitly defined business operation** with an audit trail and retryability, not an implicit undo.

## 6. Reversing the order: Kafka-first via nested transactions

When Kafka must commit before the DB, Spring Kafka lets you use nested `@Transactional` methods with **two distinct transaction managers**, where the outer method uses the DB manager and the inner method uses the Kafka manager.

```java
@Service
public class KafkaOrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders-events", event.orderId(), event);
    }
}
```

Outer method:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaOrderEventPublisher eventPublisher;

    public OrderService(
            OrderRepository orderRepository,
            KafkaOrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional("dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {
        Order order = orderRepository.save(Order.fromCommand(command));
        eventPublisher.publish(new OrderCreated(
                command.eventId(), order.getId(), order.getStatus()));
        // DB commits when the outer method finishes.
    }
}
```

In this flow, calling `eventPublisher.publish(...)` passes through the Spring proxy of **another bean**, allowing the inner method's Kafka transaction to start and commit before the outer DB transaction finishes. If both methods sit in the same class and call `this.publish(...)`, self-invocation can bypass the `@Transactional` proxy, changing the actual order from what was intended.

This design **does not handle** the case where `eventPublisher.publish()` committed Kafka successfully and then the DB commit failed. `OrderCreated` may already be visible to downstream while `orders` has no matching row. Only reverse commit order when you have a clear business reason and a plan for this state.

### Do not confuse `KafkaTransactionManager` with XA

`KafkaTransactionManager` coordinates Kafka producer transactions. `DataSourceTransactionManager` coordinates JDBC transactions. Having a class use two `@Transactional` annotations does not make them participants in an XA two-phase commit. Legacy ways of chaining transaction managers, such as `ChainedKafkaTransactionManager`, were deprecated in corresponding Spring Kafka lines; even with a coordinator committing sequentially, you must still handle partial commits if the second manager fails.

## 7. Kafka consumer → database: the second transaction can fail here too

Failure windows do not only happen when a REST service writes to a DB and publishes an event. They also occur in a listener processing records from Kafka:

```text
Kafka consumer receives PaymentCaptured
          |
          v
Kafka listener container starts Kafka transaction
          |
          v
@Transactional(DB) updates ledger and inbox
          |
          v
DB COMMIT                         [succeeded]
          |
          v
Kafka transaction commit
  (offset or output + offset)    [failed]
          |
          v
Source record may be redelivered after restart/rebalance
```

When a listener runs inside a container-managed Kafka transaction, a separate `@Transactional` business method can commit the database before the container commits the Kafka transaction. If the Kafka commit fails, **the database already has the side effect**, while the group offset may remain unrecorded. On the next delivery, the same `PaymentCaptured` can be processed again.

If the consumer only performs DB operations, you usually do not need Kafka transactions just to achieve an "exactly once" consumer with a DB. A simpler approach is **a DB transaction with inbox/idempotency + consumer offset commit after DB commit**, embracing at-least-once delivery. That way, replays never duplicate business effects.

Example idempotent listener and service:

```java
@KafkaListener(topics = "payments", groupId = "ledger-service")
public void onPayment(PaymentCaptured event) {
    ledgerService.applyOnce(event);
}

@Service
public class LedgerService {

    private final ProcessedEventRepository processed;
    private final LedgerRepository ledger;

    @Transactional("dataSourceTransactionManager")
    public void applyOnce(PaymentCaptured event) {
        // processed_event.event_id has a UNIQUE constraint in the database.
        if (processed.insertIfAbsent(event.eventId())) {
            ledger.credit(event.accountId(), event.amount());
        }
    }
}
```

`insertIfAbsent` here represents an atomic insert into a table protected by a unique constraint; never hand-roll "SELECT to check existence then INSERT" without race-condition protection. The marker insert and ledger update must belong to **the same DB transaction**. If the DB commit succeeds while the Kafka offset commit fails, redelivery encounters the same event ID and skips the duplicate side effect.

## 8. Transactional outbox: preferred solution for DB → Kafka

If an operation **must guarantee that DB state and event publish intent are saved together**, transactional outbox is usually far more durable than committing DB and Kafka sequentially within the same request.

Instead of sending directly to Kafka inside the DB transaction, save an outbox row inside **the same DB transaction** as the business change:

```text
Client / command
     |
     v
BEGIN DATABASE TRANSACTION
     |
     +--> INSERT/UPDATE orders
     |
     +--> INSERT outbox_events
     |
COMMIT DATABASE TRANSACTION
     |
     v
Outbox relay (polling or CDC)
     |
     v
Publish Kafka OrderCreated
     |
     v
Mark outbox as published / advance CDC position
```

If the DB commit fails, neither the order nor the outbox row appears. If the DB commit succeeds while Kafka is unavailable, the outbox row **remains** for retry when Kafka recovers. There is no longer a window where "DB committed and publish intent was lost." The relay may be delayed, yet it does not depend on a live request thread holding the event in RAM.

### Simple schema example

```sql
CREATE TABLE orders (
    id              VARCHAR(64) PRIMARY KEY,
    request_id      VARCHAR(80) NOT NULL UNIQUE,
    status          VARCHAR(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    aggregate_id    VARCHAR(64) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload_json    JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ NULL
);
```

PostgreSQL example; other databases require their own data types and syntax. `request_id` prevents duplicate orders when clients retry requests; `event_id` is the durable identifier used to deduplicate events across relay publish attempts.

### Example saving order and outbox in one DB transaction

```java
@Service
public class PlaceOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional("dataSourceTransactionManager")
    public void place(PlaceOrder command) {
        Order order = orders.insertIfAbsent(command.requestId(), command);

        outbox.insertIfAbsent(
                order.createdEventId(),
                order.id(),
                "OrderCreated",
                serializeEvent(order));
    }
}
```

`insertIfAbsent`, `createdEventId`, and `serializeEvent` are illustrative domain methods, not default Spring Data APIs. When a request is retried, generate a deterministic `event_id` or derive it from an idempotent business key; if a retry generates a fresh UUID and inserts another outbox row, duplicate events can still be emitted.

### Why does an outbox still need idempotency?

Suppose the relay publishes the event to Kafka successfully but crashes **before setting `published_at`**. On restart, the relay sees the unmarked outbox row and publishes it again. Thus outbox solves **never losing publish intent**, yet can send duplicates. Consumers must deduplicate by `event_id`; the relay can enable Kafka producer idempotence, though an idempotent producer does not eliminate duplicates across two separate logical publish attempts.

Outbox relays can use polling with `FOR UPDATE SKIP LOCKED` and backoff, or change-data-capture (CDC) reading the database log. Either way, monitor outbox backlog, publish latency, poison events, and resume strategies.

## 9. Inbox + outbox for Kafka → DB → Kafka flows

When a listener both updates a DB and emits a new Kafka event, you can combine **transactional inbox** and **transactional outbox** inside the same DB transaction:

```text
Kafka input record (eventId = E123)
              |
              v
BEGIN DB TRANSACTION
              |
              +--> INSERT inbox(E123) with UNIQUE constraint
              |
              +--> UPDATE domain state
              |
              +--> INSERT outbox(EventDerivedFromE123)
              |
COMMIT DB TRANSACTION
              |
              v
Container commits Kafka input offset (may fail)

Outbox relay --> Kafka output
```

If the Kafka input offset commit fails, the record is redelivered. Then `inbox(E123)` already exists, so the service recognizes it was processed, **neither updating the DB again nor inserting a second outbox event**. The outbox relay ensures the output publish intent survives even if Kafka is temporarily unavailable. This is a very practical at-least-once + idempotency pattern when two resources lack distributed atomicity.

Use the aggregate key as the Kafka key to preserve partition ordering if needed; the outbox/relay must also preserve event order per aggregate. If multiple relay workers pick up outbox rows in unstable order, `OrderShipped` might be published before `OrderCreated`. Solve this in relay design, not just via DB unique constraints.

## 10. Second transaction fails with uncertain outcome: reconcile

When logs show `commitTransaction failed`, the runbook should not immediately "resend the event." If the commit actually succeeded and only the response was lost, resending can produce a duplicate. Reconcile using verifiable keys:

- **Database:** look up the order/transaction by request ID, aggregate ID, event ID, or committed state version.
- **Kafka:** use a `read_committed` consumer or supporting audit/index to verify whether the event ID appeared as a committed record. Searching for an event by key in a Kafka log can be expensive; plan verification capabilities ahead of time.
- **Outbox:** verify outbox row presence, published marker/checkpoint, and publish/ack attempt counts.
- **Downstream consumers:** check inbox/event-processing ledgers to see whether side effects completed.

Finding a record in Kafka does not by itself prove DB state is right; finding a DB row does not prove the Kafka event committed. Conclusions must check **both sides** and business invariants.

Example reconciliation table:

| DB state | Kafka event committed | Action to consider |
|---|---|---|
| Yes | Yes | Verify downstream processed it; avoid unnecessary republishes |
| Yes | No | Emit compensating/missing event via an idempotent job; ideally backed by outbox |
| No | Yes | Investigate ghost event; emit compensating event or restore state if business allows |
| No | No | Inspect failed/uncommitted request; retry with idempotency key if appropriate |
| Indeterminate | Indeterminate | Pause actions causing new side effects, gather evidence, and escalate |

Do not assume both columns can always be confirmed solely from one producer log: multiple publish attempts, retention, compaction, and schemas complicate lookups. The goal is designing the system to be **reconcilable** from day one.

## 11. Compensation: when the first commit cannot be undone

When Kafka-first leaves a visible event while the DB commit fails, the system may have to emit a **compensating event** such as `OrderCreationCancelled` or move the workflow to `FAILED_REQUIRES_RECONCILIATION`. Compensation should represent a new business action rather than attempting to erase Kafka history.

```text
OrderCreated published on Kafka
             |
             v
DB commit fails
             |
             v
Reconciliation detects missing Order in DB
             |
             v
OrderCreationCancelled / compensation workflow
             |
             v
Downstream idempotently applies compensating state
```

Compensation itself can fail or arrive late, so it needs its own retries, idempotency, correlation IDs, and monitoring. If downstream already executed an irreversible action (such as sending an email or executing a bank transfer), a compensating event does not make that action vanish. Define compensability boundaries clearly before choosing Kafka-first.

With DB-first and a missing Kafka event, the compensating emission is usually **an event representing current DB state**, with a stable ID and provenance so it causes no duplicate if the original Kafka commit actually succeeded. Outbox avoids having to infer missing events by comparing two systems post-incident.

## 12. Role of retries, DLT, and `DefaultErrorHandler`

Retries and Dead Letter Topics (DLT) handle **failed record consumption**; they do not fix a partial commit between a DB and Kafka. For example, a listener committed to the DB, then the Kafka offset commit failed, and the record was redelivered. If the listener is not idempotent, whether retry succeeds or routes to the DLT, the DB can still be updated twice.

`DefaultErrorHandler` and `DeadLetterPublishingRecoverer` should focus on exception classification, backoff, and storing unprocessable records. When an exception happens after the DB already committed, never assume retrying the whole business method is safe.

A DLT is useful for:

- Temporarily quarantining events the consumer cannot process.
- Preserving original topic/partition/offset and exception details for investigation.
- Supporting controlled replay after bug fixes and idempotency protections.

However, a DLT **is not** a guarantee that every DB change has a matching Kafka event. In DB-first, a second-transaction failure can occur in a request publisher before any consumer record or DLT exists. That case requires an outbox or dedicated reconciliation.

Furthermore, if the DLT publisher itself uses transactions, committing the DLT send and source offset must still be configured properly to prevent record loss or duplicates. "The record was sent to the DLT" does not mean an earlier DB commit can be revoked.

## 13. Exception handling rules after the first transaction commits

When the framework reports a failure after the first commit, safe responses typically include:

1. **Do not tell the caller all changes rolled back.** HTTP 500 only indicates the request did not complete as intended; it does not prove the DB has no data.
2. **Do not blindly retry the whole command.** Inputs need an idempotency key and logic recognizing already-executed state.
3. **Mark the outcome as uncertain**, such as `PENDING_RECONCILIATION`, if the system supports that state.
4. **Log/audit correlation IDs** and durable identifiers to trace both resources.
5. **Run reconciliation or outbox relay** with bounded retries and age-based alerts.
6. **Compensate only per explicit business definitions**, never ad-hoc manual deletion of committed data.

HTTP APIs can choose to return `202 Accepted` with a request ID when async steps remain incomplete, or return an error code allowing clients to poll status. Returned statuses must reflect actual workflow state; never return "failed" after a DB commit unless the system detects and deduplicates client retries.

For an order creation API, a unique `request_id` and a status lookup endpoint by request ID are essential to avoid creating two orders when callers retry after timeouts.

## 14. Observability and runbook for second-commit failures

Monitoring must go beyond Kafka producer errors. Design metrics and alerts for **the gap between the two systems**:

| Metric / trace | Purpose |
|---|---|
| DB transaction success/error | Know whether the primary operation committed |
| Kafka transaction commit/abort/timeout | Detect failure windows and producer fencing |
| Outbox unpublished count and oldest age | Spot DB-persisted publish intent not yet received by Kafka |
| Relay publish attempts, success, duplicates | Distinguish normal backlog from duplicate sends |
| Inbox duplicate rate | Measure redelivery rates and idempotent consumer hits |
| Consumer lag, offset commit errors | Detect inputs likely to be redelivered after DB side effects |
| Reconciliation mismatch count | Spot DB state missing events or Kafka ghost events |
| Compensation pending/failed | Track unresolved inconsistency repair obligations |

Suggested runbook:

1. Record exactly which transaction committed first and which manager reported the error.
2. Identify `requestId`, `eventId`, `orderId`, topic, partition, offset, and transaction ID if available.
3. Verify whether the first transaction actually committed; do not infer from the second transaction's exception.
4. Check Kafka transaction state/record visibility using a `read_committed` consumer or pre-built audit.
5. Verify whether an outbox/inbox row and downstream side effects exist.
6. Pause bulk replays while commit outcomes remain unclear.
7. Apply reconciliation, missing-event publish, or compensation per the business runbook.
8. Monitor until both systems converge, document root cause, and revise design if needed.

During an incident, never arbitrarily reset consumer group offsets to "fix" missing events. Resetting backward can duplicate side effects; resetting forward can skip unprocessed records. Offset commits and event publishes are separate state tracks requiring independent verification.

## 15. Common failure scenarios

| Symptom | Possible cause | Approach |
|---|---|---|
| API returns 500, yet order exists | DB commit succeeded, synchronized Kafka commit failed | Use request ID to check status; outbox/reconciliation instead of creating a new order |
| Kafka event exists, DB has no order | Kafka-first commit succeeded, DB commit failed | Reconcile, compensate, or move architecture to outbox |
| One payment posted to ledger twice | DB committed first, Kafka offset commit failed, record redelivered | Inbox/unique constraint and single DB transaction wrapping marker + side effect |
| Duplicate events appear after retry | Publish actually committed, response timed out, caller republished | Stable event ID and idempotent downstream; do not equate producer idempotence with business dedup |
| DB-first where app thought everything rolled back | Exception happened after DB commit | Log two commit phases, report uncertain status |
| Kafka transaction fenced during scaling | Multiple instances share transactional ID or old producer not replaced cleanly | Scope transactional ID/prefix per instance; monitor fencing |
| Outbox grows continuously | Kafka outage, relay serializer/ACL error, or poison payload | Alert on oldest age, retry with backoff, relay DLT/quarantine, and investigate |
| Re-running reconciliation emits duplicate events | Missing idempotency or non-durable job checkpoint | Use stable event IDs and deduplication by business key |
| Two `@Transactional` do not invert commit as expected | Self-invocation bypassed Spring proxy or wrong manager selected | Separate beans, explicit transaction manager names, and test flow |

## 16. Integration test scenarios for failure windows

To prove the system survives second-commit failures, actively inject faults at transaction boundaries. Use Testcontainers for Kafka and the database, adding fault injection at producer/DB/network layers or controlled test adapters. Never mock `KafkaTemplate.send()` alone and claim commits are tested: failures can happen **after the send future completes**, at `commitTransaction()`.

Valuable scenarios:

1. **DB-first success:** DB has row, Kafka has committed event, downstream processes once in business terms.
2. **DB-first Kafka commit failure:** DB retains row; reconciliation/outbox ensures the event is eventually published.
3. **Kafka-first DB commit failure:** Kafka event may be visible; compensation or reconciliation detects divergence.
4. **Timeout right at Kafka commit:** test the uncertain-outcome branch; avoid unbounded republishing.
5. **Crash after DB commit, before Kafka commit:** restart preserves publish intent when backed by outbox.
6. **Crash after Kafka publish, before marking outbox:** relay republishes without duplicating downstream side effects.
7. **Consumer DB commit succeeds, offset commit fails:** same input redelivered, inbox unique constraint blocks duplicate writes.
8. **Multiple instances and rebalances:** duplicate delivery causes no lost funds, corrupted order state, or duplicate business events.
9. **Extended outbox relay outage:** backlog triggers alerts and drains cleanly once Kafka/ACLs recover.
10. **Schema/serializer failure:** faulty event is quarantined cleanly without corrupting DB state, with a replay plan.

When testing, assert **final DB data**, **unique committed event IDs in Kafka**, **committed consumer offsets**, **actual side-effect counts**, and **outbox/inbox states**. Counting Java method or listener invocations does not prove business-level exactly-once.

## 17. Which requirements should drive architectural choice?

| Primary requirement | Typical suitable approach |
|---|---|
| DB is primary data store; state-change events must never be lost | Transactional outbox + relay/CDC + idempotent consumers |
| Consume Kafka, update DB, never duplicate side effects | Transactional inbox + DB unique constraint; at-least-once offset commits |
| Consume Kafka then produce Kafka, no external resources | Kafka transaction + offsets in same transaction, `read_committed` downstream |
| Multiple systems with long business flows needing compensation | Saga/workflow + compensation + reconciliation |
| Best-effort sync acceptable with rare minor divergence and repair process | Transaction synchronization with clear monitoring and repair jobs |

No single annotation solves every case. For payments, inventory, or critical data, favor architectures that are **crash-recoverable** and **reconcilable**, rather than relying on the happy path where two sequential commits always succeed smoothly.

## 18. Core principles

1. Databases and Kafka have separate transaction boundaries; Spring transaction synchronization does not create an atomic cross-system commit.
2. **Once the first commit succeeds, a second-transaction failure cannot automatically roll back the first.**
3. DB-first risks **DB having data while the Kafka event is missing**; Kafka-first risks **Kafka having the event while DB data is missing**.
4. Timeouts during commit can leave outcomes **uncertain**; reconcile before retrying or compensating.
5. Never equate a successful `KafkaTemplate.send()` with a completed Kafka transaction commit.
6. Use stable request/event IDs and idempotency so clients, relays, and consumers can retry safely.
7. For critical DB→Kafka flows, prefer transactional outbox; for Kafka→DB, prefer an inbox inside the same DB transaction as side effects.
8. Kafka transactions are powerful for Kafka→Kafka and transactional offset commits, yet do not cover databases or HTTP automatically.
9. DLTs, offset resets, and listener retries do not replace partial-commit repair/reconciliation.
10. Test the fault window **between the two commits**, verifying actual DB, Kafka, offset, and downstream states rather than inspecting exceptions alone.

**Conclusion:** "Second transaction commit failure" is the clearest illustration of the boundaries when coordinating a DB transaction and a Kafka transaction with Spring. Once the first transaction commits, rolling back the second transaction cannot restore the system to its prior state. A reliable design prepares recovery upfront: outbox/inbox, idempotency, provenance, reconciliation, and compensation when needed. The goal is not assuming partial commits will never happen, but ensuring the system can detect, repair, and reconcile accurately after they do.
