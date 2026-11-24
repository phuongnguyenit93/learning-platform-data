# Testing Queries with Appropriate Dataset Size, Distribution, and Data Characteristics

## 1. A Query Passing on 5 Rows May Still Fail on Real Data

A common data-testing mistake is inserting three to five rows with completely distinct values, calling `repository.find...()`, seeing the expected result, and concluding the query is verified. That tiny dataset lacks the traits that trigger real-world bugs: millions of rows, one tenant dominating the table, skewed statuses, foreign keys with massive fan-out, `NULL`s, duplicates, tied timestamps, outliers, or concurrent writes during pagination.

For example: an API fetches paid invoices for a tenant, sorted newest first, returning 40 rows per page. With three invoices at three distinct timestamps, sorting solely by `createdAt` looks fine. With thousands of invoices sharing timestamps, omitting a secondary tie-breaker `id` causes page boundaries to jitter. When a hot tenant has 70% paid rows while a cold tenant has 20%, an index great for one may perform poorly for the other. When a single invoice has a huge total, summing into `int` overflows.

**Lesson topic:** how to design, generate, and verify **test datasets whose size, distribution, and characteristics match the query under test**, instead of treating test data as a handful of throwaway rows.

### After This Lesson, You Can

1. Distinguish **query logic correctness** from **query performance**: they require different evidence.
2. Analyze real workloads to choose row counts, cardinality, value frequencies, skew, table relationships, and edge cases.
3. Build **deterministic** datasets with fixed seeds and known expected statistics reproducible on developer laptops and CI.
4. Write Spring Data JPA tests covering tenant filters, statuses, half-open time intervals, `NULL`s, empty strings, duplicates, aggregates, and pagination.
5. Understand why `Page`, `Slice`, offset paging, keyset/seek paging, and `ORDER BY` with a tie-breaker behave differently.
6. Read `EXPLAIN`/`EXPLAIN ANALYZE` and recognize effects of indexes, statistics, skew, correlated columns, and database engines.
7. Avoid brittle benchmarks like `assertThat(duration).isLessThan(100)` on shared laptops or CI runners.
8. Use Java 17+, Spring Boot 3.x, Spring Data JPA, H2, and JUnit Jupiter to build a complete 1,200-row example with **11 JUnit tests**.
9. Know when H2/`@DataJpaTest` suffices for logic checks and when to use real PostgreSQL/MySQL, Testcontainers, and dedicated load tests.

**Scope:** the direct focus is *test data for SQL/JPA queries*. This lesson examines data characteristics from a Spring Boot testing perspective rather than treating 1,200 rows as representative of every production scale. The runnable example targets Spring Boot **3.x / Jakarta Persistence / Hibernate 6 / Java 17+**; other versions should verify imports, dependencies, and SQL dialects.

## 2. Which Dimensions Should Describe a Dataset?

A useful dataset is not defined by `size = N` alone. It must specify dimensions affecting the query's **predicates, joins, grouping, ordering, and business constraints**.

| Data Dimension | Design Question | Bugs It Can Expose |
|---|---|---|
| **Row count** | 0, 1, equal to page size, over page size, thousands/millions? | Empty results, limit/offset, memory, count queries |
| **Tenant/group distribution** | Does one big tenant hold 75% while small tenants share 25%, or uniform? | Tenant leakage, selectivity swings, index skew |
| **Status frequencies** | 70% PAID or only 1% PAID? Rare statuses present? | Plan selectivity, counts, wrong predicates |
| **NULL values** | Does a field have 5% nulls, 40% nulls, or none? | `IS NULL`, outer joins, null sort ordering |
| **Duplicate values** | Multiple rows sharing customer, timestamp, or code? | Duplicate handling, pagination ties, aggregation |
| **Empty strings & whitespace** | Do `""`, `" "`, Unicode, or mixed case appear? | Trimming, collation, equality, normalization |
| **Time distribution** | Peak hours, tied timestamps, boundary instants, historical ranges? | Inclusive/exclusive ranges, order ties |
| **Outlier values** | Unusually large amounts, very long strings, valid negative numbers? | Overflow, precision, sorting, validation |
| **Multi-column correlation** | Are large tenants also more likely to be PAID? | Wrong planner estimates, cross-filter bugs |
| **Relationship cardinality** | Does 1:n include n=0, n=1, n=1000, or heavy fan-out? | JOIN duplicates, `GROUP BY`, N+1, pagination |
| **Row width** | Large TEXT/BLOB/JSON payloads vs. narrow IDs/enums? | I/O, memory, serialization, index-only scans |
| **History / mutations** | Soft-deleted, archived, legacy-versioned rows? | Forgotten filters, snapshots, concurrent paging |
| **Domain semantics** | Multi-tenancy, PII, timezones, currencies, encoding? | Security, timezones, precision/collation |

**Key mindset:** pick dimensions **that affect the query under test**. Never cram every edge case into one giant fixture. If a query looks up a unique email, email cardinality and case sensitivity come first. If a query aggregates monthly revenue, time distribution, statuses, monetary ranges, and row counts determine test quality.

### 2.1. Cardinality and Selectivity

- **Cardinality** of a column: count of distinct values. For example, `status` has three distinct values while `id` has 1,200.
- **Selectivity** of a condition: fraction of matching rows. For example, `tenant_id='HOT' AND entry_state='PAID'` matches 630/1,200 = 52.5% of the table, while `tenant_id='COLD' AND entry_state='PAID'` matches 60/1,200 = 5%.
- A common predicate returns huge result sets; a rare predicate returns a few rows. Test both because queries and query planners handle them very differently.

A guiding formula:

\[
\text{selectivity}(P) = \frac{\text{number of rows satisfying predicate }P}{\text{total number of rows}}
\]

Do not use cardinality as a synonym for selectivity. Two columns can both have 10 distinct values while heavily skewed frequencies produce drastically different behavior.

### 2.2. Skew: Unevenly Distributed Data

A uniform dataset hides a common failure mode:

```text
A uniform dataset:
  Tenant A: 500 rows, 250 PAID
  Tenant B: 500 rows, 250 PAID

A skewed dataset:
  Tenant HOT : 900 rows, 630 PAID
  Tenant COLD: 300 rows,  60 PAID
```

Knowing the total is 1,000 or 1,200 says nothing about each predicate's selectivity. A query planner may prefer a table scan for the dominant group while using an index for the rare group. Testing only an “average” tenant fails multi-tenant apps with a few massive tenants.

### 2.3. Correlation: Non-Independent Conditions

When `HOT` has 70% `PAID` and `COLD` has 20% `PAID`, `tenant_id` and `entry_state` are **correlated**. A generator picking statuses uniformly at random fails to reproduce that correlation.

Query planners often need *extended/multivariate statistics* to estimate combined selectivity accurately. For instance, PostgreSQL gathers extended statistics (dependencies, n-distinct, most-common-value combinations) via `ANALYZE`; whether they apply depends on the query, version, and settings. **This must be measured on the real database engine**, never assumed because H2 picked some plan.

### 2.4. Duplicates and Ties Are Not Corrupted Data

A customer with hundreds of orders is **valid data**. Multiple transactions sharing the same timestamp due to batch writes or DB clock precision are also normal. Tests that generate unique values in every column never catch bugs like:

- Queries accidentally using `distinct` and dropping valid rows.
- `LIMIT`/`OFFSET` without stable ordering causing Page 1 and Page 2 to overlap.
- `GROUP BY` missing a column and corrupting aggregates.
- One-to-many `JOIN`s causing fan-out and duplicate entities.
- Mapping queries calling `getSingleResult()` when conditions are non-unique.

## 3. Separating Two Goals: Correctness and Performance

### 3.1. Query Correctness Tests

Logic tests must make deterministic assertions:

- Are the exact rows for tenant, state, and time range returned?
- Do any rows from another tenant leak in?
- Are `NULL` and `""` kept distinct?
- Are duplicate keys preserved instead of silently dropped?
- Do pages return the right slice size, total count, and stable order?
- Are sums and counts accurate with outliers and large values?
- Are empty results handled cleanly?
- Do the last page and out-of-range pages behave properly?
- Does sorting avoid ambiguity when multiple rows share timestamps?

These tests should be deterministic, repeatable, and valuable in CI. You do not need a million rows when 1,200 **properly shaped** rows expose the logic bugs.

### 3.2. Query Performance Tests

Performance tests require different conditions:

- Total row counts and index sizes representative of production workloads.
- Realistic distributions, histograms, most-common values, correlations, and fan-out.
- Database engine, version, collation, isolation, and configuration matching production.
- Fresh `ANALYZE`/statistics matching how production operates.
- Controlled warm-up, cache state (cold/warm), concurrency, connection pooling, and client network latency.
- Measuring p50/p95/p99 latencies, throughput, memory, I/O, and execution plans.
- SLO budgets independent of noisy CI runs on shared runners.
- Baselines measured under identical conditions before claiming performance regressions.

**Never hardcode “SQL must finish under 20 ms” in a JVM/H2 unit test and claim production meets its SLO.** Measured runtime reflects JIT warmup, GC pauses, noisy CI neighbors, disk/cache state, networking, DB settings, and planner choices. Use a dedicated performance integration job with statistical baselines—or carefully bounded plan-shape checks—rather than millisecond assertions on H2.

### 3.3. A Practical Testing Matrix

| Test Layer | Data | Purpose | Cadence |
|---|---|---|---|
| Logic unit test | A few fixed objects | Pure filter/domain logic | Every commit |
| `@DataJpaTest` / H2 | Hundreds–few thousand shaped rows | Repository correctness, paging, aggregation | Every commit or PR |
| Integration + prod DB engine | Medium size with realistic skew | SQL dialect, indexes, counts/JOINs, constraints | PR/main depending on cost |
| Performance job | Production-scale volume and distribution | Query plans, latency distributions, memory/I/O | Nightly / weekly / pre-release |
| Staging / E2E | Anonymized/synthetic workload | End-to-end API, proxies, caching, concurrency | Per release |
| Production monitoring | Real workload with PII safeguards | Slow-query tracking and regression alerts | Continuous |

Never force every logic test to seed millions of rows. Equally, never treat an H2 slice test as proof of PostgreSQL production indexing and query plans.

## 4. Designing a Quantitative Dataset Profile Before Writing Code

We choose an `invoice_entries` table with:

- `id`: unique primary key generated sequentially `1...1,200`.
- `tenant_id`: 900 `HOT` rows and 300 `COLD` rows.
- `entry_state`: `HOT` has 70% `PAID`; `COLD` has 20% `PAID`; remainder `OPEN`.
- `created_at`: only 24 distinct hourly values, producing heavy timestamp ties.
- `customer_ref`: includes `NULL`, empty string `""`, and many duplicate refs.
- `gross_cents`: small typical amounts plus one `1,000,000` cents outlier.

### 4.1. Target Profile

| Group | Total | PAID | OPEN | NULL `customer_ref` |
|---|---:|---:|---:|---:|
| HOT | 900 | 630 | 270 | 45 |
| COLD | 300 | 60 | 240 | 15 |
| **Total** | **1,200** | **690** | **510** | **60** |

Frequencies:

- `HOT` represents 75% of rows; `COLD` represents 25%.
- `PAID` represents 70% of `HOT`, yet only 20% of `COLD`.
- `NULL` `customer_ref` appears whenever `id % 20 == 0` (5% of all rows).
- Empty string `customer_ref` appears on IDs divisible by 33 and not divisible by 20; `HOT` has **26** such rows.
- Customer ref `CUST-7` appears **18** times in `HOT`; `COLD` has **5** occurrences because one would-be match turns into an empty string.
- Timestamps are `2026-01-01 00:00:00` plus `id % 24` hours. Thus in `HOT`, `12:00` occurs **38** times and `13:00` occurs **37** times.
- Invoice `id=900` belongs to `HOT`/`PAID` with `gross_cents=1_000_000`, far larger than the typical `100 + id % 7`.

These numbers serve as the **test oracle**: tests assert these exact values rather than computing “expected counts” using the very SQL query under test.

### 4.2. Why Use a Deterministic Formula?

Using an unseeded `Random()` or `Instant.now()` in seeding makes failures—especially page-boundary bugs—hard to reproduce. An ID-driven formula:

```text
tenant(i) = HOT  if 1 <= i <= 900; else COLD
state(i)  = PAID if (HOT && i % 10 < 7)
                    or (COLD && i % 10 < 2)
             OPEN otherwise
time(i)   = 2026-01-01T00:00 + (i % 24) hours
amount(i) = 1_000_000 if i = 900; else 100 + (i % 7)
ref(i)    = NULL if i % 20 = 0
            "" if i % 33 = 0 and not NULL
            "CUST-" + (i % 50) otherwise
```

When CI fails at `id=957`, developers know immediately it belongs to `COLD`, its exact timestamp, and its ref, and can reproduce the whole dataset cleanly. Deterministic datasets also let you compare two implementations of a query on identical input.

### 4.3. When to Use Seeded Randomness?

Seeded randomness remains helpful for complex distributions: log-normal/Zipfian curves, multi-dimensional probabilities, or Monte Carlo simulations. Still, follow five rules:

1. Pick a fixed seed and log it in the test report.
2. Pin generator/algorithm versions so outputs never drift unexpectedly.
3. Verify generated histograms and quantiles afterward.
4. Add **explicit edge fixtures** alongside random generation so rare states always appear.
5. Never assume `Random.nextInt(...)` approximates real production workloads.

This lesson's example uses a non-random formula so tests remain exact and transparent.

## 5. Runnable Spring Boot 3.x / Java 17+ Example

The example has 4 files: Spring Boot application, JPA entity, repository, and JUnit test class. No HTTP server, Docker, Redis, or external API is required. H2 verifies JPA/SQL semantics at an appropriate scope.

**Target versions:** Java 17+, Spring Boot 3.x (e.g., 3.5), Spring Data JPA, Hibernate 6, H2, and JUnit Jupiter. Boot 3 uses `jakarta.persistence.*` imports; do not copy directly into Boot 2 (`javax.persistence.*`) or assume Boot 4 keeps identical test module packages.

### 5.1. Dependencies

**Gradle Groovy DSL**, in a project already configured with the Boot Gradle plugin, dependency management, repositories, and Java toolchain:

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

**Maven**, in a project already using the Spring Boot parent/BOM and compatible Maven Surefire/JDK 17:

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

**These are dependency snippets, not complete build files.** H2 stays on the test runtime classpath; never point the demo at a production database connection.

### 5.2. Project Structure

```text
src/
├── main/java/com/example/queryshape/
│   ├── QueryShapeApplication.java
│   ├── InvoiceEntry.java
│   └── InvoiceEntryRepository.java
└── test/java/com/example/queryshape/
    └── InvoiceQueryShapeTest.java
```

The test avoids external CSV files. `@BeforeEach` seeds the dataset via `JdbcTemplate.batchUpdate(...)` inside the test-managed transaction, loading 1,200 rows quickly without forcing Hibernate to track 1,200 managed entities.

### 5.3. Spring Boot Application Class

**File `src/main/java/com/example/queryshape/QueryShapeApplication.java`:**

```java
package com.example.queryshape;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QueryShapeApplication {
    public static void main(String[] args) {
        SpringApplication.run(QueryShapeApplication.class, args);
    }
}
```

The main class sits in the root package alongside the entity and repository, allowing `@DataJpaTest` to discover the Spring Boot configuration and auto-configure the JPA slice without explicit `@EntityScan` or `@EnableJpaRepositories`.

### 5.4. Entity Defining Table, Columns, and Two Indexes

**File `src/main/java/com/example/queryshape/InvoiceEntry.java`:**

```java
package com.example.queryshape;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
        name = "invoice_entries",
        indexes = {
            @Index(
                name = "idx_inv_tenant_state_time_id",
                columnList = "tenant_id,entry_state,created_at,id"
            ),
            @Index(
                name = "idx_inv_tenant_time_id",
                columnList = "tenant_id,created_at,id"
            )
        }
)
public class InvoiceEntry {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 20)
    private String tenantId;

    @Column(name = "entry_state", nullable = false, length = 20)
    private String entryState;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "gross_cents", nullable = false)
    private long grossCents;

    @Column(name = "customer_ref")
    private String customerRef;

    protected InvoiceEntry() {
        // Constructor required by JPA.
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getEntryState() {
        return entryState;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public long getGrossCents() {
        return grossCents;
    }

    public String getCustomerRef() {
        return customerRef;
    }
}
```

**Why assign IDs explicitly?** Tests seed IDs 1 through 1,200 so every run reproduces the exact same ordering. With `@GeneratedValue(IDENTITY)`, sequences/identity counters can keep incrementing across test contexts or resets, complicating fixtures targeting fixed IDs. Real apps can still use auto-generated IDs while tests use stable business keys or capture inserted IDs.

**Why use `LocalDateTime`?** This lesson tests ordering and interval conditions on fixed *local timestamps*. `LocalDateTime` **has no timezone**; the sample avoids UTC offset bugs while focusing on data shapes. For global event timestamps, use `Instant` or `OffsetDateTime` and verify timezone and JDBC mapping separately.

The two entity indexes illustrate distinct access paths:

- `(tenant_id, entry_state, created_at, id)` fits filtering by tenant+status and sorting by time/id.
- `(tenant_id, created_at, id)` fits filtering by tenant and sorting by time/id without status.

Never assume H2 and PostgreSQL choose the same index or execution plan. **Declaring an index does not guarantee a query is fast.** Measure actual plans and latency under representative workloads.

### 5.5. Repository with `count`, `Page`, `Slice`, Seek, and Aggregate

**File `src/main/java/com/example/queryshape/InvoiceEntryRepository.java`:**

```java
package com.example.queryshape;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InvoiceEntryRepository
        extends JpaRepository<InvoiceEntry, Long> {

    long countByTenantId(String tenantId);

    long countByTenantIdAndEntryState(
            String tenantId, String entryState);

    long countByTenantIdAndCustomerRefIsNull(String tenantId);

    long countByTenantIdAndCustomerRef(
            String tenantId, String customerRef);

    long countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            String tenantId,
            LocalDateTime fromInclusive,
            LocalDateTime toExclusive);

    Page<InvoiceEntry> findByTenantId(
            String tenantId, Pageable pageable);

    Page<InvoiceEntry> findByTenantIdAndEntryState(
            String tenantId, String entryState, Pageable pageable);

    Slice<InvoiceEntry> findSliceByTenantIdAndEntryState(
            String tenantId, String entryState, Pageable pageable);

    List<InvoiceEntry>
    findTop10ByTenantIdAndEntryStateOrderByCreatedAtDescIdDesc(
            String tenantId, String entryState);

    @Query("""
            select sum(e.grossCents)
            from InvoiceEntry e
            where e.tenantId = :tenant
              and e.entryState = :state
            """)
    Long sumGrossCents(
            @Param("tenant") String tenantId,
            @Param("state") String entryState);

    @Query("""
            select e
            from InvoiceEntry e
            where e.tenantId = :tenant
              and (
                    e.createdAt > :cursorTime
                    or (e.createdAt = :cursorTime and e.id > :cursorId)
              )
            order by e.createdAt asc, e.id asc
            """)
    List<InvoiceEntry> seekAfter(
            @Param("tenant") String tenantId,
            @Param("cursorTime") LocalDateTime cursorTime,
            @Param("cursorId") Long cursorId,
            Pageable pageable);
}
```

Notes:

1. `countBy...` returns `long` because row counts can exceed `int`.
2. The time-range method uses `GreaterThanEqual` and `LessThan`, expressing **[from, to)** (inclusive start, exclusive end).
3. `Page<T>` includes `totalElements`/`totalPages`, typically requiring Spring Data JPA to run an extra count query.
4. `Slice<T>` only checks whether a next page exists, avoiding total-count overhead in suitable use cases.
5. `findTop10...OrderByCreatedAtDescIdDesc` includes an `id` tie-breaker for identical timestamps.
6. JPQL `sum` returns `Long` matching the `long` field; when **zero rows** match, SQL/JPA `SUM` returns `null` rather than `0`.
7. `seekAfter` is a **manual keyset query**: pass the last seen `(createdAt, id)` pair to fetch the next 40 records. It is **not** the full Spring Data Scroll API and does not provide snapshot consistency across concurrent transactions.
8. `Pageable` in `seekAfter` limits the row count; tests pass `PageRequest.of(0, 40)` without dynamic `Sort`, since JPQL already defines `ORDER BY`.

## 6. JUnit Class Generating the Dataset and Testing Scenarios

**File `src/test/java/com/example/queryshape/InvoiceQueryShapeTest.java`:**

```java
package com.example.queryshape;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.LongStream;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class InvoiceQueryShapeTest {

    private static final int TOTAL = 1_200;
    private static final LocalDateTime BASE =
            LocalDateTime.of(2026, 1, 1, 0, 0);

    private static final Comparator<InvoiceEntry> STABLE_ASC =
            Comparator.comparing(InvoiceEntry::getCreatedAt)
                    .thenComparing(InvoiceEntry::getId);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    EntityManager entityManager;

    @Autowired
    InvoiceEntryRepository repository;

    private static String tenant(int id) {
        return id <= 900 ? "HOT" : "COLD";
    }

    private static String state(int id) {
        boolean paid = id <= 900
                ? (id % 10 < 7)
                : (id % 10 < 2);
        return paid ? "PAID" : "OPEN";
    }

    private static LocalDateTime createdAt(int id) {
        return BASE.plusHours(id % 24);
    }

    private static long grossCents(int id) {
        return id == 900 ? 1_000_000L : 100L + (id % 7);
    }

    private static String customerRef(int id) {
        if (id % 20 == 0) {
            return null;
        }
        if (id % 33 == 0) {
            return "";
        }
        return "CUST-" + (id % 50);
    }

    private static Sort stableSort() {
        return Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id"));
    }

    @BeforeEach
    void seedDeterministicFixtureInTestTransaction() {
        jdbc.batchUpdate(
                """
                insert into invoice_entries (
                    id, tenant_id, entry_state,
                    created_at, gross_cents, customer_ref
                ) values (?, ?, ?, ?, ?, ?)
                """,
                new BatchPreparedStatementSetter() {

                    @Override
                    public void setValues(
                            PreparedStatement ps, int row)
                            throws SQLException {

                        int id = row + 1;

                        ps.setLong(1, id);
                        ps.setString(2, tenant(id));
                        ps.setString(3, state(id));
                        ps.setTimestamp(4,
                                Timestamp.valueOf(createdAt(id)));
                        ps.setLong(5, grossCents(id));

                        String ref = customerRef(id);
                        if (ref == null) {
                            ps.setNull(6, Types.VARCHAR);
                        }
                        else {
                            ps.setString(6, ref);
                        }
                    }

                    @Override
                    public int getBatchSize() {
                        return TOTAL;
                    }
                });

        // Seeded via JDBC; keep no managed entities from the fixture.
        entityManager.clear();
    }

    @Test
    void profileHasExpectedVolumeAndStatusSkew() {
        assertThat(repository.count()).isEqualTo(1_200L);

        assertThat(repository.countByTenantId("HOT"))
                .isEqualTo(900L);
        assertThat(repository.countByTenantId("COLD"))
                .isEqualTo(300L);

        assertThat(repository.countByTenantIdAndEntryState(
                "HOT", "PAID")).isEqualTo(630L);
        assertThat(repository.countByTenantIdAndEntryState(
                "HOT", "OPEN")).isEqualTo(270L);

        assertThat(repository.countByTenantIdAndEntryState(
                "COLD", "PAID")).isEqualTo(60L);
        assertThat(repository.countByTenantIdAndEntryState(
                "COLD", "OPEN")).isEqualTo(240L);
    }

    @Test
    void filterSelectivityDiffersByTenant() {
        long hotPaid = repository.countByTenantIdAndEntryState(
                "HOT", "PAID");
        long coldPaid = repository.countByTenantIdAndEntryState(
                "COLD", "PAID");

        assertThat(hotPaid).isEqualTo(630L);
        assertThat(coldPaid).isEqualTo(60L);

        // 70% of HOT tenant, 20% of COLD tenant.
        assertThat(hotPaid * 100 / 900).isEqualTo(70L);
        assertThat(coldPaid * 100 / 300).isEqualTo(20L);
    }

    @Test
    void nullEmptyAndRepeatedRefsAreDifferent() {
        assertThat(repository.countByTenantIdAndCustomerRefIsNull(
                "HOT")).isEqualTo(45L);

        assertThat(repository.countByTenantIdAndCustomerRefIsNull(
                "COLD")).isEqualTo(15L);

        // Every 33rd id has empty ref, excluding ids with NULL ref.
        assertThat(repository.countByTenantIdAndCustomerRef(
                "HOT", "")).isEqualTo(26L);

        // One customer has multiple invoices; never assume uniqueness.
        assertThat(repository.countByTenantIdAndCustomerRef(
                "HOT", "CUST-7")).isEqualTo(18L);
        assertThat(repository.countByTenantIdAndCustomerRef(
                "COLD", "CUST-7")).isEqualTo(5L);
    }

    @Test
    void halfOpenTimeRangeIncludesStartAndExcludesEnd() {
        LocalDateTime noon = BASE.plusHours(12);
        LocalDateTime onePm = BASE.plusHours(13);
        LocalDateTime twoPm = BASE.plusHours(14);

        // Id=12,36,...,900 -> 38 HOT rows at 12:00.
        assertThat(
                repository
                        .countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                                "HOT", noon, onePm))
                .isEqualTo(38L);

        // 13:00 belongs to the next interval, not the previous one.
        assertThat(
                repository
                        .countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                                "HOT", onePm, twoPm))
                .isEqualTo(37L);
    }

    @Test
    void stablePagingWithTiesDoesNotDuplicateRows() {
        Page<InvoiceEntry> first =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(0, 40, stableSort()));

        Page<InvoiceEntry> second =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(1, 40, stableSort()));

        assertThat(first.getTotalElements()).isEqualTo(630L);
        assertThat(first.getTotalPages()).isEqualTo(16);
        assertThat(first.getContent()).hasSize(40);
        assertThat(second.getContent()).hasSize(40);

        List<InvoiceEntry> combined = new ArrayList<>(
                first.getContent());
        combined.addAll(second.getContent());

        for (int i = 1; i < combined.size(); i++) {
            assertThat(STABLE_ASC.compare(
                    combined.get(i - 1), combined.get(i)))
                    .isLessThan(0);
        }

        Set<Long> ids = new HashSet<>();
        for (InvoiceEntry row : combined) {
            assertThat(row.getTenantId()).isEqualTo("HOT");
            assertThat(row.getEntryState()).isEqualTo("PAID");
            assertThat(ids.add(row.getId())).isTrue();
        }
        assertThat(ids).hasSize(80);
    }

    @Test
    void lastPageHasOnlyRemainingRows() {
        Page<InvoiceEntry> last =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(15, 40, stableSort()));

        assertThat(last.getTotalElements()).isEqualTo(630L);
        assertThat(last.getContent()).hasSize(30);
        assertThat(last.isLast()).isTrue();
        assertThat(last.hasNext()).isFalse();
    }

    @Test
    void sliceHasNextWithoutRequiringTotalCount() {
        Slice<InvoiceEntry> first =
                repository.findSliceByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(0, 40, stableSort()));

        Slice<InvoiceEntry> last =
                repository.findSliceByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(15, 40, stableSort()));

        assertThat(first.getContent()).hasSize(40);
        assertThat(first.hasNext()).isTrue();
        assertThat(last.getContent()).hasSize(30);
        assertThat(last.hasNext()).isFalse();
    }

    @Test
    void seekPaginationMatchesOffsetOnUnchangedFixture() {
        Page<InvoiceEntry> first =
                repository.findByTenantId(
                        "HOT", PageRequest.of(
                                0, 40, stableSort()));

        InvoiceEntry cursor = first.getContent().get(39);

        List<InvoiceEntry> after =
                repository.seekAfter(
                        "HOT", cursor.getCreatedAt(),
                        cursor.getId(), PageRequest.of(0, 40));

        Page<InvoiceEntry> offsetSecond =
                repository.findByTenantId(
                        "HOT", PageRequest.of(
                                1, 40, stableSort()));

        assertThat(after).hasSize(40);
        assertThat(after.stream()
                .map(InvoiceEntry::getId).toList())
                .isEqualTo(offsetSecond.getContent().stream()
                        .map(InvoiceEntry::getId).toList());
    }

    @Test
    void aggregateIncludesLargeOutlierWithoutIntOverflow() {
        long expected = LongStream.rangeClosed(1, 900)
                .filter(i -> i % 10 < 7)
                .map(i -> grossCents((int) i))
                .sum();

        assertThat(repository.sumGrossCents("HOT", "PAID"))
                .isEqualTo(expected);
        assertThat(expected).isGreaterThan(1_000_000L);

        // SUM with no matching rows returns NULL, not 0.
        assertThat(repository.sumGrossCents("MISSING", "PAID"))
                .isNull();
    }

    @Test
    void topTenHasDeterministicTieBreaker() {
        List<InvoiceEntry> top =
                repository
                        .findTop10ByTenantIdAndEntryStateOrderByCreatedAtDescIdDesc(
                                "HOT", "PAID");

        assertThat(top).hasSize(10);
        assertThat(top.get(0).getCreatedAt())
                .isEqualTo(BASE.plusHours(23));

        for (int i = 1; i < top.size(); i++) {
            assertThat(STABLE_ASC.compare(
                    top.get(i - 1), top.get(i)))
                    .isGreaterThan(0);
        }
    }

    @Test
    void emptyTenantProducesEmptyPageAndZeroCount() {
        Page<InvoiceEntry> page =
                repository.findByTenantId(
                        "NOT-PRESENT", PageRequest.of(
                                0, 40, stableSort()));

        assertThat(repository.countByTenantId("NOT-PRESENT"))
                .isZero();
        assertThat(page.getContent()).isEmpty();
        assertThat(page.getTotalElements()).isZero();
        assertThat(page.getTotalPages()).isZero();
    }
}
```

### 6.1. Expectations of the Sample Code

The class has **11 `@Test` methods**, checking:

| Test | Dataset Feature Used | Key Assertions |
|---|---|---|
| `profileHasExpectedVolumeAndStatusSkew` | 1,200 rows; 900/300; status imbalance | Exact six counts |
| `filterSelectivityDiffersByTenant` | Tenant/status correlation | 70% and 20% |
| `nullEmptyAndRepeatedRefsAreDifferent` | NULL/empty/duplicates | 45, 15, 26, 18, 5 |
| `halfOpenTimeRangeIncludesStartAndExcludesEnd` | 24 hours, heavy ties | 12:00 has 38, 13:00 has 37 |
| `stablePagingWithTiesDoesNotDuplicateRows` | 630 PAID HOT, timestamp ties | 80 rows, zero overlap, sorted `(time, id)` |
| `lastPageHasOnlyRemainingRows` | 630 divided by page size 40 | Last page has 30 |
| `sliceHasNextWithoutRequiringTotalCount` | Same filter + page size | First `hasNext`, last does not |
| `seekPaginationMatchesOffsetOnUnchangedFixture` | Keyset with `(time, id)` cursor | 40 IDs match offset page two |
| `aggregateIncludesLargeOutlierWithoutIntOverflow` | 1,000,000-cent outlier | Sum matches fixture oracle |
| `topTenHasDeterministicTieBreaker` | Tied timestamps, DESC sort | 10 rows ordered by time/id |
| `emptyTenantProducesEmptyPageAndZeroCount` | Zero matching rows | Empty page, total = 0 |

**Applicability condition:** assumes Spring Boot 3.x + H2 + Hibernate without custom converters/entities, schema migrations, or conflicting test auto-configuration. This sample was statically reviewed; to verify your specific environment, run the build/test commands below. Do not claim p95 measurements or production benchmarks from this H2 example.

### 6.2. Running Tests with Gradle or Maven

Linux/macOS, matching your project's build tool:

```bash
# Gradle Wrapper
./gradlew test --tests "com.example.queryshape.InvoiceQueryShapeTest"

# Or Maven Wrapper
./mvnw -Dtest=InvoiceQueryShapeTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.queryshape.InvoiceQueryShapeTest"

# Or if the project uses Maven:
.\mvnw.cmd "-Dtest=InvoiceQueryShapeTest" test
```

In multi-module projects, select the module containing the test class. If no Wrapper exists yet, generate one per your build standards or use the CI-pinned Maven/Gradle installation. Inspect the JUnit report to verify **11 tests actually executed**, rather than trusting a green build that skipped cached `UP-TO-DATE` tasks.

### 6.3. Why Seed a JPA Test Using JDBC?

Using `repository.saveAll(...)` right before querying leaves many **managed** entities in the persistence context; subsequent `findById(...)` or queries can be influenced by the first-level cache, JPA dirty checking, and flush timing.

Using `JdbcTemplate.batchUpdate` lets us:

1. Insert 1,200 controlled rows via SQL.
2. Avoid holding 1,200 managed entities in `EntityManager`.
3. Seed faster than looping `saveAndFlush` per entity.
4. Explicitly verify SQL rows through the JPA repository afterward.
5. Leverage `@DataJpaTest`'s default transaction + rollback per test so data never leaks across methods.

**Note:** JDBC seeding executes inside the test transaction when sharing the same `DataSource` and transaction manager in a normal Spring Boot JPA slice. `entityManager.clear()` clears the persistence context without committing the JDBC transaction. If a project configures multiple `DataSource`s or managers, verify JDBC seeding and JPA queries hit the same database.

### 6.4. Why Seed Before Each Test Instead of Once Globally?

Every test must remain independent and runnable standalone from an IDE:

- `@BeforeEach` populates the fixture inside the **test-managed transaction**.
- Each test asserts one contract.
- Spring TestContext rolls back after the method, removing all INSERTs for that method.
- The next test re-seeds from the same formula without depending on IDs or row counts from prior tests.

For hundreds of thousands of rows, re-seeding before every test becomes too slow. In that case:

- Split test tiers (small/shaped logic vs. production-scale volume).
- Use isolated schemas/databases, controlled snapshots/restores, or Testcontainers templates.
- Seed once for a **read-only performance suite** where no test mutates rows, managing lifecycle, cleanup, and parallel isolation explicitly.
- Never use `@TestMethodOrder` as an “optimization” where Test A seeds, Test B reads, and Test C deletes.

### 6.5. SQL Aggregates Should Use `long`, Not Arbitrary `int`

A revenue query computing `sum(gross_cents)` can overflow Java `int` when row counts or outliers are large. In the code above, entity field `grossCents` is `long`, the repository returns `Long`, and the oracle uses `LongStream.sum()`.

Even so, **`long` is insufficient for every monetary case**. When domains involve fractional decimals, multiple currencies, or extreme scales, use `BigDecimal` with explicit rounding, scale, and currency rules. Summing 1,200 rows catches basic mistakes, whereas overflow bugs may surface only past a couple billion; add edge fixtures near numeric limits when needed.

### 6.6. Never Compare Timestamps by Guessing Timezones

The fixture uses `LocalDateTime`. When an application stores timestamps with UTC or offsets, clarify:

- DB column type (`TIMESTAMP [WITH TIME ZONE]` or equivalent).
- Java type (`Instant`, `OffsetDateTime`, `LocalDateTime`).
- JDBC driver/session timezone, DST, and precision.
- Which timezone defines query intervals, and `[from, to)` boundaries after conversion.
- Whether client input carries an offset or local wall time.

For instance, a month crossing a DST transition is not always 30 × 24 hours long in that timezone. Build business-time test bounds from **`Instant` boundaries derived per zone policy** rather than arbitrarily adding hours for monthly reports.

## 7. Additional Boundary Data Needed Depending on Query Type

The 1,200-row dataset covers many dimensions, yet **does not cover every edge case** of a real system.

### 7.1. Counts: 0, 1, N = Page Size, N = Page Size + 1

With page size 40, also test scenarios for:

| Result Count | What to Assert |
|---|---|
| 0 | Empty content, total count 0, no phantom next page |
| 1 | One row, no next page |
| 39 | One partially filled page |
| 40 | One full page, no next page |
| 41 | Two pages, second page has 1 row |
| 80 | Two full pages, third page empty |
| 630 | Last page has 30 rows, `totalPages = 16` |

A query can work for 39 yet break at 40 or 41 due to off-by-one bugs in limit/offset. For `Slice`, verify `hasNext`; for `Page`, also verify total-count semantics. Not every query needs all seven cases—choose boundaries relevant to its contract.

### 7.2. String Semantics: Null, Empty, Whitespace, Case, and Unicode

In SQL:

- `customer_ref IS NULL` is not `customer_ref = ''`.
- `NULL = NULL` does not evaluate like normal equality; use `IS NULL`.
- `"CUST-7"` vs. `"cust-7"` depends on collation and case-sensitivity rules.
- `"A"` vs. `"A "` can differ by column type, collation, and engine.
- Composed vs. decomposed Unicode characters may require a normalization policy.
- Wide `VARCHAR`/`TEXT` values impact row width and index storage.

The sample dataset includes null, empty, and repeated refs; if queries normalize customer names or support international search, create fixtures with Vietnamese diacritics, combining characters, and mixed case, and test against the **real RDBMS collation**. H2 does not replicate PostgreSQL or MySQL Unicode collation rules.

### 7.3. JSON, XML, and Wide Payloads

A table storing multi-kilobyte or megabyte `JSONB`/`TEXT` columns creates very different I/O and memory pressure than a narrow table of integers and short codes. Performance suites should model:

- Typical small payloads.
- p95/p99 payload sizes.
- Very large outlier payloads.
- Missing keys or null fields inside documents.
- Varied JSON shapes when queries filter JSON paths.
- Real DB compression ratios, index overhead, and TOAST/page storage.

Do not scale 1,200 narrow rows up to a million narrow rows and assume it reflects a production table full of `TEXT` or `BLOB` columns.

### 7.4. Join Fan-Out and N+1

Queries joining `orders` and `order_lines` need datasets containing:

- An order with zero lines.
- An order with one line.
- An order with several lines.
- A “whale” order with hundreds or thousands of lines.
- Lines referencing duplicate products/variants with different sequences.
- Orphan/cascade/soft-delete cases where the domain allows them.

If every order in tests has exactly one line, a `JOIN` looks like a one-to-one relation and hides duplicated parent rows or broken pagination counts when fetching collections.

N+1 happens when code fetches N parents and lazy-loads children per parent, issuing many extra SQL selects. Fetching just 2 parents hides the cost; with 100 parents and skewed fan-out, statistics and logs expose it clearly. Still, **avoid brittle exact SQL statement-count assertions** unless your test tightly controls caches, fetch strategies, batch sizes, and lazy initialization.

### 7.5. Soft Deletes, Active/Inactive Flags, and Historical Data

When entities have `deletedAt`, `archived`, `validFrom`/`validTo`, or status workflows, include transitional states:

- active vs. soft-deleted;
- expired yet not purged;
- `validFrom == query boundary`;
- `validTo == query boundary`;
- legacy deprecated statuses still present in DB rows;
- per-tenant archival policies.

A fixture containing only active rows will never catch a query forgetting to exclude soft-deleted data.

### 7.6. Security-Sensitive Data

In multi-tenant queries, **tenant isolation is both a correctness and a security contract**. Asserting `COUNT` alone fails if a query pulls rows from another tenant that happen to sum to the same count. For stronger checks, assert **every returned row belongs to the expected `tenantId`**, and test Spring Security, row-level security, and DB layers appropriately.

Never copy production customer records into tests. Use synthetic data matching aggregate distributions, or data governed/anonymized under security policy—never hardcode real emails, addresses, or tokens.

## 8. Page, Slice, Offset, and Keyset: Which Data Shapes Expose Bugs?

### 8.1. `Page` and Count Semantics

Given:

```java
Page<InvoiceEntry> page =
        repository.findByTenantIdAndEntryState(
                "HOT", "PAID",
                PageRequest.of(15, 40, stableSort()));
```

This is a snippet from Section 6's test class. Since `HOT`/`PAID` has 630 rows and page size is 40, zero-based page 15 returns 30 rows. Spring Data JPA `Page` provides `totalElements=630` and `totalPages=16` for queries like this sample.

Complex custom queries using `JOIN`, `GROUP BY`, or native SQL often require an explicit `countQuery` so totals reflect business entity cardinality rather than raw joined row counts. Never assume count queries are inferred accurately for complex native SQL.

### 8.2. `Slice` Fits When Total Count Is Unneeded

`Slice<T>` focuses strictly on whether another page exists. It typically fetches just enough rows to determine `hasNext`, avoiding total-count overhead for “Load more / Next” UIs.

Switching from `Page` to `Slice` does not solve every performance bottleneck, however. The query may still scan or sort huge row sets, and deep offsets remain expensive—especially when sorting lacks index support.

### 8.3. Stable Sorting Is Mandatory When Ties Exist

If a query specifies only:

```sql
ORDER BY created_at ASC
```

and hundreds of rows share the same `created_at`, relative ordering among tied rows is **undefined**. Adding:

```sql
ORDER BY created_at ASC, id ASC
```

creates a **total ordering** whenever `id` is unique, making paged responses reproducible on an **unchanged dataset**.

In the sample repository, `stableSort()` sorts by `createdAt` and `id`. For the top-10 descending query, the method specifies `OrderByCreatedAtDescIdDesc`.

**Never equate total ordering with snapshot isolation.** If `INSERT`s or `DELETE`s occur between two page fetches, offset pagination can still skip or duplicate rows as positions shift. A stable tie-breaker eliminates nondeterminism among tied rows; it does not freeze the dataset across requests.

### 8.4. Offset Pagination and Deep Pages

`PageRequest.of(100_000, 40)` rarely scales efficiently. The database may have to traverse or sort vast numbers of rows before discarding the offset, just to return 40 rows.

For deeply scrolled feeds, keyset/seek pagination is often preferred. Logical form:

```sql
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = ?
  AND (
       created_at > ?
       OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 40;
```

This is conceptual SQL with cursor placeholders, not a standalone JDBC method. With an index aligned to the filter and sort columns, the DB can seek directly instead of scanning deep offsets. However, `OR` predicates, collations, nullable sort keys, and engine optimizers affect plan selection; inspect plans on the real production DB.

Keyset cursors must include **the entire unique sort key**. A cursor carrying only `createdAt` skips remaining rows sharing that timestamp across page boundaries. Section 6's test uses `(createdAt, id)`.

### 8.5. Static Datasets Do Not Prove Concurrency Behavior

`seekPaginationMatchesOffsetOnUnchangedFixture` proves both strategies return identical IDs when no concurrent writes occur. It **does not prove** how the API behaves under `INSERT` or `DELETE` calls between Page 1 and Page 2.

If a cursor feed is critical to your product, add integration tests with:

- Two separate transactions/connections.
- Deterministic `INSERT`/`DELETE` operations between Page 1 and Page 2.
- Explicit isolation levels and snapshot semantics.
- Clear business rules: “fixed snapshot,” “latest feed,” or “no duplicates”?
- Cursor predicates aligned with ordering and indexes.
- Edge cases with nullable sort keys if allowed.

Never use arbitrary sleeps to reproduce races; coordinate steps deterministically using latches/barriers and controlled transactions.

## 9. Query Plans and Statistics: Why Does the Same SQL Pick Different Plans?

### 9.1. `EXPLAIN` Does Not Mean “Indexes Are Always Better”

Databases choose execution plans based on:

- cardinality estimates, histograms, and most-common values;
- table/index page counts and row width;
- index availability and composite index column order;
- combined selectivity of multiple predicates;
- index scan vs. sequential/table scan costs;
- sort and aggregate costs;
- join ordering, join algorithms, and fan-out;
- `LIMIT`/`OFFSET` and estimated row counts;
- freshness of table statistics.

An index ideal for `tenant_id='COLD' AND entry_state='PAID'` (60/1,200 rows) may lose to a sequential scan for a very common filter on a small table—and that **is not necessarily a bug**.

### 9.2. `EXPLAIN` in H2

H2 supports `EXPLAIN` and `EXPLAIN ANALYZE`. You can inspect:

```sql
EXPLAIN
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = 'HOT'
  AND entry_state = 'PAID'
ORDER BY created_at ASC, id ASC;
```

This diagnostic query runs in H2 when the schema and table exist. `EXPLAIN` shows the estimated plan; **`EXPLAIN ANALYZE` actually executes the query** and reports scan counts as supported by H2. Never run `EXPLAIN ANALYZE` on `UPDATE`/`DELETE` statements in production without strict transaction controls, because they execute side effects.

Diagnostic snippet inside `@DataJpaTest`:

```java
String plan = jdbc.queryForObject(
        """
        EXPLAIN SELECT id
        FROM invoice_entries
        WHERE tenant_id = ? AND entry_state = ?
        ORDER BY created_at, id
        """,
        String.class,
        "HOT", "PAID");

assertThat(plan).isNotBlank();
```

This is a **snippet inside a test context** providing `jdbc` and AssertJ, not a standalone file. It intentionally asserts only that a plan is returned, **without hardcoding** index names or H2 planner text, since planner formatting and cost estimates change across versions while query logic stays valid.

### 9.3. PostgreSQL `EXPLAIN ANALYZE` and Row Estimates

On PostgreSQL, commands like these aid analysis:

```sql
ANALYZE invoice_entries;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = 'COLD'
  AND entry_state = 'PAID'
ORDER BY created_at, id
LIMIT 40;
```

**Run in controlled test environments**, never blindly against live production. In PostgreSQL, `EXPLAIN (ANALYZE)` executes the query; even read-only `SELECT`s consume resources and locks under load.

Inspect:

- **Estimated rows vs. actual rows:** whether the planner estimated selectivity accurately.
- **Loops:** whether nested-loop joins iterate excessively.
- **Sort:** whether sorting happens outside indexes or spills to disk.
- **Buffers:** how much data comes from shared buffers vs. disk reads.
- **Planning time vs. execution time:** whether overhead lies in planning or execution.
- **Index Cond vs. Filter:** which predicates are pushed into the index vs. filtered afterward.
- **Temp files / `work_mem`:** whether sorts or hashes spill to temporary disk files.

When a dataset is tiny or skewed differently from production, `EXPLAIN` output is **unrepresentative** of production plans. A query “using an index” on 1,200 rows does not guarantee low latency at 100 million rows.

### 9.4. Multivariate Statistics for Correlated Data

PostgreSQL supports extended statistics, for example:

```sql
CREATE STATISTICS invoice_tenant_state_stats
    (dependencies, mcv)
    ON tenant_id, entry_state
    FROM invoice_entries;

ANALYZE invoice_entries;
```

This DDL example **belongs strictly in appropriate environments** after checking privileges, DB version, and real need. Extended statistics can improve planner estimates for correlated columns, though they do not magically speed up every query, carry stats-collection cost, and remain one factor among many.

Correctness tests in this lesson need no PostgreSQL statistics because they run on H2. In performance jobs, test against the real DB engine and realistic distributions before deciding whether extended statistics are warranted.

### 9.5. Index Design Must Match Query Shape

Index `(tenant_id, entry_state, created_at, id)` fits equality filters on tenant/status combined with sorting by time/id. A query filtering only `tenant_id` and sorting `created_at, id` benefits from a different index. A frequent, high-volume `customer_ref` count query may justify a tenant/ref index.

**Never index every column** just to appease tests: indexes increase write overhead, storage, and maintenance cost. Choose indexes from actual workloads, query plans, and domain requirements, then test correctness and performance separately.

## 10. Generating Production-Like Datasets Without Copying Sensitive Data

### 10.1. Three Strategies

**Hand-crafted fixtures:** great for edge cases and logic, yet prone to being too small and uniform.

**Deterministic generators:** great for medium datasets with controlled histograms and relationships, easy to reproduce; define distributions and verify summary stats.

**Profile-driven synthetic data:** great for performance jobs. Derive strictly from approved aggregate/anonymized statistics without copying PII or secrets. Preserve statistical correlations without retaining real identifiers.

### 10.2. Distributions to Model Carefully

For heavily skewed data, consider:

- Log-normal distributions for transaction amounts or payload sizes.
- Zipf/Pareto distributions for tenant popularity or hot products.
- Mixture distributions for distinct user segments.
- Piecewise distributions for statuses conditioned on tenant or region.
- Bursty timestamps for peak-hour traffic.
- Correlated variables tying statuses to account age or category.

Picking a convenient probability formula **does not guarantee** realism. Compare generated histograms, percentiles, distinct counts, null rates, rows per tenant, fan-out per parent, and conditional distributions against approved target metrics.

### 10.3. Writing a “Data Profile Contract”

Example specification for a performance job:

```yaml
dataset:
  version: query-shape-v3
  generator_seed: 20261108
  total_rows: 1000000
  partitions:
    tenants: 400
    largest_tenant_share: 0.35
  status:
    paid_share_given_hot_tenant: 0.70
    paid_share_given_cold_tenant: 0.20
  customer_ref:
    null_share: 0.05
    duplicates_allowed: true
  timestamps:
    distribution: bursty
    duplicate_sort_keys: true
  amounts:
    heavy_tail: true
  workload:
    page_size: 40
    query_mix:
      hot_tenant_paid: 0.50
      cold_tenant_paid: 0.15
      tenant_time_seek: 0.35
```

This is a **metadata design example**, not a YAML file consumed by Section 5's application. Ratios are illustrative; substitute real product profiles and requirements. “One million rows” is just one test scale, not a universal standard.

## 11. Query Testing, SQL Logging, and Evidence-Gathering Cost

### 11.1. Inspecting SQL During Logic Tests

With Spring Boot 3 / Hibernate 6, diagnostic test properties include:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Exact logger categories depend on Hibernate/Boot versions; `@DataJpaTest(showSql=false)` in the sample disables SQL logging to avoid flooding output with thousands of `INSERT`s. Enable verbose logging only in targeted diagnostic tests or controlled profiles.

**Never enable `TRACE` bind-parameter logging on production data** because logs can expose PII, tokens, account numbers, and sensitive payloads.

### 11.2. Counting SQL Statements to Detect N+1

Hibernate statistics and SQL logs can help measure query counts. However, an assertion such as:

```java
assertThat(hibernateStatistics.getPrepareStatementCount())
        .isLessThanOrEqualTo(3L);
```

is a **non-standalone illustrative snippet**; it is meaningful only if statistics are enabled, counters are reset at the right moment, and setup queries, lazy associations, caches, and session boundaries are controlled.

Better practice:

- Seed data *before resetting SQL counters*.
- Execute the exact query path plus the DTO/association loading used by the real endpoint.
- Assert query counts or architecturally acceptable upper bounds rather than brittle exact log line counts.
- Run across 1, 10, and 100 parents to verify query counts do not grow linearly (N+1).
- Measure inside a realistic context instead of calling only the repository and skipping DTO mapping that triggers lazy loads.

### 11.3. Performance Is More Than Query Latency

A query returning 10,000 entities may execute fast in SQL while triggering heavy heap allocations, JSON serialization cost, and huge payloads. For HTTP APIs, monitor:

- DB query latency.
- Query count and total DB time per request.
- Result row counts and byte sizes.
- Hibernate entity hydration and first-level cache memory.
- Pagination and count-query overhead.
- Network bytes and HTTP serialization time.
- GC pressure, heap usage, peak RSS, and client timeouts.
- Connection pool saturation under concurrency.

A repository correctness test never replaces end-to-end performance testing; profile endpoints under realistic workloads.

## 12. Anti-Patterns in Query Test Data Design

### 12.1. “Testing 5 Rows in H2 and Claiming Production SLOs”

**Wrong:** treating `< 5 ms` on in-memory H2 as proof that PostgreSQL over a network will stay under `100 ms` at 100 million rows.

**Right:** use H2 tests for query semantics, then test performance on the real DB engine/version with representative datasets, controlled workloads, multiple runs, and percentiles. Inspect plans and row estimates before tuning.

### 12.2. Unseeded Randomness

**Wrong:** generating 1,000 customers with `new Random()`, causing intermittent failures when a rare status disappears or page boundaries shift.

**Right:** use fixed seeds, verify histograms, and add deterministic edge cases so rare states are always covered.

### 12.3. Uniform Data for Heavily Skewed Domains

**Wrong:** giving every tenant 50 rows and 50% `PAID` when production tenants differ by orders of magnitude.

**Right:** preserve top tenants, long tails, and conditional state distributions. Test filters across both popular and rare predicates.

### 12.4. Making Every Timestamp Unique

**Wrong:** generating timestamps with `BASE.plusNanos(id)` so sort keys never tie.

**Right:** generate multiple rows sharing timestamps and always include a unique tie-breaker for stable pagination.

### 12.5. Skipping NULL, Empty, and Duplicate Cases

**Wrong:** populating unique non-null `customer_ref` values everywhere even though the schema permits nulls and duplicates.

**Right:** distinguish `NULL`, `""`, whitespace, and repeated refs; assert exact query predicates and business semantics.

### 12.6. Computing Expected Query Results with the Same Query

**Wrong:**

```java
long expected = repository.countByTenantId("HOT");
assertThat(repository.countByTenantId("HOT"))
        .isEqualTo(expected);
```

This is an **anti-pattern**: calling the same method twice and comparing the outputs proves nothing. Derive expectations independently, such as `HOT = 900` from the generator contract or a separate verified oracle.

### 12.7. Asserting Wall-Clock Milliseconds on Uncontrolled CI

**Wrong:**

```java
long start = System.currentTimeMillis();
repository.findByTenantId("HOT", pageable);
assertThat(System.currentTimeMillis() - start)
        .isLessThan(20);
```

This is an **anti-pattern**, not a reliable performance test. It depends on OS scheduling, CPU contention, JVM/JIT, DB caches, and timer granularity.

**Right:** test correctness in unit/slice tests; measure performance in dedicated suites with warm-ups, controlled workloads, repeated trials, p95/p99 metrics, query plans, and controlled hardware/DB settings.

### 12.8. Committed Data Leaking into Later Tests

**Wrong:** seeding a shared database without cleanup so outcomes depend on test order.

**Right:** in `@DataJpaTest`, seed inside transactional tests with default rollback; in `@SpringBootTest(RANDOM_PORT)`, remember test-thread transactions **do not roll back** server-thread writes. Isolate schemas and clean up at the right transaction boundary.

### 12.9. Checking Only `totalElements` Without Checking Content

**Wrong:** asserting `Page` `totalElements` matches while `content` contains wrong tenants or duplicates.

**Right:** assert total counts, every row's tenant/state scope, page size, ordering, zero overlap, and boundaries. A right count can happen by sheer coincidence with broken filters.

### 12.10. Asserting Plans via Hardcoded Index Names

**Wrong:** asserting `EXPLAIN` output must contain `idx_inv_tenant_state_time_id` across every H2 and PostgreSQL version.

**Right:** use `EXPLAIN` for diagnostics and measure actual rows/plans in matching environments; for regression guards, pin DB versions, datasets, and statistics, tracking plan classes and clear thresholds.

## 13. When You Need to Test Against a Production-Like Database

### 13.1. H2 Is Useful, Yet No Substitute for Real Database Engines

H2 gives rapid feedback on entity mappings, JPQL, and basic sorting/pagination/aggregates. However, it differs from PostgreSQL and MySQL in:

- Optimizer/planner choices and statistics.
- Index types, index-only scans, and partial indexes.
- SQL dialects, functions, collations, and `NULL` ordering.
- JSONB, arrays, full-text search, and partitioning.
- Isolation, locking, and deadlock behavior.
- Timezone handling and timestamp precision.
- Plan stability under heavy skew and large volumes.
- DDL constraints, uniqueness, and deferrable checks.

When production queries rely on PostgreSQL JSONB, trigram search, partial indexes, or recursive CTEs, write **integration tests on real PostgreSQL** instead of forcing H2 to emulate everything.

### 13.2. Testcontainers at the Integration Layer

Run PostgreSQL in Testcontainers to test against the matching major engine version. Sketch configuration for Spring Boot 3.1+:

```java
@Testcontainers
@SpringBootTest
class PostgresQueryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject real repository, seed representative dataset,
    // run queries, assert correctness/plan/performance contract.
}
```

**This is an architectural snippet only**, not a complete test class. It requires `org.testcontainers:postgresql`, `junit-jupiter` / Boot `spring-boot-testcontainers`, a Docker runtime, and matching migrations/schemas. Do not drop this into Section 5's H2 project without adding dependencies and configuration.

When using Testcontainers, match the production PostgreSQL major version, pin image tags, manage reused containers, migrations, DB isolation, cleanup, and CI resources. Never treat container startup overhead as DB query latency.

### 13.3. Staging Datasets and Snapshots

To benchmark millions of rows:

1. Provision production-equivalent schemas, indexes, and constraints.
2. Seed via bulk loading/batch inserts timed separately from query timings.
3. Run `ANALYZE`/statistics updates per production strategy.
4. Warm up query paths and document cache state.
5. Execute a realistic query mix (both popular and rare predicates).
6. Apply controlled concurrency rather than single-client loops.
7. Capture actual plans, latencies, and resource metrics.
8. Flag regressions against baselines/SLOs with sensible tolerances and save artifacts for debugging.
9. Clean up test data or drop isolated schemas/containers.
10. Never use real personal identifiers or customer data without explicit authorization and anonymization.

## 14. Questions to Document in Your Test Plan

| Question | Example Answer from This Lesson's Dataset |
|---|---|
| Which queries are primary paths? | HOT/PAID, COLD/PAID, tenant timeline |
| Which group dominates volume? | HOT has 900 of 1,200 rows |
| Are predicates correlated? | HOT is 70% PAID; COLD is 20% PAID |
| Are there duplicate sort keys? | 24 distinct timestamps across 1,200 rows |
| Are nulls or blanks present? | 60 NULL refs; HOT has 26 blank refs |
| Are many-to-one duplicates present? | `CUST-7` has 18 HOT and 5 COLD rows |
| Are outliers included? | One 1,000,000-cent row |
| What is the page size? | 40 |
| Is there a partial last page? | HOT/PAID 630 → last page has 30 |
| Is there an empty-result case? | Tenant `NOT-PRESENT` |
| Where is the query oracle? | Generator contract, expected counts, half-open boundaries |
| What is the transaction scope? | `@DataJpaTest` transactional, rolled back per method |
| Which DB tests logic? | H2 |
| Which DB tests performance? | Production-matching engine required |
| Where are plans measured? | `EXPLAIN`/`EXPLAIN ANALYZE` in workload integration |
| Are concurrency tests needed? | Yes if paging/feeds receive concurrent writes |

**A strong test dataset carries a documented profile like this**, versioned alongside test code and reviewed whenever queries or business rules evolve.

## 15. Hands-On Exercises and Solutions

### Exercise A. Catching a Pagination Bug

A query uses `ORDER BY created_at DESC`, `LIMIT 40 OFFSET 40`. The table contains 500 rows sharing the same `created_at`. Two runs of Page 2 return different IDs. Is the SQL syntax necessarily invalid?

**Answer:** No; SQL only guaranteed sorting by `created_at`. Within tied timestamps, row order is undefined. Add a unique tie-breaker like `ORDER BY created_at DESC, id DESC` and test with heavy timestamp ties. Under concurrent writes, also define snapshot/cursor semantics.

### Exercise B. What Bugs Does Uniform Data Hide?

Tenant HOT is 70% PAID and COLD is 20% PAID, yet all fixtures use 50%. Why might performance regressions stay hidden?

**Answer:** Cardinality/selectivity estimates and chosen plans shift when distributions and correlations change. Planners pick different indexes, table scans, or joins; uniform tests miss popular vs. rare predicate behavior. Use skewed, correlated workloads with refreshed DB statistics.

### Exercise C. NULL and Blank

A repository defines `findByCustomerRefIsNull()`. Does a row with `customerRef = ""` match?

**Answer:** No; an empty string is distinct from `NULL` in standard SQL semantics (with notable vendor quirks in certain databases). Test both `NULL` and `""` separately, and verify on the real DB engine when compatibility matters.

### Exercise D. Overflowing Revenue Totals

A `SUM(gross_cents)` is mapped to Java `int`. A test with 5 rows of 100 cents each passes. What is the risk?

**Answer:** Once the sum exceeds 2,147,483,647, it overflows or fails conversion. Use `long`/`Long` or `BigDecimal` per domain needs, and include large outliers or near-limit boundary fixtures.

### Exercise E. `Page` vs. `Slice`

An API only displays a “Load More” button without a total record count. Must it use `Page`?

**Answer:** No. `Slice` handles “has next” cleanly and avoids the count query. Test `hasNext` and page boundaries while keeping sorting and pagination datasets realistic.

### Exercise F. Keyset Cursor Missing `id`

A query filters `createdAt > cursorTime` when 100 rows share the timestamp at the page boundary. What goes wrong?

**Answer:** All remaining tied rows at that timestamp get skipped. Cursors must include the full unique sort key, e.g., `(createdAt, id)`, with `createdAt > t OR (createdAt = t AND id > cursorId)` for ascending order.

### Exercise G. Does `EXPLAIN` on H2 Prove PostgreSQL Is Fast?

**No.** H2 and PostgreSQL have different optimizers, statistics, and index capabilities. H2 `EXPLAIN` is useful for learning diagnostics; performance guarantees require the production DB engine, version, schemas/indexes, row counts, and realistic workloads.

### Exercise H. JPA Test Data Keeps Vanishing

You seed 1,200 rows in `@BeforeEach` of a `@DataJpaTest`; the test queries them fine, yet the next test finds nothing until `@BeforeEach` seeds again. Is H2 losing data?

**No.** `@DataJpaTest` opens a test-managed transaction and rolls it back after each method by default. The fixture inside that transaction is undone intentionally to isolate correctness tests.

### Exercise I. Monthly Date Ranges

A report filters `createdAt BETWEEN start AND end` where consecutive periods share the same boundary timestamp. What is the risk?

**Answer:** `BETWEEN` is inclusive on both ends, double-counting rows sitting right on the boundary. Prefer half-open intervals `[from, to)`: `>= from AND < to`, while clarifying timezone and precision rules for the business domain.

### Exercise J. Optimizing 30-Second Test Seeds

A test class has 100 methods, each seeding 1 million rows. Should you delete all large-data tests?

**No.** Separate fast logic-shape tests from scheduled performance/integration suites. Use reproducible isolated snapshots or bulk loaders for large suites while keeping fast correctness tests with edge cases. Never drop volume validation when the business relies on it—reorganize how it runs.

### Exercise K. Right `COUNT`, Wrong Tenant

A repository method returns 40 rows, yet several belong to another tenant. Why isn't a count assertion enough?

**Because** hitting 40 can be pure luck. Assert the `tenantId` on every returned row, and for complex queries combine API/security-scope tests with database row-level security where applicable.

### Exercise L. Test Timestamps Drifting Today

A fixture uses `LocalDateTime.now()` and filters by UTC midnight—passing in the morning and failing in the afternoon. How do you fix it?

**Answer:** Use fixed instants, an injected/fake `Clock`, an explicit timezone policy, and explicit interval boundaries. Never depend on the CI runner's local timezone for expected query results.

## 16. Checklist Before Calling Query Tests Trustworthy

- [ ] Does the query spec document tables, predicates, joins, sorting, pagination, and aggregates?
- [ ] Does the dataset have the **row count** needed for either logic or performance goals?
- [ ] Are **histograms and conditional distributions** defined rather than just total `N`?
- [ ] Are popular and rare values, plus large and small tenants, represented?
- [ ] Are cross-column correlations modeled when real workloads exhibit them?
- [ ] Are `NULL`, blank strings, duplicates, and outliers included per schema/business constraints?
- [ ] Are tied timestamps/sort keys included when real data can tie?
- [ ] Are counts `0`, `1`, `page size`, `page size + 1`, and `last page` covered?
- [ ] Are half-open `[from, to)` intervals and timezone/precision policies verified?
- [ ] Is an explicit unique tie-breaker used for stable pagination on static datasets?
- [ ] For keyset pagination, does the cursor carry all sort keys?
- [ ] When concurrent writes happen between pages, are dedicated concurrency/snapshot tests present?
- [ ] Are test oracles independent of the query under test?
- [ ] Are all returned rows checked for expected tenant/scope rather than count alone?
- [ ] Are count queries and `Page.totalElements` checked when joins or grouping exist?
- [ ] Are aggregates tested with outliers and empty/null results?
- [ ] Are fixtures deterministic with documented seeds/versions and reproducible builds?
- [ ] Can tests run standalone without depending on execution order?
- [ ] Do setup and cleanup respect transaction boundaries (`@DataJpaTest` rollback or explicit cleanup)?
- [ ] Are production PII and secrets absent from fixtures and logs?
- [ ] Are correctness assertions separated from flaky millisecond benchmarks?
- [ ] Do performance jobs run on DB engines, versions, schemas, and indexes matching production?
- [ ] Are statistics/`ANALYZE` updated before inspecting plans?
- [ ] Does the workload mix cover representative popular and rare predicates?
- [ ] Are DB latency, row counts, count queries, N+1, memory/GC, and network metrics tracked where relevant?
- [ ] Do tests avoid single-run comparisons or brittle hardcoded optimizer index names?
- [ ] Are Testcontainers or real-engine tests present when relying on vendor SQL dialects, indexes, collations, or JSONB?
- [ ] Are schemas, containers, and bulk fixtures cleaned up cleanly after performance runs?
- [ ] Do build wrappers and JUnit reports prove tests ran rather than being skipped or cached?

## 17. Conclusion

**The quality of query tests depends not just on row counts, but on how data is distributed and which traits can alter query results or execution plans.** A purposefully designed 1,200-row fixture—900/300 across tenants, 70%/20% status skew, NULL/blank/duplicate refs, tied timestamps, and outlier amounts—catches far more correctness bugs than thousands of uniform rows.

In Spring Boot, use **`@DataJpaTest` with deterministic fixtures** for filter, count, aggregate, pagination, and query-semantics contracts; use **real-database integration/performance suites** when validating optimizers, scale, indexes, concurrency, or production latency. Keep expected results independent of the query under test, enforce stable tie-breaker ordering, maintain reproducible dataset profiles, and align cleanup with transaction boundaries.

A trustworthy query test answers three questions: **which data characteristics were chosen to represent the workload, what did the query prove, and what are the limits of that evidence?**

## Official References

- [Spring Boot 3.5 — `@DataJpaTest`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): JPA slice, embedded database, default rollback.
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): query method names, `Page`/`Slice`, `Pageable`, sorting, pagination, keyset.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Query`, named parameters, native SQL count queries, query rewriting, scrolling.
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): `Page`, `Slice`, `Sort`, `Pageable`, `Window`, `ScrollPosition`.
- [Hibernate ORM — User Guide](https://docs.hibernate.org/stable/orm/userguide/html_single/): JDBC batching, fetching, N+1, query pagination, JPA persistence context.
- [H2 — SQL Commands](https://h2database.github.io/html/commands.html): `EXPLAIN`, `EXPLAIN ANALYZE`, H2 DDL and SQL dialect.
- [PostgreSQL 17 — Planner Statistics](https://www.postgresql.org/docs/17/planner-stats.html): histograms, most-common values, extended statistics, `ANALYZE`.
- [PostgreSQL 17 — Using EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html): estimated/actual rows, buffers, plan evaluation.
- [Spring Boot — Testcontainers Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, Docker-based integration tests.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction rollback, fixture lifecycle, and thread boundaries.
