# @Rollback, @Commit, and Controlling Data After Each Test in Spring Boot

When testing database-interacting code, a test can **PASS** yet still leave data behind for another test, or conversely: data appears inside the same transaction yet **disappears right after the test** due to rollback. Misunderstanding this leads to two opposite problems: "false green" tests caused by not flushing/committing at the right moment, and **order-dependent** tests caused by using `@Commit` or independent transactions without cleanup.

In Spring Boot, **`@Transactional` on a JUnit test**, **`@Rollback`**, **`@Commit`**, **`@BeforeTransaction`**, **`@AfterTransaction`**, and **`TestTransaction`** are tools of the **Spring TestContext Framework**. They must be distinguished from **`@Transactional` on a business service**, from real transactions on an HTTP server thread, from SQL initializers, and from database cleanup mechanisms.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring Data JPA, Hibernate, H2, and JUnit Jupiter**. Complete runnable examples following a Gradle structure are included: default rollback, commit then cleanup, `@Rollback(false)`, method overriding class-level `@Commit`, `TestTransaction.commit/end/start`, and a **`Propagation.REQUIRES_NEW`** service that intentionally creates a commit not rolled back by the outer test. Test outcomes are presented as **expected from the code**, not stdout from an executed Gradle session.

## 1. The Most Important Model: Test-Managed Transaction

Spring TestContext has a **`TransactionalTestExecutionListener`** (configured by default in most Spring integration tests). When a test has **Spring `@Transactional`** on the class or method, and the `ApplicationContext` has a **`PlatformTransactionManager`**, the listener opens a **test-managed transaction before the test method runs** and ends the transaction when the test finishes.

By default, the test transaction is **ROLLED BACK**. This is behavior of the test framework, **not** a rule that every business transaction in production also rolls back.

~~~text
Spring TestContext prepares ApplicationContext
                    |
                    v
          @BeforeTransaction          [outside test transaction]
                    |
                    v
         BEGIN test transaction
                    |
                    v
              @BeforeEach              [inside test transaction]
                    |
                    v
                @Test                  [inside test transaction]
          repository.saveAndFlush(...)
          query in same transaction sees row
                    |
                    v
              @AfterEach               [inside test transaction]
                    |
                    v
        TestContext decides:
          default          -> ROLLBACK
          @Rollback(false) -> COMMIT
          @Commit          -> COMMIT
                    |
                    v
           @AfterTransaction           [outside test transaction]
~~~

**`@BeforeTransaction` and `@AfterTransaction`** are invoked only when the test method is actually configured to run inside a test-managed transaction. In contrast, **`@BeforeAll`/`@AfterAll`** are not inside individual test transactions. **`@BeforeEach`/`@AfterEach`** normally run **inside the test transaction already opened by the listener**; therefore, if `@AfterEach` deletes rows, that change may also be rolled back and **fail to clean up data the test committed in a separate transaction**.

### A Test Transaction Does Not Mean Every Thread's Transaction

The test-managed transaction is bound to the **test execution thread** via the transaction context/`ThreadLocal`. A direct call to a Spring service with **`@Transactional(propagation=REQUIRED)`** usually joins that transaction. However, a real HTTP request running on a servlet server thread, an `@Async` task, or a **`REQUIRES_NEW`** service can use a different transaction and commit independently. **Rollback of the JUnit test does not automatically pull those transactions in.**

This is a boundary you must grasp before designing cleanup and evaluating data that persists after a test.

## 2. Three Core Annotations: @Transactional, @Rollback, @Commit

| Annotation / situation | Is a test-managed transaction opened? | Default ending | Meaning |
| --- | --- | --- | --- |
| No `@Transactional` | **No**, unless another mechanism opens one in code | No automatic test rollback | DML may commit per service/connection behavior |
| `@Transactional` on test method | **Yes**, if a suitable transaction manager exists | **ROLLBACK** | Test DB inside a transaction then auto-isolate |
| `@Transactional` on test class | **Yes** for each test method in that class | **ROLLBACK** | Every test gets an independent method-level transaction |
| `@Transactional` + `@Rollback` | Yes | **ROLLBACK** | Explicitly states rollback behavior; equivalent to default |
| `@Transactional` + `@Rollback(false)` | Yes | **COMMIT** | Keeps data after test; requires active cleanup |
| `@Transactional` + `@Commit` | Yes | **COMMIT** | `@Commit` is the dedicated form of `@Rollback(false)` |
| `@Commit` **without** `@Transactional` | Does not generate a test transaction | No test transaction to commit | Do not expect `@Commit` alone to open a transaction |
| `@Transactional(propagation=NOT_SUPPORTED)` | Listener **does not** open a test transaction | No listener rollback | Suitable when intentionally testing a non-transactional path |

You can use **`@Rollback`** / **`@Commit`** at the class or method level. A **method-level** annotation can override the class-level policy:

~~~java
@SpringBootTest
@Transactional
@Commit
class Example {
    @Test
    @Rollback
    void thisMethodRollsBack() {
        // Method-level @Rollback wins over class-level @Commit.
    }
}
~~~

This is an **excerpt**, without business code yet. **Do not place both `@Commit` and `@Rollback` on the same method** because they express contradictory intents; pick one clear mechanism. An exception inside a service can mark the transaction **rollback-only**, so "having `@Commit`" does not guarantee the database will actually commit if the transaction is already rollback-only or commit hits a constraint error.

**`@Rollback(false)`** and **`@Commit`** are two ways to choose the ending behavior **of the test-managed transaction**; they do not change every transaction in the system. If a service creates **`REQUIRES_NEW`**, that inner transaction has its own lifecycle. If using an external database with `@Commit`, data persists after the JUnit method until cleaned up or reset per database policy.

## 3. @SpringBootTest and @DataJpaTest Do Not Share the Same Transaction Default

**`@DataJpaTest`** is a JPA slice test: by default it configures an embedded `DataSource` when a suitable driver is present, JPA repositories/entities, and **each test runs in a transaction rolled back after the method**. It is suited for testing mappings, repository queries, cascades, constraints, and JPA flush.

**`@SpringBootTest`** loads the full `ApplicationContext`, yet **this annotation alone does not make every test method transactional**. To get test-managed rollback, add **`@Transactional`** on the class or method. If a test uses `@SpringBootTest` without `@Transactional` and calls a transactional business service, the service can commit at the end of the call, and the data will remain after the test.

Intent examples:

~~~java
@DataJpaTest
class RepositorySliceTest {
    @Test
    void insertIsRolledBackByDefault() {
        // @DataJpaTest is transactional by default.
    }
}
~~~

~~~java
@SpringBootTest
@Transactional
class FullContextTransactionalTest {
    @Test
    void insertIsRolledBackByDefault() {
        // @Transactional opens a test-managed transaction.
    }
}
~~~

Both examples are **excerpts**, without repositories yet. The runnable project starting in section 7 uses **`@SpringBootTest` + `@Transactional`** to demonstrate full service propagation and test transactions. You can use `@DataJpaTest` for simpler repository checks.

**`@DirtiesContext` is no substitute for DB cleanup.** It marks the `ApplicationContext` so Spring will not reuse it from the context cache; closing and reopening the context **does not guarantee deleting committed data** in PostgreSQL/MySQL or an H2 database that outlives the context. Data must be cleaned up via dedicated transactions/scripts/truncate/delete or proper database isolation.

## 4. @BeforeTransaction and @AfterTransaction vs. @BeforeEach/@AfterEach

This is the crucial point when you want to **prove real rollback/commit**.

| Hook | When does it run for a `@Transactional` test? | Has test transaction? | Best used for? |
| --- | --- | --- | --- |
| **`@BeforeTransaction`** | Before the listener starts the test transaction | **No** | Inspect/clean baseline outside the transaction |
| **`@BeforeEach`** | After the test transaction has started | **Yes** | Prepare fixtures that should roll back with the test |
| **`@Test`** | Inside the test transaction | **Yes** | Execute and assert business behavior |
| **`@AfterEach`** | Before the listener closes the test transaction | **Yes** | Assert in-transaction state; temporary cleanup in same tx |
| **`@AfterTransaction`** | After the listener rolls back/commits the transaction | **No** | Verify row persists after commit or disappears after rollback; clean up committed data |

**Do not use `@AfterEach` and claim "rollback verified."** At the time `@AfterEach` runs, the test transaction is still open, so queries will see the row the test just inserted. Only **`@AfterTransaction`** observes the outcome after the transaction finishes. If there is no test transaction, `BeforeTransaction`/`AfterTransaction` will not run merely because you placed the annotations on methods.

The `BeforeTransaction`/`AfterTransaction` hooks come from package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

Note: in Spring Framework 6.1+ with JUnit Jupiter/`SpringExtension`, these hooks can also accept parameters via JUnit `ParameterResolver`s, such as `TestInfo` or `@Autowired` beans. The project here uses autowired fields so the API remains easy to follow.

### If a Test Commits, Where Should Cleanup Live?

For a **`@Commit`** test, committed data will **not** be deleted just because you call `DELETE` in **`@AfterEach`**, because the `DELETE` can belong to **the very transaction being committed**; and if you deleted before commit, you would not even have proof that the data actually existed after commit.

A more accurate pattern:

1. **`@BeforeTransaction`:** delete leftover test-key rows from a previous run, outside the test tx.
2. **`@Test @Commit`:** insert or update; **flush** and assert managed state.
3. **`@AfterTransaction`:** read the row from a fresh transaction/connection to confirm it committed.
4. **`finally` in `@AfterTransaction`:** `DELETE` the row using `JdbcTemplate` outside the test tx, ensuring other tests are not polluted even if an assertion fails.

Cleaning up by **test-specific key** is safer than `"DELETE FROM every_table"` on a shared database. On production databases, destructive data tests must **never** point to a real datasource.

## 5. Flush, Clear, and Commit: Three Distinct Behaviors

In JPA/Hibernate:

- **`persist`/`save`** places an entity into the persistence context, possibly without pushing all SQL yet.
- **`flush`** synchronizes pending changes as SQL inside the transaction and can expose constraint violations.
- **`clear`** detaches managed entities so the next query does not simply return the level-1 cached object.
- **`commit`** ends the transaction successfully; changes become durable/visible per isolation rules.
- **`rollback`** cancels the transaction's changes on the database, even if already flushed.

Example:

~~~java
repository.saveAndFlush(new EventRecord("EVT-A", "created"));
assertEquals(1L, repository.countByEventKey("EVT-A"));
~~~

When running inside a `@Transactional` test, `count=1` only proves **the row exists within this transaction**. After the default rollback, the result from a new connection will be **0**. That is not a repository bug.

Spring Framework recommends **flushing in ORM tests** when you need to catch constraint/lifecycle errors that might only arise during flush. If a test simply saves and ends with rollback without flushing, some mapping/constraint errors are never caught. Both `@DataJpaTest` and `@SpringBootTest @Transactional` can hit this "false positive" issue.

### Does Reading a Row in the Same Transaction Prove Commit?

**No.** A `SELECT` right after an `INSERT` in the same transaction normally sees uncommitted data (read-your-writes). Therefore, a test wishing to prove **actual commit** must observe data **after the transaction ends**, such as in `@AfterTransaction` or via `TestTransaction.end()` followed by a query outside the old transaction.

## 6. Rollback/Commit Outcomes and Failing Test Cases

When a test carries `@Transactional`, by default Spring TestContext rolls back after the method even if JUnit assertions succeed. Conversely, **`@Commit`** only requests commit at the end; if a test fails an assertion, the transaction can still be committed depending on the `rollback-only` flag, errors, and listener lifecycle. Thus using `@Commit` requires attention to **potential data leaks even when a test fails**.

A safe strategy is:

- Only use `@Commit` when a test genuinely needs to verify post-commit behavior, `AFTER_COMMIT` event listeners, or visibility.
- Use a **dedicated test key/namespace**, never fixed IDs of real data.
- Clean leftovers in **`@BeforeTransaction`** so re-runs do not hit unique constraints.
- Clean up after commit in **`@AfterTransaction`**, using **`try`/`finally`** so cleanup runs even if an assertion fails.
- If the process is killed before cleanup, a subsequent run can still clean up via the before hook; in CI, use an isolated database/container.
- Never depend on test A committing fixtures for test B; test order is not a valid way to manage data state.

**`@Sql AFTER_TEST_METHOD`** can run according to its configured transaction mode; do not automatically assume every "after" script runs **after the test transaction has committed**. If you need cleanup outside the test tx, **`@SqlConfig(transactionMode=ISOLATED)`** or `@AfterTransaction` can be used depending on the goal, provided you understand the execution order and transaction mode of `SqlScriptsTestExecutionListener`. In the runnable example, cleanup uses `@AfterTransaction` so the lifecycle stays transparent.

## 7. Java 17 + Spring Boot 3.4.5 + JPA + H2 Project

Goal: verify **test-managed transactions** using a single table **`audit_events`**. Each test uses a **unique `event_key`** to avoid order dependence, and a `JdbcTemplate` reads the real table outside the JPA persistence context.

Sample behaviors:

- Default rollback test: inside `@Test` the row exists, after the method the row is gone.
- `@Commit` test: inside `@Test` the row exists; after commit the row remains; after `@AfterTransaction` cleanup the row disappears.
- `@Rollback(false)` test: commit semantics equivalent to `@Commit`, then cleanup.
- `@Rollback` method overriding class `@Commit`: the specific method still rolls back.
- `TestTransaction`: actively commits one transaction mid-method, starts a second transaction, and rolls back temporary changes.
- `REQUIRES_NEW` service: inner commit is not rolled back by the outer test transaction and must be cleaned up explicitly.

**File structure:**

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/txqa/TxQaApplication.java
src/main/java/com/example/txqa/EventRecord.java
src/main/java/com/example/txqa/EventRecordRepository.java
src/main/java/com/example/txqa/IndependentEventWriter.java
src/test/java/com/example/txqa/DefaultRollbackTest.java
src/test/java/com/example/txqa/CommitCleanupTest.java
src/test/java/com/example/txqa/RollbackFalseCleanupTest.java
src/test/java/com/example/txqa/MethodOverrideRollbackTest.java
src/test/java/com/example/txqa/ManualTransactionTest.java
src/test/java/com/example/txqa/RequiresNewEscapesRollbackTest.java
~~~

### 7.1. Gradle Build and H2 Test Database

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-transaction-control'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

**H2 + `create-drop`** is only for learning and isolated testing. Never use **`ddl-auto=create-drop`** on a production DB. Tests can share a Spring `ApplicationContext` via caching, so each test has a **unique `event_key`** and cleans up its own commits. When running against Testcontainers or a real database, always use an independent test database/schema.

The project has no web starter, so it does not start an HTTP server. This is **intentional**, because the main exercise tests the test-managed transaction listener on the thread calling the JUnit test, not networking. Section 12 clarifies how HTTP integration tests differ.

### 7.2. Application Class

**src/main/java/com/example/txqa/TxQaApplication.java**

~~~java
package com.example.txqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxQaApplication.class, args);
    }
}
~~~

### 7.3. JPA Entity with a Test-Specific Business Key

**src/main/java/com/example/txqa/EventRecord.java**

~~~java
package com.example.txqa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_events")
public class EventRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_key", nullable = false, unique = true)
    private String eventKey;

    @Column(nullable = false)
    private String payload;

    protected EventRecord() {
        // JPA constructor.
    }

    public EventRecord(String eventKey, String payload) {
        this.eventKey = eventKey;
        this.payload = payload;
    }

    public Long getId() {
        return id;
    }

    public String getEventKey() {
        return eventKey;
    }

    public String getPayload() {
        return payload;
    }
}
~~~

**`event_key`** is a unique key; each test uses a different string. The ID is generated by H2 to illustrate entity generation, yet assertions do not depend on a specific auto-increment ID, because sequences/identity values may not roll back when a transaction rolls back.

### 7.4. Repository and Service Using an Independent Transaction

**src/main/java/com/example/txqa/EventRecordRepository.java**

~~~java
package com.example.txqa;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EventRecordRepository
        extends JpaRepository<EventRecord, Long> {

    long countByEventKey(String eventKey);
}
~~~

**src/main/java/com/example/txqa/IndependentEventWriter.java**

~~~java
package com.example.txqa;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentEventWriter {
    private final EventRecordRepository repository;

    public IndependentEventWriter(EventRecordRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String eventKey) {
        repository.saveAndFlush(
                new EventRecord(eventKey, "independent commit"));
    }
}
~~~

**`REQUIRES_NEW`** opens a new Spring-managed transaction for a public service method called **through a Spring proxy**. If the outer test already has a test-managed transaction, Spring suspends it, executes the service transaction, commits the new transaction, and then resumes the outer transaction. Rolling back the outer transaction **does not undo the inner commit**.

Do not try to reproduce this with a `private` method or self-invocation **`this.record(...)`** inside the same bean, because the Spring AOP proxy can be bypassed. In the tests, the service is **`@Autowired`** so calls go through the proxy properly.

## 8. Default Rollback Test: Evidence Before, During, and After

**src/test/java/com/example/txqa/DefaultRollbackTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class DefaultRollbackTest {
    private static final String KEY = "default-rollback";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    @BeforeTransaction
    void beforeTransaction() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
        assertEquals(0L, count());
    }

    @BeforeEach
    void beforeEachRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void insertedRowExistsBeforeRollback() {
        repository.saveAndFlush(new EventRecord(KEY, "temporary"));

        assertEquals(1L, repository.countByEventKey(KEY));
        assertEquals(1L, count());
    }

    @AfterEach
    void afterEachStillRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1L, count());
    }

    @AfterTransaction
    void afterTransactionVerifiesRollback() {
        assertEquals(0L, count());
    }
}
~~~

**Reading the evidence:**

1. **`@BeforeTransaction`** runs outside the test transaction, deletes any old row matching `KEY` (if present), and asserts a baseline of 0.
2. **`@BeforeEach`** proves `TestTransaction.isActive()==true`.
3. **`@Test`** calls `saveAndFlush`, and then both repository and `JdbcTemplate` see the row inside the same transaction.
4. **`@AfterEach`** is still inside the transaction, so it still sees the row even though it is about to be rolled back.
5. Spring TestContext **rolls back by default** because the test class has `@Transactional` and no `@Commit`.
6. **`@AfterTransaction`** queries outside the transaction and confirms **the row is gone**.

You do not need to "delete the row again" in `@AfterEach`; rollback cleans up the test transaction's own changes. Still, cleaning the baseline before each run ensures the test does not depend on leftover data from an out-of-transaction operation in a prior run.

## 9. @Commit: Verifying Data After Commit Then Cleaning Up

**src/test/java/com/example/txqa/CommitCleanupTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class CommitCleanupTest {
    private static final String KEY = "commit-and-cleanup";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void removeResidueFromEarlierRun() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    @Commit
    void persistsRowBeyondEndOfTestTransaction() {
        repository.saveAndFlush(new EventRecord(KEY, "committed"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyCommittedDataThenCleanUp() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

Why not simply put cleanup in **`@AfterEach`**? Because `@AfterEach` runs inside the still-open transaction. Here we need to confirm that data **actually survived after commit**, so `@AfterTransaction` is where we verify it. `JdbcTemplate` outside the transaction uses its own connection/transaction lifecycle to execute the `DELETE`. **`finally`** ensures cleanup executes even if the post-commit count assertion fails; if the JDBC cleanup itself fails, the test reports the real error.

**Important:** `@Commit` should not be used if the goal is just simple repository CRUD testing. Default rollback is usually faster and better isolated. Only commit when you need to check **post-commit** behavior; the more `@Commit` tests you have, the stronger your lifecycle cleanup must be.

## 10. @Rollback(false): Equivalent to @Commit at the End of the Test

**src/test/java/com/example/txqa/RollbackFalseCleanupTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class RollbackFalseCleanupTest {
    private static final String KEY = "rollback-false";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void reset() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    @Rollback(false)
    void commitsRatherThanRollsBack() {
        repository.saveAndFlush(
                new EventRecord(KEY, "kept until cleanup"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyThenRemoveCommittedRow() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

Here **`@Rollback(false)`** on the method achieves the exact same effect as **`@Commit`**. Both alter **the ending decision of the test-managed transaction**; neither attaches a transaction if `@Transactional` is absent.

**Do not place both annotations simultaneously on the same method**. Choose one consistent style in the codebase, e.g. `@Commit` when you want to write data intentionally and `@Rollback` when emphasizing that a method overrides a class-level policy.

## 11. Method-Level @Rollback Overrides Class-Level @Commit

A class can place **`@Commit`** at the class level so tests needing commit stay readable, while one method aims to roll back. Put `@Rollback` explicitly on that method.

**src/test/java/com/example/txqa/MethodOverrideRollbackTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
@Commit
class MethodOverrideRollbackTest {
    private static final String KEY = "method-overrides-commit";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    @BeforeTransaction
    void baseline() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
        assertEquals(0L, count());
    }

    @Test
    @Rollback
    void methodChoosesRollbackDespiteClassCommit() {
        repository.saveAndFlush(
                new EventRecord(KEY, "should disappear"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void methodWasRolledBack() {
        assertEquals(0L, count());
    }
}
~~~

When the framework decides how to end the test transaction, **method-level `@Rollback`** takes precedence over **class-level `@Commit`**; thus the row disappears. This is a useful check when a project has a base test class or meta-annotation declaring a transaction policy that a specific test needs to override.

**Design recommendation:** do not scatter `@Commit` on base classes where it causes many tests to commit implicitly. Place the commit policy as close as possible to the test that actually needs to commit so it is easy to audit and clean up.

## 12. TestTransaction: Actively Committing/Rolling Back Mid-Method

Sometimes you want to check data **after commit** right inside the same JUnit method rather than waiting for `@AfterTransaction`, or you need a fresh transaction after the first transaction ends. Spring TestContext provides **`TestTransaction`**:

| API | Meaning |
| --- | --- |
| **`TestTransaction.isActive()`** | Is there an active test-managed transaction? |
| **`TestTransaction.flagForCommit()`** | Marks the current transaction to commit when ended |
| **`TestTransaction.flagForRollback()`** | Marks the current transaction to roll back when ended |
| **`TestTransaction.isFlaggedForRollback()`** | Ending flag of the current transaction |
| **`TestTransaction.end()`** | Ends the current test transaction according to the commit/rollback flag |
| **`TestTransaction.start()`** | Starts a new test transaction when a previous one has ended |

**src/test/java/com/example/txqa/ManualTransactionTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class ManualTransactionTest {
    private static final String PERMANENT_KEY = "manual-committed";
    private static final String TEMP_KEY = "manual-rolled-back";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count(String key) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, key);
    }

    private void cleanup() {
        jdbc.update(
                "DELETE FROM audit_events WHERE event_key IN (?, ?)",
                PERMANENT_KEY, TEMP_KEY);
    }

    @BeforeTransaction
    void baseline() {
        cleanup();
        assertEquals(0L, count(PERMANENT_KEY));
        assertEquals(0L, count(TEMP_KEY));
    }

    @Test
    void commitFirstTransactionThenRollbackSecond() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        repository.saveAndFlush(
                new EventRecord(PERMANENT_KEY, "committed"));

        TestTransaction.flagForCommit();
        assertFalse(TestTransaction.isFlaggedForRollback());
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(1L, count(PERMANENT_KEY));

        TestTransaction.start();
        TestTransaction.flagForRollback();
        assertTrue(TestTransaction.isActive());

        repository.saveAndFlush(
                new EventRecord(TEMP_KEY, "temporary"));
        assertEquals(1L, count(TEMP_KEY));

        // TestContext rolls back the second transaction after the method.
    }

    @AfterTransaction
    void onlyFirstTransactionWasCommitted() {
        try {
            assertEquals(1L, count(PERMANENT_KEY));
            assertEquals(0L, count(TEMP_KEY));
        } finally {
            cleanup();
        }
        assertEquals(0L, count(PERMANENT_KEY));
        assertEquals(0L, count(TEMP_KEY));
    }
}
~~~

**Timeline:**

~~~text
TestTransaction active (default rollback flag)
  -> insert PERMANENT_KEY
  -> flagForCommit(); end()  => first COMMIT
  -> isActive() == false; count(PERMANENT_KEY)==1
  -> start() new transaction
  -> flagForRollback()
  -> insert TEMP_KEY
  -> @Test ends
  -> listener ROLLBACK second transaction
  -> @AfterTransaction:
       count(PERMANENT_KEY)==1
       count(TEMP_KEY)==0
       cleanup committed row PERMANENT_KEY
~~~

**`TestTransaction` only manages Spring TestContext's active test transaction.** It is not a general API to control service transactions on other threads or transactions already committed. **`TestTransaction.end()` does not need to be called in every test**; use it only when the test needs to change transaction boundaries mid-method. If you want the new transaction to have default rollback, calling `flagForRollback()` explicitly as shown here keeps intent clear.

**Warning:** if you call **`TestTransaction.end()`** without calling `start()` again, subsequent operations may execute outside a transaction, leading to unintended commits. Always track `isActive` and clean up any committed data.

## 13. REQUIRES_NEW: A Commit Not Rolled Back with the Test

**src/test/java/com/example/txqa/RequiresNewEscapesRollbackTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class RequiresNewEscapesRollbackTest {
    private static final String KEY = "requires-new-commit";

    @Autowired
    private IndependentEventWriter writer;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void baseline() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    void independentServiceCommitSurvivesOuterRollback() {
        assertTrue(TestTransaction.isActive());

        // Proxy opens REQUIRES_NEW, inner transaction commits.
        writer.record(KEY);

        // Outer test transaction is still active; when the test ends,
        // outer rollback does not undo the inner commit.
    }

    @AfterTransaction
    void committedInnerRowMustBeRemovedExplicitly() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

**This is a very important counter-example.** The test has `@Transactional` and rolls back by default at the end of the method, yet the service called through the proxy has **`Propagation.REQUIRES_NEW`**. The service's transaction commits independently, so the row remains. If you believed "`@Transactional` on a test cleans up all data created by the test," this test proves that assumption **false**.

Key distinctions:

- **`REQUIRED`:** the service usually joins the existing transaction, so its data can roll back along with the test transaction.
- **`REQUIRES_NEW`:** the service suspends the current transaction and opens a new one; when the method returns normally, it commits independently.
- **`NOT_SUPPORTED`:** the method runs outside the current transaction, so JDBC/JPA behavior and auto-commit must be checked specifically.
- **`@Async`** or a new thread: the test's transaction context does not automatically propagate to other threads; how data commits depends on the service transaction.
- **HTTP with `RANDOM_PORT`:** requests are handled on a servlet server thread with a different transaction from the JUnit test thread.

Do not use `REQUIRES_NEW` in business code just to "escape test rollback"; choose propagation according to business requirements, and design test cleanup accordingly.

## 14. Why Can't @AfterEach Clean Up Everything?

Suppose a `@Test` has an **outer transaction** yet calls a `REQUIRES_NEW` service that committed a row. In **`@AfterEach`**, if you write:

~~~java
@AfterEach
void cleanup() {
    jdbc.update(
            "DELETE FROM audit_events WHERE event_key = ?",
            "requires-new-commit");
}
~~~

This is a **counter-example excerpt**. `@AfterEach` may be running **inside the outer test transaction**. The `DELETE` runs inside the outer transaction and will be **rolled back with the outer transaction**, while the `REQUIRES_NEW` `INSERT` already committed; the row can **remain**. That explains why cleaning up in `@AfterTransaction` outside the transaction, or using an intentionally separate cleanup transaction, is more reliable for this kind of data.

**It is not that `@AfterEach` is always useless**: when data is created inside the same test transaction, both `INSERT` and `DELETE` roll back; though that cleanup is usually unnecessary because default rollback already handles it. For data committed outside the test transaction, cleanup must sit outside the rolled-back boundary.

An integration test with a shared database may need **`@SqlConfig(transactionMode=ISOLATED)`** for teardown, or invoke repository cleanup through a separate transaction. Check the listener ordering and SQL script transaction mode for your Spring version; do not assume `AFTER_TEST_METHOD` always means "after commit."

## 15. When Does @Sql Help Control Fixtures and Cleanup?

Spring TestContext supports **`@Sql`** to run scripts before/after a test:

~~~java
@Sql(
    scripts = "/sql/seed-entries.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
    scripts = "/sql/cleanup-entries.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class ExampleSqlScriptsTest {
}
~~~

This is an **excerpt**, not part of the runnable project because it lacks the two scripts/imports and test configuration. **`ISOLATED`** means the script runs in its own transaction and commits immediately, suitable when cleanup must persist outside test rollback. However, which script runs before/after the test transaction depends on listener ordering and configuration; if you need to assert post-commit results, **`@AfterTransaction`** is the clearer hook.

**Fixture recommendations:**

- Use **`@Sql` or repository setup** when seeding test-specific data.
- When `@Sql` joins the test transaction, the fixture also rolls back; good for isolating test methods.
- When `@Sql` uses an `ISOLATED` transaction, data can be **committed before the test runs** and is not auto-rolled back by `@Transactional` tests; teardown is required.
- When using `@Commit`, you usually need **post-commit cleanup** or a test DB that is recreated/reset between runs.
- With multiple tables having foreign keys, clean up in child → parent order or use truncate/schema isolation appropriately.
- Never run destructive scripts against a production datasource.

If a test uses SQL init from **`schema.sql`/`data.sql`** at context startup, those initialized rows are not inside any test transaction. Test rollback **does not delete baseline fixtures**; it only cancels changes made within the test transaction.

## 16. Test Transactions and Spring Data Repositories: Limits to Know

### 16.1. @Transactional on a Test Does Not Have Full Service @Transactional Semantics

According to the Spring TestContext docs, `@Transactional` on a **test method/class** has limited attribute support in the listener:

| Attribute on test `@Transactional` | Supported for test-managed transaction |
| --- | --- |
| `value` / `transactionManager` | Yes |
| propagation `NOT_SUPPORTED` and `NEVER` | Used to not run a test transaction |
| propagation `REQUIRED`/`REQUIRES_NEW`/... | Do not expect the listener to apply full business-service semantics |
| `isolation` | Not used by TestContext listener to customize the test transaction |
| `timeout` | Not used by listener as a business tx timeout |
| `readOnly` | Not used by listener as the test transaction policy |
| `rollbackFor` / `noRollbackFor` | Not used by listener to choose test commit/rollback |

To control commit/rollback of a test, use **`@Rollback`**, **`@Commit`**, or **`TestTransaction.flagForCommit/flagForRollback`**. To test isolation/timeout/readOnly or detailed propagation of a **service**, invoke the service through a Spring-managed proxy and verify behavior against an appropriate transaction manager/database.

**Do not put `@Transactional` on `@BeforeEach` to "open a transaction"**: the test listener opens transactions based on the test class/method, not lifecycle methods; placing it on a lifecycle method does not have that effect.

### 16.2. If There Are Multiple PlatformTransactionManagers

An `ApplicationContext` can have multiple transaction managers (e.g., JPA + JDBC or multiple datasources). TestContext needs to choose the right manager; you can specify:

~~~java
@Transactional(transactionManager = "orderTransactionManager")
class ExampleTwoManagers {
}
~~~

This is an excerpt; the `orderTransactionManager` bean does not exist in the runnable demo. Choosing the wrong manager can cause the test to roll back one datasource while the service writes and commits to another. You must test all datasources that have side effects, not just one DB.

### 16.3. @Commit and Event Listeners

A method annotated with **`@TransactionalEventListener(phase = AFTER_COMMIT)`** runs only when the transaction actually commits, not when the test ends with default rollback. Therefore:

- A test using default rollback does not prove the `AFTER_COMMIT` listener executed.
- You can use **`@Commit`** or **`TestTransaction.flagForCommit` + `end`** to trigger `AFTER_COMMIT` in a test.
- Then assert side effects **outside the transaction**, e.g., in `@AfterTransaction`.
- With async listeners, Kafka, HTTP, or queue side effects, database commit does not guarantee synchronous event delivery; synchronization/wait policies and external resource cleanup are needed.
- A listener using `REQUIRES_NEW` may persist additional rows; clean up those side effects as well.

### 16.4. Transaction Commit Can Fail

Unique constraint/deferred foreign-key errors, optimistic conflicts, deadlocks, or `rollback-only` can arise at flush or commit time. A `@Commit` test does not guarantee a committed row will exist. Code must assert **expected success** or **expected failure** in the right phase. When an error only surfaces on commit, using `TestTransaction.flagForCommit()/end()` moves the boundary inside the `@Test` body so you can assert the exception directly instead of letting it fail after the method during listener cleanup.

## 17. HTTP Integration Tests: Why Does Data Persist Even Though the Test Has @Transactional?

A test like:

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpIntegrationTest {
    // HTTP client sends POST /events to the server.
}
~~~

This is an excerpt. When the HTTP client sends a request to the real server:

~~~text
JUnit test thread:
    BEGIN test transaction
    HTTP POST /events --------------+
    wait response                    |
    ROLLBACK test transaction        |
                                     v
Servlet server thread:
    BEGIN service transaction
    INSERT row
    COMMIT service transaction
    HTTP 201 response
~~~

**Rollback on the test thread does not roll back the server transaction.** If the HTTP request creates data, `@Transactional` on the JUnit test can even cause confusion because the test reads data using a different connection/transaction. Never rely on it as your sole cleanup. Use a separate database per test, a test-key with `DELETE` after the request, `@Sql` with isolated cleanup, Testcontainers per suite, or an authorized cleanup API.

**`MockMvc` does not open a real socket** and usually runs on the test thread, though behavior with async dispatch/security/transactions can be subtle depending on setup. Do not extrapolate test-managed transaction behavior from `MockMvc` to a real HTTP server or vice versa. Choose assertions matching the layer under test.

## 18. Cleaning Data and Test Isolation: Choosing the Right Approach

| Data management approach | When appropriate | Pros | Risks/warnings |
| --- | --- | --- | --- |
| **Default rollback** | JPA/JDBC repository tests on same test thread | Fast, automatically isolates DML inside test tx | Does not roll back `REQUIRES_NEW`/async/HTTP side effects |
| **`@BeforeTransaction` + `@AfterTransaction`** | Need assertions after rollback/commit and cleanup | Clear boundary, tests DB after completion | Longer hooks, cleanup must be idempotent |
| **`TestTransaction.end/start`** | Need to verify commit mid-`@Test` | Explicit lifecycle control | Easy to forget restarting, creating unintended commits |
| **`@Sql`** | Clear SQL fixtures/teardown | Reusable scripts, controlled datasets | Must understand `TransactionMode` and listener ordering |
| **Repository/`JdbcTemplate` cleanup outside transaction** | Tests with committed rows | Cleans by business/test key | Must avoid deleting other tests' data |
| **Truncate/reset schema** | Dedicated database per test/suite | Broad cleanup, little stale residue | Unsafe on shared DB, FK constraints |
| **Testcontainers** | Want realism close to production DB and isolation | More realistic dialect/transaction behavior than H2 | Startup overhead and lifecycle management |
| **Unique generated test keys** | Parallel tests or shared context | Reduces collisions and order dependence | Does not replace cleanup if data commits |
| **`@DirtiesContext`** | Need fresh Spring bean/context state | Isolates context cache | Does not guarantee cleaning committed database |
| **Separate transaction for seeding** | Tests reading committed baseline data | Proves visibility from another connection | Committed baseline must be cleaned up after suite |

### Test Keys and Idempotent Cleanup

Use a dedicated `KEY` per test, as in the project, or a prefixed UUID to target only that test's data. Cleanup like:

~~~sql
DELETE FROM audit_events WHERE event_key = ?;
~~~

is generally safer than:

~~~sql
DELETE FROM audit_events;
~~~

on a DB with shared fixtures. Deleting by key when it may already be absent from a prior run makes cleanup **idempotent**: a zero-row `DELETE` is acceptable. However, if test code creates more than one kind of side effect (audit rows, caches, messages, files), clean up **all related resources**, not just the primary table.

## 19. Checking Lifecycle Order Without Depending on Test Order

A visual way to verify order is logging inside hooks:

~~~java
@BeforeTransaction
void beforeTx() { System.out.println("BEFORE_TX"); }

@BeforeEach
void beforeEach() { System.out.println("BEFORE_EACH"); }

@Test
void test() { System.out.println("TEST"); }

@AfterEach
void afterEach() { System.out.println("AFTER_EACH"); }

@AfterTransaction
void afterTx() { System.out.println("AFTER_TX"); }
~~~

This is an illustrative excerpt **inside a `@Transactional` class**; these methods are not in the runnable file tree and require JUnit/Spring imports. Expected lines for a test method lifecycle:

~~~text
BEFORE_TX
BEFORE_EACH
TEST
AFTER_EACH
AFTER_TX
~~~

This is **the logical order executed by the listener/JUnit**, not actual Gradle run logs. Other Spring `TestExecutionListener`s or JUnit extensions may print logs in between; the hook sequence above remains the key milestone order.

**Do not use JUnit `@TestMethodOrder` to ensure test B only passes after test A commits.** Each test must set up, assert, and clean up its own data. If the application truly has a multi-step workflow, write **a single test method** driving that workflow or use independent fixtures with clear contracts rather than depending on state left behind by another test.

## 20. Common Issues and Fixes

| Symptom | Possible cause | Verification and fix |
| --- | --- | --- |
| `@SpringBootTest` test writes to DB and data remains after test | No test `@Transactional`, or side effect in another transaction | Check annotations, thread, and service propagation |
| `@DataJpaTest` sees row in test but next test does not | Default rollback | Expected behavior; use `@Commit` with cleanup if verifying commit |
| `@Commit` yet `@AfterEach` query still does not prove commit | `@AfterEach` runs before transaction ends | Assert inside `@AfterTransaction` |
| `@Commit` ran yet DB has no row | Transaction rollback-only, commit failed, or cleanup deleted before commit | Check logs and lifecycle, separate side effects |
| Used `@Rollback(false)` without `@Transactional` | No test transaction | Add `@Transactional` or pick a non-transactional test with other cleanup |
| Test fails with unique constraint on re-run | Committed row from previous run was not cleaned up | Idempotent pre-clean + post-clean, unique fixture keys |
| `@AfterEach` deletes `REQUIRES_NEW` row yet row remains | `DELETE` joined outer test tx and rolled back | Clean up outside tx in `@AfterTransaction` |
| JUnit test rolls back yet async job still writes DB | New thread does not join test transaction | Await job completion, clean up separately |
| HTTP `RANDOM_PORT` test rollback does not clean API rows | Server thread has its own tx | Clean up outside transaction or use isolated database |
| `@DirtiesContext` yet DB data still exists | Context cache is not database cleanup | Use `DELETE`/truncate/schema isolation |
| Entity save does not throw constraint error | Hibernate has not flushed | `saveAndFlush`/`entityManager.flush` in test |
| `@Sql` fixture does not roll back as expected | Script uses `ISOLATED`/committed transaction | Check `SqlConfig` `transactionMode` and listener ordering |
| SQL cleanup deletes other tests' data too | Shared DB and `DELETE` without `WHERE` | Dedicated keys/namespace, isolated test DB |
| Test passes alone, fails in suite | Context cache, committed rows, global state | Idempotent cleanup, no order dependence |
| `@Transactional(readOnly=true)` on test expected to prevent writes | Test listener does not apply `readOnly` like service | Check supported attrs, test at the right layer |
| `REQUIRES_NEW` test commits unexpectedly | Independent service transaction | Understand propagation, assert after `@AfterTransaction` |
| Test using `assertTimeoutPreemptively` leaks data | Code runs on another thread, losing test tx `ThreadLocal` | Avoid preemptive timeouts with transactional tests |
| Multiple transaction managers, wrong DB rolled back | Listener picks a different manager than service | Specify `transactionManager` and test multi-DB state |
| H2 PASSES yet production transaction isolation differs | DB engine/dialect/isolation differ | Use Testcontainers with production-like engine for critical cases |

## 21. Self-Check Exercises

**1.** A `@DataJpaTest` calls `saveAndFlush` and `countById` returns 1. After the method, does the row remain? **No by default**; `@DataJpaTest` rolls back. You need `@AfterTransaction` or another transaction to observe post-rollback state.

**2.** Does plain `@SpringBootTest` auto-roll back every test method? **No.** Add `@Transactional` if you want a test-managed transaction.

**3.** What happens if you put `@Commit` on a method without `@Transactional`? **It does not create a test transaction**; there is no test-managed transaction for `@Commit` to control.

**4.** Do `@Commit` and `@Rollback(false)` differ in intent regarding committing the test transaction? **No**: both choose commit; `@Commit` expresses it more concisely.

**5.** Class uses `@Commit`, method uses `@Rollback`. Which policy applies? **Method-level `@Rollback`**, so the test transaction rolls back.

**6.** Is `@AfterEach` called after test rollback? **No.** For transactional tests, it usually runs before the listener rolls back/commits.

**7.** Can `@AfterTransaction` inspect a committed row? **Yes**, because the hook runs after the transaction finishes and can query with a connection outside the test transaction.

**8.** A `@Transactional(REQUIRES_NEW)` service inserts and commits. The outer `@Transactional` test rolls back at the end of the method. Does the inner row disappear? **No**, `REQUIRES_NEW` commits independently.

**9.** In a `@Transactional` test, you call `TestTransaction.flagForCommit()` then `end()`. Can the data be read outside the transaction yet? **Yes**, provided commit succeeded and visibility rules permit; that is the purpose of the API.

**10.** After `TestTransaction.end()`, if you call `repository.save()` without calling `start()` again, is test rollback still protecting you? **Do not assume so**; you are outside the test-managed transaction.

**11.** Does `@DirtiesContext` clean committed rows in an external DB? **No guarantee**; it primarily manages the Spring `ApplicationContext` cache.

**12.** A `@Transactional` JUnit test sends HTTP POST to an embedded `RANDOM_PORT` server. Will it reliably roll back the request's DB writes? **No**, the server runs a separate transaction.

**13.** What is the risk of using `assertTimeoutPreemptively` with a Spring `@Transactional` test? The body runs on another thread, so DB writes may not join the test transaction and may be committed.

**14.** Why is flushing needed in a JPA test before claiming there is no constraint error? Because the error may only surface when Hibernate sends SQL during flush/commit.

**15.** Does cleaning data in `@BeforeTransaction` replace `@AfterTransaction`? **Not completely.** Pre-cleaning protects re-runs, while post-cleaning keeps the suite clean right after the test.

**16.** A test wants to verify an `AFTER_COMMIT` listener. Does default rollback trigger this listener? **No**; an actual commit and right-timed assertions are required.

### Pre-QA Sign-Off Checklist

- Is the test actually `@Transactional` at the class/method level or via `@DataJpaTest`?
- Is the right `PlatformTransactionManager` present for the datasource under test?
- Is default rollback understood, with `@Commit`/`@Rollback(false)` used only when truly needed?
- Are **`@BeforeEach`/`@AfterEach` inside the tx** distinguished from **`@BeforeTransaction`/`@AfterTransaction` outside the tx**?
- Is flushing used to catch SQL/constraint/lifecycle errors in JPA?
- Is data observed after commit/rollback in the proper phase, not merely counted inside the transaction?
- If `@Commit` is used, are unique test keys, pre-cleaning, and `finally` cleanup outside the transaction in place?
- Are method-level overrides of class-level transaction policies tested with the right annotations?
- When using `TestTransaction.end/start`, is it clear which transaction is active and which flag ends it?
- Do `REQUIRES_NEW` services, `@Async`, and real HTTP servers leave side effects outside test rollback?
- Are `@Sql` fixtures, `SqlConfig.ISOLATED`, and teardown scripts understood with the right transaction mode?
- Is `@DirtiesContext` avoided as a substitute for database cleanup?
- Are thread-switching preemptive timeouts avoided so the test-managed transaction is not lost?
- Are tests free from dependence on JUnit test order or fixed shared IDs?
- Is the test database isolated with zero risk of deleting production data?
- When behavior depends on DB isolation/locking/constraints, are there integration tests against the production DB engine?

**Conclusion:** **`@Rollback`** chooses to cancel a test-managed transaction; **`@Commit`** and **`@Rollback(false)`** allow it to commit; all three are meaningful only within a transaction managed by Spring TestContext. To verify post-test state, use **`@AfterTransaction`** or **`TestTransaction.end()`**, and clean up committed data **outside the transaction that will roll back**. A strong test suite both proves CRUD correctness and prevents other tests from being polluted by `REQUIRES_NEW`, HTTP requests, `@Async` jobs, or committed fixtures.

## Official References

- Spring Framework 6.2 — TestContext Transaction Management, `@Rollback`/`@Commit`, hooks, and `TestTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Integration Testing: https://docs.spring.io/spring-framework/reference/6.2/testing/integration.html
- Spring Boot 3.4 — `@DataJpaTest` API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Framework — `@Sql` and SQL scripts in TestContext: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html
- Spring Framework — `TestTransaction` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
