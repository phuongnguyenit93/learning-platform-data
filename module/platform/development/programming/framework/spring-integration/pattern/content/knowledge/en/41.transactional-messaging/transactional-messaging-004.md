# Transaction Synchronization in Flows with Spring Integration

## 1. Why Synchronize Actions with the Transaction Lifecycle?

An **IntegrationFlow** may receive a request via a Gateway, use a Transformer to normalize data, a Filter to drop invalid messages, a Router to branch, and a Service Activator to write to a database. Alongside business steps, systems often need to execute actions **at the exact moment the transaction finishes**, such as:

- Emitting a notification only when the order-creation transaction has **committed**.
- Recording or cleaning up resources when the transaction **rolls back**.
- Updating a file's status after database writes complete.
- Tracking transaction outcomes across synchronous processing branches, pollers, or listeners.

**Transaction Synchronization** is a mechanism for registering callbacks attached to **the lifecycle of an active transaction**. Instead of guessing whether an SQL statement actually committed, the callback receives a signal from the transaction manager at well-defined phases.

However, **callbacks do not expand the atomicity scope**. Running a send to a broker inside `afterCommit` means the send executes *after* the DB commits, not that the broker joins the DB transaction. If the application crashes between DB commit and sending, the event can still be lost.

This lesson belongs to the **Transactional messaging** chapter in the `SPRING_INTEGRATION_PATTERN` module, aimed at designing Enterprise Integration Patterns that are loosely coupled, extensible, traceable along message paths, and explicit in error handling.

### Learning Objectives

After this lesson, you can:

1. Distinguish between a transaction, a transaction boundary, and a synchronization callback.
2. Understand the order and meaning of `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion`.
3. Register callbacks from a handler inside a Spring Integration flow when a real transaction is active.
4. Understand how transaction synchronization relates to polling endpoints, message stores, and asynchronous branches.
5. Predict outcomes when a callback fails, a transaction rolls back, or a process crashes after commit.
6. Choose between post-commit callbacks, `@TransactionalEventListener`, and the transactional outbox; test via failure injection.

## 2. Distinguishing Transactions from Transaction Synchronization

| Concept | Responsibility | What must NOT be inferred |
| --- | --- | --- |
| **Transaction** | Groups operations on participating resources to commit or roll back per configuration. | That all HTTP, broker, or email calls belong to the JDBC transaction. |
| **Transaction manager** | Starts and ends transactions and coordinates resources within its management scope. | That a local transaction manager automatically coordinates every database and broker. |
| **Transaction boundary** | The start and end points of a transaction. | That the boundary automatically crosses threads, async channels, or other services. |
| **Transaction synchronization** | Allows callbacks to run at commit/rollback/completion phases of a transaction. | That callbacks create a new transaction or are guaranteed to run after a process crash. |
| **Acknowledgement (ACK)** | Confirms message reception/processing per the source/broker contract. | That DB commit means the ACK also commits atomically. |

In Spring's imperative transaction model, transaction state is typically bound to the **current thread**. Therefore:

- A handler running through a `DirectChannel` on the same thread can see the caller's transaction.
- A handler running on an `ExecutorChannel` usually runs on a different thread and does not automatically inherit the transaction/synchronization.
- Message headers like `correlationId` or `sequenceNumber` do not carry a transaction downstream.
- For brokers or remote services, each side must define its own transaction and ACK mechanism.

When you need an action "after the order has committed", transaction synchronization helps pick the timing; when you need "the event **must not be lost** if the process crashes", durable storage such as an outbox is required.

## 3. Spring's Standard Callback Lifecycle

Spring Framework provides `TransactionSynchronization` and `TransactionSynchronizationManager`. A synchronization is normally registered within an **active transaction**; the transaction manager invokes the corresponding methods based on completion status.

~~~mermaid
flowchart TD
    A["Begin transaction"] --> B["Flow executes business logic"]
    B --> C{"Ends with commit?"}
    C -->|"Yes"| D["beforeCommit(readOnly)"]
    D --> E["beforeCompletion()"]
    E --> F{"Resource commit succeeds?"}
    F -->|"Yes"| G["afterCommit()"]
    G --> H["afterCompletion(COMMITTED)"]
    F -->|"No / unknown outcome"| U["afterCompletion(ROLLED_BACK or UNKNOWN, depending on outcome)"]
    C -->|"Rollback"| R["beforeCompletion()"]
    R --> S["Rollback resources"]
    S --> T["afterCompletion(ROLLED_BACK)"]
~~~

The diagram illustrates the primary meaning of each phase. Exact details when errors occur or when the transaction manager cannot ascertain the commit outcome depend on the specific resource and transaction manager.

| Callback | Timing | Valid uses | Notes |
| --- | --- | --- | --- |
| `beforeCommit(boolean readOnly)` | Before the transaction manager proceeds to commit. | Final checks, syncing internal state when appropriate. | **Commit can still fail** after the callback; exceptions can prevent commit/lead to rollback. |
| `beforeCompletion()` | Before transaction completion, even when about to roll back. | Resource cleanup during pre-completion preparation. | Unsuitable for emitting "committed" events; exceptions here are typically logged per framework handling. |
| `afterCommit()` | After the transaction has committed successfully. | Best-effort notifications, cache eviction, triggering secondary work. | Cannot roll back an already committed transaction; the callback is not guaranteed to run if the process crashes. |
| `afterCompletion(int status)` | When the transaction ends, with commit/rollback/unknown status. | Logging/tracing, cleanup, resource release; branching on success/failure. | Not a new transaction; callback exceptions do not turn a commit into a rollback. |

Common status constants:

~~~java
TransactionSynchronization.STATUS_COMMITTED
TransactionSynchronization.STATUS_ROLLED_BACK
TransactionSynchronization.STATUS_UNKNOWN
~~~

**There is no `afterRollback()` method on the standard `TransactionSynchronization` interface.** To handle rollback specifically, check `status == STATUS_ROLLED_BACK` inside `afterCompletion(status)`. Some Spring Integration abstractions expose an "after rollback" hook/expression concept; do not confuse those with the Spring Framework interface signature.

### Three Misconceptions to Avoid

1. **`beforeCommit` does not guarantee commit will succeed afterward.** Commit failures, rollback-only status, or resource errors can still prevent the transaction from succeeding.
2. **`afterCommit` is not inside a new JDBC transaction.** Resources may still be bound during the callback phase; if you need a separate committable DB write, call a service that genuinely opens **`REQUIRES_NEW`** through a Spring proxy.
3. **`afterCompletion(COMMITTED)` does not mean the broker received the message.** It only describes the state of the transaction the synchronization participated in.

## 4. Where Transaction Synchronization Fits in an IntegrationFlow

Consider an order processing flow:

~~~mermaid
flowchart LR
    A["CheckoutService @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Filter / Transformer"]
    D --> E["Service Activator: save order"]
    E --> F["Register synchronization"]
    F --> G[("Orders DB")]
    G --> H{"Transaction completes"}
    H -->|"Commit"| I["afterCommit: send event"]
    H -->|"Rollback"| J["afterCompletion: cleanup"]
~~~

For **DirectChannel**, the handler runs synchronously on the sender's thread. If the application service has opened a transaction, the handler can register a synchronization onto **that same transaction**.

Conversely, if input passes through an `ExecutorChannel` or a broker before reaching the handler, the original transaction **does not travel with** the message. The handler must execute inside a new transaction opened by a consumer, service, or polling endpoint.

A synchronization registered inside a handler does not necessarily execute when the handler returns: if the transaction is managed by an **outer service**, the callback only runs **when the outer transaction actually completes**.

## 5. Java Example: Sending an Event After DB Commit

Suppose this lab uses Spring Boot, Spring Integration Java DSL, Spring JDBC, and a suitable `DataSourceTransactionManager`/`JdbcTransactionManager`. Database table:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    state VARCHAR(24) NOT NULL
);
~~~

Payload definitions:

~~~java
record CreateOrder(String orderId, BigDecimal amount) {}
record OrderCreated(String eventId, String orderId) {}
~~~

Create the Gateway and two flows. `outboundEvents` is configured as a `DirectChannel` in the example to illustrate when the external handler is invoked; actual publishing to a broker is implemented by `OrderEventPublisher`:

~~~java
@MessagingGateway(defaultRequestChannel = "orderCommands")
interface OrderGateway {
    void create(CreateOrder command);
}

interface OrderEventPublisher {
    void publish(OrderCreated event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlowConfig {
    @Bean("orderCommands")
    MessageChannel orderCommands() {
        return new DirectChannel();
    }

    @Bean("outboundEvents")
    MessageChannel outboundEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow createOrderFlow(OrderWriter writer) {
        return IntegrationFlow.from("orderCommands")
                .handle(writer, "writeAndRegister")
                .get();
    }

    @Bean
    IntegrationFlow eventPublishFlow(OrderEventPublisher publisher) {
        return IntegrationFlow.from("outboundEvents")
                .handle(message -> publisher.publish(
                        (OrderCreated) message.getPayload()))
                .get();
    }
}
~~~

The application service owns the transaction:

~~~java
@Service
class CheckoutService {
    private final OrderGateway gateway;

    CheckoutService(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void place(CreateOrder command) {
        gateway.create(command);
    }

    @Transactional
    public void placeThenFail(CreateOrder command) {
        gateway.create(command);
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

The handler writes to the DB, checks the transaction, and registers synchronization:

~~~java
@Component
class OrderWriter {
    private final JdbcTemplate jdbc;
    private final MessageChannel outboundEvents;

    OrderWriter(
            JdbcTemplate jdbc,
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.jdbc = jdbc;
        this.outboundEvents = outboundEvents;
    }

    public void writeAndRegister(CreateOrder command) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException(
                    "A real transaction with synchronization is required");
        }

        jdbc.update("""
                INSERT INTO orders(order_id, amount, state)
                VALUES (?, ?, ?)
                """,
                command.orderId(), command.amount(), "CREATED");

        // Generate the ID once for the event; do not mint a new ID on publish retries.
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(), command.orderId());

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        boolean accepted = outboundEvents.send(
                                MessageBuilder.withPayload(event).build());
                        if (!accepted) {
                            throw new IllegalStateException(
                                    "outboundEvents rejected the event");
                        }
                    }

                    @Override
                    public void afterCompletion(int status) {
                        if (status ==
                                TransactionSynchronization.STATUS_ROLLED_BACK) {
                            // Can clean up internal state or record metrics.
                            // DO NOT infer that all external side effects
                            // have been undone.
                        }
                    }
                });
    }
}
~~~

**Success path:**

1. `CheckoutService.place()` is invoked through the Spring proxy and opens a transaction.
2. The Gateway sends `CreateOrder` over `DirectChannel` to `OrderWriter` on the same thread.
3. The handler inserts into `orders`, then registers a synchronization on the active transaction.
4. The handler and Gateway calls return; `place()`'s transaction commits.
5. Spring invokes `afterCommit()`. Only then does `outboundEvents.send()` execute.
6. Spring finishes the lifecycle and calls `afterCompletion(STATUS_COMMITTED)`.

When `placeThenFail()` throws an exception matching rollback rules, the DB transaction rolls back; `afterCommit()` **is not called**. However, `afterCompletion(STATUS_ROLLED_BACK)` can be used for cleanup or observability.

### Conditions for the Example to Work Properly

- `@Transactional` must genuinely apply via the Spring transaction interceptor; do not call `this.place(...)` expecting the proxy to activate.
- `DirectChannel` must remain synchronous; replacing it with an executor causes the handler to run outside `CheckoutService`'s transaction.
- `JdbcTemplate` must use a datasource participating in the transaction manager.
- `OrderEventPublisher` is an application-provided bean implemented appropriately for the real broker/API.
- The example illustrates **best-effort post-commit send**; it does not yet guarantee events will not be lost on crash.

### What If There Is No Active Transaction?

`TransactionSynchronizationManager.isSynchronizationActive()` checks whether the framework currently allows synchronization registration, whereas `isActualTransactionActive()` reflects an actual running transaction. Under propagation settings like `SUPPORTS`, synchronization may be active without an actual transaction; thus the example deliberately checks **both** when aiming for a callback after a **real DB commit**.

If a handler can be invoked in both cases, choose an **intentional policy**:

- Require a transaction: reject as in the example; invoke through an application service or handler with an appropriate boundary.
- Allow no transaction: define dedicated handling for the non-transactional path, such as sending directly or writing to an outbox; do not pretend an after-commit callback was registered.

Never register a callback when transaction synchronization is inactive, because `registerSynchronization()` will fail.

## 6. If the Callback Fails, Does the DB Roll Back?

Consider `afterCommit()` calling a broker and the broker returning a network error:

~~~text
INSERT order in transaction    -> succeeds
COMMIT DB                      -> succeeds
afterCommit -> publish broker  -> fails
~~~

**The order remains in the database.** An exception from `afterCommit()` may propagate out of the transactional call depending on the callback and transaction manager, making the caller think `place()` failed even though data committed. If the caller retries `place()` entirely, it may hit a duplicate key or run business logic twice.

Therefore:

- Never treat a post-commit exception as proof that data can be rolled back.
- If retrying at the sender, determine the prior commit result or design idempotent operations.
- For critical events, **write to an outbox in the same transaction** to establish a durable recovery point.
- For best-effort tasks (such as cache eviction or metrics), the callback may catch and record the error per business policy; never silently swallow critical errors.

### Can `beforeCommit()` Save Cross-DB-and-Broker Atomicity?

No. If external publishing executes in `beforeCommit()`, the broker may already receive the message while the database still rolls back due to a subsequent commit failure. Both approaches have a "gap":

| Broker send timing | Primary risk |
| --- | --- |
| `beforeCommit()` | Message was sent, yet the database has not committed and may roll back. |
| `afterCommit()` | Database committed, yet the process may crash before sending. |
| `afterCompletion(COMMITTED)` | Also a post-commit action; not guaranteed to execute on process crash. |
| **Outbox in the same DB transaction** | Send intent is persisted with business data; replayable after restart, though the publisher may send duplicates. |

Thus **transaction synchronization is a timing coordination tool**, not a mechanism guaranteeing atomic messaging across independent resources.

## 7. `afterCompletion` on Rollback and Unknown States

Some logic should run only when a transaction fails:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status ==
                        TransactionSynchronization.STATUS_ROLLED_BACK) {
                    // Clean up temporary in-memory state, record rollback metric.
                } else if (status ==
                        TransactionSynchronization.STATUS_COMMITTED) {
                    // Record commit metric or release resources.
                } else {
                    // STATUS_UNKNOWN: final state is uncertain.
                    // Must reconcile using durably persisted state.
                }
            }
        });
~~~

**A rollback callback is not a compensating transaction.** If the handler already called an external ordering API before rolling back, after-completion does not undo that call. If true compensation is needed, persist state and provide a retryable compensation mechanism (typically a Saga or standalone job).

When the final status is `STATUS_UNKNOWN`, do not assume committed or rolled back. You may need to query the database, inspect transaction logs, or use a business request ID to reconcile, depending on resource manager behavior.

### Writing to the Database in `afterCommit` or `afterCompletion`

At synchronization invocation time, some resources may still be held/bound on the thread by Spring. Simply reusing a repository or `JdbcTemplate` **does not mean a new commit will happen**. If you need to write an audit log in an independent transaction, call **another Spring bean** with a new propagation:

~~~java
@Service
class AuditRecordingService {
    private final JdbcTemplate jdbc;

    AuditRecordingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String result) {
        jdbc.update(
                "INSERT INTO order_tx_audit(order_id, result) VALUES (?, ?)",
                orderId, result);
    }
}
~~~

The `record(...)` call assumes an `order_tx_audit` table exists. The bean registering the synchronization must invoke `AuditRecordingService` **through its proxy**. Using `this.record(...)` within the same bean bypasses `@Transactional`. Even so, writing audit logs in a new post-commit transaction still risks loss if the process dies; write to an outbox/audit inside the original transaction if auditing is mandatory.

## 8. Transaction Synchronization at a Polling Endpoint

In Spring Integration, a polling endpoint can be configured so a transaction wraps the poll task and **synchronous** downstream processing:

~~~java
@Bean
IntegrationFlow workerFlow(
        PlatformTransactionManager transactionManager,
        OrderWriter writer) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "writeAndRegister")
            .get();
}
~~~

This snippet illustrates the **boundary**; `workQueue` and incoming payloads must match the handler, and the sample `writeAndRegister` handler expects a `CreateOrder` payload. With a transactional poller:

1. The poller opens a transaction per the configured advice.
2. The poller receives a message from the `PollableChannel` or source.
3. Synchronous downstream handlers execute and can register synchronizations.
4. When all work within the boundary finishes, Spring commits/rolls back and invokes callbacks.

**Message source note:** if `workQueue` is an in-memory `QueueChannel`, a JDBC rollback does not automatically make dequeuing transactional. An `afterRollback` callback does not put the element back into the queue. To recover messages after crashes, use a source with appropriate persistence/ack/redelivery.

### Spring Integration's Own Synchronization Abstractions

Beyond Spring Framework's `TransactionSynchronization`, Spring Integration provides abstractions such as `TransactionSynchronizationFactory`, `DefaultTransactionSynchronizationFactory`, and `ExpressionEvaluatingTransactionSynchronizationProcessor` to register phase-based actions in supported polling/adapter scenarios.

The typical idea is: **when polling a resource**, capture context about the received data and evaluate an expression or send to a corresponding channel after commit or rollback. This is useful for file sources or message sources where you want to mark items processed, relocate files, or report errors based on the transaction outcome.

Business example:

~~~text
Poll file import/orders-17.csv
    -> begin transaction
    -> parse/filter/transform rows
    -> insert orders into database
    -> commit DB transaction
    -> afterCommit: move file to processed/

If rollback:
    -> afterCompletion(ROLLED_BACK) / rollback hook:
       keep or move file to retry/quarantine area
       per configured policy
~~~

In real configurations, inspect the Spring Integration version's API, how the adapter manages resources/messages, post-commit expressions, and the transaction manager used. **Moving a file** on a standard filesystem is not part of a JDBC transaction; the callback can fail after the DB commits. Design processing to tolerate re-runs if the file remains in the source directory.

### Poller Transactions and Callbacks Do Not Replace ACK

Suppose messages arrive from JMS or Kafka:

- **The poller/handler transaction** can roll back database updates if the handler fails.
- **The source's transaction or acknowledgement** determines whether the message is redelivered or the offset is committed.
- **Transaction synchronization** invokes callbacks according to the registered transaction lifecycle; it does not alter the broker's redelivery policy.

Specifically, errors on an `ExecutorChannel` branch can occur **after the poller/listener completes**. Callbacks on the earlier transaction do not wait for asynchronous work to finish without explicit coordination.

## 9. Comparing `@TransactionalEventListener` with Direct Synchronization

Spring Framework also supports transaction-bound event listeners:

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher events;
    private final JdbcTemplate jdbc;

    OrderService(ApplicationEventPublisher events, JdbcTemplate jdbc) {
        this.events = events;
        this.jdbc = jdbc;
    }

    @Transactional
    public void create(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, amount, state) VALUES (?, ?, ?)",
                orderId, new BigDecimal("100.00"), "CREATED");

        events.publishEvent(new OrderCreated(
                UUID.randomUUID().toString(), orderId));
    }
}

@Component
class AfterCommitEventHandler {
    private final MessageChannel outboundEvents;

    AfterCommitEventHandler(
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.outboundEvents = outboundEvents;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publishAfterCommit(OrderCreated event) {
        outboundEvents.send(
                MessageBuilder.withPayload(event).build());
    }
}
~~~

Here a Spring application event is published **inside** the transaction; the listener runs at the specified phase when the transaction completes successfully. By default, a `@TransactionalEventListener` does not run if the event is published **outside** a transaction unless `fallbackExecution` is configured. It does not automatically persist the event to durable storage.

| Criterion | Direct `TransactionSynchronization` | `@TransactionalEventListener` |
| --- | --- | --- |
| Registration | Call `TransactionSynchronizationManager.registerSynchronization(...)` in code. | Publish an application event and declare a listener with `TransactionPhase`. |
| Purpose | Direct control over callbacks, cleanup, and commit/rollback status. | Decouple event-emitting code from phase-reactive listeners. |
| Observing rollback | `afterCompletion(status)`, checking status constants. | Choose `AFTER_ROLLBACK` or `AFTER_COMPLETION` as appropriate. |
| Transaction requirement | Synchronization must be active; usually needs an actual transaction for real commit semantics. | Normally the listener runs with the event's transaction; has `fallbackExecution`. |
| Crash durability guarantee | No. | No. |
| Best-fit scenarios | Technical hooks, cleanup, or in-flow coordination. | Decoupled business events, best-effort post-commit actions. |

**Do not use both mechanisms simultaneously just to "be extra safe"**: if both send the same event, application code itself will emit duplicates. Pick one consistent mechanism per responsibility.

## 10. Transactional Outbox When Durable Event Publishing Is Required

For critical business logic, we need a stronger guarantee than "try sending if the process is still alive after commit". The standard solution is the **transactional outbox**:

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant DB as Business DB + Outbox
    participant Relay as Outbox Publisher
    participant Broker as Broker
    participant Consumer as Consumer
    App->>DB: BEGIN
    App->>DB: INSERT orders
    App->>DB: INSERT outbox_events
    App->>DB: COMMIT both
    Note over DB: Pending event is durable
    Relay->>DB: Poll/claim PENDING
    Relay->>Broker: Publish eventId
    Broker-->>Relay: Publish confirmation
    Relay->>DB: Mark SENT
    Broker->>Consumer: Deliver eventId
    Consumer->>Consumer: Deduplicate eventId
~~~

Illustrative schema:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Within a `@Transactional` service, write business data **and** the outbox row using the same datasource:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    String eventId = UUID.randomUUID().toString();
    jdbc.update(
            "INSERT INTO orders(order_id, amount, state) VALUES (?, ?, ?)",
            command.orderId(), command.amount(), "CREATED");

    jdbc.update("""
            INSERT INTO outbox_events
              (event_id, aggregate_id, event_type,
               payload_json, delivery_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            eventId,
            command.orderId(),
            "OrderCreated",
            serializeOrderCreated(eventId, command.orderId()),
            "PENDING");
}
~~~

The example assumes a `serializeOrderCreated(...)` helper and `jdbc` bean exist in the service. When the transaction rolls back, neither the order nor the outbox row commits; when it commits, the outbox row remains for the relay to send even after an app restart.

**Outboxes can still publish duplicates**: the broker may accept the event successfully while the relay crashes before marking `SENT`. Hence you must have a stable event identifier (`eventId`) and an **idempotent** consumer, such as a `processed_events` table with a unique constraint updated in the same transaction as business logic.

In this architecture, transaction synchronization can serve as a **post-commit wake-up signal for the relay** to reduce latency; however, **the outbox record itself is the source of truth** for recovery if the callback signal is lost. The relay still needs an independent polling schedule or equivalent recovery mechanism.

## 11. Error Channel, Retry, and Asynchronous Branches

Patterns make flows readable, yet also introduce multiple boundary shifts:

~~~mermaid
flowchart LR
    A["Gateway"] --> B["DirectChannel"]
    B --> C["Filter / Transformer"]
    C --> D{"Router"}
    D --> E["JDBC handler + callback"]
    D --> F["ExecutorChannel"]
    F --> G["Async worker"]
    E --> H["Transaction completes"]
    G --> I["Worker's own transaction"]
    I --> J["Aggregator / error channel"]
~~~

### Where Are Errors Caught?

- **DirectChannel:** handlers normally run synchronously. If an exception propagates up to the `@Transactional` service, the transaction can roll back; `afterCommit` callbacks will not execute.
- **ExecutorChannel:** handlers can fail after the caller has returned. Transaction callbacks on the caller's thread do not automatically know the worker's outcome.
- **Error channel:** an `ErrorMessage` may reach a dedicated error flow. A handler consuming the error and returning normally **can cause the transaction/container to treat the task as successful**. Verify which exceptions actually escape the boundary.
- **Retry advice:** if retry wraps outside the transaction boundary, each attempt can open a fresh transaction; if retry sits *inside* a transaction already marked `rollback-only`, retrying on the same connection may fail. Check advice ordering.
- **Splitter/Aggregator:** correlation links results, but does not merge transactions across branches into a single atomic transaction; the aggregator must handle timeouts, duplicates, and durable state when needed.

### When a Callback Is Registered and Then Retried

Suppose a handler writes to the DB, registers `afterCommit`, and later encounters an error:

1. If the transaction **rolls back**, that attempt's `afterCommit` callback does not run.
2. A retry opening a **new transaction** can register a new callback.
3. If multiple messages or handlers register callbacks within one transaction, **multiple callbacks** may fire at commit; control them by event ID to avoid duplicate publishing.
4. If commit succeeds but the callback fails to send, retrying the whole order may duplicate business actions; use an outbox or idempotency.

Never generate a new ID on every publish retry of **the same event**. Spring Integration's `messageId`, job-grouping `correlationId`, and deduplication `eventId` serve distinct purposes.

## 12. Testing Transaction Synchronization

The most valuable tests verify **when callbacks run** and **whether data actually committed/rolled back**.

### Testing with a Recording Event Publisher

Suppose `OrderEventPublisher` is replaced by a fake bean recording received `eventId`s in memory, with the service/flow from section 5:

~~~java
@SpringBootTest
class OrderSynchronizationIT {
    @Autowired CheckoutService checkout;
    @Autowired JdbcTemplate jdbc;
    @Autowired RecordingPublisher publisher;

    @Test
    void sendsOnlyAfterSuccessfulCommit() {
        String orderId = UUID.randomUUID().toString();

        checkout.place(new CreateOrder(
                orderId, new BigDecimal("125.00")));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);
        assertEquals(1, rows);
        assertTrue(publisher.containsOrder(orderId));
    }

    @Test
    void skipsAfterCommitOnRollback() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> checkout.placeThenFail(new CreateOrder(
                        orderId, new BigDecimal("125.00"))));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);
        assertEquals(0, rows);
        assertFalse(publisher.containsOrder(orderId));
    }
}
~~~

`RecordingPublisher` is a test double for `OrderEventPublisher`, implemented in the lab and registered via Spring test configuration. The test assumes the database schema exists and publisher state is isolated across tests. Avoid putting `@Transactional` on **the test itself** if doing so wraps the service transaction and hides actual commit timing.

To test **ordering**, use a fake publisher that queries `orders` right when receiving the event: when invoked in `afterCommit`, it must see the committed record on an independent test connection/transaction under appropriate isolation. Avoid letting the fake run inside the caller's uncommitted transaction, which yields misleading conclusions.

### Failure Injection Matrix

| Scenario | Observation to verify | Conclusion |
| --- | --- | --- |
| `@Transactional` service writes DB then rolls back | `afterCommit` does not send; `afterCompletion` sees rollback status. | Callback is bound to the real transaction. |
| `beforeCommit` throws runtime exception | DB does not commit per rollback rules and manager handling. | before-commit can prevent commit; no "committed" event fires. |
| DB commits, `afterCommit` broker call fails | DB still has the row; caller may observe the error. | Post-commit errors do not undo DB writes. |
| App crashes right after DB commit before callback | Event from callback may never be sent. | Durable outbox is required if no loss is allowed. |
| Flow switches to `ExecutorChannel` | Sender callback may run before worker handler finishes. | Worker needs its own transaction and tracking. |
| Transactional poller reads in-memory queue then fails | DB rolls back but message is not automatically requeued. | Synchronization does not replace a source transaction. |
| Outbox relay sends then crashes before marking `SENT` | Event may be resent after restart. | Consumer must be idempotent. |
| One transaction registers two callbacks publishing the same event | Duplicate emissions may occur. | Single-registration / deduplication policy is required. |

With a real broker, add tests for ACK/redelivery, DLQ, backoff, and async failures. In telemetry, distinguish timestamps for `message_received`, `db_commit`, `after_commit_hook`, `send_accepted`, `broker_confirmed`, and `consumer_processed`.

## 13. Guide to Choosing a Mechanism

| Requirement | Solution | Guarantees and limitations |
| --- | --- | --- |
| In-memory cleanup or resource release when transaction finishes | `afterCompletion(status)` | Suits local technical tasks; not crash-durable. |
| Invalidate cache only once data commits | `afterCommit` or `AFTER_COMMIT` event listener | Cache invalidation can be missed if app crashes; consider TTL/reconciliation. |
| Emit optional notification after commit | `@TransactionalEventListener(AFTER_COMMIT)` or callback. | Best-effort; specify logging/metrics when sends fail. |
| Emit critical business event that must not be lost | Transactional outbox + relay + idempotent consumer. | May publish duplicates; must manage retries, backlog, and dead letters. |
| Move file after polling and DB write | Poller/adapter transaction synchronization if supported. | Filesystem moves do not roll back with DB; safe replay is needed. |
| Receive from broker and write to DB | Consumer transaction + appropriate ACK/redelivery; idempotent inbox. | Broker transaction and DB transaction are not automatically atomic together. |
| Router/Splitter processing multiple async branches | Separate transaction per worker + correlation + durable state. | Callbacks on one branch do not reflect commit outcomes on other branches. |

### Rules for Placing Callbacks

**A callback must be registered in the transaction that owns the data the callback cares about.** Registering too early in an unrelated transaction or too late after the transaction finishes makes the callback semantically wrong.

With `REQUIRES_NEW`, a callback registered inside the child transaction runs when the **child transaction** completes; that does not imply the outer transaction will commit. Explicitly decide whether to synchronize with the **inner transaction** or the **outer business transaction**.

If a callback should execute only once for the whole transaction, ensure code does not register duplicates when a flow passes through multiple handlers/routes. When multiple synchronizations run, you can consider ordering via the `Ordered` contract if dependencies truly exist, though avoid business designs requiring complex callback ordering that is hard to test.

## 14. Hands-On Exercises

**Exercise 1 — Tracing callback timing.** Draw the timeline `CheckoutService @Transactional → Gateway → DirectChannel → JDBC handler → commit → afterCommit`. Add a Filter that drops valid messages, a Transformer that throws `RuntimeException`, and a handler that catches exceptions and returns; predict when commit/rollback occurs.

**Exercise 2 — Switching to ExecutorChannel.** Replace `DirectChannel` with `ExecutorChannel`. Check active transactions inside the worker, the ordering between caller commit and worker execution, and error handling when the worker fails after the caller's callback has already completed.

**Exercise 3 — Post-commit send is not durable.** Use a fake publisher that throws an exception in `afterCommit`. Observe that the DB committed while the caller sees an error. Propose how to prevent retries from creating duplicate orders, then replace direct sending with an outbox.

**Exercise 4 — File polling and moving directories.** Configure a polling flow that reads files, writes to the DB, and moves the file to `processed` only after commit. Simulate a file move failure right after DB commit; use business ID/idempotency so the next poll does not duplicate data.

**Exercise 5 — Branching and Aggregator.** Use Router/Splitter to send two async tasks sharing a `correlationId`. Each branch persists results in its own transaction, and an aggregator waits for all results. Determine what happens if one branch rolls back while the other branch's result already committed.

### Self-Assessment Questions

**1. Does a failing `afterCommit()` roll back the JDBC transaction?** No. The commit phase has already completed; callback errors cannot reverse the commit outcome.

**2. Why is `beforeCommit()` insufficient to guarantee a message is valid after commit?** Because the DB commit can still fail after the callback; an external message sent earlier may already have been received.

**3. Can you implement `afterRollback()` directly on `TransactionSynchronization`?** No. Use `afterCompletion(status)` and check `STATUS_ROLLED_BACK`; specific abstractions may provide separate rollback hooks.

**4. In a flow with `ExecutorChannel`, does a callback registered at the caller wait for the worker to finish?** Not by default. Thread-bound transactions do not automatically propagate to workers.

**5. When do you use an outbox instead of an after-commit callback?** When a business event must be recoverable and replayable after a process crash, requiring the send intent to be persisted in the same transaction as source data.

## 15. Pre-Production Checklist

- [ ] Clearly map transaction boundaries and identify who owns commit/rollback.
- [ ] Distinguish `isSynchronizationActive()` from `isActualTransactionActive()` when a real DB transaction is required.
- [ ] Register synchronizations only on the relevant transaction, avoiding duplicate registrations.
- [ ] Know which callbacks run on commit, rollback, and uncertain states.
- [ ] Never treat `beforeCommit` as proof that the DB will commit.
- [ ] Never use `afterCommit` as a guarantee that events definitely reached the broker.
- [ ] If performing additional DB writes in callbacks, use a genuinely new transaction when needed and define crash recovery.
- [ ] Inspect thread handoff points across `ExecutorChannel`, queues, brokers, and consumer transactions.
- [ ] For polling flows, verify whether the resource/source participates in the transaction and supports redelivery.
- [ ] Configure retries, error channels, DLQs, idempotency, and event ID/correlation ID tracking.
- [ ] For critical events, have an outbox, restartable relay, unique event IDs, and idempotent consumers.
- [ ] Test with failure injection before commit, after commit before callback, inside callbacks, and across each async branch.

**Takeaway:** **Transaction synchronization determines *when* a hook is invoked**, whereas the transaction manager and resources determine **what can commit/roll back together**. In Spring Integration, combining patterns makes flows extensible, yet every polling point, executor, and broker can create a new boundary; choose callbacks, transactions, and redelivery strategies matching your true reliability requirements.
