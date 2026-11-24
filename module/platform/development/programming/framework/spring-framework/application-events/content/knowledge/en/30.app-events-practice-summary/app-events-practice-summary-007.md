# Testing Commit and Rollback with Spring Application Events

## 1. Objectives of the Practice

When a Spring application modifies data and publishes an event, the critical question is not merely **whether the listener was invoked**. You must also know whether the listener ran **before commit**, **after a successful commit**, **after a rollback**, or **after the transaction completed regardless of outcome**.

Example of an order-creation service:

```java
@Transactional
public void createOrder(String orderId) {
    orderRepository.insert(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
}
```

This is only an **illustrative skeleton**, not a standalone runnable program. Because the event is published inside the transaction, if a listener immediately sends an email or calls a payment system, external side effects can happen **before the data is committed**. The DB transaction may roll back afterward, yet the transaction manager cannot retract an email or HTTP request that was already sent.

Conversely, if you use `@TransactionalEventListener(phase = AFTER_COMMIT)`, the handler runs only when the transaction commits. However, a test with `@Transactional` on **the test method itself** normally rolls back at the end of the test; hence `AFTER_COMMIT` may not run, leading developers to think the listener is misconfigured.

This lesson aims to build the capability to **write tests that verify both the exact phase and real persisted state**, not just logs or mocked calls:

- Distinguish `@EventListener` from `@TransactionalEventListener`.
- Understand the four phases: `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
- Trigger intentional transaction commits and rollbacks with `@Transactional` and H2.
- Use JUnit 5/Spring TestContext to verify what was actually saved to the DB.
- Use `TestTransaction.flagForCommit()`, `flagForRollback()`, and `end()` to observe callbacks **inside the test method**.
- Test failures in `BEFORE_COMMIT`, out-of-transaction publishing, and common anti-patterns.
- Understand an essential limit: `AFTER_COMMIT` **does not by itself guarantee** durable event delivery after a process crash.

## 2. Distinguishing Event Publishing from Transaction Commit

In Spring, the call:

```java
publisher.publishEvent(new OrderPlaced("ORD-1"));
```

means **asking Spring to distribute a Java object**. That call alone does not mean:

- The current transaction has committed.
- Data has been flushed to the DB.
- Listeners have finished their side effects.
- The event has been saved in a durable queue.
- A transaction rollback can undo an operation on another HTTP API.

For internal events, Spring typically uses `SimpleApplicationEventMulticaster` to dispatch listeners. A plain `@EventListener` runs synchronously under the default configuration; if invoked inside an active transaction, the listener's code can participate in that transaction context if it performs DB operations on the same resource.

Meanwhile, `@TransactionalEventListener` binds method execution to **a transaction phase**. When an event is published inside an active transaction, Spring registers a transaction synchronization to invoke the callback at the appropriate time.

```text
OrderService @Transactional
        |
        v
BEGIN transaction
        |
        +--> INSERT orders
        |
        +--> publisher.publishEvent(OrderPlaced)
        |          |
        |          +--> @EventListener: usually called immediately
        |          |
        |          +--> @TransactionalEventListener:
        |                    registers to wait for phase
        |
        +--> service method returns
        |
        +--> BEFORE_COMMIT callbacks (when preparing to commit)
        |
        +--> COMMIT or ROLLBACK
        |
        +--> AFTER_COMMIT / AFTER_ROLLBACK
        |
        +--> AFTER_COMPLETION
```

The diagram is a **conceptual model** for imperative transactions. Do not interpret the milestones as fixed API calls from business code: the transaction manager and synchronizations handle actual coordination.

### Four Phases to Know

| Phase | When is the handler called? | Runs on rollback? | Common purpose |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction attempts to commit | Not in a normal rollback flow; may have run before commit subsequently fails | Checks/preparations that can still affect commit |
| `AFTER_COMMIT` | After the transaction commits successfully | No | Post-processing strictly for committed data |
| `AFTER_ROLLBACK` | When the transaction rolls back | Yes | Recording failure, controlled compensation |
| `AFTER_COMPLETION` | Once the transaction completes, commit or rollback | Yes | Final cleanup/metrics/auditing |

Note: `AFTER_COMPLETION` does not automatically pass a `committed=true/false` parameter to the `@TransactionalEventListener` method. If you need to distinguish outcomes inside this callback, add another state source or use separate `AFTER_COMMIT`/`AFTER_ROLLBACK` phases.

### Default Is `AFTER_COMMIT`

```java
@TransactionalEventListener
public void on(OrderPlaced event) {
    // Equivalent to phase = TransactionPhase.AFTER_COMMIT.
}
```

If the event is published **when no transaction is active**, this listener **does not run** by default (`fallbackExecution=false`). You can set `fallbackExecution=true`, though the handler can then run outside a transactional context, which differs from "only run after commit"; define the contract clearly before using it.

## 3. Behavior Matrix to Test

Assume a service executes `INSERT orders` and then publishes `OrderPlaced` in the same transaction:

| Scenario | DB row after transaction | BEFORE_COMMIT | AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION |
| --- | --- | --- | --- | --- | --- |
| Normal commit | Exists | Yes | Yes | No | Yes |
| Exception causing rollback before commit | Does not exist | No | No | Yes | Yes |
| `BEFORE_COMMIT` listener throws causing rollback | Does not exist | Started, may throw | No | Yes | Yes |
| Unfinished test-managed transaction | May see **uncommitted** data within same transaction | Not yet | Not yet | Not yet | Not yet |
| `TestTransaction` real commit | Exists | Yes | Yes | No | Yes |
| `TestTransaction` real rollback | Does not exist | No | No | Yes | Yes |
| Event published outside transaction | No DB operation from event | No | No | No | No |

The table assumes listeners are not filtered out by conditions, no async executor is used, and the transaction manager works normally. Tests should not assert only method invocation counts; assert **the final data in the DB** and **the set of phases that actually occurred**.

In particular, **reading a row inside a transaction does not mean the row has been committed**. A transaction can read data it just wrote even if it ultimately rolls back.

## 4. Designing the Practice: Real Transactions, Not Mocked Transactions

To test these differences, we build a small project with:

- Java 17+ and Spring Boot 3.3.13.
- `spring-boot-starter-jdbc` for `JdbcTemplate` and the transaction manager.
- In-memory H2 for real commits/rollbacks without installing an external database.
- `ApplicationEventPublisher` publishing a Java record `OrderPlaced`.
- A listener bean recording all four phases into a `CopyOnWriteArrayList` **purely for observation in the demo**.
- JUnit Jupiter and Spring TestContext (via starter-test) to assert outcomes.
- `TestTransaction` to explicitly end test transactions.

**Why not just mock `PlatformTransactionManager`?** A mock returns test-fabricated results; it does not verify transaction synchronization, Spring proxies, DB commit/rollback, or `@TransactionalEventListener` registration. Unit tests remain useful for logic inside handlers, but this is an **integration test** of transaction behavior.

### 4.1. Directory Structure

```text
tx-event-testing/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/TxEventDemo.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/example/events/TxEventDemoTest.java
```

All files are shown in full below. The demo uses an in-memory DB and distinct order IDs so tests do not depend on execution order.

## 5. Runnable Java 17+ Project

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>tx-event-testing</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot manages H2, Spring JDBC, and JUnit versions via dependency management. Do not declare conflicting versions for Spring Framework modules in the same project.

### 5.2. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:tx_events_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
logging.level.root=WARN
```

This is an in-memory DB: data **must not be used for production storage** and is not preserved when the entire process/DB memory is destroyed. The `spring.sql.init.mode=always` property instructs Spring Boot to run `schema.sql` to create the table.

### 5.3. src/main/resources/schema.sql

```sql
CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
```

`IF NOT EXISTS` makes the script suitable across multiple context initializations in this practice. The `orders` table serves solely to test commits/rollbacks; it is not a full domain model.

### 5.4. src/main/java/example/events/TxEventDemo.java

```java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
@EnableTransactionManagement
public class TxEventDemo {

    // Spring can publish this POJO record.
    public record OrderPlaced(String orderId) {
    }

    // NOT final: service is proxied by Spring AOP to apply @Transactional.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String orderId, boolean forceFailure) {
            jdbc.update(
                    "INSERT INTO orders (id, status) VALUES (?, ?)",
                    orderId, "CREATED");

            // Publish while transaction has not yet committed.
            publisher.publishEvent(new OrderPlaced(orderId));

            if (forceFailure) {
                throw new IllegalStateException(
                        "simulated business failure");
            }
        }
    }

    // Only records phases in RAM to clarify callback behavior.
    public static class PhaseProbe {
        private final List<String> observed =
                new CopyOnWriteArrayList<>();

        private void add(String phase, OrderPlaced event) {
            observed.add(phase + ":" + event.orderId());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderPlaced event) {
            add("BEFORE_COMMIT", event);

            // Exercise: an exception while preparing to commit can
            // cause the transaction to roll back.
            if ("ORD-VETO".equals(event.orderId())) {
                throw new IllegalStateException(
                        "before-commit validation failed");
            }
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            add("AFTER_COMMIT", event);
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            add("AFTER_ROLLBACK", event);
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderPlaced event) {
            add("AFTER_COMPLETION", event);
        }

        public boolean has(String phase, String orderId) {
            return observed.contains(phase + ":" + orderId);
        }

        public List<String> snapshot() {
            return List.copyOf(observed);
        }

        public void clear() {
            observed.clear();
        }
    }

    @Bean
    OrderService orderService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher) {
        return new OrderService(jdbc, publisher);
    }

    @Bean
    PhaseProbe phaseProbe() {
        return new PhaseProbe();
    }

    public static int count(JdbcTemplate jdbc, String orderId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE id = ?",
                Integer.class, orderId);

        return count == null ? 0 : count;
    }

    @Bean
    CommandLineRunner scenario(
            OrderService orders,
            JdbcTemplate jdbc,
            PhaseProbe probe) {

        return args -> {
            probe.clear();
            orders.place("ORD-DEMO-C", false);

            System.out.printf(
                    "COMMIT rows=%d before=%s after=%s"
                            + " rollback=%s completion=%s%n",
                    count(jdbc, "ORD-DEMO-C"),
                    probe.has("BEFORE_COMMIT", "ORD-DEMO-C"),
                    probe.has("AFTER_COMMIT", "ORD-DEMO-C"),
                    probe.has("AFTER_ROLLBACK", "ORD-DEMO-C"),
                    probe.has("AFTER_COMPLETION", "ORD-DEMO-C"));

            probe.clear();
            try {
                orders.place("ORD-DEMO-R", true);
            } catch (IllegalStateException expected) {
                // Swallow only the error intentionally triggered in the demo.
            }

            System.out.printf(
                    "ROLLBACK rows=%d before=%s after=%s"
                            + " rollback=%s completion=%s%n",
                    count(jdbc, "ORD-DEMO-R"),
                    probe.has("BEFORE_COMMIT", "ORD-DEMO-R"),
                    probe.has("AFTER_COMMIT", "ORD-DEMO-R"),
                    probe.has("AFTER_ROLLBACK", "ORD-DEMO-R"),
                    probe.has("AFTER_COMPLETION", "ORD-DEMO-R"));
        };
    }

    public static void main(String[] args) {
        SpringApplication.run(TxEventDemo.class, args).close();
    }
}
```

### 5.5. Role of Each Component

**`OrderService`** is declared as a Spring bean. Its `place(...)` method has `@Transactional` and is invoked through the Spring-managed bean, so the transaction interceptor creates/coordinates the transaction. Do not manually instantiate `new OrderService(...)` and call `place` in a test expecting the annotation to open a transaction.

**`JdbcTemplate`** runs an `INSERT` inside the current transaction. Without a JPA persistence context or ORM-level buffering, DB state is easy to observe directly; JPA flushing semantics will be discussed separately.

**`ApplicationEventPublisher`** is called while the transaction is still open. Spring handles the `OrderPlaced` record via payload events; we do not need the record to extend `ApplicationEvent` when using `@TransactionalEventListener` methods with a matching parameter type.

**`PhaseProbe`** has four separate listener methods, each bound to one phase. The bean simply stores `PHASE:orderId` strings. It performs no HTTP requests, writes nothing to the DB after commit, and does not itself make events durable.

**`ORD-VETO`** is an intentional scenario: when the `BEFORE_COMMIT` callback encounters that order ID, it throws an exception. The corresponding test confirms the transaction **does not commit** and the rollback listener fires.

**`CommandLineRunner`** runs two scenarios on application startup, then `main` closes the context. This produces short, easy-to-inspect stdout before running tests.

### 5.6. How to Run

From the directory containing `pom.xml`, with Java 17+ and Maven:

```bash
mvn -q package
java -jar target/tx-event-testing-1.0.0.jar
```

Two lines **printed by the demo code itself**, excluding library logs:

```text
COMMIT rows=1 before=true after=true rollback=false completion=true
ROLLBACK rows=0 before=false after=false rollback=true completion=true
```

Why is the output deterministic?

1. `OrderService.place("ORD-DEMO-C", false)` finishes normally so the transaction commits; the row exists in H2, `BEFORE_COMMIT` and `AFTER_COMMIT` were called, `AFTER_ROLLBACK` did not run, and `AFTER_COMPLETION` ran.
2. For `ORD-DEMO-R`, the method throws an unchecked `IllegalStateException` **before preparing to commit**. The transaction interceptor rolls back; the DB row is reverted, `BEFORE_COMMIT` did not run, and `AFTER_ROLLBACK` and `AFTER_COMPLETION` were invoked.
3. The demo prints booleans indicating whether each phase appeared instead of dumping the raw list, so it does not depend on relative order between callbacks in the same stage.
4. The demo uses synchronous event listeners with an imperative transaction manager; there is no async executor, broker, or connection to other services.

**Scope limit:** The main program only illustrates two branches; the tests below also verify `BEFORE_COMMIT` failure, publishing without a transaction, and TestContext-managed transactions.

## 6. Integration Tests: Verifying Both Event Phases and DB State

Create `src/test/java/example/events/TxEventDemoTest.java`:

```java
package example.events;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = TxEventDemo.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TxEventDemoTest {

    @Autowired
    TxEventDemo.OrderService orders;

    @Autowired
    TxEventDemo.PhaseProbe probe;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ApplicationEventPublisher publisher;

    @BeforeEach
    void resetProbe() {
        probe.clear();
    }

    private int rows(String id) {
        return TxEventDemo.count(jdbc, id);
    }

    private void assertCommitPhases(String id) {
        assertTrue(probe.has("BEFORE_COMMIT", id));
        assertTrue(probe.has("AFTER_COMMIT", id));
        assertFalse(probe.has("AFTER_ROLLBACK", id));
        assertTrue(probe.has("AFTER_COMPLETION", id));
        assertEquals(3, probe.snapshot().size());
    }

    private void assertRollbackPhases(String id, boolean hadBefore) {
        assertEquals(hadBefore,
                probe.has("BEFORE_COMMIT", id));
        assertFalse(probe.has("AFTER_COMMIT", id));
        assertTrue(probe.has("AFTER_ROLLBACK", id));
        assertTrue(probe.has("AFTER_COMPLETION", id));
        assertEquals(hadBefore ? 3 : 2,
                probe.snapshot().size());
    }

    @Test
    void serviceCommitPersistsRowAndFiresCommitPhases() {
        String id = "ORD-TEST-C";

        orders.place(id, false);

        assertEquals(1, rows(id));
        assertCommitPhases(id);
    }

    @Test
    void serviceExceptionRollsBackAndFiresRollbackPhases() {
        String id = "ORD-TEST-R";

        assertThrows(
                IllegalStateException.class,
                () -> orders.place(id, true));

        assertEquals(0, rows(id));
        assertRollbackPhases(id, false);
    }

    @Test
    void beforeCommitExceptionPreventsCommit() {
        String id = "ORD-VETO";

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> orders.place(id, false));

        assertEquals(
                "before-commit validation failed",
                error.getMessage());
        assertEquals(0, rows(id));
        assertRollbackPhases(id, true);
    }

    @Test
    void eventOutsideTransactionIsIgnoredByDefault() {
        publisher.publishEvent(
                new TxEventDemo.OrderPlaced("ORD-NO-TX"));

        assertTrue(probe.snapshot().isEmpty());
    }

    @Test
    @Transactional
    void testTransactionCanBeCommittedExplicitly() {
        String id = "ORD-TX-COMMIT";

        assertTrue(TestTransaction.isActive());

        // @Transactional(REQUIRED) service joins the test transaction.
        orders.place(id, false);

        // Reading inside the transaction sees the uncommitted row.
        assertEquals(1, rows(id));
        assertTrue(probe.snapshot().isEmpty());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(1, rows(id));
        assertCommitPhases(id);
    }

    @Test
    @Transactional
    void testTransactionCanBeRolledBackExplicitly() {
        String id = "ORD-TX-ROLLBACK";

        assertTrue(TestTransaction.isActive());
        orders.place(id, false);

        assertEquals(1, rows(id));
        assertTrue(probe.snapshot().isEmpty());

        TestTransaction.flagForRollback();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(0, rows(id));
        assertRollbackPhases(id, false);
    }
}
```

### 6.1. Running the Tests

```bash
mvn test
```

To run only the class above:

```bash
mvn -Dtest=TxEventDemoTest test
```

The project defines **6 JUnit test methods**. When the environment and dependencies are properly configured, all six checks pass. Maven Surefire reports the actual test count, errors, and duration; do not assert verbatim framework logs because startup/log lines depend on the environment.

The tests use **a real context + real transaction manager + H2**. That differs from a unit test calling `listener.beforeCommit(event)` directly: a direct call does not prove Spring registered transaction synchronization, does not trigger commit, and does not touch the DB.

### 6.2. What Each Test Proves

| Test | Action | Evidence |
| --- | --- | --- |
| `serviceCommitPersistsRowAndFiresCommitPhases` | Calls service outside a test transaction; method returns normally | Row exists in DB; `BEFORE`+`AFTER_COMMIT`+`AFTER_COMPLETION` |
| `serviceExceptionRollsBackAndFiresRollbackPhases` | Service throws runtime exception | No row in DB; `AFTER_ROLLBACK`+`AFTER_COMPLETION` |
| `beforeCommitExceptionPreventsCommit` | `BEFORE_COMMIT` callback throws exception | Commit prevented, DB rolled back, rollback callback observed |
| `eventOutsideTransactionIsIgnoredByDefault` | Publishes record with no transaction | No phase listener runs |
| `testTransactionCanBeCommittedExplicitly` | Test-managed transaction committed via `TestTransaction` | Commit callbacks appear only after `end()`, DB commits |
| `testTransactionCanBeRolledBackExplicitly` | Test-managed transaction rolled back via `TestTransaction` | Rollback callbacks appear only after `end()`, DB rolls back |

The two tests with `@Transactional` on the method are managed by Spring TestContext. `@BeforeEach` clears the probe before every test; in transactional tests, lifecycle methods also run within the test transaction context. We do not wipe the whole table in `@BeforeEach` because distinct IDs are used; this keeps tests independent and free from execution-order assumptions.

**Note:** Boot also runs `CommandLineRunner` during test context startup. The runner uses separate IDs `ORD-DEMO-C/ORD-DEMO-R`; `@BeforeEach` clears the probe so startup traces do not leak into assertions, and each test uses distinct IDs. This is accounted for intentionally so tests can run within the same demo project.

## 7. The Biggest Trap: `@Transactional` on a Test Does Not Mean Committed

A common anti-pattern:

```java
@Test
@Transactional
void wrongAssumption() {
    orderService.place("ORD-1", false);
    assertTrue(afterCommitWasCalled);
}
```

This snippet is **not a standalone test**; it only illustrates a false assumption.

In Spring TestContext, `@Transactional` on a test method usually makes Spring open a **test-managed transaction** before executing the method and **roll it back by default when the test ends**. A service using `Propagation.REQUIRED` joins that transaction, so calling the service method **does not commit a separate transaction upon returning**.

Consequences:

1. `orderService.place(...)` executed `INSERT`, yet has not committed.
2. Spring registered the `@TransactionalEventListener` callback.
3. A DB read on the current connection/transaction can see the row.
4. `AFTER_COMMIT` **has not been called yet** at the assertion line.
5. When the test finishes, TestContext rolls back by default; the `AFTER_ROLLBACK` listener may run **after the test body**.

A test can pass if it only checks that the row was inserted inside the same transaction, even if production fails at flush/commit. This is especially common with JPA/Hibernate because writes can be deferred until flush.

### 7.1. Controlling the Transaction with `TestTransaction`

In a test with `@Transactional` and an appropriate transaction manager:

```java
TestTransaction.flagForCommit();
TestTransaction.end();
```

These two calls have distinct meanings:

- `flagForCommit()` marks the current test-managed transaction **to end with a commit**.
- `end()` **actually ends** the transaction; here `BEFORE_COMMIT`/`AFTER_COMMIT`/`AFTER_COMPLETION` callbacks can run.

Similarly:

```java
TestTransaction.flagForRollback();
TestTransaction.end();
```

flags and ends with a rollback. **Calling only `flagForCommit()` without `end()` means the test body still cannot observe the commit.**

There is also `TestTransaction.start()` to start a new test transaction after one has ended. Do not call `start()` while a test transaction is still active; understand the lifecycle and end it explicitly. In the Section 6 example, we only need one transaction and end it immediately.

### 7.2. `@Commit`, `@Rollback`, and `@AfterTransaction`

These annotations are also useful:

```java
@Test
@Transactional
@Commit
void commitAtEndOfTest() {
    // TestContext commits after the test body finishes.
}
```

```java
@Test
@Transactional
@Rollback
void rollbackAtEndOfTest() {
    // TestContext rolls back after the test body finishes.
}
```

These are **illustrative methods**, requiring imports `org.springframework.test.annotation.Commit` and `Rollback`. `@Commit` fits when you want to override the default rollback **after** the test. However, if you need to assert right **after commit inside the same method**, `TestTransaction.end()` is more convenient.

With `@AfterTransaction`, you can verify outcomes **after** the test-managed transaction finishes, or use `@BeforeTransaction` to inspect prior state. Never put `AFTER_COMMIT` assertions right in the middle of a transactional test body expecting the handler to run as soon as the service method returns.

### 7.3. Test Timeouts and Thread-Local Transactions

Spring manages imperative transactions using thread-bound context. A **preemptive** timeout mechanism can execute test code on another thread, causing DB statements to run outside the test transaction and risking real commits even while Spring rolls back the transaction on the original thread.

Avoid timeout mechanisms that run the test body on a separate worker when expecting automatic Spring TestContext rollback. Prefer non-thread-switching timeouts or explicitly control task/transaction boundaries per Spring documentation.

## 8. When the Service Transaction Differs from the Test Transaction

The examples above use the default `REQUIRED` propagation: if a transaction exists, the service joins it; otherwise, it starts a new one.

Changing propagation changes behavior as well:

| Service propagation | Effect when test already has `@Transactional` |
| --- | --- |
| `REQUIRED` | Service typically joins the test transaction; does not commit when method returns |
| `REQUIRES_NEW` | Suspends current transaction and runs a **new** transaction that can commit independently |
| `NESTED` | May use a savepoint in the same physical transaction if supported; not equivalent to a separate physical commit |
| `SUPPORTS` | Joins transaction if present; does not necessarily create a new one |
| `NOT_SUPPORTED` | Suspends current transaction; DB behavior outside transaction must be evaluated |
| `MANDATORY` | Requires an existing transaction; throws if none exists |

**Warning:** A `@Transactional` test that rolls back at the end **cannot reliably clean up changes made by `REQUIRES_NEW`**. The new transaction may commit and persist after the outer transaction rolls back. When testing services with complex propagation, use isolated IDs, a dedicated test database, or controlled cleanup.

Do not add `REQUIRES_NEW` just to "make tests pass easily". Any separate transaction must have a clear business reason; otherwise tests mask differences from production behavior.

## 9. `BEFORE_COMMIT` Failure and Rollback-Only

In the example, `PhaseProbe.beforeCommit(...)` throws an exception for `ORD-VETO`. This is an instructive scenario:

```text
place("ORD-VETO", false)
    |
    +--> INSERT orders
    +--> publish OrderPlaced
    |
    v
@Transactional service returns
    |
    v
BEFORE_COMMIT callback
    |
    +--> log BEFORE_COMMIT
    +--> throw IllegalStateException
    |
    v
Transaction manager rollback
    |
    +--> AFTER_ROLLBACK
    +--> AFTER_COMPLETION
    |
    v
Caller receives exception; orders has no ORD-VETO
```

**Key takeaway:** `BEFORE_COMMIT` can perform work that influences the commit decision. However, never attach **un-rollbackable** external side effects to `BEFORE_COMMIT` assuming they are safe; the DB commit can still fail after the remote side effect has executed.

Another way to roll back a transaction is marking it rollback-only:

```java
TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
```

This is an **illustrative snippet**, meaningful only when a Spring AOP-managed transaction status is active. If an inner participant marks a shared transaction rollback-only while the outer service still attempts to commit, Spring can throw `UnexpectedRollbackException` depending on boundaries and configuration. In tests, distinguish the exception thrown outward from **the final DB state**.

You should also test failures coming from flushes, constraints, or commits rather than only an explicit `throw new IllegalStateException(...)` in the service.

## 10. `AFTER_COMMIT`: What Can Be Trusted, What Must Not Be Inferred?

Once the source transaction has committed successfully, `@TransactionalEventListener(AFTER_COMMIT)` suits tasks such as:

- Triggering updates to a projection separate from the write model.
- Requesting a notification email once an order is genuinely saved.
- Invoking an adapter to send an integration event outward after source data commits.
- Recording metrics/audits for committed events, with a dedicated error policy.

Keep three limits in mind:

**First: `AFTER_COMMIT` does not roll back an already-committed DB.** If an email, HTTP API, or message publish fails in the callback, the order-writing transaction has already ended; you cannot "uncommit" it by throwing an exception in the listener. You must choose retries, persisted jobs, an outbox, or compensation.

**Second: a post-commit callback does not guarantee the task is durably persisted.** The process can die right after DB commit, before the listener runs or finishes. `@TransactionalEventListener` is not a transactional outbox.

**Third: transaction resources may remain bound to the thread during the callback.** Per Spring documentation, post-commit data-access operations can appear to join an old transaction, yet **new changes have no subsequent commit**. When a new DB write is needed in the callback, open an independent transaction via another service with `Propagation.REQUIRES_NEW`.

Illustrative structural example:

```java
@Component
public class OrderAuditListener {
    private final AuditWriter auditWriter;

    public OrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        auditWriter.saveAfterCommit(event.orderId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAfterCommit(String orderId) {
        repository.save(orderId);
    }
}
```

These are **two illustrative classes**, not part of the Section 5 project; they assume `AuditRepository`, `OrderPlaced`, and imports for `@Component`, `@Service`, `@TransactionalEventListener`, `TransactionPhase`, `@Transactional`, and `Propagation`. The critical point is calling from **the listener bean into a separate service bean** so the Spring proxy can open a new transaction. Calling `this.saveAfterCommit(...)` on the same bean usually bypasses the proxy.

When testing this structure, assert that the audit row **exists after** transaction commit, not just that a mock repository was called. On rollback, assert the audit row is absent. Also test failures when the new transaction cannot be created or the DB write fails.

## 11. `AFTER_ROLLBACK`: For Recording Failure, Not Undoing Rollback

`@TransactionalEventListener(AFTER_ROLLBACK)` runs after the source transaction fails. Some use cases:

- Signaling a retry in a durably stateful job layer.
- Recording rollback counts and reasons in monitoring.
- Releasing temporary resources or adding designed compensating actions.
- Investigating why a transaction failed to save an aggregate.

However, the `AFTER_ROLLBACK` handler **does not automatically know the full cause of the rollback** from the event parameter alone. The event is the object published earlier; to know the specific exception/status, correlate appropriate data or observe at the service boundary, logs, or tracing.

A rollback can stem from many causes: a service exception, a `BEFORE_COMMIT` exception, validation errors, timeouts, deadlocks, or rollback-only flags. Tests should distinguish these categories if recovery differs.

**Caution on writing audits in rollback callbacks:** Any new DB write requiring a commit must have a new transaction; it cannot depend on a rolled-back transaction and expect persistence. Never swallow all exceptions in the callback without leaving operational traces.

## 12. `AFTER_COMPLETION` and Callback Ordering

`AFTER_COMPLETION` is an observation point when a transaction finishes in either case. In the example, this phase always appears for both successful commit and rollback branches from a transaction-management standpoint.

However:

- Do not conflate `AFTER_COMPLETION` with `AFTER_COMMIT`: rollbacks trigger completion too.
- If you must distinguish commit from rollback, use dedicated phase listeners or transaction synchronization with status.
- Never treat log order between **two listeners in the same phase** as a business contract. Order among synchronizations/listeners can be configured and affected by other components.
- If two operations must run sequentially by business logic, use explicit workflow/service orchestration rather than relying solely on callback order.
- If a listener runs asynchronously or submits additional tasks, when the event callback returns does not prove child work finished.

In tests, **checking the expected set of values + count**, like `assertCommitPhases(...)` in the example, is usually much more resilient than asserting a list whose relative order is not guaranteed by contract.

## 13. Comparing `@EventListener` and `@TransactionalEventListener` on Rollback

Compare:

```java
@EventListener
public void immediate(OrderPlaced event) {
    // Typically runs immediately at publish time.
}

@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Runs only when the transaction has committed.
}
```

These are **two illustrative methods**, omitted from the demo to avoid changing probe record counts.

If the service inserts an order, publishes an event, and then throws an exception:

- `immediate(...)` **may already have executed** before rollback. If it sent an email, the email is gone.
- `afterCommit(...)` **does not run** on normal transaction rollback.
- `AFTER_ROLLBACK` runs to record the rollback.
- A synchronous `@EventListener` throwing an unchecked exception before commit can cause the transaction to roll back, though if swallowed by a multicaster `ErrorHandler` or run async, the outcome can differ.

Choose the phase based on **business consequences**: do not switch every listener to `AFTER_COMMIT` merely for "looser coupling"; each side effect has its own requirements.

## 14. Testing Async and Transactions: Two Independent Axes

In the runnable example, phase listeners are invoked synchronously. If an application uses:

```java
@Async("eventExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    remoteClient.send(event.orderId());
}
```

this is an **illustrative snippet** with an executor, `@EnableAsync`, a `remoteClient` bean, and a Spring-managed listener. Callback registration must occur inside the proper transaction-bound context; after commit, the remote call can execute on another worker.

When testing:

1. Do not assert remote side effects immediately after the service call if the method is async.
2. Use `CountDownLatch`, `Awaitility`, or polling with a timeout to wait for completion.
3. Verify that events from rolled-back transactions **do not schedule a send task**, when the contract requires `AFTER_COMMIT`.
4. Test executor rejections, shutdown, timeouts, and exception-handling paths.
5. Do not assume the publisher's imperative transaction automatically transfers to workers; it is typically thread-bound.
6. If the worker must write to the DB, open a new transaction and define retry behavior on failure.

**Important:** `@Async` only moves work to another thread; **it does not make delivery durable**. A process crash can lose queued tasks. For critical events, testing crash/restart scenarios and durable state tracking is essential.

## 15. When Events Must Not Be Lost: Transactional Outbox

`AFTER_COMMIT` guarantees **not processing rolled-back transactions**, yet leaves this gap:

```text
T1: UPDATE orders
T2: publish application event (AFTER_COMMIT registered)
T3: DB COMMIT succeeds
T4: process crash
T5: listener never got to send message to broker
```

After restart, Spring Application Events has no durable event record to replay automatically. The order data committed, yet other systems may never know.

**Transactional outbox** is commonly chosen for events that must be delivered:

```text
BEGIN DB TRANSACTION
    UPDATE orders
    INSERT outbox(eventId, type, payload, status=NEW)
COMMIT
           |
           v
Outbox relay / CDC reads committed record
           |
           +--> publish to broker
           +--> broker confirm
           +--> mark SENT / retry
           |
           v
Idempotent consumer
```

In tests:

- **Commit:** both the order and the outbox record exist.
- **Rollback:** neither the order nor the outbox record exists.
- **Broker failure:** outbox remains unfinished so the relay can retry.
- **Relay crash after publish before marking SENT:** may redeliver; consumer must deduplicate.
- **Consumer crash after side effect before ACK:** redelivery must not apply the side effect a second time.

An outbox **does not equal end-to-end exactly-once**. Retries and redeliveries can produce duplicates; you need a stable `eventId` and consumer idempotency/inbox tracking. Especially for payments, emails, or HTTP calls, a local DB transaction cannot automatically roll back external side effects.

**Section takeaway:** an `AFTER_COMMIT` test verifies **processing timing**, not the full **durability of an event pipeline**.

## 16. Common Pitfalls in Testing Commit and Rollback

**Pitfall 1 — Using `@Transactional` on the test and expecting `AFTER_COMMIT` right after the service call.** A `REQUIRED` service joins the test transaction; it has not committed yet. Use `TestTransaction.end()` or a test without an enclosing transaction.

**Pitfall 2 — Asserting only that `repository.save(...)` was called.** Mockito `verify` does not prove the DB committed. Use H2/a test database and query after the transaction ends.

**Pitfall 3 — Seeing a row inside the same transaction and concluding it committed.** Re-read outside the transaction or verify across a real transaction boundary.

**Pitfall 4 — Calling the listener method directly.** Bypasses Spring event dispatch and transaction synchronization. Direct unit calls are only for isolated handler logic.

**Pitfall 5 — Calling `TestTransaction.flagForCommit()` and forgetting `end()`.** Flagging commit does not run callbacks immediately; the transaction stays active.

**Pitfall 6 — Using `@Commit` to assert `AFTER_COMMIT` inside the test body.** `@Commit` takes effect when the test ends, so the body cannot observe the callback yet. Use `@AfterTransaction` or `TestTransaction` when needed.

**Pitfall 7 — Forgetting to test publishing outside a transaction.** `@TransactionalEventListener` skips by default; test explicitly rather than blindly enabling fallback.

**Pitfall 8 — Putting transaction annotations on private/final/self-invoked methods and expecting proxying.** Check how Spring manages the bean and invoke through the proxy.

**Pitfall 9 — Asserting only the exception while ignoring DB state.** An exception from `AFTER_COMMIT` can occur after data already committed; an exception alone does not prove rollback.

**Pitfall 10 — Writing to the DB inside `AFTER_COMMIT` without opening a new transaction.** Old transaction resources may still be bound to the thread, yet no commit remains for new changes. Use a `REQUIRES_NEW` service via proxy.

**Pitfall 11 — Using log order between listeners as proof.** Multiple listeners, async, or synchronizations can yield different orderings. Assert states/phases rather than relying on log order without an ordering contract.

**Pitfall 12 — Using `sleep` to wait for async listeners.** Flaky tests; use latches/polling with timeouts and watch executor errors.

**Pitfall 13 — Forgetting JPA flush.** ORM tests may defer SQL/constraint checks until flush; call `entityManager.flush()` where appropriate to avoid false positives.

**Pitfall 14 — Implicitly assuming `afterRollback` knows the root cause.** The phase only indicates the transaction rolled back; it does not pass the original exception. Use dedicated correlation/observability.

**Pitfall 15 — Treating `AFTER_COMMIT` as an outbox.** The process can die after commit before sending the message. Use a durable outbox when events must not be lost.

**Pitfall 16 — Letting `REQUIRES_NEW` pollute test data.** An independent transaction can commit even when the test transaction rolls back. Clean up fixtures properly and verify isolation.

**Pitfall 17 — Using a preemptive timeout that switches the test thread.** Can run code outside the test-managed transaction so rollback no longer protects the DB. Avoid incompatible timeout mechanisms.

## 17. Checklist Before Finishing This Practice

1. Is the test calling the **Spring-managed service proxy** rather than a manually instantiated object?
2. Is the event published **inside or outside a transaction**?
3. Is the listener a plain `@EventListener` or `@TransactionalEventListener`?
4. Is the phase declared explicitly, knowing the default is `AFTER_COMMIT`?
5. Do tests distinguish normal commit, exception-induced rollback, and rollback caused by a failing `BEFORE_COMMIT` callback?
6. Are tests asserting **DB state after the transaction ends** rather than reading uncommitted rows?
7. If a test has `@Transactional`, does it explicitly call `TestTransaction.end()` when observing callbacks?
8. Do you understand TestContext's default rollback and the roles of `@Commit`/`@Rollback`?
9. Have you tested out-of-transaction publishing with `fallbackExecution=false`?
10. Have you tested `AFTER_COMPLETION` for both commit and rollback?
11. If an after-commit callback writes to the DB, does it use an appropriate new proxied transaction?
12. If async is involved, do tests wait with timeouts and capture exceptions?
13. Have you distinguished pre-commit exceptions from post-commit processing exceptions?
14. Have you tested rollbacks for validation errors, deadlocks/constraints, or rollback-only policies?
15. With JPA, have you flushed/cleared when verifying committed state or constraint violations?
16. If an event must reach a broker, have you designed an outbox, broker confirms, retries, and idempotency?
17. Do tests use isolated IDs/data, avoid execution-order dependencies, and avoid leftover records from new transactions?
18. Are metrics/logs tracked by event ID, transaction outcome, phase, latency, and handler outcome without leaking sensitive data?

**Remember:** A sound Spring Application Events test must know **which transaction is real, who terminates it, and which phase invokes the listener**. Use integration tests with a real database and `TestTransaction` to verify both callbacks and commit/rollback state. When cross-service delivery is required, add durable event persistence: `AFTER_COMMIT` solves timing, not transactional outbox durability.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, phases, fallback, and transaction resource notes.
- [Spring Framework — Transaction Management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test transactions, default rollback, `TestTransaction`, `@Commit`, `@Rollback`, and `@AfterTransaction`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` and listener dispatch.
- [Spring Framework — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): `phase`, `fallbackExecution`.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `flagForCommit()`, `flagForRollback()`, `end()`, and `start()`.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC/H2 and schema initialization.
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/): lifecycle, assertions, and running tests.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): dual-write gap and relay mechanics.
