# @BeforeTransaction and @AfterTransaction in Spring Boot Testing

## Objectives

In Spring TestContext, when a JUnit test runs inside a **test-managed transaction**, Spring can open the transaction before the test and automatically **roll back** when the test finishes. This suits repository testing, yet causes confusion when learners want to verify data **before the transaction starts** or **after commit/rollback has occurred**. JUnit's `@BeforeEach` and `@AfterEach` methods do not solve this properly because they normally run **inside the test-managed transaction itself**.

Two specialized Spring annotations:

- **`@BeforeTransaction`** — executes a callback **before** Spring starts the test-managed transaction.
- **`@AfterTransaction`** — executes a callback **after** Spring has ended the test transaction via commit or rollback.

This lesson belongs to the **Transaction Testing** track of the **Spring Boot – testing** module. The focus is on *the test's transaction boundary*, observing committed data on another connection, and cleaning up at the right time.

After this lesson, you can:

1. Describe the exact lifecycle of `@BeforeTransaction`, `@BeforeEach`, `@Test`, `@AfterEach`, and `@AfterTransaction`.
2. Distinguish **transactions managed by Spring TestContext** from transactions of services, HTTP servers, `REQUIRES_NEW`, or manually opened transactions.
3. Understand the prerequisites for the two transaction hooks to be invoked — the test must actually have a test-managed transaction.
4. Write tests verifying **default rollback**, `@Commit`, and `@Rollback(false)` using real data on H2.
5. Use out-of-transaction JDBC queries to observe before/after state instead of looking only at entities sitting in the JPA persistence context.
6. Clean up committed records in `@AfterTransaction` without being rolled back with the test.
7. Know when to use `TestTransaction.flagForCommit()`, `TestTransaction.end()/start()`, `@Sql`, `TransactionTemplate`, or a non-`@Transactional` test.
8. Avoid false positives caused by unflushed changes, timeouts running on another thread, multiple transaction managers, and non-database side effects.
9. Run the Java 17 + Spring Boot 3.3.5 + Spring Data JPA + H2 + Gradle + JUnit Jupiter example independently.

**Key takeaway to remember immediately:** `@BeforeTransaction` and `@AfterTransaction` are not aliases for JUnit's `@BeforeEach` and `@AfterEach`. They are orchestrated by **`TransactionalTestExecutionListener`**, **outside the boundary** of the test-managed transaction, and apply only when Spring manages a transaction for that test.

## 1. What Is a Test-Managed Transaction?

`@Transactional` on a JUnit test method or test class can activate Spring TestContext's **test-managed transaction** mechanism. `TransactionalTestExecutionListener` detects the annotation, locates a matching `PlatformTransactionManager`, opens a transaction **before invoking the test method**, and by default **rolls back when the test finishes**.

Example:

~~~java
@SpringBootTest
@Transactional
class AccountRepositoryIntegrationTest {

    @Test
    void createsAccount() {
        // repository.save(...) normally joins the
        // test-managed transaction if using REQUIRED propagation.
    }
}
~~~

This is an explanatory snippet (without service/entity/imports) rather than a standalone runnable project. For test-managed transactions to work, you need:

- Spring TestContext activated (e.g., `@DataJpaTest`, `@SpringBootTest` with the Spring/JUnit extension).
- `TransactionalTestExecutionListener` registered; it is normally included among default listeners.
- A suitable `PlatformTransactionManager` in the `ApplicationContext`.
- The test class/method annotated with `@Transactional` — directly or via a meta-annotation such as `@DataJpaTest`.
- Test transaction propagation not disabling the test-managed transaction.

**Default is rollback**, unless `@Commit`, `@Rollback(false)`, or programmatic logic changes the rollback flag. This is **a policy of the test-managed transaction**, not a promise that every transaction/side effect across the entire application rolls back.

### Three Types of Transactions to Distinguish

| Scope | Managed by whom? | Example | Relation to JUnit rollback |
| --- | --- | --- | --- |
| Test-managed transaction | Spring `TransactionalTestExecutionListener` | JUnit test with `@Transactional` | Rolled back by default after test |
| Spring-managed transaction | AOP transaction of service/repository | `@Service @Transactional` | Usually joins test transaction when same thread, manager, and `REQUIRED/SUPPORTS` |
| Application-managed transaction | App code explicitly controls transaction | `TransactionTemplate`, manual JDBC transaction | Can be independent; check boundaries and propagation |

If a service uses `REQUIRES_NEW`, the service transaction can commit independently. If an HTTP test sends a request via `RANDOM_PORT`, the server handles it on **a different thread**, so server commits do not roll back merely because the test method carries `@Transactional`.

## 2. Exact Lifecycle Order

For a typical JUnit Jupiter test method with a test-managed transaction, the flow is:

~~~text
Spring TestContext initializes context, injects dependencies
    |
    v
@BeforeTransaction                [NO test-managed transaction]
    |
    v
BEGIN test-managed transaction
    |
    v
@BeforeEach                      [INSIDE test-managed transaction]
    |
    v
@Test                            [INSIDE test-managed transaction]
    |
    v
@AfterEach                       [INSIDE test-managed transaction]
    |
    v
ROLLBACK (default) / COMMIT (when @Commit / @Rollback(false))
    |
    v
@AfterTransaction                [NO test-managed transaction]
~~~

This is the exact lifecycle **relative to the test-managed transaction**; it does not depict other JUnit extensions, `@Sql` execution listeners, or transactions opened by services/async threads.

### Comparison Table

| Annotation | Origin | Runs relative to test transaction | Typical purpose |
| --- | --- | --- | --- |
| `@BeforeTransaction` | Spring TestContext | **Before BEGIN**, outside test transaction | Read committed baseline; create precondition data outside test transaction if needed |
| `@BeforeEach` | JUnit Jupiter | **Inside** transaction for transactional tests | Create fixtures that belong to the rolled-back transaction |
| `@Test` | JUnit Jupiter | **Inside** transaction | Execute SUT and internal assertions |
| `@AfterEach` | JUnit Jupiter | **Inside** transaction for transactional tests | Check temporary state, teardown that needs no separate commit |
| `@AfterTransaction` | Spring TestContext | **After END**, outside test transaction | Verify actual commit/rollback and clean up committed changes |
| `@BeforeAll` | JUnit Jupiter | Outside per-method test transactions | Class-level setup; do not rely on per-test transaction |
| `@AfterAll` | JUnit Jupiter | Outside per-method test transactions | Class-level teardown; verify data scope manually |

`@BeforeTransaction` and `@AfterTransaction` are Spring TestContext hooks; they are **not** JUnit lifecycle callbacks. In a plain JUnit test without `SpringExtension`/TestContext, Spring annotations will not be invoked automatically.

### Why Can't @AfterEach Observe End-of-Test Commit?

Suppose:

~~~java
@AfterEach
void checkDatabase() {
    // Here the test transaction is still active.
    // Newly saved data may already exist inside the transaction.
}
~~~

Because rollback/commit has not happened yet, an assertion here **does not prove final state after the transaction finishes**. To know whether a row still exists **after rollback**, inspect from `@AfterTransaction`, querying data outside the test transaction.

Conversely, if you want setup/cleanup inside the transaction that rolls back with the test, `@BeforeEach` or `@AfterEach` is usually the right place.

## 3. Imports, Invocation Rules, and Execution Conditions

Both annotations live in package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

They are completely distinct from:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
~~~

A structural example:

~~~java
@BeforeTransaction
void verifyInitialState() {
    // Read data committed before the test transaction.
}

@BeforeEach
void createFixtureInsideTestTransaction() {
    // Can create temporary data, rolled back by default.
}

@Test
void behavior() {
    // Test business logic.
}

@AfterEach
void inspectWithinTestTransaction() {
    // End-of-test rollback/commit has not happened yet.
}

@AfterTransaction
void verifyFinalState() {
    // The test transaction has ended.
}
~~~

This is a non-standalone method snippet. In modern Spring Framework, Spring callbacks can be **non-public void methods**; `public` is not required. `@BeforeTransaction`/`@AfterTransaction` methods can also be declared via **default methods on test interfaces**, as supported by TestContext. With **Spring Framework 6.1 + JUnit Jupiter**, callbacks can even accept arguments resolved by JUnit `ParameterResolver`s (such as `TestInfo` or `@Autowired` beans).

Spring Framework 6.1 example:

~~~java
@BeforeTransaction
void verifyState(@Autowired DataSource dataSource) {
    // Use DataSource injected by SpringExtension
    // to read baseline.
}
~~~

This is a non-standalone snippet requiring `DataSource` imports and a proper injection context. The simplest, most compatible, and easiest-to-review approach in demos is **field injection** of `JdbcTemplate`/repository with parameterless hooks.

### When Do the Two Hooks NOT Run?

- The test lacks `@Transactional` or another annotation enabling test-managed transactions.
- No Spring TestContext/`TransactionalTestExecutionListener` orchestrates them.
- The test is marked `@Transactional(propagation = NOT_SUPPORTED)` or `NEVER`: Spring **does not open** a test-managed transaction.
- The test method uses a context without a suitable transaction manager, causing transaction support initialization to fail (typically a setup error, not a silent skip).
- You put `@Transactional` **only on a service** without enabling test-managed transactions on the test method: a service transaction does not cause test transaction callbacks to run.

**Important realization:** `@BeforeTransaction`/`@AfterTransaction` run **per test transaction**, not before/after **every `repository.save(...)` call** or every `@Transactional` service method.

## 4. Why Check "Outside the Transaction"?

Test example:

~~~java
@Test
void insertWithinTestTransaction() {
    repository.save(new JournalEntry(...));
    assertEquals(1, repository.count());
}
~~~

This snippet is only illustrative with an existing entity/repository. If both `save` and `count` run inside **the same test transaction**, a result of 1 only proves the transaction **sees its own data**. It does not prove:

- The row **committed** and is visible to another transaction.
- The row remains **after rollback**.
- Database constraints were checked at `flush`/`commit`.
- Another process/job can read the data right after the test.
- `@AfterEach` cleanup actually deleted a record committed from another transaction.

`@BeforeTransaction` is ideal for verifying a previously committed **baseline**. `@AfterTransaction` is ideal for verifying **post-transaction state**. The exact same SQL query can return different results depending on whether it runs **inside or outside** the transaction.

### Distinguishing `flush` from `commit`

In JPA:

- `repository.save(entity)` places the entity in the persistence context and may schedule SQL.
- `repository.saveAndFlush(entity)` forces JPA to synchronize pending SQL to the database inside the current transaction.
- **`flush` does not commit**: the row can still roll back if the transaction has not ended.
- After `@Commit`, the transaction completes and the row becomes visible to new connections.
- After rollback, the row is absent from the committed database.

The runnable project below uses `saveAndFlush` to ensure the INSERT has been sent to H2 **inside the transaction**, then uses `JdbcTemplate` **outside the transaction** in `@AfterTransaction` to observe the final outcome.

## 5. Runnable Project: Spring Boot 3.3.5 + Java 17 + JPA/H2

To illustrate commit/rollback clearly, we use a small table `tx_probe_notes` with a unique `test_key` per test method run. No HTTP server, no PostgreSQL, no Docker needed. The test suite has **3 methods**:

1. **Default rollback:** save row inside the transaction, test rolls back at the end, `@AfterTransaction` must see **0 rows**.
2. **`@Commit`:** save row, commit at end of test, `@AfterTransaction` must see **1 row** and then delete only that row.
3. **`@Rollback(false)`:** also requests commit, distinguishing the annotation from default rollback; scoped cleanup at the end.

A unique UUID per method prevents collisions on re-runs or when multiple tests share a database. The hooks check `TestTransaction.isActive()` explicitly to prove their position relative to the test transaction.

### 5.1. Directory Tree

~~~text
transaction-hook-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/txhooks/
    │   ├── TxHooksApplication.java
    │   ├── TxProbeNote.java
    │   └── TxProbeNoteRepository.java
    └── test/java/com/example/txhooks/
        └── TransactionBoundaryHooksTest.java
~~~

This is the source/config listing. The `gradlew`/Wrapper JAR files must be generated with an appropriate Gradle version or taken from a repository; `gradle-wrapper.jar` is a binary and cannot be recreated by copying Markdown.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'transaction-hook-demo'
~~~

### 5.3. `build.gradle` (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-boot-starter-data-jpa` provides Hibernate, transaction manager, repositories, and DataSource support.
- `spring-boot-starter-test` provides `@DataJpaTest`, Spring TestContext/JUnit Jupiter, and assertions.
- H2 at `testRuntimeOnly` lets the test slice use an in-memory database without needing a real DB server.
- `useJUnitPlatform()` tells Gradle to discover and run JUnit 5 `@Test` methods.
- Versions come from the Spring Boot BOM, avoiding pinning mismatched Hibernate/Spring versions that could alter `@DataJpaTest` behavior.

Do not use the demo `ddl-auto=create-drop` setting in production. In real applications, schemas should be managed by Flyway/Liquibase or equivalent migrations.

### 5.4. Spring Boot Root Configuration

**`src/main/java/com/example/txhooks/TxHooksApplication.java`**:

~~~java
package com.example.txhooks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxHooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxHooksApplication.class, args);
    }
}
~~~

Spring Boot tests can find `@SpringBootConfiguration` from the root package. `@DataJpaTest` loads only the JPA slice and does not start an HTTP server.

### 5.5. Real JPA Entity

**`src/main/java/com/example/txhooks/TxProbeNote.java`**:

~~~java
package com.example.txhooks;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "tx_probe_notes")
public class TxProbeNote {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "test_key", nullable = false, length = 100)
    private String testKey;

    @Column(name = "message", nullable = false, length = 160)
    private String message;

    protected TxProbeNote() {
        // Required by JPA
    }

    public TxProbeNote(String testKey, String message) {
        this.testKey = testKey;
        this.message = message;
    }

    public Long getId() {
        return id;
    }

    public String getTestKey() {
        return testKey;
    }

    public String getMessage() {
        return message;
    }
}
~~~

`testKey` is a fixture marker, not a business identity. `GenerationType.IDENTITY` lets H2 generate IDs; do not hardcode IDs in tests. The lesson queries rows by `test_key` because we need to find the exact data created by the current method.

### 5.6. Spring Data JPA Repository

**`src/main/java/com/example/txhooks/TxProbeNoteRepository.java`**:

~~~java
package com.example.txhooks;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TxProbeNoteRepository
        extends JpaRepository<TxProbeNote, Long> {

    long countByTestKey(String testKey);
}
~~~

`countByTestKey` is a Spring Data JPA derived query using the Java property `testKey`. It is called only **inside the test transaction** to verify temporary state. When checking data **after the transaction ends**, the demo uses `JdbcTemplate` inside `@AfterTransaction` and direct SQL to keep the perspectives clearly separated.

### 5.7. Complete Integration Test

**`src/test/java/com/example/txhooks/TransactionBoundaryHooksTest.java`**:

~~~java
package com.example.txhooks;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.show-sql=false"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
class TransactionBoundaryHooksTest {

    @Autowired
    private TxProbeNoteRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private String testKey;
    private boolean expectCommitted;

    // Spring callback: NO test-managed transaction yet.
    @BeforeTransaction
    void beforeTransaction() {
        assertFalse(TestTransaction.isActive());

        testKey = "case-" + UUID.randomUUID();
        expectCommitted = false;

        assertEquals(0, countCommittedRows());
    }

    // JUnit callback: CURRENTLY inside test-managed transaction.
    @BeforeEach
    void beforeEach() {
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void defaultRollbackDiscardsTheInsertedRow() {
        repository.saveAndFlush(
                new TxProbeNote(testKey, "rollback"));

        assertEquals(1L,
                repository.countByTestKey(testKey));

        // No @Commit or @Rollback(false):
        // Spring rolls back the test transaction by default.
    }

    @Test
    @Commit
    void commitMakesTheRowVisibleAfterTransaction() {
        expectCommitted = true;

        repository.saveAndFlush(
                new TxProbeNote(testKey, "commit"));

        assertEquals(1L,
                repository.countByTestKey(testKey));
    }

    @Test
    @Rollback(false)
    void rollbackFalseAlsoCommitsTheTransaction() {
        expectCommitted = true;

        repository.saveAndFlush(
                new TxProbeNote(testKey, "rollback-false"));

        assertEquals(1L,
                repository.countByTestKey(testKey));
    }

    // JUnit callback: end-of-test commit/rollback has NOT happened yet.
    @AfterEach
    void afterEach() {
        assertTrue(TestTransaction.isActive());
    }

    // Spring callback: the test transaction HAS ended.
    @AfterTransaction
    void afterTransaction() {
        assertFalse(TestTransaction.isActive());

        int actualCommittedRows = countCommittedRows();

        try {
            assertEquals(
                    expectCommitted ? 1 : 0,
                    actualCommittedRows);
        } finally {
            // Cleanup outside test-managed transaction,
            // deleting only the row created by the current method.
            jdbcTemplate.update(
                    "DELETE FROM tx_probe_notes WHERE test_key = ?",
                    testKey);
        }

        assertEquals(0, countCommittedRows());
    }

    private int countCommittedRows() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM tx_probe_notes "
                    + "WHERE test_key = ?",
                Integer.class,
                testKey);

        return count == null ? 0 : count;
    }
}
~~~

### 5.8. Why Is This Code Trustworthy?

**First: the test actually has a managed transaction.** `@DataJpaTest` is a transactional test slice in Boot 3.3. Spring TestContext opens a transaction around the method; `TestTransaction.isActive()` directly verifies this condition in `@BeforeEach`/`@AfterEach`.

**Second: `@BeforeTransaction` observes the baseline.** Because the test has not opened a transaction yet, the `SELECT COUNT(*)` via `JdbcTemplate` reads the committed database. Each method has a unique `testKey`, so expecting 0 does not depend on other test outcomes.

**Third: test data is flushed to the DB yet not committed.** `saveAndFlush` guarantees the SQL INSERT runs inside the transaction, so `repository.countByTestKey` sees 1; this **does not mean** an external connection sees the record yet.

**Fourth: `@AfterTransaction` sees the final outcome.**

- **Default rollback** test: the inserted row was rolled back, expected **0**.
- **`@Commit`** test: the transaction committed, expected **1**.
- **`@Rollback(false)`** test: also committed, expected **1**.

**Fifth: cleanup runs outside the just-finished transaction.** `JdbcTemplate.update("DELETE ... WHERE test_key = ?")` targets only the current method's row. In the H2/autocommit demo when no Spring transaction is active, the DELETE commits; the final assertion confirms it is clean.

**Sixth: cleanup still runs when the row-count assertion fails.** The `try`/`finally` block attempts the DELETE even if `assertEquals` throws an `AssertionError`. This reduces leftover garbage after normal failures. It does not guarantee cleanup if the JVM is killed, the DB becomes unreachable, or the process crashes.

### Expected Results for Each Test

| Test | Inside `@Test` after `saveAndFlush` | After transaction in `@AfterTransaction` | After cleanup |
| --- | ---: | ---: | ---: |
| `defaultRollbackDiscardsTheInsertedRow` | 1 | 0 | 0 |
| `commitMakesTheRowVisibleAfterTransaction` | 1 | 1 | 0 |
| `rollbackFalseAlsoCommitsTheTransaction` | 1 | 1 | 0 |

The project defines **3 JUnit `@Test` methods**. Transaction hooks run for **each test method**, though they do not count as separate test methods. Under proper configuration, **3 tests are expected to pass**; this expectation is derived from the source code, **not from having run Gradle on the learner's machine**.

## 6. Running the Project and Checking Reports

From the root directory with `gradlew`, `build.gradle`, and JDK 17:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the transaction hooks class:

~~~bash
./gradlew test --tests 'com.example.txhooks.TransactionBoundaryHooksTest'
~~~

Reports are typically located at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.txhooks.TransactionBoundaryHooksTest.xml
~~~

There is no `System.out.println`, so there is no fixed business stdout. Gradle may report `BUILD SUCCESSFUL` on success; if the test task is cached, it may show `UP-TO-DATE` or `FROM-CACHE`.

To force tests to re-run during diagnostics:

~~~bash
./gradlew test --rerun-tasks
~~~

If a repo lacks the Gradle Wrapper, generate it from a compatible installed Gradle, e.g.:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then keep Wrapper scripts/JAR according to repository policy. Do not change a project team's Gradle version unilaterally without evaluating compatibility.

### Reading Reports Within Proper Scope

If a `@Commit` test fails in `@AfterTransaction` with expected 1 but actual 0, check whether the transaction really committed, whether an annotation overrode it, whether JDBC and JPA datasources point to the same database, or whether code deleted data before the hook. Never change expected to 0 just to turn a test green.

If a rollback test fails with expected 0 but actual 1, check whether:

- The transaction committed due to `@Commit`/`@Rollback(false)` on the class/method or a meta-annotation.
- Code used `REQUIRES_NEW` in a service, committing independently.
- The repository/transaction manager points to a different DataSource than `JdbcTemplate` reads.
- SQL ran directly on an autocommit connection outside the Spring test transaction.
- The test method ran on another thread due to a preemptive timeout or async logic.

Diagnosis should start with the **transaction boundary** and **correct data source**, not merely an assertion stack trace.

## 7. How Do @Commit and @Rollback Differ?

A transactional test rolls back by default. Spring's annotations can change how it finishes:

~~~java
@Test
@Commit
void shouldCommitAtEnd() {
    // Commits the test transaction when the test ends.
}
~~~

~~~java
@Test
@Rollback(false)
void shouldAlsoCommitAtEnd() {
    // In final outcome, equivalent to @Commit.
}
~~~

~~~java
@Test
@Rollback
void shouldRollBackAtEnd() {
    // Explicitly rolls back, even if the class has @Commit.
}
~~~

These examples are method snippets, not standalone classes. `@Commit` is a convenience annotation meaning `@Rollback(false)`. When both class `@Commit` and method `@Rollback` exist, the more specific method configuration overrides at the appropriate level.

**Do not put `@Transactional(rollbackFor = ...)` on a test expecting the listener to honor it like service AOP.** According to Spring TestContext, attributes of `@Transactional` such as `rollbackFor`/`noRollbackFor`, `isolation`, and `timeout` are **not supported mechanisms** for controlling a test-managed transaction like a service transaction. Use `@Commit`, `@Rollback`, or `TestTransaction.flagForCommit()/flagForRollback()`.

### Committed Data Can Pollute the Suite

If you place `@Commit` on a test using a shared database without cleanup, the row persists after the test. The demo solves this with `@AfterTransaction` combined with a marker. In production-like environments, you should:

- Use a dedicated test database/schema or Testcontainers.
- Track resource IDs/test-run keys.
- Delete only test-created data in a committed cleanup transaction.
- Never call `deleteAll()` system-wide on a shared DB.
- Have infrastructure-level teardown in case the JVM is killed before `@AfterTransaction`.

## 8. @AfterEach Cleanup Can Roll Back with the Test

A misleading pattern:

~~~java
@AfterEach
void cleanup() {
    repository.deleteAll();
}
~~~

If the class is a transactional test, `@AfterEach` normally **still runs inside the test transaction**. The `DELETE` command can be enrolled in that transaction and rolled back with the test. For data committed **from another transaction**, that `DELETE` may fail to actually remove the committed record.

For data created and rolled back by **the test transaction itself**, separate cleanup is usually unnecessary. However, for `@Commit` or independent transactions, cleanup must **actually commit**. `@AfterTransaction` is a logical place to observe and clean up state **after** the test transaction.

### Difference Between Cleanup and Assertion

A test should not merely write:

~~~java
@AfterTransaction
void cleanup() {
    repository.deleteAll();
}
~~~

That risks deleting other tests' data while failing to tell you whether commit/rollback worked properly. Better:

1. Create a marker before the test.
2. Know the **expected outcome** (commit or rollback).
3. Read actual state from the database after the transaction.
4. Assert the expected outcome.
5. Clean up only that marker, **even if a normal assertion fails**.
6. Verify cleanup succeeded or report an error if it did not.

The runnable project performs all these steps. It does not use `repository.deleteAll()`, does not modify other schemas/tables, and needs no HTTP port.

## 9. `TestTransaction` Allows Controlling the Transaction Mid-Test

Spring provides `org.springframework.test.context.transaction.TestTransaction` to interact with the test-managed transaction:

- `TestTransaction.isActive()`: is a TestContext-managed transaction active on this thread?
- `TestTransaction.flagForCommit()`: requests the current transaction to commit when ended.
- `TestTransaction.flagForRollback()`: requests rollback when ended.
- `TestTransaction.end()`: ends the current test transaction according to the rollback/commit flag.
- `TestTransaction.start()`: starts a new test-managed transaction when lifecycle/test context allows.

Illustrative example inside a transactional JUnit method:

~~~java
@Test
void commitsMidTestThenStartsNewTransaction() {
    repository.saveAndFlush(new TxProbeNote(testKey, "first"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    // Observe committed data from a new connection.
    assertEquals(1, countCommittedRows());

    TestTransaction.start();
    assertTrue(TestTransaction.isActive());

    // New operations in this transaction roll back by default
    // if flagged for rollback accordingly.
    TestTransaction.flagForRollback();
}
~~~

This is an **advanced snippet**, omitted from the runnable class to keep the primary example focused. It assumes the project's `repository`, `testKey`, and `countCommittedRows()`. When using `TestTransaction.end()` early, track hook lifecycles, test transaction state, and cleanup carefully; never call `start()` or `end()` indiscriminately when inactive.

### `TestTransaction` Is Not Equivalent to `TransactionTemplate`

- `TestTransaction` works with the **test-managed transaction** managed by Spring TestContext.
- `TransactionTemplate` programmatically executes a callback with a transaction manager; it can open/suspend another transaction depending on propagation.
- `@BeforeTransaction`/`@AfterTransaction` are **callbacks before/after the test method's transaction**, not callbacks around every `TransactionTemplate.execute(...)` call.

Therefore, calling `TransactionTemplate.executeWithoutResult(...)` inside a JUnit test **does not automatically make** `@BeforeTransaction`/`@AfterTransaction` run around each callback. The hooks attach strictly to the lifecycle of a transactional test method managed by the listener.

## 10. When a Test Method Has No Transaction

Suppose a class has `@Transactional`, yet one method wants to opt out of the test-managed transaction:

~~~java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void worksWithoutTestTransaction() {
    // No test-managed transaction.
}
~~~

This is a Java snippet with appropriate Spring transaction imports. For this method, `@BeforeTransaction`/`@AfterTransaction` **are not invoked** because Spring does not start a test-managed transaction for it. If a test has no `@Transactional` at all, those two callbacks do not run either.

This matters when using `@SpringBootTest` where an author puts `@Transactional` only on the **service**. Even though the service method has a transaction, the JUnit test method may **not be a transactional test**; the two Spring TestContext hooks will not wrap the service transaction.

### Methods in a Mixed Class

If the same class contains some transactional methods and some non-transactional ones:

- Hooks run for methods that have a test-managed transaction.
- Hooks skip methods without a test-managed transaction.
- `@BeforeEach`/`@AfterEach` still follow the JUnit lifecycle for every test method.
- Assertions calling `TestTransaction.isActive()` in `@BeforeEach` must reflect the method accurately; do not hardcode `true` for the entire class if a `NOT_SUPPORTED` method exists.

The runnable project keeps all three methods transactional via `@DataJpaTest` so lifecycle semantics remain consistent and easy to follow.

## 11. Repositories and `REQUIRES_NEW`: When Rollback Does Not Erase Everything

A service can split out a transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(String testKey) {
    auditRepository.save(new AuditEvent(testKey));
}
~~~

This is a theoretical snippet; it needs a class/field/imports. `REQUIRES_NEW` can **suspend the current transaction** and create a separate transaction independent of the test transaction.

If a default-rollback test calls `writeAudit(...)` through a real Spring proxy, the audit row may **already be committed** before the test transaction rolls back. `@AfterTransaction` may still see the audit row even though the test method had no `@Commit`.

This is not a callback bug. It reflects:

- The service transaction is independent of the test transaction;
- Commit of transaction B is not undone by rollback of A;
- Constraint/lock contention can occur if A and B touch related rows;
- Connection pool exhaustion can happen if the test holds connection A and `REQUIRES_NEW` needs connection B.

**Important:** `@Transactional` on an internal method called via `this.method()` on the same object may bypass the Spring AOP proxy, so `REQUIRES_NEW` may not actually apply. Tests must verify real wiring/proxies when propagation is part of the contract.

### Cleanup for `REQUIRES_NEW`

If a service writes audit records in a separate transaction, the test fixture must track audit IDs/test keys and clean them up after the test in a committed transaction. Do not assume "the test is `@Transactional`, so every table will clean itself." `@AfterTransaction` is a good place to verify final state, though teardown in a dedicated DB/container may also be needed when there are multiple side effects.

## 12. HTTP Tests Have Different Transactions

When using:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpIntegrationTest {
    // TestRestTemplate/WebTestClient sends HTTP to server.
}
~~~

Illustrative snippet, not runnable source. The HTTP client on the test thread sends a request over a socket; the controller/service runs on a **server thread** and usually opens a different transaction. Rolling back the test-managed transaction affects only the test thread's transaction and **does not automatically roll back transactions committed on the server**.

Consequently:

- `@BeforeTransaction` is not a hook "before each HTTP server transaction."
- `@AfterTransaction` is not a hook "after every HTTP request."
- It runs only at the boundary of the **test-managed transaction**.
- Server-committed data can persist even after the test rolls back.
- Cleanup via repository/API in an out-of-test transaction or a dedicated database/schema container is typically necessary.

To prove an **HTTP API really commits**, use `RANDOM_PORT`, send the HTTP request, and then GET or query the DB from another connection/transaction. To prove the **test transaction lifecycle**, the JPA slice project in this lesson is sufficient and faster.

## 13. `@Sql` and Other Levels of Data Preparation

Spring TestContext provides `@Sql` to execute scripts before/after test methods. It can be a good choice when fixtures are static SQL data; meanwhile, `@BeforeTransaction`/`@AfterTransaction` are lifecycle hooks suited for **Java logic** that needs to observe the DB before/after the transaction.

Illustrative example:

~~~java
@Sql(
    scripts = "/sql/seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Transactional
@Test
void readsSeedData() {
    // ...
}
~~~

This is not a runnable project because `seed.sql`, imports, and table mappings are not included.

The key detail is `@Sql`'s **transaction mode**. If a cleanup script runs **inside a transaction that eventually rolls back**, that script will fail to clean up server-committed data. When SQL cleanup needs its own commit, you can configure `SqlConfig.TransactionMode.ISOLATED` matching the datasource/transaction manager and data scope.

Do not assume `@Sql(AFTER_TEST_METHOD)` is always equivalent to `@AfterTransaction` in every configuration; listener ordering and `@Sql` transaction mode can differ. When the requirement is **asserting state after rollback/commit**, `@AfterTransaction` expresses the intent more directly.

### Why Is `@BeforeTransaction` Not `@BeforeAll`?

`@BeforeAll` runs once before all test methods of the class (under JUnit instance lifecycle), whereas `@BeforeTransaction` is called **for each transactional test method**. Therefore:

- Per-case baseline → `@BeforeTransaction`.
- Class-shared resource initialization → `@BeforeAll` or appropriate test infrastructure.
- Fixtures inside the rolled-back transaction → `@BeforeEach`.
- Per-case marker cleanup of committed data → `@AfterTransaction`.
- External container teardown at the end of a class/suite → class/infrastructure lifecycle.

## 14. Avoiding False Positives from the JPA Persistence Context

In JPA, a test usually has an `EntityManager`/Hibernate persistence context bound to the transaction. Calling `repository.save(entity)` and asserting on the just-saved object may not have verified database constraints or executed SQL at all.

Example:

~~~java
repository.save(new TxProbeNote(testKey, "sample"));
// Reading properties of the Java object is not proof of INSERT.
~~~

A `NOT NULL`, unique constraint, or data truncation error might only surface at `flush`/`commit`. Therefore, when testing ORM/database behavior, use `saveAndFlush` or `entityManager.flush()` at the right step.

In the project:

~~~java
repository.saveAndFlush(
    new TxProbeNote(testKey, "rollback"));
~~~

SQL was sent to H2, yet rollback at the end of the test still erases the transaction's effects. `@AfterTransaction` uses `JdbcTemplate` outside the transaction to inspect the final data.

### Queries Outside the Transaction Can Also Be Affected by Caching/Routing

- If using a read replica with lag, a post-commit query may not see the row immediately.
- If the `DataSource` routes by tenant, the hook must read the right tenant/schema.
- With a JPA `EntityManager` still holding managed entities, `repository.findById` in the same persistence context may return cached state.
- `JdbcTemplate` queries the DB more directly yet can still pass through a proxy/routing `DataSource`.
- With `REPEATABLE_READ` DB isolation, another transaction holding an older snapshot may not see a new commit.

The demo avoids these issues via a primary in-memory H2 database and a JDBC query after the test transaction completes. When production involves replication or eventual consistency, tests must match that contract rather than relying on unguaranteed assumptions.

## 15. Preemptive Timeouts Can Escape the Test Transaction

Spring TestContext binds transaction state to the **current thread**. If a JUnit or framework timeout runs the test body on a **different thread**, operations in the body may not join the test-managed transaction even while hooks still observe the original thread's transaction.

A dangerous pattern:

~~~java
@Test
@Transactional
void writeWithPreemptiveTimeout() {
    assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> repository.save(new TxProbeNote("x", "y")));
}
~~~

This is an illustrative snippet requiring imports and a repository; it is **not recommended** for real database writes. `assertTimeoutPreemptively` runs the lambda on another thread, risking that the transaction does not propagate across threads, causing the row to **commit** and survive test-thread rollback.

Spring Framework issues a similar warning for other preemptive timeout mechanisms that run test bodies on a new thread. For transactional tests, prefer timeouts that do not switch threads or manage transactions/cleanup explicitly. With async/reactive code, understand its dedicated context/transaction propagation rather than assuming thread-bound transactions cover every scheduler.

### `assertTimeout` vs. `assertTimeoutPreemptively`

The two JUnit APIs have different semantics. Non-preemptive `assertTimeout` executes the code on the calling thread in normal usage, whereas `assertTimeoutPreemptively` can execute on a separate thread. When a test has a JDBC/JPA test-managed transaction, that difference can decide whether a row rolls back or not.

## 16. Multiple Transaction Managers and @Transactional Qualifiers

In an application with a single `DataSource`, `PlatformTransactionManager` is usually auto-configured appropriately. With multiple data sources, you must know **which transaction manager** TestContext selects.

Example:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
@Test
void orderRepositoryTest() {
    // ...
}
~~~

Illustrative snippet requiring a matching bean name. An `@BeforeTransaction` querying an audit DB while the test transaction manages an orders DB will see different behavior; you cannot conclude that rolling back orders deletes audit data.

To test accurately:

1. Identify which manager the method/class `@Transactional` specifies.
2. Verify the repository or `JdbcTemplate` injects the matching `DataSource`.
3. When multiple managers exist, use qualifiers or `TransactionManagementConfigurer` per Spring's supported mechanisms.
4. Inspect before/after data against the right DB/schema.
5. When a service uses a different transaction manager, treat it as an independent transaction that may require separate cleanup.

### `@BeforeTransaction` Can Run When No Spring TX Exists Yet a Service Will Open Its Own

That is valid behavior: the callback only signals that the **test transaction** is not active yet. It **does not prove there are no transactions in the DB** (for example, a separate service transaction or another JDBC connection running). Avoid interpreting `TestTransaction.isActive() == false` as "the whole system has no transactions."

## 17. Comparison with Other Approaches

| Goal | Suitable tool | Notes |
| --- | --- | --- |
| Verify baseline before test tx | `@BeforeTransaction` | Outside test tx, runs per transactional method |
| Set up fixtures inside test tx | `@BeforeEach` | Rolls back with test by default |
| Inspect state inside test tx | JUnit `@Test` or `@AfterEach` | End-of-method commit/rollback has not happened yet |
| Verify DB after test tx | `@AfterTransaction` | Outside test tx, observes commit/rollback |
| Commit instead of roll back at end of test | `@Commit` / `@Rollback(false)` | Requires cleanup of committed data |
| Control commit/end mid-test | `TestTransaction` | Advanced usage, tied to test tx lifecycle |
| Independent transaction in Java callback | `TransactionTemplate` | Not a TestContext lifecycle hook |
| Static SQL fixtures tied to lifecycle | `@Sql` and transaction mode | Watch `ISOLATED` and script scope |
| Fast JPA repository tests | `@DataJpaTest` | Transactional, rolled back by default |
| Fast JDBC query tests | `@JdbcTest` | Transactional, rolled back by default |
| Test full bean graph/config | `@SpringBootTest` | Not automatically transactional without annotation |
| Verify commit through real HTTP server | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Separate server tx; explicit cleanup |
| Clean external test DB state | Scoped cleanup + committed transaction | Or separate DB/schema/container |

## 18. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@BeforeTransaction` does not run | Test is not transactional or lacks TestContext listener | Check `@Transactional`, `@DataJpaTest`, TestContext |
| `@AfterTransaction` does not run | No test-managed transaction or `NOT_SUPPORTED`/`NEVER` propagation | Separate test or enable transaction |
| `@AfterEach` sees row despite test rollback | `@AfterEach` still runs inside the transaction | Check final outcome in `@AfterTransaction` |
| Row persists after default-rollback test | Data committed in independent tx/HTTP/other thread | Trace transaction boundary, clean up separately |
| `@AfterTransaction` sees 0 despite `@Commit` | `@Rollback` override, wrong DB/manager, or early cleanup | Check annotations, qualifiers, DataSource |
| `@AfterTransaction` sees 1 with default rollback | `REQUIRES_NEW` or independent auto-commit write | Check propagation, proxy, and side effects |
| Test passes despite invalid DB constraint | `save` not flushed yet | Use `saveAndFlush`/`entityManager.flush` |
| `@BeforeTransaction` throws table not found | Test schema/migrations not ready yet | Run migrations/DDL properly before test lifecycle |
| `@Commit` pollutes suite with leftover data | Missing post-commit cleanup | Clean up by test key/ID in `@AfterTransaction` |
| `@AfterEach` cleanup fails to delete committed row | Cleanup ran inside transaction that rolled back | Clean up after transaction or in a new transaction that commits |
| `TestTransaction.isActive()` is always false | Test lacks `@Transactional` or body ran on another thread | Check TestContext and preemptive timeouts |
| `TestTransaction.end()` reports transaction inactive | Called when no test tx exists | Check `isActive`/lifecycle before calling `end` |
| Hook DataSource query differs from repository | Multi-DataSource or wrong tenant routing | Use matching qualifier/schema/manager |
| `@AfterTransaction` fails during cleanup | `DELETE` targets wrong table/column or DB unavailable | Verify schema, log sanitized info, fail loudly on cleanup errors |
| `deleteAll()` wipes other tests' data | Overly broad cleanup in shared DB | Filter by test key/resource IDs |
| H2 test passes yet Postgres fails | Dialect, isolation, DDL, locking differences | Use Testcontainers on production engine |
| Connection pool timeout error | Test holds transaction/connection while opening another tx | Avoid accidental nested `REQUIRES_NEW`, check pool config |
| Hooks run more times than expected | Each transactional method gets a callback pair | Distinguish per-method vs. per-class lifecycles |
| Hook parameter fails to resolve | Incompatible JUnit extension/version | Use field injection or Spring Framework 6.1+ |
| `@SpringBootTest` test does not auto-roll back | `@SpringBootTest` is not `@Transactional` by itself | Mark test transactional if needed, or clean up |
| Event/cache/file remains after rollback | Side effect lives outside JDBC tx | Compensate/clean up per resource |

### Troubleshooting Workflow

1. Inspect test method/class annotations: is there actually a test-managed transaction?
2. Check `@Commit`/`@Rollback` and any overriding annotations.
3. Add `TestTransaction.isActive()` assertions in the hooks to prove boundaries.
4. Check whether `saveAndFlush` sent SQL to the DB **without** committing yet.
5. In `@AfterTransaction`, query the right `DataSource`, marker, and schema.
6. Check for `REQUIRES_NEW`, HTTP requests, async work, or preemptive timeouts.
7. Verify whether cleanup actually committed rather than rolling back with the test.
8. If multiple DB managers exist, select the right bean and qualifier.
9. If running against a real test DB, verify tenant/fixture/replica lag.
10. Never change expected to match a broken actual just to keep tests green; verify against the contract.

## 19. Self-Practice Exercises

**Exercise A — Lifecycle order:** Draw a diagram for the 5 annotations `@BeforeTransaction`, `@BeforeEach`, `@Test`, `@AfterEach`, `@AfterTransaction`. Clearly mark `BEGIN` and `ROLLBACK`/`COMMIT`.

**Exercise B — Default rollback:** Run `defaultRollbackDiscardsTheInsertedRow`. Temporarily change expected `0` to `1` in the rollback check to confirm the test turns red, then revert it.

**Exercise C — `@Commit`:** Run `commitMakesTheRowVisibleAfterTransaction`. Remove `@Commit` and observe the assertion in `@AfterTransaction` fail with expected 1 vs. actual 0 in the database. Restore the annotation.

**Exercise D — `@Rollback(false)`:** Try replacing `@Rollback(false)` with `@Rollback` on the third test and explain why expectations must change if that behavior is intentional.

**Exercise E — Cleanup:** Remove `DELETE FROM tx_probe_notes WHERE test_key = ?` on an isolated test DB branch and re-run. Observe the committed record remaining; restore the scoped cleanup.

**Exercise F — `@AfterEach`:** Move the `actualCommittedRows` assertion into `@AfterEach`, and analyze why it fails to prove post-commit/post-rollback data state.

**Exercise G — `TestTransaction`:** In a separate transactional test, call `flagForCommit()` and `end()`, query the database before calling `start()` for a new transaction. Ensure end-of-test cleanup and intact lifecycle.

**Exercise H — No test transaction:** Create a `@SpringBootTest` class without `@Transactional`. Attach `@BeforeTransaction`/`@AfterTransaction` and observe that they do not run, even though JUnit `@BeforeEach` still runs.

**Exercise I — Propagation:** Write a `REQUIRES_NEW` service that creates an audit row in the test DB. Call it from a default-rollback transactional test, verify the audit row can survive rollback, and design separate cleanup.

**Exercise J — Preemptive timeout:** Compare `assertTimeout` and `assertTimeoutPreemptively` in a JDBC test that writes data; explain the risk of escaping the transaction due to another thread. Test only on an isolated DB.

**Exercise K — Testcontainers:** Replace H2 with PostgreSQL Testcontainers, run test schema migrations, execute commit/rollback tests, and inspect engine metadata before cleanup.

**Exercise L — Multiple DataSources:** Use separate orders and audit DataSources. Specify `@Transactional(transactionManager=...)` and query the right DB in `@AfterTransaction`.

## 20. Transaction Hooks Testing Checklist

- [ ] Do I know whether the test uses `@DataJpaTest`, `@JdbcTest`, or `@SpringBootTest` and has a test-managed transaction?
- [ ] Are `TransactionalTestExecutionListener`/`PlatformTransactionManager` ready?
- [ ] Do I distinguish `@BeforeTransaction`/`@AfterTransaction` from JUnit `@BeforeEach`/`@AfterEach`?
- [ ] Do I know `@BeforeTransaction` runs before `BEGIN` and `@AfterTransaction` runs after `COMMIT`/`ROLLBACK`?
- [ ] Do I avoid mistaking `@AfterEach` for post-rollback timing?
- [ ] Do I use hooks only for transactional tests, without expecting them to run under `NOT_SUPPORTED`/`NEVER`?
- [ ] Do I scope `@Commit`/`@Rollback` properly and avoid `rollbackFor` to control test tx?
- [ ] With JPA, did I `flush` when testing SQL/constraints?
- [ ] Did I read the database after the transaction using a suitable connection/transaction and the right test key?
- [ ] Do I clean committed data with a transaction that actually commits, rather than wiping whole tables?
- [ ] Do I understand `REQUIRES_NEW` services or HTTP servers can be independent of the test tx?
- [ ] Do I avoid preemptive timeouts that let test DB operations escape the transaction-bound thread?
- [ ] When multiple transaction managers exist, do hooks and queries target the right `DataSource`?
- [ ] Are tests order-independent without leaking committed state across methods?
- [ ] Does the test database use isolated credentials/schema without touching production?
- [ ] Do test outcomes/assertions read back expected state genuinely rather than passing due to the same persistence context?
- [ ] Do Gradle/JUnit reports show the tests actually executed rather than `UP-TO-DATE`?

## 21. Official References

- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, lifecycle, hooks, programmatic `TestTransaction`, timeouts, and flushing.
- [Spring Framework — @BeforeTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html): timing of the pre-transaction callback.
- [Spring Framework — @AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-aftertransaction.html): timing of the post-transaction callback.
- [Spring Framework 6.1 — AfterTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): void methods, JUnit parameter resolution.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `isActive`, `flagForCommit`, `end`, `start`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest` and default rollback.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): repository transaction semantics.
- [JUnit Jupiter — Lifecycle Methods](https://docs.junit.org/5.10.2/user-guide/#writing-tests-annotations): `@BeforeEach`, `@AfterEach`, test lifecycle.

**Remember:** `@BeforeTransaction` inspects **state before the test transaction opens**, and `@AfterTransaction` inspects **state after the test transaction commits/rolls back**. `@BeforeEach` and `@AfterEach` run **inside** the transaction for transactional tests. Using the right callbacks, flushing at the right time, defining commit/rollback expectations, and performing scoped cleanup verifies real transactions rather than temporary state inside a persistence context.