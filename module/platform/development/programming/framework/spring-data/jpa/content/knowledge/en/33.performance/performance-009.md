# Measuring Flush Cost, Dirty Checking, and Redundant Updates in Spring Data JPA

## 1. Objectives and Cost Model

When optimizing an application built with **Spring Data JPA + Hibernate**, you need to distinguish three questions:

1. **How much work does Hibernate spend checking for changes?** This is *dirty checking* across managed entities in the *persistence context*.
2. **How long does a single `flush()` take?** Flushing synchronizes pending changes into SQL in the proper order. A flush may emit zero `UPDATE` statements.
3. **How many updates must the database process, including redundant ones?** Dispatched SQL can incur network, parse/execute, locking, WAL/redo log, index maintenance, replication, or trigger costs.

Do not equate `repository.save()`, `entityManager.flush()`, and `COMMIT`:

| Operation | Primary effect | What to measure |
| --- | --- | --- |
| Modifying a *managed* entity's attribute | Changes state in memory; Hibernate typically defers SQL until flush | Dirty-checking cost and number of records actually modified |
| `save(entity)` in Spring Data JPA | Calls `persist` or `merge` based on how new/existing entity is determined; not an immediate SQL `UPDATE` in every case | Generated SELECT/MERGE, SQL timing, whether entity is already managed |
| `flush()` | Synchronizes pending operations with the DB, **without committing the transaction** | Flush duration, flush count, SQL count, and entity updates |
| `saveAndFlush(...)` | Saves and requests an immediate flush inside the transaction | Extra flush cost, potential loss of batching effectiveness |
| `commit` | Ends the transaction; normally flushes remaining pending changes before committing | Overall transaction duration and outcome |
| JPQL bulk `UPDATE` or native `UPDATE` | Sends an update SQL statement directly, bypassing per-entity dirty checking | Actual DML executed, DB locks, row count, stale data in persistence context |

**Principle:** `flushCount > 0` does not imply `UPDATE > 0`; conversely, a JPQL bulk update can execute SQL even though Hibernate's `entityUpdateCount` statistic does not increment like per-entity updates do.

## 2. How Does Hibernate Dirty Checking Work?

Inside a transaction:

```text
SELECT account -> MANAGED entity in persistence context
                        |
                        v
               modify one or more fields
                        |
                        v
             flush / auto-flush / commit
                        |
                        v
          Hibernate determines dirty state
                  /                  \
              not dirty             dirty
                  |                    |
             no UPDATE          generates SQL UPDATE
                                       |
                                  JDBC -> database
```

With *snapshot*-based change tracking, Hibernate retains the loaded state and compares it against current values at flush time. Hibernate also supports bytecode-enhanced change tracking mechanisms, so you should not assume every version/configuration compares all attributes identically. The work involved in dirty checking depends on managed entity count, attribute count, data types, collections, and enhancement configuration.

Key points to remember:

- `new`, `managed`, `detached`, and `removed` entities follow distinct rules. Automatic dirty checking primarily applies to **managed** entities in the current persistence context. Mutating a detached object does not automatically generate SQL; `merge` has its own rules and costs.
- For simple attributes, reassigning the **same value** typically does not generate an `UPDATE` on flush. However, setters, custom types, callbacks, collections, or change-tracking mechanisms can influence actual behavior; verify via SQL.
- When an entity is genuinely dirty, Hibernate by default may generate an `UPDATE` setting all updatable columns, even unchanged ones. `@DynamicUpdate` can restrict `SET` columns, at the cost of producing more SQL shapes and potentially reducing statement reuse/batching; apply only after measuring.
- Dirty checking and flushing are not one query per entity. Hibernate may inspect many entities in memory and emit SQL for only a few. Conversely, native SQL/JPQL bulk statements can update rows without passing through entity dirty checking.
- `@Version` supports optimistic locking when the ORM updates entities; bulk JPQL/native updates typically **do not automatically increment version** and do not sync already-loaded entities, so you must handle that explicitly when using bulk DML.

**Example:** 1,000 entities are loaded, one name is changed, and `flush()` is called. Statistics may record one flush and one entity update, yet Hibernate still had to manage the loaded entity set. To find out CPU time spent on dirty checking, measure a controlled flush segment and/or use a profiler; counting SQL alone is insufficient.

## 3. Defining Metrics Before Optimizing

| Metric | How to collect | Meaning and limitations |
| --- | --- | --- |
| Flush count | `Statistics.getFlushCount()` | Counts Hibernate full flush events; **does not** measure SQL count or duration per flush |
| Entity update count | `Statistics.getEntityUpdateCount()` | Counts updates handled by Hibernate via entity mechanisms; **does not cover all JPQL/native bulk DML** |
| Prepared statement count | `Statistics.getPrepareStatementCount()` | Statement preparations tracked by Hibernate Statistics; includes SELECT/INSERT/UPDATE, not equivalent to network round-trips |
| Duration of `entityManager.flush()` | `System.nanoTime()` around the flush call in tests | Includes dirty checking, SQL generation/binding, and DB I/O if any; **not pure dirty-checking CPU** |
| SQL `UPDATE` count, total SQL time | SQL logs, JDBC instrumentation, APM, DB-side metrics | Confirms executed SQL; heavy logging skews performance, and metrics may count per batch/statement differently |
| DB load: locks, I/O, WAL, indexes | PostgreSQL `pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)` when appropriate, DB monitoring | Reveals database-side cost; requires appropriate scope and permissions |
| Allocations, CPU stacks, GC | Java Flight Recorder (JFR) or profiler | Pinpoints Java/Hibernate costs; must be observed on a representative workload |

`org.hibernate.stat.Statistics` belongs to **SessionFactory**, meaning counters are aggregated across the entire factory, not isolated to a single request. In experiments, run sequentially with no other traffic and take before–after deltas; **do not call `statistics.clear()` on a multi-user system** just to measure one request. In production, use metrics tagged by transaction/task, JDBC telemetry, and database-side measurements.

You can enable Hibernate statistics for experiments:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
# Enable SQL logs only when verifying in a test environment:
logging.level.org.hibernate.SQL=DEBUG
# Hibernate 6 - inspect bind values when needed, watch out for sensitive data:
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Both statistics and logging incur overhead; do not use benchmark numbers collected with verbose logging enabled to extrapolate production latency.

## 4. Runnable Experiment: Same Value, New Value, and Redundant Bulk Update

This example uses **Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6, and H2**. In a configured Spring Boot Gradle project, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
```

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:flush_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
# For lab use only; do not keep create-drop with a real database.
```

### 4.1. Entity with Optimistic Version

File `src/main/java/com/example/flushlab/DemoAccount.java`:

```java
package com.example.flushlab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "demo_account")
public class DemoAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false, length = 120)
    private String displayName;

    protected DemoAccount() { }

    public DemoAccount(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

### 4.2. Repository with an Intentionally Redundant Bulk Update

File `src/main/java/com/example/flushlab/DemoAccountRepository.java`:

```java
package com.example.flushlab;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DemoAccountRepository
        extends JpaRepository<DemoAccount, Long> {

    @Modifying
    @Query("""
        update DemoAccount a
           set a.displayName = a.displayName
         where a.id = :id
        """)
    int redundantBulkUpdate(@Param("id") Long id);
}
```

The bulk statement above **intentionally** sets the column to its existing value to illustrate the difference: it is still a SQL `UPDATE` sent to the database if a row matches the predicate. The DB may optimize some internal work, but you must not assume the statement is free. The `getEntityUpdateCount()` statistic also does not fully reflect this bulk statement.

### 4.3. Service: Each Scenario Is a Real Transaction

File `src/main/java/com/example/flushlab/AccountScenarioService.java`:

```java
package com.example.flushlab;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountScenarioService {
    private final DemoAccountRepository repository;
    private final EntityManager entityManager;

    public AccountScenarioService(
            DemoAccountRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public Long seed() {
        return repository.saveAndFlush(new DemoAccount("An")).getId();
    }

    @Transactional
    public void assignSameValue(Long id) {
        DemoAccount account = repository.findById(id).orElseThrow();
        account.setDisplayName(account.getDisplayName());
        entityManager.flush();
    }

    @Transactional
    public void assignNewValue(Long id) {
        DemoAccount account = repository.findById(id).orElseThrow();
        account.setDisplayName("Binh");
        entityManager.flush();
    }

    @Transactional
    public void executeRedundantBulkUpdate(Long id) {
        int affected = repository.redundantBulkUpdate(id);
        if (affected != 1) {
            throw new IllegalStateException("Unexpected affected row count");
        }
    }
}
```

The `@Transactional` methods are called from another Spring bean, so the transaction proxy is active. Do not call `this.assignNewValue(...)` from inside the same class as evidence of `@Transactional` behavior.

In `assignSameValue`, the code simply reassigns the existing name; with this mapping, zero entity updates are expected. In `assignNewValue`, the entity becomes dirty and Hibernate generates an UPDATE on flush. In `executeRedundantBulkUpdate`, JPQL issues DML immediately when `executeUpdate` runs through the repository; entity dirty checking does not decide whether an UPDATE runs.

### 4.4. Measuring Statistics Deltas and Latency

File `src/main/java/com/example/flushlab/FlushMetricsRunner.java`:

```java
package com.example.flushlab;

import java.util.Locale;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class FlushMetricsRunner implements CommandLineRunner {
    private final AccountScenarioService scenarios;
    private final Statistics statistics;

    public FlushMetricsRunner(
            AccountScenarioService scenarios,
            EntityManagerFactory entityManagerFactory) {
        this.scenarios = scenarios;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Override
    public void run(String... args) {
        Long id = scenarios.seed(); // Outside all three measured samples.
        measure("same-value", () -> scenarios.assignSameValue(id));
        measure("changed-value", () -> scenarios.assignNewValue(id));
        measure("bulk-same-value",
                () -> scenarios.executeRedundantBulkUpdate(id));
    }

    private void measure(String name, Runnable action) {
        long beforeFlush = statistics.getFlushCount();
        long beforeUpdates = statistics.getEntityUpdateCount();
        long beforeStatements = statistics.getPrepareStatementCount();

        long started = System.nanoTime();
        action.run(); // Returns after the transaction completes.
        long elapsedNanos = System.nanoTime() - started;

        long flushes = statistics.getFlushCount() - beforeFlush;
        long updates = statistics.getEntityUpdateCount() - beforeUpdates;
        long statements =
                statistics.getPrepareStatementCount() - beforeStatements;

        System.out.printf(Locale.ROOT,
                "%s | ms=%.3f | flush=%d | entityUpdate=%d | prepared=%d%n",
                name, elapsedNanos / 1_000_000.0,
                flushes, updates, statements);
    }
}
```

File `src/main/java/com/example/flushlab/FlushLabApplication.java`:

```java
package com.example.flushlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlushLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FlushLabApplication.class, args);
    }
}
```

Run from the Spring Boot project directory containing the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, run `.\gradlew.bat bootRun`. All Java files above share package `com.example.flushlab`. The experiment is self-contained when placed in a Spring Boot project with the stated dependencies; it is not a Java SE program runnable with `javac` alone without Spring/Hibernate.

### 4.5. How to Interpret the Results

The `ms` and `prepared` values depend on hardware, JDBC, transaction manager, Hibernate version, warmup, and environment. **There is no single fixed stdout to copy into documentation.** Verify results by the following relationships:

| Scenario | Entity dirty? | Expected `entityUpdate` | Actual DML |
| --- | --- | --- | --- |
| `same-value` | No, for a simple `String` field and this mapping | 0 | SELECT to load; usually no UPDATE |
| `changed-value` | Yes | 1 | SELECT then UPDATE on flush |
| `bulk-same-value` | Bypasses per-entity dirty checking | May be 0 | Direct SQL UPDATE still executes |

Cross-check SQL logs to see whether `UPDATE` actually appears. Note that `prepared` includes SELECT and other statements, and `flush` also depends on auto-flush/commit, so **do not enforce absolute flush or prepared numbers** across all environments.

Use at least two independent verifications: Hibernate counters and actual SQL execution / JDBC telemetry. When database-side cost is needed, add affected row count, SQL statement latency, and DB metrics. Concluding no update occurred simply because `entityUpdate=0` on bulk DML is wrong.

## 5. Measuring Flush Separately and the Impact of Persistence Context Size

Timing an entire `service.assignNewValue(id)` call includes transaction startup, SELECT, Java logic, flush, DB update, and commit. If the goal is **flush cost**, place the timer **tightly around `entityManager.flush()`**:

```java
// Place inside a real @Transactional method:
DemoAccount account = entityManager.find(DemoAccount.class, id);
account.setDisplayName("Binh");

long started = System.nanoTime();
entityManager.flush();
long flushNanos = System.nanoTime() - started;
// Report flushNanos after the transaction completes successfully.
```

This is still **overall flush time**, which may include database round-trips. To inspect solely the overhead of checking unchanged entities, preload entities and time only the flush:

```java
// Illustration for a @Transactional service method:
public long measureCleanFlush(java.util.List<Long> ids) {
    for (Long id : ids) {
        entityManager.find(DemoAccount.class, id);
    }
    long started = System.nanoTime();
    entityManager.flush(); // Intentionally do not modify any attribute.
    return System.nanoTime() - started;
}
```

The second snippet is a **method fragment** meant to sit in a service bean with `EntityManager` and `@Transactional` on the method. The ID list must contain existing rows. Loading entities is intentionally placed outside the timed block; each run must still use a fresh transaction/persistence context for comparable conditions.

Design measurements across `N = 0, 100, 1,000, 5,000` managed entities, repeating multiple times with warmup and randomized execution order; report median/p95 instead of single samples. With no changes, entity update count should be 0, yet flush time may vary with persistence context size, tracking configuration, and JVM behavior. Use **JFR/profiler** to inspect CPU time in `flush`/`dirtyCheck` stacks before attributing costs to Hibernate, rather than taking raw time deltas and labeling them "dirty-checking cost" unconditionally.

To make measurements reliable:

- **Separate warmup from measurement** to avoid JIT, pool/metadata initialization, and cold-cache effects.
- Use identical data sizes, indexes, isolation levels, JDBC batch settings, and dirty entity counts.
- Avoid running benchmarks alongside live traffic; `Statistics` counters are global to the `SessionFactory`.
- Measure **flush**, **end-to-end transaction**, and **DB SQL time** separately. Differences between them are clues, not an exact CPU decomposition.
- Repeat to collect distributions (median/p95), recording JVM/DB versions and settings; GC, connection pools, locks, disk cache, and logging can all skew samples.
- Do not compare `@Transactional(readOnly=true)` against a write transaction to draw dirty-checking conclusions: in some Spring/Hibernate setups, read-only alters flush mode and tracking policies.

If record counts are small and measured differences fall below JVM noise, the right conclusion is "no evidence of a meaningful difference yet," not automatically "optimization succeeded."

## 6. Common Sources of Redundant Updates

### 6.1. Assigning the Same Value vs. Forced DML

```java
// Entity is managed; if a simple value is unchanged,
// Hibernate typically does not need an UPDATE:
account.setDisplayName(account.getDisplayName());

// By contrast, JPQL bulk DML still sends UPDATE when WHERE matches:
repository.redundantBulkUpdate(account.getId());
```

Distinguish *truly redundant* updates from intentional updates (e.g., updating `last_seen_at`, bumping version, generating audit signals). DBs have triggers, auditing, replication, and policies; two statements with the same value do not necessarily have identical side effects.

For conditional bulk updates, you can avoid redundant UPDATEs using a "value differs" predicate, though null-safe comparison syntax varies across DBs:

```sql
-- PostgreSQL; example with single parameter :new_name:
UPDATE demo_account
   SET display_name = :new_name
 WHERE id = :id
   AND display_name IS DISTINCT FROM :new_name;
```

If `rowCount=0`, either the row does not exist **or** the value already matched; business logic must distinguish these when needed. For versioned/optimistically locked columns, bulk UPDATEs must explicitly include the version predicate, increment the version, and check the row count; they do not automatically inherit full ORM protections.

### 6.2. `save()` and `saveAndFlush()` Inside Loops

```java
// Usually unnecessary when entities are already managed:
for (DemoAccount a : managedAccounts) {
    a.setDisplayName("New");
    repository.saveAndFlush(a); // Multiple flushes, prevents batching.
}

// Inside the same @Transactional, this is usually sufficient:
for (DemoAccount a : managedAccounts) {
    a.setDisplayName("New");
}
entityManager.flush(); // One deliberate flush if actually needed.
```

This is an isolated illustration assuming `managedAccounts` are managed entities in a transaction; it is not a standalone method. Hibernate flushes automatically on transaction commit under normal configuration; calling `flush()` manually at the end may **not even be necessary**. For large datasets, consider chunked flush + clear within memory limits, while managing detached entities, processing order, and transaction boundaries.

`saveAll(...)` does not automatically equal SQL bulk insert/update. For updates, it may invoke multiple persist/merge operations. JDBC batching effectiveness requires configuration and verification via SQL/batch metrics, especially with IDENTITY generation and statement ordering.

### 6.3. Loading Too Many Entities into the Persistence Context

Reading tens of thousands of managed entities just to compute an aggregate creates memory, hydration, snapshot, and unnecessary flush overhead. For read-only tasks, pick DTO projections, aggregate queries, or properly resource-managed streams. For large updates, evaluate bulk SQL or JDBC batching after accounting for domain events, callbacks, optimistic locking, and already-managed data.

Do not treat `entityManager.clear()` as a "free optimization": it detaches every entity in the context, potentially dropping unflushed changes and altering subsequent code behavior. In batch jobs, typically flush first and then clear according to a controlled strategy.

### 6.4. Updating All Columns When Only One Field Changes

For dirty entities, Hibernate-generated SQL UPDATEs may assign all updatable columns even when only one field changed. `@DynamicUpdate` can reduce written data/costs in some cases:

```java
import org.hibernate.annotations.DynamicUpdate;

@DynamicUpdate
@Entity
public class SomeEntity {
    // Valid fields, @Id, and constructor...
}
```

This is an **annotation illustration**, not a runnable standalone class. Base the decision on measured SQL and per-column change frequency. `@DynamicUpdate` can generate many SQL shapes, reducing statement reuse and batching; do not apply it indiscriminately before benchmarking.

## 7. Flush Mode, Transactions, and Measurement Side Effects

Hibernate/JPA supports different flush modes. In `AUTO`, flushes may occur before queries requiring consistent data and before commit, in addition to explicit `flush()` calls. Switching to `COMMIT` or `MANUAL` changes when queries see unflushed data; it is **not a default cure** for performance issues. A `flush()` merely sends SQL and remains subject to rollback until the transaction commits.

Specifically:

1. `repository.findById` may return an entity already in the persistence context or emit a SELECT depending on state; verify via SQL instead of counting repository calls.
2. JPQL/criteria queries may trigger auto-flush; the time of a "slow query" can include flush overhead. If a profiler only watches query method duration, it is easy to misattribute cost.
3. Writing SQL logs or enabling detailed statistics can increase latency. When comparing options, keep instrumentation levels identical.
4. A bulk update bypasses the persistence context; if an entity for that row is already loaded, in-memory state may become stale. Define clear `flush`/`clear`/`refresh` boundaries after bulk DML; avoid accidentally overwriting newer data with stale state.
5. Counting `UPDATE`s alone misses row locks, index churn, WAL, triggers, or replication lag. With PostgreSQL, combine database metrics and `pg_stat_statements` (if enabled) to see which statements truly consume resources.

For SQL needing analysis, run `EXPLAIN (ANALYZE, BUFFERS)` in a test environment with representative data. `ANALYZE` **executes the statement**, including UPDATEs, so prepare a transaction rollback or data copy; never run it casually on production writes.

## 8. Optimization Verification Plan

| Test case | How to execute | Passing signal |
| --- | --- | --- |
| Assigning exact old value | Load entity, set identical value, flush | No unnecessary entity UPDATE; DB result unchanged |
| Modifying one value | Load, update field, flush | One valid change committed; version increments if `@Version` present |
| Redundant JPQL bulk update | Execute `SET col = col` | Real SQL UPDATE recorded even though entityUpdate statistic may be 0 |
| Flushing many clean entities | Increase `N` managed entities without edits | Measure flush duration distribution and CPU profile; do not infer from update count |
| Flushing inside a loop | Compare against modifying multiple entities then flushing deliberately | Count flushes/SQL, latency, JDBC batches; business output identical |
| Using `@DynamicUpdate` | Compare against default SQL on same data | Inspect SET columns, SQL shape count, batching, and latency—not just SQL bytes |
| JPQL bulk + loaded entity | Load entity, run bulk update, re-read | Detect stale persistence context; clear refresh/clear strategy |
| Concurrency and optimistic lock | Two transactions modify same row | No lost updates; version conflict or conditional update handled properly |

For transaction/SQL-dependent cases, use integration tests on the **same DB engine as production** when evaluating locking, batching, or actual plans. H2 is convenient for API demonstrations, but it does not faithfully represent PostgreSQL/MySQL locking, MVCC, planner behavior, and WAL costs.

A minimal benchmark report should record: scenario name, managed entity count, dirty entity count, transaction count, flush count, entity update count, SQL DML count, median/p95 flush time, median/p95 transaction time, DB/driver/versions, and statistics settings. Verify **post-run business values** before accepting any performance change.

## 9. Evidence-Based Optimization Process

1. **Establish a baseline:** identify slow requests/jobs, transaction boundaries, managed entity counts, actual SQL executed, and DB costs.
2. **Find the cause:** excessive repeated flushes, oversized persistence context, unconditional DML, wide-column updates, or queries triggering auto-flush.
3. **Pick the smallest change:** remove unnecessary `saveAndFlush`; update only when values differ; use projections for read tasks; consider batching/`@DynamicUpdate` when evidence warrants it.
4. **Re-measure on the same workload:** latency, CPU, allocations, statement counts, row locks, and DB resources. Do not rely on a single run or `getEntityUpdateCount()` alone.
5. **Verify business correctness:** optimistic locking, callbacks, event listeners, caching, auditing, and consistency after bulk updates.
6. **Deploy with observability:** monitor deltas on real workloads and have a rollback plan if metrics or behavior degrade.

**Core takeaway:** `flush` is a synchronization checkpoint, *dirty checking* is the process of detecting changed entities, and *redundant updates* are unnecessary writes to the DB. To know whether an optimization works, **measure each layer with the right metric**, inspect executed SQL, and verify business invariants; reducing `save()` or `flush()` calls by itself does not prove lower database cost.