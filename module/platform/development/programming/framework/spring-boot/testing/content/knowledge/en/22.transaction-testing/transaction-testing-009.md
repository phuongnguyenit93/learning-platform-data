# Preemptive Timeouts and the Risk of Out-of-Transaction Operations in Spring Boot Testing

## 1. The Symptom: The Test Rolls Back Yet Data Still Persists

In a Spring Boot integration test, developers commonly use `@Transactional`, `@JdbcTest`, or `@DataJpaTest` and expect database changes to automatically **roll back** after each test. That expectation holds when code runs on the **test execution thread**. However, if you wrap a write operation inside JUnit Jupiter's `assertTimeoutPreemptively(...)`, the callback runs on **a different thread**, detached from the transaction Spring TestContext bound to the test thread. The result can be surprising: the assertion reports no timeout, the test passes green, yet the INSERT/UPDATE/DELETE commits and remains in the database after Spring rolls back the test.

This is not a bug in JDBC, JPA, or Spring "forgetting to roll back." **Spring properly rolled back the test's transaction**, but the write executed on a different thread and therefore **was not inside that transaction**. With standard JDBC/H2, an INSERT outside any Spring transaction on an auto-commit connection commits independently and is unaffected by rollback on the original thread.

**Short scenario:**

~~~java
// Inside a test whose transaction is managed by Spring:
assertTimeoutPreemptively(Duration.ofSeconds(5), () -> {
    jdbcTemplate.update(
            "INSERT INTO audit_marks (id, note) VALUES (?, ?)",
            42L, "escaped");
});
~~~

This is a dangerous illustrative snippet, not a standalone program. Even when the callback finishes in 1 ms with no timeout, it still runs on a separate JUnit thread. Thus **a timeout does not have to occur for the risk to exist**.

**Lesson objectives:**

1. Distinguish **test-managed transactions**, **Spring-managed transactions**, and **application-managed transactions**.
2. Explain how Spring TestContext binds transactions to **`ThreadLocal`** before running a test method.
3. Compare JUnit Jupiter **`assertTimeout`**, **`assertTimeoutPreemptively`**, and **`@Timeout(threadMode=...)`**.
4. Understand why `assertTimeoutPreemptively` can cause writes to escape rollback while also leaking other `ThreadLocal` state.
5. Verify transaction state with **`TestTransaction.isActive()`** and **`TransactionSynchronizationManager.isActualTransactionActive()`** in proper context.
6. Build a Java 17 + Spring Boot **3.3.5** + Gradle + H2 + **`@JdbcTest`** example with safe tests and a dangerous demo **`@Disabled` by default**.
7. Verify real rollback **after the test** using **`@AfterTransaction`**, not merely checking data while the transaction is open.
8. Use **`try`/`finally`**, a test-only database, and cleanup to avoid leaving data behind when intentionally demonstrating out-of-transaction commits.
9. Recognize other boundaries that lose transaction context: `CompletableFuture`, `ExecutorService`, `@Async`, server-side HTTP threads, and **`REQUIRES_NEW`** propagation.
10. Build a checklist to prevent false positives in CI and avoid treating preemptive timeouts as a rollback/task-kill guarantee.

**Scope:** Spring Framework TestContext/JUnit Jupiter (not HTTP request timeouts, SQL statement timeouts, or production transaction timeouts). Code uses JDK 17, Spring Boot 3.3.5, Spring Framework 6.1.x, and H2. Never run out-of-transaction write demos against a real production database.

## 2. How Does a Test-Managed Transaction Differ from Regular Transactions?

Three concepts often lumped together as "transaction":

| Concept | Who creates/manages it? | Where context lives | How does it end? |
|---|---|---|---|
| **Test-managed transaction** | Spring TestContext's `TransactionalTestExecutionListener`; controllable via `TestTransaction` | `ThreadLocal` of the test thread | Rolls back by default after a transactional test |
| **Spring-managed transaction** | Spring `PlatformTransactionManager`, usually via `@Transactional` on service/proxy | Bound to the current thread | Commits/rolls back per propagation and invocation outcome |
| **Application-managed transaction** | Code explicitly using `TransactionTemplate`, transaction manager, or JDBC connection | Per transaction code/connection mechanism | Per explicit commit/rollback calls from application |

When a transactional test invokes a Spring service with `REQUIRED` propagation, the service normally **joins the existing transaction on the test thread**. Hence data changes made by the service also roll back at the end of the test. Yet when a callback runs on a new thread lacking the test-managed transaction, a `@Transactional(REQUIRED)` service can **start a new transaction and commit** when the service returns. Standard JDBC without a Spring transaction can auto-commit after the update.

Different transaction mechanisms can coexist. **Simply putting `@Transactional` on a test method does not cover every thread spawned from it.**

### 2.1. Lifecycle of a Transactional Test

~~~text
Thread T1 — JUnit/Spring test thread
  |
  | Spring TestContext / TransactionalTestExecutionListener
  | Starts test-managed transaction TX-A
  | Binds JDBC Connection/transaction state to ThreadLocal(T1)
  |
  +-- @BeforeEach        [normally inside TX-A]
  +-- @Test method       [inside TX-A]
  |     jdbc.update(...) [joins TX-A]
  +-- @AfterEach         [normally inside TX-A]
  |
  | Rollback TX-A (default)
  | Unbinds resources / transaction state on T1
  |
  +-- @AfterTransaction  [outside TX-A]
~~~

`@BeforeTransaction` runs **before** TX-A starts; `@AfterTransaction` runs **after** TX-A ends. These are specialized Spring TestContext hooks useful for verifying real database state after rollback. JUnit's `@BeforeAll`/`@AfterAll` are also outside per-test transactions by default. `@BeforeEach`/`@AfterEach` run inside the test-managed transaction for transactional tests, though placing `@Transactional` on a lifecycle method is not how test transactions are activated.

**Prerequisites:** Spring TestContext must have a `PlatformTransactionManager` and the test must run with Spring `@Transactional` or a transactional slice such as `@JdbcTest`. With Spring Boot 3.3's `@JdbcTest`, tests are transactional and roll back by default. If a test is not transactional at all, there is no transaction to "escape" — preemptive timeouts still carry other thread-local risks, but you cannot expect Spring to roll back a transaction that never existed.

### 2.2. Execution Path of a Preemptive Callback

~~~text
Thread T1 — transactional test thread        Thread T2 — timeout worker
┌───────────────────────────────────┐      ┌─────────────────────────────┐
│ Begin TX-A; bind ThreadLocal(T1)  │      │ No TX-A on T2               │
│                                   │      │                             │
│ assertTimeoutPreemptively(...) ─────────►│ jdbc.update INSERT          │
│                                   │      │ Acquires separate connection│
│                                   │      │ Auto-commits or opens new TX│
│ callback returns; test ends       │◄─────│                             │
│ Rollback TX-A                     │      └─────────────────────────────┘
│ Undoes only writes inside TX-A    │
└───────────────────────────────────┘

Result: data committed by T2 can persist after TX-A rolls back.
~~~

The JDBC connection Spring binds to T1 is normally fetched through `TransactionSynchronizationManager` and `DataSourceUtils`. T2 does not see those `ThreadLocal` resources. **`ThreadLocal` does not propagate across thread pools automatically**; and you should never manually copy a `Connection` or `TransactionStatus` from T1 to T2 as a quick fix — doing so does not make transactions thread-safe.

## 3. Three Ways to Set Timeouts in JUnit Jupiter

### 3.1. assertTimeout: Checks After Code Finishes, Same Thread

`Assertions.assertTimeout(Duration, Executable)` runs the callback **on the calling thread**. Once it finishes, JUnit checks elapsed time and fails if it exceeded the limit. It **does not interrupt the callback early** merely because the deadline passed.

~~~java
assertTimeout(Duration.ofSeconds(3), () -> {
    // Same thread as the transactional test.
    repository.save(entity);
});
~~~

This snippet is conceptual; repository/entity types must be defined in the real app. Because it runs on the same thread, the callback still sees the test's TX-A and writes normally roll back. This is the preferred option when testing a database inside a test-managed transaction and simply **asserting execution duration**.

**Trade-off:** a hung task can prolong the test, since `assertTimeout` does not forcibly abort code on expiration. Coordinate JDBC driver/HTTP client/DB statement timeouts when real resource limits are needed rather than wrapping in a dangerous preemptive timeout just for a hard cap.

### 3.2. assertTimeoutPreemptively: Runs Callback on Another Thread

`Assertions.assertTimeoutPreemptively(Duration, Executable)` always runs the executable/supplier on a **different thread from the caller**. If it exceeds the deadline, JUnit attempts to interrupt via `Thread.interrupt()` and fails the test; **this does not guarantee stopping all work**. A task that ignores interrupts can keep running after the timeout failure returns, causing late side effects.

~~~java
assertTimeoutPreemptively(Duration.ofSeconds(3), () -> {
    // DIFFERENT thread from the test-managed transaction.
    repository.save(entity);
});
~~~

Warning snippet—**do not** drop directly into transactional integration tests. The problem is not the number of seconds: even if the callback completes well under 3 seconds, it still runs on a different thread. Beyond JDBC rollback, other `ThreadLocal`-bound state such as Spring `SecurityContext`, request attributes, MDC logging, or locale context may also fail to propagate as expected, depending on the tools/frameworks.

### 3.3. @Timeout: Check threadMode, Not Just Seconds

JUnit Jupiter supports the `@Timeout` annotation and `Timeout.ThreadMode`:

| Configuration | Which thread runs the test body? | Impact on test-managed transaction |
|---|---|---|
| `@Timeout(..., threadMode = SAME_THREAD)` | Same thread as Spring TestContext | Keeps TX-A scope; on expiration JUnit can interrupt the thread |
| `@Timeout(..., threadMode = SEPARATE_THREAD)` | Different thread, preemptive | Carries the same risks as `assertTimeoutPreemptively` |
| `@Timeout(..., threadMode = INFERRED)` | Per JUnit configuration parameter | Must check config; do not assume it is always safe |
| `assertTimeout(...)` | Calling assertion thread | Non-preemptive; preserves that thread's TX-A |
| `assertTimeoutPreemptively(...)` | Different thread from caller | Detaches from TX-A even when callback finishes quickly |

`INFERRED` is the default for `@Timeout`; it reads `junit.jupiter.execution.timeout.thread.mode.default`. Without a valid config value, JUnit Jupiter falls back to **`SAME_THREAD`**. For sensitive transactional tests, **specify `SAME_THREAD` explicitly** so behavior never shifts due to a global suite/CI config change.

~~~java
@Test
@Timeout(
        value = 5,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
void testWithinSameThread() {
    // Suitable for Spring test-managed transactions.
}
~~~

This snippet is inside a JUnit class importing `org.junit.jupiter.api.Timeout`, `org.junit.jupiter.api.Test`, and `java.util.concurrent.TimeUnit`; full code appears in section 6.

**Interrupt caveat:** `SAME_THREAD` avoids switching threads, yet does not guarantee every operation can be interrupted safely. A JDBC operation may ignore interrupts, or produce side effects before timeout is flagged. Timeouts signal timing violations—they are **not rollback policies or transaction boundaries**.

## 4. Why Doesn't @Transactional Protect Every Thread?

Common misconceptions:

**Misconception A:** `@Transactional` on a test method makes every `Runnable` or `CompletableFuture` inside it join the same transaction.

False. Spring test transactions are thread-bound; a callback on another thread does not inherit T1's transaction. If a service call on T2 has `@Transactional(REQUIRED)`, Spring can start **a new transaction** instead of joining TX-A.

**Misconception B:** `assertTimeoutPreemptively(5s)` takes 1 ms, so there is "no difference" from `assertTimeout(5s)`.

False. Switching to a separate thread is inherent to the API, **regardless of whether a timeout ever occurs**. Finishing before the limit only avoids a timeout assertion failure.

**Misconception C:** If `TestTransaction.isActive()` is true in the test method, it is also true inside an async callback.

False. `TestTransaction` inspects the **calling thread's test-managed transaction**, not the entire JVM. On T2, `TestTransaction.isActive()` is typically false. `TransactionSynchronizationManager.isActualTransactionActive()` is also false until T2 opens its own transaction; once a service creates a new Spring-managed transaction, that flag can become true, **yet it is not TX-A**. Distinguish "some transaction is active" from "the test's transaction."

**Misconception D:** `@Rollback` or `@Transactional` on the test can force revoking data committed on another thread.

False. Rollback controls only the managed transaction. There is no automatic mechanism to undo an independent transaction already committed on another connection. `@Rollback(false)` or `@Commit` actively alters the test transaction's policy, which is a different matter.

**Misconception E:** Adding `@Transactional` to the service fixes the worker losing the test transaction.

No. When called from T2, the `@Transactional` proxy can open **a new transaction**, finish, and commit. `@Transactional` is essential for business atomicity, yet **does not attach T2 to T1's test-managed transaction**.

**Misconception F:** Avoiding preemptive timeouts guarantees all side effects roll back.

Also false. `@Transactional(propagation=REQUIRES_NEW)` can commit a separate transaction even on the same thread; HTTP calls to a server running another thread/transaction, broker messages, external APIs, or file writes are not undone by a test database rollback either. Non-preemptive timeouts only eliminate **one assertion-induced thread hop**; they do not guarantee all side effects stay inside TX-A.

## 5. What Must the Tests Prove?

A solid test suite for this topic should check **both during execution and after rollback**:

| Check | While test is still inside TX-A | After TX-A rolls back |
|---|---|---|
| `TestTransaction.isActive()` on T1 | true | false |
| `TransactionSynchronizationManager.isActualTransactionActive()` on T1 | usually true | false |
| INSERT inside `assertTimeout(...)` on T1 | New row visible inside TX-A | Row disappears via rollback |
| INSERT inside `assertTimeoutPreemptively(...)` on T2 | Row visible if T2 committed | Row can still persist |
| `@AfterTransaction` | Has not run yet | Can query final state on a connection outside TX-A |

**Never prove rollback with a `SELECT` right after `INSERT` inside the test.** A `SELECT` inside the same T1/TX-A sees **its own uncommitted data**; it cannot tell whether the data survives or vanishes on rollback. Verify outside TX-A, such as in `@AfterTransaction`.

To avoid polluting the test suite, the preemptive commit demo later in the article is **`@Disabled` by default**. When intentionally removing `@Disabled`, run only against an **embedded H2 test database** with an `@AfterTransaction` hook that both asserts the outcome and **`DELETE`s the committed data in `finally`**. This is an educational test—**never run it on a shared DB**. A hung callback ignoring interrupts can even execute late after cleanup; that is why the dangerous demo is disabled in everyday suites.

## 6. Runnable Spring Boot 3.3.5 Project

### 6.1. Project Structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/tx/TxTimeoutApplication.java
src/test/resources/schema.sql
src/test/java/demo/tx/SameThreadTimeoutTest.java
src/test/java/demo/tx/PreemptiveThreadBoundaryTest.java
src/test/java/demo/tx/PreemptiveWriteDemoTest.java
~~~

No `data.sql` is needed here: `schema.sql` creates an empty table, and each test uses distinct IDs. `@JdbcTest` is Spring Boot's JDBC slice backed by embedded H2, auto-configuring `JdbcTemplate` and test-managed transactions. We do not need `@SpringBootTest`, an embedded HTTP server, or Spring Data JPA just to verify transactional boundaries.

**settings.gradle**

~~~groovy
rootProject.name = 'spring-preemptive-timeout-tx'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Dependency explanation:** `starter-jdbc` brings `JdbcTemplate`/`DataSource`/transaction manager; H2 is the embedded database for JDBC tests; `starter-test` includes JUnit Jupiter, Spring Boot test, and Spring `TestTransaction` support. The Spring Boot BOM selects compatible versions. SQL-only tests need no web starter/Redis/database containers.

**src/main/java/demo/tx/TxTimeoutApplication.java**

~~~java
package demo.tx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxTimeoutApplication.class, args);
    }
}
~~~

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE tx_marks (
    id BIGINT PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);
~~~

The table has a primary key ID so tests do not write colliding IDs. `schema.sql` sits on the **test classpath**. In Spring Boot 3.3, `@JdbcTest` includes SQL initialization infrastructure with embedded H2; under default SQL init, `schema.sql` runs when the test `ApplicationContext` initializes.

**Why H2?** We get a disposable in-process DB with no network ports and no risk to real data. Still, because the demo creates side effects on another thread, cleanup remains necessary even with H2: TestContext can cache the `ApplicationContext` and `DataSource` across test classes in the same suite.

### 6.2. Safe Test: assertTimeout and @Timeout SAME_THREAD

**src/test/java/demo/tx/SameThreadTimeoutTest.java**

~~~java
package demo.tx;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
class SameThreadTimeoutTest {

    @Autowired
    JdbcTemplate jdbc;

    private Long expectedRolledBackId;

    private long count(long id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_marks WHERE id = ?",
                Long.class, id);
    }

    @Test
    void nonPreemptiveTimeoutKeepsTestTransaction() {
        expectedRolledBackId = 1101L;
        Thread testThread = Thread.currentThread();

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertTimeout(Duration.ofSeconds(5), () -> {
            assertSame(testThread, Thread.currentThread());
            assertTrue(TestTransaction.isActive());

            int updated = jdbc.update(
                    "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                    expectedRolledBackId, "same-thread");

            assertEquals(1, updated);
            assertEquals(1L, count(expectedRolledBackId));
        });
    }

    @Test
    @Timeout(
            value = 5,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void timeoutAnnotationExplicitlyKeepsTestThread() {
        expectedRolledBackId = 1102L;

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        jdbc.update(
                "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                expectedRolledBackId, "timeout-annotation");

        assertEquals(1L, count(expectedRolledBackId));
    }

    @Test
    void nonPreemptiveSupplierAlsoKeepsTransaction() {
        Thread parent = Thread.currentThread();

        Long result = assertTimeout(
                Duration.ofSeconds(5),
                () -> {
                    assertSame(parent, Thread.currentThread());
                    assertTrue(TestTransaction.isActive());
                    return jdbc.queryForObject(
                            "SELECT COUNT(*) FROM tx_marks",
                            Long.class);
                });

        assertNotNull(result);
        assertTrue(result >= 0L);
    }

    @AfterTransaction
    void verifyRollbackAfterSpringEndsTransaction() {
        // Each @Test gets its own test instance under JUnit's default.
        if (expectedRolledBackId == null) {
            return;
        }

        assertFalse(TestTransaction.isActive());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());

        // Only now is the row proven to have rolled back.
        assertEquals(0L, count(expectedRolledBackId));
    }
}
~~~

**The three tests in this class serve distinct roles:**
- **`nonPreemptiveTimeoutKeepsTestTransaction`:** asserts the same `Thread` object before/inside the callback, verifies `TestTransaction` is active, and confirms the INSERT is visible inside TX-A. Afterward, `@AfterTransaction` confirms row ID 1101 **is gone**.
- **`timeoutAnnotationExplicitlyKeepsTestThread`:** `@Timeout(threadMode=SAME_THREAD)` sets a method timeout without moving execution to worker T2. `@AfterTransaction` confirms row ID 1102 rolled back.
- **`nonPreemptiveSupplierAlsoKeepsTransaction`:** the value-returning overload of `assertTimeout` also runs on the calling thread. It writes nothing to the DB; it simply verifies transaction state and queries the table.
- `@AfterTransaction` runs outside the transaction; `expectedRolledBackId` is an instance field set only by the two tests that perform INSERTs. By default JUnit Jupiter creates a fresh test instance per test method, so the read-only test's hook does not check the wrong ID.
- The tests need no explicit `@Transactional` because `@JdbcTest` is transactional by default. When moving to a general `@SpringBootTest`, configure `@Transactional` for tests expecting rollback and ensure a transaction manager is present.

**Key takeaway:** asserting `count(id)==1` **right after INSERT** only proves the current transaction sees the write; asserting `count(id)==0` inside **`@AfterTransaction`** proves post-test rollback.

### 6.3. Safe Test: Observing Loss of Transaction on a Worker Thread

**src/test/java/demo/tx/PreemptiveThreadBoundaryTest.java**

~~~java
package demo.tx;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
class PreemptiveThreadBoundaryTest {

    @Test
    void preemptiveCallbackHasNoTestManagedTransaction() {
        Thread parent = Thread.currentThread();

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertTimeoutPreemptively(Duration.ofSeconds(5), () -> {
            assertNotSame(parent, Thread.currentThread());
            assertFalse(TestTransaction.isActive());
            assertFalse(TransactionSynchronizationManager
                    .isActualTransactionActive());
        });
    }

    @Test
    void completableFutureAlsoDoesNotInheritTransaction() {
        assertTrue(TestTransaction.isActive());

        boolean activeOnWorker = CompletableFuture.supplyAsync(
                TransactionSynchronizationManager
                        ::isActualTransactionActive).join();

        assertFalse(activeOnWorker);
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void nonPreemptiveWrapperDoesNotFixNestedAsyncHop() {
        assertTimeout(Duration.ofSeconds(5), () -> {
            // Wrapper on T1 still has the test transaction.
            assertTrue(TestTransaction.isActive());

            // Yet the nested async call itself hops onto T2.
            boolean workerActive = CompletableFuture.supplyAsync(
                    TransactionSynchronizationManager
                            ::isActualTransactionActive).join();

            assertFalse(workerActive);
            assertTrue(TestTransaction.isActive());
        });
    }
}
~~~

These are **three non-writing DB tests**, so they are safe to run by default. They verify the root cause: the thread to which Spring bound the test transaction **differs** from the thread running the callback/async work. `CompletableFuture.supplyAsync` uses a different executor (typically the ForkJoin common pool) and does not copy the test transaction from the parent's `ThreadLocal`.

**Subtle detail:** `assertTimeout` does not switch threads, yet inside its callback you could still **explicitly** invoke `CompletableFuture`, `ExecutorService`, `@Async`, or an HTTP call. Then the inner worker's operations can still run outside TX-A. Merely changing preemptive to non-preemptive **is not enough** if the test already contains another thread hop.

### 6.4. Dangerous Demo, Disabled by Default: Real INSERT Escapes Rollback

The class below intentionally uses `assertTimeoutPreemptively` to write on T2 and then verifies the row still exists **after T1 rolls back**. To avoid polluting CI, **the entire class is `@Disabled` by default**. Run it only after deliberately removing `@Disabled`, and only against a disposable H2 test database. The `@AfterTransaction` hook deletes the row inside `finally`.

**src/test/java/demo/tx/PreemptiveWriteDemoTest.java**

~~~java
package demo.tx;

import java.time.Duration;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@Disabled("Educational commit-leak demo; enable only on disposable H2")
@JdbcTest
class PreemptiveWriteDemoTest {

    private static final long ESCAPED_ID = 2101L;

    @Autowired
    JdbcTemplate jdbc;

    private boolean attemptedWrite;

    private long countEscapedRow() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_marks WHERE id = ?",
                Long.class, ESCAPED_ID);
    }

    @Test
    void preemptiveWriteIsNotRolledBackWithTestTransaction() {
        assertTrue(TestTransaction.isActive());
        attemptedWrite = true;

        assertTimeoutPreemptively(Duration.ofSeconds(15), () -> {
            // Worker does not inherit test's TX-A.
            assertFalse(TestTransaction.isActive());
            assertFalse(TransactionSynchronizationManager
                    .isActualTransactionActive());

            int changed = jdbc.update(
                    "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                    ESCAPED_ID, "committed-outside-test-tx");

            assertEquals(1, changed);
        });

        // Callback finished before timeout. T1 still holds TX-A.
        assertTrue(TestTransaction.isActive());
    }

    @AfterTransaction
    void verifyCommittedSideEffectThenAlwaysCleanUp() {
        if (!attemptedWrite) {
            return;
        }

        // Method runs AFTER Spring rolled back TX-A.
        assertFalse(TestTransaction.isActive());

        try {
            // T2's data committed so it still exists: T1 rollback did not delete it.
            assertEquals(1L, countEscapedRow());
        } finally {
            // Clean up row independently on a thread outside TX-A.
            jdbc.update(
                    "DELETE FROM tx_marks WHERE id = ?",
                    ESCAPED_ID);
        }
    }
}
~~~

**Experiment walkthrough:**

1. `@JdbcTest` causes Spring to start TX-A on the test method's thread T1.
2. `attemptedWrite=true` tells `@AfterTransaction` there is a demo to verify and clean up.
3. JUnit runs the `assertTimeoutPreemptively` callback on T2, where both `TestTransaction.isActive()` and the actual transaction flag are false **before the INSERT**.
4. `JdbcTemplate.update` on T2 acquires a connection not participating in TX-A. Under the lesson's default H2 DataSource/auto-commit, the INSERT commits independently.
5. T2 finishes quickly before the deadline and returns to T1. At the end of the test, Spring rolls back TX-A; that rollback does not touch the independent transaction already committed on T2.
6. `@AfterTransaction` runs outside TX-A, counts row ID 2101, and **expects 1**. That is the post-rollback verification proof.
7. `finally` runs the `DELETE` so no row lingers in H2 during normal demo execution.

**Risk even in a demo with cleanup:** If the callback blocks, times out, and fails to stop despite interruption, T2 could INSERT **after** `@AfterTransaction` already ran cleanup. Thus `finally` only guards normal demo execution, **not hung threads**. That is why the demo stays `@Disabled`, uses a dedicated ID, runs only on a disposable DB, and must never run on a shared/prod database.

**Another intentionally dangerous variant to recognize:**

~~~java
@Timeout(
        value = 3,
        threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
@Test
void unsafeTransactionTestMethod() {
    jdbc.update("INSERT INTO tx_marks(id, note) VALUES (?, ?)",
            3001L, "danger");
}
~~~

This is a **warning snippet**, not a method in the runnable project. `@Timeout(SEPARATE_THREAD)` can run the entire test body on a thread without the test-managed transaction, distorting transactions and cleanup. **Do not use this setting for transactional integration tests** unless you explicitly manage transactions inside the worker and know how side effects are cleaned up.

## 7. Running the Project and Checking Test Counts

If the project has the Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only copied the sample files without Gradle Wrapper scripts/JAR, generate the wrapper with a compatible Gradle installation or run `gradle test`. Sample source does not generate `./gradlew` by itself.

Total JUnit Jupiter test methods across **three complete Java files**:

| Test class | Declared `@Test` | Default execution | Focus |
|---|---:|---:|---|
| `SameThreadTimeoutTest` | **3** | **3 PASS** expected | `assertTimeout`, `@Timeout SAME_THREAD`, rollback |
| `PreemptiveThreadBoundaryTest` | **3** | **3 PASS** expected | preemptive/`CompletableFuture` lose `ThreadLocal` |
| `PreemptiveWriteDemoTest` | **1** | **1 DISABLED** | Out-of-rollback commit demo and cleanup |
| **Total** | **7** | **6 executed, 1 skipped** | No intentionally failing tests in default suite |

These are **expected outcomes from the source code**, not a claim that they were executed on your machine. Spring Boot can cache `ApplicationContext`/H2 across test classes, yet default tests do not produce escaped writes; both writes in `SameThreadTimeoutTest` roll back; the dangerous demo is disabled.

Gradle report is typically at:

~~~text
build/reports/tests/test/index.html
~~~

Run only the safe tests:

~~~bash
./gradlew test --tests demo.tx.SameThreadTimeoutTest
./gradlew test --tests demo.tx.PreemptiveThreadBoundaryTest
~~~

To observe the demo yourself:
1. Use a **dedicated project and embedded H2**, never a shared environment database.
2. Remove the **`@Disabled`** annotation on `PreemptiveWriteDemoTest`.
3. Run only that class; do not run the whole suite if another context/fixture shares ID 2101.
4. Observe `@AfterTransaction` proving the row remains after rollback, and `finally` deleting it.
5. Restore `@Disabled` after the experiment. If the test times out, the process is killed, or the connection drops midway, discard the entire H2 database/test context and restart cleanly; never assume cleanup completed.

Example command after intentionally removing `@Disabled`:

~~~bash
./gradlew test --tests demo.tx.PreemptiveWriteDemoTest
~~~

**Never set up a demo against a production database to prove a commit leak.** Even in an educational demo, writing outside a transaction, sending emails, calling webhooks, or publishing messages can create irreversible side effects.

## 8. @BeforeTransaction, @AfterTransaction, @BeforeEach, and @AfterEach

| Hook or phase | Inside test-managed transaction? | Why use it |
|---|---|---|
| `@BeforeTransaction` | **No** | Inspect DB state before TX-A |
| `@BeforeEach` | **Yes** for transactional tests | Prepare data belonging to TX-A |
| `@Test` method | **Yes**, if test-managed transaction is active | Run assertions and mutate data |
| `@AfterEach` | **Yes** for transactional tests | Clean up/assert data still inside TX-A |
| `@AfterTransaction` | **No** | Verify rollback/commit actually occurred |
| `@BeforeAll` / `@AfterAll` | Outside TX-A by default | Class-level initialization/summary |

Do not place `@Transactional` on JUnit `@BeforeEach` expecting it to open a test transaction; let the test method/class and `TransactionalTestExecutionListener` activate the test-managed transaction. In a transactional test, `@BeforeEach` runs after Spring opens TX-A, whereas `@BeforeAll` and `@BeforeTransaction` run outside.

Example solely to show hook positions:

~~~java
@BeforeTransaction
void beforeTx() {
    assertFalse(TestTransaction.isActive());
}

@BeforeEach
void setUp() {
    assertTrue(TestTransaction.isActive());
}

@AfterEach
void tearDown() {
    assertTrue(TestTransaction.isActive());
}

@AfterTransaction
void afterTx() {
    assertFalse(TestTransaction.isActive());
}
~~~

This snippet is for a Spring-managed transactional test class, not a standalone source file. The `@AfterTransaction` hook is especially important because a `SELECT` inside `@AfterEach` still sees un-rolled-back data.

## 9. @Transactional Propagation and Side Effects Not Rolled Back by the Test

### 9.1. REQUIRED, SUPPORTS, and REQUIRES_NEW

A Spring service called from the test thread with `@Transactional(propagation=REQUIRED)` normally joins the active transaction. Yet if it executes on T2 due to a preemptive timeout, it does not see T1's test transaction and can open its own transaction and commit.

Even on **the same T1**, a `@Transactional(propagation=REQUIRES_NEW)` service can suspend TX-A, open TX-B, commit TX-B, and resume TX-A; rolling back TX-A does not revoke TX-B's commit. Therefore, to guarantee zero leftover data after tests, check not only threads but also actual **transaction propagation**.

**Do not count distinct transactions solely via `isActualTransactionActive()`**: it only reports whether an actual transaction is active on the current thread, not whether it is TX-A or TX-B. In complex tests, combine `TestTransaction`, transaction manager logs, `@AfterTransaction` assertions, and DB isolation.

### 9.2. HTTP, @Async, CompletableFuture, ExecutorService

- `@Async` typically offloads work to an `Executor` thread, so it does not keep the test-managed transaction.
- `CompletableFuture.supplyAsync` does not copy transaction `ThreadLocal` state.
- `ExecutorService.submit(...)` uses an executor thread, not the test thread.
- `@SpringBootTest(RANDOM_PORT)` sends HTTP requests to a separate server thread: the server request's transaction **is not inside the JUnit test client's transaction**, even when the test method has `@Transactional`.
- Kafka/message queues, the filesystem, outbound HTTP requests, and emails are likewise not undone by a JDBC test rollback.

**Avoid manually passing `TransactionSynchronizationManager` resources or `Connection` objects across threads** as a quick fix. Connection/transaction contexts belong to a specific lifecycle and are generally not thread-safe; hand-copying them risks races, corruption, or using closed resources.

If business logic requires asynchronous execution, design **real transaction boundaries inside each worker/task**, use isolated fixtures, and clean up properly. If you only want to measure query duration inside a transactional test, avoid spawning unnecessary threads.

### 9.3. Other Timeout Tools Can Also Create New Threads

Spring Framework warns about testing framework preemptive timeouts in general. Historical examples include **JUnit 4 `@Test(timeout=...)` / `Timeout` Rule**, JUnit Jupiter **`assertTimeoutPreemptively`**, and TestNG **`@Test(timeOut=...)`**. Check each version's actual mechanism. Never assume that because an annotation sits on the test, transaction context automatically follows callbacks.

Even when a timeout API does not change threads, the task itself might spawn threads. **The root issue is thread-bound `ThreadLocal` transactions meeting an execution thread switch**, not the word "preemptive" in an API name.

## 10. Choosing the Right Solution for Your Goal

**Goal A — Measure database processing time while keeping test-managed rollback.** Use `assertTimeout(Duration, ...)` or `@Timeout(threadMode=SAME_THREAD)` intentionally. Add statement/driver timeouts when real I/O bounds are needed. Verify rollback after the test using `@AfterTransaction` when that is an important contract.

**Goal B — Stop an external call that might hang.** Enforce timeouts at the real tool's boundary: HTTP client connect/request timeouts, JDBC `queryTimeout`, RPC deadlines, or Testcontainers readiness/health limits. A JUnit preemptive timeout cannot guarantee safely halting driver/remote operations and does not undo committed side effects.

**Goal C — Test asynchronous execution.** Acknowledge that workers have their own transaction boundaries. Use a disposable test DB, synchronize worker completion with `Future`/`CountDownLatch` (with deadlines), and clean up after the worker truly finishes. Do not rely on parent-thread rollback to clean worker commits.

**Goal D — Genuinely test preemptive cancellation.** Pick **pure CPU logic with no side effects or `ThreadLocal` dependencies**, and test how it responds to interruption. If you must test task side effects, design compensation/cleanup and run in an isolated environment; never treat preemptive timeouts as "automatically safe."

**Goal E — Parallel suites.** Every test must use unique keys and avoid shared mutable static fixtures. Test transactions are per-thread, yet the database is shared if test classes/contexts share a datasource. Writes escaping transactions can race or pollute other tests; enforce isolation and dedicated data management.

## 11. Common Issues and Diagnostics

| Symptom | Possible cause | Check/fix |
|---|---|---|
| `@Transactional` test passes yet DB has extra rows | Write ran outside TX-A due to preemptive/async/HTTP | Check threads and `@AfterTransaction`; clean up properly |
| `TestTransaction.isActive()` true before callback, false inside | Callback ran on a new thread | Use `assertTimeout` or `SAME_THREAD` |
| `isActualTransactionActive()` true on worker yet data still commits | Worker has its own TX-B | Distinguish TX-A vs. TX-B, check propagation |
| Fast callback still commits outside test | `assertTimeoutPreemptively` always uses another thread | Do not use preemptive for transactional writes |
| `@Timeout` test causes unexpected side effects | `SEPARATE_THREAD` threadMode or global `INFERRED` config | Specify `SAME_THREAD` explicitly |
| `@AfterEach` sees row so you think rollback failed | `@AfterEach` is still inside TX-A | Use `@AfterTransaction` to verify post-rollback |
| `@AfterTransaction` does not run | Test is not transactional or listener inactive | Check `@JdbcTest`/`@Transactional`, transaction manager |
| `@JdbcTest` does not roll back | Disabled `@Transactional`, `NOT_SUPPORTED`, commit flag, or off-thread | Check `TestTransaction`/annotations/thread |
| Test passes alone, fails in full suite | Committed data from T2 lingers in shared H2/DB | Isolate IDs/schemas/DBs, clean up after worker |
| Preemptive assertion fails yet INSERT still appears later | Callback did not stop on interrupt | Do not treat preemptive as a kill switch |
| DB UPDATE hangs due to lock | Main transaction holds lock, worker waits for it | Avoid updating same row from two threads, set DB statement timeout |
| Spring Security/MDC/Locale lost inside callback | `ThreadLocal` not propagated automatically | Design explicit context propagation or avoid switching threads |
| `@Transactional` service does not roll back with test | Service ran on T2 worker or `REQUIRES_NEW` | Inspect transaction boundary and post-commit state |
| `@Transactional` test does not roll back HTTP endpoint write | Server HTTP request runs on another thread | Dedicated test DB, cleanup; do not expect TX-A rollback |
| `@Commit` or `@Rollback(false)` used | Test intentionally commits | Distinguish commit policy from timeout behavior |

**10-step debug checklist:**

1. Did the test actually open a test-managed transaction? Check `TestTransaction.isActive()` right inside the test method.
2. Are `PlatformTransactionManager` and `@JdbcTest`, `@DataJpaTest`, or `@Transactional` properly configured?
3. Is there `assertTimeoutPreemptively`, `@Timeout(SEPARATE_THREAD)`, `CompletableFuture`, `@Async`, an executor, or HTTP `RANDOM_PORT`?
4. Log thread name/ID where the test starts and where the DB update runs, without exposing secrets.
5. Check `TransactionSynchronizationManager.isActualTransactionActive()` at each boundary; remember it does not distinguish TX-A from TX-B.
6. Inspect the service's `@Transactional` propagation: `REQUIRED`/`SUPPORTS`/`REQUIRES_NEW`/`NOT_SUPPORTED`.
7. Check whether the test uses `@Commit`, `@Rollback(false)`, `TestTransaction.flagForCommit()`, or `end()`.
8. Compare post-rollback data only in `@AfterTransaction`, not only `@AfterEach`.
9. Check DB connection/auto-commit, rollback logs, and lock status per driver.
10. If any out-of-tx write occurred, clean up data independently or use a disposable DB; never leak across the suite.

## 12. Notes on Sustainable Test Design

**Never use `Thread.sleep` to construct a scheduling-dependent timeout demo.** `Thread.sleep` is a simplistic way to simulate slowness that makes tests flaky on CI. For this topic, you do not need to exceed the deadline; simply running the callback on another thread proves the mechanism. The example suite intentionally uses fast callbacks and assertions on thread/transaction state.

**Longer timeouts do not fix transaction leaks.** Increasing 5 seconds to 60 seconds gives the callback more time to finish, yet it **still runs on T2**. The issue is execution structure, not timeout duration.

**Blocking inside the same transaction can lock the database.** If TX-A holds a row lock and T2 inside a preemptive callback tries to update that same row, T2 may wait on TX-A while T1 waits for T2 to finish → deadlock-like hang. The examples insert a fresh row, avoid shared row locks, and do not make the main thread read uncommitted data before the worker writes.

**Verify post-rollback and clean up.** `@AfterTransaction` helps, yet any delete/compensation can still fail on network/DB outages; in CI, prefer ephemeral databases, dedicated schemas, containers per suite, or proper teardown policies. A test producing committed side effects must never run unconditionally on a shared DB.

**Do not overuse `@DirtiesContext`.** It forces Spring to rebuild the `ApplicationContext`, yet **does not automatically wipe external databases**. In-memory H2 may be reclaimed when the `DataSource`/context closes, whereas Testcontainers/external DBs keep data until you explicitly clean up. Use proper isolation.

**Watch out for global timeout configuration.** `@Timeout` in `INFERRED` mode reads a JUnit property; if a suite sets `SEPARATE_THREAD` globally, a Spring transactional test without an explicit mode can accidentally switch execution threads. Use `SAME_THREAD` for sensitive tests.

## 13. Self-Practice Exercises

1. **Compare APIs:** Create two tests using `assertTimeout` and `assertTimeoutPreemptively`, checking `Thread.currentThread()` and `TestTransaction.isActive()`. Why does code faster than the deadline still behave differently?
2. **Rollback:** Add an INSERT in a same-thread test, assert `count=1` inside the test, and assert `count=0` in `@AfterTransaction`. Which assertion actually verifies rollback?
3. **Preemptive commit:** In disposable H2, intentionally enable `PreemptiveWriteDemoTest`, explain why `@AfterTransaction` sees `count=1` and requires `DELETE`. Why isn't the demo enabled by default?
4. **`@Timeout`:** Change `SAME_THREAD` to `SEPARATE_THREAD` in a separate demo and inspect transaction state. Why does `threadMode` affect semantics more than whether a timeout occurs?
5. **`INFERRED`:** Check the value of `junit.jupiter.execution.timeout.thread.mode.default` in CI. Write tests with explicit `SAME_THREAD` to avoid config dependence.
6. **`@Async`:** Write a Spring `@Async` service method calling a repository. When the test has `@Transactional`, does the service use TX-A? Design valid cleanup.
7. **`REQUIRES_NEW`:** Call a `@Transactional(REQUIRES_NEW)` service from a transactional test on the same thread, and inspect after-commit/rollback. Why do writes persist even without preemptive timeouts?
8. **JDBC lock:** Try updating the same row from T1 and T2 in an isolated H2 environment with a statement timeout to prevent hangs. Avoid running this demo in default CI.
9. **Server thread:** Send HTTP POST to `@SpringBootTest(RANDOM_PORT)`, then roll back the test method. Why don't server-side database writes auto-roll back?
10. **Test cleanup:** Update the demo to always use a new ID/namespace and delete after the worker finishes; analyze what happens if the worker ignores interrupts.
11. **Other `ThreadLocal`s:** Read MDC/`SecurityContext` in T1 and T2 and observe the difference. Should you copy a raw JDBC `Connection` between threads to fix it? Explain the risks.
12. **Test design review:** Search a repository for preemptive timeouts inside tests with `@Transactional`/`@JdbcTest`/`@DataJpaTest`; propose replacing them with same-thread timeouts and adding `@AfterTransaction` verification where needed.

## 14. Official References

- [Spring Framework 6.1 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, `ThreadLocal`, preemptive timeouts, `@BeforeTransaction`/`@AfterTransaction`, and propagation.
- [JUnit Jupiter User Guide — Assertions, Preemptive Timeouts](https://docs.junit.org/5.11.4/user-guide/): `assertTimeout`, `assertTimeoutPreemptively`, and `ThreadLocal`/Spring warnings.
- [JUnit Jupiter User Guide — @Timeout Thread Modes](https://docs.junit.org/5.11.4/user-guide/): `SAME_THREAD`, `SEPARATE_THREAD`, `INFERRED`, and global configuration.
- [Spring Boot 3.3 — JDBC Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JdbcTest`, `JdbcTemplate`, embedded datasource, and rollback.
- [Spring TestTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `isActive`, `flagForRollback`/`flagForCommit`, `start`/`end`.
- [Spring @AfterTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): runs after a transactional test ends.
- [Spring TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): thread-bound resources and actual transaction flag.
- [JDK 17 ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread state.
- [Java SE 17 CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): async execution and executor boundaries.

**Remember:** In Spring TestContext, **a test-managed transaction belongs to the test thread**, not as an umbrella covering the entire JVM process. `assertTimeoutPreemptively` and `@Timeout(SEPARATE_THREAD)` can move test code onto a thread without that transaction; writes can commit separately and **fail to roll back at the end of the test**, even when the callback never times out. For transactional integration tests, prefer **`assertTimeout`** or **`@Timeout(SAME_THREAD)`**, verify real state with **`@AfterTransaction`**, and isolate/clean up any worker-thread side effects. Timeouts never replace proper transaction and resource boundary design.