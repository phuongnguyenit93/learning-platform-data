# Do Not Assume Two Tasks on Two Threads Can Roll Back Together

In Spring Framework, `@Transactional` manages transaction boundaries, whereas `@Async` and `TaskExecutor` move work onto another thread. Combining these two mechanisms **does not automatically create a single transaction spanning multiple threads**.

In Spring's standard imperative transaction model (`PlatformTransactionManager`, JDBC/JPA), transactions are bound to the **current execution thread**. When method A is inside a transaction and submits method B to a thread pool worker, the worker **does not automatically inherit A's transaction**. If B has its own transaction, B can commit independently before A rolls back; conversely, A can commit while B fails.

**Core rule: rolling back one transaction is not an "undo all concurrent work" command**. For two operations to be genuinely atomic, they must share a single transaction boundary supported by the transaction manager and resources. To achieve durable, consistent asynchronous processing across multiple steps, design explicit protocols such as post-commit events, transactional outboxes, or sagas — do not merely slap `@Transactional` onto two methods.

This Knowledge article belongs to the **Transactions and Events** group in **Spring Framework - concurrency**. Examples target Java 17+, Spring Framework 6.x / Spring Boot 3.x; plain Java sections compile standalone, while Spring code requires a database and Spring dependencies.

## 1. What Is a Transaction Really Doing Here?

A database transaction typically comprises starting, reading/writing, and committing or rolling back. With JDBC, statements executed on the same connection within the same transaction can commit or roll back **as one unit** per database capabilities.

In imperative Spring, `@Transactional` is typically implemented through a Spring AOP proxy and `TransactionInterceptor`. The transaction manager manages the connection, session, and thread-bound transaction state. Data-access operations **participate in the same transaction boundary when they use the appropriate transaction manager/resources and run within that context**.

Same-thread example:

~~~text
HTTP Thread #1
    |
    | --> Transaction T1 begins
    |     INSERT orders
    |     INSERT audit_events
    |     throw RuntimeException
    | --> T1 rolls back
    |
    +--> both INSERTs of T1 roll back
         (assuming the same transactional resource and no independent commit)
~~~

This differs starkly from two workers:

~~~text
HTTP Thread #1 / Transaction T1             Worker #2 / Transaction T2
    |                                               |
    | BEGIN T1                                      |
    | INSERT orders                                 |
    |---- submit async audit ---------------------->|
    |                                               | BEGIN T2
    |                                               | INSERT audit_events
    |                                               | COMMIT T2
    | throw RuntimeException                        |
    | ROLLBACK T1                                   |
    |                                               |
    v                                               v
  orders rolled back                        audit_events from T2
                                            still committed
~~~

This is **one possible outcome**, not a claim that every run follows that exact schedule. If the worker sits in the queue longer, it may start after T1 rolls back. If the worker needs to read T1's uncommitted data, it may block, miss the data, or hit a foreign-key constraint error. The essential point is that **two transactions do not synchronize commit/rollback merely because they were triggered by the same request**.

### 1.1. Scope of This Statement

This article covers imperative transactions managed by `PlatformTransactionManager` in standard Spring configurations, such as `DataSourceTransactionManager` / `JdbcTransactionManager` or `JpaTransactionManager`. These transactions are normally **thread-bound** and do not automatically propagate across threads.

Spring's reactive model can use `ReactiveTransactionManager` and Reactor Context instead of ThreadLocal. That is a different context-propagation architecture, **not proof that `@Transactional` automatically rolls back tasks across multiple threads in lockstep**. Do not mix reactive semantics with imperative JDBC/JPA when evaluating this problem.

## 2. Why Does @Transactional Not Follow @Async Automatically?

The standard sequence:

1. Caller passes through the `@Transactional` method's Spring proxy; the interceptor opens/registers a transaction **for the caller thread**.
2. Inside the method, code invokes an `@Async` bean through another Spring proxy.
3. The `@Async` interceptor submits the callback to a `TaskExecutor`. With an asynchronous thread pool, a different worker runs the callback.
4. The transaction context bound to the caller thread **does not automatically transfer to the worker**.
5. If the worker calls a transactional method through a proxy, Spring may open **a separate transaction** on the worker; without transactional advice on the worker, statements may run in auto-commit or under another configuration.
6. The caller finishes or throws an exception; the caller's transaction commits/rolls back according to its own rules. That state does not automatically undo a worker transaction that already committed.

~~~text
HTTP thread                     @Async interceptor                Pool worker
    |                                  |                               |
    | BEGIN parent TX                  |                               |
    | INSERT parent                    |                               |
    |---- asyncMethod() -------------->|-- queue task ---------------->|
    |<--- return Future ---------------|                               |
    |                                  |                         BEGIN worker TX?
    |                                  |                         INSERT child
    |                                  |                         COMMIT/ROLLBACK
    | ROLLBACK parent TX               |                               |
    |                                  |                               |
    | No implicit shared transaction between the two threads           |
~~~

The question mark in `BEGIN worker TX?` is intentional: the worker receives its own transaction only if configuration, annotations/proxies, and resource managers actually create one; **not every `@Async` task automatically has a transaction**.

### 2.1. REQUIRED, REQUIRES_NEW, and Common Misunderstandings

- `Propagation.REQUIRED`: on the same thread with the same transaction manager, a transactional method can join an existing transaction; if none exists, Spring creates a new one.
- When B runs on **another worker**, B normally cannot see transaction A on the caller. `REQUIRED` on B therefore opens a new transaction **for the worker**, rather than attaching to A.
- `Propagation.REQUIRES_NEW` creates an independent physical transaction when a transaction is already active in that context; it **is not a tool to merge two threads**. The new transaction commits/rolls back independently.
- `Propagation.NESTED` uses a savepoint within one physical transaction where supported by the transaction manager/database; it does not turn two DB connections on different threads into one shared rollback unit.
- Using the same `DataSource` still **does not mean** sharing the same JDBC connection or transaction. Each thread normally receives its own resource bound by the transaction manager.

In imperative Spring code, propagation describes how to handle **calls within the currently visible transaction context**, not a mechanism to ship a transaction across `ExecutorService.submit`.

## 3. Java 17: Simulating Two ThreadLocal Transactions

This program simply models **how transaction context binds to a thread** and commits/rolls back separately. It **does not connect to a database and is not a JDBC transaction implementation**; its purpose is to clarify why a worker does not automatically inherit state from its caller.

Create **`CrossThreadTransactionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CrossThreadTransactionDemo {
    record Tx(String name, List<String> staged) {}

    private static final ThreadLocal<Tx> CURRENT = new ThreadLocal<>();
    private static final List<String> COMMITTED = new CopyOnWriteArrayList<>();

    static void begin(String name) {
        CURRENT.set(new Tx(name, new ArrayList<>()));
    }

    static void stage(String change) {
        Tx tx = CURRENT.get();
        if (tx == null) {
            throw new IllegalStateException("No local transaction");
        }
        tx.staged().add(change);
    }

    static void commit() {
        Tx tx = CURRENT.get();
        if (tx == null) {
            throw new IllegalStateException("No local transaction");
        }
        COMMITTED.addAll(tx.staged());
        CURRENT.remove();
    }

    static void rollback() {
        CURRENT.remove();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        begin("caller");
        try {
            stage("order");
            Future<?> child = executor.submit(() -> {
                System.out.println("1. Child inherited transaction: "
                        + (CURRENT.get() != null));
                begin("child");
                try {
                    stage("audit");
                    commit();
                    System.out.println("2. Child committed audit");
                } finally {
                    CURRENT.remove();
                }
            });
            child.get();
            rollback();
            System.out.println("3. Caller rolled back order");
            System.out.println("4. Committed changes: " + COMMITTED);
        } finally {
            CURRENT.remove();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 CrossThreadTransactionDemo.java
java CrossThreadTransactionDemo
~~~

Verified stdout when compiled and run at `--release 17`:

~~~text
1. Child inherited transaction: false
2. Child committed audit
3. Caller rolled back order
4. Committed changes: [audit]
~~~

Explanation:

1. A regular `ThreadLocal<Tx>` is not copied to the worker thread. `CURRENT.get()` on the worker is `null`, printing `false`.
2. The worker calls `begin("child")` itself, stages `audit`, and calls `commit()`. The simulated committed-data list receives `audit`.
3. `Future.get()` makes the caller **wait for the worker to finish**, yet **does not merge the worker's transaction into the caller's transaction**.
4. The caller rolls back the `order` staged in its own context; the committed `audit` change remains in the list.
5. Output ordering is deterministic thanks to `Future.get()` and avoiding unsynchronized concurrent printing across threads during checked steps.

Key takeaway: **waiting for a worker to finish does not mean sharing a transaction**. `CompletableFuture.allOf(...).join()` is likewise only a completion-waiting barrier; it has no ability to roll back already-committed transactions.

### 3.1. What This Simulation Does Not Prove

- It performs no real JDBC commits or rollbacks.
- It does not test isolation levels, locks, deadlocks, or constraints.
- It does not prove that using Spring always yields this exact stdout ordering.
- It has no distributed transaction coordinator.

To evaluate real applications accurately, you need integration tests with a real database and transaction manager as covered below.

## 4. A Spring Anti-Pattern: Parent Rolls Back While Worker Commits Independently

Suppose an application manages orders and audits using Spring JDBC. This schema is strictly for learning: the `audit_events` table here **has no foreign key** to `orders` so we can observe an independent audit still committing even when the order rolls back.

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(48) NOT NULL
);
~~~

The DDL above targets databases supporting that identity syntax (such as H2); for PostgreSQL or other engines, verify the matching dialect and migrations. **Never drop foreign keys in real schemas just to avoid errors**; omitting the FK here intentionally exposes the risk of writing "orphaned audits".

### 4.1. Executor and Transaction Management Beans

File `ConcurrentTxConfig.java`:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableAsync
@EnableTransactionManagement
public class ConcurrentTxConfig {

    @Bean("auditExecutor")
    public ThreadPoolTaskExecutor auditExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("audit-");
        return executor;
    }
}
~~~

This is **Spring Framework 6.x / Java 17+ integration code**, not runnable via `javac` without Spring dependencies. It requires a properly configured `PlatformTransactionManager` for JDBC/JPA, a datasource, schema, and component scanning. In compatible Spring Boot apps, starters typically provide these pieces; in plain Spring Framework, register them explicitly.

### 4.2. AuditWriter Opens Its Own Transaction When Called by the Worker

File `AuditWriter.java`:

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {
    private final JdbcTemplate jdbc;

    public AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveRequested(long orderId) {
        jdbc.update(
                "INSERT INTO audit_events(order_id, event_type) VALUES (?, ?)",
                orderId, "ORDER_REQUESTED");
    }
}
~~~

File `AsyncAuditDispatcher.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncAuditDispatcher {
    private final AuditWriter writer;

    public AsyncAuditDispatcher(AuditWriter writer) {
        this.writer = writer;
    }

    @Async("auditExecutor")
    public CompletableFuture<Void> dispatch(long orderId) {
        writer.saveRequested(orderId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

The call traverses **two distinct beans/proxies**: Spring dispatches `AsyncAuditDispatcher.dispatch(...)` to a worker; on the worker, `AuditWriter.saveRequested(...)` passes through a transactional proxy and opens the worker's transaction. This separation avoids confusion over advice ordering when placing `@Async` and `@Transactional` on the same method, and avoids self-invocation.

### 4.3. Parent Transaction Dispatches Work and Then Rolls Back

File `OrderCreationService.java`:

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {
    private final JdbcTemplate jdbc;
    private final AsyncAuditDispatcher audit;

    public OrderCreationService(
            JdbcTemplate jdbc, AsyncAuditDispatcher audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    @Transactional
    public void createThenFail(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "PENDING");

        audit.dispatch(orderId);

        throw new IllegalStateException("rollback order transaction");
    }
}
~~~

This example deliberately demonstrates an **unsafe design**:

- Parent inserts into `orders` in uncommitted transaction T1.
- Parent submits the audit; the caller **does not wait** for the worker and does not handle the returned future.
- The worker can start T2, insert into `audit_events`, and commit.
- Parent throws `IllegalStateException`, causing T1 to roll back per `@Transactional`'s default rule for `RuntimeException`.
- If T2 already committed, the audit row remains even though the order rolled back. Or T2 can run after T1 rolled back and still insert the audit.

There is no fixed stdout for this Spring integration example because scheduler ordering, database, queue, and connection-pool settings affect the observed result. Adding a foreign key from audit to order may cause the worker to block or hit a constraint error because the order is uncommitted/rolled back; that is **a different failure mode**, not a fix for transaction boundaries.

With `@Async` returning `CompletableFuture`, worker exceptions fail the Future. Because the parent neither retains nor observes the Future, errors are easily missed; and even if the parent called `get()` and threw to roll back T1, an **already-committed T2 will not roll back automatically**.

### 4.4. Four Distinct Outcomes to Separate

| Actual execution order | Possible outcome |
| --- | --- |
| T2 commits, then T1 rolls back | Audit exists, order does not exist |
| T1 rolls back first, T2 runs and commits | Audit can still exist if no constraint prevents it |
| T1 commits, T2 fails/rolls back | Order exists, audit is missing |
| T1 commits, T2 commits | Both exist, yet still **not a single atomic transaction** |

Parallel execution yields multiple interleavings with no all-or-nothing guarantee. If both need DB connections and the pool runs dry, blocking or deadlocks can also occur when the caller holds a transaction while waiting for the worker.

## 5. When Atomic Rollback Is Needed: Keep Related Writes in One Transaction

If both operations write to the same database and business logic demands **all-or-nothing**, the simplest solution is usually executing them **inside one transactional method on the same thread**.

File `AtomicOrderService.java` (an **alternative**, not used alongside the anti-pattern):

~~~java
package example.concurrency;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AtomicOrderService {
    private final JdbcTemplate jdbc;

    public AtomicOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrderWithAudit(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "PENDING");
        jdbc.update(
                "INSERT INTO audit_events(order_id, event_type) VALUES (?, ?)",
                orderId, "ORDER_CREATED");
    }
}
~~~

When `@Transactional` is genuinely active and both SQL statements share the transaction of the same datasource/transaction manager, if one throws an unhandled `RuntimeException`, the transaction rolls back both. If the method commits successfully, both writes are confirmed per the database's contract.

Note: never automatically extend this claim to external HTTP requests, emails, non-transactional message brokers, or non-enlisted resources. A DB transaction **has no Undo button for external side effects**.

### 5.1. What If Parallel Processing Is Still Wanted?

Ask first: does the requirement truly demand parallel AND atomic execution? A local DB transaction backed by one connection is not meant to be shared arbitrarily across workers. Never hand the same `Connection` or JPA `EntityManager` to multiple threads to share: these data-access objects are generally not thread-safe, and Spring provides no magic to make doing so safe.

When throughput requires parallelism, perform pure/side-effect-free computation in parallel first, then collect the results and run the atomic writes inside one transaction on one thread. This pattern still requires watching memory, timeouts, and errors in the parallel computations, while avoiding cross-thread DB transaction sharing.

## 6. Emit Events Only After Commit: @TransactionalEventListener

A separate requirement is **not running secondary tasks if the main transaction rolls back**. For events meaningful only once data has committed, Spring supports `@TransactionalEventListener`, which binds listeners to `AFTER_COMMIT` by default.

For example, a service publishing an event inside a transaction:

~~~java
package example.concurrency;

public record OrderCreatedEvent(long orderId) {}
~~~

File `OrderRegistrationService.java`:

~~~java
package example.concurrency;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRegistrationService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    public OrderRegistrationService(
            JdbcTemplate jdbc, ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void create(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "CREATED");
        events.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

File `OrderCreatedListener.java`:

~~~java
package example.concurrency;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedListener {
    private final AuditWriter writer;

    public OrderCreatedListener(AuditWriter writer) {
        this.writer = writer;
    }

    @Async("auditExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        writer.saveRequested(event.orderId());
    }
}
~~~

These snippets are an **alternative integration pattern** replacing the anti-pattern, using `ConcurrentTxConfig`, `AuditWriter`, and the schema/transaction manager above. There is no fixed output. Semantics:

- The event is published inside transaction T1.
- If T1 rolls back, the `AFTER_COMMIT` listener **does not run post-commit logic**.
- Only after T1 commits is the listener callback triggered; `@Async` offloads processing to the chosen executor.
- `AuditWriter.saveRequested(...)` runs on the worker through its transactional proxy, so it gets **its own** audit transaction rather than sharing T1.

**Important limitation:** `AFTER_COMMIT` only determines **when event processing starts relative to commit**, not that the audit is guaranteed to succeed. The app can crash right after DB commit before the async job is saved/run; the executor can reject, the worker can fail, and in-memory events can be lost. And if the audit fails after commit, **it does not roll back the already-committed order**.

By default, `@TransactionalEventListener` **does not run when no transaction exists** to bind the phase to, unless `fallbackExecution=true` is explicitly enabled. Do not turn on fallback just to "force it to run no matter what" when business rules demand post-commit emission.

### 6.1. Event Phases Do Not Mean Cross-Thread Rollback

| Phase | When does the listener trigger? | What must NOT be inferred |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction prepares to commit | No guarantee an async callback is part of the DB commit |
| `AFTER_COMMIT` | After the transaction commits successfully | Does not make subsequent tasks atomic with the prior transaction |
| `AFTER_ROLLBACK` | After the transaction rolls back | Does not automatically roll back side effects already executed on other workers |
| `AFTER_COMPLETION` | After transaction completion, commit or rollback | Does not provide durable retries or exactly-once events |

If processing **synchronously inside AFTER_COMMIT** and writing to the DB using old transactional resources, be careful: resources may still be bound during the callback phase even though the primary transaction already finished; new writes may not commit as expected. Open a new transaction (e.g., `REQUIRES_NEW` depending on the case) or offload to a worker with its own transaction. Even then, the two transactions are not atomic.

## 7. When Post-Commit Dispatch Must Be Guaranteed: Transactional Outbox

If the requirement is **"whenever an order commits, a record must exist to emit the event later"**, an in-memory `AFTER_COMMIT` listener lacks durability. The **transactional outbox** pattern stores **domain data and event records** inside the same local DB transaction.

~~~text
Transaction T1 (single DB)
     |
     +-- INSERT orders
     +-- INSERT outbox_events
     +-- COMMIT both
             |
             v
      Independent worker / relay
             |
             +-- reads committed outbox rows
             +-- publishes event / sends to broker
             +-- marks sent or retries
             |
             v
      Idempotent consumer processing
~~~

If T1 rolls back, both `orders` and `outbox_events` roll back together. If T1 commits, at least a durable outbox record exists for the relay to resume after a restart. **This is the genuine atomic boundary needed** — between order data and *intent to emit an event*, not between a DB transaction and remote processing.

Additional schema example (illustrative SQL; adjust dialect):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload VARCHAR(2048) NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

File `OutboxOrderService.java`:

~~~java
package example.concurrency;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxOrderService {
    private final JdbcTemplate jdbc;

    public OutboxOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(long orderId) {
        jdbc.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                orderId, "CREATED");

        String eventId = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO outbox_events(" +
                "event_id, aggregate_id, event_type, payload, published) " +
                "VALUES (?, ?, ?, ?, ?)",
                eventId, orderId, "ORDER_CREATED",
                "{\"orderId\":" + orderId + "}", false);
    }
}
~~~

This is **Spring/JDBC integration code**, with no relay shown in this snippet. A separate relay must read unpublished rows, manage concurrency/claiming/leasing, publish to the broker, handle retries/backoff, and update status with proper loss/duplicate prevention.

### 7.1. Why Does an Outbox Not Mean System-Wide Exactly-Once?

A relay can publish an event successfully to the broker and crash **before** marking the outbox row published. After restart, the event is sent again. Therefore practical implementations provide **at-least-once delivery**, and receivers must process **idempotently** by `event_id` or an idempotency key.

An outbox closes the gap between committing domain data and **durably recording the intent to send an event**; it does not merge the DB, email, and payment systems into a single rollbackable transaction. You must design ordering, deduplication, poison-message handling, and backlog monitoring per requirements.

## 8. Sagas and Compensation Across Multiple Independent Transactions

When a business flow spans multiple services/databases, steps usually cannot be combined into one local transaction. A **Saga** treats each step as its own local transaction while defining **compensating actions** if later steps fail.

Example order flow:

~~~text
T1: create PENDING order    -> commit
T2: reserve inventory       -> commit
T3: charge payment          -> fail

Compensation C2: release inventory (new transaction)
Compensation C1: mark order FAILED (new transaction)
~~~

Key points:

- Compensation **is not a physical rollback**. It is a new business action that can itself fail, retry, or leave an audit trail.
- Once an email is sent or a third party saw an event, there is no perfect "undo".
- You need a state machine, correlation IDs, idempotency, timeouts, bounded retries, stuck-workflow detection, and operator tooling for exceptions.
- If compensation fails, the workflow must remain in an actionable failure state rather than falsely reporting "everything rolled back".
- A saga is not implemented simply by catching exceptions from `CompletableFuture.allOf` and trying to roll back already-committed databases.

### 8.1. Do Distributed Transactions / XA Exist?

Some systems can deploy distributed transactions via JTA/XA and a transaction coordinator with supporting resources. However, **that is a specialized architecture** with overhead, limitations, and resource-enlistment requirements; it does not appear automatically simply from placing `@Transactional` on methods across workers.

That is why this article's title does not say "two threads can never participate in a distributed transaction protocol", but rather **do not assume by default that two tasks on two Spring threads can roll back together**.

## 9. Futures, join, and Exceptions Do Not Create a Shared Transaction

A common design mistake:

~~~java
@Transactional
public void process() {
    CompletableFuture<Void> f1 = worker.updateA();
    CompletableFuture<Void> f2 = worker.updateB();

    CompletableFuture.allOf(f1, f2).join();
    // If any Future fails, throw an exception to roll back the parent.
}
~~~

This is **Java/Spring pseudocode** requiring `worker` beans and other methods. If `worker.updateA()` / `updateB()` run on separate threads with their own transactions:

- `allOf(...).join()` only waits for the Futures to complete. It **has no knowledge of which DB transactions committed** and has no Undo button for those commits.
- If f1 commits T1, f2 rolls back T2, and `join()` throws `CompletionException`, the caller's transaction (if any) may roll back; **the already-committed T1 stays independent**.
- When the caller holds a DB connection inside its transaction while waiting for workers needing other connections, connection exhaustion, blocking, or deadlocks can result. Long waits also make the outer transaction hold locks longer.
- `Future.cancel(true)` does not guarantee stopping a running task either; with `CompletableFuture.cancel()`, cancelling the Future certainly does not roll back a worker transaction that already committed.

If you genuinely need one atomic transaction, do not use `allOf` to mimic a transaction manager. If you need concurrency, separate parallel computation from the atomic commit phase, or adopt an eventual-consistency model with compensation.

## 10. Default Transaction Rollback Rules Must Be Understood Correctly

In Spring `@Transactional` with a standard imperative transaction manager:

- Uncaught `RuntimeException` or `Error` at the transactional method boundary normally causes Spring to mark rollback per default rules.
- Checked exceptions (such as `Exception` subclasses that are not `RuntimeException`) **do not trigger rollback** by default; use `rollbackFor` when needed.
- If a method catches an exception and returns normally without marking rollback-only, the transaction can commit even though a logical step failed.
- Calling a method in the same bean via `this.transactionalMethod()` bypasses the Spring proxy, disabling `@Transactional` in default proxy mode.
- `@Async` also depends on interceptors/proxies. There is no boundary guarantee if a call does not pass through the proxy as expected.

This is why the Spring examples in this article use **separate beans**, rather than having one method both dispatch async work and directly call a `@Transactional` method on the same object.

### 10.1. What Happens to Worker Errors Once the Parent Transaction Committed?

Suppose the parent dispatches an async worker and commits successfully. Seconds later, the worker encounters an error. The parent transaction **is no longer active** to be rolled back by a worker exception. You must update job status, apply retries/idempotency, or run compensation per the business contract.

With `@Async void`, unhandled exceptions go to `AsyncUncaughtExceptionHandler`. With `@Async CompletableFuture<T>`, execution exceptions surface on the Future. **Neither automatically rolls back another already-committed transaction.**

## 11. Observability and Error Handling in Real Systems

States worth tracking per workflow:

| Event / State | Important metadata |
| --- | --- |
| `PARENT_TX_STARTED` | Correlation ID, transaction/workflow ID |
| `PARENT_COMMITTED` or `PARENT_ROLLED_BACK` | End boundary of the parent |
| `CHILD_SUBMITTED` and `CHILD_REJECTED` | Whether the executor accepted or rejected the task |
| `CHILD_STARTED` | Worker actually started |
| `CHILD_COMMITTED` or `CHILD_ROLLED_BACK` | Outcome of the child transaction |
| `EVENT_PERSISTED` | Outbox event written inside the local transaction |
| `EVENT_PUBLISHED` and `EVENT_RETRIED` | Relay sent the event, possibly retried |
| `COMPENSATION_REQUESTED` / `COMPENSATION_DONE` | Compensation workflow and outcome |
| `FAILED_NEEDS_ATTENTION` | Workflow unable to self-recover |

These names are **application log/metric suggestions**, not built-in Spring states. Avoid logging full sensitive payloads; use correlation/job/event IDs to link steps and control label cardinality when pushing metrics.

### 11.1. Distinguishing Three Error Classes

**Submission errors:** the executor is saturated or shut down and refuses tasks, e.g., Spring `TaskRejectedException`. If the parent transaction is still open and the exception goes uncaught, it can roll back the parent. That **is not rolling back a committed child transaction**, since the child was never accepted.

**Child execution errors:** the worker ran, the DB operation failed, and the child transaction rolled back; the parent may already have committed or still be running. Future/handler errors only aid observation; they do not synchronize rollbacks.

**Event-delivery / messaging errors:** the DB transaction committed, yet the relay, broker, or network failed. With an outbox, the event remains to retry; with in-memory async only, the work may be lost.

Assign distinct retry policies to each group. Never retry deterministic errors forever, and never retry payments/side effects without idempotency.

## 12. Testing Transaction Boundaries With Real Evidence

With the Section 3 Java demo, `ThreadLocal` and the `COMMITTED` list demonstrate **separate contexts across two threads**. Verifying Spring/JDBC, however, requires integration tests with a real transaction manager and DB.

A checklist:

1. **Verify proxies:** `@EnableTransactionManagement` / auto-configuration, `@EnableAsync`, bean injection, calls from other beans. Never instantiate `new Service()` directly.
2. **Verify connections/transactions:** inside the worker, `TransactionSynchronizationManager.isActualTransactionActive()` shows whether a transaction is active **on the current thread**, though it does not prove a shared transaction with the caller. You can log thread names and datasource connection IDs to confirm.
3. **Use latches instead of random sleeps:** explicitly pause the worker or parent at specific boundaries to force commit/rollback orderings; avoid flaky tests driven by OS scheduling.
4. **Test parent rollback, child commit:** where schema allows, parent inserts and throws; child runs separately and commits; query the DB outside the test transaction afterward to confirm only child data exists.
5. **Test parent commit, child failure:** parent commits then worker throws; verify parent data remains and Future/job status records the child error.
6. **Test AFTER_COMMIT:** publish the event inside a transaction. On rollback, listener does not dispatch commit work; on commit, listener fires. With `@Async`, wait for callback completion via latch or eventual assertions.
7. **Test outbox:** on rollback, both domain and outbox rows disappear; on commit, both exist. Simulate relay sending successfully then dying before ACK to verify deduplication.
8. **Test connection pressure:** test when the caller holds a transaction while waiting for a worker that also needs a connection. Avoid pool sizing with insufficient connections.
9. **Test compensation failures:** ensure the state machine never reports a workflow as successfully rolled back when a compensation step failed.

**Be careful with default `@Transactional` on the test method itself**: test frameworks often roll back the test's transaction after each case while the async worker uses a different transaction. This can mask bugs or make results confusing. For commit/rollback durability tests, manage transaction boundaries explicitly and inspect the DB outside the test transaction.

## 13. Misconceptions to Avoid

**"Both A and B have `@Transactional`, so A's rollback rolls back B too."** False when A and B have separate transactions on different workers. Annotations do not create a global transaction.

**"Using the same `DataSource` guarantees the same transaction."** False. Different threads normally acquire different connections and transaction contexts.

**"`Propagation.REQUIRED` automatically joins the caller's transaction even over `@Async`."** False in the thread-bound `PlatformTransactionManager` model; the worker cannot see the caller's context.

**"Use `REQUIRES_NEW` to make two tasks roll back together."** False. `REQUIRES_NEW` intentionally creates an independent physical transaction.

**"Calling `allOf().join()` before returning makes all children atomic."** False. Waiting on Futures does not unify already-executed commits.

**"If the parent rolls back, the dispatched `@Async` task definitely won't run."** False. The task may already have been picked up and processed; it has no way to know the parent rolled back without a protocol.

**"`@TransactionalEventListener(AFTER_COMMIT)` guarantees events are never lost."** False. It prevents execution when the parent rolls back, yet an in-memory async callback can still be lost after commit; an outbox solves intent durability.

**"If audit has a foreign key to order, the two transactions become atomic."** False. An FK may cause the worker to block or fail while the parent is uncommitted/rolled back; it does not create a shared transaction.

**"Sagas roll back all committed transactions."** False. Sagas execute new **compensating actions**; they do not perform physical cross-service DB rollbacks.

**"A late exception from a child Future still rolls back the committed parent."** False. Once the parent transaction ended, no active boundary remains to roll back.

## 14. Exercises and Solutions

**Question 1.** Method A has `@Transactional` on an HTTP thread and calls B with `@Async`. B has `@Transactional(propagation=REQUIRED)`. Is B guaranteed to join transaction A?

**Answer:** No. In imperative Spring, transaction A is bound to the HTTP thread; B on a worker normally cannot see that transaction and will open its own transaction.

**Question 2.** B committed successfully on a worker; afterward, A throws a `RuntimeException`. Does Spring also roll back B's commit?

**Answer:** No. A rolls back its own transaction, without undoing B's already-committed transaction.

**Question 3.** If A calls `CompletableFuture.allOf(f1, f2).join()` before committing, does that make the two child transactions atomic?

**Answer:** No. `join()` only awaits and propagates Future status; it does not merge commit boundaries across multiple database transactions.

**Question 4.** When can a single `@Transactional` roll back both order writes and audit writes?

**Answer:** When both DB operations participate in **the same physical transaction** under a supporting model/resource/manager — normally on the same thread for JDBC/JPA without opening another independent transaction.

**Question 5.** What does `@TransactionalEventListener(phase=AFTER_COMMIT)` solve, and what does it NOT solve?

**Answer:** It invokes the listener only after the parent commits successfully; it does not guarantee durable delivery, retries, or rolling back the parent if subsequent async processing fails.

**Question 6.** Why does an outbox require idempotent consumers?

**Answer:** A relay can publish successfully and crash before recording sent status; upon restart it will republish, leading to at-least-once delivery.

**Question 7.** How does saga compensation differ from a DB rollback?

**Answer:** Compensation is a new business action offsetting an effect, rather than a physical reversal of committed transactions, and it can itself fail.

**Question 8.** If A holds a DB connection and calls `join()` waiting for B which also needs a connection, what is the risk?

**Answer:** Connection exhaustion, lock waits, timeouts, or deadlocks depending on workload; avoid waiting on workers that need resources held by the parent transaction.

**Question 9.** A worker task throws an exception after HTTP already returned 202. Can the earlier response be changed to 500 or the committed parent transaction be rolled back?

**Answer:** No. You need job status, alerts, retries, or compensation; 202 must be understood as accepted per the designed contract, not completion of the entire workflow.

## 15. Design Principles to Remember

- **Different threads do not share a transaction by default.** In imperative Spring, transaction context is typically thread-bound.
- **`@Transactional` does not create a global rollback.** Operations need the same transaction manager/resource and the same managed transaction boundary.
- **Future/`join` synchronizes completion, not commits.**
- **If targeting the same DB and atomicity is required, write inside one local transaction.**
- **If post-commit execution is needed and best-effort is acceptable, consider `@TransactionalEventListener(AFTER_COMMIT)` with error monitoring.**
- **If event-sending intent must be stored durably alongside domain data, use a transactional outbox.**
- **When multiple systems have committed side effects, consider sagas with compensation and idempotency rather than promising a shared rollback.**

## 16. Official References

- Spring Framework 6.2 — Declarative Transaction Implementation (thread-bound transactions): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.2 — Using `@Transactional` and rollback settings: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction Propagation (REQUIRED, REQUIRES_NEW, NESTED): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Framework 6.2 — Transaction-bound Events (`@TransactionalEventListener`): https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — Task Execution and Scheduling (`@Async`): https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 — ThreadLocal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 — ExecutorService/Future: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
