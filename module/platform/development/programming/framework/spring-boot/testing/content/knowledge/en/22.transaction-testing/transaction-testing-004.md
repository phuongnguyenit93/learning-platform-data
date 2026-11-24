# TestTransaction for Intentionally Ending and Reopening Transactions in Spring Boot

## 1. When Do You Need TestTransaction?

In Spring Boot, many database-accessing tests are wrapped by Spring TestContext in a **test-managed transaction**. With `@DataJpaTest`, `@JdbcTest`, or a `@SpringBootTest @Transactional` test, data changes are typically **rolled back after the test**. This approach is convenient because it leaves no records behind, yet sometimes prevents the test from answering **commit**-related questions:

- An `INSERT` is read back right inside the same transaction, but did it actually commit successfully?
- Does the data still exist when read in a **different** transaction after commit?
- If T1 commits and then T2 modifies data and rolls back, is T1's data preserved?
- When can `@AfterEach` fail to clean up committed data?
- How do `flush()`, `commit`, `rollback`, `@Commit`, and `TestTransaction.end()` differ?
- How can you actively verify a rollback branch **before** the test method finishes?

Spring TestContext provides `org.springframework.test.context.transaction.TestTransaction` to **set the commit/rollback flag, end the current test transaction, and start a new test transaction** without ending the test method.

```text
Spring TestContext opens T1 (rollback by default)
   |
   +-- JDBC/Repository writes data in T1
   |
   +-- flagForCommit() or flagForRollback()
   |     (only changes the ending decision)
   |
   +-- end() -----------------> COMMIT or ROLLBACK T1
   |
   +-- inspect data outside test-managed transaction
   |
   +-- start() ---------------> OPEN NEW T2
   |
   +-- further operations in T2
   |
   +-- test ends -------------> ROLLBACK T2 by default
```

**Core point:** `flagForCommit()` **does not commit by itself**, `flagForRollback()` **does not roll back by itself**, and `start()` **does not revive T1**. Only `end()` ends the transaction according to the current flag. A committed transaction is not undone merely because a subsequent transaction rolls back.

This lesson uses **Java 17+, Spring Boot 3.5.x / Spring Framework 6.x, H2, JdbcTemplate, and JUnit Jupiter** to provide a runnable sample project. The same principles apply to JPA once you also account for `EntityManager` and `flush()`.

## 2. Test-Managed, Spring-Managed, and Application-Managed Transactions

| Category | Who manages it? | Example | How far does TestTransaction reach? |
|---|---|---|---|
| **Test-managed** | Spring TestContext's `TransactionalTestExecutionListener` | `@Transactional` test, `@JdbcTest` | `start/end/flag` on the test transaction itself |
| **Spring-managed** | Spring transaction infrastructure inside `ApplicationContext` | `@Transactional` service | May join T1 or create a separate transaction per propagation |
| **Application-managed** | Code using `TransactionTemplate` or transaction manager directly | Service opening programmatic transactions | Not by default a transaction controlled by TestContext |

In a test with an active T1, a `@Transactional(propagation = REQUIRED)` service normally joins T1 when using the same transaction manager/resource, so end-of-test rollback also deletes the service's changes.

A `@Transactional(propagation = REQUIRES_NEW)` service can suspend T1 and create **a different transaction**. If the new transaction commits, rolling back T1 does not automatically delete those independent changes. `NESTED` usually relies on savepoints when supported and is **not equivalent** to `REQUIRES_NEW`.

**HTTP integration:** with `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the test client and embedded HTTP server run on different threads. `TestTransaction` on the client **does not manage** the transaction opened by the server thread, and rolling back the client does not delete DB rows committed by the server.

## 3. Conditions for Calling TestTransaction Properly

You need:

1. The test runs via Spring TestContext with `TransactionalTestExecutionListener` (usually enabled by default).
2. The Spring context has a `PlatformTransactionManager` matching the datasource.
3. The test is actually transactional, e.g., via `@JdbcTest`/`@DataJpaTest` or `@Transactional` on the test.
4. Code invokes `TestTransaction` on the **test thread** that holds `TransactionContext`.
5. The test does **not** disable transactions via `@Transactional(propagation=NOT_SUPPORTED)` or `NEVER`.

```java
import org.springframework.test.context.transaction.TestTransaction;

assertTrue(TestTransaction.isActive());
assertTrue(TestTransaction.isFlaggedForRollback());
```

This is an illustrative snippet **inside a transactional test with default rollback** and JUnit assertions imported. A `@SpringBootTest` test without `@Transactional` does not automatically have a test-managed transaction. Likewise, `TestTransaction` is not a factory for opening arbitrary transactions in a plain JUnit unit test.

**Thread-bound:** Spring TestContext uses thread-bound state. `CompletableFuture`, executors, Reactor schedulers, or preemptive timeout callbacks do not automatically inherit the caller's test transaction.

## 4. Six TestTransaction Methods and Their Meanings

| API | Question answered | Notes |
|---|---|---|
| `isActive()` | Is there an active test-managed transaction on the current thread? | Does not mean "all system transactions are inactive" |
| `isFlaggedForRollback()` | Is the current rollback flag true or false? | Throws an error if no test transaction is active |
| `flagForCommit()` | When ending, attempt to commit this transaction | **Does not commit immediately** |
| `flagForRollback()` | When ending, roll back this transaction | **Does not roll back immediately** |
| `end()` | Ends the current test transaction per flag | Must not be called when inactive |
| `start()` | Opens a **new test transaction** in the current context | Only after `end()` or when context has no active transaction |

The import does not depend on Boot 3.5 vs. 4.x packages:

```java
import org.springframework.test.context.transaction.TestTransaction;
```

### 4.1. Flags Are Only Intent, Not Database Operations

```java
TestTransaction.flagForCommit();
assertFalse(TestTransaction.isFlaggedForRollback());
assertTrue(TestTransaction.isActive());

TestTransaction.flagForRollback();
assertTrue(TestTransaction.isFlaggedForRollback());
assertTrue(TestTransaction.isActive());
```

After both calls, the transaction is still active. Calling `flagForRollback()` after `flagForCommit()` **reverts the flag of that same transaction**. To actually end it, call `end()` or wait for Spring TestContext to finish the test method.

### 4.2. Lifecycle: Commit T1 Then Start T2

```java
// Inside test's T1.
TestTransaction.flagForCommit();
TestTransaction.end();                    // Commits T1 if successful
assertFalse(TestTransaction.isActive());

// Now you can inspect data outside the test transaction.
TestTransaction.start();                  // Starts a new T2
assertTrue(TestTransaction.isActive());
```

The snippet above is not a standalone program. When T2 starts, the test's **default rollback flag** applies again: with `@JdbcTest` the default is rollback; on a test with `@Commit` or `@Rollback(false)`, the default may be commit.

### 4.3. Invalid Calls

- `start()` while a test-managed transaction is still active: typically throws `IllegalStateException`.
- `end()`, `flagForCommit()`, `flagForRollback()` when no test-managed transaction is active: throws `IllegalStateException`.
- `isFlaggedForRollback()` also requires an active transaction; check `isActive()` first.
- Do not call `TestTransaction.start()` as a substitute for `TransactionTemplate` in application code.

## 5. Choosing a JDBC Example to Observe Commit Boundaries Most Clearly

We use `@JdbcTest`: Spring Boot creates JDBC infrastructure and `JdbcTemplate`, uses an H2 test database, and **rolls back each test's transaction by default**. Since the lesson is `TestTransaction`, there is no need to pull controllers/services/JPA into the context.

Example SQL schema:

```sql
CREATE TABLE tx_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    note_text VARCHAR(200) NOT NULL
);
```

Each test uses a unique UUID `note_id`; when a test intentionally commits a record, `@AfterTransaction` deletes it **after the final test transaction ends**. Thus, learning about commit does not turn into residual data pollution on a shared test DB.

Test scenarios:
- Default transaction is active and scheduled to roll back.
- `flagForCommit()` only changes the flag and does not end the transaction.
- `end()` with rollback removes changes before the test finishes.
- `flagForCommit(); end()` persists a durable row readable outside the transaction.
- Commit T1 then update in T2; rolling back T2 keeps T1's committed v1.
- `start()` while active is rejected.
- `end()`/`flag` when no active transaction exists is rejected.

## 6. Complete Java 17+ Project

### 6.1. File Structure

```text
build.gradle
src/main/java/com/example/txlab/
    TxLabApplication.java
src/test/resources/sql/
    tx-notes-schema.sql
src/test/java/com/example/txlab/
    TestTransactionBoundaryTest.java
```

### 6.2. build.gradle for Boot 3.5.x

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Choose a Boot 3.5.x patch version matching your project's update policy; `3.5.8` is a concrete build example. Spring/JUnit dependencies should stay aligned via the Boot BOM. Requires a compatible Gradle/JDK and repository access to download dependencies. H2 is scoped to test runtime only so it never accidentally becomes a production datasource.

If using Maven, include the Spring Boot parent/BOM, `starter-jdbc`, `starter-test`, H2 in test scope, and matching Surefire/JUnit Jupiter.

### 6.3. Application Class

File `src/main/java/com/example/txlab/TxLabApplication.java`:

```java
package com.example.txlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }
}
```

`@SpringBootApplication` helps Spring Boot locate application configuration, yet `@JdbcTest` still loads only the JDBC slice without starting an HTTP server.

### 6.4. SQL Schema Used in Tests

File `src/test/resources/sql/tx-notes-schema.sql`:

```sql
CREATE TABLE tx_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    note_text VARCHAR(200) NOT NULL
);
```

Spring SQL initialization runs when the application context/datasource is initialized. The script does not re-run just because `TestTransaction.start()` opens a new transaction.

### 6.5. Complete JUnit Jupiter Test

File `src/test/java/com/example/txlab/TestTransactionBoundaryTest.java`:

```java
package com.example.txlab;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/tx-notes-schema.sql"
})
class TestTransactionBoundaryTest {

    @Autowired
    JdbcTemplate jdbc;

    // Under default JUnit Jupiter lifecycle, each test method has its own instance.
    // Track only the row that the current test intentionally committed.
    private String committedId;

    private String newId() {
        return "tx-" + UUID.randomUUID();
    }

    private void insert(String id, String note) {
        int affected = jdbc.update(
                "INSERT INTO tx_notes (note_id, note_text) VALUES (?, ?)",
                id, note);
        assertEquals(1, affected);
    }

    private int count(String id) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_notes WHERE note_id = ?",
                Integer.class, id);
        return value == null ? 0 : value;
    }

    private String readNote(String id) {
        return jdbc.queryForObject(
                "SELECT note_text FROM tx_notes WHERE note_id = ?",
                String.class, id);
    }

    // Ends the transaction per current flag; runs assertions with
    // no test-managed transaction active; always restarts the next T.
    private void endVerifyAndRestart(Runnable verifyOutsideTx) {
        TestTransaction.end();

        try {
            assertFalse(TestTransaction.isActive());
            verifyOutsideTx.run();
        } finally {
            TestTransaction.start();
        }
    }

    @BeforeTransaction
    void beforeInitialTransaction() {
        assertFalse(TestTransaction.isActive());
    }

    @AfterTransaction
    void cleanupCommittedRowAfterTest() {
        assertFalse(TestTransaction.isActive());

        if (committedId != null) {
            // Runs outside the final test transaction:
            // JdbcTemplate's DELETE commits via auto-commit.
            jdbc.update(
                    "DELETE FROM tx_notes WHERE note_id = ?",
                    committedId);
        }
    }

    @Test
    void startsWithRollbackFlagEnabled() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        String id = newId();
        insert(id, "uncommitted");
        assertEquals(1, count(id));

        // No commit: TestContext rolls back transaction at end of test.
    }

    @Test
    void changingFlagDoesNotImmediatelyCommitOrRollback() {
        String id = newId();
        insert(id, "pending");

        TestTransaction.flagForCommit();
        assertTrue(TestTransaction.isActive());
        assertFalse(TestTransaction.isFlaggedForRollback());
        assertEquals(1, count(id));

        // Flip flag back to rollback before the test ends.
        TestTransaction.flagForRollback();
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
    }

    @Test
    void canRollbackAndStartNewTransactionBeforeTestEnds() {
        String id = newId();
        insert(id, "will rollback");

        TestTransaction.flagForRollback();
        endVerifyAndRestart(
                () -> assertEquals(0, count(id)));

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
        assertEquals(0, count(id));
    }

    @Test
    void canCommitAndReadOutsideTheTransaction() {
        String id = newId();
        committedId = id;
        insert(id, "committed");

        TestTransaction.flagForCommit();
        assertFalse(TestTransaction.isFlaggedForRollback());

        endVerifyAndRestart(() -> {
            assertEquals(1, count(id));
            assertEquals("committed", readNote(id));
        });

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
        assertEquals("committed", readNote(id));
    }

    @Test
    void rollingBackSecondTransactionKeepsFirstCommit() {
        String id = newId();
        committedId = id;
        insert(id, "v1");

        TestTransaction.flagForCommit();
        endVerifyAndRestart(
                () -> assertEquals("v1", readNote(id)));

        // Now in T2, modify the data committed by T1.
        assertEquals(1, jdbc.update(
                "UPDATE tx_notes SET note_text = ? WHERE note_id = ?",
                "v2", id));
        assertEquals("v2", readNote(id));

        TestTransaction.flagForRollback();
        endVerifyAndRestart(
                () -> assertEquals("v1", readNote(id)));

        // Helper already opened T3, rolled back by default at end of test.
        assertTrue(TestTransaction.isActive());
        assertEquals("v1", readNote(id));
    }

    @Test
    void cannotStartNewTransactionWhileOneIsActive() {
        assertTrue(TestTransaction.isActive());

        assertThrows(
                IllegalStateException.class,
                TestTransaction::start);

        assertTrue(TestTransaction.isActive());
    }

    @Test
    void cannotEndOrChangeFlagWhenInactive() {
        // Roll back T1, then test the API while inactive.
        TestTransaction.end();
        try {
            assertFalse(TestTransaction.isActive());

            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::end);
            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::flagForCommit);
            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::flagForRollback);
        } finally {
            TestTransaction.start();
        }

        assertTrue(TestTransaction.isActive());
    }
}
```

**Guarantees in the example:**
- The SQL table exists before every test thanks to schema init on context startup.
- IDs use UUIDs so tests never depend on run order or leftover data from prior tests.
- Only tests that intentionally commit populate `committedId`.
- `@AfterTransaction` is invoked by Spring after the final test-managed transaction ends, so cleanup of the committed row is not rolled back with T2/T3.
- The helper uses `finally`: even if an assertion after `end()` fails, it still opens a fresh test transaction to keep the lifecycle clean.
- Neither `@Commit` nor `@Rollback(false)` is on the class, so T2/T3 start with default rollback.
- If the process is killed before the final callback or the DB connection fails, cleanup is not guaranteed; therefore tests should use an **isolated H2/DB**, never running against production.

### 6.6. Meaning of the Seven Test Cases

| Case | Well-founded evidence | Not proven |
|---|---|---|
| `startsWithRollbackFlagEnabled` | T1 active, default rollback | Row is committed |
| `changingFlagDoesNotImmediatelyCommitOrRollback` | Changing flag does not end T1 | `flagForCommit` persisted data durably |
| `canRollbackAndStartNewTransactionBeforeTestEnds` | T1 rolls back before test ends, T2 active and sees row gone | Independent service transactions also roll back |
| `canCommitAndReadOutsideTheTransaction` | T1 commits and row is readable outside test transaction | Replica or external system received the change |
| `rollingBackSecondTransactionKeepsFirstCommit` | T1 commits `v1`, T2 writes `v2` then rolls back so `v1` persists | Isolation/locking under concurrent load |
| `cannotStartNewTransactionWhileOneIsActive` | `start()` is not a nested transaction API | All transaction managers share the same propagation |
| `cannotEndOrChangeFlagWhenInactive` | `end/flag` require an active test transaction | `TestTransaction` works outside Spring TestContext |

There is no fixed business stdout: these tests use assertions and no `System.out.println`. Only claim runtime PASS after running the actual Gradle/Maven task and checking the report; the example is **designed to run**, not an execution log inside this article.

### 6.7. Running the Tests

Linux/macOS:

```bash
./gradlew test --tests "com.example.txlab.TestTransactionBoundaryTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.txlab.TestTransactionBoundaryTest"
```

Maven wrapper if the project has an equivalent `pom.xml`/dependencies:

```bash
./mvnw -Dtest=TestTransactionBoundaryTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=TestTransactionBoundaryTest test
```

Requires JDK 17+, the wrapper, and suitable JUnit Jupiter dependencies. Gradle reports are typically at `build/reports/tests/test/index.html`; Maven Surefire at `target/surefire-reports/`. Confirm **7 test methods are discovered and executed**, not `SKIPPED`, `NO-SOURCE`, or skipped by CI configuration.

## 7. Reading a Sequence of Commit T1, Rollback T2, Restart T3

```text
DB initially has no key X

Step   Transaction         Action                    DB sees
----   -----------         ------                    -------
 A     T1 active           INSERT X = "v1"          T1: v1
 B     T1 active           flagForCommit()           T1 still active
 C     T1 end()            COMMIT T1                 v1 committed
 D     Outside test tx     SELECT X                  v1
 E     T2 start()          Starts new transaction    T2: v1
 F     T2 active           UPDATE X = "v2"          T2: v2
 G     T2 active           flagForRollback()         T2 still active
 H     T2 end()            ROLLBACK T2               v1 still stored
 I     Outside test tx     SELECT X                  v1
 J     T3 start()          Starts new transaction    T3: v1
 K     Test ends           ROLLBACK T3               v1 still stored
 L     @AfterTransaction   DELETE X                  DB clean
```

B and G only toggle flags. **C and H are the real boundaries**, when the transaction manager terminates a transaction. Rolling back T2 cannot undo T1's completed commit.

During D/I, no *test-managed transaction* is active, yet calling a `@Transactional` service can cause the service to open its own Spring-managed transaction. Distinguish **test transaction inactive** from **the entire system having no transactions**.

## 8. @BeforeTransaction, @AfterTransaction, and JUnit Callbacks

Spring TestContext provides two out-of-transaction callbacks:

- `@BeforeTransaction`: runs **before the initial test transaction starts**.
- `@AfterTransaction`: runs **after the final test transaction ends**.

They differ from JUnit Jupiter's `@BeforeEach` and `@AfterEach`. Those method-level callbacks normally run **inside** the active test-managed transaction.

| Hook | Typical position | Best for |
|---|---|---|
| `@BeforeTransaction` | Before T1 | Verifying committed baseline |
| `@BeforeEach` | Inside T1 | Creating fixtures expected to roll back with the test |
| `@Test` | Inside T1, possibly with tx-free segments after `end()` | Running assertions, `end/start` across boundaries |
| `@AfterEach` | Inside final active transaction | Cleaning uncommitted fixtures |
| `@AfterTransaction` | After the final test transaction ends | Reading DB outside tx, cleaning committed data |

**Important:** `@BeforeTransaction` and `@AfterTransaction` are **test method lifecycle** hooks; they are not re-invoked every time a test manually calls `end()/start()`. In the example, checks between transactions are invoked directly inside `endVerifyAndRestart`; `@AfterTransaction` runs only at the very end.

If data was committed in T1, a `DELETE` inside `@AfterEach` belonging to T2 can be rolled back at the end of the test, leaving **T1's record intact**. That is why the sample test uses `@AfterTransaction` to clean up committed rows.

## 9. TestTransaction vs. @Commit and @Rollback

| Need | Suitable tool | What differs |
|---|---|---|
| Regular CRUD test, data should not remain after test | Default rollback | No `TestTransaction` needed |
| Want to commit when test method completes | `@Commit` or `@Rollback(false)` | Declarative; requires cleanup |
| Want to commit mid-test, then inspect data | `flagForCommit(); end(); ... start()` | Lets you observe DB after commit |
| Want to roll back mid-test, then continue in a new transaction | `flagForRollback(); end(); ... start()` | Cleanly separates T1 and T2 |
| Want production service to manage its own transaction | Test real service with appropriate tx setup | Do not let test tx mask service boundary |
| Want to open a transaction in application code | `TransactionTemplate` | Not a TestContext API |

`@Commit` changes the **default decision** of the test transaction; it does not commit before the test method finishes. `@Rollback(false)` has the same meaning. `TestTransaction.flagForCommit()` acts on the **current transaction**, and `end()` finishes that transaction mid-test.

When `TestTransaction.start()` creates the next transaction, the flag reverts to the **test's default**; if the test has `@Commit`, the new transaction may also commit at the end instead of rolling back. Therefore, check the flag on **every new transaction** rather than assuming T1's state.

Illustrative example:

```java
TestTransaction.start();
assertTrue(TestTransaction.isActive());
assertTrue(TestTransaction.isFlaggedForRollback());
```

The final assertion holds only for the **default rollback setup** of this lesson, not universally for every test.

## 10. TestTransaction, JPA Flush, and First-Level Cache

With `@DataJpaTest`, `EntityManager` typically keeps entities managed in the persistence context. `repository.save(entity)` does not guarantee SQL/constraints have executed immediately in every case. `entityManager.flush()` tells Hibernate to send pending changes to the database **without committing**.

```java
repository.save(entity);
entityManager.flush();            // Syncs SQL, does not commit
TestTransaction.flagForCommit();
TestTransaction.end();            // Ends transaction T1
TestTransaction.start();          // New transaction T2
```

This is an illustrative snippet inside a test with valid repository/entity/`EntityManager`, not a standalone file. If commit/flush hits a constraint violation or the transaction is already marked rollback-only, `flagForCommit()` **cannot force the database to ignore errors**. Never report "commit succeeded" before `end()` has actually completed.

**Common false-positive mistake:** calling `save` then `findById` on the same `EntityManager` can return the same managed entity from the first-level cache instead of performing a real `SELECT`. When verifying mapping/SQL, do `flush → clear → read`, or end and start a new transaction and read again; you can add a JDBC assertion to observe data outside the JPA cache.

For a transaction marked rollback-only after an exception, calling `TestTransaction.flagForCommit()` does not turn it back into a healthy transaction. Read the root cause and let it roll back; do not continue operating on the broken persistence context.

## 11. Boundaries That TestTransaction Does Not Manage

### 11.1. @Transactional(REQUIRES_NEW)

A service called **through a Spring proxy** may have:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(...) {
    // DB operation in a separate transaction.
}
```

This is an illustrative method, not a standalone Java file. When called mid-test during T1, `REQUIRES_NEW` can open an independent T2 and **commit T2**. Rolling back T1 will not delete the committed audit record. By contrast, `REQUIRED` usually joins T1 if using the exact same transaction manager/resource.

This `TestTransaction` lesson demonstrates committing/rolling back **test-managed transactions**; it does not replace genuinely testing service propagation.

### 11.2. Real HTTP Server, Async, Executors, Preemptive Timeouts

`@SpringBootTest(RANDOM_PORT)` runs HTTP handlers on a separate server thread. `@Transactional` on the test thread does not make the server thread share the same transaction. A committed server request requires its own cleanup and is not auto-rolled back by the test.

JUnit Jupiter's `assertTimeoutPreemptively` can run its callback on a different thread lacking the `ThreadLocal` transaction attached by Spring TestContext on the test thread. A JDBC write there can commit independently and pollute the test database. If you need a timeout without switching threads, use `assertTimeout` where appropriate (noting it does not interrupt a hung JDBC call).

Likewise, `CompletableFuture.runAsync`, custom executors, or Reactor schedulers do not inherit `TestTransaction` by default. `isActive()==false` on a background thread does not prove the test thread lacks a transaction.

### 11.3. Side Effects Outside the RDBMS

SQL rollback does not revoke Redis keys, Kafka events, sent emails, or written files. `TestTransaction` is not a distributed transaction coordinator. Tests with such side effects need dedicated isolation and cleanup.

## 12. Transaction Isolation and Two Independent Connections

A test reading data back **inside the same T1** does not prove external transactions can see it. To check:
- Commit visibility: `end()` T1, then read via JDBC outside the test transaction.
- Rollback: `end()` T1 with rollback, then read to confirm the row does not exist.
- Dirty reads/nonrepeatable reads/phantoms: require **two concurrent transactions/connections** and timing coordination, not merely a sequential T1 → T2 flow.

H2 can differ from PostgreSQL/MySQL in isolation levels, locks, deferred constraints, and deadlock behavior. If business logic relies on those details, use Testcontainers with a database close to production. `TestTransaction` helps open/end test transactions, yet cannot by itself prove all concurrency behaviors.

## 13. SQL Fixtures and Intentional Cleanup

Safe strategies:

- Put schemas in SQL initialization (as in the example).
- Create fixtures inside the test transaction so they roll back automatically.
- Use `@BeforeTransaction` when you need committed fixtures before T1 and have a deletion plan.
- Use `@AfterTransaction` to clean up committed test data.
- Use `@Sql` and `@SqlConfig(transactionMode=ISOLATED)` intentionally when a fixture needs a separate transaction; do not assume results will roll back with T1.
- Use UUIDs for keys, separating DB/schema/container per test suite if many tests commit.

Do not use `@DirtiesContext` as a way to delete committed data: it affects the context cache, not external databases. Never run `DELETE FROM all_business_tables` against a datasource you are not certain is a test DB.

In particular, an `@AfterEach` running inside T2 and then rolling back can perform a "phantom" cleanup (`DELETE` gets rolled back), leaving T1's data intact. Check the lifecycle callback and actual transaction state before deciding where cleanup belongs.

## 14. Common Errors and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| `IllegalStateException` on `start()` | Test transaction is still active | Only start after end; check `isActive` |
| `IllegalStateException` on `end()` | No active test transaction | Check `isActive`, annotations, thread |
| `flagForCommit()` yet DB still rolls back | Not ended, flag reverted, or rollback-only | Track flag, end, root cause |
| Rollback flag returns after `start()` | T2 uses the test's default rollback | Expected behavior in default setup |
| Commit flag active after `start()` | Test has `@Commit`/`@Rollback(false)` | Identify the exact default |
| Save/find test passes yet row is not committed | Same-T1 query sees uncommitted data | `end` then read outside transaction |
| `@AfterEach` cleans yet row remains | `DELETE` ran in T2 and rolled back | Clean up in `@AfterTransaction` |
| Failure when calling `end()` | Constraint/flush failure or transaction manager error | Do not assume commit succeeded before `end()` |
| Row leaks to next test | T1 committed, missing cleanup | Unique IDs, isolated DB, cleanup outside tx |
| `@BeforeTransaction` does not re-run per `start` | Hook follows test method lifecycle, not each transaction | Assert directly at boundaries |
| Test rollback does not remove service changes | `REQUIRES_NEW` or separate resource | Test propagation and cleanup |
| `RANDOM_PORT` test leaves DB row | HTTP server thread has separate transaction | Clean up against isolated test DB |
| `assertTimeoutPreemptively` leaks data | Callback runs on another thread | Avoid preemptive timeouts when writing DB |
| JPA `find` sees stale value | First-level cache | Flush/clear/reload in a new transaction |
| Multiple transaction managers | Listener picks wrong manager or ambiguous | Specify `@Transactional(transactionManager="...")` |
| R2DBC `Mono`/`Flux` ignores JDBC test tx | `ReactiveTransactionManager`/Reactor Context differs from `PlatformTransactionManager` | Test reactive separately with `TransactionalOperator`/`StepVerifier` |
| `@Sql` fixture does not commit as expected | `@Sql` shares test transaction | Configure `transactionMode` explicitly |
| Test "green" yet did not run | Test skipped/`NO-SOURCE` | Check test report |

## 15. Versions and API Scope

The example code above uses Spring Boot 3.5.x, importing:

```java
org.springframework.boot.test.autoconfigure.jdbc.JdbcTest
org.springframework.test.context.transaction.TestTransaction
```

In Spring Boot 4.x, `@JdbcTest` moved into a dedicated module, e.g. importing:

```java
org.springframework.boot.jdbc.test.autoconfigure.JdbcTest
```

For Boot 4 projects, use the `spring-boot-jdbc-test` test module matching the BOM and avoid mixing Spring 6/7 or Boot 3/4 dependencies. **`TestTransaction` itself belongs to Spring Framework TestContext** (`org.springframework.test.context.transaction` package), not an API defined by Spring Boot.

**R2DBC:** `TestTransaction` in this lesson is used with a JDBC/JPA-style `PlatformTransactionManager`, and cannot simply be used identically for a `ReactiveTransactionManager` attached to Reactor Context. For reactive applications, design dedicated transaction tests matching `TransactionalOperator` and publisher signals.

## 16. Checklist Before Trusting a Transaction Test

- [ ] Verified TestContext created a real test-managed transaction via `isActive()`.
- [ ] Identified the right `PlatformTransactionManager` when multiple datasources exist.
- [ ] Aware of the default rollback flag and the effect of `@Commit`/`@Rollback(false)`.
- [ ] Understood flags only change intent, while `end()` performs commit/rollback.
- [ ] After `end()`, checked the DB outside the test transaction, not just re-reading within T1.
- [ ] Only called `start()` after `end()`, restoring a transaction in `finally` if needed.
- [ ] After `start()`, checked the flag of the **new** transaction rather than assuming from T1.
- [ ] Included T1 commit / T2 rollback tests when the use case requires that boundary.
- [ ] With JPA, distinguished flush/commit and accounted for persistence caching.
- [ ] Committed data uses unique IDs, out-of-transaction cleanup, or an isolated DB/container.
- [ ] Did not rely on `@AfterEach` rollback to delete rows already committed from T1.
- [ ] Did not treat `@Transactional` tests as proof of production service transaction boundaries.
- [ ] Did not assume HTTP server threads/async threads use the test's `TestTransaction`.
- [ ] Avoided preemptive timeouts causing DB writes to run outside the transaction.
- [ ] When isolation/concurrency matters, tested on an appropriate DB dialect using two truly independent transactions.
- [ ] Executed JUnit tests and verified the executed test count in reports before claiming PASS.

## 17. Official References

- [Spring Framework — Transaction Management in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, programmatic `TestTransaction`, lifecycle callbacks, and preemptive timeout risks.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): signatures and preconditions of `start/end/flag`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest` and default rollback, `@SpringBootTest` with real server.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Framework — @BeforeTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html), [@AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-aftertransaction.html): out-of-transaction hooks.

**Conclusion:** `TestTransaction` is Spring TestContext's tool to intentionally **end T1 with commit or rollback, observe data at the boundary, and then open a new T2**. It does not replace the production transaction manager, does not "revive" an ended transaction, and end-of-test rollback does not delete previously committed data or non-SQL side effects. Use it when you need real evidence of commit/rollback, with a safe test database, `try/finally` to restore lifecycle state, and cleanup for committed records.