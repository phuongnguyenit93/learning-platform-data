# Re-reading Data in Spring Framework's AFTER_COMMIT

## 1. The problem: after commit, why must reading data still be done carefully?

When an application publishes an event inside a `@Transactional` method, a listener sometimes needs to **re-read persisted data from the database, but only after the original transaction commits successfully**. For example: an order transitions to `CONFIRMED`; after commit, the system needs to read the latest record to build a notification payload or update a search index.

Spring supports this scenario via `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. However, there is an important detail: **the transaction has committed, yet resources bound to the old transaction may still be held by Spring while invoking the callback**. A direct read or write inside the callback might use the connection/`EntityManager` still bound to the old thread. Therefore:

- `AFTER_COMMIT` determines **when the listener is triggered**, not automatically creating a new read transaction.
- Reading directly may return data in some circumstances, but does not mean it is always an independent read with a fresh persistence context and the desired consistency semantics.
- Writing further to the old transaction resource is especially dangerous: **there is no subsequent commit of the original transaction** to persist those changes.
- When you need to **re-read from the database under a new transaction boundary**, the clear approach is moving the read operation to another Spring bean with `@Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)`.

This article focuses on the post-commit re-read flow, callback execution timing, persistence context behavior, designing the new transaction, and verifying that data genuinely comes from the database.

## 2. Transaction progression and TransactionPhase.AFTER_COMMIT

Suppose `OrderService.confirmOrder(id)` is called through a Spring transaction proxy:

~~~text
Request processing thread
   |
   | @Transactional starts transaction T1
   v
UPDATE orders SET status = 'CONFIRMED' WHERE id = 42
   |
   | publisher.publishEvent(new OrderConfirmed(42))
   | -- @TransactionalEventListener registers phase-based handling
   | -- AFTER_COMMIT body has not executed yet
   v
@Transactional method exits normally
   |
   | Transaction manager performs commit of T1
   v
COMMIT succeeds
   |
   | Transaction synchronization calls AFTER_COMMIT listener
   |       |
   |       +--> calls re-read bean with REQUIRES_NEW
   |                |
   |                +--> suspends T1 resources
   |                +--> starts independent transaction T2
   |                +--> SELECT ... WHERE id = 42
   |                +--> completes T2
   |
   v
Spring cleans up T1 resources/synchronizations
   |
   v
Outer flow continues
~~~

If T1 rolls back, listeners registered with `AFTER_COMMIT` **are not executed**. When there is no active transaction at event publication time, `@TransactionalEventListener` also does not run by default unless `fallbackExecution = true` is enabled.

Commonly used phases:

| Phase | Timing | Meaning for re-reading data |
|---|---|---|
| `BEFORE_COMMIT` | Before T1's commit operation | Cannot yet assert changes are committed |
| `AFTER_COMMIT` | T1 has committed successfully | Appropriate for triggering an independent post-commit read |
| `AFTER_ROLLBACK` | T1 has rolled back | For failure handling; do not read expecting T1's changes were saved |
| `AFTER_COMPLETION` | Ends after commit or rollback | Must distinguish the outcome if behavior depends on a successful commit |

**A subtle point:** In Spring Framework, `TransactionPhase.AFTER_COMMIT` is a specialized case of `AFTER_COMPLETION`, handled within the `TransactionSynchronization.afterCompletion(...)` callback chain for the committed status; it is **not identical** to the `TransactionSynchronization.afterCommit()` callback. Even though the names share `AFTER_COMMIT`, do not guess the exact order between different callback styles without checking the contract and `@Order`.

## 3. Why might the old transaction's resources still be present?

Spring typically binds transaction resources to the thread via `TransactionSynchronizationManager`. Depending on the stack:

- With JDBC: the `ConnectionHolder`/connection used in T1 may still remain until the transaction manager completes cleanup.
- With JPA/Hibernate: the `EntityManager`/persistence context attached to the committed transaction may still remain.
- With synchronous listeners: the callback runs while Spring is processing transaction completion, **before full cleanup has finished**.

Spring's Javadoc for `@TransactionalEventListener` notes that during `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`, the transaction has ended yet resources may still be available. Accessing data then can continue "participating" in the old transaction resource, even though **there is no corresponding commit at the end of the callback**.

### Distinguishing three things often lumped into one

1. **Transaction T1 has COMMITTED:** the work was successfully written per the transaction manager.
2. **T1's resources have been unbound from the thread:** this is a separate cleanup step that may happen after the callback.
3. **A SELECT using a fresh connection/EntityManager:** this is an independent read boundary that the program must design; it does not follow automatically from (1).

Example of a flawed design:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    Order order = orderRepository.findById(event.orderId())
        .orElseThrow();
    order.setAuditStatus("DONE");
    // Do not assume this operation will have a new commit.
}
~~~

The snippet above **illustrates the problem**, not a standalone runnable program. A still-managed entity or a repository method participating in the old resource may leave the change visible in memory without committing it as expected. Even a `findById` call may return an entity already in the first-level cache, leading readers to think it freshly loaded from the database.

**Do not conclude that every direct SELECT in AFTER_COMMIT returns stale data.** In many cases a direct read still sees the newly committed value. The problem is lacking a verifiable new transaction/persistence context boundary, so behavior can depend on the specific resource and integration setup.

## 4. Safe approach: extract a read service with REQUIRES_NEW

Suppose the event-publishing service passes only an ID:

~~~java
public record OrderConfirmed(long orderId) {}
~~~

The listener receives the event and delegates to a dedicated reader bean:

~~~java
@Component
public class OrderConfirmedListener {

    private final CommittedOrderReader reader;

    public OrderConfirmedListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmed event) {
        OrderView view = reader.load(event.orderId());
        // Use the freshly read data for post-processing.
    }
}
~~~

An independent bean opens a new transaction:

~~~java
@Service
public class CommittedOrderReader {

    private final OrderRepository repository;

    public CommittedOrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
    public OrderView load(long orderId) {
        Order order = repository.findById(orderId).orElseThrow();
        return new OrderView(order.getId(), order.getStatus());
    }
}
~~~

The snippets above are an **integration architecture pattern**: `OrderRepository`, `Order`, and `OrderView` must be defined for the application. `REQUIRES_NEW` causes Spring to create an independent physical transaction (where supported by the transaction manager), temporarily suspending the current transaction/resource for the scope of the call. With typical JPA configuration, it operates through a persistence context belonging to the new transaction; `readOnly = true` expresses read intent and may enable optimizations, **not an immutability guarantee**.

Why place `@Transactional(REQUIRES_NEW)` on **another bean**? Spring's proxy-based mechanism intercepts only calls passing through the proxy. If the listener calls `this.load(...)` on the same instance, the annotation may have no effect (*self-invocation*).

### Can we use @Transactional(REQUIRED) or just @Transactional(readOnly=true)?

`@Transactional` uses `Propagation.REQUIRED` by default. Inside an `AFTER_COMMIT` callback, the old resource may still be seen as participating in a transaction; thus merely adding `@Transactional(readOnly = true)` without specifying propagation **is not a clear way to request an independent transaction**. Choose `REQUIRES_NEW` when the goal is a separate post-commit read.

### Can we use NOT_SUPPORTED?

`@Transactional(propagation = Propagation.NOT_SUPPORTED)` suspends the current transaction and executes logic outside a Spring transaction. For certain simple JDBC reads, this can be an intentional choice. However, if the read's consistency requirements demand a well-defined transaction, or consistent JPA usage, `REQUIRES_NEW` is easier to reason about and test. Do not treat `NOT_SUPPORTED` and `REQUIRES_NEW` as equivalent.

## 5. Complete Java 17 example: commit sees new data, rollback does not trigger listener

The example below uses **Spring Framework 6.2.8**, Spring JDBC, and in-memory H2. It demonstrates:

1. A `@Transactional` method updates a record and publishes an event.
2. `@TransactionalEventListener(AFTER_COMMIT)` handles only when commit succeeds.
3. The listener calls a `REQUIRES_NEW` bean to SELECT after commit.
4. When another transaction rolls back, the listener does not run and data retains its old value.

Structure:

~~~text
after-commit-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterCommitReadDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/demo/AfterCommitReadDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitReadDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );
            jdbc.update("INSERT INTO orders (id, status) VALUES (?, ?)", 1L, "PENDING");
            jdbc.update("INSERT INTO orders (id, status) VALUES (?, ?)", 2L, "PENDING");

            OrderService service = context.getBean(OrderService.class);
            AuditListener listener = context.getBean(AuditListener.class);

            // Transaction T1 will commit.
            service.confirm(1L);

            System.out.println("order 1 after service: " +
                jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, 1L
                )
            );

            // Transaction T2 will roll back due to RuntimeException.
            try {
                service.confirmThenFail(2L);
            } catch (IllegalStateException expected) {
                System.out.println("rolled back: " + expected.getMessage());
            }

            System.out.println("order 2 after rollback: " +
                jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, 2L
                )
            );
            System.out.println("listener calls: " + listener.handledCount());
        }
    }

    public record OrderConfirmed(long orderId) {}

    @Configuration
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
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

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public CommittedOrderReader committedOrderReader(JdbcTemplate jdbc) {
            return new CommittedOrderReader(jdbc);
        }

        @Bean
        public AuditListener auditListener(CommittedOrderReader reader) {
            return new AuditListener(reader);
        }
    }

    public static class OrderService {

        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void confirm(long orderId) {
            jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                "CONFIRMED", orderId
            );
            publisher.publishEvent(new OrderConfirmed(orderId));
        }

        @Transactional
        public void confirmThenFail(long orderId) {
            jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                "CONFIRMED", orderId
            );
            publisher.publishEvent(new OrderConfirmed(orderId));
            throw new IllegalStateException("simulated failure");
        }
    }

    public static class CommittedOrderReader {

        private final JdbcTemplate jdbc;

        public CommittedOrderReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            readOnly = true
        )
        public String readStatus(long orderId) {
            return jdbc.queryForObject(
                "SELECT status FROM orders WHERE id = ?",
                String.class, orderId
            );
        }
    }

    public static class AuditListener {

        private final CommittedOrderReader reader;
        private final List<Long> handledIds = new ArrayList<>();

        public AuditListener(CommittedOrderReader reader) {
            this.reader = reader;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterOrderCommitted(OrderConfirmed event) {
            String status = reader.readStatus(event.orderId());
            handledIds.add(event.orderId());
            System.out.println(
                "AFTER_COMMIT fresh read: " + event.orderId() + " = " + status
            );
        }

        public int handledCount() {
            return handledIds.size();
        }
    }
}
~~~

Run from the `after-commit-demo` directory using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AfterCommitReadDemo
~~~

Lines printed by the program upon a successful run (ignoring extra tool logs if any):

~~~text
AFTER_COMMIT fresh read: 1 = CONFIRMED
order 1 after service: CONFIRMED
rolled back: simulated failure
order 2 after rollback: PENDING
listener calls: 1
~~~

**Result explanation:**

- For ID 1, the change is committed before `afterOrderCommitted` runs. The `CommittedOrderReader` bean is called through a Spring proxy and creates a new read transaction, so the SELECT receives the committed `CONFIRMED` status.
- `service.confirm(1L)` goes through a transaction proxy. The synchronous `AFTER_COMMIT` listener completes during the transaction completion step before the service call returns, so the listener line appears before `order 1 after service`.
- For ID 2, `RuntimeException` rolls back the transaction; the event published inside the transaction does not trigger the `AFTER_COMMIT` listener. The database status remains `PENDING` and the listener invocation count is one.
- `handledIds` uses `ArrayList` here because the demo runs synchronously on a single calling thread with no async listeners. If switching to multi-threaded processing, do not keep using this structure as a shared counter without synchronization.

The example intentionally uses JDBC to clarify transaction boundaries. With JPA/Hibernate, you must also account for the first-level cache, entity state, and lazy loading.

## 6. With JPA/Hibernate: reading a cached entity vs. fresh load from database

In JPA, `EntityManager` manages a persistence context (first-level cache). Within the same persistence context, calling `find` by key for an already-managed entity typically returns the managed instance. That does not prove a fresh `SELECT` query just ran.

Example scenario to watch out for:

~~~java
@Transactional
public void confirm(long id) {
    Order order = repository.findById(id).orElseThrow();
    order.setStatus(Status.CONFIRMED);
    events.publishEvent(new OrderConfirmed(id));
}
~~~

If the event carries the `Order` entity itself and the listener reuses that object, the listener sees the state in the **object** it holds, which does not necessarily reflect a load from the database. If the callback still clings to the old `EntityManager`, even calling the repository again risks going through the old persistence context.

Preferred organization:

1. **Publish an ID or immutable payload:** e.g., `new OrderConfirmed(id)`; avoid passing managed entities and relying on lazy associations after the transaction.
2. **Read through another bean with a new transaction:** `@Transactional(propagation = REQUIRES_NEW, readOnly = true)` to establish an independent read boundary.
3. **Map to a DTO before leaving the new transaction:** carry only necessary data out to email sending, index syncing, or cache updating.
4. **Do not rely on `flush()` as a substitute for commit:** flush only synchronizes changes to the database within the transaction scope; if the transaction rolls back, changes are still undone.

Illustrative code mapping to a DTO:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
public OrderSnapshot loadSnapshot(long id) {
    Order order = repository.findById(id).orElseThrow();
    return new OrderSnapshot(
        order.getId(),
        order.getStatus(),
        order.getVersion()
    );
}
~~~

`OrderSnapshot` and the `Order` entity here are illustrative types to define in a real application. If lazy relationships must also be read, fetch them completely inside the new read transaction using an appropriate fetch join/entity graph/projection before returning the DTO.

**Limitation to know:** a new transaction does not guarantee reading the exact *version at T1's commit time* when the application has multiple concurrent writers. After T1 commits, another transaction T3 may update the same record before T2 executes SELECT. When you need the record corresponding to an exact event version, attach an immutable version/ID, filter by version when reading, or use an outbox/snapshot per business requirements. If reading from a read replica, replication lag can prevent the fresh read from seeing the primary's commit yet.

## 7. Why must further writes in AFTER_COMMIT be handled with special care?

Suppose a listener is responsible for creating an audit record:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    auditRepository.save(new AuditRecord(event.orderId(), "CONFIRMED"));
}
~~~

This is an **error-prone illustrative snippet**. If the repository call still participates in T1's resource held during the callback, there is no second T1 commit to ensure the audit is written. Hence, do not look at a mutated object value, a normal `save()` return, or SQL logs and conclude persistence succeeded.

For post-processing writes that must commit independently:

~~~java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        // Write audit in new transaction T2, which has its own T2 commit.
    }
}
~~~

The listener simply calls `auditWriter.writeAudit(event.orderId())`. Note: T1 has already committed, so if T2 fails, that **cannot roll back T1**. If atomicity between the order change and the audit record is required, write them in **the same initial transaction**, or use a transactional outbox: write the outbox with T1 and process post-actions from the outbox with a retry mechanism.

## 8. AFTER_COMMIT + @Async: thread boundaries still require clear design

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` and `@Async` can be combined:

~~~java
@Component
public class NotificationListener {

    private final CommittedOrderReader reader;

    public NotificationListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @Async("notificationsExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyAfterCommit(OrderConfirmed event) {
        var snapshot = reader.loadSnapshot(event.orderId());
        // Send notification based on the snapshot loaded after commit.
    }
}
~~~

This snippet is an **illustrative configuration**; it requires `@EnableAsync`, a `notificationsExecutor` bean, and appropriate `CommittedOrderReader`/`OrderSnapshot` definitions. When functioning properly, the transaction callback schedules the listener body to run on a worker thread **after commit**. The publisher's transaction T1 does not automatically propagate to the worker. If the worker needs reads/writes with clear transaction boundaries, it should still call a bean that opens an appropriate transaction, such as `REQUIRES_NEW`.

Points to keep in mind:

- `@Async` means post-commit processing may finish **after the event-publishing service has already returned**.
- Exceptions raised in the worker do not automatically propagate back to the `publishEvent` caller; logging, metrics, `AsyncUncaughtExceptionHandler`, or appropriate application error handling are needed.
- ThreadLocal, security context, MDC, persistence context, and transaction context are not automatically preserved across threads.
- When the executor is overloaded/rejects tasks, you must understand the error policy; the original transaction having committed does not guarantee the post-commit task was enqueued or processed.
- `@Async` runs only in the current JVM; if the process crashes right after T1 commits but before the worker finishes, there is no built-in durable retry.

Do not confuse this with setting an executor on `SimpleApplicationEventMulticaster` and assuming all transactional listeners automatically run async. Since Spring Framework 6.1, listeners can specify `supportsAsyncExecution() = false` to require execution on the original thread, because transaction synchronization registration depends on the proper thread context.

## 9. When to use an event snapshot vs. when to re-read?

The two strategies serve different needs:

| Strategy | Advantages | Risks to manage |
|---|---|---|
| Event carries immutable snapshot | Knows the data at the moment the application published the event | Snapshot is built before commit and might not reflect changes by triggers/other transactions |
| Event carries ID only; AFTER_COMMIT re-reads | Obtains committed state via a fresh read | Extra latency/query, and may see newer updates if there are concurrent writers |
| Transactional outbox storing payload with T1 | Supports durable reprocessing and worker decoupling | Requires outbox table, publisher/consumer, monitoring, and idempotency |

Choose a snapshot when the need is "process the exact facts at event publication time" and the payload is already accurately determined. Choose re-reading if post-processing needs the committed database state. If processing must survive crashes or be delivered to external systems, consider an outbox instead of relying solely on in-memory listeners.

### Race condition example when re-reading

- T1 updates an order from `PENDING` to `CONFIRMED`, then commits.
- T3 updates the same order to `CANCELLED` and commits right after.
- T1's `AFTER_COMMIT` listener opens T2 and runs SELECT, seeing `CANCELLED`.

This is not necessarily a transaction bug; it is a valid result if T2 reads the **latest state at read time**. For a business rule like "send order confirmation for the committed version", attach a version or event type in the payload, check the version before sending notifications, or use an outbox with a snapshot/sequence.

## 10. Off-thread transactions and ReactiveTransactionManager

The examples above use **thread-bound transactions** from `PlatformTransactionManager`, suitable for imperative Spring JDBC/JPA.

Since Spring Framework 6.1, `@TransactionalEventListener` can also work with reactive transactions, yet reactive transactions use **Reactor Context** instead of ThreadLocal. Therefore, binding listeners to the right transaction requires passing the transaction context in the event's source through a mechanism like `TransactionalEventPublisher`. Do not copy the imperative JDBC example verbatim and expect it to keep the same semantics when switching to Reactor/R2DBC.

In multi-datasource/multi-transaction-manager applications, the transaction manager name must also be specified consistently; `REQUIRES_NEW` on a different manager does not automatically ensure reading from where the data was committed.

## 11. Testing: proving commit happened and data was read from a new transaction

A proper test must prove **both processing timing and the read boundary**:

1. Create initial data (e.g., `PENDING`) via an already-committed operation.
2. Call the `@Transactional` service through a Spring bean proxy; update, publish event, let the transaction commit.
3. Verify the `AFTER_COMMIT` listener is called and the reader bean uses `REQUIRES_NEW`; assert the returned data is `CONFIRMED`.
4. Exercise the service branch throwing `RuntimeException` to roll back; assert the rollback branch event does not trigger the `AFTER_COMMIT` listener and the database has no changes.
5. If `@Async` is involved, synchronize tests with a latch/await condition with a clear timeout before asserting; do not rely on `Thread.sleep`.

### Common trap in @Transactional tests

An integration test with `@Transactional` on the **test method itself** is usually rolled back by Spring Test by default when the test ends. Consequently, the `AFTER_COMMIT` listener may never run, causing the test to fail even though the application works correctly.

Example solution using `spring-test`:

~~~java
@Test
@Transactional
void confirmsAfterCommit() {
    service.confirm(42L);

    // Drive the test transaction to an actual commit before asserting callbacks.
    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Only here assert the results of synchronous AFTER_COMMIT.
}
~~~

The snippet above is **illustrative in a Spring Test environment**, requiring test runner configuration, a database, and data for ID 42; the corresponding imports are `org.junit.jupiter.api.Test`, `org.springframework.transaction.annotation.Transactional`, and `org.springframework.test.context.transaction.TestTransaction`. Only use `TestTransaction` when the test runs under Spring Test's transaction management. Alternatively, structure the test method without its own transaction and call the `@Transactional` service separately like the Maven program above.

### Logs/metrics worth collecting

- `eventId`, `orderId`, transaction phase, listener name, and thread name.
- T1 start time, successful commit time; callback start time.
- T2 datasource/transaction manager name, SELECT duration, record version.
- With async: enqueue, start, completion, failure, and retry timestamps.
- On read errors: exception type, transaction propagation, timeout, connection state.

Do not use the return of `publishEvent` as "confirmation that data has been read after commit".

## 12. Common troubleshooting checklist

| Symptom | Common cause | How to fix |
|---|---|---|
| Listener does not run | No transaction, rollback, listener not a Spring bean | Verify `@Transactional` is actually proxied, `fallbackExecution`, and phase |
| Listener runs but reads unexpected data | Using entity held from T1, first-level cache, concurrent writer | Pass ID; read inside `REQUIRES_NEW` bean; check version |
| `save()` inside listener is not durable | T1 resource still participated in, no commit after callback | Write in a new transaction or move logic to T1/outbox |
| Added `@Transactional(readOnly=true)` with no new boundary | `REQUIRED` may join the current resource | Use `Propagation.REQUIRES_NEW` and call through proxy |
| Declared `REQUIRES_NEW` but it did not take effect | Self-invocation or bean not Spring-managed | Split bean, verify proxy and transaction manager |
| Test does not see AFTER_COMMIT | Test transaction auto-rolls back | Commit genuinely via Spring Test or non-transactional test calling transactional service |
| Async listener reads assuming it is in T1 | ThreadLocal transaction is not transferred to worker | Start proper transaction on worker, pass ID/DTO |
| SELECT on replica sees stale value | Replication lag or datasource routing | Consider primary read or explicit consistency requirements |
| SELECT sees a newer version than expected | Another writer committed before T2 read | Attach version/snapshot or use outbox |
| Errors because connection is held by T1 while opening T2 | Pool lacks connections, timeout | Size connection pool appropriately and check connection policies |

## 13. Knowledge summary

`@TransactionalEventListener(AFTER_COMMIT)` is the right tool to **defer listener invocation until the transaction commits successfully**. However, the callback may be invoked **before Spring finishes cleaning up the original transaction's resources**. Therefore, when the goal is **re-reading committed data with an independent read**, move the SELECT operation to another Spring bean and apply `@Transactional(propagation = REQUIRES_NEW, readOnly = true)`, ensuring the call goes through the transaction proxy. Use events carrying IDs/immutable payloads, understand the impact of the JPA first-level cache, and test both commit and rollback paths.

`REQUIRES_NEW` establishes a new transaction, rather than replacing business contracts around snapshots, versioning, race conditions, retries, or crash durability. When those guarantees are required, combine with locking/versioning or a transactional outbox.

### Official documentation

- [Spring Framework Reference 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework Javadoc 6.2.8 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework Javadoc 6.2.8 — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework Javadoc 6.2.8 — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
