# Building a Pre-Release Data, Transaction, and Performance Regression Suite with Spring Data JPA

## 1. Objective: confirming an upgrade is genuinely safe

Upgrading Spring Boot, Spring Data JPA, Hibernate, JDBC drivers, or the database is not just about getting the application to **compile and start up**. A new version can generate different SQL, alter `Instant`/`BigDecimal` mappings, break cascades, change flush timing, introduce N+1 queries, bypass optimistic locking, or apply migrations that lose data.

A pre-release *regression suite* must provide evidence across three areas of commitment:

1. **Data accuracy:** existing data retains its meaning after migration; constraints, foreign keys, monetary totals, statuses, enums, timestamps, sequences, and query results align with business rules.
2. **Transaction correctness:** related changes commit or roll back together; concurrency conflicts are detected or coordinated; retries do not duplicate side effects.
3. **Performance compliance:** SQL counts, latency, throughput, lock waits, CPU, and I/O do not regress beyond thresholds set from baselines and SLOs.

Tests should not stop at checking that `repository.save()` returns a non-null object. Verify **database state after the transaction ends**, both on the happy path and when failures occur mid-flight. Defects affecting money, data integrity, atomicity, or lost updates must block release, even if every HTTP endpoint returns 200.

## 2. Building a risk-based regression matrix

| Category | Required checks | Acceptance criteria |
| --- | --- | --- |
| Schema and migrations | Flyway/Liquibase from old schema, DDL, FK, UNIQUE, CHECK, indexes, sequences | Runs cleanly on a copy of the old database; `hibernate.hbm2ddl.auto=validate` passes |
| Data | Counts, sums, duplicates, orphans, nulls, decimals, enums, timezones, statuses | No discrepancies beyond approved changes |
| JPA mapping | Entities, associations, cascades, orphan removal, converters, lazy loading | Repository reads/writes preserve domain semantics |
| Transactions | Commits, unchecked/checked exceptions, rollbacks, propagation, isolation | No partial writes; explicit rollback rules |
| Concurrency | Optimistic/pessimistic locks, two requests editing the same record | No lost updates/double effects; conflict errors handled |
| SQL and latency | N+1, pagination, batching, redundant DML, query plans | SQL counts and p50/p95/p99 meet budgets |
| Release | Old/new schema compatibility, backups, canary, recovery | Clear go/no-go criteria and accountable owners |

Split the suite into **unit**, **database integration**, and **workload/performance** tests. Unit tests verify logic fast but do not prove SQL or transactions. Integration tests require a real database. Large benchmarks use representative datasets and report distributions rather than relying on a single measurement.

Document in the plan: test name, invariant protected, input data, expected result, blocking severity, runtime duration, and evidence artifacts. If the older version already had a business bug, the baseline is not absolute truth; expected results must be confirmed against the domain contract.

## 3. Locking down a baseline before upgrading versions

For each stably running release, save at least:

- Application Git commit, Java version, Spring Boot/Spring Data/Hibernate/JDBC driver, DB engine/version, migration version, isolation level, connection pool, and Hibernate settings affecting SQL.
- A **consistent** schema/data snapshot or reproducible dataset: row counts per table, row counts per status, large relationship distributions, duplicate keys, null ratios, and edge-case fields.
- Core business queries and results: SQL shape, execution plans, SELECT/UPDATE counts per operation, p50/p95 latency, throughput, DB CPU/IO, lock waits, connection waits.
- Business invariants: no negative balances, total money conserved across transfers, no orphans, orders only in valid statuses, entity version increments on modification.
- Measurement conditions: concurrent users, data volume, JVM warmup, query cache, indexes, batch size, tracing/logging, network, and CPU/memory limits.

After upgrading, run the same fixtures and workloads. Comparing two p95 numbers across differing data sizes, caches, DB versions, or hardware can mislead. Record differences and noise levels; intentional valid changes must have their expected values updated through review.

## 4. Preparing test databases and legacy data

For applications using PostgreSQL in production, prefer **Testcontainers PostgreSQL from the same version family** for integration tests; H2 does not faithfully emulate SQL dialects, data types, MVCC, locking, indexes, or execution plans.

A proper migration plan has **two test paths**:

1. **Fresh install:** empty database runs all migrations up to the new version, JPA validates the schema, and smoke tests run.
2. **Real upgrade:** initialize schema/fixtures on the older version, take a backup snapshot, run the upgrade migrations, and verify data, constraints, and business queries on the new version.

The first path cannot replace the second: migrations may pass on an empty DB yet fail when columns contain nulls/duplicates in legacy data or when backfill logic misses a rare status.

Build fixtures with stable keys covering Unicode, fractional currency amounts, UTC/offset timestamps, one-to-many relationships, insufficient/sufficient balances, legacy enum values, valid nulls, and same-key contention. With production copies, anonymize sensitive data while keeping structural distributions representative enough for query planner statistics. Tests should reset data between runs and avoid order dependencies.

### Data reconciliation queries

The `orders` and `customers` tables below are **checklist examples only**, unrelated to the `bank_accounts` table in the runnable code later in this lesson:

```sql
-- Check counts by status, compared against pre-upgrade snapshot.
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY status;

-- Find orphans in business relationships.
SELECT COUNT(*) AS orphan_count
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL;

-- Find duplicates by business key.
SELECT external_key, COUNT(*) AS occurrences
FROM orders
GROUP BY external_key
HAVING COUNT(*) > 1;

-- Reconcile monetary totals using NUMERIC, never binary floating-point.
SELECT COALESCE(SUM(total_amount), 0) AS amount_total
FROM orders;

-- Business invariants.
SELECT COUNT(*) AS invalid_count
FROM orders
WHERE total_amount < 0
   OR status NOT IN ('NEW', 'PAID', 'CANCELLED');
```

If `customer_id` is mandatory, also add an `IS NULL` check: the anti-join above only catches non-null keys with no match. Reconciliation outputs should be compared against a normalized expected snapshot (e.g., excluding time-generated technical columns if allowed by contract). A full-dump checksum is insufficient for logic verification because row order and timestamps change.

For tricky changes, add targeted checks:

| Migration | Regression cases easily missed |
| --- | --- |
| String → enum | Legacy values fail to map; null/unknown silently mapped to another value |
| Double → decimal | Wrong precision/scale, rounding errors, mismatched totals after type conversion |
| Timestamp → timestamptz | UTC/offset drift, daylight saving issues, data lacking original timezone |
| Adding NOT NULL/UNIQUE | Existing data contains nulls/duplicates; migration fails or drops data arbitrarily |
| Renaming/splitting tables | Orphan FKs, rows multiplied by joins, skewed ID/sequence order |
| Adding indexes | Queries still seq scan on large data; write cost rises |
| Changing id/sequence | New IDs collide with existing IDs after restore, ID generation exhaustion, or sequence skew |

Do not edit a migration that has already run in shared environments just to make tests pass. Migrations must have clear versions, impacts, backfill logic, and forward-recovery plans.

## 5. Complete example: transaction test suite on Spring Data JPA

We use a sample application managing two accounts to demonstrate full database migrations, entity writes, rollbacks, optimistic locking, and SQL measurement. The example targets **Java 17+, Spring Boot 3.x, Spring Data JPA/Hibernate 6, PostgreSQL, JUnit 5, Testcontainers, Flyway**. The files below live in package `com.example.regression`; this is a Spring Boot/Gradle project, not a standalone Java SE program runnable via `javac` alone.

A real-world application also needs currency, auditing, idempotency keys, and transfer workflows; this lesson presents a minimal fixture to verify the persistence capabilities of an upgrade.

### 5.1. Dependencies, configuration, and migration

Add to `build.gradle` of a project with the Spring Boot plugin and compatible dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not pin Hibernate/Testcontainers/Flyway to arbitrary versions outside the BOM in use: check the Spring Boot compatibility matrix before upgrading. With Spring Boot 3, entities import from `jakarta.persistence`, not `javax.persistence`.

File `src/main/resources/application.properties`:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.flyway.enabled=true
# Enable only during test profiling:
# spring.jpa.properties.hibernate.generate_statistics=true
```

Note that real environments must supply the datasource via dedicated configuration/secrets; tests use Testcontainers below. Do not use `ddl-auto=update` in place of managed migrations.

File `src/main/resources/db/migration/V1__create_bank_accounts.sql`:

```sql
CREATE TABLE bank_accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_bank_accounts_nonnegative CHECK (balance >= 0)
);
```

For projects that already have a V1 migration, **do not replace a released V1**. Create a migration with the next version number and run the test suite against the project's actual schema. This table is solely for the standalone example.

### 5.2. Entity with optimistic locking

File `src/main/java/com/example/regression/BankAccount.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "bank_accounts")
public class BankAccount {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected BankAccount() { }

    public BankAccount(Long id, BigDecimal openingBalance) {
        if (id == null || openingBalance == null
                || openingBalance.signum() < 0) {
            throw new IllegalArgumentException("Invalid account");
        }
        this.id = id;
        this.balance = openingBalance;
    }

    public Long getId() { return id; }
    public BigDecimal getBalance() { return balance; }
    public Long getVersion() { return version; }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("Insufficient balance");
        }
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

An initially `null` `@Version Long` field helps Spring Data JPA recognize new entities when using assigned IDs (`id` already populated) and lets Hibernate initialize the version upon persist. When a dirty entity is flushed, the UPDATE checks `version` in the WHERE clause; a transaction holding a stale version fails to update and raises an optimistic lock error.

File `src/main/java/com/example/regression/BankAccountRepository.java`:

```java
package com.example.regression;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BankAccountRepository
        extends JpaRepository<BankAccount, Long> { }
```

### 5.3. Service defining transaction boundaries

File `src/main/java/com/example/regression/BankTransferService.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BankTransferService {
    private final BankAccountRepository accounts;

    public BankTransferService(BankAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(Long from, Long to, BigDecimal amount) {
        moveBalances(from, to, amount);
    }

    @Transactional
    public void transferThenFail(Long from, Long to, BigDecimal amount) {
        moveBalances(from, to, amount);
        throw new IllegalStateException("Simulated failure after changes");
    }

    private void moveBalances(Long from, Long to, BigDecimal amount) {
        if (from == null || to == null || from.equals(to)
                || amount == null || amount.signum() <= 0
                || amount.scale() > 2) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        BankAccount source = accounts.findById(from).orElseThrow();
        BankAccount target = accounts.findById(to).orElseThrow();

        source.debit(amount);
        target.credit(amount);
        // Managed entities: Hibernate flushes when the transaction commits.
    }
}
```

`@Transactional` methods must be invoked **from outside through the Spring bean proxy**, as the JUnit test invokes the service below. `moveBalances` is a private helper and needs no separate annotation. When `transferThenFail` throws an unchecked exception, the transaction rolls back both changes.

File `src/main/java/com/example/regression/RegressionApplication.java`:

```java
package com.example.regression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegressionApplication.class, args);
    }
}
```

### 5.4. Integration test using real PostgreSQL

File `src/test/java/com/example/regression/BankTransferRegressionTest.java`:

```java
package com.example.regression;

import java.math.BigDecimal;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceException;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "spring.jpa.hibernate.ddl-auto=validate",
    "spring.jpa.open-in-view=false",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@Testcontainers
class BankTransferRegressionTest {
    @Container
    static final PostgreSQLContainer<?> DB =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DB::getJdbcUrl);
        registry.add("spring.datasource.username", DB::getUsername);
        registry.add("spring.datasource.password", DB::getPassword);
    }

    @Autowired BankAccountRepository accounts;
    @Autowired BankTransferService transfers;
    @Autowired EntityManagerFactory entityManagerFactory;

    @BeforeEach
    void seed() {
        accounts.deleteAllInBatch();
        accounts.saveAllAndFlush(List.of(
            new BankAccount(1L, new BigDecimal("100.00")),
            new BankAccount(2L, new BigDecimal("20.00"))
        ));
    }

    @Test
    void commitsBothSidesOfTransfer() {
        transfers.transfer(1L, 2L, new BigDecimal("30.00"));
        assertBalance(1L, "70.00");
        assertBalance(2L, "50.00");
    }

    @Test
    void rollsBackBothSidesAfterFailure() {
        assertThrows(IllegalStateException.class,
            () -> transfers.transferThenFail(
                1L, 2L, new BigDecimal("30.00")));
        assertBalance(1L, "100.00");
        assertBalance(2L, "20.00");
    }

    @Test
    void rejectsOverdraftWithoutPartialWrite() {
        assertThrows(IllegalArgumentException.class,
            () -> transfers.transfer(
                1L, 2L, new BigDecimal("200.00")));
        assertBalance(1L, "100.00");
        assertBalance(2L, "20.00");
    }

    @Test
    void rejectsStaleOptimisticWriter() {
        EntityManager first = entityManagerFactory.createEntityManager();
        EntityManager stale = entityManagerFactory.createEntityManager();

        try {
            first.getTransaction().begin();
            stale.getTransaction().begin();

            BankAccount current = first.find(BankAccount.class, 1L);
            BankAccount old = stale.find(BankAccount.class, 1L);

            current.debit(new BigDecimal("1.00"));
            first.getTransaction().commit();

            old.debit(new BigDecimal("1.00"));
            assertThrows(PersistenceException.class,
                () -> stale.getTransaction().commit());
        } finally {
            if (first.getTransaction().isActive()) {
                first.getTransaction().rollback();
            }
            if (stale.getTransaction().isActive()) {
                stale.getTransaction().rollback();
            }
            first.close();
            stale.close();
        }

        assertBalance(1L, "99.00");
    }

    @Test
    void keepsStatementCountWithinIsolatedTestBudget() {
        SessionFactory factory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = factory.getStatistics();

        long before = statistics.getPrepareStatementCount();
        transfers.transfer(1L, 2L, new BigDecimal("30.00"));
        long statements =
                statistics.getPrepareStatementCount() - before;

        // Example budget for the fixture: two SELECTs and two UPDATEs
        // in a JVM with no concurrent traffic.
        assertTrue(statements > 0 && statements <= 6,
                "Unexpected prepared statements: " + statements);

        assertBalance(1L, "70.00");
        assertBalance(2L, "50.00");
    }

    private void assertBalance(Long id, String expected) {
        BigDecimal actual = accounts.findById(id)
                .orElseThrow().getBalance();
        assertEquals(0, actual.compareTo(new BigDecimal(expected)));
    }
}
```

**Run the test** from the project directory with Gradle wrapper and Docker daemon running:

```bash
./gradlew test --tests com.example.regression.BankTransferRegressionTest
```

On PowerShell, use `.\gradlew.bat test --tests com.example.regression.BankTransferRegressionTest`. JUnit reports assertion results; there is no fixed stdout for latency or SQL count to transcribe beforehand. A complete run starts the PostgreSQL container, Flyway runs the SQL migration, Hibernate validates the schema, and then the test cases execute.

**Important detail:** do not put `@Transactional` on this test class: if the test itself wraps everything in a transaction, it can hide whether the service actually commits or rolls back. The two `EntityManager`s in the optimistic locking test are created separately, each with an independent resource-local transaction; if the second transaction attempts to commit stale data, JPA/Hibernate may throw `OptimisticLockException` or wrap it in `RollbackException` (both under `PersistenceException`). If changing providers/versions alters the exception hierarchy, inspect the root cause and DB state to confirm the optimistic lock failure rather than checking only message strings.

## 6. Adding transaction tests for real-world scenarios

The tests above are the core; real releases should also cover:

| Scenario | Setup | Required behavior |
| --- | --- | --- |
| Checked exception | `@Transactional` method throws a checked exception after modifying entities | Verify `rollbackFor` is set properly; Spring does not roll back all checked exceptions by default |
| `REQUIRES_NEW` | Inner transaction commits, outer transaction fails | Independent commit is intentional; if atomicity is required, redesign |
| Self-invocation in same bean | `this.methodAnnotatedTransactional()` | Understand self-invocation normally bypasses the proxy |
| Optimistic contention | Two transactions read the same `@Version` then write | One succeeds, stale update is detected, controlled retry if needed |
| Pessimistic lock | Two transactions lock the same row | No permanent deadlock; timeouts/ordering are verified |
| Isolation | Concurrent read/write under READ COMMITTED or REPEATABLE READ | Behavior aligns with domain and real DB |
| Bulk JPQL/native update | Bulk modifies rows already loaded as managed entities | Handle stale persistence context/`@Version`/cache explicitly |
| Cascades and orphan removal | Add/remove children with FK/UNIQUE | Both sides of the relationship are accurate after flush and commit |
| Retry after deadlock | Trigger transient error, perform bounded retry | No duplicate transactions or side effects |
| Outbox/events | Failure before commit or after commit before publish | No events published for uncommitted state; publish recovery exists |

`@Transactional(readOnly = true)` may tune flushing/tracking depending on the provider, but should not be relied upon as an absolute DB write ban. Test whether read methods accidentally dirty entities or run bulk DML, especially after an upgrade. Remember `@Transactional` rolls back on unchecked exceptions by default; checked exceptions require explicit policy rather than guesswork.

For concurrency tests, have each thread call the service **through the bean** so each gets its own transaction; synchronize timing with `CountDownLatch`/barriers and finite timeouts. Do not rely on lucky `Thread.sleep` calls to simulate races. After both commits/rollbacks complete, read the DB in a new transaction to catch lost updates. Optimistic locking only **raises an error**; it does not automatically retry for the user.

## 7. Performance regressions: do not measure only test execution time

A regression suite should separate **SQL count gates** from **performance benchmarks**.

### 7.1. SQL count/shape in integration tests

In an isolated test with Hibernate statistics enabled, you can measure the delta of `Statistics.getPrepareStatementCount()` before and after a service call. This is Hibernate's prepared statement count, covering SELECT/INSERT/UPDATE, not the exact record count or network round-trips. Do not call `statistics.clear()` on a production SessionFactory handling live traffic, because the counter is shared.

Add tests for these queries:

- Loading 100 orders with an association: verify it does not issue 101 SELECTs due to N+1 when accessing each child.
- Pagination and sorting: entity/result counts are accurate, no collection fetch causing in-memory pagination.
- Updating entities: avoid `saveAndFlush` loops causing repeated flushes; distinguish `saveAll` from actual JDBC batching.
- Bulk JPQL/native DML: SQL counts and affected rows; bulk operations generally bypass dirty checking and do not handle `@Version` like managed entity updates.
- Lazy/eager fetching: verify both data and SQL count. `@EntityGraph`, `JOIN FETCH`, or DTO projections are options, but evaluate cardinality/duplication and memory instead of turning EAGER on everywhere.

### 7.2. Pre-release benchmarks on representative data

Run load tests with a sufficiently large dataset, warm up JVM/pools/caches, run multiple rounds across concurrency levels; report p50/p95/p99, throughput, error rates, CPU, allocations, GC, DB buffers, lock waits, connection waits, and SQL counts. Evaluate differences on the **same** driver/DB/data/indexes/infra. A single 200 ms timeout on a shared CI runner is not enough to draw performance conclusions.

Example gating rules (**illustrative** thresholds—replace with your project's SLOs/baselines):

| Metric | Example baseline | Illustrative rule |
| --- | ---: | --- |
| Search endpoint p95 | 180 ms | ≤ 216 ms; >20% increase triggers investigation/block per SLO |
| SQL SELECTs per operation | 4 | ≤ 5; jumping to 100 indicates N+1 |
| Import throughput | 2,000 records/min | ≥ 1,800 records/min |
| Lost updates / monetary discrepancies | 0 | 0, release blocker |
| Migration drops valid records | 0 | 0, release blocker |

With PostgreSQL, analyze query plans using `EXPLAIN (ANALYZE, BUFFERS)` on staging with representative data. `EXPLAIN ANALYZE` **actually executes the SQL statement**, including DML, so never run UPDATE/DELETE with ANALYZE casually in production. If `pg_stat_statements` is enabled, combine latency and buffer metrics to spot query shape/index regressions. Separate query latency from any auto-flush time occurring right before the query.

## 8. Common pitfalls when upgrading Spring Data JPA/Hibernate

- **`javax` → `jakarta`:** when upgrading to Spring Boot 3/Hibernate 6, update entity/validation imports and related dependencies. Check native queries/dialects, table/column names, and sequences.
- **Data types:** decimal scale, enum representations, UUIDs, JSON, `Instant`/`LocalDateTime`/`OffsetDateTime`, and timezones. Read data back from the new DB to verify semantics.
- **Flush/dirty checking:** a single `flush()` may emit no UPDATE; `saveAndFlush` inside a loop can multiply SQL/round-trips; measure both counts and elapsed time.
- **`@Version` and bulk DML:** JPQL/native bulk updates do not auto-increment versions or refresh managed entities; add explicit version predicates and clear/refresh when needed.
- **ID generation:** sequence allocation, identity strategies, insert batching, sequences out of sync after restore.
- **Cascades/collections:** `orphanRemoval` and FKs can surface errors from altered flush ordering, especially when reparenting children.
- **Query shapes:** DISTINCT, FETCH JOIN, pagination, sorting, null comparisons, equality, projections. SQL changes can alter query plans even when results remain valid.
- **Transactions:** checked exceptions, self-invocation, `REQUIRES_NEW`, isolation, read-only hints, retries. Test actual commits to be sure.
- **Caching:** second-level/query caches can hold stale data after bulk updates; if caching is enabled, verify invalidation.
- **Database versions:** drivers/dialects and schema indexes/constraints may behave differently; test on a real DB equivalent to the deployment target.

Do not adjust expected test results just because Hibernate emits new SQL. If the new SQL is accurate yet slow, investigate the planner/indexes and compare against baseline; if a behavioral change is intentional, document the migration, logic, and sign-off decision.

## 9. Pre-release CI/CD gates

Recommended pipeline:

1. **Compile + unit:** verify Java code, validation, and business rules.
2. **Migration from old schema:** initialize schema/data from the prior release, run new migrations, check counts/sums/duplicates/orphans and schema validation.
3. **JPA integration:** repository queries, entity mappings, FKs, rollbacks, optimistic locking, and SQL counts via Testcontainers.
4. **Staging performance:** representative workload, query plans, latency/throughput/DB resources vs. baseline.
5. **Release readiness:** backup/restore drill, rolling schema compatibility, canary plan, and alerts.

Example GitHub Actions workflow for a Gradle project with wrapper:

```yaml
name: JPA regression
on:
  pull_request:
  workflow_dispatch:

jobs:
  jpa-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: PostgreSQL integration tests
        run: ./gradlew --no-daemon test --tests "com.example.regression.BankTransferRegressionTest"
```

The workflow above illustrates a standalone integration job with Testcontainers; it **does not replace** pipelines restoring legacy schemas or running benchmarks. Adjust module paths/Java versions for your actual build, isolate databases across jobs, and avoid parallel tests polluting `Statistics`. Archive artifacts by commit SHA including JUnit reports, schema/migration versions, fixture datasets, SQL/plan diffs, benchmarks, and gate decisions.

## 10. Rolling releases, canaries, and recovery

Before release, verify database compatibility with **both old and new application versions** during rolling deployments. Prefer **expand → backfill/migrate → switch → contract**: add compatible columns/tables first, let both versions run, switch read/write traffic, and drop old columns only once no consumers remain.

On PostgreSQL, certain DDL/index operations can lock tables; assess lock/backfill duration, statement timeouts, and concurrent index creation where appropriate. `CREATE INDEX CONCURRENTLY` has specific transaction requirements and must coordinate with your migration tool.

Canaries should monitor at least application errors, deadlocks, optimistic-lock failures, SQL/query counts, p95/p99 latency, DB CPU/IO, connection pools, background jobs, and data invariants. If orphans/duplicates/monetary mismatches, partial transaction writes, or blocking regressions appear, halt the rollout.

**Rolling back the application does not roll back the schema.** Migrations that drop columns or perform lossy type conversions can prevent the old binary from running. Therefore, maintain tested backups with restore drills, a clear rollback window, reviewed forward-fix/compensation scripts, and the ability to re-run tests against restored state.

## 11. Regression suite completion checklist

| Question | Passing criteria |
| --- | --- |
| Is there a reproducible baseline? | Recorded commits, DB/ORM versions, schemas, datasets, workloads, SLOs, and artifacts |
| Tested upgrading from old schema with data? | Migrations/constraints/sequences/backfills pass; reconciliation SQL matches |
| Are JPA mappings still valid? | Repository queries, flushing, cascades, lazy loading, converters, pagination pass on real DB |
| Are transactions atomic? | Failures after modifying multiple entities roll back all changes; DB checked post-completion |
| Is concurrency protected? | No lost updates; version/locking conflicts handled deliberately |
| No performance regressions? | SQL budgets, plans, p95/p99/throughput meet chosen thresholds |
| Are release gates strong enough? | Blocking tests halt builds/deploys; logs/reports archived with the release |
| Can we halt and recover? | Canary, backup/restore, compatibility, and forward-fixes rehearsed |

**Conclusion:** A pre-release Spring Data JPA regression suite connects **historical data**, **transaction behavior**, and **SQL/database cost** in a single evidence-based process. Only when schema upgrades, data invariants, concurrency, query budgets, benchmarks, and recovery plans are all verified do you have a solid basis for releasing.
