# Commit When Both Handler and Downstream Succeed

In Spring Integration, a message can travel from an inbound adapter through a channel, consumer endpoint, and handler, and then continue to a transformer, router, service activator, outbound gateway, or other consumers. Many systems want a clear guarantee: **only commit data when both the current handler and all downstream steps belonging to the same unit of work succeed**.

This requirement is not automatically satisfied just because a method is annotated with <code>@Transactional</code>. A Spring transaction is bound to the **thread and invocation scope** that opened the transaction. A downstream step running after the method returns, or running on another executor/poller, can fail **after** the handler's transaction has already committed.

This lesson belongs to the **Transaction runtime** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will identify transaction boundaries when Spring Integration coordinates message flows across channels, endpoints, consumers, pollers, and executors; then we will practice configuring them, verifying rollback/commit, handling retries, error channels, message stores, and correlation.

> **Principle:** "Only commit after downstream succeeds" is only meaningful when **the transaction spans the downstream segment that needs protection**, exceptions still propagate back to the transaction interceptor, and the resources requiring rollback actually participate in that transaction. A single transaction does not turn all APIs, brokers, and external systems into an atomic operation.

## 1. "Handler succeeded" does not mean "Flow succeeded"

Consider an order placement flow:

~~~text
order.input
    → OrderService.save()
    → order.saved (DirectChannel)
    → AuditService.record()
    → reply
~~~

We want both the <code>orders</code> and <code>order_audit</code> records to succeed together or roll back together. There are at least three points to separate:

- **Handler succeeded:** <code>OrderService.save()</code> has returned, but audit may not have been invoked yet.
- **Downstream succeeded:** <code>AuditService.record()</code> completed normally, yet that alone does not prove the transaction committed successfully.
- **Commit succeeded:** the transaction manager finished committing the participating transactional resources; unprotected external side effects may still exist.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant TX as Transaction boundary
    participant H as Order handler
    participant D as Downstream audit
    participant DB as Transactional DB
    C->>TX: start unit of work
    TX->>H: handle(order)
    H->>DB: INSERT orders
    H-->>TX: SavedOrder
    TX->>D: record audit
    D->>DB: INSERT order_audit
    D-->>TX: AuditReceipt
    TX->>DB: COMMIT
    TX-->>C: success
    Note over TX,DB: Commit only occurs after both steps return successfully
~~~

The diagram illustrates a transaction initiated **outside both steps**, with all processing calls occurring synchronously on the same thread. If audit throws an exception before commit, the transaction interceptor can roll back both database operations.

## 2. Rules for transaction boundaries in message flows

Spring Integration merely routes messages between components; it **does not automatically open a single wide transaction for the entire graph**. The transaction manager and the point where the transaction starts determine the actual scope.

| Factor | Impact on commit |
|---|---|
| <code>DirectChannel</code> | Consumer typically runs on the sender's thread; the current transaction can continue across the synchronous chain |
| <code>PublishSubscribeChannel</code> **without executor** | Subscribers are invoked synchronously; error propagation and handling still need to be checked |
| <code>ExecutorChannel</code> or <code>PublishSubscribeChannel</code> with executor | Processing after handoff runs on another thread; the sender's thread-bound transaction is not transferred automatically |
| <code>QueueChannel</code> and polling consumer | Creates a boundary for later receive/processing; the sender's transaction does not automatically wrap the poller's consumer |
| <code>@Transactional</code> on handler | Usually wraps only the handler method call; downstream dispatched after the method returns may lie outside the scope |
| <code>@Transactional</code> on caller/gateway facade | Can wrap the entire **synchronous** request–reply flow, when all downstream calls finish before the facade returns |
| Poller transaction advice | Can open a transaction wrapping a receive-and-handle cycle and synchronous downstream steps |
| <code>REQUIRES_NEW</code>, a different transaction manager | Can create an independent commit even when an outer transaction exists |

<code>DirectChannel</code> **does not initiate transactions on its own**. It simply keeps invocations on the same thread, allowing an existing transaction to continue. Conversely, <code>ExecutorChannel</code> can report a successful send as soon as the task is accepted, even though the downstream handler has not run yet or will fail later.

### Two ways to place <code>@Transactional</code>, two different outcomes

**Error-prone approach:**

~~~java
@Service
public class OrderService {
    @Transactional
    public SavedOrder save(OrderCommand command) {
        // INSERT orders
        return new SavedOrder(command.orderId(), command.quantity());
    }
}

// Flow: .handle(orderService, "save").handle(auditService, "record")
~~~

<code>save()</code>'s transaction may **commit when the method finishes**, before Spring Integration dispatches the output to <code>auditService.record()</code>. If audit fails, the already-committed order record does not automatically roll back due to that error.

**Approach aligned with this lesson's goal:** place the transaction at an entry point outside the entire synchronous message flow invocation, such as a facade calling a messaging gateway. Or, for a polling consumer, configure transaction advice on the poller to wrap receive and synchronous downstream processing. Both approaches are illustrated in the following sections.

## 3. Complete example: transaction wrapping Gateway → Handler → Downstream

The example uses Spring Integration Java DSL, Java 17+, and a JDBC database. Saving the order and recording the audit must be in the same transaction. All components are assumed to reside in a Spring context with Spring JDBC, Spring Transaction, Spring Integration, and a transaction manager managing the same <code>DataSource</code>.

**Step 1 — define data types:**

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record SavedOrder(String orderId, int quantity) {}
public record AuditReceipt(String orderId, String status) {}
~~~

Minimal schema:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);

CREATE TABLE order_audit (
    order_id VARCHAR(64) PRIMARY KEY,
    event VARCHAR(40) NOT NULL
);
~~~

Unique key constraints help prevent duplicate writes when upstream retries/redelivers. A full idempotency mechanism needs to define how to return a result on duplicate-key requests.

**Step 2 — two services sharing the same data source:**

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public SavedOrder save(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than 0");
        }
        jdbc.update("INSERT INTO orders(order_id, quantity) VALUES (?, ?)",
            command.orderId(), command.quantity());
        return new SavedOrder(command.orderId(), command.quantity());
    }
}

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public AuditReceipt record(SavedOrder order) {
        // Create an intentional failure to test rollback.
        if (order.orderId().equals("FAIL-AUDIT")) {
            throw new IllegalStateException("Audit failed");
        }
        jdbc.update(
            "INSERT INTO order_audit(order_id, event) VALUES (?, ?)",
            order.orderId(), "SAVED");
        return new AuditReceipt(order.orderId(), "RECORDED");
    }
}
~~~

Here the two services do not need to manage transactions themselves. The JDBC operations will join the transaction bound by Spring to the thread when the outer facade opens a transaction.

**Step 3 — configure synchronous channels and IntegrationFlow:**

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderFlowConfig {

    @Bean(name = "orders.input")
    MessageChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.saved")
    MessageChannel savedChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService orders, AuditService audit) {
        return IntegrationFlow.from("orders.input")
            .handle(orders, "save")
            .channel("orders.saved")
            .handle(audit, "record")
            .get();
    }
}
~~~

Key imports: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.annotation.IntegrationComponentScan</code>, and <code>org.springframework.messaging.MessageChannel</code>. Both handlers are dispatched synchronously on the thread entering <code>orders.input</code>; <code>orders.saved</code> is also a <code>DirectChannel</code>.

**Step 4 — messaging gateway and facade opening the transaction outside the flow:**

~~~java
@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrderGateway {
    AuditReceipt submit(OrderCommand command);
}

@Service
public class CheckoutFacade {
    private final OrderGateway gateway;

    public CheckoutFacade(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public AuditReceipt submit(OrderCommand command) {
        return gateway.submit(command);
    }
}
~~~

<code>@MessagingGateway</code> belongs to <code>org.springframework.integration.annotation</code>, and <code>@Transactional</code> belongs to <code>org.springframework.transaction.annotation</code>. The application must invoke <code>CheckoutFacade.submit(...)</code> **through the Spring proxy**; an internal call <code>this.submit(...)</code> inside the same bean does not trigger the transaction interceptor in standard proxy mode.

When invoked:

~~~java
AuditReceipt receipt =
    checkoutFacade.submit(new OrderCommand("O-204", 2));
// After submit() completes and commits successfully,
// both orders and order_audit have corresponding records.
~~~

Expected sequence:

1. The Spring transaction interceptor opens a transaction before <code>CheckoutFacade.submit()</code> runs.
2. The facade calls the gateway; the gateway sends the message via <code>orders.input</code> (synchronously).
3. <code>OrderService.save()</code> inserts into <code>orders</code> and returns <code>SavedOrder</code>.
4. Spring Integration sends the payload through <code>orders.saved</code>; <code>AuditService.record()</code> inserts into <code>order_audit</code>.
5. The <code>AuditReceipt</code> reply returns to the gateway, and then the facade returns.
6. Only then does the facade's transaction interceptor perform the commit.

With <code>new OrderCommand("FAIL-AUDIT", 2)</code>, audit throws <code>IllegalStateException</code> (a runtime exception). The exception propagates back through the <code>DirectChannel</code>s to the facade's transaction interceptor, so **the INSERT into <code>orders</code> is also rolled back**. This assumes the right transaction manager, no advice swallowing exceptions, and no <code>REQUIRES_NEW</code> step or second data source committing independently.

### Important limitation of the example

The transaction only covers operations participating in the same transaction manager. If <code>AuditService</code> also sends an email or calls an HTTP API, a database rollback **does not retract** the sent email or the completed HTTP request. If audit writes to a different database using an independent transaction manager, the "both commit together" guarantee is also no longer automatically true.

## 4. Commit and rollback diagrams

### Case A — both handler and downstream succeed

~~~mermaid
flowchart LR
    A["BEGIN TX"] --> B["Handler: write orders"]
    B --> C["DirectChannel"]
    C --> D["Downstream: write audit"]
    D --> E["Return reply"]
    E --> F["COMMIT DB"]
    F --> G["Caller receives result"]
~~~

### Case B — downstream throws an exception

~~~mermaid
flowchart LR
    A["BEGIN TX"] --> B["Handler: write orders"]
    B --> C["DirectChannel"]
    C --> D["Downstream: audit error"]
    D -. "exception propagates back" .-> E["Transaction interceptor"]
    E --> F["ROLLBACK DB"]
    F --> G["Caller receives exception"]
~~~

In both diagrams, commit/rollback occurs **after the synchronous segment within the transaction finishes**. If the handler opens its own transaction and commits before the output message is dispatched, the second diagram will no longer hold.

## 5. With a poller: the transaction must wrap receive and processing

Not every flow starts from a synchronous gateway. A polling consumer can pull messages from a <code>QueueChannel</code>, JDBC-backed message store, JMS, or another polling source. A poller can have transaction advice attached to open a transaction before <code>receive()</code> and complete only after the synchronous processing chain finishes.

XML example configuring a poller using Spring Integration's mechanism:

~~~xml
<int:service-activator input-channel="orders.queue"
                       ref="orderProcessor"
                       method="process">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

<code>orderProcessor.process(...)</code> can forward further through one or more <code>DirectChannel</code>s. When the poller transaction wraps the receive-and-process cycle, synchronous downstream steps can stay in the same transaction until the poll task ends. The XML configuration above illustrates the **polling endpoint's transaction**; appropriate beans for <code>orders.queue</code>, <code>orderProcessor</code>, and <code>transactionManager</code> must be added for the application.

However, the rollback result of the **receive operation** depends on the source type:

| Message source/channel | What can rollback do? |
|---|---|
| <code>JdbcChannelMessageStore</code> via transactional queue/channel, using the same transaction manager | Pulling/deleting the message can roll back together with DB changes per actual configuration |
| JDBC polling adapter using the same database transaction | Can roll back read/status-marking work when source and operations participate in the same transaction |
| JMS channel or inbound adapter | Redelivery/ACK depends on session, transaction mode, and container/broker configuration |
| Standard in-memory <code>QueueChannel</code> | Does not automatically become a durable or transactional queue just because the poller has <code>@Transactional</code> |
| File/FTP or external API | No real database rollback for operations on files/external servers; requires transaction synchronization or separate compensation |

**Common mistake:** seeing JDBC records roll back and assuming the message definitely returns to the queue. You must check the message source's own transaction, how the message is removed/acked, and replay behavior after a crash.

### Transaction synchronization for heterogeneous sources

Spring Integration supports <code>TransactionSynchronizationFactory</code> with callbacks such as <code>beforeCommit</code>, <code>afterCommit</code>, and <code>afterRollback</code>. For example, after processing a file successfully and committing the database, you can move the file to a "processed" directory in <code>afterCommit</code>; on rollback, move it to a "failed" directory where appropriate.

What matters is:

- <code>beforeCommit</code> runs before commit; an error detected and thrown at this stage can cause the transaction to roll back.
- <code>afterCommit</code> runs when the transaction has **already committed**; a subsequent failure cannot roll back the completed transaction.
- <code>afterRollback</code> helps trigger post-rollback handling actions; the callback does not turn an external source into a transactional resource.

If the strict requirement is "downstream must finish before committing," a downstream task running **in <code>afterCommit</code>** does not satisfy that condition. It is a **post-commit task**, suitable for notifications or independently retryable work, not a mandatory part of an atomic commit.

## 6. Crossing an asynchronous boundary: handoff success can lead to premature commit

Suppose the flow changes <code>orders.saved</code> from a <code>DirectChannel</code> to an <code>ExecutorChannel</code>:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as Transaction (thread A)
    participant H as Handler (thread A)
    participant X as ExecutorChannel
    participant D as Downstream (thread B)
    C->>T: begin
    T->>H: save()
    H-->>T: saved
    T->>X: send message
    X-->>T: task accepted
    T->>T: COMMIT DB on thread A
    X->>D: process on thread B
    D--xX: exception
    Note over T,D: Exception on thread B cannot roll back commit on thread A
~~~

The diagram depicts a trigger source that does not wait for the downstream result and succeeds at handing off the task. With a **request–reply gateway**, the caller can also wait for a reply and time out if downstream is slow; waiting for a reply **does not transfer the caller's transaction to the worker thread**. Depending on timeouts, wrappers/exceptions, the caller's transaction may commit or roll back, yet it **does not create cross-thread atomicity**.

| Boundary | Why doesn't commit wait for all downstream work? | Design approaches to consider |
|---|---|---|
| <code>ExecutorChannel</code> | Shifts processing to another thread | Open a new transaction on the consumer; use outbox/inbox or durable messages for multi-step workflows |
| <code>QueueChannel</code> + poller | Message sits in the queue and is processed in another cycle | Separate transaction for the poller; queue with a transactional message store if needed |
| Broker (Kafka/JMS/AMQP) | Publish/ACK and consumer processing have their own protocols and commit timing | Follow each adapter's transaction support; idempotency, outbox, DLQ, redelivery |
| <code>@Async</code> or manually created thread | Does not automatically propagate thread-bound transactions | Explicit async contract, separate transaction on the worker |
| Reactor/reactive flow | Context and transaction semantics differ from thread-bound imperative transactions | Use appropriate reactive transaction support; do not rely on same-thread assumptions |

**Do not keep a database transaction open waiting for a chain of long-running asynchronous tasks.** A better design usually consists of a short transaction to save business state along with an outbox, after which workers process subsequent steps with controlled retries and idempotency.

## 7. Downstream fails yet the flow still commits: common causes

| Symptom | Why might it commit? | Check/fix |
|---|---|---|
| Handler writes DB then audit fails, order still exists | <code>@Transactional</code> only wraps the handler method | Move the transaction up to the caller or poller if the flow is synchronous |
| Audit fails yet caller receives success | Advice/handler catches the exception and only logs or returns a fallback value | Only recover under an explicit contract; if rollback is required, let the exception propagate |
| Handler finishes, async downstream fails later | Transaction already completed at thread handoff | Use a multi-transaction workflow, outbox, and compensating actions when needed |
| Exception is a checked exception | Default <code>@Transactional</code> usually rolls back on <code>RuntimeException</code>/<code>Error</code>, not automatically on every checked exception | Use <code>rollbackFor</code> when the contract requires it, or translate the exception appropriately |
| Downstream uses <code>REQUIRES_NEW</code> | Independent transaction can commit separately | Review propagation; identify which resources must be atomic |
| Two operations go through different transaction managers | Only one resource is managed by the transaction | Design clear boundaries; avoid assuming distributed atomicity |
| <code>ErrorMessage</code> is published successfully | Error flow only observes/publishes the error after an exception occurs | Distinguish notification from rollback; verify whether the error still propagates to the transaction owner |
| Audit sent HTTP yet JDBC rolled back | HTTP does not automatically participate in a JDBC transaction | Use outbox, receiver-side idempotency, or saga/business compensation |

An easily missed scenario: the handler throws an exception after writing to the DB, yet retry advice retries and **swallows the final exception**. The outer layer only sees the call complete, so it may commit. Recovery must be explicitly designed around "success," "failure requiring rollback," and "routed to a retry queue."

## 8. Retry combined with transactions: which attempt commits?

Retry and transaction can be ordered in two ways:

**A. Retry wrapping a separate transaction for each attempt**

~~~text
Retry
  ├─ attempt #1: BEGIN → handler + downstream → error → ROLLBACK
  ├─ attempt #2: BEGIN → handler + downstream → error → ROLLBACK
  └─ attempt #3: BEGIN → handler + downstream → success → COMMIT
~~~

This is usually appropriate when retrying a *unit of work* and each attempt must start with fresh transaction state. The requirement is that transaction advice is genuinely invoked on each attempt, or the service uses appropriate propagation, and no outer transaction holds all attempts in a single transaction.

**B. Transaction wrapping multiple attempts**

~~~text
BEGIN TRANSACTION
  Retry
    attempt #1 → exception
    attempt #2 → exception
    attempt #3 → success
COMMIT? (may fail if the transaction is already rollback-only)
~~~

An earlier attempt can mark the transaction rollback-only. Even if the final handler attempt returns successfully, the outermost commit can still fail, for example with <code>UnexpectedRollbackException</code>. Therefore, you must determine whether retry occurs **inside or outside** the transaction interceptor and which errors mark rollback.

Retries can also produce duplicate side effects if an earlier attempt sent an email, processed a payment, or published an event before throwing an exception. Business idempotency keys, unique constraints, inbox/outbox, and attempt/backoff limits are necessary accompanying components.

## 9. Error channel and correlation do not decide commit

When an exception occurs in a synchronous consumer, it can propagate back to the sender and transaction interceptor; in an asynchronous/poller consumer, it can be turned into an <code>ErrorMessage</code> on the corresponding error channel. However:

- <code>MessagePublishingErrorHandler</code> is responsible for publishing errors when used by the runtime; it **does not automatically roll back a transaction that has already finished**.
- The <code>errorChannel</code> header specifies where <code>ErrorMessage</code> is sent in appropriate error-handling paths; it is not a "rollback" command.
- <code>correlationId</code> helps link processing, retry, and error steps across threads; it does not represent a transaction ID and does not guarantee two steps share a transaction.
- <code>MessageHeaders.ID</code> is the identifier of a single message; when a message is recreated or redelivered, its ID can differ. Do not rely on this ID alone to prevent duplicate side effects.
- With a poller, the error handler usually runs at the boundary after the task throws an exception; verify whether the transaction rolled back and whether the message source will redeliver.

In production, log/trace at minimum <code>correlationId</code>, order ID or idempotency key, endpoint name, thread name, transaction status when needed for diagnostics, exception type, and retry count. Do not write entire sensitive payloads into logs.

## 10. Properly testing "commit only when everything succeeds"

Unit tests mocking services do not prove database rollback. For this goal, use **integration tests with a real database and transaction manager**, such as H2 or Testcontainers, running the Spring Integration flow and querying the data after the transaction completes.

| Scenario | DB expectation | Additional verification |
|---|---|---|
| Order + audit succeed | Both <code>orders</code> and <code>order_audit</code> exist | Gateway returns receipt after successful commit |
| Handler <code>save()</code> fails | No new records in either table | Audit is not invoked |
| Handler succeeds, audit throws runtime exception | **No** new records in either table | Exception propagates to facade, transaction rolls back |
| Audit throws checked exception (if permitted by app) | Follows configured rollback rules | Check <code>rollbackFor</code> if rollback is required |
| Audit catches exception and returns success | May commit | This test demonstrates the risk of swallowing errors |
| Flow has <code>ExecutorChannel</code> | Handler and worker transactions are separate | Do not expect one rollback to cover both |
| Poller + transactional message store | DB rollback and message state are consistent per config | Verify message redelivery after failure |
| Retry then succeed | No duplicate data | Unique keys, attempt count, transaction per attempt |

**Integration test outline** (assuming <code>JdbcTemplate jdbc</code>, <code>CheckoutFacade checkoutFacade</code> are available and test data is cleaned before each case):

~~~java
@Test
void commitOnlyWhenDownstreamSucceeds() {
    AuditReceipt result =
        checkoutFacade.submit(new OrderCommand("O-OK", 2));

    assertEquals("RECORDED", result.status());
    assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE order_id = ?",
        Integer.class, "O-OK"));
    assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM order_audit WHERE order_id = ?",
        Integer.class, "O-OK"));
}

@Test
void rollbackWhenDownstreamFails() {
    assertThrows(RuntimeException.class, () ->
        checkoutFacade.submit(new OrderCommand("FAIL-AUDIT", 2)));

    assertEquals(0, jdbc.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE order_id = ?",
        Integer.class, "FAIL-AUDIT"));
    assertEquals(0, jdbc.queryForObject(
        "SELECT COUNT(*) FROM order_audit WHERE order_id = ?",
        Integer.class, "FAIL-AUDIT"));
}
~~~

The assertions are from JUnit 5. **Do not place <code>@Transactional</code> on the test itself** if the goal is to verify the transaction committed/rolled back independently by the facade: an outer test transaction can distort observed results. The test must verify database state after <code>checkoutFacade.submit(...)</code> completes.

### Checking whether a transaction is active at each point

During diagnosis, you can temporarily add:

~~~java
boolean active = TransactionSynchronizationManager
    .isActualTransactionActive();
log.debug("component={}, thread={}, txActive={}",
    "audit", Thread.currentThread().getName(), active);
~~~

<code>TransactionSynchronizationManager</code> belongs to <code>org.springframework.transaction.support</code>. A result of <code>txActive=true</code> indicates the thread currently has a Spring-managed transaction, **not** that every resource is participating in that transaction. Combining thread ID logs, transaction manager, datasource, and rollback integration tests is required to establish the actual scope.

## 11. Pre-adoption checklist

1. Identify precisely which downstream steps **must** succeed before commit; separate post-commit tasks such as sending emails, notifications, or indexing.
2. Place the transaction at an entry point covering the **entire** synchronous segment that needs atomicity (gateway facade or poller transaction), without assuming placing it on one handler is enough.
3. Check channel types between steps: <code>DirectChannel</code> keeps the same thread; <code>QueueChannel</code>, executors, or async adapters create new boundaries.
4. Confirm data operations share the same transaction manager and configured resource/connection, and do not commit independently via <code>REQUIRES_NEW</code>.
5. Ensure downstream exceptions propagate to the transaction interceptor; explicitly specify checked exceptions, rollback-only, and advices with recovery.
6. For message sources, determine what rollback does to ACK, removal, visibility, message stores, and redelivery; test worker crashes or restarts.
7. Define retry and idempotency strategies, especially if downstream has side effects outside the database.
8. Test the success path, handler failure, downstream failure, async boundary, and failures immediately before/after commit.
9. Observe correlation, threads, endpoints, transaction lifecycle, retries, and queue depth, while limiting sensitive data in logs.

**Conclusion:** Commit should only be understood as the success of **a specific transaction**, not the success of every step across an entire distributed message flow. If handler and downstream run synchronously in the same transaction, a downstream exception can cause all transactional changes to roll back. When the flow shifts to pollers, executors, brokers, or external systems, you must design new commit boundaries along with message stores, retries, idempotency, or an outbox to achieve the desired business guarantee.

## References

- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration — Message Endpoints and poller transactions](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
