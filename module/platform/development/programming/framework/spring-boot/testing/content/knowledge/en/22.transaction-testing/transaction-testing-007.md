# REQUIRES_NEW and Data That Can Commit Outside the Test Transaction

## 1. The Symptom: @Transactional Is on the Test Yet Data Still Persists

In **Spring Boot - testing**, under **Transaction Testing**, a common misconception is that every database write inside a JUnit test annotated with `@Transactional` will automatically be rolled back. Spring TestContext only rolls back **the transaction managed by the test listener**. A Spring bean method annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` can open an **independent physical transaction** and commit while the test-managed transaction is still active.

Suppose a service records a stock receipt and also writes an audit log:

~~~text
TestContext opens transaction T_TEST
        |
        +-- InventoryWriter.save() [REQUIRED, joins T_TEST]
        |
        +-- AuditWriter.record()   [REQUIRES_NEW]
        |       |
        |       +-- suspend T_TEST
        |       +-- open T_AUDIT on another resource/connection
        |       +-- INSERT audit
        |       +-- COMMIT T_AUDIT
        |       +-- resume T_TEST
        |
        +-- test ends: ROLLBACK T_TEST

After rollback:
  data belonging to T_TEST   -> gone
  data belonging to T_AUDIT  -> remains
~~~

This **does not prove Spring TestContext rollback is broken**. The two scopes are using different physical transactions. The new transaction committed independently and cannot be rolled back merely because the outer transaction ends later.

This lesson answers thoroughly: how `REQUIRES_NEW` works; how it differs from `REQUIRED`/`NESTED`; when TestContext opens and rolls back transactions; how to test commits by observing data **after the test**; how to clean up; why self-invocation, separate threads, real HTTP, DB locks, and connection pools affect results; and when to use or avoid `REQUIRES_NEW` in an application.

The main example uses **Java 17, Spring Boot 3.5.16, Spring JDBC, H2, and JUnit Jupiter**. It includes an application, two services, database configuration, DDL, and three complete test cases. JDBC is chosen to observe commits/rollbacks directly, avoiding ambiguity from JPA flush and first-level caching.

## 2. Test-Managed Transactions vs. Spring Service Transactions

According to Spring Framework, there are three transaction boundary types:

| Type | Managed by | Example |
| --- | --- | --- |
| **Test-managed transaction** | `TransactionalTestExecutionListener` or `TestTransaction` | `@Transactional` on a JUnit test class/method |
| **Spring-managed transaction** | Transaction interceptor/AOP of a Spring bean | `@Transactional(REQUIRED)` or `REQUIRES_NEW` on a service |
| **Application-managed transaction** | Code explicitly invoking transaction APIs | `TransactionTemplate`, `PlatformTransactionManager` |

A test-managed transaction is normally bound to the **test execution thread**, using the `PlatformTransactionManager` discovered by Spring TestContext or specified via qualifier. A `REQUIRED` service method called from the test on the same thread normally joins that transaction. A `REQUIRES_NEW` service method **does not** join: Spring suspends the outer resource and creates a new transaction.

An important consequence: `@Rollback`/`@Commit` on a test governs the outcome of the **test-managed transaction**, not a "command to roll back everything the application ever committed."

### Conditions for Propagation to Actually Apply

- The service is a **bean in the Spring `ApplicationContext`**.
- The public method is called through the **Spring transaction proxy** in standard proxy-based setups. `this.someRequiresNewMethod()` can bypass the proxy.
- There is a transaction manager matching the datasource/resource under test.
- The manager supports opening/suspending/resuming the relevant transaction.
- The connection pool has enough connections for both outer and inner.
- The test runs synchronously on the transaction thread if relying on test-managed rollback.

Do not take the presence of an annotation on a method as proof that transaction advice actually executed. A Mockito mock or direct Java instantiation does not trigger Spring transactions.

## 3. REQUIRED, REQUIRES_NEW, NESTED: Similar Names, Different Meanings

| Propagation | When an outer transaction exists | Physical transaction | When outer rolls back |
| --- | --- | --- | --- |
| `REQUIRED` | Joins outer | Same physical transaction | Writes participating in outer all roll back |
| `REQUIRES_NEW` | Suspends outer, opens new transaction | **Different** physical transaction | Committed inner work remains |
| `NESTED` | Creates a savepoint inside same transaction when supported | Usually same physical transaction | Outer rollback also erases nested changes |
| `SUPPORTS` | Joins outer if present | Follows outer if present | When joined, rolls back with outer |
| `NOT_SUPPORTED` | Suspends outer and runs without transaction | Does not create T_NEW | SQL may auto-commit per datasource |
| `MANDATORY` | Requires an outer transaction to exist | Joins outer | Fails if no outer exists |

`REQUIRES_NEW` creates a **new physical transaction** and decides its own commit/rollback. `NESTED` relies on savepoints; releasing a savepoint **does not** turn nested changes into an independent commit. `NESTED` support also depends on the transaction manager and JDBC savepoints; do not assume every JPA manager works identically to JDBC.

~~~text
REQUIRED:
  T_TEST [write A][write B][ROLLBACK]     => A=0, B=0

REQUIRES_NEW:
  T_TEST [write A]---suspend----------[ROLLBACK] => A=0
                  T_NEW [write B][COMMIT]         => B=1

NESTED (when savepoints are supported):
  T_TEST [write A][savepoint][write B][release][ROLLBACK]
                                                => A=0, B=0
~~~

When **no outer transaction exists**, both `REQUIRED` and `REQUIRES_NEW` can open a new transaction and commit on normal return; however, their semantics diverge when an outer transaction already exists.

## 4. Transaction Lifecycle of a JUnit Jupiter Test

In a `@SpringBootTest` test (or a test slice with a transaction manager) annotated with `@Transactional`, Spring TestContext opens a test-managed transaction before the method and rolls back by default afterward. General sequence:

~~~text
@BeforeTransaction              [outside T_TEST]
           |
TestContext BEGIN T_TEST
           |
@BeforeEach                     [inside T_TEST]
           |
@Test                           [inside T_TEST]
           |
@AfterEach                      [inside T_TEST]
           |
TestContext ROLLBACK/COMMIT T_TEST
           |
@AfterTransaction               [outside T_TEST]
~~~

This is why **`@AfterEach` is unsuitable for concluding data committed**: it can still see uncommitted INSERTs inside the same test transaction, which Spring then rolls back right afterward.

`@BeforeTransaction` and `@AfterTransaction` are Spring TestContext lifecycle hooks for transactional tests. They can query the DB **outside the test transaction**, making them ideal for proving an inner transaction committed independently and cleaning up leftover data.

`@BeforeAll` and `@AfterAll` (class-level JUnit lifecycle) do not normally run inside a test-managed transaction. Avoid casually using them to write shared data when tests run in parallel or share a database.

### @Transactional on a Test Does Not Have Full Service Propagation

Spring TestContext supports only a few attributes of `@Transactional` on a test: the transaction manager name, and `Propagation.NOT_SUPPORTED`/`NEVER` to **skip opening a test transaction**. Do not write:

~~~java
// Wrong intent: do not put this annotation on a JUnit test
// expecting TestContext to enforce full REQUIRES_NEW semantics.
@Test
@Transactional(propagation = Propagation.REQUIRES_NEW)
void misleadingTest() {
}
~~~

This is a **counter-example**, not part of the runnable program. To test `REQUIRES_NEW`, **place the propagation on a Spring service bean invoked through a proxy**.

Similarly, `rollbackFor`/`noRollbackFor` on a test method does not control the test listener the way it does on a service method. For test-managed transactions, use `@Rollback`, `@Commit`, or `TestTransaction`.

## 5. Preparing the Runnable Example: In-Memory Database and Two Services

The example uses table `tx_events`, where each record is identified by `event_key`. Two writers in separate beans:

- `RequiredEventWriter` has a `@Transactional` method (default `REQUIRED`); when a test transaction exists, it writes into **T_TEST**.
- `IndependentEventWriter` has a `@Transactional(REQUIRES_NEW)` method; it suspends `T_TEST` and writes/commits in **T_NEW**.
- A second method on the independent writer intentionally throws `IllegalStateException` to prove inner **independent rollback**.
- The test generates a different UUID in `@BeforeTransaction`, preventing data from bleeding across tests.
- `@AfterTransaction` asserts **after** the outer transaction rolled back/committed, then cleans up committed rows in `finally`.

No HTTP server, Docker, or external database is required. H2 suffices for demonstrating semantics; to test production-like locking/isolation, run against the same database type as production.

### File Tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/txdemo/
  TxDemoApplication.java
  RequiredEventWriter.java
  IndependentEventWriter.java
src/test/resources/
  application.properties
  schema.sql
src/test/java/com/example/txdemo/
  RequiresNewIsolationTest.java
~~~

All Java files use package `com.example.txdemo`. The project needs the Gradle Wrapper to run the commands at the end of the lesson.

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

### settings.gradle

~~~groovy
rootProject.name = 'requires-new-demo'
~~~

`spring-boot-starter-jdbc` provides `JdbcTemplate`/JDBC transaction infrastructure and HikariCP. `spring-boot-starter-test` includes JUnit Jupiter, AssertJ, and Spring TestContext. H2 is scoped only to test runtime; running the application standalone outside tests requires configuring an appropriate JDBC driver/datasource.

### src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS tx_events (
    event_key VARCHAR(100) PRIMARY KEY,
    category VARCHAR(32) NOT NULL
);
~~~

This schema intentionally omits foreign keys. Outer and inner write **rows with different primary keys** so the inner transaction is never blocked trying to reference an uncommitted outer row.

### src/test/resources/application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:requiresnew_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
~~~

`maximum-pool-size=4` provides enough connections for a single-threaded demo with outer + inner. This is **not** a production sizing formula. `DB_CLOSE_DELAY=-1` keeps the in-memory DB alive for the JVM's lifetime, so tests must clean up committed rows rather than relying on closing a connection to discard data.

### src/main/java/com/example/txdemo/TxDemoApplication.java

~~~java
package com.example.txdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }
}
~~~

`@SpringBootTest` will locate this application configuration. Neither Spring MVC nor WebFlux starter is needed since the experiment tests JDBC transactions.

## 6. REQUIRED Writer: Joins the Outer Test Transaction

**File `src/main/java/com/example/txdemo/RequiredEventWriter.java`:**

~~~java
package com.example.txdemo;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiredEventWriter {
    private final JdbcTemplate jdbc;

    public RequiredEventWriter(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional
    public void write(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "REQUIRED"
        );
    }
}
~~~

When the test transaction is active on the same thread and transaction manager, Spring-managed `@Transactional` (default `REQUIRED`) joins **T_TEST**. Even after `write` returns, the SQL write remains inside the **uncommitted** outer transaction. At the end of the test, rolling back `T_TEST` deletes that record.

If no outer transaction exists, the `REQUIRED` method opens its own transaction and commits/rolls back based on its outcome. Thus you cannot claim every `REQUIRED` method always rolls back or always commits: you must check whether a transaction already exists.

## 7. REQUIRES_NEW Writer: Commits and Rolls Back Independently

**File `src/main/java/com/example/txdemo/IndependentEventWriter.java`:**

~~~java
package com.example.txdemo;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentEventWriter {
    private final JdbcTemplate jdbc;

    public IndependentEventWriter(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "INDEPENDENT"
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeThenFail(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "FAILED_INNER"
        );

        throw new IllegalStateException("audit rejected");
    }
}
~~~

When called through a Spring proxy inside an outer transaction, each `REQUIRES_NEW` method:

1. Suspends the outer's transaction resources.
2. Opens a new transaction with appropriate resources (typically another JDBC connection).
3. Executes the `INSERT` inside the new transaction.
4. If `write` returns normally: commits the new transaction.
5. If `writeThenFail` throws an unchecked exception: rolls back the new transaction per default rollback rules.
6. Resumes the outer transaction.

**Note:** independent inner rollback **does not force the outer to roll back**. The caller can catch the exception and continue if the outer remains valid. In the demo, the outer rolls back at the end of the test due to `@Rollback`, not because the inner forced an outer rollback.

The two writers are separate `@Service` beans so test calls go through proxies. If `this.writeThenFail(...)` were called internally within the same class under proxy-based AOP, propagation might **not** activate.

## 8. Integration JUnit Suite: Verifying Committed Data After the Test

**File `src/test/java/com/example/txdemo/RequiresNewIsolationTest.java`:**

~~~java
package com.example.txdemo;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Transactional
@Rollback
class RequiresNewIsolationTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    RequiredEventWriter requiredWriter;

    @Autowired
    IndependentEventWriter independentWriter;

    private String runId;
    private boolean expectedRequiredCommitted;
    private boolean expectedIndependentCommitted;

    private String requiredKey() {
        return "required-" + runId;
    }

    private String independentKey() {
        return "new-" + runId;
    }

    private String failedKey() {
        return "failed-" + runId;
    }

    private int count(String eventKey) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events WHERE event_key = ?",
                Integer.class,
                eventKey
        );
        return result == null ? 0 : result;
    }

    @BeforeTransaction
    void prepareOutsideTransaction() {
        runId = UUID.randomUUID().toString();
        expectedRequiredCommitted = false;
        expectedIndependentCommitted = false;

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(count(requiredKey())).isZero();
        assertThat(count(independentKey())).isZero();
        assertThat(count(failedKey())).isZero();
    }

    @Test
    void newTransactionCommitsEvenWhenTestTransactionRollsBack() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        requiredWriter.write(requiredKey());
        independentWriter.write(independentKey());
        expectedIndependentCommitted = true;

        // Sees the outer transaction's own uncommitted change;
        // does not yet prove it committed.
        assertThat(count(requiredKey())).isEqualTo(1);
    }

    @Test
    void failingInnerTransactionRollsBackItsOwnInsert() {
        requiredWriter.write(requiredKey());

        assertThatThrownBy(() ->
                independentWriter.writeThenFail(failedKey())
        ).isInstanceOf(IllegalStateException.class)
         .hasMessage("audit rejected");

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count(requiredKey())).isEqualTo(1);
        // T_TEST will roll back per the class annotation.
    }

    @Test
    @Commit
    void commitOverridesDefaultTestRollback() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isFalse();

        requiredWriter.write(requiredKey());
        independentWriter.write(independentKey());

        expectedRequiredCommitted = true;
        expectedIndependentCommitted = true;
    }

    @AfterTransaction
    void verifyCommittedStateAndCleanUp() {
        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(
                TransactionSynchronizationManager
                        .isActualTransactionActive()
        ).isFalse();

        try {
            assertThat(count(requiredKey()))
                    .isEqualTo(expectedRequiredCommitted ? 1 : 0);
            assertThat(count(independentKey()))
                    .isEqualTo(expectedIndependentCommitted ? 1 : 0);
            assertThat(count(failedKey())).isZero();
        } finally {
            jdbc.update(
                    """
                    DELETE FROM tx_events
                    WHERE event_key IN (?, ?, ?)
                    """,
                    requiredKey(),
                    independentKey(),
                    failedKey()
            );
        }
    }
}
~~~

### 8.1. What Exactly Do the Three Cases Prove?

| Case | Outer T_TEST | Inner T_NEW | After test transaction ends, before cleanup |
| --- | --- | --- | --- |
| `newTransactionCommitsEvenWhenTestTransactionRollsBack` | `REQUIRED` write then **rollback** | `REQUIRES_NEW` write then **commit** | `required=0`, `new=1` |
| `failingInnerTransactionRollsBackItsOwnInsert` | `REQUIRED` write then **rollback** | `REQUIRES_NEW` insert then exception → **rollback** | `required=0`, `failed=0` |
| `commitOverridesDefaultTestRollback` | Method-level `@Commit` makes `T_TEST` **commit** | `REQUIRES_NEW` **commit** | `required=1`, `new=1` |

The first two tests use default/`@Rollback` rollback; the third has `@Commit` at the method level, overriding the class-level rollback policy.

**The most important part is `@AfterTransaction`.** When this hook runs, Spring has completed committing/rolling back the test-managed transaction. Only then can queries distinguish **an independently committed row** from **a row existing temporarily inside the outer transaction**. After asserting, `finally` deletes only the `runId` rows to avoid polluting subsequent tests.

### 8.2. Why Not Check Entirely Inside @AfterEach?

`@AfterEach` of a transactional test still runs inside **T_TEST**. A `SELECT` inside the same `T_TEST` can see `T_TEST`'s own uncommitted data, so it cannot answer "does the record survive rollback?". `@AfterTransaction` is the right fit.

### 8.3. Why Use a UUID for Each Test?

Because `REQUIRES_NEW` tests create real committed rows. If all tests shared `event_key = "audit"`, running the suite multiple times could hit `duplicate key` errors or falsely assert data from an earlier test. UUIDs prevent collisions; scoped cleanup in `finally` avoids deleting other tests' data.

### 8.4. Can You Observe the Inner Commit Inside T_TEST?

With H2's default `READ_COMMITTED` and appropriate access, the outer transaction can observe another transaction's commit. However, under `REPEATABLE_READ`, snapshots/caching or the JPA first-level cache may return stale data. Always verify committed state **after the outer ends** using a new transaction/connection rather than relying on a query inside the outer transaction.

### 8.5. What If an @AfterTransaction Assertion Fails?

`finally` still runs cleanup along normal JVM exception paths, minimizing dirty data when a test reports FAIL. If the process is killed/crashes, in-JVM cleanup will not run; critical CI pipelines should use dedicated test schemas/databases or out-of-process lifecycle teardown.

## 9. Deeper Dive: Why Is Flush Not Equivalent to Commit?

The example uses JDBC, so `JdbcTemplate.update` executes SQL immediately inside the transaction. Still, **SQL sent to the database does not mean committed**: the JDBC connection remains in a transaction that can roll back.

In JPA, a change to a managed entity might only be sent to the DB at `flush()` or commit. Thus two concepts are often conflated:

- **Flush:** synchronizes persistence context state with the database inside the transaction; SQL may be sent, yet **can still roll back**.
- **Commit:** ends the transaction successfully, making changes durable per database semantics.

A JPA `@Transactional(REQUIRES_NEW)` service can call `repository.save(...)` and return; the transaction interceptor commits when the method completes, flushing via the JPA provider as needed. If the method throws a runtime exception before commit, the new transaction can roll back.

In JPA tests, if you want to catch DB constraints/optimistic locking at the right moment, consider `entityManager.flush()` or `saveAndFlush`. However, **never use `flush()` as proof that the outer transaction committed**.

### EntityManager First-Level Cache

If outer `T_TEST` already loaded entity X, and inner `T_NEW` updates X and commits, the outer's `EntityManager` may still hold the previously loaded object X. `findById` in the outer will not necessarily re-read from the DB. Use a fresh context or appropriate `clear()/refresh()`, and best of all, query **after the outer transaction** to prove final state.

In the simple JDBC example there is no first-level entity cache, keeping the focus on propagation.

## 10. When Can an Inner Transaction Not See Outer Data?

`REQUIRES_NEW` uses a different physical transaction; it cannot by default read **uncommitted** data in the outer transaction.

A design bug:

~~~text
T_TEST: INSERT orders(id=123)      [uncommitted]
T_NEW:  INSERT audit(order_id=123) [foreign key referencing 123]

Under READ_COMMITTED, T_NEW does not yet see committed order 123.
May block on locks/constraints, time out, or fail.
~~~

The exact outcome depends on the DB, lock manager, isolation, and foreign key implementation. Do not assume every DB throws the exact same exception.

The demo intentionally avoids this by inserting distinct primary keys into a `tx_events` table without foreign keys. In real business logic:

- If audit must commit independently **even when the order fails**, store only independent metadata such as `requestId`, actor, and an "attempted/failed" event.
- If the audit event means **the order succeeded**, do not commit it before the outer commits.
- If post-commit processing is needed, consider `@TransactionalEventListener(phase=AFTER_COMMIT)`, transaction synchronization, or a **transactional outbox**.
- If atomicity between order and audit is required, `REQUIRES_NEW` may be the **wrong** choice because it intentionally breaks atomicity.

Never "fix" this by turning on `READ_UNCOMMITTED` globally without analyzing consistency and DB semantics.

## 11. Spring Transaction Proxy and the Self-Invocation Trap

An example that does not run as imagined:

~~~java
@Service
class OrderService {
    @Transactional
    public void create() {
        persistOrder();
        audit();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void audit() {
        // Write audit...
    }
}
~~~

This is an **explanatory skeleton**, lacking `persistOrder()` and imports. Under default proxy-based transaction management, calling `audit()` on **the same `this` instance** bypasses the Spring AOP proxy; the `REQUIRES_NEW` annotation may have no effect.

What you should do:

~~~java
@Service
class OrderService {
    private final IndependentEventWriter auditWriter;

    OrderService(IndependentEventWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void create(String eventKey) {
        // Write order data in outer transaction...
        auditWriter.write(eventKey); // through Spring-managed proxy
    }
}
~~~

This is also a skeleton, yet the principle is sound: **call a public method on a separate bean** so transaction advice triggers. In the main runnable example, the test injects and directly calls the two beans `RequiredEventWriter` and `IndependentEventWriter`.

Testing with Mockito `verify(writer).write(...)` **does not** prove a physical commit. When the goal is transaction behavior, use a real database and check data after completion.

## 12. What Do @Commit, @Rollback, and TestTransaction Control?

| API/annotation | Controls | Cannot do |
| --- | --- | --- |
| `@Rollback` | Rolls back `T_TEST` after test method | Does not roll back already-committed `T_NEW` |
| `@Commit` | Commits `T_TEST` after test method | Does not merge all service calls into one transaction |
| `TestTransaction.flagForRollback()` | Marks `T_TEST` to roll back when ended | Does not "undo" an inner commit |
| `TestTransaction.flagForCommit()` | Marks `T_TEST` to commit when ended | Does not change propagation on services |
| `TestTransaction.end()` | Ends the current test-managed transaction | Does not auto-clean committed data outside it |
| `TestTransaction.start()` | Starts a new test-managed transaction | Does not restore an old finished transaction |

`@Commit` on a test method overrides class-level `@Rollback`, as in the example. It changes the **ending policy of `T_TEST`**, not the `REQUIRES_NEW` annotation on the bean.

When you want to observe post-rollback state actively mid-test:

~~~java
// Illustrative code body inside a transactional @Test:
TestTransaction.flagForRollback();
TestTransaction.end();

assertThat(TestTransaction.isActive()).isFalse();
// Use JDBC/query from a new connection to inspect committed data.

TestTransaction.start();
// Subsequent operations can continue in the new T_TEST.
~~~

This is not a standalone Java file; it requires Spring TestContext and matching dependencies. For typical needs, `@AfterTransaction` is clearer because it does not alter the lifecycle mid-test.

### Do Not Use Service rollbackFor to Control Tests

`@Transactional(rollbackFor=IOException.class)` on a service bean adjusts rollback rules of the **Spring transaction interceptor**. TestContext does not fully support `rollbackFor` on a **test method's** `@Transactional` annotation; use `@Rollback`, `@Commit`, or `TestTransaction.flagForRollback/flagForCommit`.

## 13. Checked Exceptions, RuntimeExceptions, and Inner Rollback

Under default Spring transaction rules, unchecked exceptions (`RuntimeException` and `Error`) trigger rollback; checked exceptions normally do not trigger rollback automatically unless configured.

The runnable example in section 7 uses:

~~~java
throw new IllegalStateException("audit rejected");
~~~

`IllegalStateException` is an unchecked exception, so inner `REQUIRES_NEW` rolls back by default.

A production method with checked exceptions might need:

~~~java
@Transactional(
        propagation = Propagation.REQUIRES_NEW,
        rollbackFor = java.io.IOException.class
)
public void recordWithIO() throws java.io.IOException {
    // DB write logic that may throw IOException.
}
~~~

This is an illustrative method; not enough class structure to compile standalone. The rollback rules of the **inner** do not directly dictate the outcome of the **outer**. If the exception propagates out of the `@Transactional` outer method uncaught, the outer may also roll back per its own rules. If the caller catches the exception, the outer may continue depending on resource/transaction state.

After an exception marks a transaction rollback-only, never try to re-commit **that same** failed transaction. Roll back and open a fresh transaction if retry is truly needed.

## 14. Connection Pool Exhaustion: The Cost of REQUIRES_NEW

Spring Framework warns that `REQUIRES_NEW` can exhaust connection pools, because the outer transaction holds onto its connection while the inner needs **another** connection.

~~~text
Pool size = 2, two concurrent requests

Thread A: T_OUTER holds connection 1
Thread B: T_OUTER holds connection 2

Thread A calls REQUIRES_NEW -> waits for a 3rd connection
Thread B calls REQUIRES_NEW -> waits for a 3rd connection

Neither request releases its outer connection:
  -> pool starvation / connection timeout
~~~

Spring Framework recommends a connection pool larger than the number of concurrent threads by at least one connection when using `REQUIRES_NEW`. That is a **minimum guideline to avoid a common failure mode**, not a substitute for measuring concurrency, nested transaction depth, and connection hold times.

In the demo, `spring.datasource.hikari.maximum-pool-size=4` suffices for a single test thread with outer + inner. The number 4 does not prove a production app with 100 concurrent requests will be safe.

If an inner call hangs, do not assume a Java race bug right away. Check:

- Active/idle/pending pool connections.
- DB lock waits if the inner touches a row locked by the outer.
- Foreign keys pointing to uncommitted outer data.
- Isolation/timeouts across transaction managers.
- Depth of nested independent transactions.
- Connection acquisition and transaction timeouts.

Stress tests must use deliberate timeouts; never use `Thread.sleep` as a way to "synchronize" threads.

## 15. @Transactional on Tests and Real HTTP Servers

Another way data survives without `REQUIRES_NEW` is **an HTTP request handled on another thread**.

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpTest {
    // HTTP client calls embedded server running on a separate thread.
}
~~~

This is a skeleton, not a standalone test. When using `TestRestTemplate`, RestAssured, or a real HTTP client against a server on a random port, the server typically handles the request in its own transaction. Even if the test client has `@Transactional`, server-side commits are **not** inside the client's test-managed transaction and **do not auto-roll back** when the test ends.

Comparison:

| Behavior | Does test-managed rollback normally apply? |
| --- | --- |
| Direct call to Spring `REQUIRED` service on same thread | Yes, if same transaction manager |
| Direct call to `REQUIRES_NEW` service | No for committed inner work |
| Real HTTP request to server on another thread | Not automatically |
| `@Async`/executor thread writing DB | Not automatically |
| `MockMvc` synchronous request on same thread | Can join, depending on handler/thread/transaction setup |
| JUnit preemptive timeout moving test body to another thread | Risks executing outside `T_TEST` |

Spring TestContext specifically warns that JUnit's `assertTimeoutPreemptively(...)` can run the body on a different thread from the transaction-bound thread, leaving real writes **un-rolled-back**. Avoid such timeouts when relying on test-managed rollback; pick a timeout mechanism that keeps the same thread or design explicit transaction boundaries.

## 16. Do @DataJpaTest and @JdbcTest Have Similar Traps?

Yes. Slices like `@DataJpaTest`/`@JdbcTest` usually open a test-managed transaction and roll back after the test. Yet an imported bean or application call using `REQUIRES_NEW` can still open an independent transaction and commit.

**Note:** data slices usually do not scan all application `@Service` beans. To test a real service with `REQUIRES_NEW` propagation, use `@Import(ServiceClass.class)` intentionally or `@SpringBootTest`. Never swap the service with a Mockito mock and claim you tested transaction propagation.

In JPA tests, also remember to:

- Flush `EntityManager` to detect constraints/optimistic locking on time.
- Clear or query in a new persistence context to avoid stale first-level cache reads.
- Identify datasources/transaction managers if the application has multiple.
- Avoid confusing committed `@Sql` setup with rolled-back test entities.

`@DirtiesContext` mainly invalidates the Spring context cache and **does not automatically roll back committed data on an external DB**. Ephemeral test databases/clusters destroyed by lifecycle teardown can clean up, yet that comes from infrastructure, not from this annotation.

## 17. @TransactionalEventListener and Outbox: When to Use Instead of REQUIRES_NEW?

If the goal is to **log an attempt to perform an action even when business logic rolls back**, an independent audit can make sense. However, if you want to announce "order succeeded," an inner audit committing **before** the outer commits can produce false data when the outer rolls back.

The solution must match semantics:

- **Attempt/failure audit:** can use `REQUIRES_NEW` if it does not depend on uncommitted outer rows.
- **Post-commit notification:** use a post-commit callback, `@TransactionalEventListener(phase = AFTER_COMMIT)`, or explicit orchestration.
- **Durable messaging without crash loss:** consider a **transactional outbox** committed atomically alongside the business row.
- **Atomicity for both order and audit:** use the same `REQUIRED` transaction if the contract requires both to commit/roll back together.

Illustrative listener snippet:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // Perform appropriate post-commit work after transaction commits.
}
~~~

This is only a skeleton requiring an event type/imports and delivery setup. An `AFTER_COMMIT` listener does not automatically provide a fresh transaction for DB writes: if durable DB writes are needed after commit, design a valid new transaction, such as delegating to a `REQUIRES_NEW` Spring bean. For critical events, evaluate JVM crash/message loss risks rather than assuming the listener guarantees exactly-once delivery.

## 18. Safe Cleanup: What Is Often Missed When Tests Are Green

Because the inner transaction committed, relying solely on end-of-test rollback can leave behind:

- Audit rows remaining in the DB.
- Held primary/unique keys causing later tests to fail.
- Tenant/user data leaking between suites.
- Order-dependent test outcomes.
- Messages/notifications or non-DB side effects that Spring TestContext cannot "roll back."

Options:

| Technique | Benefit | Risk / limitation |
| --- | --- | --- |
| `@AfterTransaction` + cleanup | Sees committed state then deletes exact data | Process crash may skip cleanup |
| `@BeforeTransaction` setup | Seeds data before test transaction | Data can linger if cleanup is forgotten |
| UUID per test | Avoids colliding with other tests' rows | Still must clean up committed data |
| Per-test DB/schema | High isolation | Heavier startup/teardown cost |
| Testcontainers DB matching production | Tests real lock/isolation behavior | Needs Docker and lifecycle management |
| `@SqlConfig(transactionMode=ISOLATED)` | Runs SQL script in a separate transaction per config | Must understand listener/script/cleanup ordering |
| `@DirtiesContext` | Resets Spring `ApplicationContext` | Does not guarantee wiping external DB |

In the example's `@AfterTransaction`, `finally` cleans up **even on normal test assertion failures**. The SQL deletes only the three specific keys instead of `DELETE FROM tx_events` table-wide, reducing the risk of breaking other tests' data.

If tests share a database across parallel workers, **never use table-wide cleanup**. In important CI pipelines, use an ephemeral database/schema so even a killed process leaves no dirty state for the next run.

### @Sql with transactionMode ISOLATED

Spring supports configuring an `@Sql` script to run in an independent transaction when a transaction manager exists. Annotation snippet only:

~~~java
@Sql(
        scripts = "/cleanup-test-data.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
~~~

You must supply the real SQL file, imports, and verify lifecycle ordering; **do not copy this snippet as a complete test**. Do not assume the script timing is always after the outer transaction in every setup: listener/phase mechanics must be verified. For **asserting right after outer rollback**, `@AfterTransaction` is usually clearer.

## 19. Diagnosing Issues by Symptom

| Symptom | Possible cause | Action |
| --- | --- | --- |
| `@Transactional` test PASSES yet audit exists in DB | Inner `REQUIRES_NEW` committed | Query after `T_TEST`, clean up intentionally |
| `@AfterEach` sees record, another test does not | It queried inside outer before rollback | Use `@AfterTransaction` |
| `REQUIRES_NEW` annotation present yet inner does not commit | Self-invocation or proxy did not run | Separate bean, check Spring proxy/transaction logs |
| Inner cannot see outer's newly created order | Outer uncommitted, separate transactions | Avoid FKs/dependencies on uncommitted data |
| Inner insert hangs/times out | Pool out of connections or DB lock | Inspect Hikari stats/lock waits |
| JPA saves then test misses exception | SQL not flushed yet | `flush()`/`saveAndFlush` when needed |
| Data persists even when using only `REQUIRED` over HTTP | Server thread has its own transaction | Test/clean server DB outside `T_TEST` |
| Test fails with duplicate key on re-run | Inner row committed from prior run | UUID/test namespace + teardown |
| `@Commit` does not roll back | Policy of `T_TEST` was intentionally changed | Check class/method annotation precedence |
| `NESTED` "commits" yet data still rolls back with outer | `NESTED` uses savepoint, not physical commit | Distinguish `NESTED`/`REQUIRES_NEW` |
| Spring `TestTransaction` not active | Test has no active test-managed transaction | Check `@Transactional`, manager, and propagation |
| An async task finishes after cleanup | Call was not awaited/joined | Synchronize lifecycle and side effects |
| Mock test calls writer yet DB is empty | Mockito does not open SQL transactions | Use an appropriate integration test |

**Never fix failures by arbitrarily increasing wait times or adding `@Commit` to every test**. That can mask broken transaction design and leave test data around longer.

## 20. When Should and Shouldn't You Use REQUIRES_NEW?

**Appropriate** when you need a small, independent operation that can commit/roll back separately and **does not depend on uncommitted outer data**: auditing failed attempts, recording technical events, or a designed independent unit of work.

**Inappropriate** when business logic requires all changes to be atomic; when the inner must reference an uncommitted outer row; when the inner records a "success" message before the outer commits; when the connection pool is insufficient; or when you merely want tests to stay green without cleaning up data.

When retrying after an exception, never retry inside a transaction already marked rollback-only. Open a new transaction, re-read data, and design for idempotency/uniqueness. `REQUIRES_NEW` does not automatically deliver exactly-once guarantees, distributed transactions, or crash-safe event durability.

## 21. QA Checklist for Testing Transaction Propagation

- [ ] Clearly identified test-managed `T_TEST` and service-managed `T_NEW`?
- [ ] `PlatformTransactionManager` and proper database connection resource present?
- [ ] `REQUIRES_NEW` placed on a public method of a Spring bean, invoked via proxy?
- [ ] Not placing `@Transactional(REQUIRES_NEW)` on a JUnit test and treating it as service semantics?
- [ ] Tests distinguish `REQUIRED`, `REQUIRES_NEW`, and `NESTED`/savepoints?
- [ ] Data verified AFTER outer rollback/commit via `@AfterTransaction`/a new transaction?
- [ ] Not using `@AfterEach` or self-queries inside `T_TEST` as proof of commit?
- [ ] Included case where inner commits, outer rolls back, and inner row remains?
- [ ] Included case where inner unchecked exception rolls back only the inner?
- [ ] Included `@Commit`/`@Rollback` case if contrasting outer policies?
- [ ] Cleanup outside `T_TEST` and unique keys per test in place?
- [ ] Not running dangerous deletes against production/shared DBs?
- [ ] Outer does not lock rows that inner must update or reference while uncommitted?
- [ ] Pool has enough connections for outer + inner, with proper timeouts?
- [ ] For JPA, accounted for flush and first-level caching?
- [ ] For real HTTP/async, accounted for different transaction threads?
- [ ] Not using preemptive timeouts that switch the test thread when relying on rollback?
- [ ] Not assuming `@DirtiesContext` deletes committed external DB data?
- [ ] Not using `REQUIRES_NEW` for "business success" events before outer commits without consistency design?
- [ ] If DB isolation/lock semantics decide production behavior, included integration tests on a production-like DB?

## 22. Running Tests and Reading Results Accurately

On Linux/macOS from a project with the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.txdemo.RequiresNewIsolationTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.txdemo.RequiresNewIsolationTest"
~~~

There are **3 JUnit cases** in `RequiresNewIsolationTest`. Expected table checked by `@AfterTransaction`, before cleanup:

~~~text
Case 1: T_TEST rollback, T_NEW commit   -> required=0, new=1
Case 2: T_TEST rollback, T_NEW rollback -> required=0, failed=0
Case 3: T_TEST commit,   T_NEW commit   -> required=1, new=1
~~~

These are **expected results based on Java/Spring/H2 semantics**, not console output observed from running Gradle. The code prints no `System.out.println`, so there is no fixed application stdout. Without a JDK, Gradle Wrapper, or dependencies, tests cannot run with plain `javac` lacking the Spring/JUnit classpath.

**Remember:** `@Transactional` on a test only ensures rollback of **`T_TEST`**. `@Transactional(propagation = REQUIRES_NEW)` on a service uses an **independent physical transaction** that can commit before `T_TEST` finishes. When you need to prove data survived, check **after** outer completion and clean up committed state intentionally.

### Official References

- [Spring Framework — TestContext transaction management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html)
- [Spring Framework — @TransactionalEventListener](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot 3.5 — Gradle plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)
