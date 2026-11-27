
# Database Transaction Boundaries and Message Acknowledgements

## 1. Lesson Objectives

A message may already have been processed and committed to the database, yet the broker still redelivers it because the ACK was not recorded. Conversely, if a message is ACKed before the database commits, the process can crash and lose the work. Both systems have distinct lifecycles and confirmation mechanisms; misunderstanding this boundary is a common cause of lost data or duplicate processing.

In the **SPRING_CLOUD_FUNCTION** module, business logic is structured using `Supplier`, `Function`, and `Consumer`, registered via `FunctionCatalog`, and deployed over HTTP, events, or serverless runtimes. The Function defines how to process the payload; the adapter/binder coordinates message receipt and ACK; the transaction manager coordinates data commit/rollback. These three responsibilities must work together cleanly.

This lesson belongs to the **Reliability** chapter and focuses on **database transaction boundaries and message acknowledgements**. After this lesson, you will be able to:

- Distinguish DB commit, Function completion, and broker ACK.
- Describe the failure windows when ACKing before vs. after commit.
- Place transactions on application services invoked by Functions through Spring proxies.
- Use an inbox/idempotency store to handle redeliveries after commit.
- Use an outbox when both writing to a database and publishing events.
- Understand the limits of transaction managers, binder transactions, and distributed transactions.
- Distinguish imperative consumers from reactive/asynchronous lifecycles.
- Test rollbacks, redeliveries, and ACKs against the real binder.

> **Design Principle:** For consumers writing to a database, let the transaction commit successfully before the adapter confirms message processing; accept that ACKs can fail after commit and guard redeliveries with an inbox/idempotency store. Never assume DB commit and broker ACK are one atomic operation.

## 2. Three Distinct Events: Function Completion, DB Commit, Message ACK

A message flow has three milestones:

1. **Function completion:** Function/Consumer execution returns normally or signals an error.
2. **Database commit:** the transaction manager confirms DB changes have committed.
3. **Message acknowledgement:** the broker/binder records that the message was handled under its delivery protocol.

The three milestones are related, not identical:

| Event | Who Manages It? | Meaning |
|---|---|---|
| Function completion | Application + adapter | The processing call returned or the Publisher terminated |
| DB commit | Database + transaction manager | Changes inside the transaction have been durably confirmed |
| ACK | Binder/broker/client protocol | The message is confirmed under the delivery mechanism |

Calling `repository.save(entity)` does not guarantee commit yet. An ORM may defer SQL until flush/commit; constraint violations or connection errors may appear only at transaction end.

Similarly, `Consumer.accept(message)` returning is not a portable ACK command. In imperative consumers, the binder typically inspects the outcome to decide completion/ACK per configuration. In reactive functions, Publisher completion plays a different role and the adapter manages subscription. With manual ACK, the application may need to invoke a binder-specific API.

### 2.1. Common Lifecycle Diagram

~~~text
Broker delivers message
       |
       v
Spring Cloud Stream adapter
       |
       v
Spring Cloud Function Consumer
       |
       v
Application service
       |
       v
DB transaction BEGIN
       |
       +-- read/write domain data
       +-- inbox marker
       +-- outbox event (if needed)
       |
       v
DB COMMIT
       |
       v
Function invocation completes
       |
       v
Binder ACKs per delivery policy
~~~

This is a conceptual model for an imperative consumer whose DB transaction finishes before the Function returns. Actual ACK ordering and exception handling must be verified for the specific binder, version, and ACK mode in use.

### 2.2. Why Separate the Three Milestones?

- A Function can return before async work finishes if code fires and forgets.
- The DB can commit and then the response/ACK is lost on the network.
- A binder may retry or redeliver a message after observing an error or missing ACK.
- A pure Function can complete without having performed any side effects at all.

When investigating incidents, you need to know **which milestone actually occurred**, not merely log "message failed."

## 3. Two ACK/Commit Orders and Their Consequences

### 3.1. ACK First, Commit Later: Risk of Losing Work

~~~text
Broker delivers message
       |
       v
ACK sent / offset committed
       |
       v
DB transaction writes Quote
       |
       v
Process dies before COMMIT
       |
       v
Broker does not redeliver
       |
       v
DB lacks Quote while message was already acknowledged
~~~

This is a **data-loss** window. If a message was ACKed or its offset committed and the DB rolls back, the broker may never send it again. ACKing too early is unsafe.

### 3.2. Commit First, ACK Later: Possible Redelivery, Guarded Against Duplicates

~~~text
Broker delivers message
       |
       v
DB transaction writes Quote + inbox
       |
       v
DB COMMIT succeeds
       |
       v
Process dies before ACK
       |
       v
Broker redelivers message
       |
       v
Inbox recognizes committed event
       |
       v
Does not write Quote a second time; completes cleanly
~~~

This order usually fits consumers writing to a DB under at-least-once delivery. It prioritizes not losing messages; in return, the application must tolerate redeliveries via inbox/idempotency.

### 3.3. Comparison Table

| Order | Failure Window | Consequence | Defense |
|---|---|---|---|
| ACK then commit DB | Process dies between ACK and commit | Lost work | Avoid early ACK; commit before ACK |
| Commit DB then ACK | Process dies between commit and ACK | Message redelivered | Inbox/unique key for no-op |
| Function returns before async DB finishes | Binder thinks processing is done | ACK before side effect | Await completion/error per contract |
| ACK and DB commit on independent systems | One succeeds while the other fails | No end-to-end atomicity | Inbox/outbox, idempotency, or deliberate distributed transaction |

**Committing before ACKing does not create exactly-once.** It creates a redelivery window that can be handled safely when the database records markers and guards side effects.

## 4. Spring Cloud Function and the Adapter Boundary


### Types and Ports Used in the Examples

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderCreated(
            String tenantId,
            String eventId,
            String orderId,
            String payloadHash) {}
}
~~~

`payloadHash` should be computed at a trusted boundary from the validated canonical payload; never blindly trust a client-supplied hash. This example uses an already-normalized hash to focus on the transaction/ACK boundary.

Ports used by the service:

~~~java
package example.functions;

public interface ProcessedMessageRepository {
    boolean insertIfAbsent(
            String tenantId, String eventId, String payloadHash);

    String findPayloadHash(String tenantId, String eventId);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.OrderCreated;

public interface OrderRepository {
    void apply(OrderCreated event);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.OrderCreated;

public interface OutboxRepository {
    void appendOrderUpdated(OrderCreated event);
}
~~~

~~~java
package example.functions;

public class DuplicateMessageConflictException
        extends RuntimeException {
    public DuplicateMessageConflictException(String message) {
        super(message);
    }
}
~~~

These interfaces are illustrative contracts. The database adapter must execute reads/writes under the same transaction manager; `insertIfAbsent` needs a unique constraint and atomic SQL insert.


Spring Cloud Function focuses on reusable logic. Example Consumer:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCreated;

@Configuration
public class OrderFunctions {

    @Bean
    public Consumer<OrderCreated> processOrder(
            OrderApplicationService service) {
        return service::handle;
    }
}
~~~

`OrderApplicationService` is a Spring-injected application service. The Consumer simply delegates the message to the service. Transactions should live on the application service method or a component with clear transactional boundaries, regardless of whether the Function bean is invoked over HTTP or a binder.

Illustrative function selection configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: order-created
          group: order-service
~~~

This configuration illustrates selecting the bean and binding. The application also needs a binder, serializer/converter, error handling, and ACK/retry policies for the target environment.

### 4.1. FunctionCatalog Does Not Manage DB Transactions or ACKs

`FunctionCatalog.lookup("processOrder")` resolves a Function by name. It does not automatically:

- Open a database transaction.
- Commit or roll back data.
- Send an ACK using one universal API across every broker.
- Guarantee single-delivery of messages.
- Create inbox/outbox tables or unique constraints.
- Coordinate DB transactions with broker transactions.

Those responsibilities belong to the application service, transaction manager, adapter, and broker/binder.

### 4.2. The Same Function Can Be Called from Multiple Adapters

- An HTTP adapter receives a request and invokes the Function.
- A Stream binder receives a message and invokes the Function.
- A serverless adapter maps an event and invokes the Function.

Each adapter has its own lifecycle and response mechanism. A `Consumer<OrderCreated>` cannot assume a broker ACK always exists; over HTTP, outcomes map to HTTP responses. In serverless, outcomes follow the trigger's contract. Keep data transactions inside the domain/application service; let each adapter handle protocol confirmation.

## 5. Placing @Transactional on the Application Service

An imperative application service can group inbox claim, business data update, and outbox insert into one transaction:

~~~java
package example.functions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import example.functions.OrderModels.OrderCreated;

@Service
public class OrderApplicationService {

    private final ProcessedMessageRepository inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            ProcessedMessageRepository inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void handle(OrderCreated event) {
        boolean claimed = inbox.insertIfAbsent(
                event.tenantId(),
                event.eventId(),
                event.payloadHash());

        if (!claimed) {
            String oldHash = inbox.findPayloadHash(
                    event.tenantId(), event.eventId());

            if (!event.payloadHash().equals(oldHash)) {
                throw new DuplicateMessageConflictException(
                        "Event ID reused with different payload");
            }

            return; // Event already committed in a previous execution.
        }

        orders.apply(event);
        outbox.appendOrderUpdated(event);
    }
}
~~~

`ProcessedMessageRepository`, `OrderRepository`, and `OutboxRepository` are illustrative ports/repositories. They must share the same datasource and transaction manager to commit atomically. `insertIfAbsent` must use a unique constraint and atomic insert rather than separate `SELECT` then `INSERT`.

With an imperative consumer calling the service through a Spring proxy, the transaction interceptor starts the transaction, runs the method, and **commits before the proxy call returns**. The Consumer completes afterward only if the service throws no error.

### 5.1. Consumer Calling Through a Proxy

~~~text
Spring Cloud Function Consumer
       |
       v
OrderApplicationService proxy
       |
       v
Transaction interceptor: BEGIN
       |
       v
handle(event)
       |
       +-- claim inbox
       +-- update order
       +-- insert outbox
       |
       v
COMMIT or ROLLBACK
       |
       v
Proxy returns to Consumer
       |
       v
Function invocation completes
       |
       v
Binder handles ACK/error per policy
~~~

This is why Function beans should inject a Spring-managed service rather than instantiating `new OrderApplicationService(...)` manually and expecting annotations to work.

### 5.2. @Transactional Must Pass Through the Spring Proxy

Spring's imperative transactions normally work via proxies. Calling from another bean into a proxied method is the standard path.

If a method calls `this.handle(...)` internally on the same object, self-invocation can bypass the proxy and skip opening a transaction. Also check proxy mode and bean registration.

### 5.3. Runtime Exceptions vs. Checked Exceptions

Under Spring's usual defaults, `RuntimeException` and `Error` trigger rollback; checked exceptions do not roll back by default in all cases. If business rules require rollback on checked exceptions, declare it explicitly:

~~~java
@Transactional(rollbackFor = Exception.class)
public void handle(OrderCreated event) throws Exception {
    // Changes requiring rollback if a checked exception occurs.
}
~~~

Do not add `rollbackFor` out of habit if there are checked exceptions the business wants committed. Choose rules based on error types and contracts.

### 5.4. save() Is Not Always Commit

An ORM may defer SQL until flush/commit. Constraint violations, deadlocks, or lost connections can surface only at the end of the transaction. Never ACK merely because `repository.save(entity)` did not throw; wait until **the transactional method finishes successfully**.

## 6. Inbox Pattern: Tying Message Markers to Business Changes

An inbox (processed-message table) stores processed message identifiers in the same transaction as business data. When the broker redelivers after commit, the consumer detects the prior message and skips writing again.

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE processed_message (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);
~~~

The primary key prevents `tenant_id + event_id` from being claimed twice. `payload_hash` catches identical event IDs with differing content.

### 6.1. Claiming an Event with One Atomic Statement

~~~sql
INSERT INTO processed_message (
    tenant_id, event_id, payload_hash
)
VALUES (:tenantId, :eventId, :payloadHash)
ON CONFLICT (tenant_id, event_id) DO NOTHING
RETURNING event_id;
~~~

- One row returned: the current transaction claimed the key.
- No row returned: the key already exists or another transaction just claimed it; read the stored fingerprint and compare.
- Matching fingerprint: valid duplicate, skip repeating side effects.
- Different fingerprint: conflict, reject or quarantine per policy.

In PostgreSQL, unique constraints resolve concurrency in storage. Under `READ COMMITTED`, the subsequent read observes committed state after the insert waits on a competing transaction. Test against a real DB and handle timeouts/deadlocks appropriately.

### 6.2. Inbox and Business Write Must Commit Together

~~~text
BEGIN
  INSERT processed_message (unique tenant + event)
  UPDATE/INSERT order
  INSERT outbox_event
COMMIT
~~~

If any step fails before commit, both the marker and business data roll back. If commit succeeds and ACK is lost, redelivery reads the committed marker and no-ops.

If the inbox marker commits separately before the order, a crash marks the event handled even though the order was never saved. If the order commits separately before the marker, redelivery can write the order again. **Sharing the same transaction** is the linchpin.

### 6.3. Valid Duplicates Should Complete Normally

When an event already committed with the same fingerprint, the service can return normally. The adapter treats redelivery as handled and ACKs per policy.

Never throw a transient error for an already-processed event; that triggers needless retry loops. A different payload under the same key must raise a conflict, never be treated silently as a duplicate.

## 7. Transaction Boundaries and Propagation

A transaction spans only the resources managed by its transaction manager. When inbox, order, and outbox share one datasource and transaction manager, they commit or roll back together.

### 7.1. REQUIRES_NEW Can Break Desired Atomicity

Suppose `orders.apply(event)` opens its own transaction with `REQUIRES_NEW`:

~~~text
Outer transaction:
  claim inbox
       |
       +---- calls orders.apply()
                  |
                  v
             New transaction
                  |
                COMMIT
       |
  outbox insert fails
       |
  Outer ROLLBACK
~~~

The result can be a committed order while the outer transaction's inbox and outbox roll back. The next redelivery finds no inbox marker and can apply the order again.

When changes must be atomic, child repositories/services should normally join the existing transaction with appropriate propagation—typically `REQUIRED`. Use `REQUIRES_NEW` only when the business genuinely wants an independent commit and understands the consequences.

### 7.2. Do Not Hold Transactions Open Across Network Calls

Never hold a DB transaction open while waiting on slow HTTP APIs or broker publishes:

- Holds connections and locks for the duration of the wait.
- Increases timeouts, deadlocks, and contention.
- Remote side effects do not roll back with the DB.
- If the remote call succeeds and the DB rolls back, the two systems diverge.

Commit publish intent via an outbox, then let a separate worker perform network calls.

### 7.3. Isolation Levels Do Not Replace Idempotency

Isolation levels govern how concurrent transactions observe each other's changes; they do not define whether a request is a duplicate. Unique constraints on event keys and business keys remain essential.

A transaction may hit deadlocks or serialization failures and require retrying the entire transaction. If so, keep non-DB side effects outside the transaction or make them idempotent; never send emails or HTTP requests directly inside a retryable transaction callback.

### 7.4. Multiple Datasources Do Not Automatically Share One Transaction

If the inbox lives in database A while order/outbox live in database B, a single default `@Transactional` usually picks only one transaction manager. Calling a repository on another datasource does not make both commit or roll back together.

~~~text
Transaction manager A: INSERT inbox → COMMIT
Transaction manager B: UPDATE order → ROLLBACK
~~~

That can leave an inbox marker persisted while the order was never updated. On redelivery, the consumer sees the marker and wrongly skips the event.

Choose deliberately:

- Keep inbox, domain data, and outbox that need atomicity in the same database/transaction manager where practical.
- If writing across genuinely independent resources, evaluate XA/JTA support and recovery semantics.
- Or design a workflow/outbox/saga with per-step state and compensating actions.

If the app has multiple transaction managers, specify the right one explicitly via configuration or qualifiers, such as `@Transactional("ordersTransactionManager")`. Naming a manager does not create a distributed transaction.


## 8. ACK Belongs to the Adapter/Binder, Not Pure Functions

Spring Cloud Function provides protocol-independent `Function`/`Consumer` beans. ACK is a message-transport concept; there is no single universal ACK command guaranteed to work identically across Kafka, RabbitMQ, and serverless.

### 8.1. Binder-Managed Acknowledgement

For imperative consumers, binders typically invoke the Function and apply their policy based on whether the call returns normally or throws. Depending on the binder, ACK/offset commit, retries, requeues, and dead-lettering are coordinated by the listener container or client.

In this model, the Function does not call ACK directly. It must:

- Return only after the business transaction commits.
- Let exceptions propagate when the transaction rolls back.
- Handle valid duplicates as normal no-op successes.
- Never swallow errors so the binder mistakenly thinks processing succeeded.

### 8.2. Manual Acknowledgement

Some binders/clients support manual ACK. When using it, retrieve the binder-specific header/API and ACK only after the DB transaction commits.

Never pass an assumed ACK object through a shared Function expecting portability. Headers, acknowledgement types, and semantics depend on the binder and version. Spring Kafka's manual ack API is not a universal API across Spring Cloud Function or the Rabbit binder.

### 8.3. ACK, Offset Commit, and Message Deletion Are Not Always the Same

- Kafka typically tracks progress by committing offsets per partition/record/batch according to ack mode.
- RabbitMQ uses delivery-tag ACK/NACK with requeue/dead-letter semantics.
- Some serverless event sources use checkpoints or batch-response formats.
- HTTP requests finish with HTTP responses; there is no equivalent broker ACK.

Never infer semantics from the word "ACK." Inspect the specific adapter: when it ACKs, whether per record or per batch, how timeouts work, how partial batch failures behave, and whether redeliveries occur.

### 8.4. Manual ACK Example Specific to a Kafka Adapter

With Spring Kafka, when the container is configured for manual acknowledgement, a listener can receive `Acknowledgment` and call `acknowledge()`. With Spring Cloud Stream's Kafka binder, header extraction and ACK configuration must follow your active binder and version.

Pseudo-flow:

~~~java
// Conceptual illustration; not a portable API across all binders.
@Transactional
public void persist(OrderCreated event) {
    repository.apply(event);
}

// Only after the transactional method returns successfully:
// the Kafka-specific adapter calls acknowledgment.acknowledge().
~~~

Never call ACK before the transactional method completes. Nor should you treat this pseudo-code as a complete config: verify headers, ack mode, record/batch semantics, and which thread calls ACK.

### 8.5. Manual ACK Does Not Eliminate the Commit/ACK Window

Even when code calls `acknowledge()` after commit, the process can still crash between the two steps. Redeliveries remain possible. Manual ACK controls **when confirmation is sent**, while inbox/idempotency handles **redeliveries**.

## 9. Outbox: Persisting DB Changes and Message Intent in One Transaction

A consumer may update an order and need to emit an `OrderUpdated` event. Performing the DB write and broker publish as two separate operations always leaves a failure window:

~~~text
DB commit succeeds
       |
       v
Process dies before publishing
       |
       v
Order changed without any downstream event
~~~

Publishing first and rolling back the DB leaves downstream holding an event for an uncommitted change.

A **transactional outbox** writes publish intent into a table inside the same database transaction as business data.

~~~text
BEGIN DB TRANSACTION
    UPDATE order
    INSERT outbox_event
COMMIT
       |
       v
Outbox worker reads unpublished events
       |
       v
Publish to broker
       |
       v
Mark outbox record published
~~~

If the transaction rolls back, neither the order change nor the outbox record exists. If it commits, a worker can publish the event later even if the original process stopped.

### 9.1. Illustrative Outbox Schema

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(120) PRIMARY KEY,
    aggregate_id    VARCHAR(120) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);
~~~

`event_id` is a stable identifier. Production needs indexes for pending queries, claim/lease state, retry metadata, retention, and payload protection policies.

### 9.2. The Publishing Worker Can Publish Duplicates

~~~text
Worker reads outbox event E
       |
       v
Broker accepts E
       |
       v
Process dies before updating published_at
       |
       v
New worker sees E as pending
       |
       v
Broker receives E again
~~~

The outbox guarantees publish intent is never lost when the DB commits, yet the publisher may have **at-least-once** semantics across this window. Downstream consumers need an inbox/dedupe keyed by `event_id`.

### 9.3. Mark Published After Broker Confirmation

Workers must not mark an event published before sending it. Even when marking after broker ACK, a crash window still exists between ACK and the DB update. That is why downstream consumers must tolerate duplicate events.

No simple ordering between two independent systems avoids both lost events and duplicates without coordinated transactions. Outboxes prevent losing publish intent and rely on deduplication to absorb duplicates.

## 10. Pairing Inbox and Outbox at Both Ends

An event-driven workflow can use both patterns:

~~~text
Producer service
  DB transaction:
    update domain data
    insert outbox event
  COMMIT
       |
       v
  Outbox publisher
       |
       v
     Broker
       |
       v
Consumer service
  DB transaction:
    claim inbox event ID
    update consumer domain data
    insert next outbox event (if needed)
  COMMIT
       |
       v
  Binder ACK
~~~

- **Producer outbox:** ties publish intent to database changes.
- **Consumer inbox:** ties event receipt to the consumer's database changes.
- **ACK:** confirms delivery to the broker/binder after the consumer transaction succeeds.
- **Downstream dedupe:** absorbs events re-emitted by an outbox or broker.

### 10.1. Consumer Duplicates Must Not Create New Outbox Rows

If the first delivery committed inbox, order, and outbox, redeliveries with the same fingerprint must no-op. If code appends to the outbox before checking the inbox, every redelivery emits a duplicate downstream event.

The order inside the transaction must be **claim inbox → check duplicate → update domain → write outbox**.

### 10.2. Outbox Publishers Need Claims/Leases

Multiple workers may poll the same pending events. Use atomic claims, row locks, or leases to curb concurrent sends. Leases need timeouts and crash recovery; even so, leases do not remove the post-publish crash window.

### 10.3. Outbox Does Not Replace Workflow Orchestration

An outbox solves persisting message-publish intent inside a DB transaction. It does not manage multi-service sagas with compensating steps, business timeouts, or human wait states. Those require dedicated sagas/process managers and workflow state.

## 11. Are DB Transactions and Broker Transactions Automatically Atomic?

Normally, a local DB transaction and a broker transaction **do not become one atomic transaction** merely because code runs inside the same Function.

Example:

~~~java
@Transactional
public void updateOrder(Order order) {
    repository.save(order);
    streamBridge.send("order-updated", event);
}
~~~

If `send` publishes and the DB commit fails, the broker holds an event for an uncommitted change. If the DB commits first and publishing fails, the DB changed while the event can be lost without an outbox.

### 11.1. Broker Transactions Have Their Own Scope

Some brokers support transactions within the broker's boundary. For instance, Kafka transactions can combine publishing records and committing offsets in Kafka-to-Kafka pipelines per Kafka configuration and semantics. That **does not automatically include an independent PostgreSQL/JPA database**.

Likewise, a broker channel transaction does not roll back an external DB transaction. Check the supported scope of your binder and transaction manager.

### 11.2. Spring Cloud Stream Binder Transactions Are Broker-Specific

Spring Cloud Stream supports transactions depending on binder and configuration. Distinguish:

- Broker transactions managing publishes/offsets/acks inside the broker.
- DB transactions managing inbox/domain/outbox tables.
- Coordinating DB and broker requires explicit architecture; `@Transactional` does not provide it automatically.

Never copy a Kafka binder transaction property into a Rabbit binder or vice versa. Read the docs for your exact version and test real crash windows.

### 11.3. Distributed Transactions / XA

Some systems can coordinate multiple resource managers via XA/two-phase commit when drivers, brokers, transaction managers, and configurations all support it.

In exchange, distributed transactions add operational complexity: coordinators, in-doubt transactions, timeouts, recovery logs, resource locks, and platform limitations. They are not Spring Cloud Function's default and are not mandatory for every app.

Outbox/inbox is often simpler in microservices: local DB transactions, at-least-once delivery, and idempotent consumers. Choose based on consistency requirements, load, latency, and operational readiness.

## 12. ACK Modes, Offsets, and Batches: Verify Real Semantics

A consumer can receive messages one record at a time or in batches. ACKing one record, committing the highest processed offset, or confirming an entire batch carries different consequences.

### 12.1. Kafka

In Kafka, consumers track offsets per partition. Committing an offset confirms read progress, not a database commit. Committing offsets before the DB transaction risks skipping unsaved records on crash. Committing DB before offsets risks re-reading records.

In batch mode, a batch holds multiple records. If record 4 fails after records 1–3 committed, how the binder/container commits offsets and retries batches may reprocess earlier records. Give each record its own idempotency guard when it has side effects.

### 12.2. RabbitMQ

RabbitMQ deliveries typically use ACK/NACK by delivery tag. ACK confirms delivery to the broker; it does not commit the database. If the channel or connection closes before ACK, messages can be requeued depending on state and config.

When processing concurrently, understand multiple-ACK, prefetch, requeue, and dead-letter semantics. Never use a delivery tag as a business idempotency key: it is tied to the delivery/session, not stable across redeliveries.

### 12.3. Batch Event Sources and Serverless

Some event sources deliver batches and support partial failure responses. Reporting only whole-batch success/failure causes a single bad item to redeliver already-committed items. Use partial batch responses where supported and keep per-record side effects idempotent.

### 12.4. Questions to Answer Before Choosing an ACK Mode

- Is ACK sent when the Function returns or when a Publisher completes?
- Has the DB transaction committed before that milestone?
- Does one ACK cover a single record, multiple records, or an offset/batch?
- Does an exception mid-batch redeliver the whole batch?
- How does the broker behave on ACK timeouts or dropped connections?
- Is manual ack available, and which binder API provides it?
- Across redeliveries, which message identifier stays stable?

There is no single portable answer across all binders.

## 13. Reactive Functions: Transactions End When the Publisher Completes

In imperative services, a transaction proxy commits before returning to the caller. In reactive services, work is usually deferred; reactive transactions must wrap the Publisher and end on the Publisher's terminal signal.

A `Mono`-returning method can be managed by a reactive transaction manager:

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveInboxRepository inbox;
    private final ReactiveOrderRepository orders;
    private final ReactiveOutboxRepository outbox;

    public ReactiveOrderService(
            ReactiveInboxRepository inbox,
            ReactiveOrderRepository orders,
            ReactiveOutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Mono<Void> handle(OrderCreated event) {
        return inbox.claim(event)
                .flatMap(claimed -> {
                    if (!claimed) {
                        return inbox.verifySamePayload(event)
                                .then();
                    }

                    return orders.apply(event)
                            .then(outbox.append(event));
                });
    }
}
~~~

This example targets **reactive repositories / R2DBC**. Repositories must return Publishers and participate in the same reactive transaction manager. Never drop in blocking JDBC and assume transactions propagate across schedulers.

### 13.1. Commit Does Not Happen When the Mono-Returning Method Returns

~~~text
Call handle(event)
       |
       v
Receive Mono (DB not run yet)
       |
       v
Adapter subscribes
       |
       v
Transaction begins in reactive context
       |
       v
DB operations emit signals
       |
       v
onComplete → commit
onError    → rollback
~~~

If an adapter only creates the Publisher without subscribing or awaiting completion, the transaction never runs. For Spring Cloud Function reactive adapters, understand the active binder's subscription contract.

### 13.2. One Transaction for the Whole Flux or One per Message?

When receiving a long `Flux<OrderCreated>`, avoid wrapping the entire stream in one giant transaction by default. A failure on message 100 can disrupt the long transaction and hold locks/connections too long.

Usually you want one transaction **per message**:

~~~java
Flux<Void> results = events.concatMap(event ->
        transactionalOperator.execute(status ->
            inbox.claim(event)
                .flatMap(claimed -> {
                    if (!claimed) {
                        return inbox.verifySamePayload(event);
                    }

                    return orders.apply(event)
                            .then(outbox.append(event));
                })
        ).then()
);
~~~

`TransactionalOperator` is built from the reactive transaction manager; `events` and repositories are reactive Publishers. This illustrates the per-item boundary; adapt port return types to match your application.

### 13.3. Cancellation Is Different from Successful Commit

If a subscriber cancels the subscription, the Publisher receives `cancel` instead of `onComplete`. Never treat cancellation as a committed success. The transaction manager can roll back per transaction lifecycle, yet an escaped I/O call or external side effect may already have occurred.

## 14. Why Fire-and-Forget Breaks ACK

A Consumer might launch async work and immediately return:

~~~java
@Bean
Consumer<OrderCreated> unsafe(OrderApplicationService service) {
    return event -> {
        service.handleAsync(event); // Does not await completion.
    };
}
~~~

If `handleAsync` returns a `CompletableFuture` or Publisher and the Consumer ignores it, the adapter sees only that `accept` returned. It may ACK before the DB commits or even if async work fails later.

Safe approaches:

- In imperative consumers, invoke a synchronous transactional service and let exceptions propagate.
- In reactive/async adapters, return a Publisher/`CompletionStage` per contract so the adapter observes terminal signals.
- Never self-subscribe and discard errors.
- Never issue a manual ACK before the transaction completes.

### 14.1. @TransactionalEventListener(AFTER_COMMIT) Does Not Replace an Outbox

An app may use `@TransactionalEventListener(phase = AFTER_COMMIT)` to run an in-process listener after commit. It works well for in-process side effects, yet **is not durable message delivery**:

~~~text
DB COMMIT
   |
   v
Process dies before listener
   |
   v
Listener never runs; event can be lost
~~~

If the listener publishes to a broker and dies right before recording completion, the event can also be re-emitted. When publish intent must never be lost, persist an outbox row inside the transaction and publish via a separate worker.

## 15. Failures and Retries: Who Is Responsible After Rollback?

When a DB transaction throws before commit:

~~~text
Function calls application service
       |
       v
DB transaction
       |
       +-- failure
       |
       v
ROLLBACK
       |
       v
Exception/error signal propagates to adapter
       |
       v
Binder applies retry/DLQ/requeue per policy
~~~

Never catch the exception inside the Consumer and return normally when a transaction fails. The binder may treat the invocation as successful and ACK the message.

### 15.1. Permanent vs. Transient Failures

| Error Type | Reference Action |
|---|---|
| Invalid payload | Do not retry same payload; reject/quarantine |
| Committed duplicate (same key, same payload) | No-op and complete |
| Same key, different payload | Conflict; do not retry blindly |
| Deadlock / serialization failure | May retry **the whole DB transaction** with bounds |
| Temporary DB outage | Retry within budget and deadline |
| Programming bug | Observe and fix code; no fake fallbacks |
| Unknown commit outcome | Query by idempotency key or idempotent retry |

### 15.2. Retrying a DB Transaction Must Rerun the Whole Transaction

Deadlocks or serialization failures leave the current transaction unusable. If retrying, open a **fresh transaction** and re-execute all DB operations belonging to it.

Never retry one statement inside a transaction already marked rollback-only. Never send emails or HTTP calls directly inside a retryable transaction callback.

### 15.3. Binder Retries Are Not Transaction Rollbacks

A binder can re-invoke a Function after an exception, yet it cannot roll back an already-committed transaction. If commit succeeded and ACK failed, the retry runs against committed data; the inbox must detect the duplicate.

### 15.4. Exhausting Retries

When transactions roll back and binder retries run out, the app needs an explicit policy: DLQ, error channel, requeue, or failure response per adapter. Never mark the inbox `DONE` when business writes did not commit. For permanently invalid payloads, avoid infinite requeue loops.

## 16. Transactional Outbox vs. Post-Commit Publishing

You may see code like:

~~~java
@Transactional
public void update(Order order) {
    repository.save(order);
    applicationEventPublisher.publishEvent(
            new OrderUpdated(order.id()));
}
~~~

If the listener uses `@TransactionalEventListener(AFTER_COMMIT)`, it runs after commit in the same process. That avoids publishing before commit, yet cannot guarantee durable delivery if the process dies between commit and listener execution.

Comparison:

| Approach | Advantage | Risk / Limitation |
|---|---|---|
| Publish inside transaction | Short code | Broker may receive event even if DB rolls back |
| `AFTER_COMMIT` listener | Runs listener only after DB commit | Process crash can lose the event |
| Transactional outbox | Publish intent commits with DB | Publisher may duplicate; downstream needs dedupe |
| XA / distributed transaction | Can span supported resources | Operational complexity, not default |

When events form a critical inter-service contract, an outbox is usually clearer and safer than in-process callbacks.

## 17. Spring Cloud Stream: Verify ACK and Transactions per Binder

Functional binding configuration picks the Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: order-created
          group: order-service
~~~

This configuration does not fully specify ACK semantics. You must know which binder is used and its binder-specific properties.

### 17.1. With the Kafka Binder

Verify:

- Whether the consumer processes single records or batches.
- Which ack mode commits offsets.
- Whether binder transactions are enabled and which broker operations they cover.
- Which manual acknowledgement header/API applies if needed.
- How mid-batch errors retry and which offsets already committed.
- Whether DB transactions are coordinated or remain independent local transactions.

Kafka transactions provide atomicity inside Kafka's scope (e.g., publishing records and committing offsets when configured properly). They do not automatically span an independent JDBC/JPA database.

### 17.2. With the Rabbit Binder

Verify:

- How the container manages ACK/NACK and requeue.
- Whether channel transactions are enabled.
- Whether consumers handle single or concurrent messages.
- How prefetch, redelivery, and dead-letter exchanges/queues behave.
- Whether DB transactions share a resource manager or run independently.

Transactions/ACKs on a Rabbit channel do not automatically commit an external database.

### 17.3. Never Copy ACK Configs Across Binders

A Kafka binder property may not exist or may mean something else in the Rabbit binder. Follow docs for your exact version, then test:

1. Failure before commit.
2. Failure after commit but before ACK.
3. Process shutdown mid-processing.
4. Redeliveries and resulting DB state.
5. DLQ/requeue behavior after exhaustion.

### 17.4. Test Binders Do Not Simulate All Broker Behaviors

Test binders help verify Function bindings and application-level routing, yet do not prove real offset semantics, ACK/NACK, broker restarts, prefetch, or real redelivery. Use integration tests against the actual broker for those guarantees.

## 18. Testing Transaction and ACK Boundaries

A unit test calling `Consumer.accept(event)` does not prove DB commit occurs before ACK. Test the service through its Spring proxy, a real or compatible database, and the real adapter/broker when verifying delivery semantics.

The snippets below are integration-test skeletons; helpers like `testEvent` and queries like `countBy...` belong to your project's test fixtures/repository adapters. They illustrate required assertions rather than a standalone runnable class without those fixtures.

### 18.1. Test Service Commit Followed by Redelivery of the Same Event

~~~java
@SpringBootTest
class OrderApplicationServiceIntegrationTest {

    // Required imports: JUnit 5, Spring Boot Test,
    // OrderModels.OrderCreated and static Assertions.

    @Autowired
    OrderApplicationService service;

    @Autowired
    OrderRepository orders;

    @Autowired
    ProcessedMessageRepository inbox;

    @Autowired
    FaultInjectingOutboxRepository outbox;

    @Test
    void repeatedInvocationDoesNotApplyOrderTwice() {
        OrderCreated event = testEvent("evt-901", "ORD-901");

        service.handle(event); // Proxy transaction commits before returning.
        service.handle(event); // Simulates redelivery after commit.

        assertEquals(1, orders.countByOrderId("ORD-901"));
        assertEquals(1, inbox.countByEventId("evt-901"));
    }
}
~~~

`testEvent` is a test-provided fixture; repository methods are illustrative contracts. Avoid annotating the test method itself with an enclosing `@Transactional` if testing the service's real commits—a test-level `@Transactional` makes the service join the test transaction and roll back only at test end, hiding real commit timing.

### 18.2. Test Inbox Rolling Back Alongside Business Data

~~~java
@Test
void failureBeforeCommitRollsBackInboxAndOrder() {
    OrderCreated event = testEvent("evt-902", "ORD-902");
    outbox.failNextInsert();

    assertThrows(RuntimeException.class,
            () -> service.handle(event));

    assertEquals(0, inbox.countByEventId("evt-902"));
    assertEquals(0, orders.countByOrderId("ORD-902"));
}
~~~

`outbox.failNextInsert` is fault injection on the test repository. With proper transaction rollback on exceptions, neither the inbox marker nor the order exists. In production, flush/commit-time failures should also be tested since exceptions can emerge at transaction end.

### 18.3. Simulating Commit Success with Lost ACK

~~~java
@Test
void redeliveryAfterCommitIsNoOp() {
    OrderCreated event = testEvent("evt-903", "ORD-903");

    service.handle(event); // DB commit succeeds.

    // Simulate process/connection failure before ACK:
    service.handle(event); // Broker redelivers the same event.

    assertEquals(1, orders.countByOrderId("ORD-903"));
    assertEquals(1, inbox.countByEventId("evt-903"));
    assertEquals(1, outbox.countByAggregateId("ORD-903"));
}
~~~

This test models redelivery at the application layer. It does not prove how a real broker redelivers; pair it with a binder integration test verifying ACK, timeouts, and redelivery.

### 18.4. Do Not Let a Test Transaction Hide Real Commits

In Spring Test, a `@Transactional` test method typically rolls back at test completion. If the service joins that outer transaction, writes do not commit independently when the service returns.

To test real boundaries:

- Omit `@Transactional` on the test method when observing real service commits.
- Or explicitly manage/end the test transaction using proper test-transaction utilities.
- Query data in a fresh transaction/connection when verifying committed state.
- Use database integration tests for unique constraints, locking, and rollbacks.

## 19. Testing Adapters: ACK After Commit

### 19.1. Scenarios Needed Against a Real Broker

| Scenario | How to Induce Failure | What to Verify |
|---|---|---|
| Failure before DB commit | Repository throws exception | Transaction rolls back; adapter does not ACK as success |
| Failure at flush/commit | Constraint/connection failure | Exception reaches adapter; message not lost |
| Post-commit, pre-ACK | Stop consumer or drop connection | Message redelivers; inbox no-ops |
| Valid duplicate | Send the same event twice | Single business change |
| Same ID, different payload | Send two payloads with same key | Conflict / quarantine |
| Batch with one failing record | Fail mid-batch | Identify which records/offsets retry |
| Broker restart | Restart broker mid-delivery | Verify redelivery and persistence |
| Consumer rebalance | Stop one instance mid-processing | No duplicate side effects |

Do not assert only that "the consumer received the message." Check **DB row counts**, **inbox/outbox rows**, **offsets/ACKs**, **DLQs**, and side-effect counts.

### 19.2. Test Binders vs. Real Brokers Have Different Roles

Test binders confirm Spring Cloud Function wiring and payload routing to the Consumer. Only real brokers verify protocol specifics such as Kafka offset commits, Rabbit ACK/NACK, redelivery, partitions/queues, and dead-lettering.

Never extrapolate full broker guarantees from test-binder results alone.

### 19.3. Testing Manual ACK

If using manual ACK, verify:

1. The transactional method committed before ACK is called.
2. Exceptions before commit never call ACK.
3. Process death after commit and before ACK allows redelivery.
4. Duplicate redelivery completes normally.
5. ACK/NACK runs on the thread/context required by the binder.

Never rely on mocking `Acknowledgment` alone to draw conclusions about real broker offsets.

## 20. Observing Transactions and ACKs in Production

To investigate duplicated or missing messages, trace these milestones:

~~~text
received
  → transaction_started
  → inbox_claimed / duplicate_detected
  → domain_write
  → outbox_inserted
  → transaction_committed / rolled_back
  → function_completed
  → ack_attempted / ack_observed
~~~

These event names are observability suggestions, not built-in Spring events.

### 20.1. Useful Log/Trace Fields

- Validated `eventId` and `tenantId`.
- `aggregateId` or business operation/version.
- `deliveryAttempt` when provided by the adapter.
- `transactionId`/correlation ID if available.
- Processing step and outcome: new, duplicate, conflict, rollback.
- Commit timestamp and ACK status.
- Binder, destination, partition/offset, or delivery tag when applicable.
- Cross-service `traceId`.
- Retry/DLQ reason without logging sensitive payloads.

Do not assume every binder supplies a stable delivery count. Offsets, partitions, and delivery tags are transport metadata, not substitutes for business keys.

### 20.2. Metrics Should Separate Commits from ACKs

| Suggested Metric | Meaning |
|---|---|
| `message_received_total` | Deliveries received |
| `db_transaction_committed_total` | DB transactions committed |
| `db_transaction_rolled_back_total` | DB transactions rolled back |
| `message_ack_attempt_total` | ACK attempts by app/binder when observable |
| `message_duplicate_total` | Redeliveries caught by inbox |
| `message_conflict_total` | Same key with different payload |
| `message_redelivery_total` | Redeliveries per binder metadata when available |
| `outbox_pending_count` | Events awaiting publish |
| `outbox_oldest_age_seconds` | Age of oldest pending outbox event |
| `message_processing_duration` | Processing time |

Not every ACK offers an application callback for direct metrics. When the binder manages ACKs, combine listener/container metrics, broker metrics, and tracing instrumentation.

### 20.3. Anomaly Alerts

- Transactions commit yet redeliveries spike: inspect ACKs, network, or broker.
- High message receipts yet low DB commits: inspect pre-commit failures or poison payloads.
- Rising DB commits yet aging outbox rows: publisher falling behind.
- Rising duplicates/conflicts: inspect producer resends, key reuse, or retention.
- Rising consumer latency and ACK timeouts: inspect long transactions, locks, or pool exhaustion.

## 21. Design Decision Table

| Scenario | DB Transaction | ACK / Delivery | Primary Safeguard |
|---|---|---|---|
| Consumer writes one database | Single transaction for inbox + domain write | After Function/service succeeds per binder | Inbox + unique key |
| Consumer writes DB and emits event | Inbox + domain + outbox in one transaction | ACK after commit | Outbox + downstream inbox |
| HTTP `POST` creates data | Transaction saves key + resource + response | HTTP response after commit | `Idempotency-Key` |
| Serverless event writes DB | Local transaction on shared storage | Trigger confirms after completion | Durable inbox / business key |
| Reactive stream of many events | Per-item transaction when appropriate | Adapter tracks completion | Per-item inbox / idempotency |
| Tight atomicity between DB and broker | XA if resources support it, or outbox | Per transaction strategy | Evaluate trade-offs carefully |
| Batch with partial failure | Defined per-record or per-batch commits | Partial ACK/checkpoint if supported | Per-record deduplication |

No single transaction/ACK pattern fits all systems. Choose by delivery guarantees, resources to commit, latency targets, operational simplicity, and replay impact.

## 22. Pre-Production Checklist

### 22.1. Transactions

- [ ] Identified which datasource and transaction manager govern which tables.
- [ ] Inbox marker and business changes commit together.
- [ ] Outbox records write in the same transaction as domain changes.
- [ ] No independent propagation accidentally breaks atomicity.
- [ ] `@Transactional` executes through a real Spring proxy.
- [ ] Rollback policies for runtime and checked exceptions are explicit.
- [ ] Commit/flush exceptions propagate to the adapter.
- [ ] No DB transaction stays open around slow remote network calls.

### 22.2. ACK and Delivery

- [ ] Know the exact binder/adapter and ACK mode in use.
- [ ] Clarified whether ACK/offset applies per record or per batch.
- [ ] Function completes only after the transaction commits.
- [ ] Manual ACK, if used, executes after commit.
- [ ] Rollback exceptions are never swallowed.
- [ ] Tested process crash after commit and before ACK.
- [ ] Duplicate redeliveries are handled as no-ops.
- [ ] Poison messages have bounded retries and proper DLQ/quarantine.

### 22.3. Coordinating DB and Broker

- [ ] Never assume DB `@Transactional` covers broker publishing.
- [ ] Broker transactions are scoped strictly to what the broker actually supports.
- [ ] Outbox publisher has retry, claim, and lease management.
- [ ] Downstream consumers maintain inbox/dedupe protection.
- [ ] XA/distributed transactions used only after verifying support and recovery.

### 22.4. Reactive and Testing

- [ ] Know who subscribes to Publishers and who observes terminal signals.
- [ ] Reactive transactions use the proper reactive transaction manager.
- [ ] Per-item transactions considered for long streams.
- [ ] No fire-and-forget followed by early ACK.
- [ ] Unit tests cover rollbacks and duplicates.
- [ ] Integration tests cover post-commit redelivery.
- [ ] Real broker tested for ACK/offset/DLQ semantics.
- [ ] Metrics/traces cover transactions, duplicates, redeliveries, and outbox.

## 23. Practice Exercises

**Exercise 1 — ACK Before Commit.** A Consumer ACKs a message, then the DB transaction rolls back. What happens to the message and data? Why is this a data-loss window?

**Exercise 2 — Commit Before ACK.** DB commit succeeds, then the process dies before ACK. The broker redelivers. Describe the inbox's role.

**Exercise 3 — Function Completion.** Why does `Consumer.accept(event)` returning not always prove DB commit happened? Mention async fire-and-forget and ORM flushing.

**Exercise 4 — @Transactional Proxy.** A Function calls `service.handle(event)` through a Spring bean proxy. When does the transaction commit relative to the service call returning? What happens with `new Service()` or self-invocation?

**Exercise 5 — Rollback.** Inbox insert, order update, and outbox insert share one transaction. Outbox throws before commit. Which changes must roll back?

**Exercise 6 — Propagation.** `orders.apply` uses `REQUIRES_NEW` and commits, then the outer transaction rolls back. Why can inbox/outbox become inconsistent?

**Exercise 7 — Outbox.** DB commit succeeds, then the process dies before publishing. Which failure window does an outbox solve? Does it guarantee the broker receives only one message?

**Exercise 8 — Publish Then Crash.** The broker accepted the event, and the publisher died before marking outbox published. Why is a downstream inbox still needed?

**Exercise 9 — Kafka.** What is the risk of committing offsets before DB commit? What is the risk of committing DB before offsets? Why is an inbox required?

**Exercise 10 — RabbitMQ.** Does a delivery-tag ACK/NACK commit a database? If the channel closes before ACK, what can happen?

**Exercise 11 — Reactive.** A Function returns a Publisher that nobody subscribes to. Has the DB transaction run? When does a reactive transaction commit?

**Exercise 12 — Per-Item Transactions.** A Flux receives 1,000 events. Why can a single transaction for the whole stream be risky? When should you use one transaction per event?

**Exercise 13 — Manual ACK.** Why is calling `acknowledge()` right after creating a Mono—before subscribing—wrong? State the proper order.

**Exercise 14 — AFTER_COMMIT.** Why is `@TransactionalEventListener(AFTER_COMMIT)` not equivalent to a transactional outbox?

**Exercise 15 — Distributed Transactions.** Does a Kafka transaction automatically commit an independent PostgreSQL database? When should XA be evaluated?

**Exercise 16 — Testing.** Propose one test proving rollback across inbox and order, and one test simulating commit success with lost ACK.

**Exercise 17 — Batch.** A batch has five records and the fourth fails. Why must you understand offset/partial-batch ACK semantics before assuming records 1–3 will not reprocess?

**Exercise 18 — Observability.** List log/metric fields that distinguish transaction rollback, successful commit, duplicate redelivery, and ACK failure.

### Suggested Answers

- **Exercise 1:** The broker may not redeliver because it received ACK; the DB has no data, so work is lost.
- **Exercise 2:** Redelivery reads the committed marker, compares fingerprints, and no-ops without repeating side effects.
- **Exercise 3:** The Consumer might ignore async completion; an ORM might flush/commit later; wait for transaction completion.
- **Exercise 4:** The proxy transaction interceptor commits before returning to the caller; manual instantiation or self-invocation can bypass the proxy.
- **Exercise 5:** Inbox, order, and outbox all roll back together if they share one transaction manager.
- **Exercise 6:** Order commits independently while inbox/outbox roll back; redelivery may re-apply the order.
- **Exercise 7:** Outbox persists publish intent with DB commit; the publisher can still duplicate sends after a crash.
- **Exercise 8:** Downstream may receive the same event again; inbox/idempotency prevents duplicate side effects.
- **Exercise 9:** Committing offsets before DB risks losing records; DB before offsets risks redelivery; inbox guards repeats.
- **Exercise 10:** ACK confirms delivery, not DB commit; closing the channel before ACK can requeue the message.
- **Exercise 11:** Without subscription, lazy work has not run; reactive transactions end on Publisher `onComplete`/`onError`.
- **Exercise 12:** Long transactions hold locks/connections and one failure affects the whole stream; per-item transactions isolate independent events.
- **Exercise 13:** Building a Publisher has not executed or committed yet; subscribe and await transaction completion before ACKing.
- **Exercise 14:** An in-process listener will not run if the process dies after commit; an outbox durably persists publish intent.
- **Exercise 15:** Kafka transactions cover only Kafka; XA requires supporting resource managers, drivers, and transaction managers plus recovery overhead.
- **Exercise 16:** Inject failure in outbox to assert inbox/order rollback; commit the service, simulate lost ACK, and re-invoke the same event.
- **Exercise 17:** Batch retry/offset semantics may replay earlier records; keep per-record processing idempotent.
- **Exercise 18:** Event ID, transaction outcome, ACK attempt, delivery count, binder/partition/offset, duplicate outcome, and outbox age.

## 24. Key Takeaways

- **Function completion, DB commit, and broker ACK are three distinct milestones.**
- ACKing before DB commit risks losing messages if the transaction rolls back; committing before ACK risks redeliveries.
- For DB-writing consumers, let the transaction complete before the binder confirms success and handle redeliveries with an inbox/unique key.
- Place `@Transactional` on application services invoked through Spring proxies; watch self-invocation, propagation, rollback rules, and flush/commit-time errors.
- Inbox markers must commit alongside business changes; outbox rows record publish intent inside the same DB transaction.
- An outbox can still publish duplicates; downstream consumers still need inbox/dedupe protection.
- Kafka, RabbitMQ, and serverless platforms have different ACK, offset, batch, and retry semantics; Spring Cloud Function provides no single portable ACK API.
- Reactive transactions finish with the Publisher's lifecycle; never fire-and-forget and assume the adapter saw completion.
- Broker transactions do not automatically include an external database; XA/distributed transactions work only when resources and configuration support them.
- Test pre-commit rollbacks, post-commit redeliveries, ACK failures, batches, and real brokers to verify post-failure data state.







