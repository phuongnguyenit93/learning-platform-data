# Performance Testing with Realistic Databases and Data

A Spring Data JPA query running fast on a few dozen rows in H2 does not prove it will perform well on a real database with hundreds of thousands or millions of rows. Performance depends on the database engine, schema, indexes, data volume and distribution, table relationships, caches, connection pools, and concurrency levels.

Performance testing is valuable when the environment and data reflect real-world workloads closely enough to guide decisions. This lesson covers spinning up a test database with Testcontainers, generating representative data, measuring query counts and latency, reading execution plans, and designing repeatable tests.

> The Java snippets below are excerpts for a Java 17+ project using Spring Boot 3+ and `spring-boot-starter-data-jpa`. They illustrate configurations and methods to integrate into a project, not standalone programs runnable directly via `javac`/`java`.

## 1. Defining What to Measure

Before writing tests, define the performance question the test must answer. Common goals include:

- Does a search or pagination query maintain acceptable latency when the table grows to expected scale?
- Does an API trigger N+1 queries when loading entities with relationships?
- Does a new index reduce query duration and blocks read?
- Does a bulk write operation sustain throughput as record counts grow?
- Does the connection pool exhaust when many requests hit the database simultaneously?
- When many transactions run concurrently, do lock waits, deadlocks, or timeouts spike?

Choose metrics aligned with the goal. Useful metrics include:

| Group | Metrics | Meaning |
|---|---|---|
| Latency | p50, p95, p99 | Response time at the median and slow tail percentiles |
| Throughput | requests/second or operations/second | Completed operations per unit of time |
| Stability | error rate, timeouts, retries | Fraction of requests failing or requiring retries |
| SQL | prepared statement count, query count, SQL time | Detecting N+1 or expensive queries |
| Database | CPU, I/O, buffer hits/reads, lock waits | Identifying database bottlenecks |
| Connection pool | active, idle, pending, timeouts | Detecting connection exhaustion or acquisition waits |
| JVM | heap, GC pauses, CPU | Separating ORM/JVM overhead from database costs |

Do not measure only a single invocation's time. A single measurement is skewed by JVM startup, connection creation, query plan compilation, caching, and background load. Measure repeatedly after a warm-up phase and compare percentiles rather than averages alone.

## 2. Using the Right Database Engine

H2 or in-memory databases are handy for unit tests and basic mapping checks, but do not fully represent PostgreSQL, MySQL, Oracle, or SQL Server. Differences in dialects, data types, indexes, collations, execution planners, isolation levels, and SQL handling can yield vastly different performance results.

For integration/performance tests, use the same database engine and a version close to deployment. Testcontainers can launch a real database inside Docker per test suite or application context. The example below uses PostgreSQL:

**Required test dependencies** (versions managed via Spring Boot dependency management or the Testcontainers BOM):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot supports `@ServiceConnection` to auto-configure the connection from the container. You can declare the container as a Spring bean so its lifecycle aligns with the application context:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class TestDatabaseConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Then import the configuration into your integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(TestDatabaseConfiguration.class)
class OrderRepositoryPerformanceIT {

    @Test
    void applicationConnectsToPostgres() {
        // The Spring context is now connected to PostgreSQL in Testcontainers.
    }
}
```

This setup requires a Docker runtime supported by Testcontainers. The `spring-boot-testcontainers` dependency provides `@ServiceConnection` integration. If configuring manually, register JDBC URL, username, and password via `@DynamicPropertySource`.

Using a Spring-managed container aligns container lifecycle with the application context Spring caches between tests. If using JUnit `@Testcontainers` with a static `@Container`, watch out that the container can stop after a test class while Spring keeps the cached application context for reuse in another test. Spring Boot recommends managing containers as beans when contexts may be cached and reused.

## 3. Generating Data with Realistic Scale and Distribution

Record count is only part of test data. A good fixture should simulate:

- Table sizes close to expected operational scale, across both primary and related tables.
- Value distribution: common/rare statuses, null values, date ranges, and skewed data groups.
- Relationship cardinality and distribution: how many orders per customer, how many line items per order.
- String lengths, JSON/blob sizes, and columns frequently filtered or sorted.
- Ratio of new/old data and selectivity of query predicates.
- Indexes, foreign keys, unique constraints, and migrations matching production.

For instance, a table with 100,000 orders where only 10 match a queried rare status produces a different query plan than one where 100,000 orders are split evenly across statuses. A date-range query also needs data spanning months/years rather than every row sharing the same timestamp.

Data can be generated using test migrations, SQL fixtures, `JdbcTemplate` batch inserts, or a dedicated data generator. With PostgreSQL, `generate_series` builds large fixtures quickly. Illustrative SQL:

```sql
INSERT INTO purchase_order (status, total_amount, created_at)
SELECT
    CASE WHEN n % 20 = 0 THEN 'CANCELLED' ELSE 'PAID' END,
    (100 + (n % 50000))::numeric / 100,
    now() - (n || ' seconds')::interval
FROM generate_series(1, 100000) AS n;
```

This statement inserts 100,000 orders with a 95/5 status skew and spread-out creation timestamps. This is simple synthetic data; realistic workloads may also need customers, order lines, addresses, histories, and more complex distributions.

Load fixtures before the measurement section. Never include data generation time in the query benchmark duration. For very large volumes, load in batches and avoid retaining all entities in the persistence context or heap. You can use JDBC batching to seed fixtures rapidly, then exercise JPA/repositories for the access path under test.

Production data must be anonymized or synthesized before entering test environments. Preserving distribution and relationships lets you evaluate performance without bringing personal information into fixtures.

## 4. Using Production-Like Schema and Configuration

The test database should be built using the same migrations deployed to production, such as Flyway or Liquibase. Do not rely solely on `hibernate.ddl-auto=create` if production uses migrations, because auto-generated schemas can miss real indexes, constraints, data types, or optimized structures.

Verify the following before measuring:

- Same major database version and key extensions.
- Same migrations, indexes, constraints, and data types.
- Comparable connection pool configuration and connection limits.
- Appropriate isolation levels and transaction settings.
- Hibernate/JPA settings, fetch strategies, and batch sizes close to the real app.
- First-level, second-level, and query caches enabled/disabled matching the scenario under test.

A database container can still differ from production in CPU, RAM, disk, network, and server tuning. Thus, Testcontainers is great for integration checks and controlled comparisons, but benchmarks on a developer laptop do not automatically represent production latency. For capacity or SLA decisions, use a controlled benchmark environment close to deployment infrastructure.

## 5. Writing Repository Integration Tests

Example repository using a projection to select only required fields, avoiding loading full entities when the screen only needs partial data:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<OrderSummary> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
```

Projection:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface OrderSummary {
    Long getId();
    BigDecimal getTotalAmount();
    Instant getCreatedAt();
}
```

An integration test can verify the query works on PostgreSQL and returns the expected page size:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootTest
@Import(TestDatabaseConfiguration.class)
class OrderRepositoryPerformanceIT {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void loadsPageWithBoundedStatementCount() {
        // Representative fixture was already seeded before measuring.
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();

        statistics.setStatisticsEnabled(true);
        statistics.clear();

        Page<OrderSummary> page = repository.findByStatus(
                OrderStatus.PAID,
                PageRequest.of(
                        0,
                        50,
                        Sort.by(Sort.Direction.DESC, "createdAt")));

        long statements = statistics.getPrepareStatementCount();

        assertThat(page.getContent()).hasSize(50);
        assertThat(statements).isLessThanOrEqualTo(2);
    }
}
```

`Statistics` is a Hibernate-specific API. `getPrepareStatementCount()` checks how many prepared statements were acquired during the measured interval. For a paginated projection query, there may be one content query and one count query; specific bounds must match your application's actual queries.

This example assumes the fixture already has enough PAID rows and the test runs in isolation. Hibernate statistics are global at the `SessionFactory` level, so do not use this reset-and-measure pattern alongside other tests executing concurrently on the same context. Statistics also add overhead; enable only for diagnostics, not as final latency benchmarks.

Counting queries helps catch N+1, yet does not prove a query is fast. A single SQL statement can still full-scan a table, join too many rows, or return huge payloads. Combine statement counts with execution plans and latency.

## 6. Measuring Performance Repeatably

A measurement process should clearly separate phases:

1. **Setup:** start the app and database, run migrations, load fixtures, and verify data.
2. **Warm-up:** send trial requests so JVM JIT, connection pools, ORM metadata, and query plan caches stabilize.
3. **Measure:** run the same workload for a predefined duration or iteration count.
4. **Repeat:** perform multiple measurement rounds under equivalent conditions; avoid conclusions from a single run.
5. **Analyze:** compare p50/p95/p99, throughput, error rate, query counts, and database resources.
6. **Record results:** log commit, configuration, database version, fixture size, concurrency, and cache state for reproducibility.

An example workload scenario might consist of:

- 70% requests searching orders by status and date range.
- 20% requests opening order details along with customer and line items.
- 10% requests updating statuses or writing data.

These ratios are examples only. Derive distributions from anonymized logs/metrics or business requirements to match your application closely. Beyond request ratios, simulate concurrent users, think time, bursts, and sustained run duration.

Record at a minimum:

- p50, p95, and p99 latency.
- Throughput over the same measurement window.
- Error rates, timeouts, and retries.
- SQL statements per request or use case.
- Database CPU, memory, disk I/O, buffer hits/reads, and lock waits.
- Connection pool active/idle/pending counts and connection acquisition waits.
- JVM heap, GC pauses, and CPU.

Avoid asserting things like "query must finish under 50 ms" across arbitrary CI runners whose hardware resources are uncontrolled. Busy CI machines, cold caches, or variable disk speeds cause flaky tests. Use CI to guard deterministic invariants like query count, row count, absence of N+1, and pagination correctness. Measure latency/throughput against baselines on dedicated runners or fixed-spec benchmark environments, using regression thresholds buffered for observed variance.

## 7. Reading Execution Plans to Find Bottlenecks

When a query is slow, take the actual SQL and representative parameters and inspect the database execution plan. With PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total_amount, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN` shows how the database intends to execute the statement. `EXPLAIN ANALYZE` runs the real statement and reports actual row counts, per-node timings, and buffer metrics. Check:

- Whether sequential scans or index scans make sense for the number of rows read.
- Whether estimated rows match actual rows closely.
- Whether large sorts or temporary disk spills occur.
- Whether join strategy and join order are appropriate.
- What buffer hits/reads indicate about memory vs. I/O access.
- Whether indexes support both filter predicates and sort order.

`EXPLAIN ANALYZE` executes the statement, including writes. Only run it on recoverable test/staging databases; for DML, wrap in a transaction and `ROLLBACK` when appropriate. Never test an impactful update/delete on production just for timing. Its output also excludes full network transmission to the application and includes measurement overhead, so it is not identical to end-to-end request latency.

After changing an index or query, re-run the same workload and dataset. Do not add indexes by guesswork: indexes increase write overhead and storage, so prove benefits across both affected reads and writes.

## 8. Sources of Bias in Benchmarks

### Data Too Small or Too Uniform

Small tables can lead the database to pick sequential scans even though production uses indexes. Data with only a few repeated values also fails to simulate real distributions and planner statistics. Create sufficiently large, diverse fixtures and update database statistics when needed.

### Uncontrolled Caching

The first run may read from disk, while subsequent runs hit database buffer caches or OS page caches. Hibernate's second-level cache and query cache can also alter how many queries reach the database. State explicitly whether you are measuring cold-cache or warm-cache, keep states equivalent across compared runs, and never mix the two.

### SQL Logging Inside the Measurement Zone

Enabling full SQL or TRACE bind parameter logging can drastically slow the application and produce massive logs. Use logging to diagnose a short scenario; disable or reduce logging during formal performance runs. Avoid logging sensitive values.

### Including Setup Time in Measurements

Do not include container startup, migrations, fixture loading, context initialization, or warm-up in query latency when measuring queries. Conversely, if measuring application cold start, measure it separately as its own scenario.

### Test Transactions Differing from Real Requests

Spring TestContext often runs `@Transactional` tests inside a test-managed transaction that rolls back when the test finishes. If a service is called inside that test, the service's transaction may join the test transaction due to `REQUIRED` propagation. This differs from HTTP requests where each request opens and commits its own transaction. When measuring actual transaction lifecycles, structure tests so transactions open and close at the exact boundaries under test.

## 9. Distinguishing Integration Tests, Load Tests, and Microbenchmarks

- **Integration test:** verifies mappings, queries, transactions, migrations, and interaction with a real database. Testcontainers fits well for consistent dependencies.
- **Performance regression test:** runs repeatable workloads and tracks query counts or stable metrics to catch regressions.
- **Load/stress test:** sends many concurrent requests through the application, measuring p95/p99, throughput, error rates, and resource limits. Tools like Gatling, k6, or JMeter can be used.
- **Microbenchmark:** measures a tiny computation inside the JVM. JMH fits this purpose; do not use a simple `System.nanoTime()` loop to draw conclusions about full Spring Data JPA + database performance.

Measuring from an HTTP endpoint captures controller, serialization, service, ORM, JDBC, network, and database. Measuring a repository directly bypasses part of that stack. Choose the measurement level matching your question and state the metric's exact scope.

## 10. Checklist Before Accepting Results

- Test database matches production engine and is close in version.
- Schema, migrations, indexes, and constraints match the deployment environment.
- Fixtures match realistic scale, distribution, relationships, and edge values.
- Data is loaded outside the measurement region and is reproducible.
- Warm-up, cache state, concurrency, and measurement duration are defined.
- p50/p95/p99, throughput, error rates, and resources are recorded.
- Query count is checked to catch N+1, without substituting query count for latency.
- Execution plans are analyzed with representative parameters and data.
- SQL logging or fixture setup does not distort measured timings.
- Comparisons run on stable configurations with details saved for repeatability.
- Integration tests, regression tests, load tests, and microbenchmarks are separated by goal.

Performance testing with realistic databases and data uncovers issues before deployment: poor query plans, missing indexes, N+1, connection pool contention, or excessive ORM overhead. Reliable results require a representative dataset, repeatable environment, and multiple complementary metrics rather than a single timing number.

## References

- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java — PostgreSQL module](https://github.com/testcontainers/testcontainers-java/blob/main/docs/modules/databases/postgres.md)
- [Hibernate ORM — Statistics API](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/Statistics.html)
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)