# Flushing to Observe SQL Errors Before a Transaction Ends — Spring Boot Testing

## 1. Real-World Problem: Tests Pass Green Even Though SQL Was Never Sent

In Spring Data JPA, the following code looks as if it has verified creating a record:

```java
repository.save(new BookingRecord("BK-100", "Mai"));
```

However, `save` **is not a guarantee that enough SQL was executed and the database accepted the record**. JPA has a **persistence context**: object changes can stay in `EntityManager`'s memory and only be synchronized into SQL when the ORM decides to flush, or when the developer calls `flush()`.

If a test runs inside a transaction that Spring TestContext **rolls back** right after the method, some unflushed changes may never be sent as SQL at all. As a result, assertions checking only Java objects will pass green, whereas production commits later fail due to a unique constraint, `NOT NULL`, foreign key, column length, or another SQL error.

One proactive way to make the test fail early:

```java
repository.save(new BookingRecord("BK-100", "Mai"));
repository.flush(); // Instructs the ORM to send pending SQL to the database.
```

Or:

```java
repository.saveAndFlush(
        new BookingRecord("BK-100", "Mai"));
```

**Yet `flush()` is not `commit()`.** The database may have executed the SQL inside the transaction while changes remain uncommitted and can still roll back. Moreover, some constraints configured as **deferred until commit** will not necessarily fail at flush time.

This lesson focuses on **transaction testing**: when to flush, where to observe SQL errors, how to write less flaky negative tests, and the limits of evidence that flush provides.

## 2. Learning Outcomes

After this lesson, you can:

1. Explain the `persistence context`, dirty checking, SQL action queue, and JPA/Hibernate flushing mechanism.
2. Distinguish `save`, `persist`, `merge`, `flush`, `saveAndFlush`, `clear`, `commit`, and `rollback`.
3. Recognize the default transaction rollback of `@DataJpaTest` and why flushing is needed before the test ends.
4. Build a Java 17 + Spring Boot 3.3 + Spring Data JPA + H2 example with a `SEQUENCE` primary key, without relying on early `IDENTITY` inserts.
5. Inspect pending INSERTs via direct JDBC queries, then observe them after `EntityManager.flush()`.
6. Write tests catching **unique constraint** errors from the database using `JpaRepository.flush()` or `saveAndFlush()`.
7. Write tests for dirty-checking UPDATEs failing at flush, not only INSERT tests.
8. Understand why a JPQL/native query can trigger an **automatic flush** under `FlushMode.AUTO`.
9. Distinguish JPA validation errors, SQL errors, Spring exception translation, and constraints deferred until commit.
10. Know when a test needs a **real commit**, a real database vendor, multiple transactions, or explicit cleanup.
11. Avoid continuing to use a broken transaction/persistence context after an SQL error.
12. Write assertions based on observable state rather than guessing exact SQL counts or absolute INSERT timing across all ID strategies.

## 3. Diagram of a Transaction and When Errors Are Detected

```text
JUnit test method, @DataJpaTest
          |
          v
Spring TestContext opens test-managed transaction
          |
          v
repository.save(entity) / entityManager.persist(entity)
          |
          +--> Entity becomes managed
          +--> Hibernate may queue pending INSERT/UPDATE/DELETE
          +--> No guarantee all SQL has run yet
          |
          v
entityManager.flush() / repository.flush()
          |
          +--> Hibernate dirty checking + SQL execution
          +--> Database may check NOT NULL / UNIQUE / FK
          +--> May throw an error right at flush
          |
          +--> NOT YET committed
          |
          v
JUnit assertions
          |
          v
Spring TestContext rolls back transaction after @Test
```

If you do **not** call explicit flush, Hibernate may auto-flush before a query or before commit depending on the flush mode. However, a test-managed transaction that simply rolls back when the method ends may never pass through commit. Do not count on Hibernate executing all pending SQL at some point before the test rolls back.

More importantly, **not every `save` defers its INSERT**. When using `GenerationType.IDENTITY`, Hibernate typically must INSERT early to obtain the ID key from the database. Therefore, the main example uses `SEQUENCE` to illustrate a case where the INSERT can remain queued until flush. Exact SQL-statement-level timing depends on the provider, ID generator, flush mode, queries, cascades, and actual configuration.

## 4. Distinguishing Operations Often Mistaken for Being the Same

| Operation | What it usually does | What it does not guarantee |
| --- | --- | --- |
| `EntityManager.persist(entity)` | Places a new entity in the persistence context, schedules persist | That SQL INSERT has completed |
| `JpaRepository.save(entity)` | Persists or merges depending on new/existing entity and detection strategy | Commit or that all SQL checks ran |
| `JpaRepository.saveAndFlush(entity)` | Saves and then requests flushing the persistence context | That the transaction committed |
| `JpaRepository.flush()` | Requests flushing all pending changes in the repository transaction's persistence context | Flushing only the single entity just saved |
| `EntityManager.flush()` | Synchronizes pending changes with the database inside the transaction | Rollback/commit |
| `TestEntityManager.persistAndFlush(entity)` | Persists entity then explicitly flushes for JPA tests | That Spring exception type always matches repository proxy |
| `EntityManager.clear()` | Detaches all managed entities from the persistence context | Deleting database rows |
| `EntityManager.refresh(entity)` | Reloads a managed entity's state from the database | Flushing prior pending changes in all providers/modes |
| `Transaction.commit()` | Ends the transaction successfully, typically flushing pending changes before commit | That changes outside the transaction roll back |
| `Transaction.rollback()` | Discards changes belonging to that transaction | Undoing changes committed by other transactions |

**Short summary:** `save` updates **JPA state**; `flush` synchronizes **SQL inside the transaction**; `commit` **completes** the transaction.

### 4.1. `save()` May Call `persist()` or `merge()`

Spring Data JPA determines whether an entity is new based on version, ID, `Persistable.isNew()`, or the corresponding identification strategy. For a new entity, the repository normally calls `EntityManager.persist`; for an existing entity, it may call `merge`.

With `merge`, the returned object can be a **different managed instance** from the original argument. Therefore, use the return value of `repository.save(...)` when working with the managed entity rather than assuming the passed-in variable is always the managed instance afterward.

The sample uses `@GeneratedValue(SEQUENCE)` so Spring Data detects new entities via `id == null` and cleanly demonstrates deferred INSERTs.

### 4.2. `flush()` Does Not Affect Only One Entity

When you call `repository.flush()`, Hibernate can flush **all pending changes** in the persistence context: all queued INSERTs, UPDATEs, DELETEs, and collection changes. Consequently, an exception from flush might come from **a different entity** than the one right before `flush()`.

Do not claim "this error is definitely from the last save line" solely based on where `flush()` sits. To isolate causes, use small fixtures, flush at clear checkpoints, and read the SQL/constraint name in the root cause.

## 5. Flush in Hibernate: Default AUTO and Exceptions

Hibernate, the typical JPA provider in Spring Boot 3.3, defaults to **AUTO** flush mode. According to Hibernate documentation, pending SQL may be flushed:

- Before transaction commit.
- Before a JPQL/HQL query that involves tables with pending changes.
- Before certain native SQL queries, depending on how Hibernate is bootstrapped and synchronized query spaces.
- When the application explicitly calls `EntityManager.flush()`, `Session.flush()`, or `JpaRepository.flush()`.

Therefore, **never say** "SQL only runs at commit." It can run at multiple points, including before queries or early due to ID generation.

### 5.1. A JPQL Query Can Trigger Flush

Illustrative example:

```java
entityManager.persist(new BookingRecord(
        "BK-200", "An"));

// A JPQL query touching the booking_records table
// may trigger AUTO flush before executing the query.
long number = repository.count();
```

In Hibernate `AUTO`, a query on a table with pending changes usually prompts the ORM to flush so query results reflect current state. Thus tests shaped like `save(); repository.count();` sometimes **accidentally exercise the INSERT**, yet relying on auto-flush does not state the test's intent clearly.

If the goal is explicitly "force the database to evaluate SQL errors before checking results," use an explicit `flush()`. Asserting exact flush timing per query/provider can be brittle; focus on database invariants.

### 5.2. FlushModeType.COMMIT

`jakarta.persistence.FlushModeType.COMMIT` asks the provider to defer flushing until commit when possible. Even then, JPA does not guarantee pending changes are always invisible to all queries before commit under this mode. An explicit `flush()` remains useful if a test needs to observe SQL at a checkpoint.

### 5.3. FlushModeType.AUTO

`AUTO` is the commonly used default. It synchronizes state before queries that need to see pending changes. However, **AUTO does not mean flushing before every query**. Hibernate can use query spaces/table overlap to skip unnecessary flushes.

### 5.4. Hibernate MANUAL and Read-Only Transactions

Hibernate also offers provider-specific flush modes like `MANUAL`; some read-only execution paths can reduce dirty checking/flushing. In Spring, `@Transactional(readOnly=true)` is mainly a hint/optimization and may be backed by read-only session behavior in Hibernate.

Do not use a read-only transaction and try to write an entity and measure lack of flushing as a business rule. If a test needs to write or verify constraints, use a writable transaction and explicit flush.

### 5.5. Native Queries

Native SQL queries can trigger flushes differently from JPQL depending on bootstrap APIs and synchronized query spaces. Hence `entityManager.createNativeQuery("select ...")` is not a portable method across JPA providers for proving "not flushed yet."

In the practical example, we use **`JdbcTemplate`** to observe rows already sent to H2. It runs JDBC directly without asking Hibernate to perform a JPA auto-flush before the query; we still keep in mind that a JDBC query in the same transaction sees flushed-yet-uncommitted changes.

## 6. Why Can Rollback Tests Hide SQL Errors?

With Spring Boot 3.3:

```java
@DataJpaTest
class BookingRepositoryTest {
    @Autowired BookingRepository repository;

    @Test
    void weakTest() {
        BookingRecord value =
                repository.save(new BookingRecord(
                        "BK-300", "Mai"));

        assertNotNull(value);
    }
}
```

This is a **counter-example pattern**, not a standalone complete test. `assertNotNull(value)` only confirms the repository returned an object. If the transaction then rolls back without flushing, SQL INSERTs/constraints may never have been evaluated by the database.

A tighter test:

```java
repository.save(new BookingRecord("BK-300", "Mai"));
repository.flush();

// You can also add a JdbcTemplate query or reload after clear.
```

**Do not misunderstand:** test-managed rollback is a benefit for isolation. The fix is not "disable rollback," but **actively flushing before asserting to force the SQL path to run** when that is what you want to test.

### 6.1. What Happens If an Exception Fires After @Test Ends?

If a test **commits** the transaction, the provider may flush and throw an exception at commit time. Yet with default `@DataJpaTest`, Spring rolls back the test-managed transaction; there is no guarantee all pending SQL will execute to uncover constraints.

Even when an exception appears during teardown/commit in another test configuration, the failure is harder to localize compared to `assertThrows(..., repository::flush)` right at the violating step.

### 6.2. Do Not Force Flush on Every Line

Flushing too often in production can:

- Increase the number of JDBC/database round trips.
- Break batching opportunities for INSERTs/UPDATEs.
- Alter Hibernate's optimized SQL execution order.
- Cause locks/contention earlier.
- Slow down the service without necessarily improving correctness.

In tests, explicit flush is useful at **observation checkpoints**, not as a rule to call after every setter/save.

## 7. SQL Errors You Should Test with Flush

Suitable scenarios:

| Risk | Where the error can occur | Testing approach |
| --- | --- | --- |
| Unique constraint | INSERT/UPDATE SQL (or commit if deferred) | Save two duplicate business keys, explicit flush |
| Foreign key constraint | INSERT/UPDATE/DELETE (or commit if deferred) | Create invalid reference; flush against vendor test data |
| NOT NULL constraint | ORM validation or database SQL | Use null input, check which layer throws |
| Column length/precision | JPA/driver/database | Test overflowing data, flush |
| CHECK constraint | Database statement/commit | Create violating value, flush, engine-dependent |
| SQL type conversion | JDBC/driver | Test invalid inputs and mappings |
| Unsupported SQL dialect | SQL execution | Run repository native query on the real vendor |
| Lazy batch of writes | Flush or commit | Intentionally flush to surface error before rollback |
| Trigger logic | Statement or transaction/commit | Test vendor database with real triggers |
| Deferred constraint | **Commit**, not necessarily flush | Test commit or `SET CONSTRAINTS IMMEDIATE` where supported |

**Not every validation failure is an SQL error.** If Bean Validation or Hibernate nullability checks reject an entity before JDBC sends a statement, the test can still be valid, yet you must label it **ORM/validation rejection**, not claim you tested a database constraint if SQL was never sent.

## 8. Java 17 + Spring Boot 3.3.0 + JPA + H2 Project

To illustrate that **INSERTs can be deferred until flush**, we use an entity with `GenerationType.SEQUENCE` instead of `IDENTITY`. Hibernate can fetch the ID value from the sequence on persist without **needing to INSERT the entity immediately**. The experiment compares direct `JdbcTemplate` queries before and after explicit flush.

The project contains:

- A Spring Boot application class.
- JPA entity `BookingRecord` with a unique business code and sequence generator.
- `BookingRepository extends JpaRepository`.
- One `@DataJpaTest` class with **5 methods**: deferred INSERT/flush, duplicate at flush, duplicate at `saveAndFlush`, dirty-check UPDATE at flush, and reload after clear.

All tests use **H2 in-memory** to run standalone; later sections clarify when to switch to PostgreSQL Testcontainers.

### 8.1. Directory Tree

```text
jpa-flush-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/flush/
    │   ├── FlushLabApplication.java
    │   ├── BookingRecord.java
    │   └── BookingRepository.java
    └── test/java/example/flush/
        └── BookingRepositoryFlushTest.java
```

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'jpa-flush-lab'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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

tasks.named('test') {
    useJUnitPlatform()
}
```

The Boot 3.3.0 BOM provides compatible Hibernate/JPA/Spring Data/JUnit versions; H2 is included only at **test runtime**. When deploying the application to production, you must configure a real production datasource/driver rather than treating the lab's `bootRun` as a complete deployment.

### 8.4. `FlushLabApplication.java`

**`src/main/java/example/flush/FlushLabApplication.java`:**

```java
package example.flush;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlushLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FlushLabApplication.class, args);
    }
}
```

Placing the application/entity/repository/test in package `example.flush` lets the Spring Boot slice locate the primary configuration and scan JPA entities/repositories properly.

### 8.5. `BookingRecord.java`

**`src/main/java/example/flush/BookingRecord.java`:**

```java
package example.flush;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "booking_records",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_booking_code",
                columnNames = "booking_code")
)
@SequenceGenerator(
        name = "booking_id_gen",
        sequenceName = "booking_id_seq",
        allocationSize = 1
)
public class BookingRecord {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "booking_id_gen")
    private Long id;

    @Column(name = "booking_code", nullable = false, length = 64)
    private String bookingCode;

    @Column(name = "customer_name", nullable = false, length = 100)
    private String customerName;

    protected BookingRecord() {
        // JPA requires a no-args constructor.
    }

    public BookingRecord(String bookingCode, String customerName) {
        this.bookingCode = bookingCode;
        this.customerName = customerName;
    }

    public Long getId() {
        return id;
    }

    public String getBookingCode() {
        return bookingCode;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void changeBookingCode(String newCode) {
        this.bookingCode = newCode;
    }
}
```

Intentional design choices:

- `@SequenceGenerator` + `GenerationType.SEQUENCE`: can retrieve an ID from the sequence without INSERTing the row yet.
- `uk_booking_code`: database unique constraint, allowing negative tests to force SQL failure.
- `@Column(nullable=false)`: describes the schema and supports provider nullability checks; the example focuses on **unique** constraints to avoid conflating Bean Validation/`NOT NULL` errors.
- `changeBookingCode(...)`: mutates a **managed entity** so Hibernate dirty checking generates an UPDATE at flush.
- The entity omits `@Version` and business services to keep flush behavior clear.
- Never assume the ID is always 1; sequences can increment across transactions even when rolled back.

### 8.6. `BookingRepository.java`

**`src/main/java/example/flush/BookingRepository.java`:**

```java
package example.flush;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookingRepository
        extends JpaRepository<BookingRecord, Long> {

    Optional<BookingRecord> findByBookingCode(String code);
}
```

`JpaRepository` provides `save`, `saveAndFlush`, `flush`, `findById`, and `delete`. The derived method `findByBookingCode` lets us check database state after clearing the persistence context.

## 9. Runnable Test: Observing INSERTs and Constraints Right at Flush

**`src/test/java/example/flush/BookingRepositoryFlushTest.java`:**

```java
package example.flush;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class BookingRepositoryFlushTest {
    @Autowired
    BookingRepository repository;

    @Autowired
    EntityManager entityManager;

    @Autowired
    JdbcTemplate jdbc;

    private long rowCount(String code) {
        Long count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM booking_records
                 WHERE booking_code = ?
                """,
                Long.class,
                code);

        assertNotNull(count);
        return count;
    }

    @Test
    void sequenceInsertAppearsInJdbcOnlyAfterFlush() {
        BookingRecord pending = new BookingRecord(
                "PENDING-1", "Mai");

        entityManager.persist(pending);

        assertNotNull(pending.getId());

        // Direct JDBC does not ask JPA to auto-flush the context.
        assertEquals(0L, rowCount("PENDING-1"));

        entityManager.flush();

        // Same test transaction sees its executed SQL write.
        assertEquals(1L, rowCount("PENDING-1"));
    }

    @Test
    void repositoryFlushReportsDuplicateUniqueKey() {
        repository.saveAndFlush(
                new BookingRecord("DUP-FLUSH", "Mai"));

        repository.save(
                new BookingRecord("DUP-FLUSH", "An"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.flush());

        // Do not continue querying in a failed transaction.
    }

    @Test
    void saveAndFlushReportsDuplicateAtCallSite() {
        repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "Mai"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new BookingRecord("DUP-CALL", "An")));
    }

    @Test
    void dirtyCheckingUpdateFailsDuringFlush() {
        repository.saveAndFlush(
                new BookingRecord("CODE-FIRST", "Mai"));

        BookingRecord second = repository.saveAndFlush(
                new BookingRecord("CODE-SECOND", "An"));

        // No repository.save(second) is needed:
        // second is a managed entity in this transaction.
        second.changeBookingCode("CODE-FIRST");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.flush());
    }

    @Test
    void flushThenClearCanReloadDatabaseState() {
        BookingRecord saved = repository.saveAndFlush(
                new BookingRecord("RELOAD-1", "Linh"));

        Long savedId = saved.getId();

        entityManager.clear();

        BookingRecord reloaded = repository
                .findByBookingCode("RELOAD-1")
                .orElseThrow();

        assertEquals(savedId, reloaded.getId());
        assertEquals("Linh", reloaded.getCustomerName());
        assertTrue(rowCount("RELOAD-1") == 1L);
    }
}
```

### 9.1. Test 1 Outcome: `persist` ≠ SQL INSERT Already Executed

`sequenceInsertAppearsInJdbcOnlyAfterFlush` intentionally uses:

1. A `SEQUENCE` entity ID so Hibernate can obtain the ID before INSERT.
2. `entityManager.persist(pending)`: the entity becomes managed and its ID is assigned from the sequence.
3. `JdbcTemplate` directly queries `booking_records` inside the **same test-managed transaction**, without calling a JPQL repository query, so it does not trigger Hibernate auto-flush.
4. Before explicit flush, the expected count is 0 under the lab's configuration.
5. `entityManager.flush()` tells Hibernate to send the INSERT.
6. After flush, JDBC in the same transaction reads the row with count 1.
7. The test ends; Spring TestContext rolls back, so the row **is not committed**.

**Scope of conclusion:** this is a demonstration for Hibernate/Spring Boot 3.3 + H2 + `SEQUENCE` under normal transactions. Do not turn it into an absolute rule that "`persist` never emits SQL before flush." With `IDENTITY`, the provider usually must INSERT early to obtain the generated ID.

### 9.2. Test 2 Outcome: Save First, Fail at `flush()`

`repositoryFlushReportsDuplicateUniqueKey`:

- First row `DUP-FLUSH` is `saveAndFlush`ed; the SQL INSERT executes inside the transaction without committing.
- Second row with the same business code is `save`d (with `SEQUENCE`, the SQL insert can stay in the action queue).
- `repository.flush()` sends the pending INSERT.
- H2 raises a unique violation, and Spring exception translation on the repository proxy typically converts it into `DataIntegrityViolationException`.
- `assertThrows` verifies the error occurs **at the flush checkpoint**, without waiting for rollback/test teardown.

If `@GeneratedValue(IDENTITY)` were used, the second `save` could throw early while inserting to fetch the ID. Then an assertion catching errors only at `flush` would become unstable; that is why the lab uses `SEQUENCE`.

### 9.3. Test 3 Outcome: `saveAndFlush` Combines Both Steps

`saveAndFlushReportsDuplicateAtCallSite` checks:

```java
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "An")));
```

It is often more readable than `save` + `flush` when associating an SQL error with saving a new entity. Keep in mind, however, that `saveAndFlush` can flush **other pending changes too** in the persistence context, not just the entity passed in.

### 9.4. Test 4 Outcome: UPDATE via Dirty Checking

With a **managed** entity, you do not need to call `repository.save(second)` after every setter:

```java
second.changeBookingCode("CODE-FIRST");
repository.flush();
```

Hibernate dirty checking detects that `bookingCode` changed and generates an SQL UPDATE at flush. The unique constraint rejects it because `CODE-FIRST` already belongs to the first row. This test proves SQL errors do not occur only on INSERTs—they can also occur on UPDATEs when an entity's state changes.

Note: calling a setter on a **detached object** after `entityManager.clear()` will not automatically queue an UPDATE like a managed entity; you must reattach/merge intentionally to test that case.

### 9.5. Test 5 Outcome: Flush Then Clear to Verify Real State

`entityManager.clear()` evicts managed entities from the first-level cache. The repository then queries by business code to reload an entity. Combining `flush` and `clear` avoids testing only in-memory Java objects.

However, in an application with a second-level cache or custom query cache, check the cache configuration if your goal is to prove a specific SQL round-trip.

### 9.6. Why Are There Both `EntityManager.flush()` and `JpaRepository.flush()`?

- `EntityManager.flush()` is the direct JPA API. Exceptions are usually JPA/Hibernate exceptions or related wrappers, not necessarily the same type as repository exceptions.
- `JpaRepository.flush()` goes through the Spring Data repository proxy, which applies Spring exception translation; tests can typically assert `DataIntegrityViolationException`.
- `TestEntityManager.flush()`/`persistAndFlush()` are convenient in `@DataJpaTest`, yet do not assume the exception type always matches the repository proxy across all call paths.

The lab uses `EntityManager` in the "observe SQL" test, and `JpaRepository.flush()` in negative tests to obtain the proper Spring data-access exception.

## 10. Running the Full Example

With JDK 17, a compatible Gradle Wrapper (e.g., Gradle 8.5), and reachable dependencies:

```bash
./gradlew test
./gradlew test --tests example.flush.BookingRepositoryFlushTest
./gradlew test --tests example.flush.BookingRepositoryFlushTest.sequenceInsertAppearsInJdbcOnlyAfterFlush
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.flush.BookingRepositoryFlushTest
```

**5 test methods are expected to pass** in this class given the right JDK/Gradle/dependencies. Negative tests **pass when the expected exception is caught by `assertThrows`**. There is no fixed business stdout; Gradle normally reports `BUILD SUCCESSFUL` when tasks succeed.

**Do not claim these tests were executed in writing this article**: the outcomes represent expected behavior for the example code. In a real project, run them in CI to confirm the exact Hibernate/H2 versions in use.

### 10.1. Reading SQL Logs When Needed

The sample sets `showSql=false` to keep logs concise. During debugging, you can enable logging in test configuration:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

This is a **reference** configuration for Hibernate 6 in Boot 3.3. Never enable bind logging in environments with passwords/PII or secrets, as bound parameter logs can expose sensitive data. Logger names vary across Hibernate versions.

When logging is enabled, observe the sequence:

```text
select next value for booking_id_seq
...   (no insert into booking_records yet, at the pre-flush checkpoint)
insert into booking_records ...
...   (at flush)
```

This illustrates **SQL ordering**, not exact stdout: exact SQL expressions, sequence syntax, bind parameters, and statement counts depend on the Hibernate dialect/config.

## 11. The `GenerationType.IDENTITY` Trap: INSERTs May Run Early

An example that often misleads learners:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

With `IDENTITY`, the database generates the ID during INSERT. Hibernate typically needs to send the INSERT immediately inside `persist`/`save` to know the ID, especially when a transaction is active and no deferred identity mode exists.

Hence a test like:

```java
repository.save(duplicateEntity);
assertThrows(
        DataIntegrityViolationException.class,
        repository::flush);
```

can **fail on the `save` line before reaching `assertThrows`**. That is not a bug in `flush()`; it is the ID generator affecting SQL timing.

**Better ways to write the test:**

- If you want to test **that the database rejects duplicates**, use `assertThrows(..., () -> repository.saveAndFlush(...))`; with some `IDENTITY` providers, the exception may still fire inside `save` within the lambda and be caught cleanly.
- If you want to demonstrate **SQL deferred until flush**, choose `SEQUENCE` or a strategy/provider where the operation can wait until flush.
- Never claim absolutely that "JPA only flushes SQL on commit" or "`save` never touches the DB."

## 12. Unique/NOT NULL Constraints vs. ORM Validation

A field like:

```java
@Column(nullable = false)
private String customerName;
```

can cause Hibernate to check nullability **before** issuing an SQL INSERT. If a test passes `null` and sees an exception, do not immediately call it a `NOT NULL` error **from the database**. Inspect the root cause/SQL logs and exact phase.

If using Jakarta Bean Validation:

```java
@NotBlank
@Column(nullable = false)
private String customerName;
```

this snippet requires `spring-boot-starter-validation` and `import jakarta.validation.constraints.NotBlank`. Bean Validation can run in lifecycle callbacks such as pre-persist/pre-update, rejecting the entity before SQL runs.

Because the focus of this lesson is **SQL errors at flush**, the runnable test uses a **real unique constraint in H2** rather than merely asserting validation annotations.

### 12.1. Column Length

`@Column(length=64)` is commonly used by Hibernate to generate DDL. Whether the DB rejects strings longer than 64 depends on the actual engine/schema and validation/provider. Do not treat an H2 test as complete proof that MySQL/PostgreSQL handle Unicode/string lengths identically.

### 12.2. Foreign Key Constraints

When an entity has a `@ManyToOne` with a foreign key, an invalid insert/reference can fail when SQL is flushed. However:

- The ORM may reorder INSERTs to satisfy FKs.
- Cascades may automatically persist referenced entities.
- Some DBs allow deferred foreign keys checked only at commit.
- H2, PostgreSQL, and MySQL differ in DDL/constraint enforcement.

If FKs are a critical invariant, test on the real database vendor with production FK configuration and assert errors at the right checkpoint.

## 13. PostgreSQL Deferred Constraints: Flush May Not Be Enough

This is an essential caveat when discussing SQL errors. PostgreSQL supports `DEFERRABLE INITIALLY DEFERRED` constraints. With a unique constraint deferred until the end of the transaction, calling `flush` can **send the INSERT/UPDATE successfully** while the constraint is checked **only at COMMIT**.

**PostgreSQL-only** SQL example, does not run on the H2 lab:

```sql
CREATE TABLE reservation_codes (
    id bigint PRIMARY KEY,
    public_code text NOT NULL,
    CONSTRAINT uk_reservation_codes
        UNIQUE (public_code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Inside a transaction:

```sql
BEGIN;
INSERT INTO reservation_codes(id, public_code)
VALUES (1, 'DUP');
INSERT INTO reservation_codes(id, public_code)
VALUES (2, 'DUP');

-- Both statements can complete
-- while the unique constraint is deferred.
COMMIT;  -- Violation is detected here.
```

**Do not claim `flush()` catches every SQL error.** It normally forces statement execution, yet when constraints are checked still depends on DB DDL. For deferred constraints, you must test a **real commit** or switch the constraint to `IMMEDIATE` inside the test transaction when the contract allows.

PostgreSQL example:

```sql
SET CONSTRAINTS uk_reservation_codes IMMEDIATE;
```

This command tells PostgreSQL to check the deferred constraint immediately upon switching modes; it can fail if data currently violates it. Do not treat it as a portable JPA command. If you need to protect commit-time behavior, vendor-specific tests are far more accurate than H2.

### 13.1. Why Does TestTransaction Matter?

Spring Test supports `TestTransaction` for test-managed transactions, e.g., controlling an explicit commit:

```java
repository.saveAndFlush(
        new BookingRecord("COMMIT-1", "Mai"));

TestTransaction.flagForCommit();
TestTransaction.end();

// Test-managed transaction has ended.
// Data may have committed; dedicated cleanup is required.
```

**This is an advanced snippet, not part of the runnable class in section 9.** It requires `import org.springframework.test.context.transaction.TestTransaction` and a test actually running inside a test-managed transaction. Once you truly commit, data is no longer auto-rolled back after the test; an ephemeral database or controlled cleanup is required.

For a transaction whose commit throws an exception, the test harness may need to wrap `TestTransaction.end()` inside `assertThrows` and ensure appropriate transaction reset/cleanup. Never continue running SQL inside a failed transaction.

## 14. Flush Does Not Commit: Visibility in Another Transaction

After `flush`, JDBC in the same transaction can see the newly written rows. Yet under typical isolation like `READ_COMMITTED`, a connection in **another transaction** cannot see those rows until commit.

```text
Transaction T1                      Transaction T2
--------------                      --------------
persist(row)
flush() -> INSERT executed
                                    SELECT row -> not visible yet
commit()
                                    SELECT row -> visible after commit
```

This is a **mental model** under `READ_COMMITTED` isolation without special behaviors; isolation/snapshot/locking levels can alter observed results. A test querying only with the same `EntityManager` after flush does not prove another transaction can read the data.

When business logic requires post-commit visibility:

- Perform a real commit in an isolated test.
- Open a second transaction/connection with the target isolation level.
- Observe state in the second transaction.
- Clean up committed data.
- If concurrency/deadlocks/locking are tested, use synchronization primitives rather than fixed sleeps.

**Do not infer from `flush()` that another HTTP API already sees the row.**

## 15. @DataJpaTest vs. @SpringBootTest: Transactions and Server Side Effects

### 15.1. @DataJpaTest

In the example, `@DataJpaTest`:

- Creates a Spring JPA slice.
- Provides a test-managed transaction per method by default.
- Rolls back after the method.
- Does not start an HTTP server.
- Can use an embedded H2 database.

Flushing in tests helps evaluate SQL before rollback.

### 15.2. @SpringBootTest with MockMvc

With:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
@Transactional
class BookingMockHttpTest {
    // MockMvc requests normally run on the test thread
    // and can join the test-managed transaction.
}
```

This is a configuration snippet, not the lab's runnable test class. With synchronous `MockMvc` requests, controller/service/repository code can run inside the test's transaction. However, if code spawns an async thread or a `REQUIRES_NEW` transaction, those side effects can escape rollback.

### 15.3. @SpringBootTest RANDOM_PORT

With:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class BookingLiveHttpTest {
    // Test client sends HTTP over socket to server thread.
}
```

Server requests typically run on a different thread/transaction from the JUnit method. `@Transactional` on the test thread **does not auto-roll back** DB commits made by server-side HTTP requests. You must clean up data according to the integration flow.

If a service calls `flush()` and then returns HTTP 201, transaction commit can still fail after flush due to deferred constraints or commit-time logic; HTTP tests should check status/state after the real request rather than relying only on unit assertions in the service.

## 16. Spring Exception Translation and Where to Put assertThrows

When Hibernate/JDBC throws a unique constraint violation:

- JDBC may throw `SQLException` or a vendor-specific subclass.
- Hibernate may wrap it as `org.hibernate.exception.ConstraintViolationException`.
- JPA may wrap it in `jakarta.persistence.PersistenceException`.
- A Spring Data `@Repository` proxy performs exception translation, typically converting it to `org.springframework.dao.DataIntegrityViolationException`.
- In some cases, the error surfaces at transaction commit rather than inside the repository method, so wrapper/type and stack location can differ.

Stable test example when using a repository proxy:

```java
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "An")));
```

If you call `entityManager.flush()` directly instead of through a repository, recognize that **the exception type differs**. Do not copy `assertThrows(DataIntegrityViolationException.class, entityManager::flush)` and blame a failure on the DB not enforcing the unique constraint.

### 16.1. Do Not Catch Too Broadly

```java
assertThrows(Exception.class, () -> repository.flush());
```

This can pass on any error — even configuration or connection errors. For constraint tests, assert the appropriate Spring data exception and, if needed, inspect the root cause/constraint name in a non-brittle way.

### 16.2. Why Not Catch the Exception and Continue Using the Transaction?

After a constraint violation:

- The Hibernate Session/persistence context may no longer be safe to continue using.
- PostgreSQL marks the transaction aborted; subsequent SQL statements are rejected until rollback.
- The Spring transaction interceptor may mark the transaction rollback-only.
- Test code continuing to execute SQL can trigger secondary errors that mask the original cause.

**Safe approach:** in a negative test, set up fixtures, execute the failing action, assert the exception, and end the method so Spring rolls back. Never try to "fix" the entity inside the same transaction after an exception and keep testing as normal.

## 17. Flush Helps Debug Tests, Yet Is Not a Universal Validation Tool

Errors that flush will not catch:

- Wrong HTTP content negotiation or JSON serialization.
- Business rules not implemented by the service.
- Async events not yet dispatched.
- External HTTP gateway failures.
- Database triggers firing at commit or deferred constraints.
- Transaction commit timeouts/serialization conflicts surfacing only at commit.
- Persistence written correctly while the API response is wrong.
- Domain validation that was never triggered.

Tests should be layered: unit tests for Java rules, JPA slices for mapping/SQL, and full integration tests for transactions/services/HTTP/external effects when needed. Do not treat `repository.flush()` as a "test everything button."

## 18. Hibernate Batching and Performance

Hibernate can batch JDBC statements when `hibernate.jdbc.batch_size` is configured. This changes when real SQL and errors occur:

- Multiple pending INSERTs can be sent in a single flush.
- A failure mid-batch can fail the entire batch.
- Stack traces may point to `BatchUpdateException` or SQL batch processing.
- SQL ordering may differ from the Java `persist` call order.
- `IDENTITY` ID generation typically restricts JDBC insert batching because generated keys are needed immediately.

For correctness tests:

1. Create minimal fixtures.
2. Call flush at the checkpoint.
3. Assert invariants/exceptions.
4. Do not assert exact SQL statement order unless part of the contract.
5. If testing batching performance, write dedicated tests with appropriate logs/metrics and data volume.

In production, **do not** add flush after every save just to make tests pass. Doing so breaks batching and increases round trips.

## 19. Bulk JPQL Update/Delete and the Persistence Context

Spring Data JPA `@Modifying` queries or `deleteAllInBatch` can bypass normal dirty checking/persistence context synchronization. Example:

```java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
@Query(
        "update BookingRecord b " +
        "set b.customerName = :name " +
        "where b.bookingCode = :code"
)
int updateCustomerName(
        @Param("code") String code,
        @Param("name") String name);
```

This is a **repository method snippet** for the extension section, not part of the runnable interface in section 8. It requires Spring Data `@Modifying`, `@Query`, `@Param` imports, and an active transaction.

- `flushAutomatically=true` requests flushing pending changes before the query.
- `clearAutomatically=true` clears the persistence context after the modifying query to prevent stale managed entities.
- Bulk updates can bypass per-instance JPA entity callbacks/dirty-checking behavior.
- Clearing while unflushed changes exist can discard changes; configure these flags intentionally.

Tests for bulk mutations should verify DB state after flush/clear and recognize that `@Modifying` does not mean commit.

### 19.1. Delete Ordering and FKs

A test creating parent/child entities and calling delete can hit an FK violation at flush if cascades/orphan removal/ordering are wrong. Hibernate attempts to order operations validly, yet only the real database enforces constraints ultimately. On DBs with deferred FKs, errors can wait until commit.

## 20. If You Want to Test Against Real PostgreSQL

H2 is handy for labs, yet does not replace PostgreSQL for:

- Deferred constraints.
- SQL dialects/indexes.
- Timestamps/precision/collation.
- Foreign key/unique/partial index behavior.
- Transaction isolation/locking/deadlocks.
- Trigger execution.
- Serialization failures at commit.
- Driver-specific error codes/wrapping.

When a test requires vendor-specific behavior, use PostgreSQL Testcontainers or an isolated real test database. With Spring Boot 3.3, `@DataJpaTest` may replace the test datasource with H2 unless replacement is explicitly disabled.

**Illustrative** pattern when PostgreSQL Testcontainers and dependencies are present:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class BookingPostgresTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

This snippet is **not in the runnable project in section 8**; it requires `spring-boot-testcontainers`, Testcontainers PostgreSQL/JUnit Jupiter, the PostgreSQL JDBC driver, Docker, and proper imports. When using a container, still assert the actual database product name so you do not pass against H2 by mistake, and run real schemas/migrations if that is the goal.

**Never** set `replace=NONE` in CI when the datasource could accidentally point to production; use only safe test credentials/URIs.

## 21. Two Different Test Styles: Immediate Constraints vs. Commit-Time Constraints

### Style A — Constraints Checked at SQL Execution/Flush

```java
repository.saveAndFlush(existing);
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(duplicate));
```

This fits most `NOT DEFERRABLE` unique/FK/CHECK constraints evaluated by the database at statement execution.

### Style B — Constraints Checked Only at Commit

```text
BEGIN
  INSERT row 1
  INSERT row 2 causing duplicate under deferred unique
  FLUSH: SQL sent, constraint may still not fail yet
COMMIT: database checks deferred unique and throws error
```

This case requires **performing a real commit** in a suitable database environment. If the test rolls back by default, it may never reach the phase where the constraint is evaluated. The H2 demo does not substitute for a PostgreSQL `DEFERRABLE` test.

### 21.1. TestTransaction with @AfterTransaction

Spring Test provides `@AfterTransaction` to observe state after the test-managed transaction finishes. However, this callback does not turn a rolled-back transaction into a commit; it only runs once the transaction ends. To test committed visibility, configure commit explicitly or control `TestTransaction`, then clean up.

**Do not** sprinkle `@Commit` or `@Rollback(false)` widely across a shared test database: they can leave data behind across test methods.

## 22. Debugging Flush with a Simple Check

When suspecting a negative test passed falsely because SQL never ran, ask three questions:

1. Is the entity managed, detached, or transient?
2. Did SQL execute yet? Was flush triggered by `IDENTITY`, a JPQL query, or another call before the JDBC check?
3. Is the constraint checked by the DB at statement execution or at commit?

You can structure the test like:

```java
// ARRANGE: create valid baseline data first.
repository.saveAndFlush(existing);

// ACT + ASSERT: force DB to evaluate the violating data.
assertThrows(DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(duplicate));

// End test and let the framework roll back.
```

This is a code pattern, not a standalone class. It is far easier to review than a test that saves a batch and asserts an object count without knowing whether SQL was ever sent.

### 22.1. Reading Root Causes

If the error message is `constraint violation`, inspect:

- The constraint name from the schema/migration.
- Which SQL statement was executing.
- JDBC vendor error code/SQLState.
- Exception wrapper from the repository/JPA layer.
- Which fixture data caused the duplicate/invalid state.
- Transaction isolation and DDL deferred status.

Never loosen the expected exception to `RuntimeException` just to make a test green.

### 22.2. Errors When Schema Does Not Exist

If a test fails with `Table not found`, the cause may be that `ddl-auto`/Flyway/Liquibase did not create the schema, not that flush is "broken." The sample uses `spring.jpa.hibernate.ddl-auto=create-drop` on ephemeral H2 to create tables/unique constraints. Never copy `create-drop` to a database holding data you want to keep.

### 22.3. When Seeing "Transaction is marked rollback-only"

Once a negative test triggers an SQL exception, the transaction may be marked rollback-only. Adding further repository operations after `assertThrows` can throw `UnexpectedRollbackException` or another driver error. End the method after the assertion and let test-managed rollback handle teardown.

## 23. Anti-Patterns to Avoid

### 23.1. Asserting the Object Returned by save Is Enough

`assertNotNull(repository.save(entity))` does not prove the database accepted the SQL. Add an explicit flush and database invariant assertions when SQL is the target.

### 23.2. Treating flush as commit

`repository.flush()` **does not** guarantee durability/visibility outside the transaction. To test committed data, you need a real commit and an independent transaction/connection.

### 23.3. Assuming flush Is Always Where Exceptions Throw

With `IDENTITY`, SQL can execute inside `save`; with deferred constraints, errors can arise at commit. Design tests around the actual behavior of the generator and database.

### 23.4. Catching All Exceptions

`assertThrows(Exception.class, ...)` is too broad: a test can pass green due to a missing table, null pointer, or network failure. Whenever possible, assert `DataIntegrityViolationException` or a meaningful invariant.

### 23.5. Continuing to Query After an SQL Error

This is unsafe with Hibernate's persistence context and PostgreSQL aborted transactions. End the negative test, let it roll back, and use a separate test for subsequent operations.

### 23.6. Enabling readOnly and Expecting Dirty Changes to Persist

`@Transactional(readOnly=true)` is an optimization hint with provider-specific behavior. Write tests must use a writable transaction and appropriate SQL flushing.

### 23.7. Calling flush After Every Save in Production

Often breaks JDBC batching and increases latency. Only use where technically required; never copy test flushes indiscriminately into business services.

### 23.8. Using H2 to Validate Deferred PostgreSQL Constraints

H2 does not fully reproduce PostgreSQL `DEFERRABLE` behavior. Test vendor-specific behavior on PostgreSQL.

### 23.9. Using @DirtiesContext to Roll Back

`@DirtiesContext` evicts the application context from cache; it does not automatically undo committed database rows. Use transactions/cleanup or ephemeral databases.

## 24. Quick Diagnostic Table

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Save succeeds yet flush throws unique violation | INSERT was deferred | Assert at flush, test DB unique constraint |
| Save already threw unique violation | `IDENTITY` or early auto-flush | Wrap the right call site; do not assume errors happen only at flush |
| Negative test passes with no SQL in logs | Maybe never flushed, or logging is off | Explicit flush, inspect DB/logs if needed |
| `flush` does not throw yet commit fails | Deferred constraints/commit-time checks | Test commit on vendor DB, clean up |
| `entityManager.flush()` throws Hibernate exception | Direct JPA API call | Distinguish from Spring repository exception translation |
| `repository.flush()` throws `DataIntegrityViolationException` | SQL constraint rejected | Assert contract exception type/root cause |
| `EntityManager.clear()` discards changes | Cleared before flush or detached state | Flush before clear if you want to keep changes |
| Query before flush already sees data | Hibernate `AUTO` flush or first-level cache | Do not infer SQL timing from a JPA query |
| JDBC query in same tx sees row after flush | SQL sent but not yet committed | Expected; check from another transaction if visibility is needed |
| Test rolls back yet ID grows across runs | Sequence/identity counters do not necessarily roll back | Do not assert fixed IDs |
| H2 test passes yet PostgreSQL fails | Dialect/constraints/isolation differ | Use PostgreSQL Testcontainers |
| Test fails with `Table not found` | Missing schema/migrations | Check `ddl-auto`/migrations |
| Test fails only in full suite run | Shared state/context/transactions | Unique fixtures, rollback/cleanup |
| Spring Boot slice missing service | `@DataJpaTest` does not scan regular services | Small `@Import` or full context |
| HTTP `RANDOM_PORT` test leaves data behind | Server transaction differs from JUnit transaction | Clean committed rows, do not rely on test-thread rollback |

## 25. Practice Exercises

### Exercise 1 — Observing Pending INSERT

Run `sequenceInsertAppearsInJdbcOnlyAfterFlush`. Log before/after flush and compare JDBC counts 0→1. Explain why `pending.getId() != null` does not prove the row has been INSERTed.

### Exercise 2 — Intentionally Removing Flush

In the duplicate test, temporarily remove `repository.flush()` and assert only two Java objects. Does the test still force the DB to evaluate the unique constraint? Fix it using `saveAndFlush` or explicit flush before ending.

### Exercise 3 — Changing SEQUENCE to IDENTITY

On a separate branch, change `GenerationType.SEQUENCE` to `IDENTITY` and run the INSERT timing observation test. `assertEquals(0, rowCount(...))` may turn red because INSERT runs early. Explain why tests must match the generator strategy.

### Exercise 4 — UPDATE Failure, Not Just INSERT

Run `dirtyCheckingUpdateFailsDuringFlush`. Try removing `second.changeBookingCode("CODE-FIRST")`; does flush still fail with unique violation? Try `entityManager.clear()` before the setter and analyze the managed/detached difference.

### Exercise 5 — Flush Does Not Commit

In an advanced test using H2 `READ_COMMITTED`, query from a second transaction before and after the first transaction commits. Assert visibility matching isolation, and clean up. Do not share the same `EntityManager` for both and call it an inter-transaction check.

### Exercise 6 — PostgreSQL Deferred Constraint

In a PostgreSQL container, create a `DEFERRABLE INITIALLY DEFERRED` unique constraint. Insert two rows with duplicate codes, explicitly flush, then commit. Identify which phase raises the error. Do not expect H2 to reproduce this.

### Exercise 7 — Queries That Auto-Flush

Use Hibernate `AUTO` and a JPQL query on the same table after `persist`. Compare with a `JdbcTemplate` query before explicit flush in the `SEQUENCE` test. Explain why you should not rely on JPA queries to measure exact SQL timing.

### Exercise 8 — Bean Validation vs. SQL

Add `@NotBlank` to `customerName` and the validation starter. Test blank/null input; read the root cause to distinguish pre-SQL validation violations from database unique violations.

### Exercise 9 — Batch Operations

Insert multiple entities via `saveAll` then `flush`, enabling Hibernate batch size in a test environment. Observe SQL logs/batch behavior. Do not assume each INSERT order matches Java call order.

### Exercise 10 — Full Integration with Spring Boot

Create a `@Transactional` service saving a booking and a POST controller endpoint. Use `@SpringBootTest(MOCK)`/`MockMvc` for HTTP and JPA logic, then a `RANDOM_PORT` live test to verify commit and data visibility after the response. Use separate cleanup for live-test server-side writes.

## 26. Checklist for Reviewing an SQL Constraint Test

- [ ] Do I know whether the test uses `@DataJpaTest` default rollback or a real commit?
- [ ] Do I know whether the entity is new/existing and its managed/detached persistence context state?
- [ ] Do I distinguish `save`/`persist`, `flush`, and `commit`?
- [ ] Does the SQL constraint test include an explicit flush at a meaningful checkpoint?
- [ ] Am I avoiding `assertNotNull(save(...))` as proof that SQL was checked?
- [ ] Has the ID generation strategy been considered (`SEQUENCE` vs. `IDENTITY` timing)?
- [ ] When reading from the DB, is there an appropriate flush/clear/reload or direct JDBC query?
- [ ] Am I avoiding concluding that flush committed or that another transaction already sees the data?
- [ ] Am I aware that `AUTO` queries can trigger early flushes?
- [ ] Do negative tests catch a sufficiently specific exception rather than generic `Exception`?
- [ ] Do I avoid issuing further queries in the transaction after an SQL failure?
- [ ] Does the test database have real constraints/schemas matching the production contract?
- [ ] If the DB uses deferred constraints, is there a test with a real commit?
- [ ] Is the test prevented from accidentally hitting a production database or running `create-drop` outside a sandbox?
- [ ] If testing on H2, do I avoid extrapolating PostgreSQL-specific behavior?
- [ ] Am I avoiding adding flushes throughout production code just so tests "see SQL"?
- [ ] For bulk updates/deletes, are flush/clear and persistence context effects handled intentionally?
- [ ] With a live HTTP server, do I avoid relying on the JUnit test transaction to roll back server writes?
- [ ] Does the test suite cover both reasonable positive fixtures and negative fixtures?
- [ ] Are expected results based on database invariants rather than fragile SQL log text?

## 27. Decision Diagram

```text
What needs to be tested?
     |
     +-- Java business logic?
     |     -> Plain JUnit / Mockito, no database needed.
     |
     +-- Repository mappings, SQL constraints?
     |     -> @DataJpaTest + test DB.
     |        save/persist -> explicit flush -> assert.
     |
     +-- Specific SQL timing?
     |     -> Account for SEQUENCE vs IDENTITY, AUTO flush, batching.
     |        Use direct JDBC observation when appropriate.
     |
     +-- Deferred constraints / committed data?
     |     -> Vendor DB + real commit + cleanup.
     |
     +-- HTTP request + service transaction + persistence?
           -> Appropriate @SpringBootTest and isolated test DB;
              RANDOM_PORT when real networking is needed.
```

**Core message:** In a JPA test with rollback, **`save()` does not guarantee SQL has run**. Calling **`flush()` or `saveAndFlush()` at a checkpoint** forces Hibernate to synchronize pending changes to the database so many constraint/SQL errors surface right inside the test body. Still, **flush is not commit**, and does not replace tests for deferred constraints, transaction visibility, or production database behavior. The right way to test is to state what you want to observe, flush intentionally when needed, and use the right engine and transaction boundary.

## 28. Official References

- Spring Boot 3.3 — `@DataJpaTest`, default transaction rollback: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — TestContext transaction management, `TestTransaction`, rollback: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Data JPA — `JpaRepository.flush`, `saveAndFlush` Javadoc: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Hibernate ORM 6 — Flushing, AUTO/COMMIT/MANUAL, IDENTITY timing: https://docs.jboss.org/hibernate/orm/6.5/userguide/html_single/Hibernate_User_Guide.html
- Jakarta Persistence 3.1 — EntityManager `flush`/`FlushModeType`: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager
- Spring Data JPA — Transactions: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Data JPA — Modifying queries and `clearAutomatically`/`flushAutomatically`: https://docs.spring.io/spring-data/jpa/reference/jpa/modifying-queries.html
- PostgreSQL — `SET CONSTRAINTS` and deferred checking: https://www.postgresql.org/docs/current/sql-set-constraints.html
- PostgreSQL — `CREATE TABLE` unique/foreign key deferrable: https://www.postgresql.org/docs/current/sql-createtable.html
- JUnit Jupiter — Assertions and lifecycle: https://docs.junit.org/current/user-guide/
