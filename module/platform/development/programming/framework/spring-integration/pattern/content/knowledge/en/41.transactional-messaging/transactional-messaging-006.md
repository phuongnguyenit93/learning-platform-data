# Transaction Propagation Across Service Activators in Spring Integration

## 1. The Problem: A Message Traverses Multiple Services—Who Owns the Transaction?

In Spring Integration, a **Service Activator** is an Enterprise Integration Pattern (EIP) that turns a message into a call to a business-processing method. A flow may receive a message from a Gateway, pass it through a Filter/Transformer/Router, and then invoke multiple Service Activators sequentially or across different branches.

For example, an order intake system executes:

1. The application service opens a transaction and writes `orders`.
2. The Gateway sends `ReserveCommand` to a `DirectChannel`.
3. Service Activator A writes `reserved_inventory`.
4. Service Activator B writes business audit log `audit_log`.
5. The application service detects an error and requests a rollback.

Question: **Are data in A and B rolled back along with the order?** The answer depends on each method's *transaction propagation*, the active transaction at invocation time, and how the channel delivers the message.

**Transaction propagation** is the rule Spring uses when a method with transaction advice is invoked **inside or outside an existing transaction**. It decides whether the method **joins the active transaction**, **starts an independent transaction**, **uses a savepoint**, **runs without a transaction**, or **rejects the call**. The fact that a method is a Service Activator does not automatically alter those rules.

In the `SPRING_INTEGRATION_PATTERN` module, understanding propagation properly helps build loosely coupled Router, Filter, Transformer, Splitter, Aggregator, and Gateway flows while accurately predicting commit/rollback, retries, error channels, and correlation across multi-branch flows.

### Learning Objectives

After this lesson, you can:

- Identify whether a transaction starts at the application service, poller, listener, or the Service Activator itself.
- Explain all seven standard `@Transactional` `Propagation` modes, especially `REQUIRED`, `REQUIRES_NEW`, and `NESTED`.
- Design two Service Activators operating under different transactions within the same `DirectChannel` flow.
- Analyze `UnexpectedRollbackException`, rollback-only, checked exceptions, non-proxied calls, and post-commit failures.
- Determine why `ExecutorChannel` or a broker breaks thread-bound transactions.
- Test outer rollback, inner commit, savepoint rollback, and duplicate handling across retry/redelivery.

## 2. Conditions for Propagation to Take Effect

A method annotated with `@Transactional` does not mean every call to it automatically passes through a transaction interceptor. In Spring's standard proxy model, the method must be called through an appropriate **Spring-managed proxy**; the annotation applies only when advice actually intercepts the call.

~~~mermaid
flowchart LR
    A["Application service @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Service Activator bean/proxy"]
    D --> E["Transaction interceptor"]
    E --> F["Business method + JDBC"]
~~~

For behavior to match the diagram:

1. The caller actually went through the `@Transactional` application service proxy.
2. The Service Activator targets a **Spring-managed bean**, and the handler invocation goes through the corresponding proxy/interceptor.
3. The flow still executes **synchronously on the same thread** if it is meant to join the caller's transaction.
4. The selected `PlatformTransactionManager` manages the exact database or resource used by the handler.
5. Exceptions and rollback rules allow the transaction interceptor to observe errors requiring rollback.

With `DirectChannel`, the handler is invoked synchronously on the message-sending thread. This is favorable for joining an active transaction, **yet `DirectChannel` does not open a transaction itself**.

With `ExecutorChannel`, the worker typically runs on a different thread: the caller's thread-bound transaction **does not automatically propagate**. `@Transactional(REQUIRED)` on the worker can open a new transaction because no caller transaction exists there.

### “Same Message” Does Not Mean “Same Transaction”

`MessageHeaders.ID`, `correlationId`, `sequenceNumber`, and `orderId` serve identification, routing, aggregation, and tracing. These headers are not a transaction context. When a message enters a queue, executor, or broker, determine the transaction at the **consumer**, rather than inferring it from the producer's transaction.

## 3. Seven Propagation Modes

`Propagation` belongs to `org.springframework.transaction.annotation.Propagation`.

| Mode | When caller **already has** a transaction | When there is **no** transaction | Use case |
| --- | --- | --- | --- |
| `REQUIRED` *(default)* | Joins the current transaction. | Opens a new transaction. | JDBC handlers belonging to the same business unit of work. |
| `REQUIRES_NEW` | Suspends the outer transaction and opens an independent one. | Opens a new transaction. | Writing a required independent outcome, at the risk of committing before the outer transaction. |
| `NESTED` | Uses a nested transaction with a savepoint if manager/resource supports it. | Usually behaves like `REQUIRED` and opens a new transaction. | Allows partial JDBC rollback while the outer transaction can continue. |
| `SUPPORTS` | Joins the existing transaction. | Runs without an actual transaction. | Queries or logic that can use a transaction if provided by the caller. |
| `MANDATORY` | Joins the current transaction. | Throws an error because no active transaction exists. | Enforces that the caller owns a transaction for operations requiring consistency. |
| `NOT_SUPPORTED` | Suspends the current transaction, runs without one. | Runs without a transaction. | Work that must not run transactionally; understand side effects outside rollback. |
| `NEVER` | Throws an error because an active transaction exists. | Runs without a transaction. | Forbids invocation inside a transactional context. |

`REQUIRED`, `REQUIRES_NEW`, and `NESTED` are the three modes requiring the closest distinction. The others matter when a Service Activator is reused across multiple endpoints or invoked through branches with differing transaction boundaries.

### Decision Diagram

~~~mermaid
flowchart TD
    A["Service Activator invoked through transaction interceptor"] --> B{"Current thread already has a transaction?"}
    B -->|"Yes"| C{"Propagation?"}
    B -->|"No"| D{"Propagation?"}
    C -->|"REQUIRED / SUPPORTS / MANDATORY"| E["Join current transaction"]
    C -->|"REQUIRES_NEW"| F["Suspend outer, open independent transaction"]
    C -->|"NESTED"| G["Savepoint if supported"]
    C -->|"NOT_SUPPORTED"| H["Suspend outer, run non-transactionally"]
    C -->|"NEVER"| I["Error"]
    D -->|"REQUIRED / REQUIRES_NEW / NESTED"| J["Open new transaction"]
    D -->|"SUPPORTS / NOT_SUPPORTED / NEVER"| K["Run non-transactionally"]
    D -->|"MANDATORY"| L["Error"]
~~~

When a `REQUIRED` method **joins an existing transaction**, attributes like `isolation`, `timeout`, and `readOnly` declared on that method **do not by default override** those of the physical transaction already opened by the outer call. A transaction manager can be configured to validate attribute compatibility when joining. Look at **which boundary actually opens the physical transaction**.

## 4. Logical Transactions vs. Physical Transactions

In Spring, each `@Transactional` invocation can create its own interceptor's **logical transaction scope**. Yet multiple `REQUIRED` scopes can share **one physical transaction** on the database.

~~~mermaid
flowchart LR
    subgraph P["Physical TX-A: single commit/rollback"]
        O["Outer @Transactional(REQUIRED)"] --> I["Activator A @Transactional(REQUIRED)"]
        I --> DB[("Same JDBC connection / DB resource")]
    end
    O --> R["Activator B @Transactional(REQUIRES_NEW)"]
    subgraph Q["Physical TX-B: independent"]
        R --> DB2[("DB connection for TX-B")]
    end
~~~

**REQUIRED:** handler A and the caller can share TX-A. Handler A returning normally **has not committed yet** while the caller keeps TX-A open. If the caller throws later, A's data can also roll back.

**REQUIRES_NEW:** handler B creates TX-B while TX-A is suspended. TX-B commits/rolls back independently. If TX-B commits and TX-A later rolls back, TX-B's data **remains persisted**. Conversely, if TX-B throws to the caller and the caller does not catch it, TX-A can also roll back per rollback rules—that does not mean the two transactions became one.

**NESTED:** with a savepoint-capable manager, the inner scope can roll back to a savepoint while the outer continues; however, the inner scope **has no independent commit** like `REQUIRES_NEW`. If the outer rolls back, changes that occurred within the savepoint still roll back with the outer transaction.

### Why Does This Matter for Messages?

One message may pass sequentially through Service Activator A and then B on the same `DirectChannel`, yet **A and B can have different commit outcomes**. Channel names, payloads, and correlation do not reveal transaction types; inspect proxy entry points, propagation, and the transaction manager.

## 5. Practical Example: REQUIRED and REQUIRES_NEW in the Same Flow

This example uses Spring Boot, Spring Integration Java DSL, Spring JDBC, and a transaction manager configured for the same `DataSource`. Imports are omitted to focus on propagation semantics.

**Scenario:** the application service writes an order, sends a command to record reserved stock through a `REQUIRED` Service Activator, then sends an audit command through a `REQUIRES_NEW` Service Activator. Finally, the outer service throws an error.

### 5.1. Schema

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL
);

CREATE TABLE reserved_inventory (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);

CREATE TABLE audit_log (
    event_id VARCHAR(96) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    action VARCHAR(40) NOT NULL
);
~~~

In this lab, `audit_log` intentionally has **no foreign key** referencing `orders`, because `REQUIRES_NEW` can write the audit row **before** the outer order-creation transaction commits. In production data models, if audit rows strictly depend on committed orders, do not design an independent commit like this; consider an outbox or writing in the same transaction.

### 5.2. Payloads and Gateway

~~~java
record ReserveCommand(String orderId, int quantity) {}
record AuditCommand(String eventId, String orderId, String action) {}

@MessagingGateway
interface ReservationGateway {
    @Gateway(requestChannel = "reserveInput")
    void reserve(ReserveCommand command);

    @Gateway(requestChannel = "auditInput")
    void audit(AuditCommand command);
}
~~~

`@MessagingGateway` creates a typed API entry point. The two methods send messages to separate channels, clarifying which handler is responsible. A Gateway does not automatically bring transactions from other threads/brokers into the current transaction.

### 5.3. IntegrationFlow and DirectChannels

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationFlowConfig {

    @Bean("reserveInput")
    MessageChannel reserveInput() {
        return new DirectChannel();
    }

    @Bean("auditInput")
    MessageChannel auditInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reserveFlow(ReservationWriter writer) {
        return IntegrationFlow.from("reserveInput")
                .handle(writer, "write")
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(AuditWriter writer) {
        return IntegrationFlow.from("auditInput")
                .handle(writer, "write")
                .get();
    }
}
~~~

`.handle(writer, "write")` is a Java DSL Service Activator. For `@Transactional` to apply properly, `writer` must be a Spring bean whose method can be invoked via the transaction proxy. If using JDK dynamic proxies, the method must be exposed via a suitable interface; if using class-based proxies, the method must be compatible with that proxy mechanism. Verify with integration tests whenever bean/proxy creation changes.

### 5.4. Handler A — REQUIRED

~~~java
@Service
class ReservationWriter {
    private final JdbcTemplate jdbc;

    ReservationWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(ReserveCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        jdbc.update("""
                INSERT INTO reserved_inventory(order_id, quantity)
                VALUES (?, ?)
                """, command.orderId(), command.quantity());
    }
}
~~~

If the method is invoked while TX-A is active, `REQUIRED` **joins TX-A**. The `INSERT` does not commit independently when `write()` returns.

If the same handler is called from another endpoint **without** a transaction, `REQUIRED` **opens a new transaction** and commits/rolls back around `write()`. Therefore a handler cannot rely on `REQUIRED` to enforce that the caller *must* already hold a transaction; to require the caller to supply one, consider `MANDATORY`.

### 5.5. Handler B — REQUIRES_NEW

~~~java
@Service
class AuditWriter {
    private final JdbcTemplate jdbc;

    AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(AuditCommand command) {
        jdbc.update("""
                INSERT INTO audit_log(event_id, order_id, action)
                VALUES (?, ?, ?)
                """,
                command.eventId(), command.orderId(), command.action());
    }
}
~~~

When the outer scope already holds a transaction, Spring suspends TX-A and opens TX-B for `AuditWriter.write()`. TX-B finishes when the handler returns or throws. **TX-B commits before outer TX-A finishes.**

### 5.6. Application Service — Intentionally Producing Different Outcomes

~~~java
@Service
class ReservationApplicationService {
    private final JdbcTemplate jdbc;
    private final ReservationGateway gateway;

    ReservationApplicationService(
            JdbcTemplate jdbc,
            ReservationGateway gateway) {
        this.jdbc = jdbc;
        this.gateway = gateway;
    }

    @Transactional
    public void reserveNormally(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PENDING");

        gateway.reserve(new ReserveCommand(orderId, 2));
        gateway.audit(new AuditCommand(
                "audit-" + orderId, orderId, "RESERVATION_REQUESTED"));
    }

    @Transactional
    public void reserveThenFail(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PENDING");

        gateway.reserve(new ReserveCommand(orderId, 2));
        gateway.audit(new AuditCommand(
                "audit-" + orderId, orderId, "RESERVATION_REQUESTED"));

        throw new IllegalStateException("Simulated outer failure");
    }
}
~~~

**What remains in the database after `reserveThenFail(...)` finishes?**

| Data | Transaction | Expected outcome |
| --- | --- | --- |
| `orders` | Application service's TX-A | **Rolled back**, no row remains. |
| `reserved_inventory` | `REQUIRED` handler joins TX-A | **Rolled back**, no row remains. |
| `audit_log` | `REQUIRES_NEW` handler creates TX-B | **Committed**, row remains if TX-B succeeded. |

With `reserveNormally(...)`, both TX-B and TX-A can commit, so all three tables hold rows. In both methods, when `gateway.audit(...)` returns, TX-B has finished, whereas TX-A **has not necessarily committed yet**.

~~~mermaid
sequenceDiagram
    participant Facade as Application Service
    participant DB as Orders / Inventory DB
    participant Audit as Audit Service Activator
    Facade->>DB: BEGIN TX-A
    Facade->>DB: INSERT orders (TX-A)
    Facade->>DB: INSERT reserved_inventory via REQUIRED (TX-A)
    Facade->>Audit: Gateway -> DirectChannel -> write()
    Note over Facade,Audit: Suspend TX-A, begin TX-B
    Audit->>DB: INSERT audit_log (TX-B)
    Audit->>DB: COMMIT TX-B
    Audit-->>Facade: Return; resume TX-A
    Facade->>DB: Throw exception -> ROLLBACK TX-A
    Note over DB: audit_log still exists
~~~

**Performance note:** `REQUIRES_NEW` may require **another DB connection** while the outer connection is still held open. An undersized connection pool, especially when many threads open outer transactions and wait on inner ones, can cause pool exhaustion or connection-wait deadlocks. Pool sizing must account for nested independent transactions, concurrency, and timeouts.

## 6. Why REQUIRES_NEW Is Not the Default Solution for Audits and Events

Having an audit row committed before the outer transaction may be a **real requirement** (recording a trace of a failed attempt), or it may be a **consistency bug**: the audit claims “order placed” while the order actually rolled back.

| Goal | Usually more appropriate design |
| --- | --- |
| Audit that *an attempt occurred* even if the order ultimately failed | `REQUIRES_NEW`, describing the action as an attempt/decision, with a unique ID and tolerance for orphan references. |
| Audit that *an order committed successfully* | Write audit inside TX-A, or write an outbox/audit record in the same source transaction. |
| Publish `OrderCreated` to a broker after order commit | Transactional outbox and relay; do not rely solely on `REQUIRES_NEW` to publish. |
| Record independent technical logs/metrics | Logging/telemetry outside DB transactions with explicit error rules. |

**An independent transaction does not guarantee business-valid data.** For instance, if TX-B references a newly inserted `orders` row from uncommitted TX-A, TX-B may not see that row or may hit locks/constraints. Design dependencies and commit ordering around domain rules, avoiding reliance on uncommitted data from a suspended transaction.

### Retries and Duplicates with REQUIRES_NEW

If the outer transaction rolls back, receives a redelivery, and re-runs the flow, TX-B may attempt to write `audit-" + orderId` again. With `event_id` as primary key, the repeat insert can throw a duplicate-key exception. Choose a strategy:

- A business event should carry a **stable ID** across retries and use upsert/idempotent inserts.
- A new *attempt* log may have a distinct ID, while distinguishing an attempt from a committed business outcome.
- Do not let a secondary audit duplicate-insert error unintentionally reject the primary business action if the domain requires independence.

If auditing uses `REQUIRES_NEW` to preserve failure logs, ensure audit write failures do not unintentionally throw and roll back the outer transaction; this depends on caller exception handling and business policy.

## 7. NESTED — How Does a Savepoint Differ from an Independent Transaction?

`Propagation.NESTED` uses the concept of a **savepoint** within a single physical transaction when supported by the transaction manager and resource. In JDBC with a suitably configured `DataSourceTransactionManager`/`JdbcTransactionManager`, it typically lets the inner scope roll back its changes while the outer continues.

~~~mermaid
flowchart TD
    A["Begin outer TX-A"] --> B["INSERT order"]
    B --> C["Savepoint S1 before NESTED activator"]
    C --> D["Inner INSERT / UPDATE"]
    D --> E{"Inner succeeds?"}
    E -->|"No"| F["Rollback to S1"]
    E -->|"Yes"| G["Keep changes inside TX-A"]
    F --> H["Outer continues"]
    G --> H
    H --> I{"Outer commits?"}
    I -->|"Yes"| J["Commit TX-A"]
    I -->|"No"| K["Rollback entire TX-A"]
~~~

Standalone example for a handler:

~~~java
@Service
class OptionalEnrichmentWriter {
    private final JdbcTemplate jdbc;

    OptionalEnrichmentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void enrich(String orderId) {
        jdbc.update(
                "INSERT INTO optional_enrichment(order_id) VALUES (?)",
                orderId);

        // Simulate failure so transaction interceptor rolls back to savepoint.
        throw new IllegalStateException("Cannot enrich order");
    }
}
~~~

A caller holding TX-A can invoke the method via proxy and **intentionally catch the error** so the outer flow proceeds:

~~~java
@Transactional
public void process(String orderId) {
    ordersRepository.insert(orderId);
    try {
        optionalEnrichmentWriter.enrich(orderId);
    } catch (IllegalStateException expected) {
        // Inner rolls back to savepoint if NESTED is supported.
        // Caller accepts missing enrichment and continues business logic.
    }
}
~~~

These two snippets demonstrate propagation when **invoking a regular Spring bean**. In an IntegrationFlow, `OptionalEnrichmentWriter` can likewise be a Service Activator invoked over `DirectChannel`; the same requirement applies that the transaction interceptor must actually be engaged.

**Important limitations:**

- Not every transaction manager supports `NESTED`; some fail immediately when attempting to start a nested transaction.
- `NESTED` uses a savepoint inside the **existing physical transaction**, not an independent commit like `REQUIRES_NEW`.
- After the inner succeeds, if the outer rolls back, the inner changes **still roll back with the outer**.
- Non-JDBC side effects such as broker publishes or HTTP calls are not undone merely by a savepoint rollback.
- If the inner method is called via `this.enrich(...)` bypassing the proxy, there is no guarantee a savepoint is created.

When unsure whether a resource supports savepoints, verify with an integration test against the exact database/transaction manager; never assume `NESTED` is a portable solution for JMS, Kafka, JPA, or distributed transactions.

## 8. SUPPORTS, MANDATORY, NOT_SUPPORTED, and NEVER on Service Activators

These modes typically express **invocation contracts**:

### MANDATORY — Handler Requires the Caller to Already Hold a Transaction

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void updateBalance(AccountMessage message) {
    jdbc.update("UPDATE accounts SET balance = ? WHERE id = ?",
            message.balance(), message.accountId());
}
~~~

When the handler runs synchronously over `DirectChannel` from a service holding a transaction, it can join that transaction. If called from a non-transactional source, Spring throws an error instead of silently opening a new transaction. This is useful for enforcing transaction boundaries **at the orchestration layer**.

**Warning:** if input is later switched to `ExecutorChannel` and the worker has no active transaction, `MANDATORY` will fail. This annotation cannot carry the caller's transaction over to the worker.

### SUPPORTS — Use Existing Transaction If Present

~~~java
@Transactional(propagation = Propagation.SUPPORTS, readOnly = true)
public CustomerInfo lookup(String customerId) {
    return repository.find(customerId);
}
~~~

If the caller has a transaction, the method joins it; otherwise it can run without a physical transaction. `readOnly = true` is a **transaction hint/attribute**, not a mechanism blocking all writes. When joining an already-open physical transaction, the method does not automatically convert that transaction to read-only.

### NOT_SUPPORTED — Suspend Transaction and Run Without One

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void invokeLegacyReport(String reportId) {
    legacyClient.generate(reportId);
}
~~~

If the caller has a transaction, Spring suspends it while running the method. Side effects in the legacy API do not roll back with the caller's transaction. Never use `NOT_SUPPORTED` to “reduce locking” while expecting the method's work to remain atomic with prior JDBC writes.

### NEVER — Forbid Invocation Inside a Transaction

~~~java
@Transactional(propagation = Propagation.NEVER)
public void performNonTransactionalTask(String taskId) {
    taskRunner.run(taskId);
}
~~~

If called within an active transaction, Spring throws an error. It fits when code must not run inside a transaction for explicit technical/business reasons. This mode **does not** suspend transactions like `NOT_SUPPORTED`.

### Decision Table by Business Requirement

| Want the handler to... | Mode to consider | What to remember |
| --- | --- | --- |
| Commit/roll back together with the caller | `REQUIRED` | Same thread/resources; default when a transaction already exists. |
| Reject if caller has no transaction | `MANDATORY` | Good contract at synchronous entry points; async needs a worker transaction. |
| Commit independently even if outer rolls back | `REQUIRES_NEW` | Requires suitable connections; business logic must accept independent state. |
| Partially roll back while outer continues | `NESTED` | Only when manager supports savepoints; outer rollback still affects inner. |
| Optionally participate in a transaction | `SUPPORTS` | No guarantee of a transaction when called directly. |
| Intentionally avoid using caller's transaction | `NOT_SUPPORTED` | Side effects are outside outer rollback. |
| Be forbidden from running inside a transaction | `NEVER` | Fails if caller holds a transaction. |

## 9. Rollback-Only and UnexpectedRollbackException

A common point of confusion: a `REQUIRED` Service Activator throws an exception, and the caller **catches it** and continues:

~~~java
@Service
class RequiredPricingWriter {
    @Transactional(propagation = Propagation.REQUIRED)
    public void updatePrice(PricingCommand command) {
        // Example throwing an error after some DB operations.
        throw new IllegalStateException("Pricing rule failed");
    }
}
~~~

~~~java
@Transactional
public void recalculate(String orderId) {
    ordersRepository.markProcessing(orderId);

    try {
        pricingGateway.apply(new PricingCommand(orderId));
    } catch (IllegalStateException ex) {
        // Catching the exception does not guarantee outer can still commit.
        log.warn("Pricing step failed", ex);
    }

    ordersRepository.markDone(orderId);
    // When outer ends, it may receive UnexpectedRollbackException.
}
~~~

Because the `REQUIRED` handler joins **the same physical transaction** while having its own logical transaction scope, the handler's transaction interceptor can mark the physical transaction **rollback-only** when the exception escapes the method. The caller catching the exception afterward **does not clear rollback-only**. When the outer transaction tries to commit, Spring typically throws `UnexpectedRollbackException` to report that a rollback occurred unexpectedly from the caller's perspective.

**The right fix depends on business semantics:**

- If the failure invalidates the whole order: let the exception propagate and roll back everything.
- If the failing step is truly **independent**: consider `REQUIRES_NEW`, while accepting separate commit/rollback and designing idempotency.
- If only the JDBC portion of a sub-step needs rollback: consider `NESTED` and savepoints where supported.
- If the error is a valid business outcome: design the handler to return an explicit result rather than throwing exceptions that trigger unwanted rollback rules.

Never "fix" this by catching and ignoring all errors in an error channel: doing so can cause a poller/listener to **ACK the message** while business logic failed.

### Checked Exceptions and setRollbackOnly

By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions do not trigger rollback by default. When business rules require it, declare:

~~~java
@Transactional(
        propagation = Propagation.REQUIRED,
        rollbackFor = Exception.class)
public void handle(OrderCommand command) throws Exception {
    // ...
}
~~~

`TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` can mark a transaction for rollback, but must be used deliberately: callers may receive `UnexpectedRollbackException` when believing every method returned normally. Explicit exception policies are usually easier to read and test.

## 10. When Propagation Meets Polling Endpoints and Listeners

A Service Activator's transaction must be examined alongside **the transaction started at the consumer**.

### Poller Opens a Transaction Before Calling the Handler

~~~java
@Bean
IntegrationFlow pollingFlow(
        PlatformTransactionManager transactionManager,
        ReservationWriter writer) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "write")
            .get();
}
~~~

Assume a `PollableChannel` named `workQueue` and a `ReserveCommand` payload:

1. The poller has transaction advice, opening TX-P for the poll/dispatch task per configuration.
2. The `@Transactional(REQUIRED)` handler runs synchronously, usually joining TX-P.
3. If the handler throws an exception causing TX-P to roll back, JDBC operations participating in TX-P are rolled back.
4. If the handler uses `REQUIRES_NEW`, it suspends TX-P and opens its own TX-H; TX-H can commit before TX-P ends.

**The message source remains a separate concern.** If `workQueue` is an in-memory `QueueChannel`, JDBC rollback **does not put the dequeued message back into the queue**. With a persistent message store or broker, redelivery depends on actual receive/ACK/transaction mechanics.

### Message-Driven Listeners

~~~text
JMS / RabbitMQ / Kafka inbound
  -> inbound adapter / listener container
  -> DirectChannel
  -> Service Activator @Transactional(REQUIRED)
  -> DB business operation
  -> return / exception
  -> source ACK / offset / redelivery per adapter
~~~

If the listener has not opened a JDBC transaction beforehand, `REQUIRED` on the handler **opens a new JDBC transaction**; it does not implicitly join JMS/Kafka/RabbitMQ transactions. When the DB commits before the source ACKs, the message can be redelivered; an **idempotent consumer** is needed.

If the listener is configured with a matching JDBC transaction and dispatches synchronously, the `REQUIRED` handler can join it. Still, **broker transactions** and **DB transactions** are separate scopes unless infrastructure genuinely supports a configured coordination mechanism. Never assume JDBC propagation replaces ACK/redelivery.

## 11. Async Boundary: When the Caller's Transaction Is Gone

Keep the same application service, but change the input channel to:

~~~java
@Bean("reserveInput")
MessageChannel reserveInput(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
~~~

With a typical asynchronous executor:

~~~mermaid
flowchart LR
    subgraph Outer["Thread A — physical TX-A"]
      A["Outer @Transactional"] --> B["Gateway sends"]
      B --> C["ExecutorChannel"]
      C --> D["Outer may commit/rollback"]
    end
    C -. "dispatched on another thread" .-> E["Worker receives message"]
    subgraph Worker["Thread B — transaction opened by handler"]
      E --> F["Service Activator REQUIRED"]
      F --> G["Separate TX-B + JDBC"]
    end
~~~

When the worker has no prior transaction, `REQUIRED` **opens a new transaction**. `REQUIRES_NEW` also opens a new transaction. This means:

- Outer rollback **does not automatically roll back** data committed by the worker.
- Worker failure **does not automatically roll back the outer transaction** if outer already returned/committed.
- `MANDATORY` can fail in the worker because no transaction is active.
- The outer transaction's `afterCommit` callback does not wait for the worker by default.
- With broker inputs, the listener may complete ACK right after handing off to the executor; if the worker fails later, the original source may not redeliver.

Some `TaskExecutor` implementations can run inline; check the actual configuration. Never use `ExecutorChannel` as a way to pass transactions or make messages durable. When recoverable background processing is needed, use a **durable queue/inbox**, consumer transactions, and idempotency.

## 12. Propagation with Router, Filter, Splitter, Aggregator, and Gateway

Consider an order flow:

~~~mermaid
flowchart LR
    A["Gateway"] --> B["Transformer"]
    B --> C{"Router"}
    C --> D["Filter: validate"]
    C --> E["Splitter: per item"]
    D --> F["Service Activator REQUIRED"]
    E --> G["ExecutorChannel"]
    G --> H["Worker REQUIRES_NEW / REQUIRED"]
    F --> I["Aggregator"]
    H --> I
~~~

Analysis by pattern:

| Pattern | Impact on propagation |
| --- | --- |
| **Gateway** | A synchronous Gateway can invoke the flow on the caller's thread, so a Service Activator behind `DirectChannel` can join the caller's transaction. A Gateway does not create transactions across brokers. |
| **Filter** | Dropping a message can be a valid branch termination without throwing/rolling back. If filtering is an error requiring rollback, design an explicit error path. |
| **Transformer** | Synchronous execution can stay in the same transaction; exceptions can affect rollback if they reach the interceptor. |
| **Router** | Routes to `DirectChannel` can keep the thread; routes to `ExecutorChannel` or a broker usually establish a new boundary. |
| **Splitter** | Emits multiple child messages. If processed sequentially on the same thread, they can share a transaction; if parallel, each branch needs its own boundary. |
| **Aggregator** | Correlation/release strategies and message store determine when results emit; it cannot automatically roll back commits completed on other branches. |
| **Error channel** | An error flow consuming an exception can make the transaction/consumer see success; check whether handlers rethrow or return. |

### REQUIRES_NEW Across Branches Does Not Create “All-or-Nothing”

If a Splitter produces three child messages and each worker uses `REQUIRES_NEW`, three transactions can commit independently. When the third branch fails, the first two committed branches **do not automatically roll back**. If business rules require undoing committed effects, use **compensating actions/Saga**, persist per-step progress, and support retries—rather than relying on a JDBC transaction at the Gateway.

### Correlation and Idempotency

`correlationId` groups messages belonging to the same order; `sequenceNumber` orders child messages. However, the deduplication key is usually a business `eventId`/`commandId` defined to be **stable across retries and redeliveries**. With a `REQUIRES_NEW` Service Activator, a duplicate may commit on an earlier attempt and reappear when the outer flow retries; use unique constraints and proper idempotent logic.

## 13. Retry and Transaction Advice Ordering

In transactional flows, two configurations can look similar yet behave very differently:

~~~text
Model A — retry wrapping outside transaction:
  retry attempt #1
      -> begin TX-1
      -> Service Activator
      -> rollback TX-1
  backoff
  retry attempt #2
      -> begin TX-2
      -> Service Activator
      -> commit TX-2
~~~

~~~text
Model B — transaction wrapping outside retry:
  begin TX-A
      -> attempt #1: handler fails
      -> attempt #2: handler retries
  commit/rollback TX-A
~~~

If TX-A was marked `rollback-only` on the first attempt, the second attempt may succeed in code yet the outer transaction still rolls back. With JDBC and errors requiring retrying the entire unit of work, it is usually best to **open a fresh transaction per attempt**; configure the advice chain/caller boundary to achieve this genuinely.

With `REQUIRES_NEW`, each handler retry can create an independent physical transaction; when an attempt committed yet the caller timed out without knowing, the next attempt can create **duplicate** side effects. Use idempotency keys, unique constraints, or durable state to prevent duplication.

With `NESTED`, rolling back to a savepoint lets the outer flow keep processing a secondary branch; however, if an outbound broker/API already received an event during the first attempt, a savepoint rollback cannot retract that event.

### Error Channel and Rollback Rules

Suppose an async endpoint converts exceptions into `ErrorMessage`s sent to an error channel. If the error handler merely logs and returns, the transaction interceptor may see a normally completed invocation and commit per configuration. If you want broker redelivery or database rollback, errors must propagate to the point deciding transaction/ACK outcomes. Never assume an error log entry equals a rollback.

## 14. Transaction Synchronization by Propagation Mode

A handler can register `TransactionSynchronization` to run post-commit actions. Yet **“after commit of which transaction?”** is the core question:

| Handler | Post-commit callback attaches to |
| --- | --- |
| `REQUIRED` joining TX-A | **Caller's TX-A**; callback does not run yet when handler returns. |
| `REQUIRES_NEW` opening TX-B | **Independent TX-B**; callback can run before TX-A commits/rolls back. |
| `NESTED` joining TX-A via savepoint | **Physical transaction TX-A**; no separate commit when inner returns. |
| `SUPPORTS` without actual transaction | May have no physical commit to synchronize with; verify before registering hooks. |
| `NOT_SUPPORTED` / `NEVER` | Runs without an actual transaction; do not expect callbacks after caller's DB commit. |

Hook registration check logic:

~~~java
if (!TransactionSynchronizationManager.isActualTransactionActive()
        || !TransactionSynchronizationManager.isSynchronizationActive()) {
    throw new IllegalStateException("Transaction required");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Runs after COMMIT of the physical transaction
                // that this synchronization participates in.
            }
        });
~~~

**Especially dangerous:** a callback publishing `OrderCreated` registered inside `REQUIRES_NEW` can emit the event when TX-B commits, even though outer TX-A containing the order **has not committed** and eventually rolls back. If the event represents outer success, write to a **transactional outbox** within TX-A and publish only after TX-A commits.

Sending inside `afterCommit` can still fail or be skipped if the process crashes right after commit. Callbacks coordinate timing; outboxes durably store **send intent**. Event consumers need idempotency when relays publish duplicates.

## 15. Testing REQUIRED and REQUIRES_NEW Against a Real Database

With the schema and beans from section 5, integration tests should inspect state **after the application service returns**:

~~~java
@SpringBootTest
class ServiceActivatorPropagationIT {
    @Autowired ReservationApplicationService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void outerRollbackAlsoRollsBackRequiredButKeepsRequiresNew() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> service.reserveThenFail(orderId));

        assertEquals(0, countByOrderId("orders", orderId));
        assertEquals(0, countByOrderId("reserved_inventory", orderId));
        assertEquals(1, countByOrderId("audit_log", orderId));
    }

    @Test
    void successfulOuterTransactionCommitsAll() {
        String orderId = UUID.randomUUID().toString();

        service.reserveNormally(orderId);

        assertEquals(1, countByOrderId("orders", orderId));
        assertEquals(1, countByOrderId("reserved_inventory", orderId));
        assertEquals(1, countByOrderId("audit_log", orderId));
    }

    private int countByOrderId(String table, String orderId) {
        String sql = switch (table) {
            case "orders" ->
                    "SELECT COUNT(*) FROM orders WHERE order_id = ?";
            case "reserved_inventory" ->
                    "SELECT COUNT(*) FROM reserved_inventory WHERE order_id = ?";
            case "audit_log" ->
                    "SELECT COUNT(*) FROM audit_log WHERE order_id = ?";
            default -> throw new IllegalArgumentException(table);
        };
        return jdbc.queryForObject(sql, Integer.class, orderId);
    }
}
~~~

**How to read the result:** if `audit_log` still contains a row after outer rollback, that proves `REQUIRES_NEW`'s TX-B committed independently in the test environment. If all three tables roll back, check whether the handler actually ran through a transaction proxy, whether data had unintended constraints, or whether beans/flows were configured differently.

For trustworthy conclusions:

- Never put `@Transactional` on **the test itself** if it masks the commit/rollback behavior of the service under test.
- Use unique IDs per test and isolate/clean up data.
- Use a database, datasource, transaction manager, and connection pool matching the target configuration.
- Record actual exceptions if results differ from expectations; do not merely assert how many times a handler was called.
- Never use external APIs or brokers as proof of JDBC atomicity; test delivery/ACK separately.

### Additional Tests for NESTED and Rollback-Only

For `NESTED`, a useful test inserts an order in outer, inserts a row after savepoint in inner and throws, then catches in outer and commits. Expected result on a savepoint-capable manager: outer row **exists**, inner row **does not**. Also run an outer-rollback case to verify every row in TX-A rolls back.

For `REQUIRED`, deliberately throw `RuntimeException` from inner while the caller catches and returns. When the inner interceptor marks global rollback-only, outer commit can throw `UnexpectedRollbackException`, confirming no partial commit occurred. This test protects against the bug “I caught the exception so it must commit”.

## 16. Failure Injection Matrix for Service Activators

| Scenario | Outcome to verify | Takeaway |
| --- | --- | --- |
| Outer rolls back after `REQUIRED` handler writes DB | Outer and handler data roll back together. | Two logical scopes can share one physical transaction. |
| Outer rolls back after `REQUIRES_NEW` handler commits | Inner row persists. | Inner commits independently; not undone by outer. |
| `REQUIRES_NEW` handler throws and caller does not catch | Inner rolls back; outer may also roll back as exception propagates. | Independent transaction does not mean independent error handling. |
| `NESTED` fails, outer catches and continues | Inner rolls back to savepoint; outer commits if resource supports it. | Savepoints differ from new physical transactions. |
| `MANDATORY` invoked from a worker with no transaction | Exception thrown at handler boundary. | Caller transaction does not travel across `ExecutorChannel`. |
| `REQUIRED` handler throws, outer catches | `UnexpectedRollbackException` may occur when outer tries to commit. | Catching exceptions does not clear rollback-only. |
| Poller uses in-memory `QueueChannel` and handler rolls back | DB rolls back, yet message may be lost from queue. | Propagation does not replace a source transaction. |
| Outer rolls back after inner published external event | External event may still exist. | JDBC transactions do not roll back brokers/APIs. |
| Broker redelivers after inner commit | Duplicate key or duplicate side effects if not idempotent. | `REQUIRES_NEW` requires deduplication and retry policies. |
| Splitter creates multiple async branches, one fails | Committed branches keep data; aggregator may miss results. | Durable state, timeouts, and compensation are required. |

Observe logs/traces with `messageId`, `correlationId`, `orderId`, `eventId`, thread, channel, propagation, commit/rollback points, retry count, and ACK status where possible. Never log sensitive payloads. For concurrency bugs, monitor connection pools, lock waits, deadlocks, and long-lived open transactions.

## 17. Design Choices for Real-World Requirements

| Problem | Suitable design | Risks to watch |
| --- | --- | --- |
| Single use case writing multiple tables in one DB, wanting all-or-nothing | `@Transactional` at application service + `DirectChannel` + `REQUIRED` Service Activator. | Same datasource/manager, exception propagation, active proxy. |
| Handler must always run inside an orchestration-layer transaction | `MANDATORY` on synchronous handler. | Fails if called from non-transactional sources or through executors. |
| Record attempt/audit independently of main business outcome | `REQUIRES_NEW`, with clear audit semantics and idempotency. | Can commit audit before outer finishes; connection pool pressure and orphan rows. |
| Optional sub-step can fail while outer still commits | `NESTED` if JDBC savepoints are supported; or decouple via another mechanism. | `NESTED` has no independent commit and does not roll back remote side effects. |
| Broker consumer writing to DB | Consumer/handler transaction + idempotency + adapter-appropriate ACK/redelivery. | DB commit before ACK can trigger redelivery. |
| Multi-branch / worker background processing | Durable messaging + per-worker transaction + correlation. | Partial commits, duplicates, timeouts, Saga/compensation. |
| Emit event only after business DB commits without losing it | Write outbox in business transaction then relay publishes. | Relay can publish duplicates; downstream must be idempotent. |

**Rule for choosing propagation:** start with `REQUIRED` when all operations **genuinely belong to one business unit of work**. Use `REQUIRES_NEW` or `NESTED` only with a concrete reason and a documented outcome for outer rollbacks. Propagation only solves local transaction boundaries, whereas end-to-end reliability depends on message sources, ACKs, retries, and idempotency.

## 18. Hands-On Exercises

**Exercise 1 — Draw real boundaries.** Use `Gateway → DirectChannel → Service Activator REQUIRED → Service Activator REQUIRES_NEW` under an outer `@Transactional`. Diagram TX-A, TX-B, suspend/resume points, and remaining rows when outer throws an exception.

**Exercise 2 — Test MANDATORY.** Switch the DB-writing handler to `Propagation.MANDATORY`. Invoke it from a transactional application service and from a non-transactional message-driven endpoint. Explain both outcomes; then test switching the channel to `ExecutorChannel`.

**Exercise 3 — NESTED with savepoints.** Create a `NESTED` handler writing to an auxiliary table and intentionally throwing an error. Have outer catch and commit. Check both tables, then switch propagation to `REQUIRED` to observe the rollback-only difference. State the exact transaction manager/database used.

**Exercise 4 — What does an audit mean?** Use `REQUIRES_NEW` to store `OrderAttempted` before outer commits. Explain why that event should not be named `OrderCreated`; redesign using an outbox if only committed orders should emit events.

**Exercise 5 — Redelivery and idempotency.** Simulate a broker redelivering the same `ReserveCommand(eventId)` after an independent handler committed. Use a unique constraint and stable idempotency key so inventory is never deducted twice.

**Exercise 6 — Multi-branch flow.** A Splitter produces three messages sent across three `ExecutorChannel`s; each worker has `@Transactional(REQUIRED)`. When one worker rolls back, determine the state of the remaining two workers, how the Aggregator handles timeouts, and when compensation is needed.

### Self-Assessment Questions

**1. Does a `REQUIRED` Service Activator create a new transaction when the caller already has one?** No. It joins the current transaction if compatible; it only opens a new one when none exists.

**2. Does an outer rollback delete rows committed by a `REQUIRES_NEW` handler?** No. The inner commit belongs to an independent physical transaction.

**3. Is `NESTED` the same as `REQUIRES_NEW`?** No. `NESTED` typically uses a savepoint within the outer transaction; an outer rollback still rolls back nested changes.

**4. Why can `MANDATORY` fail after adding an `ExecutorChannel`?** Because the worker does not automatically inherit the transaction context from the caller's thread.

**5. Does catching an exception from a `REQUIRED` handler guarantee the outer transaction will commit?** No. The inner interceptor may already have marked the transaction rollback-only, resulting in rollback/`UnexpectedRollbackException` at outer commit.

**6. When do you need an outbox instead of `REQUIRES_NEW` to emit events?** When the event must reflect **committed** business data and be recoverable/replayable after crashes; an independent handler transaction does not provide that guarantee.

## 19. Pre-Production Checklist

- [ ] Verify the Service Activator is invoked through a real Spring bean/proxy and transaction advice is active.
- [ ] Diagram outer transactions, inner logical scopes, physical transactions, and commit/rollback points.
- [ ] Choose propagation per handler based on business requirements, not pattern names.
- [ ] Use `REQUIRED` when sharing a transaction; `MANDATORY` when the caller must own the transaction.
- [ ] For `REQUIRES_NEW`, document outer-rollback outcomes, connection pool sizing, and duplicate risks.
- [ ] For `NESTED`, verify savepoints are supported by the transaction manager and database.
- [ ] Check error propagation, rollback rules, rollback-only, and `UnexpectedRollbackException`.
- [ ] Prevent `this.method()` self-calls or unexposed JDK proxy methods from bypassing transaction interceptors.
- [ ] Identify channels with thread handoffs; never assume `ExecutorChannel` transfers transaction context.
- [ ] For pollers/listeners, verify source transactions, ACK/offset/redelivery, and message store durability.
- [ ] Check retry advice vs. transaction advice ordering; ensure each attempt gets an appropriate transaction.
- [ ] Use stable business event IDs, unique constraints, and idempotent consumers on redelivery.
- [ ] For Router/Splitter/Aggregator, track correlation, partial commits, timeouts, and compensation.
- [ ] Emit critical events via transactional outbox; test crashes between DB commit and broker publish.
- [ ] Test outer rollback, inner commit, nested savepoints, caught exceptions, and async branches.

**Takeaway:** **Transaction propagation determines how a Service Activator joins or creates a transaction at invocation time.** `DirectChannel` usually preserves the thread so `REQUIRED` joins the caller's transaction; `REQUIRES_NEW` commits independently; `NESTED` uses savepoints if supported; executors and brokers create new boundaries. Combine propagation with error handling, retries, idempotency, and ACK/redelivery so Spring Integration flows behave correctly on both success and failure.
