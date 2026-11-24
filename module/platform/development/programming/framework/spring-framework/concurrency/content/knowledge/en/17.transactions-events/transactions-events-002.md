# Creating a New Transaction Boundary in the Processing Bean When Business Logic Requires It

## Objectives

In Spring Framework, a transaction managed under the imperative model with `PlatformTransactionManager` is normally bound to the **executing thread**. When business logic dispatches work to an executor using `@Async`, **the caller's transaction does not automatically carry over to the worker**. If the worker needs to persist data atomically, you must design **a transaction boundary for the processing unit itself**.

The issue is not simply slapping `@Transactional` anywhere. You need to decide **whether the business logic truly permits an independent transaction**, place the transaction around the right logic, invoke it through a Spring proxy, choose the right propagation, and understand the effects when the caller commits/rolls back, the worker succeeds/fails, or an event is processed after commit.

This lesson helps you:

1. Understand thread-bound transactions and why `@Async` does not automatically inherit the caller's transaction.
2. Know how to separate the async-receiving bean from the `@Transactional` processing bean to open a transaction on the worker.
3. Distinguish `Propagation.REQUIRED`, `REQUIRES_NEW`, and `NESTED`; avoid assuming `REQUIRES_NEW` is always needed when switching threads.
4. Identify cases where the worker **should** and **should not** commit independently of the caller.
5. Use `@TransactionalEventListener(phase = AFTER_COMMIT)` and a transactional outbox appropriately when work depends on the source transaction committing.
6. Run a Java 17+ and Spring Framework example with H2: the caller rolls back while the transaction opened by the worker still commits.
7. Handle self-invocation, failures, timeouts, connection-pool contention, retries, and idempotency.

**Core message:** `@Async` determines **where the work runs**; `@Transactional` determines **the atomic boundary of data operations**. Those are two distinct contracts. A new transaction on the worker is only right when the business logic truly needs and accepts that independence.

## 1. Which Thread Does a Spring Imperative Transaction Live On?

For standard JDBC/JPA, `@Transactional` is enforced by Spring's transaction advice/proxy. A suitable `PlatformTransactionManager` binds the connection, synchronizations, and transaction state to the **current thread** via mechanisms such as `TransactionSynchronizationManager`.

```text
HTTP / caller thread
    |
    +-- @Transactional method
    |      Spring opens transaction A
    |      binds transaction resources to caller thread
    |      SQL operations inside transaction A
    |
    +-- calls @Async("workExecutor") ----> worker thread
    |                                    |
    |                                    +-- does not automatically have transaction A
    |                                    +-- if needed, opens separate transaction B
    |                                    +-- commits/rolls back transaction B
    |
    +-- caller commits/rolls back A
```

When a `@Transactional` method on the caller invokes `@Async`, the worker cannot "see" transaction A merely because the caller still has an open transaction. This is a property of **thread-bound imperative transactions**; in reactive programming, Spring uses Reactor context and a separate contract, so you should not apply thread-bound logic verbatim.

Three things to distinguish:

- **Transaction opened:** Did transaction advice start or join a transaction on the currently executing thread?
- **Task submitted:** Did the async proxy submit the invocation to the executor? The task might still be sitting in the queue.
- **Data committed:** Can others or the worker see the record yet? This also depends on isolation level, locks, and commit timing.

If the caller just ran `INSERT order` without committing, a worker using its own connection normally cannot see that order at an isolation level such as `READ_COMMITTED`. Some databases may make the worker wait on a lock; async submission **does not guarantee** the caller's data is ready.

## 2. When Should You Open a New Transaction in the Processing Bean?

**Valid** examples when there is a unit of work that must be atomic inside the worker:

- Saving the result of a background job **that is permitted to run independently**, including updating job status and writing related records within the same worker transaction.
- Recording an independent processing attempt (attempt log), when the business intentionally wants to persist it even if the caller fails.
- Processing a message already fetched from a broker; the consumer's data transaction should cover the update operations inside the handler itself.
- After the order-creation transaction **has committed**, updating a projection or notification status in a new transaction.
- Splitting a pipeline into multiple steps with explicit states, where each step is its own transaction coordinated via a job record/event, without pretending all steps form one cross-thread transaction.

Examples where you **should not** let the worker commit independently just because `@Async` is present:

- The caller creates an order in transaction A, the worker immediately writes shipment/payment and commits B; later A rolls back. Shipment/payment may remain even though the order never committed.
- Business rules require **all-or-nothing** semantics between the caller's operations and the worker's operations; a separate transaction breaks global atomicity.
- The worker needs to read data the caller just created but has not committed; running the worker early can miss data, hit locks, or retry erroneously.
- There is no durable work store yet every task is expected to survive crashes/restarts.

**Ask before writing the annotation:** If the caller's transaction rolls back, is the worker's record allowed to exist? If the answer is "no", do not choose an independent transaction and hope that putting `@Transactional` on both sides will coordinate their commits automatically.

## 3. Separating Responsibilities Into Two Spring Beans

An easy-to-understand structure that reduces AOP confusion:

```text
Caller bean / controller
  |
  +-- calls asyncGateway.dispatch(...)
                 |
                 v
       Spring async proxy
                 |
                 v
            workExecutor
                 |
                 v
          worker thread
                 |
                 +-- asyncGateway target method
                              |
                              +-- transactionalWorker.save(...)
                                        |
                                        v
                                  Spring tx proxy
                                        |
                                  BEGIN transaction B
                                        |
                                  JDBC / JPA writes
                                        |
                                  COMMIT / ROLLBACK B
```

Recommended separation:

- **`AsyncGateway`** accepts the request, holds the `@Async` method or explicitly submits to an executor. It defines the thread boundary and can return `CompletableFuture<T>` for the caller to track.
- **`TransactionalWorker`** contains the cohesive data operations that must commit/roll back together, is annotated with `@Transactional`, and **is called through a Spring proxy**.
- **Repository/JdbcTemplate** uses the right `DataSource`/`EntityManagerFactory` managed by the worker's `PlatformTransactionManager`. When using two different DataSources, select the right transaction manager; a single transaction manager does not automatically cover all databases.

Structural example:

```java
@Service
class AsyncGateway {
    private final TransactionalWorker worker;

    AsyncGateway(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("workExecutor")
    public CompletableFuture<String> dispatch(long id) {
        String result = worker.save(id); // call another transactional bean
        return CompletableFuture.completedFuture(result);
    }
}

@Service
class TransactionalWorker {
    @Transactional(propagation = Propagation.REQUIRED)
    public String save(long id) {
        // JDBC/JPA operations sharing the same commit/rollback boundary.
        return "saved:" + id;
    }
}
```

**This is an illustrative snippet** requiring annotation imports, `@EnableAsync`, `@EnableTransactionManagement`, an executor, and matching dependencies; `save` must perform real data operations for the transaction to be meaningful. The complete program in Section 6 includes all required pieces.

Advantage of two beans: `AsyncGateway.dispatch` runs on the worker, while the call to `worker.save` passes through **a different transaction proxy** and the transaction starts directly inside the worker. You do not have to rely on guessing advice ordering when placing both `@Async` and `@Transactional` on a single method.

## 4. `REQUIRED` or `REQUIRES_NEW`?

This is the most important point of the topic. Both propagation modes are often misunderstood as "default" vs "new thread", yet **both are transaction rules, not thread-creation policies**.

| State on the thread calling the `@Transactional` method | `REQUIRED` | `REQUIRES_NEW` |
| --- | --- | --- |
| **No existing transaction** on that thread | **Starts a new transaction**. | Also starts a new transaction. |
| **Existing transaction** on the same thread, same manager/resource | **Joins the existing transaction**; distinct logical scopes can share one physical transaction. | **Suspends** the existing transaction and creates an **independent** physical transaction. |
| When the inner method rolls back | If participating in an outer physical transaction, rollback-only can prevent the entire transaction from committing. | The new transaction rolls back on its own; the outer transaction can continue if business logic and exception handling allow. |
| Resources | Can share the connection already bound to the thread. | Usually needs a separate connection/resource while the outer resource remains held. |
| Does it create a new thread? | **No**. | **No**. |
| When used inside an `@Async` worker **that has no transaction of its own yet** | Opens a new transaction independent of the caller thread. | Also opens a new transaction; unnecessary merely to differ from the caller's transaction. |

If the caller has transaction A on thread 1 while `@Async` actually executes on thread 2 **with no transaction**, `@Transactional(propagation = REQUIRED)` on `TransactionalWorker` opens B. There is no need to force `REQUIRES_NEW` just to "escape the caller's transaction"; transaction A **was never propagated across threads**.

However, if **on the same worker thread** transaction B is already active and another bean must always commit an audit record independently of B, `REQUIRES_NEW` may be considered:

```java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(AuditRecord record) {
        auditRepository.insert(record);
    }
}
```

This is a **structural snippet** requiring `AuditRecord`, `auditRepository`, and imports. It must be invoked from **another bean/proxy**; calling `this.recordAttempt(...)` within the same class does not trigger transaction advice in proxy mode.

### Watch Out for Connection Pools and Deadlocks

`REQUIRES_NEW` on a thread that is already holding another transaction may require **an additional connection**, while the outer transaction's connection remains held. If N threads each hold N outer connections and wait for another connection for `REQUIRES_NEW`, a pool with only N connections can suffer starvation or deadlock. Spring recommends sizing the connection pool appropriately, typically larger than the number of concurrent transactional threads by at least one connection for this scenario.

For async work, a similar trap exists: the caller holds an open connection, **blocks on `future.get()`**, while the worker needs a connection from an exhausted pool. Do not pick "await async inside an open transaction" as a default production pattern.

### `NESTED` Is Not an Independent Transaction

`Propagation.NESTED` typically uses a **savepoint** within the same physical transaction (when supported by the transaction manager and resource, typically JDBC savepoints). A portion can roll back to the savepoint, yet the real commit still depends on the outer transaction. It does not mean the inner transaction commits independently like `REQUIRES_NEW`, nor does it transfer a transaction to a worker thread.

## 5. Characteristics of the New Transaction in the Worker

A method:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void process(JobId id) {
    repository.markRunning(id);
    repository.writeResult(id);
    repository.markSucceeded(id);
}
```

This is **structural code** requiring concrete types/repositories. If the method is invoked through a transaction proxy on a worker thread with no active transaction, all three operations share the same transaction; if step 2 throws an unhandled `RuntimeException`, the transaction typically rolls back, including the SQL already executed in step 1.

Key principles:

- The transaction starts **when the transaction interceptor is actually invoked** on the worker, not when the caller submits the work to the queue.
- While the worker waits in the executor queue, the caller's transaction may already have committed, rolled back, or finished before the worker begins.
- The transaction commits after the target `@Transactional` method returns normally through the transaction proxy. If an exception triggers a rollback per the rules, writes in that transaction are not committed.
- By default, Spring rolls back on `RuntimeException` and `Error`, and does not automatically roll back on all checked exceptions. You can configure `rollbackFor` (or matching project rules) when business logic requires it.
- If a method catches an exception, **swallows** it, and returns normally, transaction advice sees no exception and may commit. If rollback is required, rethrow the error or mark rollback-only at the proper boundary.
- An async `CompletableFuture` completing successfully does not by itself prove external systems processed a message or email; it only represents completion per the method contract.
- Keep transactions small; avoid long remote HTTP calls or unnecessarily long CPU work **inside a transaction**, as connections and locks can be held too long.

These principles apply to Spring imperative transactions. With R2DBC/reactive programming, study `ReactiveTransactionManager` and Reactor context separately; do not copy a transaction-bound `ThreadLocal` to another thread as a workaround.

## 6. Runnable Example: Caller Rolls Back, Worker Still Commits Its Own Transaction

This example uses **Java 17+**, Maven, **Spring Framework 6.2.12**, Spring JDBC, and in-memory H2. It demonstrates independence in a deliberate scenario:

1. `main` starts transaction A via `TransactionTemplate` and inserts a record into `caller_records`.
2. While transaction A **is still uncommitted**, `main` calls `AsyncGateway.enqueue(...)` through a Spring proxy.
3. On the `workExecutor` thread, the gateway verifies **transaction A is not bound**.
4. The gateway calls the `TransactionalWorker.save(...)` bean, where `@Transactional(REQUIRED)` opens its own transaction B and writes to **another table**, `worker_records`.
5. `main` waits for the worker to finish B, then marks transaction A for rollback.
6. Reading the database outside both transactions shows `caller_records` has no rows, while `worker_records` has one committed row.

**Why two tables?** The demo aims to show **transaction boundaries**, without introducing row locking from two threads modifying the same record. Choosing two tables makes the example less dependent on H2's locking strategy; in production you still need to evaluate locks, isolation, and connection pools.

### Directory Structure

```text
async-worker-transaction-demo/
├── pom.xml
└── src/main/java/example/AsyncWorkerTransactionDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>async-worker-transaction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.AsyncWorkerTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/AsyncWorkerTransactionDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class AsyncWorkerTransactionDemo {

    public record Receipt(
        boolean txAtAsyncStart,
        boolean txInsideWriter,
        String writerThread
    ) {
    }

    public static class TransactionalWorker {
        private final JdbcTemplate jdbc;

        public TransactionalWorker(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public Receipt save(String value, boolean txAtAsyncStart) {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();

            jdbc.update(
                "INSERT INTO worker_records(id, payload) VALUES (?, ?)",
                2, value
            );

            return new Receipt(
                txAtAsyncStart,
                active,
                Thread.currentThread().getName()
            );
        }
    }

    public static class AsyncGateway {
        private final TransactionalWorker writer;

        public AsyncGateway(TransactionalWorker writer) {
            this.writer = writer;
        }

        @Async("workExecutor")
        public CompletableFuture<Receipt> enqueue(String payload) {
            // Before calling writer, this worker has no transaction yet.
            boolean activeBeforeWriter =
                TransactionSynchronizationManager.isActualTransactionActive();

            // Call to another bean/proxy so @Transactional takes effect.
            Receipt saved = writer.save(payload, activeBeforeWriter);

            return CompletableFuture.completedFuture(saved);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_boundary_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("worker-");
            return pool;
        }

        @Bean
        public TransactionalWorker transactionalWorker(JdbcTemplate jdbc) {
            return new TransactionalWorker(jdbc);
        }

        @Bean
        public AsyncGateway asyncGateway(TransactionalWorker writer) {
            return new AsyncGateway(writer);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // Initialize schema outside the test transaction.
            jdbc.execute(
                "CREATE TABLE caller_records(" +
                "id INT PRIMARY KEY, payload VARCHAR(100))"
            );
            jdbc.execute(
                "CREATE TABLE worker_records(" +
                "id INT PRIMARY KEY, payload VARCHAR(100))"
            );

            PlatformTransactionManager manager =
                context.getBean(PlatformTransactionManager.class);
            TransactionTemplate tx = new TransactionTemplate(manager);
            AsyncGateway gateway = context.getBean(AsyncGateway.class);

            AtomicBoolean callerTransactionActive = new AtomicBoolean();
            AtomicReference<Receipt> receipt = new AtomicReference<>();

            tx.executeWithoutResult(status -> {
                callerTransactionActive.set(
                    TransactionSynchronizationManager
                        .isActualTransactionActive()
                );

                jdbc.update(
                    "INSERT INTO caller_records(id, payload) VALUES (?, ?)",
                    1, "will-rollback"
                );

                try {
                    // Wait for worker only to prove B commits before A rolls back.
                    receipt.set(
                        gateway.enqueue("worker-committed")
                            .get(10, TimeUnit.SECONDS)
                    );
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Interrupted while waiting for worker", ex
                    );
                } catch (ExecutionException | TimeoutException ex) {
                    throw new IllegalStateException(
                        "Worker failed or timed out", ex
                    );
                }

                // Intentionally roll back A.
                status.setRollbackOnly();
            });

            Receipt saved = receipt.get();
            int callerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM caller_records", Integer.class
            );
            int workerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM worker_records", Integer.class
            );

            System.out.println("callerTransactionActive="
                + callerTransactionActive.get());
            System.out.println("txAtAsyncStart=" + saved.txAtAsyncStart());
            System.out.println("txInsideWriter=" + saved.txInsideWriter());
            System.out.println("ranOnWorkerThread="
                + saved.writerThread().startsWith("worker-"));
            System.out.println("callerRowsAfterRollback=" + callerRows);
            System.out.println("workerRowsAfterCallerRollback=" + workerRows);
        }
    }
}
```

Run from the `async-worker-transaction-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

When the application runs successfully, **six lines printed by the program** in order:

```text
callerTransactionActive=true
txAtAsyncStart=false
txInsideWriter=true
ranOnWorkerThread=true
callerRowsAfterRollback=0
workerRowsAfterCallerRollback=1
```

### Explaining Each Verification Check

1. `TransactionTemplate` opens transaction A on the main thread; `TransactionSynchronizationManager.isActualTransactionActive()` returns `true`.
2. `main` inserts a row into `caller_records` without committing. `gateway.enqueue(...)` passes through the Spring async proxy to the `workExecutor` worker.
3. Inside `AsyncGateway` **before** calling `TransactionalWorker`, transaction A is not bound to the worker; `txAtAsyncStart=false`.
4. `writer.save(...)` is invoked through **a different transaction proxy**. Because the worker has no transaction yet, `Propagation.REQUIRED` starts B, so `txInsideWriter=true`.
5. `writer.save` inserts a row into `worker_records`. When the method finishes normally through the proxy, transaction B commits; `AsyncGateway` then completes the future.
6. `main` waited on the future with `get(10, SECONDS)` (only for the experiment), so we know B completed before A is marked for rollback.
7. `status.setRollbackOnly()` causes transaction A to roll back when `TransactionTemplate` finishes. The row in `caller_records` disappears; the row committed by B remains.
8. Because the pool prefix is `worker-`, `ranOnWorkerThread=true` and the worker genuinely differs from the main thread under this configuration.

**Warning:** The example deliberately lets the worker commit before the caller rolls back to prove independence. This is something you **should not** do if the worker's data depends on an order the caller's transaction has not committed yet. Waiting on `Future.get()` while holding a transaction on the caller can also cause connection exhaustion or deadlocks in real systems; the example uses two tables and `DriverManagerDataSource` (a fresh connection per acquisition) to isolate the lesson from pool limits.

`DriverManagerDataSource` works for a simple illustration, **not as a production connection pool**. Real applications typically use a bounded pool that must be sized for both open caller transactions and concurrent workers. With multiple services, identify which transaction manager controls each DataSource.

## 7. What Happens If the Worker Fails?

When `TransactionalWorker.save(...)` throws an unhandled `RuntimeException`:

```text
AsyncGateway worker thread
     |
     +-- call TransactionalWorker proxy
               |
               +-- BEGIN B
               +-- update SQL
               +-- RuntimeException
               +-- ROLLBACK B
     |
     +-- future caller completed exceptionally
```

A method might look like:

```java
@Transactional
public void writeTwoRows() {
    repository.insertFirst();
    repository.insertSecond(); // may throw an exception
}
```

This is a snippet requiring real repositories. If the second insert throws an unchecked exception, Spring transaction advice normally rolls back both operations within the same physical transaction. If the exception is **caught and swallowed** inside the method, transaction advice sees a normal return and may commit; logging the error alone does not trigger an automatic rollback.

By default `@Transactional` rolls back on unchecked exceptions (`RuntimeException`) and `Error`, not automatically on all checked exceptions. If policy requires rolling back on business checked exceptions as well, configure:

```java
@Transactional(rollbackFor = Exception.class)
public void process(...) throws Exception {
    // ...
}
```

This pattern is a **signature illustration** whose parameters and body must be replaced for your business logic; it is not standalone code. Rollback rules should be narrow enough not to turn every conditional error into an unintended rollback.

With `@Async` returning `CompletableFuture<T>`, the caller can observe failures via `get()` (typically `ExecutionException`), `join()` (typically `CompletionException`), or `whenComplete`/`handle`. Do not discard the Future if the work must be tracked to completion.

If the executor **rejects the submission** because the queue is full or it has shut down, the error can occur before a valid future exists; that is not equivalent to rolling back transaction B, since B may never have started.

## 8. Proxy Pitfall: Self-Invocation in the Same Bean Does Not Open a New Transaction

Both `@Transactional` and `@Async` rely on AOP proxies in standard mode. If a single bean contains:

```java
@Service
class SameBean {
    public void outer() {
        this.inner(); // self-invocation: bypasses the transaction proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Intended to open an independent transaction.
    }
}
```

This is an illustrative class snippet without full imports/implementation. In proxy mode, calling `this.inner()` is a **direct Java call on the target object**, bypassing the proxy; `REQUIRES_NEW` is not automatically applied to that invocation. If an outer transaction is active, the inner code may continue running in the old transaction; if no transaction exists, it may run without any transaction at all.

The clean solution: extract `inner` into another Spring bean, inject a reference to that bean, and call it through the container-provided reference. For very small blocks of code, you can use `TransactionTemplate` inside the method to control scope via an explicit API.

Do not call an `@Async` method via `this` expecting it to switch threads; if it executes synchronously on the caller, both the observation "the transaction did not propagate" and latency numbers lose their intended meaning.

### What About Putting Both `@Async` and `@Transactional` on One Method?

It can work depending on advice/proxy order and application configuration. However, it is **harder to observe** which part moved to the worker, which thread opened the transaction, and when commits occur — especially alongside `@Retryable`, security, `@Cacheable`, or layered proxies.

When the goal is to make a new transaction on the worker explicit, two beans such as `AsyncGateway` and `TransactionalWorker` clarify responsibilities: async advice belongs to the gateway, transaction advice belongs to the worker. This is a design recommendation for easy verification, not a claim that Spring completely forbids both annotations on the same method.

## 9. Transactions and Events: Do Not Process Before the Caller Commits

A common bug:

```java
@Transactional
public void createOrder(Command command) {
    repository.insertOrder(command);
    asyncGateway.startShipping(command.orderId());
}
```

This snippet assumes suitable repository, command, and gateway types. `startShipping` may run **before the order-creation transaction commits**. If the caller rolls back, the worker may still create a shipping record; if the worker queries the database on a separate connection, it may fail to see the uncommitted order.

**Solution when you only want post-commit processing:** publish a domain event inside the caller transaction and use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` so it triggers only after a successful commit.

Architectural example with separate beans:

```java
public record OrderCreated(long orderId) {
}

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(ApplicationEventPublisher publisher,
                        OrderRepository repository) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void createOrder(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}

@Component
public class OrderCommittedListener {
    private final AsyncOrderProcessor asyncProcessor;

    public OrderCommittedListener(AsyncOrderProcessor asyncProcessor) {
        this.asyncProcessor = asyncProcessor;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        asyncProcessor.processAsync(event.orderId());
    }
}

@Service
public class AsyncOrderProcessor {
    private final OrderWorker worker;

    public AsyncOrderProcessor(OrderWorker worker) {
        this.worker = worker;
    }

    @Async("orderExecutor")
    public CompletableFuture<Void> processAsync(long orderId) {
        worker.processCommittedOrder(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class OrderWorker {
    @Transactional(propagation = Propagation.REQUIRED)
    public void processCommittedOrder(long orderId) {
        // Read the committed order and update worker data.
    }
}
```

**This is an application code sketch**, not a standalone Java file. Full repositories, imports, executor configuration, `@EnableAsync`, and `@EnableTransactionManagement` are needed. The main point: the post-commit listener **dispatches the task to another async bean**, while the data method inside the worker **opens its own transaction** when executed.

`@TransactionalEventListener` defaults to the `AFTER_COMMIT` phase. When an event is published **without an active transaction**, the listener is not invoked by default (unless `fallbackExecution = true` is configured); verify this if there are code paths publishing events outside transactions.

### Why Care About Transactions in an AFTER_COMMIT Listener?

Spring notes that after a transaction has completed, certain transactional resources may **still remain bound/accessible** during the callback phase. If a listener running synchronously on the same thread **performs database writes directly** after commit, those writes may join the old resource context without a subsequent commit as expected. For writes that must reliably commit inside a synchronous listener, you usually need to delegate to another `@Transactional(REQUIRES_NEW)` bean called through a proxy.

In the pattern above, the listener does **not** write to the database directly: it hands off work via an executor to another worker thread, where `@Transactional(REQUIRED)` opens a new transaction. Even then, remember that async dispatch can fail and does not guarantee the work will definitely be processed.

### AFTER_COMMIT Alone Does Not Guarantee Durability

`@TransactionalEventListener(AFTER_COMMIT)` is a way to pick **execution timing relative to the current transaction**, not a durable queue. The process can crash **after the order commits but before the task is submitted**, or while the task sits in an in-memory queue before finishing. If "every committed order will eventually be processed" is mandatory, you need a transactional outbox, durable queue, or job persistence with retries and idempotency.

## 10. Transactional Outbox When Both Source Atomicity and Background Processing Are Required

For critical workflows, the caller's transaction should write both the primary data and an **outbox record** inside the same physical transaction:

```text
Caller transaction A
   |
   +-- INSERT order
   +-- INSERT outbox_event(order-created, orderId, eventId)
   |
   +-- COMMIT A
         |
         v
Outbox dispatcher (independent process)
   |
   +-- reads committed outbox records
   +-- publishes or dispatches processing
   +-- retries/acks per policy
         |
         v
Worker receiving event
   |
   +-- BEGIN transaction B
   +-- idempotent handling by eventId
   +-- updates worker state
   +-- COMMIT B
```

If A rolls back, both the order and the outbox event roll back. If A commits, the outbox event remains in the database for the dispatcher to recover after a crash. The system may deliver duplicates during retries, so the worker needs idempotency via `eventId`, unique constraints, or an equivalent protocol.

An outbox does **not** create a distributed ACID transaction between the database and the broker; it shifts the problem to retryable delivery and deduplication. This is usually a better trade-off than holding a transaction across multiple threads, remote systems, or in-memory queues.

## 11. Waiting for a Future Inside a Transaction: Easy Connection Exhaustion and Locks

In the main example, the caller intentionally calls `future.get(...)` **while transaction A is still open** to demonstrate B committing followed by A rolling back. Do not copy that pattern directly into production.

A dangerous scenario:

```text
Caller thread 1..N:
  BEGIN A; holds DB connection 1..N
  submits @Async work
  Future.get() waits for worker to finish

Worker thread:
  @Transactional needs a new connection
  DB pool only has N connections, all held by callers
  -> worker waits for connection
  -> caller waits for worker
  -> starvation / deadlock
```

Even with enough pool connections, the worker may wait on a **row lock** held by the caller while the caller waits on the worker, causing a transaction-level deadlock. Splitting threads does not eliminate data contention.

Ways to reduce risk:

- Avoid waiting on a `Future` inside a transaction unless strictly necessary; commit before dispatching work that depends on that data.
- For post-commit work, use an `AFTER_COMMIT` listener or a durable outbox depending on requirements.
- Bound executor concurrency/queue size, DB/HTTP timeouts, lock timeouts, and retry budgets.
- Monitor busy/waiting DB connections, worker counts, queue lengths, transaction durations, and lock waits.
- With `REQUIRES_NEW`, provision extra connections when outer transactions hold connections; do not treat raising max pool threads as a solution if the DB is already saturated.

## 12. Timeout, Cancellation, and Rollback Are Not the Same Thing

Suppose the caller receives a `CompletableFuture<Result>` from an async gateway:

```java
Result value = gateway.runAsync(id).get(2, TimeUnit.SECONDS);
```

This is a snippet inside a method handling checked exceptions. `get(timeout)` only bounds **how long the caller waits for the result**. If it throws `TimeoutException`, the worker may still be running, and transaction B might not have started yet, might be open, or might already have committed.

Conclusions you **must not draw** after a timeout:

- "The worker definitely rolled back": false; the worker may still be running normally.
- "The caller rolled back so the worker also rolled back": false, if B is independent.
- "`Future.cancel(true)` definitely interrupts JDBC and rolls back": false; cancellation/interruption depends on the future, JDBC driver, and cooperative code.
- "Retrying is safe": false; the old task may already have committed with its result arriving late.

For operations with side effects, you must have an **idempotency key** or verifiable state data. If a caller times out and retries an `INSERT` lacking a unique constraint, the worker can create duplicate records. A `CompletableFuture` is only a completion handle, not proof of exactly-once execution.

Place timeouts where waiting actually happens: connection acquisition timeout, query timeout, HTTP connect/read timeout, lock timeout, and job deadlines. Avoid long transactions and avoid holding locks across unexpected network I/O.

## 13. Exceptions and Rollbacks Across Multiple Transactions

| Scenario | Transaction A on caller | Transaction B on worker |
| --- | --- | --- |
| A rolls back **before** the worker starts | A rolls back | B can still start afterward if the task was already submitted, unless prevented by a guard. |
| A rolls back **after** B commits | A rolls back | B remains committed unless business rules or database constraints prevent it. |
| B rolls back due to exception while A is still running | A can commit or roll back per its own logic. | B rolls back its writes. |
| A commits, B fails | A remains committed. | B rolls back; needs retry/compensation if business logic requires it. |
| Task is rejected before the worker runs | Depends on whether caller throws/rolls back or continues. | B was never opened. |
| Caller times out while waiting | A may continue or roll back per handler. | B may be running and later commit or roll back. |

On the same thread when **REQUIRED joins transaction A**, marking an inner logical scope rollback-only can cause A to roll back and trigger `UnexpectedRollbackException` if the caller expected to commit. With two independent threads as in the example, there is no automatic cross-transaction rollback-only relationship; coordination must happen via domain workflow rather than treating two proxies as one global transaction.

If multiple steps require reversible states, consider sagas/compensation at the business level. Compensation is **a new action** to undo a committed effect, not a physical rollback of the old transaction.

## 14. Configuration and Reminders for JPA

The example uses `JdbcTemplate` so the transaction manager behavior is clear. With JPA, you can use `JpaTransactionManager`, repositories, or a container-managed `EntityManager`. However:

- An `EntityManager` bound to a persistence context/transaction is usually **not thread-safe** to pass wholesale to an async worker.
- Lazy-loaded entities from the caller may no longer have a valid session when the worker accesses them; do not pass unmaterialized entity objects as arbitrary transport payloads.
- Pass IDs or immutable DTOs to the worker, then **reload** the entity inside the worker's transaction B. You may need to verify the record has committed and handle optimistic locking/version conflicts.
- `@Transactional(readOnly = true)` is a hint/configuration for the framework, not a mechanism that guarantees zero writes on every database.
- If multiple transaction managers exist (JDBC/JPA/multi-DataSource), specify the right manager — e.g. `@Transactional(transactionManager = "ordersTransactionManager")` — and ensure the repository actually participates in that manager.
- Do not keep transactions open across HTTP calls just for JPA lazy loading: define clear data-access boundaries and design appropriate fetch graphs or DTOs.

A worker method processing an entity after commit may need `@Transactional(REQUIRED)` to load and update state. Only when **another transaction already exists on the same worker thread** and business rules demand an independent commit should you consider `REQUIRES_NEW` along with all its connection and error consequences.

## 15. Alternative Using TransactionTemplate

Not every boundary must be declared via annotations. When transaction start/end logic needs to be controlled around a code block inside a worker, `TransactionTemplate` expresses it explicitly:

```java
public class TransactionalJobRunner {
    private final TransactionTemplate txTemplate;
    private final JdbcTemplate jdbc;

    public TransactionalJobRunner(PlatformTransactionManager txManager,
                                  JdbcTemplate jdbc) {
        this.txTemplate = new TransactionTemplate(txManager);
        this.jdbc = jdbc;
    }

    public String runJob(long jobId) {
        return txTemplate.execute(status -> {
            jdbc.update("UPDATE jobs SET status = ? WHERE id = ?",
                        "DONE", jobId);
            return "done:" + jobId;
        });
    }
}
```

This is an **illustrative class template**, not a standalone program since it requires the `jobs` schema, imports, and integration into a Spring bean/executor. When called from a worker thread, `txTemplate.execute(...)` creates/joins a transaction using `TransactionTemplate`'s default propagation (REQUIRED). It does not need an `@Transactional` proxy on `runJob`, because the template itself manages the transaction.

Still, `TransactionTemplate` does **not** make code run asynchronously. You still need an executor or `@Async` to switch threads. Choosing programmatic vs declarative transactions depends on clarity and project conventions, not as a mechanism to "fix" automatic transaction propagation across threads.

## 16. Common Mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| "The caller's transaction automatically follows an `@Async` worker." | Imperative transactions are bound to the caller thread. | Open a worker transaction if needed and independence is allowed. |
| "Having `@Async` gives the worker a transaction automatically." | An executor only runs tasks; it does not start JDBC transactions. | Call a `@Transactional` bean via proxy or use a template. |
| "Must use `REQUIRES_NEW` because the worker is a different thread." | The worker has no transaction A to suspend; REQUIRED also opens a new transaction. | Pick propagation based on the transaction **already on the worker**. |
| "`REQUIRES_NEW` starts a new thread." | It swaps physical transactions, not executors. | Separate transaction boundaries from execution threads. |
| "Putting `@Transactional` on `this.inner()` opens a new tx." | Self-invocation bypasses proxy mode. | Call another bean or use `TransactionTemplate`. |
| "If the caller rolls back, all worker writes roll back too." | Independent transaction B has its own commit. | Choose independence only when business permits; consider after-commit/outbox. |
| "Submitting the worker right after insert lets it see the record." | Caller may not have committed; isolation and locks govern visibility. | Dispatch after commit or use an outbox. |
| "Waiting on a Future inside a transaction is safe." | Can hold connections/locks while waiting on a worker needing those resources. | Avoid blocking; commit first, size pools and timeouts properly. |
| "`REQUIRES_NEW` has no resource cost." | The outer transaction typically keeps its connection while the inner needs another. | Size pools and evaluate contention/deadlocks. |
| "`NESTED` commits independently." | Usually a savepoint within the same physical transaction. | Use `REQUIRES_NEW` only when an independent physical transaction is needed. |
| "`AFTER_COMMIT` events survive crashes automatically." | In-memory listeners/queues can lose work. | Use a transactional outbox or durable broker when needed. |
| "Catching an exception and returning normally still rolls back." | Transaction advice sees success and may commit. | Rethrow or call `setRollbackOnly` per rules. |
| "Future timeout/cancel rolls back the DB." | Completion/cancellation does not prove the transaction stopped. | Use real I/O timeouts, idempotency, and job state tracking. |
| "You can share an EntityManager from caller to worker." | Persistence contexts are not thread-safe across workers. | Pass IDs/DTOs and load inside the worker's transaction. |

## 17. Checklist When Designing an Async Transactional Workflow

1. **Does business logic allow independence?** If A rolls back, may B stay committed? If not, do not create B prematurely.
2. **When is the source data readable?** Has it committed? Are there locks, isolation rules, or version conflicts to handle?
3. **Which thread/executor does the worker use?** Is it called via a Spring proxy, or is there self-invocation?
4. **Where is the transactional bean?** Is there a `TransactionalWorker` called via proxy on the worker, or a `TransactionTemplate` wrapping the data block?
5. **Which propagation?** If the worker has no tx, REQUIRED creates a new one; only if a tx already exists should you decide between joining or independent `REQUIRES_NEW`.
6. **Which manager/resource?** Does the TransactionManager manage the right DataSource/JPA context?
7. **Timeouts/retries/cancellation?** A Future timeout does not roll back; a task might commit late, so ensure idempotency.
8. **Are you waiting on the worker inside the outer transaction?** Check connection pool/lock deadlocks — usually avoid doing so.
9. **Can the task be lost?** If it depends on A committing and must eventually execute, use an outbox or durable job store.
10. **Is observability in place?** Queue wait, tx duration, DB connections, rollback rate, retry/dead-letter metrics, and domain correlation IDs.
11. **Have exception/rollback rules been tested?** Runtime vs checked, caught exceptions, rollback-only, and async completion.
12. **Is security/context carried safely?** Do not copy transaction ThreadLocals; pass required immutable metadata and re-authenticate when appropriate.

## 18. Self-Check Questions

**1.** Caller has transaction A and calls an `@Async` method. Does the worker automatically join transaction A?

**Answer:** No, for thread-bound imperative transactions. If the worker needs a transaction, transaction advice invoked on the worker must create or join a transaction on the worker itself.

**2.** On a worker with no active transaction, does `@Transactional(propagation=REQUIRED)` open a new transaction?

**Answer:** Yes. REQUIRED creates a new transaction when none exists on the relevant thread, so `REQUIRES_NEW` is not needed merely to differ from the caller's transaction on another thread.

**3.** When does `REQUIRES_NEW` differ most clearly from REQUIRED?

**Answer:** When a transaction already exists on **the same thread**. REQUIRED normally joins the existing physical transaction; REQUIRES_NEW suspends it and opens a separate physical transaction, using different resources and committing/rolling back independently.

**4.** In the demo, why is `callerRowsAfterRollback=0` while `workerRowsAfterCallerRollback=1`?

**Answer:** The caller wrote in A and marked it rollback-only. The worker opened B on another thread, wrote to the worker table, and committed before A rolled back; A does not automatically roll back B.

**5.** Why did the demo invoke `AsyncGateway` and `TransactionalWorker` via two separate beans?

**Answer:** So `@Async` advice moves the invocation to the worker first, and then the `@Transactional` proxy of the other bean opens the transaction on the worker; this avoids self-invocation and reduces advice-ordering confusion.

**6.** Caller inserts an uncommitted order and submits a worker to ship the order. Is the worker guaranteed to see the order?

**Answer:** No. The worker uses its own connection/transaction and depends on isolation/locks; dispatch only after commit or use an outbox when work is tied to a committed order.

**7.** Is `@TransactionalEventListener(AFTER_COMMIT)` enough to guarantee tasks are not lost across crashes?

**Answer:** Not yet. It selects callback timing relative to the transaction, not a durable broker. To guarantee crash recovery, persist the work/outbox inside the source transaction and use retries with idempotency.

**8.** A synchronous listener in the AFTER_COMMIT phase writes directly to the database inside the listener method; what might it need?

**Answer:** Resources from the just-committed transaction may still be bound during the callback. If a write needs its own commit, call another `@Transactional(REQUIRES_NEW)` bean through a proxy, or offload to an async worker with an appropriate new transaction.

**9.** `Future.get(2, SECONDS)` times out. Does that prove the worker transaction rolled back?

**Answer:** No. Only the caller's wait budget expired; the worker may still be running and commit afterward. You need idempotency and proper I/O/transaction timeouts.

**10.** Can the worker directly use the caller's `EntityManager` or JDBC connection?

**Answer:** It should not. Resources bound to a transaction/thread are not designed to be shared across workers; pass IDs/DTOs and acquire separate resources inside the worker's transaction.

### Key Takeaway

When **business logic permits an independent unit of work**, let the processing bean open a transaction on **the thread actually executing the work**: `@Async` via proxy to the worker, then invoke another bean with `@Transactional(REQUIRED)` or use `TransactionTemplate`. Only when the worker already has a transaction and needs **an independent physical transaction** should you consider `REQUIRES_NEW` along with its connection cost. If work is only valid after the caller commits, use a **post-commit** mechanism; if work must survive crashes, consider a **transactional outbox**. Do not use transaction annotations as a way to "stitch" ACID across threads.

### Official References

- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): thread-bound transactions in the imperative model and proxy mechanics.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW, NESTED, and resources/connections.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, AFTER_COMMIT, and callback boundaries.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executors, proxy mode.
- [Spring Framework — TransactionTemplate](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): programmatic transaction management.
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): thread-bound transaction state and resources.
