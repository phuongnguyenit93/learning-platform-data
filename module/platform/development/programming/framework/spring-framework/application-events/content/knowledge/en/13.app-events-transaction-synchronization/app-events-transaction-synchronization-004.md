# Is an Event Published Before or After Data Changes?

In Spring Framework Application Events, **where `publishEvent()` is called**, **when data changes are executed**, and **when the transaction commits** are three distinct milestones. Confusing them easily causes bugs such as "notification sent even though data rolled back", or "listener reads stale values even though the service just called `save()`".

This article examines publishing application events inside a Spring process, especially when data updates occur within a transaction. The goal is to choose the right execution timing, understand the `@EventListener` and `@TransactionalEventListener` mechanisms, and verify via observable outcomes.

## 1. Three timestamps to keep separate

Suppose a service changes an order status from `NEW` to `PAID`:

1. **In-memory change or SQL write:** `order.setStatus(PAID)`, `repository.save(order)`, `jdbc.update(...)`. With an ORM, `save()` may only update the persistence context; actual SQL may be flushed later.
2. **Event publication:** `publisher.publishEvent(new OrderPaid(id))`. This is when the notification is sent to the multicaster mechanism; Spring does not automatically tie this call to preceding or following data writes.
3. **Transaction completion:** commit finalizes valid changes; rollback discards changes belonging to the transaction.

The two ways of writing below have different meanings:

~~~java
// Illustrates code inside a transactional business method:
publisher.publishEvent(new OrderPaid(orderId));
repository.markPaid(orderId); // Event is published BEFORE the change.

// Compared to:
repository.markPaid(orderId);
publisher.publishEvent(new OrderPaid(orderId)); // Event published AFTER the change,
// yet still possibly BEFORE transaction commit.
~~~

These are snippets, not standalone Java classes. In the second example, **"after calling the write operation" is not synonymous with "after commit"**. If the transaction rolls back at a later step, the published event still occurred.

### Timeline view

| Milestone | Data in transaction | Synchronous `@EventListener` | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- | --- |
| `publishEvent()` before write | Does not yet have that write's change | Runs immediately; may see old state | Has not run yet; registered for post-commit handling |
| Write finishes then `publishEvent()`, transaction still open | Change may be written as SQL or still in ORM context | Runs immediately; if reading through the same transaction, may see the change | Has not run yet |
| Transaction commits successfully | Data is finalized per database rules | Not automatically invoked again by the old event | Invoked in the `AFTER_COMMIT` phase |
| Transaction rolls back | Changes belonging to the transaction are discarded | Synchronous listener that already ran **is not automatically "undone"** | Does not run; `AFTER_ROLLBACK` phase may run |

A listener running in the same transaction can read uncommitted data from that transaction. Conversely, a listener running on another thread or using another transaction/connection usually does not see uncommitted data, depending on isolation level and data access technology. Thus, you must determine **where, when, and through which transaction the listener runs**.

## 2. When does `@EventListener` run?

With Spring's default `ApplicationEventMulticaster` (without configuring an async executor), an `@EventListener` is invoked **synchronously on the event-publishing thread**. Therefore:

~~~java
@Transactional
public void pay(String orderId) {
    orderRepository.markPaid(orderId);              // Data change.
    publisher.publishEvent(new OrderPaid(orderId)); // Listener typically runs here.
    validateFinalState(orderId);                    // May throw an exception.
} // If the transaction remains valid, commit occurs when the interceptor exits the method.
~~~

This is a **method snippet**: `OrderPaid`, the repository, the publisher, and `validateFinalState` must be defined in the application; `@Transactional` works only when the call goes through Spring's transaction management mechanism, such as via a proxy. If `validateFinalState()` throws an error causing rollback per transaction rules, a regular listener may already have sent an email or called an external API beforehand. Effects outside the database **are not rolled back together with the JDBC/JPA transaction**.

Similarly, if a synchronous listener writes additional data through the same transaction, the listener's changes can commit or roll back with the main transaction. But sending HTTP/email directly from the listener is an external effect without shared atomicity.

If `@Async` is configured or an executor is attached to the multicaster, the listener may run on another thread; the `publishEvent()` call site no longer guarantees the listener finishes before the next line of code. Thread-bound transactions also do not automatically propagate to async threads.

## 3. `@TransactionalEventListener` binds events to transaction phases

`@TransactionalEventListener` allows a listener to register event handling according to transaction outcome. When an event is published on a thread with a suitable transaction, Spring holds the event for execution at the configured phase:

| Phase | Timing and meaning | Suitable when |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the actual commit step; commit can still fail | Need to check/prepare data within the same transaction; must not be treated as finalized |
| `AFTER_COMMIT` (**default**) | After successful commit | Emitting signals/notifications only once data is committed |
| `AFTER_ROLLBACK` | After rollback | Recording/alerting that the transaction failed |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback | Cleanup based on final completion; use a specific phase to know the exact outcome |

Example receiving an event after commit:

~~~java
@Component
class ReceiptListener {
    private final ReceiptGateway gateway;

    ReceiptListener(ReceiptGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        gateway.sendReceipt(event.orderId());
    }
}
~~~

This is an **application listener snippet**, requiring `ReceiptGateway`, `OrderPaid`, and imports for `org.springframework.stereotype.Component`, `org.springframework.transaction.event.TransactionalEventListener`, and `org.springframework.transaction.event.TransactionPhase`. It expresses the intent not to send a receipt if the transaction rolls back, but **does not automatically provide retry, idempotency, or guaranteed delivery** if the process crashes after commit or the gateway fails.

By default, when `publishEvent()` occurs **outside an active transaction**, `@TransactionalEventListener` **is not invoked**. `fallbackExecution = true` allows execution when there is no transaction; if business rules strictly require running only upon commit, avoid enabling it casually since there is no longer an "after commit" constraint.

### Note on database access in `AFTER_COMMIT`

During phases after the transaction finishes, transaction resources may still be bound to the thread. A DB write inside an `AFTER_COMMIT` listener may still "join" the old transaction's resource, yet **there is no subsequent commit** for that write. If you need to persist additional separate records after commit, start a new transaction explicitly—for example through another service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` (called via a Spring proxy), or a `TransactionTemplate` configured with `PROPAGATION_REQUIRES_NEW`. Do not rely on the old transaction to ensure new records commit.

## 4. Verification example: before write, after write but before commit, commit, and rollback

The following example is a complete Java 17+ test using **Spring Context + Spring JDBC + Spring Test + H2 + JUnit 5**. To make timing clear, the code uses `TransactionTemplate` and `JdbcTemplate`, avoiding ORM flush differences. `@Transactional` is not used on the test method itself, allowing assertions immediately **after** `TransactionTemplate` returns.

### 4.1. Create a minimal Gradle project

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-jdbc:6.1.14'
    implementation 'org.springframework:spring-tx:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'com.h2database:h2:2.2.224'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The versions above are a Java 17-compatible example set; in a Spring Boot project using a BOM, use the Spring versions managed by the BOM to avoid conflicts. If using the Gradle wrapper in a project, global Gradle installation is not needed.

### 4.2. File `src/test/java/example/events/OrderEventTimingTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(OrderEventTimingTest.Config.class)
class OrderEventTimingTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired Timeline timeline;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM purchase_order");
        timeline.clear();
    }

    @Test
    void publishBeforeInsert_observesOldStateUntilCommit() {
        tx.executeWithoutResult(status -> {
            publisher.publishEvent(new OrderChanged("A"));
            assertEquals(
                List.of("immediate:A:0"),
                timeline.snapshot()
            );

            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "A"
            );
            // AFTER_COMMIT listener has not run even though INSERT finished.
            assertEquals(
                List.of("immediate:A:0"),
                timeline.snapshot()
            );
        });

        assertEquals(
            List.of("immediate:A:0", "afterCommit:A"),
            timeline.snapshot()
        );
        assertEquals(1, rowCount("A"));
    }

    @Test
    void publishAfterInsert_seesOwnUncommittedWrite() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "B"
            );
            publisher.publishEvent(new OrderChanged("B"));

            // Same thread and same JDBC transaction: sees the INSERT.
            assertEquals(
                List.of("immediate:B:1"),
                timeline.snapshot()
            );
        });

        assertEquals(
            List.of("immediate:B:1", "afterCommit:B"),
            timeline.snapshot()
        );
        assertEquals(1, rowCount("B"));
    }

    @Test
    void rollbackDoesNotTriggerAfterCommit() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO purchase_order(id) VALUES (?)", "C"
            );
            publisher.publishEvent(new OrderChanged("C"));
            status.setRollbackOnly();
        });

        assertEquals(
            List.of("immediate:C:1", "afterRollback:C"),
            timeline.snapshot()
        );
        assertEquals(0, rowCount("C"));
    }

    @Test
    void withoutTransactionTransactionalListenersDoNotRun() {
        publisher.publishEvent(new OrderChanged("D"));

        assertEquals(
            List.of("immediate:D:0"),
            timeline.snapshot()
        );
    }

    private int rowCount(String id) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM purchase_order WHERE id = ?",
            Integer.class, id
        );
        return count.intValue();
    }

    record OrderChanged(String id) { }

    static class Timeline {
        private final List<String> entries = new ArrayList<>();

        void record(String entry) {
            entries.add(entry);
        }

        List<String> snapshot() {
            return List.copyOf(entries);
        }

        void clear() {
            entries.clear();
        }
    }

    static class TimingListeners {
        private final JdbcTemplate jdbc;
        private final Timeline timeline;

        TimingListeners(JdbcTemplate jdbc, Timeline timeline) {
            this.jdbc = jdbc;
            this.timeline = timeline;
        }

        @EventListener
        public void immediate(OrderChanged event) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE id = ?",
                Integer.class, event.id()
            );
            timeline.record("immediate:" + event.id() + ":" + count);
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderChanged event) {
            timeline.record("afterCommit:" + event.id());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(OrderChanged event) {
            timeline.record("afterRollback:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:event_timing;DB_CLOSE_DELAY=-1",
                "sa",
                ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS purchase_order (" +
                "id VARCHAR(50) PRIMARY KEY)"
            );
            return jdbc;
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Timeline timeline() {
            return new Timeline();
        }

        @Bean
        TimingListeners timingListeners(
                JdbcTemplate jdbc, Timeline timeline) {
            return new TimingListeners(jdbc, timeline);
        }
    }
}
~~~

Run the test from the project directory containing the Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.OrderEventTimingTest"
~~~

On Windows PowerShell use `./gradlew.bat test --tests "example.events.OrderEventTimingTest"`. The tests **do not print business data to stdout**; observable results are assertions on `timeline` and the database. If the test passes, the results can be interpreted as:

- `A`: published **before INSERT** → synchronous listener counts `0`; `afterCommit:A` appears only after commit; final database has 1 record.
- `B`: published after INSERT **before commit** → synchronous listener using the same JDBC transaction counts `1`; `afterCommit:B` still waits for commit.
- `C`: INSERT and publish then **rollback** → regular listener had already run (`immediate:C:1`); `afterRollback:C` runs; **there is no `afterCommit:C`**, and the database has no record left.
- `D`: published **outside transaction** → regular listener still receives the event, whereas the two transactional listeners do not run by default.

**Why is this an appropriate integration test?** Events flow through `ApplicationEventPublisher` inside a real Spring context; `DataSourceTransactionManager` and `JdbcTemplate` share the same `DataSource`, so reads inside the synchronous listener participate in the open JDBC transaction. `TransactionTemplate` explicitly commits/rolls back so subsequent assertions observe transaction callbacks. `Timeline` is a simple list that works because the example runs synchronously; if async/concurrent execution is enabled, a thread-safe synchronization mechanism and data structure are required.

## 5. When using JPA/Hibernate, what do `save()` and `flush()` mean?

In JPA, `repository.save(entity)` does not always cause SQL `INSERT`/`UPDATE` to execute immediately. The persistence context may hold the modified entity and flush only when needed or near commit.

Consider the sequence:

~~~java
@Transactional
public void updateStatus(String id) {
    Order order = orderRepository.findById(id).orElseThrow();
    order.setStatus(OrderStatus.PAID);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPaid(id));
}
~~~

This is an illustrative service snippet, not a standalone file. At `publishEvent()`:

- A synchronous `@EventListener` accessing the **same managed entity** may see the `PAID` state, even if SQL has not flushed or the transaction has not committed.
- A JPA query may trigger a flush depending on flush mode and query type; do not infer from "listener queried the new value" that the transaction has committed.
- A listener reading with an **independent connection/transaction** usually sees only committed data according to the applicable isolation level.
- `saveAndFlush()` or `entityManager.flush()` can push SQL to the database and surface constraint errors earlier, yet **flush is not commit**. The transaction can still roll back.

Therefore, design events around the **business event that occurred in the transaction** (such as the decision to transition state), while any listener that must wait for finalized data should use `AFTER_COMMIT` or a post-commit delivery mechanism. Do not swap `save()` and `publishEvent()` as a substitute for an explicit commit contract.

## 6. Choosing a design based on consistency requirements

**Case A — the listener only updates data that must belong to the same transaction.** If using a synchronous listener in the same transaction/thread, DB side effects can commit or roll back together with the main operation. However, if it is a mandatory step to complete the business operation, a direct service call may be clearer and easier to test than an implicit listener.

**Case B — sending email or notifications only after successful commit.** Use `@TransactionalEventListener(phase = AFTER_COMMIT)` to avoid sending on rollback. You must accept that a gateway failure after commit does not automatically roll back committed data; error handling, retry, and idempotency are needed according to criticality.

**Case C — notifications must never be lost, even if the process stops right after commit.** `AFTER_COMMIT` alone does not guarantee durability. The **transactional outbox** pattern stores business state and an outbox record inside the *same database transaction*. An independent worker/broker publisher reads committed records, sends with retries, marks them sent, and handles duplicates via idempotency.

~~~text
BEGIN TRANSACTION
  UPDATE purchase_order SET status = 'PAID' WHERE id = ...
  INSERT INTO outbox(event_id, type, payload, status)
    VALUES (..., 'OrderPaid', ..., 'PENDING')
COMMIT

Worker reads committed outbox -> publishes -> records outcome/retry
Consumer processes event_id idempotently
~~~

This is **pseudocode**, not standalone runnable SQL. An outbox bridges the gap between "DB committed" and "event not yet sent", yet still requires retry and duplicate-prevention design; it does not automatically make the system end-to-end exactly-once.

**Case D — multiple consumers/threads.** `@Async`, executors, reactive pipelines, or message brokers have different transaction boundaries. With reactive transactions from Spring 6.1, the transaction context lives in the Reactor Context; when using transactional events, you must follow `TransactionalEventPublisher`'s approach for carrying the transaction context. Do not mechanically apply the thread-bound assumptions of the JDBC example to a reactive pipeline.

## 7. Testing exact timing and common mistakes

| Common mistake | Why it is wrong | Proper verification |
| --- | --- | --- |
| "I already called `save()`, so the event is definitely after commit" | `save()` is inside an unfinished transaction | Test real commit/rollback and observe effects after transaction |
| "The listener already read the new data, so the data is committed" | It may be reading state within the same persistence context/transaction | Query from an independent connection/transaction after commit if proving visibility |
| "Using `@Order` to run the listener after commit" | `@Order` only controls listener priority, not transaction phase | Use `@TransactionalEventListener(AFTER_COMMIT)` |
| "Sending HTTP in `@EventListener` will roll back" | HTTP/email are outside the DB transaction | Move side effects to after-commit or outbox |
| "A default `@Transactional` test already verifies AFTER_COMMIT" | Spring TestContext rolls back the test transaction by default | Explicitly commit with `TransactionTemplate` or `TestTransaction` |
| "`AFTER_COMMIT` writing to DB via repository is guaranteed to persist" | Old resource may still be thread-bound with no new commit | Open a new transaction, e.g., `REQUIRES_NEW`, and verify DB readback |
| "Without a transaction, the listener will run normally by default" | Transactional listeners ignore events when there is no transaction | Test the no-transaction branch; enable `fallbackExecution` only intentionally |
| "With async enabled, the original transaction is still visible" | Thread-bound context does not automatically pass through an executor | Redesign data boundaries, await results, and test separately |

Minimum tests should cover **publish before change**, **publish after change but before commit**, **successful commit**, **rollback**, and **publish outside transaction** if the application has that path. When JPA is present, add flush/constraint tests; when an outbox is present, add worker retry and duplicate-event scenarios.

In Spring TestContext, a test annotated with `@Transactional` usually **rolls back automatically after the test ends**, so asserting `AFTER_COMMIT` in the middle of the method may fail because callbacks have not had a chance to run. To observe post-commit timing, you can use `TransactionTemplate` in a non-transactional test as in the example above, or use `TestTransaction.flagForCommit()` and `TestTransaction.end()` when the test has a transaction managed by Spring TestContext.

## 8. Self-check questions

1. If `publisher.publishEvent()` is called before `jdbc.update()` in the same transaction, will a synchronous listener see the new record yet? In this example, **no**, because the write statement has not run yet.
2. If `jdbc.update()` completes first and then you publish, does a synchronous listener sharing the same transaction see the uncommitted record? **Yes**, in this JDBC example.
3. If an event is published after `save()` and then rolls back, does Spring retract non-DB side effects of a synchronous `@EventListener`? **No**.
4. When does a default `@TransactionalEventListener` run? **After successful commit** of the suitable transaction that published the event.
5. When is an outbox needed? When you must ensure an event is not lost in the window between data commit and external delivery and need durable retry/idempotency mechanisms.

**Key takeaway:** "publishing after data changes" only describes **statement ordering in the service**; "handling after commit" speaks to **transaction outcome**. Choose listeners and tests according to the business contract you need to protect, especially when emails, brokers, or extra DB writes are involved.

## References

- [Spring Framework – Application Events, `@EventListener`, and synchronous dispatch default](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Transaction-bound Events and `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – TransactionSynchronization (note on post-commit transaction resources)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
