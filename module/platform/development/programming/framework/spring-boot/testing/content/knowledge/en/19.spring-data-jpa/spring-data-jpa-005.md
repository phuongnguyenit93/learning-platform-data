# Distinguishing Data in the Persistence Context from Data Written to the Database

## 1. The Problem: Seeing a New Value in Java Does Not Guarantee SQL Has Run

In Spring Data JPA, each `EntityManager` works with a **persistence context**. Entities in the *managed* state are tracked in memory. When you change a property of a managed entity, Java code sees the new value immediately; however, Hibernate/JPA may **not have emitted an `UPDATE` statement to the database yet** until a `flush` occurs.

Conversely, if a SQL statement has already been sent to the database, that **still does not mean the transaction has committed** or that other users/transactions can see the data. After `flush`, data has usually changed inside the current transaction, yet it can still be rolled back.

Confusing situations during testing:

- `repository.findById(id)` returns an entity holding the new value even though SQL `UPDATE` has not run; a green test does not prove the database row changed.
- `repository.save(entity)` returns an entity with an ID, leading the author to think the full INSERT/UPDATE was committed.
- `repository.saveAndFlush(entity)` executes a flush and the test assumes data is “saved permanently”; yet `@DataJpaTest`'s transaction still rolls back by default.
- Executing direct SQL via `JdbcTemplate` and then calling `findById(id)` still returns the **old value** because the entity is cached in the first-level cache.
- Calling `entityManager.clear()` before flushing discards changes that existed only in the persistence context.
- A JPQL/native SQL query can trigger *AUTO flush*, causing a “before flush” test to run SQL unintentionally.
- Using `@GeneratedValue(strategy = IDENTITY)` forces an early INSERT to obtain the ID; you cannot claim every `save()` keeps data solely in RAM.
- H2 tests pass while production PostgreSQL/MySQL differs in isolation, constraints, SQL dialect, or ID strategy.

**Core theme:** clearly separate three states: **entity in memory (managed state)** → **SQL synchronized to the database within the transaction (flushed state)** → **transaction committed (committed state)**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the persistence context/first-level cache and dirty checking.
2. Distinguish `persist`, `merge`, `save`, `flush`, `clear`, `refresh`, and `commit`.
3. Understand why `findById` or a JPA query does not always prove the database row currently matches the entity's contents.
4. Inspect **actual row state in the database within the same transaction** using `JdbcTemplate` without accidentally triggering a JPA flush.
5. Distinguish flush from commit, and test rollbacks and cross-transaction visibility.
6. Write Java 17+, Spring Boot 3.x, `@DataJpaTest`, H2, and JUnit Jupiter tests demonstrating these differences.
7. Avoid false-green tests caused by caching, auto-flush, IDENTITY, bulk queries, transaction rollback, or database environment differences.

## 2. What Is a Persistence Context?

A persistence context is the set of entities managed by a JPA `EntityManager`, along with an identity lookup keyed by entity type + primary key. Within a single context, one database row normally corresponds to **one managed entity instance** for that key.

Example inside a transaction:

```java
PurchaseRecord first = entityManager.find(
        PurchaseRecord.class, id);
PurchaseRecord second = entityManager.find(
        PurchaseRecord.class, id);

assertThat(first).isSameAs(second);
```

This is an **illustrative snippet**, not a standalone program; it assumes the `PurchaseRecord` entity, `entityManager`, and AssertJ import. It shows the persistence context's **identity map**: the second lookup can reuse the already-managed object without running a new SELECT.

### 2.1. First-Level Cache Is Not Second-Level Cache

- **First-level cache:** tied to `EntityManager`/persistence context, an essential part of JPA holding managed entities for the scope of that context.
- **Second-level cache:** an optional provider cache shared across persistence contexts; requires dedicated configuration/strategy.
- **Database buffer/cache:** internal RDBMS caching, not Java managed entity state.
- **Spring Cache/Redis:** a separate application caching layer, potentially unaware of whether an entity has been flushed/committed.

This lesson examines the **first-level cache**. Basic H2/Hibernate examples do not enable a second-level cache. When a project enables an L2 cache, `clear()` clears only the **first-level cache**; L2 caching rules still matter when ensuring fresh row reads.

### 2.2. Entity States to Understand

| State | Meaning | Does JPA Auto-Track Changes? |
|---|---|---|
| Transient/new | Java object not yet attached to a persistence context | No |
| Managed/persistent | Object inside the persistence context with managed identity | Yes, when dirty-checking conditions apply |
| Detached | Formerly managed, no longer managed by the context | No, until merged into a managed instance |
| Removed | Marked for deletion inside the context | Deletion is typically synchronized on flush |

`new PurchaseRecord(...)` does not write to the database. `entityManager.persist(entity)` adds a new entity to the context and schedules an INSERT (or inserts early depending on ID generation/constraints). `entityManager.clear()` detaches all managed entities; `entityManager.detach(entity)` detaches only a single object. `entityManager.refresh(entity)` reloads the **managed entity's** state from the database, potentially discarding unflushed changes on that object.

### 2.3. Dirty Checking and Write-Behind

With a managed entity:

```java
PurchaseRecord record = repository.findById(id)
        .orElseThrow();

record.setState("PAID");
```

Hibernate normally detects the change to `state` when a flush is needed; there is no need to call `save(record)` again just so Hibernate notices the setter. SQL statements can be queued/batched rather than executed after each setter.

However, do not overgeneralize: immutable/read-only entities, `@Transient` fields, special mappings, bytecode enhancement, read-only transactions, triggers, or custom persistence providers can alter how dirty checking/SQL emission behaves. What we verify is the **contract of the actual entity mapping and transaction**.

## 3. Three Milestones: RAM → Database Inside Transaction → Commit

Suppose the database initially contains a row:

```text
id = 10, state = "NEW"
```

A JPA transaction reads that row into a managed entity and calls a setter:

```text
T0: JPA SELECT row id=10
    Persistence context: state="NEW"
    Database (in transaction): state="NEW"

T1: managed.setState("PAID")
    Persistence context: state="PAID"
    Database row: may still be state="NEW"
    No UPDATE SQL at this step yet

T2: entityManager.flush()
    Hibernate dirty checking -> UPDATE state="PAID" WHERE id=10
    Persistence context: state="PAID"
    Database in current transaction: state="PAID"
    Transaction: NOT YET committed

T3a: transaction COMMIT
    Data is finalized per RDBMS semantics

T3b: or transaction ROLLBACK
    SQL UPDATE is undone; previous committed state remains
```

At T2, a JDBC query **on the same transaction/connection that ran the UPDATE** normally sees `"PAID"`. Yet a query on another transaction/connection may **not see it** due to isolation (e.g., `READ_COMMITTED`); you cannot infer external visibility merely because a same-transaction query sees the row.

**Key point:** `flush` is not `commit`. Flush can execute SQL, trigger constraint checks, and alter rows inside the transaction; commit is what finishes the transaction to make changes permanent.

### 3.1. A Three-Layer Mental Model

```text
┌──────────────────────────────┐
│ Java / JPA PersistenceContext│
│ Managed entity state="PAID"  │
└──────────────┬───────────────┘
               │ entityManager.flush()
               ▼
┌──────────────────────────────┐
│ Uncommitted RDBMS transaction│
│ UPDATE row: state="PAID"     │
└──────────────┬───────────────┘
               │ commit() or rollback()
               ▼
┌──────────────────────────────┐
│ Committed DB state           │
│ "PAID" if commit succeeds    │
│ "NEW" if rolled back         │
└──────────────────────────────┘
```

This diagram simplifies transaction isolation, triggers, locks, concurrency, and provider internals to highlight the **distinction between persistence context / SQL / commit**.

## 4. Exact Meaning of the APIs

| API | What It Can Do | What You Must Not Infer |
|---|---|---|
| `EntityManager.persist(entity)` | Attaches a new entity and schedules INSERT; may issue SQL early per ID strategy | All mappings/constraints were checked; transaction committed |
| `EntityManager.merge(detached)` | Copies detached object state into a managed instance; returns managed instance | The passed object itself became managed or SQL ran immediately |
| `JpaRepository.save(entity)` | Calls persist/merge per new-entity detection strategy | Every UPDATE/INSERT has definitely flushed and committed |
| `JpaRepository.saveAndFlush(entity)` | Saves then flushes pending changes | Transaction committed or other transactions see the data |
| `JpaRepository.flush()` | Flushes the corresponding persistence context | Ends the transaction |
| `EntityManager.flush()` | Synchronizes pending state via SQL (per provider/mapping) | Clears cache, refreshes state, or commits |
| `EntityManager.clear()` | Detaches all managed entities | Flushes before detaching, or deletes rows from DB |
| `EntityManager.detach(entity)` | Detaches one managed entity | Writes that entity's dirty changes |
| `EntityManager.refresh(entity)` | Reloads state from DB into a managed entity | Commits or preserves unflushed dirty state on the entity |
| `EntityManager.find(Entity.class,id)` | Looks up by primary key; may return managed instance from first-level cache | A fresh SELECT just ran |
| `JpaRepository.findById(id)` | Typically delegates to `EntityManager.find` | The DB row was just read directly, bypassing persistence context |
| `Transaction.commit()` | Finalizes transaction if successful; usually triggers flush in appropriate mode | Data was visible before commit under every isolation level |

Other APIs such as JPQL/criteria queries, bulk updates, native SQL, and `JdbcTemplate` have different flush/cache semantics. **Never use the word “query” as if every read operation behaved identically.**

### 4.1. “Save Succeeded” Does Not Equal “SQL Write Finished”

Spring Data JPA typically calls `persist(...)` for entities identified as new and `merge(...)` for entities identified as existing. How “new” is detected depends on id, `@Version`, the `Persistable` interface, or custom entity information. When using `IDENTITY`, INSERT may be sent **immediately on persist to retrieve the ID**; thus “save always stays purely in RAM” is false.

Conversely, when mutating an **existing managed entity**, Hibernate may wait until flush to send the UPDATE; thus “seeing the object change means the DB row changed” is also false.

### 4.2. SaveAndFlush Also Flushes Other Pending Changes

`saveAndFlush(entity)` does not selectively send SQL solely for the fields of the passed entity. Flush generally synchronizes **all pending work in the persistence context** of the transaction. Another dirty entity in the same context can also have its SQL executed during this flush.

Do not use `saveAndFlush` to try to “save only entity A” inside a transaction holding multiple dirty entities. Manage transaction boundaries and entity states deliberately.

## 5. Flush Modes: Why Can a Query Trigger SQL Earlier Than You Expect?

JPA defines standard flush modes:

- `FlushModeType.AUTO`: the provider ensures query consistency per flush rules; Hibernate may flush before a query affected by pending changes.
- `FlushModeType.COMMIT`: the provider may defer flushing until commit; visibility of pending changes to queries before commit **is not guaranteed identically across JPA providers**.

Hibernate also offers provider-specific modes such as `ALWAYS` and `MANUAL`/`EXPLICIT` depending on version/API. Do not copy Hibernate-specific flush modes to another JPA provider expecting identical behavior.

### 5.1. JPQL Queries Can Trigger a Flush

Example:

```java
PurchaseRecord record = repository.findById(id)
        .orElseThrow();
record.setState("PAID");

List<PurchaseRecord> found = entityManager
        .createQuery(
                "select p from PurchaseRecord p "
                + "where p.state = :state",
                PurchaseRecord.class)
        .setParameter("state", "PAID")
        .getResultList();
```

This is an **illustrative snippet** assuming `java.util.List` imports and a JPA context. With Hibernate `AUTO`, a query referencing an entity/table with pending updates normally causes Hibernate to **flush before the SELECT**. Seeing `PAID` in the query result **does not prove** the row had already been updated before the query started.

Therefore, when the goal is to distinguish RAM from SQL **before an explicit flush**, avoid running a JPQL query that mutates the state you are trying to measure.

### 5.2. Native Queries via EntityManager Are Not Harmless Probes Either

Some developers write:

```java
entityManager.createNativeQuery(
        "select state from purchase_records where id = :id")
        .setParameter("id", id)
        .getSingleResult();
```

assuming “native SQL surely will not auto-flush”. That is **not true in general**. When Hibernate is bootstrapped via JPA with `AUTO` flush mode, native SQL queries through `EntityManager` can still trigger auto-flush, even without explicit synchronized query spaces. Behavior depends on provider/version/bootstrap/query configuration.

**Solution in section 7's example:** use `JdbcTemplate`, executing SQL directly over the Spring-managed JDBC connection in the same transaction. Calling `JdbcTemplate.queryForObject(...)` does not instruct the Hibernate EntityManager to flush; this lets us measure the database row before and after an explicit JPA flush cleanly.

### 5.3. JDBC Differs from EntityManager, Yet Must Share the Transaction

For a JDBC query comparison to be meaningful:

1. `@DataJpaTest` must be running a Spring-managed test transaction.
2. `JdbcTemplate` uses the same DataSource/transaction connection able to join the active transaction (Spring uses connection utilities like `DataSourceUtils`).
3. The query reads the exact right table and record.
4. No JPA query/flush happens between mutating the managed entity and running the JDBC SELECT.
5. Do not manually open a separate connection outside the transaction and interpret its result as “same transaction state”.

When multiple transaction managers, multiple DataSources, or JTA are present, define boundaries clearly; this article's example intentionally uses **one H2 DataSource and one JPA transaction manager**.

## 6. Choosing the Right Test Technique for the Goal

| Testing Goal | More Reliable Verification Approach |
|---|---|
| Entity is attached to the persistence context | `entityManager.contains(entity)` |
| Entity instance is reused within one context | Assert object identity after `findById`/`find` |
| Dirty value changed in Java | Check getter on managed entity |
| Database received UPDATE in the **same transaction** | JDBC SELECT before/after `entityManager.flush()` |
| Force SQL to catch constraint errors early | `flush()` or `saveAndFlush()` |
| A fresh EntityManager must reload from DB | `flush(); clear(); find(...)` as appropriate |
| Database value changed via SQL outside JPA | JDBC UPDATE then `refresh(entity)` or `clear(); find(...)` |
| Data actually committed | End transaction with commit, observe in a new transaction, clean up |
| Data rolled back | `TestTransaction.end()` when flagged for rollback, inspect in a new transaction |
| Isolation between two transactions | Separate transactions/TransactionTemplate with proper DataSource and isolation |
| Production-like constraints/locking/dialect | Test on a real database engine, e.g., Testcontainers PostgreSQL |

### 6.1. A Test Checking Only “findById” Is Not Enough

Anti-pattern:

```java
PurchaseRecord record = repository.save(
        new PurchaseRecord("PO-100", "NEW"));
record.setState("PAID");

assertThat(repository.findById(record.getId()).orElseThrow()
        .getState()).isEqualTo("PAID");
```

This is a **counterexample**, lacking standalone imports/context. It can pass solely because the entity remains managed. Without `flush()`, `clear()`, or JDBC verification, the test **does not measure** whether an UPDATE reached the database.

How to improve it depends on the contract:

- To test dirty checking: `flush()` then JDBC query.
- To test loading state from a database query rather than the first-level cache: `flush(); clear(); findById(...)`.
- To test commit: leave the current transaction and read from a new transaction.
- To test mapping/queries: `@DataJpaTest` with H2 or an appropriate database; assert values and constraints.

## 7. Runnable Example: Spring Boot 3.x, JPA, H2, JUnit Jupiter

This test suite **intentionally compares two read paths**:

1. JPA managed entity / repository `findById`.
2. Direct SQL via `JdbcTemplate` inside the same transaction.

The sample uses one record with a status, a `JpaRepository`, Hibernate, and H2. No Web MVC/server, external network services, Testcontainers, or production DB access are needed.

**Environment:** Java 17+, Spring Boot 3.x (e.g., 3.4/3.5), Spring Data JPA + H2 runtime + Spring Boot Starter Test. Root package `com.example.jpaboundary`.

### 7.1. Dependencies

Gradle Groovy DSL — `dependencies` section for a project **already having** the Spring Boot Gradle plugin, dependency management, repositories, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — `dependencies` section of `pom.xml` using Spring Boot parent/BOM and a test plugin supporting JUnit Jupiter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
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
```

These are **snippets**, not full build files. Do not manually pin versions for Hibernate, Spring Data, or H2 when your project's Boot BOM manages them. H2 is used here to reproduce behavior; do not conclude from H2 tests that all PostgreSQL/MySQL triggers, isolation, sequences, and constraints behave identically.

### 7.2. File Structure

```text
src/
├── main/java/com/example/jpaboundary/
│   ├── JpaBoundaryApplication.java
│   ├── PurchaseRecord.java
│   └── PurchaseRecordRepository.java
└── test/java/com/example/jpaboundary/
    └── PersistenceBoundaryTest.java
```

In this example, all entities/repositories/tests sit under the root package containing `@SpringBootApplication`, allowing `@DataJpaTest` to discover configuration and scan JPA components accordingly.

### 7.3. Application Bootstrap

**File `src/main/java/com/example/jpaboundary/JpaBoundaryApplication.java`:**

```java
package com.example.jpaboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaBoundaryApplication.class, args);
    }
}
```

There is no custom `@ComponentScan` or manual `@EnableJpaRepositories`. `@DataJpaTest` limits scope to the JPA slice without loading unnecessary services/controllers.

### 7.4. JPA Entity

**File `src/main/java/com/example/jpaboundary/PurchaseRecord.java`:**

```java
package com.example.jpaboundary;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false)
    private String referenceCode;

    @Column(name = "state", nullable = false)
    private String state;

    protected PurchaseRecord() {
        // JPA requires an accessible no-arg constructor.
    }

    public PurchaseRecord(String referenceCode, String state) {
        this.referenceCode = referenceCode;
        this.state = state;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getState() {
        return state;
    }

    public void setState(String state) {
        this.state = state;
    }
}
```

**Why use IDENTITY while still teaching flush?** With IDENTITY, Hibernate typically must run INSERT early to retrieve the generated ID. Hence the tests **do not try to prove INSERT is deferred until flush**. Instead, they create a baseline row via `saveAndFlush()`, mutate an **existing managed entity**, and measure UPDATE before/after flush. This avoids overgeneralizing INSERT timing.

Table and column names are explicit, so JDBC queries in tests read `purchase_records.state` directly. There is no `@Version` to keep the sample simple; for optimistic locking, see section 11.

### 7.5. Repository

**File `src/main/java/com/example/jpaboundary/PurchaseRecordRepository.java`:**

```java
package com.example.jpaboundary;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRecordRepository
        extends JpaRepository<PurchaseRecord, Long> {
}
```

Spring Data provides the repository implementation in the JPA slice. `JpaRepository` includes `save`, `saveAndFlush`, `flush`, and `findById`; tests will invoke those exact methods.

### 7.6. Complete Test Class with 7 JUnit Jupiter Tests

**File `src/test/java/com/example/jpaboundary/PersistenceBoundaryTest.java`:**

```java
package com.example.jpaboundary;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class PersistenceBoundaryTest {

    @Autowired
    PurchaseRecordRepository repository;

    @Autowired
    EntityManager entityManager;

    @Autowired
    JdbcTemplate jdbcTemplate;

    private PurchaseRecord seeded(String referenceCode) {
        return repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));
    }

    private String sqlState(Long id) {
        return jdbcTemplate.queryForObject(
                "select state from purchase_records where id = ?",
                String.class,
                id);
    }

    @Test
    void managedValueChangesBeforeDatabaseUpdateIsFlushed() {
        PurchaseRecord managed = seeded("PO-101");

        managed.setState("PAID");

        assertThat(entityManager.contains(managed)).isTrue();
        assertThat(managed.getState()).isEqualTo("PAID");

        // JDBC shares the same Spring transaction; does not trigger JPA auto-flush.
        assertThat(sqlState(managed.getId())).isEqualTo("NEW");

        entityManager.flush();

        assertThat(sqlState(managed.getId())).isEqualTo("PAID");
    }

    @Test
    void findByIdMayReturnCachedManagedInstance() {
        PurchaseRecord managed = seeded("PO-102");
        Long id = managed.getId();

        managed.setState("PACKING");

        PurchaseRecord found = repository.findById(id)
                .orElseThrow();

        assertThat(found).isSameAs(managed);
        assertThat(found.getState()).isEqualTo("PACKING");

        // Returning a managed entity from findById does not prove SQL UPDATE.
        assertThat(sqlState(id)).isEqualTo("NEW");
    }

    @Test
    void directJdbcUpdateDoesNotRefreshManagedEntity() {
        PurchaseRecord managed = seeded("PO-103");
        Long id = managed.getId();

        int changed = jdbcTemplate.update(
                "update purchase_records set state = ? where id = ?",
                "SHIPPED",
                id);
        assertThat(changed).isEqualTo(1);

        // Current row changed inside the transaction.
        assertThat(sqlState(id)).isEqualTo("SHIPPED");

        // First-level cache still holds the managed entity's state.
        PurchaseRecord cached = repository.findById(id)
                .orElseThrow();
        assertThat(cached).isSameAs(managed);
        assertThat(cached.getState()).isEqualTo("NEW");

        entityManager.clear();

        // Entity is no longer managed; this lookup reloads from DB.
        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();
        assertThat(reloaded).isNotSameAs(managed);
        assertThat(reloaded.getState()).isEqualTo("SHIPPED");
    }

    @Test
    void clearWithoutFlushDiscardsPendingDirtyState() {
        PurchaseRecord managed = seeded("PO-104");
        Long id = managed.getId();

        managed.setState("CANCELLED");
        assertThat(managed.getState()).isEqualTo("CANCELLED");

        // DO NOT flush: new state exists only in the persistence context.
        entityManager.clear();

        assertThat(entityManager.contains(managed)).isFalse();
        assertThat(sqlState(id)).isEqualTo("NEW");

        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();
        assertThat(reloaded.getState()).isEqualTo("NEW");
    }

    @Test
    void flushThenClearCanReloadWrittenButUncommittedState() {
        PurchaseRecord managed = seeded("PO-105");
        Long id = managed.getId();

        managed.setState("PAID");
        repository.flush();
        entityManager.clear();

        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();

        assertThat(reloaded).isNotSameAs(managed);
        assertThat(reloaded.getState()).isEqualTo("PAID");
        assertThat(sqlState(id)).isEqualTo("PAID");

        // PAID was written via SQL, yet @DataJpaTest still rolls back.
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
    }

    @Test
    void refreshOverwritesManagedStateFromDatabaseRow() {
        PurchaseRecord managed = seeded("PO-106");
        Long id = managed.getId();

        int changed = jdbcTemplate.update(
                "update purchase_records set state = ? where id = ?",
                "RETURNED",
                id);
        assertThat(changed).isEqualTo(1);

        assertThat(managed.getState()).isEqualTo("NEW");

        entityManager.refresh(managed);

        assertThat(entityManager.contains(managed)).isTrue();
        assertThat(managed.getState()).isEqualTo("RETURNED");
    }

    @Test
    void flushedInsertIsUndoneByExplicitTestRollback() {
        PurchaseRecord managed = seeded("PO-107");
        Long id = managed.getId();

        assertThat(sqlState(id)).isEqualTo("NEW");
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        // End current transaction with ROLLBACK.
        TestTransaction.end();
        assertThat(TestTransaction.isActive()).isFalse();

        // Open another transaction to read data after rollback.
        TestTransaction.start();

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from purchase_records where id = ?",
                Integer.class,
                id);

        assertThat(count).isZero();
    }
}
```

**Expected result:** **7/7 tests pass** on a compatible Spring Boot 3.x/H2/Hibernate project with the stated dependencies. There are no `System.out.println` lines in the sample; the build tool prints startup logs and summaries, with no fixed application stdout to copy.

**How to interpret:** `managedValueChangesBeforeDatabaseUpdateIsFlushed` demonstrates the divergence between a managed object and the database row; `directJdbcUpdateDoesNotRefreshManagedEntity` shows the opposite direction (the database row changed while the managed object stayed stale). These two cases are two sides of the same issue.

### 7.7. Run Commands

Linux/macOS:

```bash
# If the project uses Gradle:
./gradlew test --tests "com.example.jpaboundary.PersistenceBoundaryTest"

# Or Maven:
./mvnw -Dtest=PersistenceBoundaryTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jpaboundary.PersistenceBoundaryTest"

# Or Maven:
.\mvnw.cmd "-Dtest=PersistenceBoundaryTest" test
```

Use **one** build tool matching your project. In a multi-module project, select the module containing the test. If Flyway/Liquibase or another custom datasource exists, isolate the sample in a small module/project or configure a proper test database; never point at a production database to test flush vs. commit.

### 7.8. Why Does the `seeded(...)` Helper Use saveAndFlush?

`seeded(referenceCode)` creates a baseline `NEW` state and calls `saveAndFlush(...)`. That starts the test from a row already sent to the database **inside the test transaction**, avoiding mixing “INSERT needed for ID generation” into dirty `UPDATE` measurements.

However, **the baseline has not committed**. When `@DataJpaTest` rolls back, both the baseline INSERT and subsequent UPDATEs are undone. The seventh test uses `TestTransaction.end()` to demonstrate this directly.

### 7.9. Why Not Use repository.findById to Measure the Row?

Within the same persistence context, `findById` normally relies on `EntityManager.find`. If the entity is already managed, JPA can return the **same object instance**. The second test verifies `isSameAs(managed)` while JDBC shows the row is unchanged due to missing flush.

When checking “did the database row change yet” **before flush**, use a read path that does not auto-flush JPA, such as JDBC in the same transaction. When checking “can a fresh EntityManager read the data”, call `flush()` then `clear()` to force JPA to drop the first-level cache and reload. Both test styles answer different questions.

### 7.10. Why Aren't TestTransaction.end/start the Default?

In `@DataJpaTest`, the test-managed transaction rolls back automatically after every method, so most tests do not need `TestTransaction.end()`.

The last test uses:

1. `isFlaggedForRollback()` confirms the test transaction follows the rollback policy.
2. `end()` ends the transaction immediately, rolling back per the flag.
3. `start()` opens a **new test transaction**.
4. JDBC `count(*)` confirms the old row is gone after rollback.

This test serves an educational purpose about transaction boundaries. Never call `TestTransaction` in production code; the class belongs to **Spring TestContext** and is for tests only. If a test uses multiple transaction managers or custom execution listeners, check which transaction manager is selected.

## 8. What Do the Seven Test Scenarios Explain?

| Test | Seen from JPA/Java | Seen from Database/Transaction | Lesson |
|---|---|---|---|
| Managed edit before flush | `state = PAID` | JDBC still `NEW` before flush, `PAID` after flush | Dirty state does not mean SQL ran |
| `findById` uses first-level cache | Returns same managed `PACKING` instance | JDBC still `NEW` | Repository `find` does not prove a SELECT/UPDATE just happened |
| JDBC UPDATE outside JPA | Managed stays `NEW` | JDBC already `SHIPPED` | Database changes do not auto-refresh managed objects |
| `clear()` without flush | Detached Java object holds `CANCELLED` | DB still `NEW` | Unflushed dirty state can be lost |
| `flush(); clear()` | Reloaded entity has `PAID` | Row is `PAID` in tx | SQL synchronized, not yet committed |
| `refresh(managed)` | Managed object flips from `NEW` to `RETURNED` | JDBC row is `RETURNED` | Refresh re-reads database, overwriting managed state |
| Explicit rollback | Sees `NEW` before rollback | Transaction after rollback counts 0 | Flush does not mean commit |

### 8.1. Do Not Confuse SQL Observation with External Visibility

The JDBC assertions share the **same Spring-managed transaction** as JPA. They prove SQL has/has not been synchronized to the database **within the current transaction**, not that a transaction in another process sees the row.

To prove external visibility, create a **truly separate transaction/connection**, specify the isolation level, and control commit/rollback timing. Avoid extrapolating from a single JDBC query running on the same connection.

### 8.2. When a Real Database Differs from H2

Hibernate generates different SQL per dialect. An RDBMS may defer constraint checking, enforce different isolation, acquire different locks, fire triggers, alter sequence/identity semantics, or exhibit distinct transaction snapshot behavior. H2 tests suffice for learning persistence context mechanics; before shipping a system on PostgreSQL/MySQL/Oracle, add integration tests on the real database engine for database-dependent rules.

## 9. Two Directions of Drift: Persistence Context Newer or Older Than DB

### 9.1. Case A: Entity Newer Than Database (Unflushed Dirty State)

```text
Java managed entity: state = "PAID"
RDBMS row:           state = "NEW"
Reason:              Setter changed RAM; UPDATE not yet flushed
Fix/test:            em.flush(); same-transaction JDBC SELECT
```

This is classic Hibernate write-behind behavior. Validation/mapping/constraint errors sometimes surface only at flush rather than at the setter or `save`. When you want to test DB errors early, force a flush at a meaningful assertion point.

### 9.2. Case B: Database Newer Than Entity (SQL Outside the Persistence Context)

```text
Java managed entity: state = "NEW"
RDBMS row:           state = "SHIPPED"
Reason:              JDBC/bulk SQL changed row; first-level cache unsynced
Fix/test:            em.refresh(managed) or em.clear(); em.find(...)
```

Changes coming from `JdbcTemplate`, native SQL bulk updates, JPQL bulk `UPDATE/DELETE`, or another transaction **do not automatically update managed Java objects** in the current persistence context.

When using Spring Data JPA bulk DML, `@Modifying(clearAutomatically=true, flushAutomatically=true)` helps synchronize beforehand and clear afterward; keep in mind that clearing can drop unflushed dirty changes if designed carelessly. Do not treat automatic clearing as a magic “sync database into every object reference I hold”.

### 9.3. Why Can Lost Updates Occur?

If a database row is updated directly via JDBC while the persistence context keeps the old state, and code then modifies the managed entity and flushes, Hibernate may issue an UPDATE based on the old snapshot and overwrite the out-of-band change. Depending on mapping, SQL generation, and concurrency, the result can be a **lost update** or another error.

Reduce the risk by:

- not mixing JDBC/JPQL bulk updates with managed entities without a clear/refresh policy;
- using `@Version`/optimistic locking when the domain requires it;
- scoping mutations inside well-defined transaction boundaries;
- testing concurrency and transaction isolation on a real RDBMS;
- avoiding overly long-lived EntityManagers, keeping persistence contexts small and well-scoped.

**Note:** `@Version` is not a cure-all for direct SQL: a JDBC UPDATE that omits version checks/increments can defeat optimistic locking assumptions. If external SQL updates the same table, establish explicit versioning/consistency rules.

## 10. Flush, Clear, and Refresh: Which Order Is Right?

### 10.1. Flush Before Clear When Preserving Dirty Changes

When you want to verify that data was written to the database:

```java
managed.setState("PAID");

entityManager.flush();
entityManager.clear();

PurchaseRecord reloaded = entityManager.find(
        PurchaseRecord.class, managed.getId());

assertThat(reloaded.getState()).isEqualTo("PAID");
```

This is an **illustrative snippet** inside a test transaction with a persisted baseline entity. Flush sends pending SQL; clear detaches managed objects; find after clear can issue a SELECT to build a new managed instance. The result reflects state **inside the transaction**, not committed.

If you reverse them:

```java
managed.setState("PAID");

entityManager.clear();
entityManager.flush();
```

with no prior flush, the object's dirty state has already been detached and may **no longer be a pending update**; flushing after clear will not rediscover the object to write it. Therefore `clear()` does not mean “save first then empty cache”.

### 10.2. Refresh When You Want State from the DB

```java
entityManager.refresh(managed);
```

tells JPA to reload database state into a valid managed entity; it can overwrite values held by the object, including unflushed changes. If the entity is already detached (after clear), `refresh` cannot be applied directly as with a managed entity; use `find`/`merge` appropriately.

**Never call refresh just to make a test pass** when production lacks refresh logic. If a bug stems from stale state, revisit transaction design or place refresh/clear where business logic calls for it.

### 10.3. Detaching a Single Entity

`entityManager.detach(entity)` detaches one object without flushing. If you keep the Java reference afterward, it retains its in-memory field values, yet JPA no longer dirty-checks it; subsequent mutations on the detached object do not propagate to the DB. `merge(entity)` can copy state from the detached object into a managed copy; you must **use the object returned by `merge`** when continuing work.

Do not confuse mutating a Java object after detaching with modifying the database row.

## 11. Constraints, Unique Keys, FKs, and Generated IDs: When Do Errors Appear?

### 11.1. Do Not Promise Every INSERT Is Deferred

With `@GeneratedValue(strategy=IDENTITY)`, the provider typically must execute INSERT to obtain the generated key. Thus:

```java
PurchaseRecord p = repository.save(
        new PurchaseRecord("PO-201", "NEW"));

assertThat(p.getId()).isNotNull();
```

does not prove “the database row doesn't exist yet”, nor does it prove commit. Having a populated ID and executing the INSERT must be analyzed by generator/provider/transaction. Our runnable sample does not depend on INSERT deferral timing.

Strategies like `SEQUENCE` or `TABLE` often allow deferring INSERT until flush, though sequence acquisition can still hit the DB early; do not assume “zero SQL ran” solely because INSERT was deferred.

### 11.2. Unique and NOT NULL Often Surface at Flush/INSERT

Suppose an entity has a unique constraint; Java code can construct two records with the same key without error until Hibernate flushes/the DB runs INSERT, at which point the RDBMS raises a constraint violation. With `IDENTITY`, an early INSERT can throw during `persist/save`. With deferred constraints (depending on the DB), the error may wait until commit.

Therefore, reliable constraint tests must:

1. Use an RDBMS suited for the constraint under test.
2. Control transactions and ID strategies consistently.
3. Explicitly flush at a sensible point to force SQL early **when the DB enforces constraints at statement time**.
4. Catch the right root cause/Spring/Hibernate exception translation; do not assume every DB throws the exact same exception class/message.
5. If a deferrable constraint checks at `COMMIT`, test the commit boundary separately.

### 11.3. Do Not Solve Everything by “Calling saveAndFlush Everywhere”

`saveAndFlush` helps surface database errors early, yet calling it on every operation can reduce batching efficiency and increase SQL round trips. In production, choose sensible flush boundaries, usually delegated to the transaction manager/provider. Use explicit flushes when you need immediate DB constraint evaluation, external synchronization, or test state verification.

## 12. @DataJpaTest, @Transactional, and Default Rollback

### 12.1. What Environment Does @DataJpaTest Actually Create?

In Spring Boot 3.5, `@DataJpaTest`:

- focuses on `@Entity`, JPA repositories, and related auto-configurations;
- can auto-configure an embedded database when compatible H2/HSQLDB/Derby is on the classpath;
- **runs each test inside a transaction by default and rolls back after the test**;
- provides `TestEntityManager` and `JdbcTemplate` when matching infrastructure is present;
- does not automatically load ordinary `@Service`/controller beans.

This keeps JPA tests fast with minimal external impact. However, when `repository.saveAndFlush(...)` succeeds and the test ends, **the transaction is rolled back** by default — meaning the row is not durably committed.

### 12.2. What Tool Is TestEntityManager?

Spring Boot provides `TestEntityManager` wrapping common JPA EntityManager test operations such as `persist`, `persistAndFlush`, `flush`, `clear`, `find`, and helpers depending on version.

In our runnable example, we inject `jakarta.persistence.EntityManager` directly to learn raw JPA semantics. If a project uses `TestEntityManager`, you must still distinguish:

- `persistAndFlush(entity)`: puts entity in context and flushes, **not commit**.
- `flush()`: sends pending SQL, does not clear.
- `clear()`: detaches, does not flush.
- `find(...)`: may return a managed entity from the persistence context.

### 12.3. Test Rollback Differs from Production Transactions

A transactional test rolled back by Spring TestContext after the method does not prove a production service rolls back in the same situation. Production transactions may:

- commit when the method finishes;
- roll back per `@Transactional` exception rules;
- open `REQUIRES_NEW` or transactions on other threads;
- execute on an HTTP server thread rather than the test thread;
- have different database timeouts/isolation.

In `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the HTTP client and embedded server run on separate threads/transactions. `@Transactional` on the JUnit test **does not automatically roll back** data committed by the server while handling a request. When moving from a repository slice to live HTTP tests, design separate cleanup/test schemas.

### 12.4. TestTransaction Helps Test Commit/Rollback Explicitly

Spring Test provides `TestTransaction.isActive()`, `isFlaggedForRollback()`, `flagForRollback()`, `flagForCommit()`, `end()`, and `start()`.

Notes:

- `flagForRollback()` only **marks** the transaction; it does not end it yet.
- `flagForCommit()` changes how the transaction will end; use cautiously with fixtures, as there is no automatic cleanup.
- `end()` ends it immediately per the current flag.
- `start()` begins a new test transaction after `end`; do not call it while a transaction is still active.

In the final test of section 7, the default rollback flag is verified before `end()`, and a new transaction is started to confirm the row disappeared. This sequence is safe for isolated H2 test data — **never run it on a production database**.

## 13. Observing from Another Transaction/Connection and Isolation

### 13.1. Flush Only Guarantees State Within the Relevant Transaction

Suppose transaction A executes:

```text
TX-A: UPDATE purchase_records SET state='PAID' WHERE id=10
TX-A: not yet COMMITted
```

Once TX-A flushes, the SQL UPDATE has run. Yet what TX-B sees when reading the row depends on isolation, snapshots, locks, timing, and the DB engine. Under standard `READ_COMMITTED`, TX-B does not see TX-A's uncommitted version; it may see the old version or block on conflicts, depending on query and engine.

Therefore:

- “Same-transaction JDBC reads PAID” **does not** prove it committed.
- “Another connection does not see PAID” does not automatically mean SQL didn't run; it may be isolation.
- “I enabled READ_UNCOMMITTED and saw PAID” also does not mean the transaction committed.

### 13.2. When Testing External Committed State

A commit/visibility check needs to:

1. Seed fixtures in a test DB/schema.
2. End the transaction with a real commit via the Spring transaction manager.
3. Open a new transaction/connection and check the value.
4. Clean up via another transaction rather than relying on rollback of the already-committed transaction.
5. When testing concurrency, coordinate threads/transaction boundaries deterministically to avoid races.

With in-memory single-process H2, you are measuring H2's behavior. If requirements involve PostgreSQL locking, write skew, or isolation anomalies, use real PostgreSQL or a container in CI.

### 13.3. Transaction-Scoped EntityManager in Spring

With Spring Data JPA and a standard transaction manager, an `EntityManager` injected by Spring is typically a proxy bound to the current transaction's persistence context. This explains why a repository and `@PersistenceContext EntityManager` inside the same transaction usually see the same managed entity, yet **forbids** assuming repositories in different transactions share the same persistence context.

If you switch threads, use different transaction propagation, or open a separate EntityManager, identity maps and visibility boundaries change. Tests should state transaction scopes explicitly.

## 14. Bulk JPQL Updates/Deletes Are a Common Cache Divergence Source

### 14.1. Bulk UPDATE Bypasses Managed Object Synchronization

Example:

```java
@Modifying
@Query("update PurchaseRecord p "
        + "set p.state = :state where p.id = :id")
int updateStateDirectly(@Param("id") Long id,
                        @Param("state") String state);
```

This is a **repository method declaration snippet**, not a standalone compilable file. JPA bulk UPDATEs hit the database directly and normally **do not update individual managed Java entities** already sitting in the persistence context.

If the same EntityManager holds `PurchaseRecord(id, state="NEW")` and a bulk UPDATE changes `state` to `"PAID"`, the managed object can remain `NEW`. `repository.findById(id)` may keep returning the stale instance from the first-level cache.

### 14.2. flushAutomatically and clearAutomatically

Spring Data JPA supports the options:

```java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
```

when annotating modifying query methods. General meaning:

- `flushAutomatically=true`: flushes the persistence context **before** running the query to avoid losing unsynchronized dirty state.
- `clearAutomatically=true`: clears the persistence context **after** the query so subsequent JPA lookups do not read stale managed entities.

However, **clear does not flush** existing changes unless properly configured and designed; enabling clear indiscriminately can discard unflushed dirty edits. Do not blindly apply both flags to every repository method; write tests to verify behavior and transaction policy.

### 14.3. Batch Deletes Can Also Diverge from the Cache

Methods such as `deleteAllInBatch(...)` or `deleteAllByIdInBatch(...)` issue batch DML, do not necessarily synchronize all managed entity states in the context, and can bypass entity lifecycle callbacks/cascade semantics that entity-by-entity deletion provides.

When using bulk deletes, consult the Javadoc for your Spring Data JPA version, account for flush/clear, and test relationships/constraints. Do not assume `findById` in the old context is reliable proof that rows were deleted in the DB.

## 15. SQL Logs: Knowing When Hibernate Actually Emits SQL

To investigate dirty changes and flush timing, enable logging in the **test environment**:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

These log settings target Hibernate 6 / Spring Boot 3; exact logger categories vary by version. `spring.jpa.show-sql=true` may format output outside your logging framework.

Expected observations when testing managed entity updates:

```text
Java Step                       SQL You May Observe
-----------------------------   -------------------------
saveAndFlush(new baseline)      INSERT (IDENTITY may INSERT early)
managed.setState("PAID")        not necessarily an UPDATE yet
JDBC SELECT before flush        SELECT state -> "NEW"
entityManager.flush()           UPDATE ... SET state='PAID'
JDBC SELECT after flush         SELECT state -> "PAID"
transaction rollback            ROLLBACK by Spring transaction manager
```

This is an **expected event timeline**, not literal Hibernate/Gradle stdout; exact SQL counts, syntax, bind order, and log format vary by Hibernate version, dialect, and batching.

**Do not use “saw UPDATE in logs” as proof of COMMIT.** SQL statements can run inside a transaction that later rolls back. Nor should you infer from absent logs that “no SQL ran” if logging is misconfigured or SQL ran over another JDBC path.

### 15.1. Do Not Log Sensitive Data in CI

`TRACE` binding can print parameter values including emails, tokens, or customer info. Use synthetic fixtures and enable this logger temporarily only for debugging; avoid enabling it broadly in production or uploading CI artifacts with sensitive data.

## 16. Common Pitfalls in JPA Testing

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `findById` sees new value, SQL row unchanged | Entity is managed, dirty state unflushed | Use JDBC before/after explicit flush, or flush+clear+find |
| `saveAndFlush` passes yet no row after test | `@DataJpaTest` rolls back by default | Distinguish flush vs commit; use TestTransaction/new tx when needed |
| JDBC UPDATE ran but JPA still reads old state | First-level cache holds managed entity | `refresh()` or `clear()+find`, redesign mixing JDBC/JPA |
| Clear loses edits | Dirty state unflushed | `flush()` before `clear()` if SQL must be written |
| “Before flush” test already sees new DB row | JPQL/native query auto-flush or early IDENTITY INSERT | Trace query paths and ID strategy; use same-tx JDBC to measure |
| `save()` returns ID so assumed committed | ID can be generated before commit | Measure across a new transaction boundary; ID is not commit proof |
| SQL UPDATE logged yet transaction rolled back | Flush emitted SQL, Spring test rolled back | Check rollback flag/test transaction |
| `@Transactional` test fails to roll back HTTP POST | Server runs in separate thread/transaction | Use separate DB cleanup/schema; do not rely on JUnit thread rollback |
| Constraint error appears at `flush` | DB checks on actual INSERT/UPDATE | Force flush where appropriate, verify DB engine |
| Unique constraint fails only at commit | Deferred constraint or transaction config | Test commit boundary on a real DB |
| Query result changes when adding `findAll()` | Hibernate AUTO flush | Place explicit flushes and check targeted SQL/queries |
| `EntityManager.refresh` throws | Entity is detached/missing or invalid transaction | Check managed state, PK existence, transaction |
| Second-level cache keeps data stale after clear | L2 cache enabled and still stale | Evict L2 per policy or test cache boundaries properly |
| H2 passes, PostgreSQL fails | Different dialect, constraints, locking/isolation, migrations | Use Testcontainers with production DB engine |
| Parallel tests fail randomly | Shared DB/schema/fixtures, fixed IDs, or tx isolation | Use unique fixtures and isolated test databases |
| Repository test suddenly needs service/HTTP | Slice scan broadened/explicit ComponentScan | Check `@DataJpaTest` and bootstrap configuration |
| Test runs without a transaction | `@Transactional` disabled, `NOT_SUPPORTED`, or custom listeners | Check `TestTransaction.isActive()` and annotations |
| `findById` stays stale after bulk update | Bulk SQL does not sync managed entity | Flush/clear or refresh, check `@Modifying` |
| Test green because it only asserts Java object | Didn't measure DB row/flush/transaction | Assert via JDBC or reload in a fresh context |

### 16.1. Layer-by-Layer Debugging Sequence

1. **Confirm the test actually ran?** JUnit Jupiter, Gradle/Maven test task, reports.
2. **Confirm a transaction is active?** `TestTransaction.isActive()`.
3. **Confirm the object is managed?** `entityManager.contains(object)`.
4. **Confirm the baseline DB row exists?** `saveAndFlush` fixture and same-transaction JDBC query.
5. **Check what SQL runs before/after flush?** Enable Hibernate SQL logs under control.
6. **Check whether your read method triggers a flush?** JPQL/native JPA queries can do this.
7. **Check whether caching affects reads?** `findById` vs. `clear()+find`.
8. **Check commit vs. rollback?** TestTransaction/transaction manager.
9. **If another transaction sees different data:** check isolation, snapshots, and locking.
10. **If production DB differs:** run integration tests with the production dialect/database.

A failure at step 2 (missing transaction) cannot be fixed by calling `clear()`. A failure at step 8 (rollback) cannot be fixed merely with `saveAndFlush()`.

## 17. Best Practices for Spring Boot Projects

### 17.1. Do Not Put Every Assertion Inside the Same Persistence Context

For checks verifying “written/read from the database”, use at least one explicit boundary:

- `entityManager.flush()` to emit pending SQL;
- `entityManager.clear()` to drop the identity map and reload fresh;
- JDBC queries in the same transaction to inspect SQL state;
- a new transaction when measuring committed state or isolation.

If a test only asserts on a managed object, name the test accurately for what it proves, such as `managedEntityIsUpdatedInMemory()`; do not name it `persistedToDatabase()` without verifying the DB.

### 17.2. Isolate Test Data, Avoid Order Dependencies

Use fixed but per-test unique reference codes in the sample; transaction rollback cleans up. In parallel setups or shared test DBs, use separate schemas/DBs or unique keys. Never use a production database to prove flush behavior, and avoid fixtures resembling real customer data.

### 17.3. Write Contract Tests at the Right Layer

- **Unit tests:** pure Java business methods, no JPA.
- **`@DataJpaTest`:** mappings, queries, dirty checking, flush/clear, JPA repository constraints.
- **`@SpringBootTest`:** coordinating services, transaction boundaries, persistence, and other beans.
- **HTTP integration tests:** requests through a server, separate threads/transactions; require DB cleanup.
- **Real database integration:** use the production engine when isolation/locking/SQL dialect matters.

Do not force all business tests into a full Spring Boot context when a repository slice suffices; equally, never assume a repository slice tests networking or production transaction topology.

### 17.4. Do Not Overuse flush/clear in Production

Flush/clear are invaluable for **testing** and specific production cases, yet:

- frequent flushes can defeat JDBC batching;
- clearing detaches all entities, requiring explicit management of lazy accesses and subsequent edits;
- refresh can overwrite pending edits;
- merging an outdated detached object can reintroduce stale state;
- explicit transaction commit/rollback belongs at service transaction boundaries, not scattered randomly across controllers/repositories.

The goal is understanding SQL timing to design cleanly, not calling `flush()` after every setter.

## 18. Exercises and Solutions

### Exercise A. When findById Returns the New Value

You just called `managed.setState("PAID")` and `repository.findById(id)` returns `PAID`. Can you conclude the database executed SQL UPDATE?

**No.** The entity may have been returned directly from the first-level cache. Read via same-transaction JDBC **before and after** explicit `flush()`, or flush+clear then reload depending on your goal.

### Exercise B. Is saveAndFlush a Commit?

You call `repository.saveAndFlush(entity)` in `@DataJpaTest`; same-transaction JDBC reads the new row. After the test, the row is gone from the database. Is that a contradiction?

**No.** `saveAndFlush` synchronizes pending SQL, yet `@DataJpaTest` rolls back the test-managed transaction by default. The transaction never committed; rollback undid the flushed SQL.

### Exercise C. clear Before flush

A baseline entity from the database has state `NEW`; the test calls `setState("SHIPPED")` and then `entityManager.clear()`. The next find returns `NEW`. Why?

**Because** dirty state lived only in the managed object that was detached before flush; `clear` does not write SQL automatically. To keep updates, flush before clearing.

### Exercise D. JDBC Newer Than Managed Object

After JPA reads state `NEW`, a JDBC UPDATE in the same transaction changes state to `PAID`. `repository.findById(id)` still returns `NEW`. Name two ways to force a reload.

**Answer:** call `entityManager.refresh(managed)` if the object is still managed, or `entityManager.clear()` followed by `repository.findById(id)`. Note both can discard pending Java-only edits, so use them only at intentional boundaries.

### Exercise E. JPQL Select Before Flush

Why can `select p from PurchaseRecord p where p.state='PAID'` cause subsequent JDBC reads to see `PAID` even though you never called `flush()`?

**Because** Hibernate AUTO flush may synchronize pending updates before a JPQL query referencing overlapping query spaces. Never use such a JPA query to measure “before flush”; use same-transaction JDBC without triggering a JPA flush.

### Exercise F. IDENTITY and INSERT

An entity is passed to `save(...)`, receives an ID, and an INSERT log appears before explicit flush. Is the ORM misconfigured?

**No.** IDENTITY typically requires an early INSERT to obtain the generated ID. Distinguish generator-driven INSERT timing from UPDATE timing on existing managed entities; both can remain uncommitted.

### Exercise G. Two Transactions and Visibility

TX-A flushed state `PAID` without committing. TX-B under `READ_COMMITTED` still reads `NEW`. Can you conclude flush didn't happen?

**No.** TX-B is not supposed to see uncommitted changes from TX-A; that is isolation behavior. To check flush, use same-transaction SQL reads or logs; to check commit, end the transaction and read from another transaction.

### Exercise H. Why Doesn't TestTransaction.end() Leave Data in the Example?

In the final test, `TestTransaction.isFlaggedForRollback()` is true. What does `end()` do? What is `start()` for afterward?

**Answer:** `end()` finishes and rolls back the transaction per the flag; `start()` opens a new test-managed transaction. JDBC `count(*)` in the new transaction returns 0 because the baseline INSERT rolled back.

### Exercise I. Bulk UPDATE Then repository.findById

A bulk JPQL update sets state to `PAID`, yet a managed entity remains `NEW`. Should you immediately call `save(managed)` to “synchronize” it?

**No.** Calling `save`/merge on a stale entity risks overwriting with old state. Identify the source of truth, flush pending changes when needed, clear/refresh at transaction boundaries, and use optimistic locking/versioning if concurrent updates occur.

## 19. QA Checklist for JPA Persistence Context Tests

- [ ] Clearly identified whether entities are transient, managed, detached, or removed.
- [ ] Know which EntityManager/persistence context owns the first-level cache.
- [ ] Separated Java state from SQL rows in the transaction and committed database state.
- [ ] Never treat getters or `findById` on a managed entity as proof SQL ran.
- [ ] Check `entityManager.contains(...)` when verifying managed state.
- [ ] Use `flush()` when testing constraint/SQL effects at a defined boundary.
- [ ] Understand `save` may persist/merge and `saveAndFlush` does not commit.
- [ ] Do not claim INSERT is always deferred when using IDENTITY generators.
- [ ] Do not use JPQL/native EntityManager queries to probe before-flush state if they can AUTO-flush.
- [ ] When using JDBC to measure DB state, ensure same transaction/connection and exact table name.
- [ ] Do not confuse same-transaction JDBC with external transaction visibility.
- [ ] `clear()`/`detach()` do not auto-flush; avoid accidentally dropping dirty changes.
- [ ] `refresh()` can overwrite Java-only edits.
- [ ] Understand bulk JPQL/native updates do not automatically update managed entities.
- [ ] Have a strategy to prevent lost updates/apply optimistic locking when mixing JPA and JDBC.
- [ ] `@DataJpaTest` transaction rollback behaves as expected.
- [ ] Use `TestTransaction` only when explicitly proving transaction boundaries.
- [ ] Do not confuse an HTTP server transaction with the test thread's transaction.
- [ ] For DB-dependent behavior, also test against the production database engine.
- [ ] Never use production data/secrets in tests or Hibernate SQL logs.
- [ ] Run tests on the exact class, JDK, Gradle/Maven Wrapper, and inspect test reports.

## 20. Conclusion

**Data in the persistence context, data flushed to the database, and committed data are three distinct state layers.** A managed entity can hold a new value before SQL UPDATE runs; a database row can change via JDBC/bulk SQL while the managed entity retains the old value; and flushed SQL can still be rolled back.

In Spring Data JPA, pick the measurement matching the question: **getters/contains** for managed state, **JDBC + flush** for in-transaction SQL state, **clear/refresh** to bypass the first-level cache, and **a fresh transaction after commit/rollback** to verify real persistence under isolation rules. When testing SQL dialects, unique constraints, transaction isolation, or production-like locking, use the target RDBMS rather than H2 alone.

## Official References

- [Hibernate ORM — User Guide, Persistence Context](https://docs.hibernate.org/stable/orm/userguide/html_single/#pc): entity states, managed/detached, dirty checking, refresh/clear, and identity map.
- [Hibernate ORM — User Guide, Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing): write-behind, AUTO/COMMIT flush, IDENTITY vs SEQUENCE, query-triggered flush, and SQL.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, transaction rollback, TestEntityManager, JdbcTemplate, and RANDOM_PORT caveat.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): save, persist/merge, and entity-is-new determination.
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html): `flush()`, `saveAndFlush()`, and batch operations.
- [Spring Data JPA — @Modifying API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html): `flushAutomatically`, `clearAutomatically` for bulk queries.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed transactions and rollback.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `flagForRollback`, `flagForCommit`, `end`/`start`.
- [Spring Boot 4 — Testing Data JPA](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): package changes for `@DataJpaTest` between Boot 3.x and 4.x; transaction/flush principles still apply per JPA/Hibernate version.