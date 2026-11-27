# Rollback When a Handler Throws an Exception in Spring Integration Runtime

## 1. The problem to solve

In **SPRING_INTEGRATION_RUNTIME**, a message passes through `MessageChannel`, consumer endpoints, and message handlers, and may call databases, brokers, HTTP, or other flows. When a handler throws an exception mid-way, the question is not only *whether an error occurred*, but also:

- Is there an **active transaction** at the moment the handler throws?
- **Who opened** that transaction: a `@Transactional` method, handler advice, poller, or inbound listener?
- Does the exception **escape to the transaction boundary**, and how do the rollback rules evaluate it?
- **Which resources participate** in the transaction, and can the source message be redelivered after rollback?
- Has the flow already crossed an `ExecutorChannel`, `QueueChannel`, or another thread boundary?
- Do retries, recovery callbacks, and error flows inadvertently turn the error into "handled successfully"?

The topic **Transaction runtime → Rollback when a handler throws an exception** is about understanding that exact decision chain and verifying it with a JDBC experiment.

Example: message `CreateOrder("O-42")` arrives at a service activator; the handler writes the order to the database, then throws `IllegalStateException`. If the database write runs inside a Spring transaction and the error escapes the boundary, the transaction can roll back the record. Without a transaction, the write may already have committed even though the handler reported an error. Even when JDBC rolls back, **the input message is not automatically resent** if the message source lacks an appropriate redelivery mechanism.

~~~mermaid
flowchart TD
    A["Message enters endpoint"] --> B{"Is a transaction wrapping\nresource operations?"}
    B -->|No| N["Handler writes DB / calls service"]
    N --> U["Exception: previously committed work\nis not automatically undone"]
    B -->|Yes| C["Handler executes inside transaction"]
    C --> D{"Does exception escape\nthe transaction boundary?"}
    D -->|No, caught/trapped| E["Boundary may commit\nunless marked rollback-only"]
    D -->|Yes| F{"Do rollback rules\nmatch the exception?"}
    F -->|Yes| R["Roll back participating resources"]
    F -->|No| K["Boundary may commit\neven though exception propagates out"]
    R --> X["Redelivery? depends on adapter,\nmessage store, and ack"]
~~~

**Core rule:** `throw` is only an error signal. Rollback requires a **real transaction**, a **boundary wrapping the right operations**, the **exception being observed by the transaction infrastructure**, **matching rollback rules**, and **participating transactional resources**.

## 2. Four layers to distinguish at runtime

| Layer | Typical components | Role | Common mistakes |
| --- | --- | --- | --- |
| **Message delivery** | `DirectChannel`, `QueueChannel`, `ExecutorChannel`, broker adapters | Delivers messages to consumers, decides threads and handoffs | Assuming every channel has a built-in transaction |
| **Transaction boundary** | `@Transactional`, `TransactionInterceptor`, poller transactional advice | Opens/joins/commits/rolls back a transaction | Assuming every handler `throw` automatically creates a transaction |
| **Transactional resources** | JDBC/JPA connection, JMS session, or transaction-capable message store | Executes commit/rollback of managed data | Assuming JDBC rollback also undoes HTTP calls |
| **Failure/recovery** | `errorChannel`, retry advice, recoverer, DLQ, broker ack/nack | Decides observation, retry, error storage, redelivery | Assuming receiving an `ErrorMessage` means the source rolled back |

A transaction is bound to a specific resource manager. For instance, `DataSourceTransactionManager` manages JDBC connections for one `DataSource`; it cannot undo an HTTP request that was already sent successfully. If JMS and JDBC must commit together as one unit, you may need a transaction manager suited to both resources' transaction model, or use outbox/inbox instead of assuming they synchronize automatically.

**Practical example:** a flow receives an order from a broker, inserts a row in the DB, and sends an HTTP call to create a shipment. If the DB and broker participate in an appropriate transaction, rollback can affect the DB and message receipt; the already-executed HTTP request normally **does not roll back**. To handle duplicates on redelivery, the HTTP endpoint needs an idempotency key or state reconciliation mechanism.

## 3. When does an exception make Spring roll back?

With standard **Spring declarative transactions**, the default rules are:

| Behavior at transaction boundary | Default outcome |
| --- | --- |
| Handler throws `RuntimeException` and it passes through interceptor | Transaction is marked for rollback |
| Handler throws `Error` and it passes through interceptor | Transaction is marked for rollback |
| Handler throws checked `Exception` (e.g., `IOException`) | By default **does not roll back**, unless a matching rule is configured |
| Handler catches error itself and returns normally | Interceptor may **commit** if transaction is not marked `rollback-only` |
| Handler returns `false`/`null` as a normal return value | Does not trigger rollback merely from the return value |
| Handler calls `setRollbackOnly()` | Transaction rolls back even if code returns normally afterward |
| Transaction was previously marked `rollback-only` by another scope | Outermost commit attempt may throw `UnexpectedRollbackException` |

You can explicitly define rules on a Spring service:

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void createOrder(OrderCommand command)
        throws BusinessCheckedException {
    repository.insert(command);
    if (hasPermanentIssue(command)) {
        throw new BusinessCheckedException("Business failure");
    }
}
~~~

This is an **illustrative snippet**; dependent types `BusinessCheckedException`, `OrderCommand`, `repository`, and `hasPermanentIssue` must be provided. `rollbackFor` uses **class types** rather than name patterns to avoid unintended matches. `noRollbackFor` can be used when an exception truly represents a business outcome that allows commit, though you must check whether a resource already marked rollback-only beforehand.

In Spring Framework 6.2+ it is also possible to configure a **global default rollback rule** (for example, rolling back on all exceptions). Thus the table above describes standard behavior when rollback policy has **not been customized**. When diagnosing an application, always check the actual configuration of the transaction interceptor and `@EnableTransactionManagement`.

### Spring Integration exception wrappers

A handler method may throw `IllegalStateException`, while the endpoint layer may wrap it in `MessageHandlingException` or another `MessagingException`. What matters is **the exception that actually passes through the transaction advice**. By default these wrappers are runtime exceptions so they still trigger rollback, but if you use `rollbackFor`/`noRollbackFor` by class, check the actual type, cause chain, and specific policy.

Do not turn every error into a checked exception while forgetting to update rules, nor swallow errors inside handlers just to reduce log volume.

## 4. Thread boundaries: what determines whether rollback propagates back

Standard Spring transactions rely on thread-bound context. With a synchronous `DirectChannel` chain, downstream handlers run on the sending thread, so they can share the same transaction if the transaction scope covers this segment.

~~~mermaid
flowchart LR
    A["Caller opens TX"] --> B["DirectChannel"]
    B --> C["@ServiceActivator A"]
    C --> D["DirectChannel"]
    D --> E["@ServiceActivator B throws"]
    E -->|Exception on same call stack| A
~~~

If A and B operate on a JDBC connection participating in the transaction opened by the caller and B throws an uncaught unchecked exception, the caller's boundary can roll back earlier changes as well.

Conversely, a handoff across an `ExecutorChannel` or pollable channel creates a new boundary:

~~~mermaid
flowchart LR
    A["Thread 1\nTX-A"] --> B["ExecutorChannel"]
    B --> C["Thread 2\nHandler throws error"]
    C --> D["Worker's error flow"]
    B --> E["Thread 1 handoff OK\nTX-A may commit"]
~~~

If message handoff succeeds, the sending thread's transaction may commit **before** the worker fails. Worker-side errors do not automatically go back to an already-ended transaction.

| Channel/consumer | Thread and failure propagation | Rollback impact |
| --- | --- | --- |
| `DirectChannel` | Handler usually runs on the `send()` thread | Synchronous exceptions can propagate back to the outermost transaction |
| `ExecutorChannel` | Dispatches to `TaskExecutor` | Old thread's transaction context does not transfer automatically; worker needs its own boundary |
| `QueueChannel` + poller | `send()` enqueues; consumer polls later | Enqueue transaction and poll transaction are separate; need to understand store and poller |
| Synchronous `PublishSubscribeChannel` | Multiple subscribers run on caller thread | Errors can affect caller's transaction depending on error handling and order |
| `PublishSubscribeChannel` with executor | Invokes subscribers asynchronously | Requires per-worker transactions and error flows |
| JMS/AMQP/Kafka inbound | Listener container has its own ack, redelivery, and transaction policy | Rollback or nack must follow the specific adapter/broker configuration |

**Thought experiment:** B writes to the DB and throws after receiving from an `ExecutorChannel`. Caller A wraps `send()` in `@Transactional`, yet `send()` returns as soon as handoff succeeds. A commits; B fails only afterward. To combine atomic handoff and processing, design durable channels, an outbox, or appropriate transactions on both sides rather than stretching a single thread's transaction across an executor.

## 5. Self-contained example: handler writes JDBC then throws exception

The example uses **Java 17+**, Spring Boot with Spring Integration, Spring JDBC, and in-memory H2. Dependencies require the Spring Integration starter, JDBC starter, and H2 runtime compatible with the Boot version. Place the code below in **one file** `RollbackDemoApplication.java` in package `demo.integration`; run the application with the package component-scanned.

Goal: send two messages, one succeeding and one failing **after INSERT**, then inspect which rows remain in the database.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableIntegration
public class RollbackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    @Bean("orderCommands")
    MessageChannel orderCommands() {
        return new DirectChannel();
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("orderCommands") MessageChannel input,
            JdbcTemplate jdbc) {

        return args -> {
            jdbc.execute("""
                CREATE TABLE IF NOT EXISTS demo_orders (
                    order_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL
                )
                """);

            sendAndReport(input, "O-SUCCESS", false);
            sendAndReport(input, "O-FAIL", true);

            Integer ok = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM demo_orders WHERE order_id = ?",
                    Integer.class, "O-SUCCESS");
            Integer failed = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM demo_orders WHERE order_id = ?",
                    Integer.class, "O-FAIL");

            System.out.printf("DB O-SUCCESS=%d, O-FAIL=%d%n", ok, failed);
        };
    }

    private static void sendAndReport(
            MessageChannel input, String id, boolean shouldFail) {

        try {
            input.send(MessageBuilder
                    .withPayload(new OrderCommand(id, shouldFail))
                    .setHeader("traceId", "trace-" + id)
                    .build());
            System.out.println("SEND_OK " + id);
        }
        catch (RuntimeException ex) {
            System.out.println("SEND_FAILED " + id + ": "
                    + ex.getClass().getSimpleName());
        }
    }
}

record OrderCommand(String orderId, boolean shouldFail) {}

@MessageEndpoint
class OrderCommandHandler {

    private final OrderTransactionService service;

    OrderCommandHandler(OrderTransactionService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orderCommands")
    public void handle(OrderCommand command) {
        service.saveOrder(command); // called through another bean -> transaction proxy
    }
}

@Service
class OrderTransactionService {

    private final JdbcTemplate jdbc;

    OrderTransactionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveOrder(OrderCommand command) {
        System.out.println("TX_ACTIVE="
                + TransactionSynchronizationManager
                        .isActualTransactionActive());

        jdbc.update(
            "INSERT INTO demo_orders (order_id, status) VALUES (?, ?)",
            command.orderId(), "CREATED");

        if (command.shouldFail()) {
            throw new IllegalStateException(
                    "Simulated failure after database INSERT");
        }
    }
}
~~~

**Expected output** (ignoring startup logs):

~~~text
TX_ACTIVE=true
SEND_OK O-SUCCESS
TX_ACTIVE=true
SEND_FAILED O-FAIL: ...
DB O-SUCCESS=1, O-FAIL=0
~~~

The exception name printed at `SEND_FAILED` may be a wrapper created by Spring Integration. The key result is **the DB has O-SUCCESS and does not have O-FAIL**.

### Why does the example roll back properly?

1. `ApplicationRunner` sends `Message<OrderCommand>` into `DirectChannel`.
2. `@ServiceActivator` receives the message and calls `OrderTransactionService.saveOrder(...)` through a **Spring bean proxy**.
3. `@Transactional` opens a transaction (or joins an existing one); `JdbcTemplate` acquires a connection participating in the `DataSourceTransactionManager` configured by Boot from the `DataSource`.
4. The code INSERTs the row. If `shouldFail` is true, `IllegalStateException` escapes `saveOrder()`.
5. The transaction interceptor catches the runtime exception and rolls back the INSERT. Then the exception continues back to `send()` on the same thread; the caller catches it to log.
6. The successful message is committed; the failing message leaves no row in the table.

**Do not confuse:** in this example, the transaction lives **inside the service**, wrapping each `saveOrder()` call. `DirectChannel` allows exceptions to travel back, yet it does not automatically turn the entire `ApplicationRunner` into a single transaction. Catching `SEND_FAILED` afterward **does not undo the rollback already performed** inside the service proxy.

The example has no broker or durable queue, so after the `O-FAIL` failure it **does not automatically reappear**. For retry/redelivery, you must add a policy and a supporting source.

### Change one thing to observe a different outcome

If you remove `@Transactional` from `saveOrder()` and no outer transaction is open, each `jdbc.update()` typically commits independently (depending on autocommit/DataSource); when the method throws, the `O-FAIL` row **may still exist**. This experiment demonstrates the difference between "a handler throws an exception" and "the resource is rolled back."

If you change `IllegalStateException` to a checked exception, declare `throws` appropriately on the method/caller and configure `rollbackFor` when you want rollback per the desired rule.

## 6. When does @Transactional take effect?

`@Transactional` typically operates via proxies (Spring AOP). Simply having the annotation in source code does not prove a transaction is actually opened.

| Situation | Typical behavior | Remediation |
| --- | --- | --- |
| Handler calls another `@Service` via an injected Spring bean | Invocation passes through proxy | Appropriate; verify `TX_ACTIVE` |
| A method in the same object calls an annotated `this.saveOrder()` | Self-invocation bypasses proxy in proxy mode | Extract to another bean or use an appropriate boundary |
| Method is not in a Spring-managed bean | Not wrapped by Spring transaction proxy | Register as a bean and enable transaction management properly |
| Private/final method, proxy target cannot be intercepted | Transaction may not apply as expected | Use public/proxy-interceptable methods per configuration |
| Two transaction managers or multiple DataSources | Wrong manager may be chosen, resource fails to join | Specify `@Transactional(transactionManager = "...")` explicitly |
| Transaction exists yet JDBC connection comes from outside manager | Resource unlikely to join transaction | Use `JdbcTemplate`/Spring-managed connections or compatible infrastructure |

In a Spring Boot application with JDBC/JPA starters and a suitable transaction manager, transaction management is usually auto-configured. In plain Spring Framework you must configure the manager and enable management explicitly. Logging `TX_ACTIVE=true` helps confirm a transaction context exists, yet **is not enough** to prove all external resources participate; you still need to check the manager type and actual logs/DB.

### When the source already opened a transaction

An inbound listener or poller may already have opened a transaction before invoking the handler. With `Propagation.REQUIRED` (default), `@Transactional` on the service usually **joins the existing transaction**. The transaction does not commit immediately when the service returns; it only commits/rolls back at the corresponding **outermost boundary**.

Suppose the service inserts and then a downstream handler on the same thread throws an exception. If the outermost transaction scope covers the downstream step as well, all participating changes can roll back. If there is no outer transaction and the service already committed, the downstream error **does not retroactively roll back** the row the service committed.

## 7. Transactional poller: does handler rollback requeue the message?

A poller is a special component: it actively calls `receive()` from a message source and feeds the message into the flow. Spring Integration supports placing a transaction around **receive-and-forward**. With the XML namespace, the conceptual syntax is:

~~~xml
<int:service-activator input-channel="workQueue"
                       ref="workHandler"
                       method="process">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"
                           propagation="REQUIRED"/>
    </int:poller>
</int:service-activator>
~~~

This is an **XML configuration snippet**: you must declare the `int` namespace, a `PollableChannel` bean `workQueue`, a `workHandler` bean, and a `transactionManager` bean, along with context configuration. Depending on the inbound adapter type, the poller can also be declared at the corresponding source.

When the handler throws a runtime exception **synchronously** during the poll and the error is not swallowed:

1. The transaction advice around the poll catches the error.
2. Transactions of participating resources (e.g., JDBC under the same manager) are rolled back.
3. The poller/error handler may record the error and continue to the next polling cycle.
4. **Whether the message returns to the queue depends on the message source/queue store.**

| Message source | What should be expected after rollback? |
| --- | --- |
| Pure **in-memory** `QueueChannel` | Does not guarantee by default that a dequeued message is put back when the database rolls back. |
| **Transaction-capable** queue/message store on the same resource using an appropriate manager | Pulling/deleting from the store can roll back with the transaction, allowing the message to reappear. |
| Transacted JMS session or matching transaction manager | The broker can redeliver per transaction and broker policy. |
| AMQP/Kafka or another adapter | Behavior depends on acknowledge, nack, rollback, and the specific adapter's container configuration. |
| File inbound adapter | Reading a file is not a filesystem transaction; synchronization can be used to move the file on commit/rollback. |

**Do not extrapolate:** putting `<int:transactional>` on a poller does not turn an in-memory `QueueChannel` into a durable transactional queue. Nor does it turn multiple independent resource managers into a distributed transaction.

### Message store and transaction synchronization

With a JDBC-backed store, select the transaction manager for the same `DataSource` and verify whether receive/delete/save statements participate in the transaction. The `TransactionSynchronizationFactory` mechanism allows executing **beforeCommit**, **afterCommit**, or **afterRollback** logic on the polled message, such as moving a source file to a success/failure folder or emitting an audit message based on the outcome.

~~~text
Poller transaction begins
    receive message
    process synchronous flow
    handler throws RuntimeException
Transaction rolls back
    afterRollback synchronization called if configured
    adapter/broker decides whether to redeliver
~~~

Transaction synchronization only synchronizes when actions run; **it does not make files, HTTP, or non-transactional resources rollbackable**. `PseudoTransactionManager` only provides simulated commit/rollback lifecycle callbacks without actually rolling back data.

## 8. Handler advice and rollback scope

Besides `@Transactional` on a Spring service, Spring Integration can attach `TransactionInterceptor` to an endpoint's advice chain.

For a **reply-producing handler** like a transformer or outbound gateway, standard request-handler advice typically wraps only `handleRequestMessage()`. Sending the reply to the downstream channel may lie **outside** that scope. Therefore:

~~~text
input -> @Transformer(tx request-handler advice) -> DirectChannel -> failing handler
               | transaction covers only transform logic |
                                                         X throw
~~~

If the transformer's transaction already committed before sending the reply, a downstream exception does not roll back that transaction. When you need to cover both `handleMessage()` and synchronous downstream work, Spring Integration provides **`TransactionHandleMessageAdvice`** (a `HandleMessageAdvice`), and `TransactionInterceptorBuilder(true)` can build the corresponding advice per the framework API.

Example builder declaration (standalone snippet; requires a transaction manager bean and appropriate imports):

~~~java
@Bean("transactionAdvice")
TransactionInterceptor transactionAdvice(
        PlatformTransactionManager transactionManager) {

    return new TransactionInterceptorBuilder(true)
            .transactionManager(transactionManager)
            .build();
}
~~~

In this snippet, `TransactionInterceptorBuilder` is in `org.springframework.integration.transaction`; attach the advice to an endpoint via `adviceChain = "transactionAdvice"` on supported annotations. Check the actual API version when importing and typing `TransactionManager`/`PlatformTransactionManager`. `true` selects `TransactionHandleMessageAdvice` instead of the regular request-handler transaction interceptor.

**Thread boundaries still apply:** `TransactionHandleMessageAdvice` can cover synchronous downstream work across `DirectChannel`, yet it does not propagate transactions across `ExecutorChannel` or another poller thread. Do not treat it as a cross-broker or cross-service transaction mechanism.

### Order of retry and transaction advice

Suppose an advice chain is declared sequentially from outside to inside:

~~~text
[retryAdvice, transactionAdvice]
  retry attempt #1 -> transaction -> handler throw -> rollback
  retry attempt #2 -> transaction -> handler success -> commit

[transactionAdvice, retryAdvice]
  transaction -> retry attempt #1 throw
              -> retry attempt #2 success
              -> commit? may hit rollback-only
~~~

With **retry outside, transaction inside**, each attempt *can* create its own transaction **if** no outer transaction exists and propagation/manager match. With transaction outside, multiple attempts in one transaction can leave rollback-only marked. A recovery callback or `trapException` can also swallow the exception, making the outer layer decide to commit.

In a flow with a poller transaction, handler advice creating its own `REQUIRES_NEW` transaction can lead to an independent commit before the poller rolls back: this can be right for error auditing, yet inappropriate if you need business data atomicity with the message source.

## 9. Caught exceptions, rollback-only, and UnexpectedRollbackException

Some bugs are hard to find because **the handler throws yet the transaction still commits**, or **the handler caught the error yet the final commit still fails**.

### Scenario A: error swallowed before the transaction interceptor

~~~java
@Transactional
public void saveOrder(OrderCommand command) {
    jdbc.update("INSERT INTO ...", ...);
    try {
        callExternalApi();
    }
    catch (RuntimeException ex) {
        logger.warn("API error", ex);
    }
    // Normal return: interceptor may commit JDBC.
}
~~~

This example illustrates the idea; helper methods are not declared. If rollback is required, **rethrow the exception** or intentionally mark rollback-only. Simply logging does not trigger rollback.

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Use only when certain an active declarative transaction exists.
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

However, `setRollbackOnly()` introduces hidden transaction logic inside business code; whenever possible, let exceptions and rollback rules express intent clearly.

### Scenario B: inner REQUIRED marks rollback-only, outer still commits

~~~text
outer @Transactional REQUIRED
    inner @Transactional REQUIRED
        DB change
        throw RuntimeException
    outer catch(RuntimeException) and continue
outer returns normally
outer commit -> UnexpectedRollbackException
~~~

When the inner method goes through a **proxy** and joins the same transaction, the inner interceptor can mark the shared transaction rollback-only. The outer catch cannot clear that flag; on commit, the transaction manager reports the commit cannot complete. This is an important signal to prevent "false successful commits."

### Scenario C: Checked exception

If a method throws `IOException` without `rollbackFor` and without other rules, the transaction interceptor may **commit** and then pass the exception to the caller. Seeing a stack trace does not prove the DB rolled back. Tests should inspect remaining data, not just assert an exception was thrown.

### Scenario D: Filter returns false or recovery succeeds

A `@Filter` returning `false` is normally a business condition outcome, not an exception. Similarly, retry advice with a `RecoveryCallback` may publish an `ErrorMessage` and return normally after storing the error. Depending on scope and the transaction manager, the outer transaction **may commit**. When broker redelivery is required, do not use a recoverer that swallows exceptions unless recovery has durably persisted the work and the business intentionally considers the original task finished.

## 10. Error events, errorChannel, retry, ack, and correlation

When an exception occurs affects where the error is observed:

| State when handler fails | Where error typically appears | What to verify |
| --- | --- | --- |
| Sync `DirectChannel`, no trap | Exception usually returns to `send()`/gateway caller | Does caller have an outer transaction? |
| Polling endpoint | Poller error handler and/or `ErrorMessage` | Does poller have a transaction around receive and handler? |
| `ExecutorChannel` | Worker thread, corresponding error flow | Does the worker have its own transaction? |
| Broker listener | Container error handler, rollback/nack/requeue | Ack mode, retry count, DLQ/redelivery policy |
| Retry advice with recovery callback | Recovery channel/handler | Did recovery persist the error before treating the message as complete? |

**`errorChannel` is not a transaction manager.** Sending an `ErrorMessage` does not invoke rollback by itself, nor does it guarantee the source message was requeued. It is an error-routing path; the original error must reach the transaction boundary at the right time to affect commit.

In Spring Integration, errors can contain `MessagingException.failedMessage`; with a poller using appropriate synchronization, the original message can also be attached to errors sent to the error channel for investigation. Log `traceId`, `correlationId`, `eventId`/idempotency key, channel/endpoint, and error class. Do not dump raw sensitive payloads into production logs.

Retries can cause **multiple executions of the same handler** for a single logical message:

- When rollback causes the broker to redeliver, the same command may come back.
- When `RequestHandlerRetryAdvice` retries within one invocation, the service can be called multiple times without broker redelivery.
- When multiple retry layers stack, invocation counts can multiply rapidly, easily causing duplicate side effects.

Therefore, handlers should be idempotent by business key and have clear transaction boundaries. If an external API was already called before throwing an error, JDBC rollback does not undo the API call; idempotency keys, an outbox, and reconciliation processes are needed.

## 11. Diagnosing unexpected rollback behavior

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| Handler throws `RuntimeException` yet DB row still exists | Missing transaction, wrong transaction manager, resource failed to join, or transaction already committed before error | Log `TX_ACTIVE`, inspect manager/DataSource and commit timing |
| `TX_ACTIVE=false` inside `@Transactional` method | Self-invocation, unproxied bean, transaction management not enabled | Extract method to another bean, verify proxy and context |
| `TX_ACTIVE=true` yet queue does not redeliver | In-memory queue, non-transacted source, adapter ack already completed | Inspect channel/store type, session transaction, and ack mode |
| Caught error yet ended with `UnexpectedRollbackException` | Inner REQUIRED marked rollback-only | Identify transaction propagation and interceptor layers |
| Checked exception propagates out yet DB still commits | Default rule does not roll back checked exceptions | Add `rollbackFor` with exact type and write a test |
| Downstream throws yet transformer's transaction still commits | Request-handler advice wraps only `handleRequestMessage()` | Check `TransactionHandleMessageAdvice` scope |
| Some steps roll back, yet HTTP side effect remains | External service does not participate in transaction | Use idempotency/compensation/outbox |
| Replacing `DirectChannel` with executor changes result | Exception does not return to original transaction thread | Redraw boundary, put manager on worker |
| Retry reports success yet data is later inconsistent | Retry/recovery swallowed error or missing idempotency | Check advice order, callback, ack, and commit |
| Poller fails yet message is gone | Receive operation cannot roll back or was marked handled | Inspect message store and poller error handler |

### Evidence-based debugging procedure

1. **Find the boundary:** which `@Transactional` method, transaction advice, poller, or listener opens the transaction? Which resource's transaction manager is it?
2. **Record a timeline:** at each handler, log thread name, endpoint name, `TransactionSynchronizationManager.isActualTransactionActive()`, message `traceId`, and exception timestamp.
3. **Inspect propagation:** `REQUIRED`, `REQUIRES_NEW`, `NESTED` (when resource supports savepoints), and where the outer transaction starts/commits; do not infer from a single annotation.
4. **Inspect the actual exception:** class at the boundary, root cause, whether caught/rethrown/trapped, and whether rollback policy matches.
5. **Check durable effects:** DB rows before/after, message source acknowledgement, queue/broker backlog, recovery store, and external side effects.
6. **Fault injection:** inject errors *before INSERT*, *after INSERT*, *after commit*, and *after async handoff* to distinguish boundaries.
7. **Optimize once semantics are right:** monitor transaction duration, waiting connections, lock waits/deadlocks, queue depth, executor saturation, and retry storms.

You can enable controlled DEBUG logging for Spring transaction packages such as `org.springframework.transaction.interceptor` and the corresponding transaction manager. Do not leave verbose SQL/sensitive payload logging enabled broadly in production.

## 12. Hands-on exercises and verification questions

1. Run `RollbackDemoApplication`, verify `O-SUCCESS=1` and `O-FAIL=0`. Check `TX_ACTIVE` in the service.
2. Remove `@Transactional`, rerun with a fresh H2 database so stale data does not interfere; compare the DB after throwing.
3. Write `BusinessCheckedException extends Exception`, change the handler to throw the checked exception, and configure `rollbackFor`. Compare before/after the rule.
4. Move `saveOrder()` logic into the same class and call it via `this`; observe whether proxy/self-invocation prevents the transaction from opening.
5. Place another `@ServiceActivator` downstream on the same `DirectChannel` and make it throw **after** the first service has committed; explain why the earlier service's separate transaction does not retroactively roll back.
6. Use an `ExecutorChannel` with a bounded executor between two handlers, log thread and active transaction on both sides; observe worker-side failures.
7. Switch the source to `QueueChannel` with a transactional poller. Compare an in-memory queue with a transaction-capable source/store; **do not assume** a dequeued message will return.
8. Test retry advice in both orders `[retry, tx]` and `[tx, retry]`; inspect rollback-only, thread hold time, and invocation counts.
9. Add a recovery consumer creating an error record with `eventId`; verify duplicates/restarts do not create two business operations.
10. Use a test adapter/broker with redelivery: cause a handler error, monitor broker ack/nack, DLQ, and retry stop conditions before concluding rollback guarantees reprocessing.

## 13. Conclusions you must verify yourself in a flow

- `throw RuntimeException` is **not** enough to prove rollback; a transaction must wrap the right operations with participating resources.
- `DirectChannel` preserves a synchronous call stack; `ExecutorChannel`/pollable channels create thread boundaries so the initial transaction does not automatically continue.
- `@Transactional` works through Spring proxies, so self-invocation and choosing the wrong transaction manager are very common reasons rollback fails to work.
- Database rollback and **message redelivery** are two distinct mechanisms. Only a transacted poller + transaction-capable message source can make message receipt roll back by design.
- Checked exceptions do not roll back by default; `rollbackFor`, `noRollbackFor`, and custom policies determine the final semantics.
- Exception recovery/trapping, retries, and transaction advice order can change commit behavior and handler execution counts.
- HTTP calls, file operations, and systems outside the transaction manager require idempotency, outbox/compensation, or appropriate transaction coordination.
- **Verify via post-error resource state** (DB rows, broker ack, DLQ), not merely by seeing an exception in logs.

## 14. Official references

- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, thread-bound transaction boundaries, synchronization, and pseudo-transactions.
- [Spring Integration — Polling and Transactions](https://docs.spring.io/spring-integration/reference/polling-consumer.html): transactional polling and receive-and-forward.
- [Spring Integration — TransactionHandleMessageAdvice](https://docs.spring.io/spring-integration/reference/handler-advice/tx-handle-message.html): `handleMessage()` vs. `handleRequestMessage()` scope.
- [Spring Integration — Advice Chain Order](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): transaction/retry ordering and advice wrapping.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): default rollback rules, checked exceptions, and custom rollback.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, manager, proxy, rollback semantics.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and rollback-only.
