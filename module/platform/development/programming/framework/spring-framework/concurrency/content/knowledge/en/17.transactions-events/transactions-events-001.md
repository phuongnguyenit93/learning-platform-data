# Regular Thread-Bound Transactions Do Not Propagate Automatically Into @Async Tasks

## 1. The Phenomenon: Caller Has @Transactional, Yet Worker Is Not in the Same Transaction

In a Spring application, we might create data inside a `@Transactional` method and then dispatch another piece of work using `@Async`:

```java
@Transactional
public void registerOrder(long orderId) {
    orderRepository.save(new Order(orderId));
    mailWorker.sendConfirmation(orderId); // @Async method on another bean.
}
```

This is an **illustrative fragment**: `Order`, `orderRepository`, and `mailWorker` are hypothetical application components. Many people assume that because `sendConfirmation()` is called *inside* a `@Transactional` method, it will join the open transaction of `registerOrder()`. In Spring's standard imperative transaction model, that reasoning is **wrong**.

When invoked through a Spring async proxy, `@Async` hands off the work to a worker thread. The caller's transaction is bound to the **thread executing the transactional call**; it is not copied intact to the new worker. The consequences can include:

- The caller has an active transaction, yet inside the worker `TransactionSynchronizationManager.isActualTransactionActive()` returns `false` if the worker does not open a transaction of its own.
- The worker uses a different JDBC connection and cannot see the record the caller just inserted but has **not yet committed**, under an isolation level such as `READ_COMMITTED`.
- If the worker has its own `@Transactional`, it may open **an independent transaction** on the worker; that is **not** the caller's transaction.
- The worker may send an email or persist its own data successfully while the caller's transaction **later rolls back**.
- If the caller waits for the worker's Future before committing, it can introduce timing dependencies or even a business deadlock when the worker tries to wait for uncommitted data.

**Foundational rule:** `@Transactional` in imperative Spring is a **thread-bound** transaction context. `@Async` normally switches the execution thread. Switching threads **does not automatically carry over the caller's transaction**.

## 2. How Does Spring's Imperative Transaction Bind to a Thread?

### 2.1. Transaction Manager and Resource Binding

In JDBC, Spring typically uses a `PlatformTransactionManager` such as `DataSourceTransactionManager`. When a call passes through a transactional interceptor:

1. The transaction manager obtains/starts a transaction according to propagation rules and current status.
2. Spring binds the transaction metadata and appropriate resources — typically including a `ConnectionHolder` for the `DataSource` — to the current thread via `TransactionSynchronizationManager`.
3. `JdbcTemplate`/DAO calls participate in the transaction when running on that thread and using the matching resource/transaction manager.
4. When the transactional call completes, Spring commits or rolls back according to its rules, and then cleans up the corresponding resource bindings.

This thread-bound nature allows different repositories/DAOs to participate in the same transaction without passing a `Connection` through every Java parameter. However, it also creates a **thread boundary**: a task running on another thread does not have those bindings by default.

```text
Thread HTTP / caller                         Worker thread (executor)
--------------------                         ------------------------
@Transactional proxy begins T1
  |
  +-- bind T1 connection to caller thread
  |
  +-- JDBC INSERT row #1 (uncommitted)
  |
  +-- invoke @Async proxy ----------------> submit task to executor
  |                                         |
  |                                         +-- worker begins
  |                                         +-- no caller T1 binding
  |                                         +-- JDBC query via own connection
  |                                         +-- might NOT see uncommitted #1
  |
  +-- continue and commit/rollback T1
  |
  +-- unbind caller transaction
```

An accurate observation: the worker can receive ordinary values such as `orderId` because they are passed as arguments, yet it **does not receive ownership of the open transaction/connection** merely by passing arguments.

### 2.2. What Can TransactionSynchronizationManager Inspect?

Two common diagnostic methods:

- `TransactionSynchronizationManager.isActualTransactionActive()`: reports whether an actual transaction is marked active on the current thread.
- `TransactionSynchronizationManager.isSynchronizationActive()`: reports whether transaction synchronization is active for the thread; this is not strictly synonymous with an active physical transaction.

In the example, `isActualTransactionActive()` is used because we want to compare **the caller being inside a transaction** against **the worker not inheriting the transaction**. This is a useful signal, though it does not replace checking the transaction manager, connection, isolation, and actual data.

**Do not pass or forcibly bind Connection/TransactionSynchronizationManager state directly from caller to worker** to "share a transaction". A JDBC `Connection` or Hibernate `Session` is normally not designed for concurrent manipulation by two threads; forcing resource sharing can cause races and violate lifecycle and consistency guarantees.

### 2.3. Exception: Reactive Transactions Do Not Use the Same Mechanism

With `ReactiveTransactionManager`, Spring manages transactions using the **Reactor Context**, not the `ThreadLocal` of the imperative `PlatformTransactionManager` model. Reasoning and propagation then follow the reactive pipeline/context, so one cannot take the rule "every transaction in Spring is thread-bound" and apply it to reactive code.

This article focuses on **Spring imperative transactions + @Async + JDBC/JPA**. When reading reactive documentation, keep the two transaction models distinct.

## 3. What Boundary Does @Async Actually Create?

Spring supports `@Async` through async advice and an executor. Under the default proxy configuration:

- With `@EnableAsync` (or `<task:annotation-driven>`), Spring registers the infrastructure to process the annotation.
- The method must reside on a Spring-managed bean, with a qualifying call going **through the proxy**.
- Async advice submits the invocation to an executor, such as `ThreadPoolTaskExecutor`.
- The target method body runs on a worker provided by the executor. At that point, the **initial calling thread's** transaction bindings **do not automatically appear** on the worker.

It is especially important to distinguish three situations:

| Situation | Does it switch threads? | Is the caller's transaction automatically inherited? |
| --- | --- | --- |
| Caller calls an `@Async` method on **another bean through a proxy** and the executor is truly asynchronous | Yes | No |
| Caller calls `this.asyncMethod()` on itself within the same target in proxy mode | Usually no: bypasses async advice | Code runs synchronously on the caller itself, so it may *see the caller's transaction*; this does not prove propagation works |
| Actual executor is `SyncTaskExecutor`, executing directly on the calling thread | No | May see the existing thread-bound transaction because there is no thread switch; that is not an independent async worker |

This is why you should not diagnose transaction propagation solely from the presence or absence of the `@Async` annotation. You must verify the **call path**, **actual executor**, **thread name**, and **transaction state**.

## 4. Commit Timing Determines What Data the Worker Sees

Suppose the caller does:

```text
T1 begins
  INSERT order id=1  (uncommitted)
  call worker.inspect(1) via @Async
  worker queries by id=1
  T1 commits after @Transactional method returns
```

If the DB uses `READ_COMMITTED` isolation, a worker reading through an independent transaction/connection typically **does not see** the row just inserted by T1 prior to commit.

Two things to understand:

1. `@Async` makes no promise to "run **after commit**". The worker may start before commit, after commit, or just as the caller is about to roll back — depending on scheduling.
2. Whether uncommitted data is visible depends on isolation, the DB engine, and the operation type. Do not assume **every database and every isolation level** produces the same result; this example deliberately uses H2's default `READ_COMMITTED` to illustrate not seeing an uncommitted row.

A very common race condition: async work depends on a record just saved in the caller. On a developer machine, the worker occasionally runs after commit and everything "appears to work"; in production, the worker is faster and the query returns empty. Adding `Thread.sleep(100)` in the worker only hides the race; it does not enforce proper transactional ordering.

### 4.1. Execution Time Does Not Mean Commit Order

Even if the caller method calls `asyncService.run()` *after* `repository.save()` in the same source code, the caller's transaction may still remain uncommitted until the transactional method **returns through the proxy**. Therefore, Java statement order does not guarantee the worker can see data from that transaction.

### 4.2. Waiting on a Future Inside a Transaction Can Make Things Worse

If the caller keeps a transaction open and immediately calls `future.get()` to wait for a worker while the worker waits for data the caller has yet to commit, the system can make very slow progress or even deadlock:

```text
Caller: holds T1 -> waits worker Future -> only after method returns can T1 commit
Worker: waits for data/lock held by T1 -> cannot finish Future
```

Do not try to solve this problem by scaling the thread pool indefinitely. Fix the **transaction boundaries**, the ordering of event emission/work dispatch, and how the task receives its data.

## 5. A Worker Without a Transaction Differs From a Worker With Its Own Transaction

There are two completely different possibilities:

### 5.1. An @Async Worker Without @Transactional

```java
@Async("workerExecutor")
public CompletableFuture<Integer> countRows(int id) {
    int count = jdbc.queryForObject(
            "select count(*) from items where id = ?",
            Integer.class, id);
    return CompletableFuture.completedFuture(count);
}
```

This is a fragment on a Spring-managed bean that already has `JdbcTemplate jdbc` and an executor. Inside the worker, `isActualTransactionActive()` may be false. The JDBC query still executes using its own connection, typically under the JDBC/driver's auto-commit behavior. This does not mean every operation is automatically "safe" or sharing the caller's transaction.

### 5.2. An @Async Worker That Also Has @Transactional

```java
@Async("workerExecutor")
@Transactional(readOnly = true)
public CompletableFuture<Integer> countRowsInOwnTransaction(int id) {
    int count = jdbc.queryForObject(
            "select count(*) from items where id = ?",
            Integer.class, id);
    return CompletableFuture.completedFuture(count);
}
```

When the call passes through advice properly, the task runs on the worker and transaction advice can open **a new transaction on that worker**. It has an active transaction state, yet **still does not participate in the caller's uncommitted transaction**.

Do not interpret `Propagation.REQUIRED` as "find the transaction of whichever thread called me". `REQUIRED` only joins an appropriate transaction **already existing in the current execution context**; if the worker has no thread-bound transaction, it starts a new transaction.

With `Propagation.REQUIRES_NEW` in a worker, it also starts an independent transaction; there is no need to use `REQUIRES_NEW` merely to force transaction creation for every async method when the worker has no pre-existing transaction. Suspending an existing transaction is only relevant when the **current thread** actually has a transaction for propagation to handle.

### 5.3. Two Independent Transactions Can Produce Different Outcomes

If the worker saves a row and commits its own transaction while the caller subsequently rolls back, the worker's row may **still exist**. Conversely, a worker reading the caller's uncommitted data may still not see it even though the worker itself is inside a new transaction.

Therefore, adding `@Transactional` to the worker is not a way to "propagate" the original transaction. It only defines the transaction boundary for the worker's own work.

## 6. Runnable Example: Spring @Transactional + @Async + H2 Verifying the Difference

The example uses **Java 21, Spring Framework 6.2.1, Spring JDBC, H2 2.3.232, and Maven**. Spring Boot is not required.

It demonstrates simultaneously:

1. A `@Transactional` caller method inserts a row and **has not yet committed**.
2. An `@Async` worker without a declared transaction reads that row: the worker lacks the caller's transaction and does not see uncommitted data.
3. An `@Async @Transactional(readOnly = true)` worker has **its own transaction**, yet still does not see the uncommitted row.
4. After the caller commits, a `@TransactionalEventListener(phase=AFTER_COMMIT)` combined with `@Async` runs and sees the committed row.
5. When the caller throws an exception and rolls back, the row does not exist, and the `AFTER_COMMIT` listener for the event in the rolled-back transaction is not invoked.

To avoid guessing with `Thread.sleep()`, the program calls `Future.get(timeout)` for the two worker queries and uses a `CountDownLatch` to await the post-commit listener.

### 6.1. Structure

```text
tx-async-demo/
├── pom.xml
└── src/main/java/demo/TxAsyncDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>tx-async-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.TxAsyncDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**File `src/main/java/demo/TxAsyncDemo.java`:**

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
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
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TxAsyncDemo {
    public record Observation(boolean txActive, int visibleRows, String thread) {}
    public record Comparison(boolean callerTxActive, Observation asyncNoTx,
                             Observation asyncOwnTx) {}
    public record ItemCreated(int id) {}

    public static class Reader {
        private final JdbcTemplate jdbc;

        public Reader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("workerExecutor")
        public CompletableFuture<Observation> withoutTransaction(int id) {
            return CompletableFuture.completedFuture(sample(id));
        }

        @Async("workerExecutor")
        @Transactional(readOnly = true)
        public CompletableFuture<Observation> withOwnTransaction(int id) {
            return CompletableFuture.completedFuture(sample(id));
        }

        private Observation sample(int id) {
            int count = jdbc.queryForObject(
                    "select count(*) from items where id = ?",
                    Integer.class, id);
            return new Observation(
                    TransactionSynchronizationManager.isActualTransactionActive(),
                    count,
                    Thread.currentThread().getName());
        }
    }

    public static class Writer {
        private final JdbcTemplate jdbc;
        private final Reader reader;
        private final ApplicationEventPublisher publisher;

        public Writer(JdbcTemplate jdbc, Reader reader,
                      ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.reader = reader;
            this.publisher = publisher;
        }

        @Transactional
        public Comparison insertAndObserve() throws Exception {
            jdbc.update("insert into items(id, label) values (?, ?)", 1, "one");
            boolean callerTx =
                    TransactionSynchronizationManager.isActualTransactionActive();

            Observation noTx = reader.withoutTransaction(1)
                    .get(5, TimeUnit.SECONDS);
            Observation ownTx = reader.withOwnTransaction(1)
                    .get(5, TimeUnit.SECONDS);

            publisher.publishEvent(new ItemCreated(1));
            return new Comparison(callerTx, noTx, ownTx);
        }

        @Transactional
        public void insertAndRollback() {
            jdbc.update("insert into items(id, label) values (?, ?)", 2, "two");
            publisher.publishEvent(new ItemCreated(2));
            throw new IllegalStateException("demo rollback");
        }
    }

    public static class AfterCommitListener {
        private final JdbcTemplate jdbc;
        private final CountDownLatch committedEvent = new CountDownLatch(1);
        private final AtomicInteger observedAfterCommit = new AtomicInteger(-1);
        private final AtomicInteger unexpectedRollbackEvent = new AtomicInteger();
        private final AtomicReference<String> listenerThread =
                new AtomicReference<>("");

        public AfterCommitListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("workerExecutor")
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCreated(ItemCreated event) {
            if (event.id() == 1) {
                observedAfterCommit.set(jdbc.queryForObject(
                        "select count(*) from items where id = ?",
                        Integer.class, event.id()));
                listenerThread.set(Thread.currentThread().getName());
                committedEvent.countDown();
            } else if (event.id() == 2) {
                unexpectedRollbackEvent.incrementAndGet();
            }
        }

        public boolean awaitCommitted() throws InterruptedException {
            return committedEvent.await(5, TimeUnit.SECONDS);
        }

        public int observedCount() {
            return observedAfterCommit.get();
        }

        public int rollbackEventCount() {
            return unexpectedRollbackEvent.get();
        }

        public String listenerThread() {
            return listenerThread.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:tx_async_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("tx-worker-");
            return pool;
        }

        @Bean
        public Reader reader(JdbcTemplate jdbc) {
            return new Reader(jdbc);
        }

        @Bean
        public Writer writer(JdbcTemplate jdbc, Reader reader,
                             ApplicationEventPublisher publisher) {
            return new Writer(jdbc, reader, publisher);
        }

        @Bean
        public AfterCommitListener afterCommitListener(JdbcTemplate jdbc) {
            return new AfterCommitListener(jdbc);
        }
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Transaction/thread behavior not as expected");
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            Writer writer = context.getBean(Writer.class);
            AfterCommitListener listener =
                    context.getBean(AfterCommitListener.class);

            jdbc.execute("create table items(id int primary key, label varchar(50))");
            Comparison c = writer.insertAndObserve();

            int committed = jdbc.queryForObject(
                    "select count(*) from items where id = 1", Integer.class);
            require(listener.awaitCommitted());

            boolean rolledBack = false;
            try {
                writer.insertAndRollback();
            } catch (IllegalStateException expected) {
                rolledBack = true;
            }

            int afterRollback = jdbc.queryForObject(
                    "select count(*) from items where id = 2", Integer.class);

            boolean onWorker = c.asyncNoTx().thread().startsWith("tx-worker-")
                    && c.asyncOwnTx().thread().startsWith("tx-worker-");
            boolean eventOnWorker = listener.listenerThread().startsWith("tx-worker-");

            require(c.callerTxActive());
            require(!c.asyncNoTx().txActive());
            require(c.asyncNoTx().visibleRows() == 0);
            require(c.asyncOwnTx().txActive());
            require(c.asyncOwnTx().visibleRows() == 0);
            require(committed == 1 && listener.observedCount() == 1);
            require(rolledBack && afterRollback == 0);
            require(listener.rollbackEventCount() == 0);
            require(onWorker && eventOnWorker);

            System.out.println("callerTxActive=" + c.callerTxActive());
            System.out.println("asyncTxActive=" + c.asyncNoTx().txActive());
            System.out.println("asyncSeesUncommitted=" +
                    (c.asyncNoTx().visibleRows() > 0));
            System.out.println("ownAsyncTxActive=" + c.asyncOwnTx().txActive());
            System.out.println("ownAsyncSeesUncommitted=" +
                    (c.asyncOwnTx().visibleRows() > 0));
            System.out.println("committedRowVisible=" + (committed == 1));
            System.out.println("afterCommitEventVisible=" +
                    (listener.observedCount() == 1));
            System.out.println("rollbackRowVisible=" + (afterRollback > 0));
            System.out.println("rollbackEventDelivered=" +
                    (listener.rollbackEventCount() > 0));
            System.out.println("workerThreadUsed=" + onWorker);
            System.out.println("listenerWorkerThreadUsed=" + eventOnWorker);
        }
    }
}
```

**Why use `DriverManagerDataSource`?** This choice is **for demo purposes only**: each `getConnection()` call can create a new connection. Production typically uses a connection pool such as HikariCP with appropriate timeout/size settings. H2 in-memory in this example uses the `DB_CLOSE_DELAY=-1` URL parameter to keep the database alive as connections are closed sequentially during the JVM lifetime.

### 6.2. Run Command and Verified Stdout

Requires Maven and JDK 21 or newer. From the `tx-async-demo` directory:

```bash
mvn -q -DskipTests compile exec:java
```

**Actual compiled/executed stdout:**

```text
callerTxActive=true
asyncTxActive=false
asyncSeesUncommitted=false
ownAsyncTxActive=true
ownAsyncSeesUncommitted=false
committedRowVisible=true
afterCommitEventVisible=true
rollbackRowVisible=false
rollbackEventDelivered=false
workerThreadUsed=true
listenerWorkerThreadUsed=true
```

The program prints booleans rather than a fixed thread-name ordering; actual worker ordering can vary with scheduling. The test includes assertions; if behavior deviates from expectations, the program throws an error instead of merely printing misleading results.

### 6.3. Interpreting Each Line of Output

| Output line | Meaning |
| --- | --- |
| `callerTxActive=true` | `Writer.insertAndObserve()` actually executes inside the caller's transaction. |
| `asyncTxActive=false` | `Reader.withoutTransaction()` runs on a worker without the caller's transaction. |
| `asyncSeesUncommitted=false` | The worker's query does not yet see row 1 because the caller's transaction has not committed under the demo isolation level. |
| `ownAsyncTxActive=true` | `Reader.withOwnTransaction()` opened a transaction on the worker. |
| `ownAsyncSeesUncommitted=false` | The worker's own transaction still does not see the uncommitted record from the caller's transaction. |
| `committedRowVisible=true` | After the transactional method finishes and commits, row 1 is visible to a new query. |
| `afterCommitEventVisible=true` | The AFTER_COMMIT listener, running asynchronously on the pool, observes the committed row. |
| `rollbackRowVisible=false` | The transaction inserting row 2 throws an exception and rolls back, so row 2 does not exist. |
| `rollbackEventDelivered=false` | The row 2 event attached to the rolled-back transaction does not trigger the AFTER_COMMIT listener. |
| `workerThreadUsed=true` | Both worker reads ran on threads with the `tx-worker-` pool prefix. |
| `listenerWorkerThreadUsed=true` | The AFTER_COMMIT listener was also processed on a worker thread. |

**Limitations of the example:** H2's default transaction isolation in this scenario is `READ_COMMITTED`; the queries are coordinated to execute before the caller commits, so the two lines about "not seeing uncommitted" are a stable demo result, not a universal claim across all databases/isolation levels.

## 7. @Transactional and @Async Mechanisms in the Example: Two Proxy Boundaries

The demo declares:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableTransactionManagement
public static class Config {
    // Beans: DataSource, transactionManager, workerExecutor,
    // Reader, Writer, and AfterCommitListener.
}
```

The same ApplicationContext registers handling for both `@Transactional` and `@Async`. However, that **does not mean** a transaction spans across threads.

- `Writer.insertAndObserve()` is called from `main` through the Spring-managed `Writer` bean. The transaction interceptor opens transaction T1 on the caller thread.
- `Writer` calls `Reader.withoutTransaction()` and `Reader.withOwnTransaction()` through dependencies injected by the container. The async interceptor submits tasks to `workerExecutor`.
- `withoutTransaction()` executes on the worker without T1. It queries the DB using a separate connection.
- `withOwnTransaction()` executes on the worker; the transaction interceptor opens a separate T2 in the worker thread's context. It queries the DB under T2's isolation level.
- Only after both Futures return and `insertAndObserve()` completes does T1 commit. Thus both worker queries are guaranteed to occur before commit in the demo.

**Bean separation matters.** If `Writer` itself contained an `@Async` method and called it via `this.workerMethod()`, the call could bypass the proxy in default mode and run synchronously on the caller. A test would then report transaction active=true in the "worker method" simply because **no thread switch happened at all**. Do not mistake that for transaction propagation.

## 8. What Happens If the Worker Needs to Write Data?

If an asynchronous job needs to update the database, there are two models with different business semantics.

### 8.1. The Worker Opens Its Own Transaction

Use another Spring-managed bean with a method:

```java
@Async("workerExecutor")
@Transactional
public CompletableFuture<Void> updateProjection(long orderId) {
    jdbc.update("update projections set status = ? where order_id = ?",
                "READY", orderId);
    return CompletableFuture.completedFuture(null);
}
```

This is a fragment requiring an actual bean with `JdbcTemplate jdbc` and a matching schema. `@Transactional` on the worker can create its own transaction. This transaction commits/rolls back according to the worker's execution outcome, **not automatically tied** to the caller's open transaction.

If the caller transaction later rolls back while the worker has already committed another side effect, the database may end up in an undesirable business state. Placing both annotations on the same method does not make them share T1.

### 8.2. Requiring the Same Atomic Transaction

If two DB operations must commit/roll back **together**, execute them within the **same transaction boundary** using the synchronous imperative model — for instance, placing them inside a single transactional application-service method or calling another transactional service synchronously on the same thread and resource context.

Do not use `@Async` and expect a single ACID transaction spanning multiple threads. If work must be distributed, choose eventual consistency semantics, an outbox, a saga, or an appropriate distributed coordination mechanism — which is a different design from a local JDBC transaction.

### 8.3. Using REQUIRES_NEW Does Not "Reconnect" to T1

A worker method with `@Transactional(propagation = Propagation.REQUIRES_NEW)` opens an independent transaction on the **worker thread**. It cannot see the caller's uncommitted data by "setting a stronger propagation". If the worker thread has no active transaction, `REQUIRED` will already create a new transaction; `REQUIRES_NEW` is unnecessary just to avoid inheriting T1 when T1 is not there.

## 9. Avoiding Pre-Commit Reads Using Transaction-Bound Events

A common requirement: "After successfully creating an order, send an email / refresh cache / update search index." Instead of calling the worker while the transaction is still open, you can **publish an event inside the transaction** and **wait until the post-commit phase** to process it.

Spring provides `@TransactionalEventListener`. For example:

```java
@Transactional
public void createOrder(long id) {
    jdbc.update("insert into orders(id) values (?)", id);
    applicationEventPublisher.publishEvent(new OrderCreated(id));
}
```

This is a fragment assuming `applicationEventPublisher` is injected and `OrderCreated` is a real record/event type. With a listener:

```java
@Async("workerExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    // Can look up the committed row and then perform post-processing.
}
```

This is a fragment on a Spring-managed listener bean; it requires `@EnableAsync`, proper transaction management, and an executor. With `AFTER_COMMIT`, the listener is triggered after the event-publishing transaction **commits successfully**. When the transaction rolls back, the `AFTER_COMMIT` listener does not process that event.

**Strength:** avoids the "async reads data before commit" race and prevents firing side effects after a rolled-back transaction in the normal execution path.

**Caveat:** `@TransactionalEventListener` is not a **durable message broker**. If the JVM dies after commit but before the async listener finishes processing, the in-memory event can be lost.

### 9.1. phase and fallbackExecution

The phases include:

- `BEFORE_COMMIT`: before commit, suitable for certain logic that needs to run as the transaction prepares to complete, but not as a marker for committed data.
- `AFTER_COMMIT`: after successful commit (default).
- `AFTER_ROLLBACK`: when the transaction rolls back.
- `AFTER_COMPLETION`: when the transaction completes, regardless of outcome.

If an event is published **outside an active transaction**, a transactional listener is **not invoked** by default unless `fallbackExecution = true` is enabled. Therefore, do not assume every `publishEvent(...)` triggers a `@TransactionalEventListener` under all circumstances.

### 9.2. Do Not Write to the DB in a Raw afterCommit Callback Without Considering a New Transaction

A synchronous `AFTER_COMMIT` callback may run during the transaction completion phase when resources bound to the caller thread have not been fully cleaned up yet. If the callback writes to the DB itself, be careful with resource/transaction state; if it must write in a new transaction, open an appropriate boundary such as `REQUIRES_NEW` in the right execution context.

In the demo, the listener has `@Async` to run **on a different worker** after the commit phase and only reads the committed row. If an async listener also needs to write to the DB, configure a new transaction for the write work as needed. Do not rely on the caller's old connection after commit.

## 10. When Post-Processing Delivery Must Be Guaranteed: Transactional Outbox

`@TransactionalEventListener(AFTER_COMMIT)` solves the **commit ordering** problem within a running process. However, it does not satisfy the requirement "once the DB commits, sending the email/event must be delivered even if the process crashes right after commit".

For critical business tasks, consider a **transactional outbox**:

1. Inside the **same transaction T1**, persist the business entity and an outbox record for the event to be processed.
2. T1 **atomically** commits both records.
3. Another relay/worker reads committed outbox records and publishes them to a message broker/destination.
4. After receiving an appropriate acknowledgement, mark the outbox record as processed; on failure, retry in a controlled manner.
5. Consumers use idempotency/deduplication because the system may deliver at least once.

```text
Caller @Transactional
  |
  +-- INSERT orders
  +-- INSERT outbox_event
  +-- COMMIT (atomic)
             |
             v
       Outbox relay
             |
             +-- publish to broker / durable job system
             |
             v
       Consumer / background worker
             |
             +-- dedup + business processing + status
```

In this model, the worker does not need to inherit T1. It operates after both the data and the outbox message have committed; consistency is ensured through **business orchestration and persistence**, not by stretching a JDBC transaction across a thread boundary.

Do not claim "exactly once" solely because of an outbox; you must analyze retries, deduplication, idempotency, and the protocol for receiving/recording results.

## 11. Exceptions, Rollbacks, and Futures in Async Tasks

### 11.1. Caller Transaction Failure

If a synchronous `@Transactional` method throws an unchecked exception and the exception propagates through the transactional proxy, Spring typically marks rollback / rolls back per default rules. In the example, `insertAndRollback()` throws `IllegalStateException`; row 2 is rolled back.

Do not assume **every exception** rolls back by default: checked exceptions follow different rules depending on configuration (such as `rollbackFor`), the transaction manager, and application policy.

### 11.2. Errors in the Worker Do Not Automatically Roll Back the Caller's Transaction

If an asynchronous worker throws an exception **after the caller has committed**, that error cannot go back in time and roll back the already-finished transaction T1. Even while the caller still holds T1 open, an error captured by the worker into a `Future` is not automatically thrown on the caller unless the caller calls `get()` and handles it.

Distinguish between:

- Error **at submission time**: a full pool/queue can throw `TaskRejectedException` directly on the caller.
- Error **inside the worker**: for an `@Async` method returning `Future`/`CompletableFuture`, the caller can observe it via `get()` or a completion handler.
- Async method returning `void`: the caller has no Future to retrieve errors; you need an `AsyncUncaughtExceptionHandler` and appropriate logging/monitoring.
- Error **inside an AFTER_COMMIT listener**: the caller's commit has already completed; failure handling and retries require a separate mechanism.

If the work is important, there must be a place tracking task ID, final status, retries, alerts, and recovery data across restarts; do not simply call `@Async` and forget about it.

### 11.3. Do Not Make the Caller Wait for the Worker Inside the Same Transaction Just to Catch Errors

Calling `future.get()` inside T1 can let the caller observe task errors, but it increases how long connections/locks are held and does not merge T1 and the worker's transaction into a single shared transaction. This is especially dangerous if the worker needs to see data that is only committed **after T1 finishes**.

Clarify the orchestration: which work belongs inside synchronous transaction T1, and which work is handed off for post-commit processing with independent state.

## 12. Thread-Locals, MDC, SecurityContext, and JPA

Transactions are one example of **thread context**. When switching threads, many other kinds of context also do not propagate automatically:

- `TransactionSynchronizationManager`: transaction/resource bindings of imperative Spring.
- Logging `MDC`: correlation ID / log fields backed by `ThreadLocal`.
- `SecurityContextHolder`: depends on the security context storage strategy; not safely copied to workers by default.
- Request-scoped context / HTTP request attributes: may no longer be valid when a worker runs after the response.
- JPA `EntityManager` / Hibernate `Session`: persistence contexts tied to a transaction/thread; do not share mutable entities or sessions arbitrarily across threads.

A `TaskDecorator` or context-propagation library can copy **appropriate metadata** such as a correlation ID or a safely handled security context. However, **do not use a TaskDecorator to copy a raw transaction connection or Session to a worker**. Pass IDs or immutable DTOs, open an independent transaction properly inside the worker, and verify the resulting state.

When fixing self-invocation so that a method truly runs asynchronously, a method that previously happened to access the caller's transaction or MDC will no longer see them. That is not a worker bug; it is the emergence of a thread boundary that previously did not exist.

## 13. Testing Without Relying on Scheduling Luck

The "worker does not see the new record" case may fail to reproduce if the worker runs too late after the caller has already committed. Therefore, **tests must control timing**.

In the complete example:

- `Writer.insertAndObserve()` keeps the caller transaction active.
- The caller **awaits both worker Futures** to complete before the transactional method returns.
- Because commit happens when `insertAndObserve()` returns through the proxy, both worker queries are guaranteed to execute **before T1 commits**.
- Assertions measure both the worker's transaction state and the JDBC query results, not merely the thread name.
- After the method returns, a new query sees the committed row.
- The `AFTER_COMMIT` listener has a `CountDownLatch` so `main` awaits completion instead of sleeping for a guessed duration.
- Another method publishes an event and throws an unchecked exception to verify rollback: neither the row nor the corresponding listener invocation occurs.

**Note on the test harness:** Waiting for workers inside T1 is designed to **prove isolation**, not as advice for structuring business workflows. Production code should avoid holding transactions open to wait for async tasks that need to read uncommitted data.

### 13.1. Integration Tests Need a Real Transaction Manager

A unit test that only mocks `JdbcTemplate` or invokes methods directly via `new Reader(...)` does not prove transaction binding through a Spring proxy. To verify threads, commits, and isolation, you must run with a Spring context, transaction manager, and a suitable real database/driver.

### 13.2. Do Not Rely on Default @Transactional Tests to Infer Production Behavior

Many test frameworks wrap test methods in a transaction and roll back at the end of the test; if the test spawns a separate worker, the worker does not automatically join the test transaction. Worker queries may unexpectedly return empty results. You need to understand the test transaction boundary, set up committed data when needed, and control rollback/cleanup intentionally.

### 13.3. Consistency Between the Database and Side Effects

Test all three cases:

1. Commit succeeds and then the worker runs.
2. Transaction rolls back before the worker is dispatched.
3. The worker fails after commit: whether the system has retries/alerts and durable state.

Case (3) is often more important than a simple demo because it determines business reliability.

## 14. Configuring Executors and Transactions in Production

The `ThreadPoolTaskExecutor` snippet in the example uses:

```java
pool.setCorePoolSize(2);
pool.setMaxPoolSize(2);
pool.setQueueCapacity(8);
pool.setThreadNamePrefix("tx-worker-");
```

These are demo parameters, not recommended defaults. In production:

- Queue/burst limits must be bounded explicitly, because delays before a worker reads data affect task timing.
- The connection pool must be sized for the concurrent DB operations that can run, without exceeding the database's capacity.
- Workers with their own transactions need timeouts, rollback rules, and isolation levels suited to their requirements.
- DB transactions should be short; avoid holding locks or connections while waiting on network/mail services unless strictly necessary.
- Monitor active threads, queue depth, rejections, DB connection wait time, transaction duration, deadlocks, slow queries, and retry rates.
- If durable work is required, use an outbox, broker, or job store rather than merely increasing executor capacity.

**Do not conflate @Async with @Transactional.** They are two separate types of advice: one decides the **execution thread**, and the other decides the **transaction boundary on the executing thread**. How the two annotations combine must be tested through real proxies and a real transaction manager.

## 15. Common Pitfalls

| Misconception or bad design | Consequence | How to handle it |
| --- | --- | --- |
| "@Transactional on the caller covers the @Async worker too" | Worker sees no uncommitted data or has no transaction | Identify the thread boundary; open a separate transaction in the worker if needed |
| Adding `@Transactional` to the worker to "inherit" T1 | Worker gets an independent T2, not T1 | Design commit order, events, or an outbox explicitly |
| Using `REQUIRES_NEW` expecting to read an uncommitted row | T2 is still subject to isolation and usually does not see T1's row | Wait for commit properly instead of forcing isolation arbitrarily |
| Dispatching @Async right after `save()` assuming the row is committed | Worker may read too early | `@TransactionalEventListener(AFTER_COMMIT)` or an outbox |
| Caller waits for worker inside T1 while worker waits for T1's data | Can cause deadlock/timeout | Fix the workflow and dispatch work after commit |
| Worker commits a side effect while caller rolls back | Divergent business state | Dispatch work only after commit, or design sagas/compensation |
| `this.asyncMethod()` happens to see the caller's transaction | Self-invocation bypasses the proxy and never actually switched threads | Extract an async bean or submit explicitly |
| Assuming switching to class-based proxies fixes self-invocation | Still bypasses internal calls | Verify the proxy boundary, not just the proxy type |
| Using `TaskDecorator` to copy a JDBC Connection to another thread | Violates resource lifecycle and concurrency assumptions | Propagate only safe metadata; do not carry raw transactions across |
| Thinking `@TransactionalEventListener` is a durable queue | Events can be lost when the process crashes | Use a transactional outbox if recovery is required |
| Publishing an event outside a transaction and expecting an AFTER_COMMIT listener | Listener does not run by default | Check `fallbackExecution` or clarify boundaries |
| Ignoring worker errors because the caller sees no exception | Tasks fail silently or outcomes are lost | Use Futures/error handlers, metrics, retries/status tracking |
| Trusting passing tests when the worker happens to run after commit | Race does not surface in light tests | Coordinate/verify pre-commit behavior with Futures/latches |
| Generalizing an H2 demo to all databases | Isolation and locking behave differently | Test against the real DB engine and isolation level |
| Assuming reactive transactions are also ThreadLocal-bound | Wrong mental model for Reactor Context | Distinguish imperative from reactive transactions |

## 16. Self-Check Questions

**Question 1.** Method `register()` is called through an `@Transactional` proxy and is inserting an order. It calls `notificationWorker.send()` on another bean via `@Async`. Does the worker automatically use T1?

No. T1 is a thread-bound imperative transaction. The worker runs on a different thread and does not automatically receive T1's resources or connection.

**Question 2.** Does adding `@Transactional` to `send()` put both methods in the same transaction?

No. When @Async advice moves the call to a worker and @Transactional advice is applied on the worker, it can open **an independent T2**. T2 does not see T1's uncommitted changes under isolation levels such as READ_COMMITTED.

**Question 3.** If a worker query sees an uncommitted row in a light test, can we conclude that the transaction propagated?

No. The caller may have committed before the worker queried, the isolation level may differ from expectations, or the `@Async` method may not have actually switched threads due to self-invocation or `SyncTaskExecutor`. You must measure thread name, transaction state, and control commit timing.

**Question 4.** Does a `@TransactionalEventListener(AFTER_COMMIT)` listener automatically guarantee an email is sent after commit even if the JVM crashes?

No. It selects the processing phase within a running process, but does not guarantee durability. For work that must not be lost, use an outbox/durable queue and retries.

**Question 5.** Why did the AFTER_COMMIT listener in the demo see row 1, whereas the same listener did not receive the event for row 2?

Row 1 was committed successfully, so the AFTER_COMMIT phase listener triggered; the transaction containing row 2 rolled back due to an exception, so there was no successful commit phase.

**Question 6.** When should two DB operations stay in the same transactional thread rather than pushing one to @Async?

When they must commit/roll back atomically within the **same local transaction**. If split asynchronously, you must accept and design eventual consistency semantics or another form of orchestration.

## 17. Pre-Production Checklist

- Do we know whether the actual transaction manager is an imperative `PlatformTransactionManager` or a reactive `ReactiveTransactionManager`?
- Are `@EnableTransactionManagement` and `@EnableAsync` located in the right ApplicationContext?
- Are `@Transactional`/`@Async` methods genuinely invoked through Spring proxies rather than `this.method()`?
- Does the real executor run on a different worker thread rather than using `SyncTaskExecutor`?
- Does the worker need an independent transaction, and are propagation/isolation/rollback rules clearly defined?
- Does the worker depend on records the caller just wrote but has not yet committed?
- If it needs to run after commit, are we using the AFTER_COMMIT phase or a transactional outbox?
- Is there a policy for when the transaction rolls back and when the worker fails **after commit**?
- Have idempotency/deduplication and durable task-state persistence been designed where needed?
- Have we avoided holding DB transactions open while waiting on Futures or network calls?
- Have we measured threads, transaction states, commit visibility, and the DB connection pool under load?
- Have we tested rollback/commit against a real DB and isolation level instead of only mocks?
- Have we avoided passing raw JDBC Connections, EntityManagers, or transaction ThreadLocals to workers?
- Are timeout, retry, and alerting mechanisms in place for critical background work?

## 18. Conclusion

In imperative Spring Framework, **regular transactions are bound to the execution thread** via the transaction manager and resource bindings. When an `@Async` call genuinely goes through a proxy and runs on another worker, **the caller's transaction does not transfer along with it**.

A worker without `@Transactional` normally has no caller transaction. A worker with `@Transactional` can open its **own** transaction, yet still cannot read uncommitted data or roll back together with the caller. To start work after commit, use explicit transaction/event boundaries; to avoid losing work across restarts, use a durable mechanism such as a **transactional outbox**.

### References

- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Task Execution and @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.2.1 — @Transactional](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2.1 — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework 6.2.1 — @TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)