# Testing AFTER_COMMIT and Rollback in Spring Framework Application Events

## 1. Goal: Proving Events Are Handled According to **Actual Transaction Outcomes**

When a Spring application publishes a domain event inside a database transaction, two separate questions arise:

1. **Was the event published?** The **ApplicationEventPublisher.publishEvent(...)** call can happen before the database commits.
2. **Did the transaction ultimately commit or roll back?** That outcome determines whether reactions such as sending notifications, updating projections, or calling an external system should run.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** lets a listener be invoked **after the transaction bound to the event commits successfully**. Conversely, **AFTER_ROLLBACK** targets the rollback branch; **AFTER_COMPLETION** targets both outcomes. To test properly, you must **explicitly drive the transaction to completion** and check both events and data state, rather than merely calling the listener method or seeing a "published" log.

This article focuses on **Spring Framework Application Events**, under the **Event Testing** group. You will learn:

- How **@TransactionalEventListener** registers callbacks, and the timing differences between **@EventListener** and **AFTER_COMMIT**.
- How to design a **test matrix** for commit, rollback-only, exception rollback, outside-transaction, and `fallbackExecution`.
- Two testing strategies: **TransactionTemplate** with a real transaction and **@Transactional test + TestTransaction**.
- A runnable **Java 17+**, **Spring Framework 6.2.9**, **H2**, **JUnit Jupiter 5** project using Gradle to execute integration tests.
- Traps: default test rollback; **@MockBean / direct method calls** not simulating the listener adapter; **REQUIRES_NEW**, **@Async**, transaction propagation, database visibility, false positives, and durability.

**Rule:** An assertion "listener has not run yet" while the transaction **is still open** does not prove the listener will **never** run; it may be waiting for commit. And asserting "`publishEvent()` was called" does not prove the transaction committed.

## 2. Recap of Transaction-Bound Event Mechanics

A regular listener:

~~~java
@EventListener
public void on(OrderPlaced event) {
    // With the default synchronous multicaster, typically runs right at publish.
}
~~~

A phase-bound listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Spring invokes this after the transaction bound to the event commits successfully.
}
~~~

Both snippets above are **illustrative only**; they require corresponding imports, Spring-managed beans, and the **OrderPlaced** event type.

If the service is inside a transaction:

~~~text
BEGIN TRANSACTION
   |
   +-- INSERT order
   |
   +-- publisher.publishEvent(OrderPlaced)
   |       |
   |       +-- @EventListener                   -> typically runs immediately
   |       |
   |       +-- @TransactionalEventListener
   |                -> registers transaction synchronization
   |
   +-- business method returns
   |
   +-- COMMIT succeeds
                |
                +-- BEFORE_COMMIT callback (before actual commit)
                +-- AFTER_COMMIT listener
                +-- AFTER_COMPLETION listener
~~~

**Do not read the diagram above as an absolute call schedule for every callback:** **BEFORE_COMMIT** belongs to the pre-commit step; **AFTER_COMMIT** and **AFTER_COMPLETION** happen during transaction completion. Exact synchronization ordering can be influenced by configuration and **@Order**. What to test is that **AFTER_COMMIT belongs solely to the successful commit branch**; **AFTER_ROLLBACK belongs solely to the rollback branch**.

If the transaction ultimately rolls back:

~~~text
BEGIN TRANSACTION
   |
   +-- INSERT order
   +-- publish OrderPlaced
   +-- regular @EventListener already ran
   |
   +-- setRollbackOnly() or exception causing rollback
   |
   +-- ROLLBACK
          |
          +-- AFTER_ROLLBACK listener
          +-- AFTER_COMPLETION listener
          +-- DO NOT invoke AFTER_COMMIT listener
          +-- INSERT order does not exist after rollback
~~~

**Important:** an event published **before rollback** does not vanish from memory/logs automatically. A **synchronous @EventListener** may already have performed an external side effect before the transaction rolls back. **@TransactionalEventListener(AFTER_COMMIT)** ties reactions to the outcome, though it is not itself a durable message queue.

## 3. Transaction Phases to Distinguish

| Phase | When Is It Processed? | Runs on Rollback? | What to Test |
| --- | --- | --- | --- |
| **BEFORE_COMMIT** | Before the transaction performs commit, as the commit path proceeds | Usually **no** if rolled back before commit | Called on commit path and not called on rollback-only |
| **AFTER_COMMIT** | After successful commit | **No** | Event present only on commit path; DB changes committed |
| **AFTER_ROLLBACK** | After rollback | **Yes** | Event present on rollback path; DB changes absent |
| **AFTER_COMPLETION** | After completion, commit or rollback | **Yes** | Both branches receive the event |
| **Regular @EventListener** | When the event is dispatched, synchronous by default | May **already have run** prior to rollback | Distinguish "published" from "committed" |

**@TransactionalEventListener** defaults to **AFTER_COMMIT** when **phase** is unspecified. In programs using imperative **PlatformTransactionManager**, it binds to the active transaction on the thread at the moment the event is emitted.

### What Happens If Published Without a Transaction?

By default **fallbackExecution=false**: transactional event listeners are **not invoked** when no matching transaction is active. If **fallbackExecution=true** is declared, the listener is permitted to handle the event **even without a transaction**, usually immediately at publish time per the dispatch mechanism.

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void withFallback(OrderPlaced event) {
    // Inside transaction: waits for commit.
    // Outside transaction: processes via fallback right on dispatch.
}
~~~

Therefore, with **fallbackExecution=true**, you cannot say "this listener always proves the DB committed." Only invocations originating from a **genuinely active transaction** carry `AFTER_COMMIT` semantics.

## 4. Minimum Required Test Matrix

| Scenario | Regular @EventListener | AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION | DB row |
| --- | --- | --- | --- | --- | --- |
| Publish **inside transaction**, then **commit** | Yes | **Yes** | No | Yes | **Present** |
| Publish **inside transaction**, call **setRollbackOnly()** | Yes | **No** | **Yes** | Yes | **Absent** |
| Publish then transaction throws **RuntimeException** | Yes, if published before exception | **No** | **Yes** | Yes | **Absent** |
| Publish **outside transaction** | Yes | **No** (default) | No | No | No DB operation in this test |
| Publish outside transaction with **fallbackExecution=true** | Unchanged regular listener behavior | Fallback listener **does run** | Per each listener's annotation | Per each listener's annotation | Unrelated to commit |
| Publish in **@Transactional test** where test ends with default rollback | Yes | **No** | **Yes** when test transaction ends | Yes on completion | Writes are rolled back |
| **@Transactional test** calling TestTransaction.flagForCommit(); end() | Yes | **Yes after end()** | No | Yes | Data committed |

**Do not misread the "DB row" column:** this is the state of the database change made inside the transaction **in the concrete example**. In-memory events may already have been delivered to non-transactional listeners before the DB commits.

## 5. Biggest Mistake: `@Transactional` Tests Roll Back by Default

In Spring TestContext Framework, a test method/class annotated **@Transactional** runs inside a **test-managed transaction** if a transaction manager and matching test listener are present. **By default Spring rolls back the transaction when the test ends**, to keep the test database clean.

~~~java
@Test
@Transactional
void misleadingTest() {
    service.createOrderAndPublishEvent();

    // Wrong if expecting AFTER_COMMIT already ran here:
    // the Spring Test-managed transaction is still active.
    verify(notificationSender).send(...);
}
~~~

This is an explanatory **counterexample**; not a standalone runnable class. Two issues:

1. While the test method is running, the transaction has not committed yet, so **a properly designed AFTER_COMMIT listener must not have run yet**.
2. When the test ends, Spring Test defaults to **rollback**; thus the `AFTER_COMMIT` listener never runs after the test.

Many tests are misdiagnosed as "listener broken" simply because this is forgotten. Or tests verify only the publisher and report PASS without ever attempting a commit.

### Controlling Execution with TestTransaction

Inside a test-managed transaction, Spring Test provides:

- **TestTransaction.isActive()**: checks whether a test transaction is active.
- **TestTransaction.isFlaggedForRollback()**: inspects the flagged outcome.
- **TestTransaction.flagForCommit()**: flags the current transaction to commit upon ending.
- **TestTransaction.flagForRollback()**: flags rollback.
- **TestTransaction.end()**: ends **immediately** and commits/rolls back per the flag, enabling post-completion assertions.
- **TestTransaction.start()**: starts a new test-managed transaction if needed after the previous one ended.

Standard testing pattern:

~~~java
@Test
@Transactional
void verifyAfterCommit() {
    service.createOrderAndPublishEvent();
    assertFalse(recorder.afterCommitReceived());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertTrue(recorder.afterCommitReceived());
}
~~~

This is a **snippet** requiring corresponding classes/test fixtures. **flagForCommit() alone does not commit**; only **end()** or Spring Test concluding the transaction actually executes the outcome.

**@Commit** or **@Rollback(false)** can also alter end-of-test behavior, yet when asserting inside **the same test method** right after commit, **TestTransaction.end()** is clearer. A test that truly commits leaves data behind unless cleaned up properly; use an isolated test database and unique IDs.

## 6. Runnable Java 17+ Project: Spring Transaction + H2 + JUnit Jupiter

This example uses **Spring Framework 6.2.9**, **JDK 17+**, **Gradle 8.x**, **JUnit Jupiter 5.11.4**, and **H2 2.3.232**. No Spring Boot, web server, or broker is required.

We use:

- **DriverManagerDataSource** and **JdbcTemplate** for observable database changes.
- **DataSourceTransactionManager** and **TransactionTemplate** for exact commit/rollback control.
- A listener bean with **@EventListener** and **@TransactionalEventListener** methods across multiple phases.
- **Set**s recording seen event IDs to assert by ID without depending on callback order or test execution order.
- Two integration test files: one explicitly driving transactions via **TransactionTemplate**, and one using **@Transactional test + TestTransaction**.

**Order-independent tests:** each test uses a **new UUID**, so the in-memory database and recorder can be cached by Spring TestContext across tests without ID collisions.

### 6.1. Directory Structure

~~~text
after-commit-test-demo/
  build.gradle
  src/test/java/demo/PhaseListenerIntegrationTest.java
  src/test/java/demo/TestManagedTransactionTest.java
~~~

Contents of **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework:spring-context:6.2.9'
    testImplementation 'org.springframework:spring-jdbc:6.2.9'
    testImplementation 'org.springframework:spring-test:6.2.9'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'com.h2database:h2:2.3.232'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
~~~

**Java 17+** is required for Spring Framework 6.x. **Gradle 8.x** runs with a compatible JDK; all dependencies here are for tests because the example has no application `main`. The command in section 6.4 runs **JUnit tests**, not **gradle run**.

### 6.2. File 1: PhaseListenerIntegrationTest.java

Contents of **src/test/java/demo/PhaseListenerIntegrationTest.java**:

~~~java
package demo;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import javax.sql.DataSource;

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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PhaseListenerIntegrationTest.Config.class)
public class PhaseListenerIntegrationTest {

    // Plain Java POJO event: no need to extend ApplicationEvent.
    public record OrderPlaced(String id) {}

    public static final class Recorder {
        final Set<String> immediate = ConcurrentHashMap.newKeySet();
        final Set<String> beforeCommit = ConcurrentHashMap.newKeySet();
        final Set<String> afterCommit = ConcurrentHashMap.newKeySet();
        final Set<String> afterRollback = ConcurrentHashMap.newKeySet();
        final Set<String> afterCompletion = ConcurrentHashMap.newKeySet();
        final Set<String> withFallback = ConcurrentHashMap.newKeySet();

        @EventListener
        public void immediate(OrderPlaced event) {
            immediate.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderPlaced event) {
            beforeCommit.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            afterCommit.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            afterRollback.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderPlaced event) {
            afterCompletion.add(event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true)
        public void withFallback(OrderPlaced event) {
            withFallback.add(event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:after_commit_event_test;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            jdbc.execute(
                    "CREATE TABLE IF NOT EXISTS demo_orders "
                    + "(id VARCHAR(64) PRIMARY KEY)");
            return jdbc;
        }

        @Bean
        Recorder recorder() {
            return new Recorder();
        }
    }

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Recorder events;

    private TransactionTemplate tx() {
        return new TransactionTemplate(transactionManager);
    }

    private int rows(String id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders WHERE id = ?",
                Integer.class, id);
    }

    @Test
    void afterCommitRunsOnlyAfterSuccessfulCommit() {
        String id = UUID.randomUUID().toString();

        tx().executeWithoutResult(status -> {
            jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
            publisher.publishEvent(new OrderPlaced(id));

            // Published, yet the transaction has not committed.
            assertTrue(events.immediate.contains(id));
            assertFalse(events.beforeCommit.contains(id));
            assertFalse(events.afterCommit.contains(id));
            assertFalse(events.afterRollback.contains(id));
            assertFalse(events.withFallback.contains(id));
        });

        // TransactionTemplate completed the commit.
        assertTrue(events.beforeCommit.contains(id));
        assertTrue(events.afterCommit.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertTrue(events.withFallback.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertEquals(1, rows(id));
    }

    @Test
    void rollbackOnlyDoesNotTriggerAfterCommit() {
        String id = UUID.randomUUID().toString();

        tx().executeWithoutResult(status -> {
            jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
            publisher.publishEvent(new OrderPlaced(id));
            assertTrue(events.immediate.contains(id));

            status.setRollbackOnly();
        });

        assertFalse(events.beforeCommit.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertFalse(events.withFallback.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    void exceptionRollsBackAndSkipsAfterCommit() {
        String id = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class, () ->
                tx().executeWithoutResult(status -> {
                    jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
                    publisher.publishEvent(new OrderPlaced(id));
                    throw new IllegalStateException("force rollback");
                }));

        assertTrue(events.immediate.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    void outsideTransactionOnlyImmediateAndFallbackRun() {
        String id = UUID.randomUUID().toString();

        publisher.publishEvent(new OrderPlaced(id));

        assertTrue(events.immediate.contains(id));
        assertTrue(events.withFallback.contains(id));
        assertFalse(events.beforeCommit.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertFalse(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }
}
~~~

**Setup explanation:**

- **@SpringJUnitConfig** integrates JUnit Jupiter with Spring TestContext, loading **Config** as the `ApplicationContext`.
- **DataSourceTransactionManager** manages JDBC transactions on the same **DataSource** used by **JdbcTemplate**. Because a real database transaction is used, committed or rolled-back data can be verified.
- **Recorder** is a Spring-managed bean; the adapter handling **@TransactionalEventListener** annotations is initialized in the context. Calling **publisher.publishEvent(...)** inside **TransactionTemplate** triggers synchronization registration on the right thread.
- `Recorder` uses separate **Set**s per phase and each test uses a **unique UUID**. Tests do not depend on method order or clearing other tests' state.
- **withFallback** receives the event on commit as well as outside transactions; on the rollback branch it does **not** run merely because fallback is enabled.
- Calling **status.setRollbackOnly()** makes `TransactionTemplate` finish with a rollback even though the callback threw no exception.
- When the callback throws **IllegalStateException**, `TransactionTemplate` performs a rollback and propagates the exception to the caller, suitable for failure-path testing.

### 6.3. File 2: TestManagedTransactionTest.java

This file illustrates Spring TestContext's special behavior when the test method itself has **@Transactional**. Contents of **src/test/java/demo/TestManagedTransactionTest.java**:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PhaseListenerIntegrationTest.Config.class)
public class TestManagedTransactionTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PhaseListenerIntegrationTest.Recorder events;

    private int rows(String id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders WHERE id = ?",
                Integer.class, id);
    }

    @Test
    @Transactional
    void defaultTestTransactionRollsBack() {
        String id = UUID.randomUUID().toString();

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
        publisher.publishEvent(
                new PhaseListenerIntegrationTest.OrderPlaced(id));

        // Cannot conclude the listener is broken: the transaction is still open.
        assertTrue(events.immediate.contains(id));
        assertFalse(events.afterCommit.contains(id));

        // Ends according to the default rollback flag.
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertFalse(events.afterCommit.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    @Transactional
    void explicitlyCommitTestTransaction() {
        String id = UUID.randomUUID().toString();

        assertTrue(TestTransaction.isActive());

        jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
        publisher.publishEvent(
                new PhaseListenerIntegrationTest.OrderPlaced(id));

        assertFalse(events.afterCommit.contains(id));

        // flagForCommit only marks it; end() actually commits.
        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(events.afterCommit.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertEquals(1, rows(id));
    }
}
~~~

With **@Transactional** on the test method, Spring TestContext creates a **test-managed transaction**. **TestTransaction.end()** forces transaction completion right inside the test, allowing post-completion callback verification. Do not slap **@Transactional** onto every test mechanically; when using **TransactionTemplate** to drive commit/rollback, avoid letting an outer test-managed transaction swallow `TransactionTemplate`'s commit.

### 6.4. Running and Understanding Results

In the **after-commit-test-demo** directory, with Java 17+ and Gradle 8.x:

~~~bash
gradle --console=plain test
~~~

Expect **6 tests to pass**: 4 tests in **PhaseListenerIntegrationTest** and 2 tests in **TestManagedTransactionTest**. Gradle may display test names differently depending on configuration, while the logical outcomes to check are:

~~~text
COMMIT                 -> AFTER_COMMIT: yes; AFTER_ROLLBACK: no;  DB rows: 1
ROLLBACK_ONLY          -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
EXCEPTION_ROLLBACK     -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
OUTSIDE_TRANSACTION    -> fallback: yes;  ordinary AFTER_COMMIT: no
TEST_DEFAULT_ROLLBACK  -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
TEST_EXPLICIT_COMMIT   -> AFTER_COMMIT: yes; AFTER_ROLLBACK: no;  DB rows: 1
~~~

The block above is a **summary table of expected test behavior**, **not stdout printed by the program**. The tests have no matching **System.out.println()**; Gradle displays JUnit results and build status per version. A successful run finishes with **BUILD SUCCESSFUL**.

Detailed Gradle reports normally reside in **build/reports/tests/test/index.html**; if a test fails, check which assertion failed and its stack trace before concluding Spring lacks `AFTER_COMMIT` support.

**QA note:** Results do not rely on fixed sleeps or waiting on executors. Listeners in the demo are all **synchronous**; once **TransactionTemplate.executeWithoutResult(...)** or **TestTransaction.end()** returns, phase callbacks have already been coordinated by the transaction manager. The demo does not require **@EnableAsync**.

## 7. Reading Test Outcomes Properly

### 7.1. Commit Test Proves Three Distinct Things

In **afterCommitRunsOnlyAfterSuccessfulCommit()**, we assert:

1. After **publishEvent(...)** while the transaction is still open: **immediate** received the event; **afterCommit** does not have it yet.
2. After `TransactionTemplate` completes: **afterCommit** and **afterCompletion** received the event; **afterRollback** did not.
3. **SELECT COUNT(*)** outside the transaction returns **1**, proving the row genuinely exists after commit.

Do not just verify a mock method was called and assume data definitely committed.

### 7.2. Rollback Test Verifies Events Do Not Leak Through the Commit Branch

In **rollbackOnlyDoesNotTriggerAfterCommit()**, the test deliberately sets rollback-only. When the test is accurate:

- **Regular @EventListener** was already invoked prior to rollback.
- **AFTER_COMMIT** and commit-phase-bound fallback listeners **do not run**.
- **AFTER_ROLLBACK** and **AFTER_COMPLETION** run.
- The database row **does not exist** after rollback.

That way, the test distinguishes **"no post-commit effect"** from "the event was never published."

### 7.3. Exception Rollback Is an Independent Scenario

A service may throw a runtime exception **after publishing an event**. `TransactionTemplate` rolls back and propagates the error to the caller. Tests must verify all three: **the exception**, **AFTER_ROLLBACK**, and **DB row count = 0**.

If an exception occurs **before** the event is published, a listener cannot be expected to receive a non-existent event. When writing tests, intentionally place publish before the exception when verifying rollback callbacks.

### 7.4. Outside Transaction and `fallbackExecution`

The **outsideTransactionOnlyImmediateAndFallbackRun()** scenario proves:

- Regular listeners receive the event.
- Listeners with **fallbackExecution=true** receive the event even without a transaction.
- Other transaction-phase listeners do not run because no valid transaction exists.

This is an **important semantic test**: if a business rule must guarantee "act only after commit," think carefully about whether fallback should be enabled. Enabling fallback can cause the listener to run even when a publisher accidentally bypasses a transaction.

## 8. Why Is `TestTransaction` More Useful Than `@Commit` Alone?

**@Commit** (or **@Rollback(false)**) changes the outcome when a test-managed transaction ends, yet the default end time is **after the test method returns**. Consequently, inside a test method still within the transaction, asserting **afterCommit** can fail even when the listener works properly.

**TestTransaction.flagForCommit(); TestTransaction.end()** cleanly separates three moments:

~~~text
test starts
  |
  +-- test-managed transaction active
  +-- service publishes event
  +-- assert AFTER_COMMIT listener has not run
  |
  +-- TestTransaction.flagForCommit()
  +-- TestTransaction.end()
         |
         +-- actual commit
         +-- AFTER_COMMIT callback
  |
  +-- assert AFTER_COMMIT was invoked
  +-- assert data has committed
~~~

To test the rollback branch: **TestTransaction.end()** with the default rollback flag, or **flagForRollback()** then **end()**.

**Never call TestTransaction.end() when no test-managed transaction is active.** This API belongs to **Spring TestContext**; it does not replace `TransactionTemplate` in production code. If you need to keep working inside a fresh test-managed transaction after **end()**, you can call **TestTransaction.start()**, bearing in mind that data committed in the earlier transaction is not automatically rolled back by the next transaction.

In tests with **@Transactional**, **@BeforeEach** and **@AfterEach** lifecycles also typically run inside the test-managed transaction. With **@BeforeTransaction** and **@AfterTransaction**, you can inspect or prepare outside the transaction when needing to check DB state before or after the transaction. Do not use **@BeforeAll** assuming a test-managed transaction exists.

## 9. Avoiding False-Positive Tests When Using Mocks

A unit test such as:

~~~java
OrderListener listener = new OrderListener(notificationSender);
listener.on(new OrderPlaced("A"));
verify(notificationSender).send("A");
~~~

only proves **the Java method was called directly**. It **does not prove** Spring registered **@TransactionalEventListener** or waited for commit, because the test completely bypasses **ApplicationEventPublisher**, listener adapters, and transaction synchronization.

If you want to test logic inside a listener, direct unit tests are still useful. Yet to prove **AFTER_COMMIT/rollback**, you need an **integration test** through a Spring `ApplicationContext` and a transaction manager.

### Which Parts Should Be Mocked Appropriately?

- **Business logic unit tests**: mock repositories/gateways to verify decisions.
- **Transaction semantics integration tests**: use a real transaction manager and real event publisher.
- **External side effects**: you may replace email/SMS/payment gateways with a **fake recorder** to assert callbacks run at the right time.
- **Database**: H2 is great for learning, though cases depending on isolation, triggers, dialects, unique constraints, or production DB behavior should be verified further with PostgreSQL/MySQL in Testcontainers or an equivalent environment.

A test verifying only **publisher.publishEvent(...) was called once** is a publication test, not an `AFTER_COMMIT` test.

## 10. Distinguishing Application-Managed, Test-Managed, and Nested Transactions

### 10.1. TransactionTemplate Inside a Non-`@Transactional` Test

This is the clearest approach when you just want to test commit/rollback:

~~~java
txTemplate.executeWithoutResult(status -> {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.id()));
});
assertTrue(recorder.wasReceivedAfterCommit(order.id()));
~~~

`TransactionTemplate` actively opens and closes the transaction. Assertions after `execute` run **after completion**. The snippet requires matching test fixtures and classes.

### 10.2. TransactionTemplate Inside an `@Transactional` Test

If the test method already has **@Transactional** and `TransactionTemplate` defaults to **PROPAGATION_REQUIRED**, the template may **join the already-open transaction** rather than creating its own commit. When the template returns, the outer test transaction has not ended yet; `AFTER_COMMIT` listeners must still wait, and the end of the test may roll back.

Therefore, do not accidentally combine both and expect **TransactionTemplate.execute(...)** inside the test to have committed. Pick one clear strategy: a **non-`@Transactional`** test method, or **TestTransaction** to end the outer transaction.

### 10.3. `REQUIRES_NEW` Has an Independent Transaction Outcome

An application service method with **Propagation.REQUIRES_NEW** can open a new transaction independent of the outer transaction. If an event is published **inside the new transaction**, `AFTER_COMMIT` binds to **the new transaction**, not the outer transaction.

Logical example:

~~~text
outer TX starts
   |
   +-- inner REQUIRES_NEW TX starts
   |       -> save row
   |       -> publish EventInner
   |       -> COMMIT inner
   |           -> AFTER_COMMIT(EventInner) runs
   |
   +-- outer TX later ROLLBACK
~~~

The outer transaction rolling back **does not automatically revoke the inner commit**. If you are writing a test requiring "no event is emitted when the entire use case fails," inspect the actual transaction-boundary contract rather than looking at annotations on one method alone.

In addition, **self-invocation** calling one method from another in the same bean typically bypasses Spring proxies; **@Transactional(REQUIRES_NEW)** may not be applied as expected. Tests of transaction propagation should go through a real Spring-managed proxy or use `TransactionTemplate` with propagation configured directly.

## 11. Can `AFTER_COMMIT` Write Further Database Changes Directly?

An advanced trap: at **AFTER_COMMIT**, the original database transaction has committed, yet **transactional resources** may remain bound/accessible during completion. Spring Javadoc warns: if a callback accesses data during **AFTER_COMMIT / AFTER_ROLLBACK / AFTER_COMPLETION**, code may still "participate" in the old transaction resources, yet **new changes are not committed** as an independent transaction.

Thus, the following snippet is easily misunderstood:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    auditRepository.save(new AuditRecord(event.id()));
}
~~~

**This is a counterexample about transaction assumptions**, not standalone code. Calling `save` inside a post-commit callback does not automatically guarantee a new commit.

If you must write an audit record after commit in a separate transaction, usually place the DB operation inside **another Spring-managed service** with **@Transactional(propagation = Propagation.REQUIRES_NEW)**, invoked via proxy:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(String id) {
        // Write audit in a new transaction.
    }
}
~~~

The snippet requires corresponding imports and repositories. **REQUIRES_NEW** also incurs connection pool and separate transaction overhead; consider failures in the callback after the main transaction already committed. Never market `AFTER_COMMIT` as guaranteeing eventual delivery or atomicity between DB and email/brokers.

### Additional Tests If Writing DB Changes in `AFTER_COMMIT`

An integration test should:

1. Commit the main transaction that published the event.
2. Assert the `AFTER_COMMIT` listener ran.
3. Use **a new transaction** to read the audit row, confirming it was genuinely **committed**, not merely sitting in an old persistence context.
4. Simulate an audit writer failure, verifying the main transaction still committed and the system has retry/monitoring policies.
5. If audit data must be atomic with business data, consider writing the audit **before commit in the same DB transaction** rather than relying on an after-commit callback.

## 12. `AFTER_COMMIT` Does Not Guarantee Events Survive Crashes

**@TransactionalEventListener(AFTER_COMMIT)** is only a callback tied to an active transaction. After the DB commits yet before the listener finishes, the JVM can crash; if the listener needs to send an important notification or integration event, in-memory-only work can be lost.

A more resilient design is the **transactional outbox**:

~~~text
BEGIN DB TRANSACTION
  -> save order
  -> save outbox(eventId, aggregateId, payload)
COMMIT
  -> outbox worker reads row
  -> send message / retry on failure
  -> mark row delivered
consumer -> idempotent processing
~~~

**The outbox row and business state** are written in the same transaction. If the transaction rolls back, both roll back; if it commits, the worker can replay after restarts. Duplicate message sending can still happen if the worker sends successfully before marking delivered, so **idempotency** is mandatory.

**Testing an outbox differs from testing `AFTER_COMMIT`:** you must verify atomic commit/rollback of both tables, worker state after crashes, duplicate processing, and retry capability; a listener unit test is insufficient.

## 13. Situations Where `AFTER_COMMIT` Tests Easily Go Wrong

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Test method has default-rollback **@Transactional** | `AFTER_COMMIT` doesn't run; looks like broken listener | Use **TestTransaction.flagForCommit(); end()** or **@Commit** with post-transaction assertions |
| Asserting listener right after publish while transaction is still open | False negative | Complete commit before asserting |
| Calling listener method directly | Unit test passes yet phase is never tested | Publish via **ApplicationEventPublisher** + Spring context |
| Verifying only that publisher was called | Unknown whether listener ran before or after commit | Assert recorder and DB state after transaction |
| Publishing outside a transaction | Transactional listener is skipped | Create a real transaction; understand **fallbackExecution** |
| Enabling `fallbackExecution` while treating every callback as post-commit | Can run immediately outside transactions | Test the outside-transaction path separately |
| Using `TransactionTemplate REQUIRED` inside an `@Transactional` test | Template joins outer transaction; has not committed | Remove `@Transactional` from test or use `TestTransaction` |
| Mocking the transaction manager improperly | Callback does not bind to a real transaction | Use a real transaction manager in integration tests |
| Testing events emitted by a service before throwing an exception | Regular `@EventListener` ran even though DB rolled back | Use the appropriate transactional phase |
| Asserting only handler invocation count without checking DB | Atomicity unverified | Check row count outside the transaction |
| Testing `@Async` with immediate assertions | Flaky test; executor not finished | Use Awaitility/`CountDownLatch` and proper executor |
| `AFTER_COMMIT` writes DB without opening a new transaction | Audit row may not commit | Use `REQUIRES_NEW` and verify in an independent transaction |
| Not distinguishing `REQUIRES_NEW` from outer TX | Inner commits event even if outer rolls back | Test each transaction boundary |
| Confusing `RuntimeException` with checked exception default rollback | Unexpected outcome | Define rollback rules; test checked exceptions too if required |
| Using H2 and assuming prod DB has identical isolation/trigger behavior | Green tests yet production differs | Testcontainers/real DB for dialect-dependent cases |
| Missing event IDs or test isolation | Order-dependent tests, colliding assertions | Use unique IDs and isolated data |
| Treating listeners as a guaranteed delivery system | Crash after commit still loses tasks | Outbox/queue + retries/idempotency |

## 14. `@Async` and Reactive Transactions: Test Scope Limits

### 14.1. Async Event Listeners

**@Async** hands processing off to an executor. Imperative transaction context is typically thread-bound and **not propagated automatically** to worker threads. With **@TransactionalEventListener**, callback registration binds to the transaction when the event is emitted; do not assume adding **@Async** means the original transaction exists inside the worker.

When testing a listener that **runs asynchronously after commit**, beyond transaction outcomes you must verify:

- **No post-commit work is scheduled on rollback**.
- After commit, the task was submitted to the proper executor.
- Wait for listener completion using **CountDownLatch / Awaitility**, not **Thread.sleep()**.
- Async errors are logged/monitored; callers may not receive exceptions.
- Trace context/tenant context, if needed, is propagated explicitly.
- Do not assume `@Async` preserves tasks across restarts.

Section 6's example intentionally uses synchronous listeners to isolate the transaction-phase problem, avoiding concurrency making test results ambiguous.

### 14.2. Reactive Transactions

Since Spring Framework 6.1, transactional event listeners also support **reactive** transactions, yet reactive transaction context lives in the **Reactor Context**, unlike imperative **PlatformTransactionManager**'s ThreadLocal. With reactive, publish events carrying the appropriate transaction context (see **TransactionalEventPublisher**).

**You cannot copy this article's `TransactionTemplate`/`DataSourceTransactionManager` tests verbatim** and draw conclusions about reactive transactions. This article tests **imperative JDBC transactions**; if using R2DBC/reactive, write integration tests for `ReactiveTransactionManager`, context propagation, and matching lifecycle.

## 15. Recommended Production Testing Strategy

To test domain events in a real Spring application, separate test layers:

### Domain/Use-Case Unit Tests

- Does the domain emit the right **OrderPlaced** fact?
- Does the service decide to publish correctly when business rules pass?
- Are repositories/ports called properly?

These tests can use fakes/mocks. They **do not verify transaction callback phases**.

### Transaction-Bound Listener Integration Tests

- Run a Spring `ApplicationContext` with a real transaction manager.
- Publish via `ApplicationEventPublisher` inside a real transaction.
- Test commit and rollback, including rollback-only and exceptions.
- Assert phase listeners **after transaction completion**.
- Assert the database committed or rolled back as expected.
- Test fallback outside transactions.
- If the listener writes new DB records, test a separate/`REQUIRES_NEW` transaction.

### End-to-End / Failure-Injection Tests

- Use a production-like database when isolation/dialect is critical.
- Inject crashes, transaction timeouts, connection failures, duplicate events, or broker outages.
- Test outbox/inbox/retries and idempotency.
- Ensure monitoring/correlation surfaces failing post-commit handlers.

Do not force every test into **@SpringBootTest** when only a few Spring Framework beans are needed. For small configs, **@SpringJUnitConfig** is fast and sharply scoped. Only reach for test slices or `@SpringBootTest` when the application depends on Spring Boot auto-configuration.

## 16. Checklist Before Declaring QA PASS

1. **Is the listener created as a Spring bean, not called directly?**
2. **Is the event published via `ApplicationEventPublisher` inside a real transaction?**
3. **Do you know the default phase is `AFTER_COMMIT`?**
4. **Are `BEFORE`/`AFTER` assertions placed at the right time, after completion?**
5. **Commit path: `AFTER_COMMIT` ran, `AFTER_ROLLBACK` did not, and DB retains data?**
6. **Rollback path: `AFTER_COMMIT` did not run, `AFTER_ROLLBACK` ran, and DB has no data?**
7. **Are exceptions thrown after publish tested?**
8. **Are outside-transaction publishing and `fallbackExecution=true/false` tested?**
9. **If the test has `@Transactional`, did you use `TestTransaction` or assert after the transaction?**
10. **If `TransactionTemplate` joins an outer transaction, did you avoid mistaking template return for commit?**
11. **If using `@Async`, did you wait for completion deterministically and check executor errors?**
12. **If the listener writes DB post-commit, is there a new transaction and verification of committed rows?**
13. **If events must not be lost, is there an outbox/queue rather than in-memory callbacks alone?**
14. **Are tests run on a suitable DB when isolation, constraints, or SQL dialect matter?**
15. **Do assertions avoid relying on test execution order or fixed sleep durations?**

**Conclusion:** Testing **@TransactionalEventListener(AFTER_COMMIT)** truly means testing **transaction outcomes**, not merely the publish call. Use **TransactionTemplate** to explicitly drive commit/rollback in integration tests, or **TestTransaction** when the test method already has **@Transactional**. Always verify both **phase callbacks** and **post-completion DB state**. **AFTER_COMMIT** solves "react only after commit," yet does not replace a new transaction for post-commit writes and does not turn a listener into a durable queue.

### Official Documentation

- Spring Framework 6.2 Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 Reference — *TestContext Framework Transaction Management*: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 Javadoc — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2 Javadoc — *TransactionPhase*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework 6.2 Javadoc — *TestTransaction*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 Javadoc — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework 6.2 Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html
