# Connection Pools in Spring Batch: Configuration and Performance Optimization

A Spring Batch job processing millions of records can still run slowly even when CPU has plenty of headroom. A common culprit is **failing to acquire a database connection in time**. The reader waits for a connection, the writer waits for a connection, a transaction stays open without committing, or `JobRepository` runs out of connections to record status updates. Adding more threads to "run faster" sometimes makes matters worse as all threads contend for a bounded connection pool.

This lesson belongs to **Spring Batch Core Processing → Performance** and covers how connection pools operate inside a batch job, configuring **HikariCP** with Spring Boot, identifying connection demands across readers/writers/transactions/metadata, budgeting pool capacity for concurrent jobs, measuring real metrics, and resolving pool exhaustion without sacrificing data correctness.

Examples use Java 17, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, HikariCP, and a relational database. Configuration values in the examples are illustrative starting points—**not universal optima for every system**.

## 1. What Problem Does a Connection Pool Solve?

Opening a fresh physical connection to a database incurs overhead: TCP/TLS handshakes, authentication, session creation, transaction initialization, and database-side memory allocation. Opening and closing a physical connection for every small query is wasteful. A **connection pool** maintains a set of reusable connections:

```text
               Spring Batch application
        ┌─────────────────────────────────┐
        │ Job A: chunk worker 1           │
        │ Job A: chunk worker 2           │
        │ Job B: writer / listener        │
        │ JobRepository metadata         │
        └───────────────┬─────────────────┘
                        │ getConnection()
                        ▼
             ┌──────────────────────┐
             │ HikariCP             │
             │ active:  3           │
             │ idle:    2           │
             │ max:    10           │
             │ pending: 0           │
             └───────────┬──────────┘
                         │
                         ▼
                   Database server
```

To code using a `DataSource`, the pool hands out a `Connection` wrapper manageable by Spring transactions. When application code calls `close()` per contract, the underlying physical connection is normally **returned to the pool** for reuse—it does not mean the TCP socket is closed immediately.

### 1.1. Limits to Keep in Mind

| Parameter / State | Meaning | What Happens Under Overload |
| --- | --- | --- |
| `maximumPoolSize` | Maximum connections the pool manages concurrently | Additional requests block waiting for a free connection |
| `minimumIdle` | Idle connections Hikari tries to maintain | Not a "minimum per-job reserved quota" |
| `connectionTimeout` | Maximum time a request waits to borrow a connection | Throws an exception upon expiration |
| `maxLifetime` | Maximum lifetime of a connection in the pool before retirement | Old connections are replaced once idle/returned |
| `idleTimeout` | Maximum idle time before a connection can be evicted | Only applies when the pool allows shrinking below max |
| `active` | Connections currently borrowed | Sustained high values signal heavy load or long hold times |
| `idle` | Connections currently available in the pool | Sustained 0 may indicate insufficient capacity |
| `pending` | Requests waiting to acquire a connection | Continuous growth signals a bottleneck needing investigation |

**A larger pool does not automatically mean a faster job.** The database also has to manage transactions, locks, per-session memory, I/O, and concurrency. Expanding a pool from 10 to 100 when the database only handles 12 concurrent queries efficiently can lower throughput, worsen lock waits, and degrade other applications sharing the database.

## 2. Where Does a Batch Job Use Connections?

Spring Batch has two primary groups of database consumers:

1. **Batch infrastructure:** `JobRepository` persists `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, and status transitions to the `BATCH_*` tables.
2. **Business data:** readers query sources, processors may perform lookups, writers persist results, and listeners or services may run additional queries.

In a simple Spring Boot setup, both groups **share a single `DataSource` and Hikari pool**. When multiple DataSources are configured, each pool has its own limits; idle connections in one pool do not help operations waiting on another pool.

```text
                              Spring Batch job
                                    │
               ┌────────────────────┴───────────────────┐
               │                                        │
        JobRepository                          Business processing
        BATCH_* tables                         reader / writer / lookup
               │                                        │
               └───────────────┬────────────────────────┘
                               ▼
                      DataSource + HikariCP
                               ▼
                            Database
```

When using two DataSources:

```text
JobRepository ──> batchMetaDataSource ──> batch-meta-pool ──> Metadata DB/schema
Business I/O  ──> businessDataSource  ──> business-pool   ──> Business DB/schema
```

Splitting pools can isolate metadata traffic from business workloads. However, it adds configuration complexity, total connection count, transaction rules, and the risk of wiring the wrong DataSource. Split pools only for a clear operational reason and audit total connection budgets against the database.

### 2.1. Connections and Chunk Transactions

A chunk-oriented step typically executes:

```text
BEGIN TRANSACTION
    read item(s)
    process item(s)
    write chunk
COMMIT
```

Within a JDBC transaction, a connection is bound to the transaction and typically held until commit or rollback once acquired. Depending on how readers, writers, and transaction managers are configured, **not every action in a chunk uses the exact same single connection**:

- A `JdbcBatchItemWriter` sharing the DataSource and transaction manager participates in the transaction's managed connection.
- A cursor-based reader may hold a separate dedicated connection across the step's lifecycle.
- A `JdbcTemplate` targeting a secondary DataSource borrows from that DataSource's pool.
- `JobRepository` updates use the batch infrastructure's configured DataSource and transaction semantics.
- A processor making HTTP or remote API calls holds any already-borrowed transactional connection idle while waiting on the network.

Measure **how many connections each execution holds concurrently and for how long**, rather than merely counting SQL statements.

### 2.2. Which Readers Hold Connections Long-Term?

| Reader Type | Connection Characteristics | Typical Impact |
| --- | --- | --- |
| `JdbcCursorItemReader` | Typically opens a JDBC cursor and holds a connection while reading; transaction sharing depends on config | Long jobs occupy a connection continuously, even when the processor is slow |
| `JdbcPagingItemReader` | Executes paginated queries; borrows connections per query | Suitable when avoiding long-lived cursors; requires deterministic sort keys |
| `JpaPagingItemReader` | Uses JPA `EntityManager`, paging, and reader-managed transactions | Watch persistence context size, fetches, and the JPA DataSource |
| `FlatFileItemReader` | Reads files; needs no JDBC connection for reading | Writer and metadata still require connections |
| `RepositoryItemReader` | Depends on repository and transaction setup | Inspect actual SQL/ORM behavior rather than guessing |

By default, `JdbcCursorItemReader` uses a separate connection for its cursor. An extended shared-connection option (`useSharedExtendedConnection`) exists for certain setups, requiring compatible DataSource wrappers and transaction configuration; do not enable it merely to "save one connection." Also note that **leak detectors** may warn about long-held cursor connections even when code behaves normally. Inspect the reader's full lifecycle before treating it as a leak.

## 3. Configuring HikariCP in Spring Boot

Spring Boot automatically selects **HikariCP** when Hikari is on the classpath and JDBC/JPA DataSource auto-configuration is active. With standard Spring starters, a batch app uses Hikari without manually instantiating `HikariDataSource`.

Example `application-batch.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/reporting
    username: ${BATCH_DB_USERNAME}
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: reporting-batch-pool
      maximum-pool-size: 12
      connection-timeout: 20000
      validation-timeout: 5000
      max-lifetime: 1500000

  batch:
    jdbc:
      initialize-schema: never
```

Here `spring.datasource.hikari` configures the Hikari pool for Boot's primary DataSource. Timeout and lifetime settings are in **milliseconds**. For instance, `connection-timeout: 20000` lets a caller wait up to ~20 seconds for a connection before failing.

Provide `BATCH_DB_USERNAME` and `BATCH_DB_PASSWORD` via secure environment configuration; never commit secrets to source control or log secret properties. `initialize-schema: never` assumes the `BATCH_*` tables already exist via migrations; do not set this if your environment lacks metadata tables.

### 3.1. Understanding Key Hikari Parameters

| Hikari Property | Purpose | Selection Guideline |
| --- | --- | --- |
| `maximum-pool-size` | Caps total connections in the pool | Size for real concurrency, hold time, and DB budget |
| `minimum-idle` | Keeps idle connections warm to cut acquire latency | Can be omitted to keep a fixed-size pool per Hikari's default strategy |
| `connection-timeout` | Max wait time when borrowing a connection | Long enough for brief bursts, short enough not to hide sustained exhaustion |
| `validation-timeout` | Max wait for connection liveness checks | Must be shorter than `connectionTimeout` |
| `max-lifetime` | Retires connections after a maximum age in the pool | Set shorter than DB/proxy connection lifetime limits if infrastructure enforces them |
| `idle-timeout` | Evicts idle connections when shrinking is enabled | Has little effect when the pool is fixed at max size |
| `keepalive-time` | Periodically validates/pings idle connections | Helpful when proxies or load balancers drop idle TCP sockets |
| `leak-detection-threshold` | Logs a warning when a connection is borrowed too long | Diagnostic tool; prone to false positives on cursors or long transactions |

Several properties interact with one another. For example, `idleTimeout` depends on `minimumIdle`, and `keepaliveTime` must be tuned relative to `maxLifetime`. Never tweak values blindly; verify rules for your HikariCP version and monitor after changes.

HikariCP defaults to `maximumPoolSize=10` when unspecified, but **never assume the default is sufficient** for multi-threaded jobs. Setting a low `minimum-idle` lets the pool shrink during quiet periods at the cost of re-creating connections under load spikes. For bursty batch jobs, a fixed-size pool often reduces startup variance.

### 3.2. Do Not Create a Second DataSource Unnecessarily

The snippet below shows how to declare a bean **only when a custom/separate DataSource is genuinely required**, not for standard Boot apps:

```java
@Bean
@ConfigurationProperties("spring.datasource.hikari")
HikariDataSource batchDataSource() {
    return DataSourceBuilder.create()
            .type(HikariDataSource.class)
            .build();
}
```

This merely illustrates binding: it still requires URL/credentials configuration, careful attention to `jdbcUrl` vs. `url` when binding directly to Hikari, and proper DataSource wiring for Spring Batch. **Do not paste this into an auto-configured app and accidentally spin up a competing pool without auditing existing beans.** Most applications only need `spring.datasource.hikari.*` properties.

In Spring Boot, if you split metadata and business DataSources, wire the primary DataSource, `@BatchDataSource`, and transaction manager according to **your exact Spring Boot/Batch version**. A misplaced `@Primary` can send batch metadata to the business DB or run writers against the wrong DataSource.

## 4. Pool Size and Worker Threads Must Be Sized Together

Consider a step using eight worker threads where each worker occasionally needs a business connection. If the pool holds only four connections, four workers wait:

```text
Executor: 8 workers        Hikari pool: maximumPoolSize = 4

W1 ── borrowed conn #1
W2 ── borrowed conn #2
W3 ── borrowed conn #3
W4 ── borrowed conn #4
W5 ── waiting
W6 ── waiting
W7 ── waiting
W8 ── waiting
```

When workers hold connections across slow transactions, sizing the pool below or even equal to thread count does not fix every bottleneck. Measure acquire times, hold durations, lock waits, and SQL execution times.

### 4.1. Workload Connection Budget

An initial estimation model:

```text
Required pool capacity ≈
    peak concurrent borrowed connections by active chunk workers
  + connections held by long-lived cursors / streaming readers
  + concurrent metadata / listeners / auxiliary operations
  + small operational headroom
```

This is a **concurrency budget**, not a rigid formula, because a worker may hold 0, 1, or multiple connections at different moments.

Peak measurement example:

| Component | Peak Concurrent Borrowed Connections |
| --- | ---: |
| Job A: 4 chunk workers | 4 |
| Job B: 3 chunk workers | 3 |
| Two long-lived cursor readers | 2 |
| Concurrent metadata and auxiliary queries | 1 |
| Short-term headroom | 2 |
| **Reference pool budget** | **12** |

Choosing `maximum-pool-size: 12` here assumes these workloads share the same pool and the database has capacity. If readers or metadata use a separate pool, budget each pool independently rather than summing blindly.

### 4.2. Total Database Capacity Matters More Than Any Single App

Suppose the database allows 100 connections total, reserving 20 for admin tasks, replication, and other services. Three batch replicas configured with max pool size 30 each could demand 90 connections and exceed the remaining budget of 80.

```text
Database allowed connections:            100
Reserved / other applications:           20
Available to batch applications:         80

3 replicas × maxPoolSize 30 = 90   --> may exceed budget
3 replicas × maxPoolSize 20 = 60   --> leaves headroom for spikes
```

This is a worst-case ceiling calculation—pools do not always open their full max simultaneously. When scaling containers, ephemeral jobs, or autoscaled pods, calculate **max concurrent instances × pools per instance × `maximumPoolSize`**. Each JVM replica owns an independent pool; HikariCP does not coordinate connection limits cluster-wide.

### 4.3. Measure Throughput, Not Just Pool Occupancy

A pool showing `active=12/12` continuously is not necessarily broken if throughput meets SLA and `pending` is near zero. Conversely, `active=3/12` with a very slow job points to database locks, unoptimized SQL, or non-DB I/O. Never enlarge the pool simply because a batch job is slow.

Correlate these metrics simultaneously:

- Items/second, total job duration, and per-step duration.
- Connection acquire wait times and timeout counts.
- Pool `active`, `idle`, and `pending` counts.
- Transaction durations, SQL latency, lock waits, query plans, and DB CPU/IO.
- Worker thread states (running, blocked, or waiting on I/O).

## 5. Multi-Threaded Steps: An Executor Does Not Replace a Pool

Spring Batch lets you configure a `TaskExecutor` to process chunks concurrently. Example using `ThreadPoolTaskExecutor`:

```java
package com.example.batch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchExecutorConfig {

    @Bean
    TaskExecutor batchTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("batch-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.initialize();
        return executor;
    }
}
```

Wiring the executor into a step:

```java
@Bean
Step importStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer,
        @Qualifier("batchTaskExecutor") TaskExecutor executor) {

    return new StepBuilder("importStep", repository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
}
```

This is a **configuration pattern**: `Customer`, reader, processor, and writer must be supplied by your project. Not all `ItemReader` and `ItemWriter` implementations are thread-safe; before enabling `.taskExecutor(...)`, audit component state, ordering requirements, checkpoints, transactions, and restartability. Verify concurrency APIs and throttling options against your exact Spring Batch 5 version.

In the executor example:

- `corePoolSize=4`: core worker threads.
- `maxPoolSize=8`: maximum worker threads.
- `queueCapacity=16`: tasks queue up before scaling past core threads; because a bounded queue is used, **do not assume `maxPoolSize=8` means 8 workers are always active**.

Meanwhile, the connection pool is a separate bottleneck. Scaling workers to 8 when the connection pool is already saturated merely leaves more workers blocked in `getConnection()`. Align executor concurrency, concurrent steps/jobs, and pool capacity together.

### 5.1. Chunk Size and Connection Hold Time

Example with chunk size 1,000:

```text
BEGIN TRANSACTION
  process 1,000 items
  write 1,000 items
COMMIT
```

Large chunks cut commit counts and allow bigger SQL batches, yet holding connections across long transactions reduces pool turnover and inflates rollback costs. Tiny chunks multiply transactions, checkpoints, and metadata writes.

Instead of assuming "bigger chunks are always faster," test values such as 100, 500, and 1,000 on a representative workload and compare:

| Metric | Chunk Too Small | Chunk Too Large |
| --- | --- | --- |
| Transaction overhead | Can be high | Lower |
| Connection hold time | Usually short | Can be long |
| Chunk memory | Low | Higher |
| Rollback cost | Usually smaller | Can be heavy |
| Metadata update frequency | Frequent | Less frequent |
| Real throughput | Database-dependent | Database-dependent |

**Avoid placing slow network calls inside an active database transaction unnecessarily.** Decouple API calls from DB writes where consistency rules permit, or cache/prefetch safely with strict timeouts while preserving consistency, retries, and restarts.

## 6. Acquiring Transactional Connections and Returning Them Properly

When using `JdbcTemplate`, a Spring transaction manager, and a Spring-managed `DataSource`, the framework automatically acquires and releases connections per contract. If you use raw JDBC directly, always close resources with `try-with-resources`.

Example standalone JDBC outside a Spring-managed transaction:

```java
package com.example.batch;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class CustomerLookup {
    private final DataSource dataSource;

    public CustomerLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(long customerId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT 1 FROM customers WHERE id = ?")) {

            statement.setLong(1, customerId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        }
    }
}
```

The snippet above uses a raw `Connection` **outside Spring transaction management**. Inside a transactional tasklet or processor, calling `dataSource.getConnection()` and closing it directly without understanding transaction binding can bypass the active transaction or borrow an extra unintended connection. In Spring apps, prefer `JdbcTemplate`, Spring Data repositories, or `DataSourceUtils` when manual JDBC is truly required.

Example using `JdbcTemplate`:

```java
public boolean exists(long customerId) {
    Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM customers WHERE id = ?",
            Integer.class,
            customerId);
    return count != null && count > 0;
}
```

When `JdbcTemplate` shares the DataSource bound to the active transaction manager, Spring reuses the transactional connection cleanly. Even so, calling `exists(...)` **per item across millions of items** still creates an N+1 query bottleneck. Replacing per-item lookups with joins or batched queries usually outperforms expanding the connection pool.

## 7. Distinguishing Pool Exhaustion, Leaks, and Slow SQL

A classic HikariCP error:

```text
java.sql.SQLTransientConnectionException:
HikariPool-1 - Connection is not available,
request timed out after 20000ms
```

This message means an operation **failed to borrow a connection within the timeout**. It does not by itself prove a connection leak.

| Symptom | What to Investigate | Evidence to Gather |
| --- | --- | --- |
| `active ≈ max`, `pending` climbing | Pool undersized for demand or connections held too long | Hikari metrics, thread dumps, transaction durations |
| `active ≈ max`, very slow SQL | Database queries, locks, or I/O | Slow query logs, query plans, DB wait events |
| Timeouts worsen when adding threads | Concurrency exceeds DB/pool capacity | Worker counts, TPS, pool pending, DB CPU |
| `active` stays high after step finishes | Unreturned connections or unclosed resources | Leak detection stack traces, reader lifecycle, JDBC close |
| Pool fails creating new connections | DB max connections hit, network/TLS/credentials | DB connection count, Hikari logs, driver errors |
| Job metadata updates fail under heavy writer load | `JobRepository` sharing a saturated pool | DataSource wiring, metadata query latency |
| Hikari leak warnings on long cursor jobs | Cursor legitimately holds connection past threshold | Reader `open/close`, step duration, transaction traces |

### 7.1. Enabling Leak Detection for Diagnostics

Temporarily in a diagnostic environment:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

Hikari logs a warning whenever a connection stays borrowed past the threshold. This is an **investigative signal**, not proof of a leak. A long-running batch transaction or an open cursor can legitimately exceed 30 seconds; check whether the connection is eventually returned and examine the borrow stack trace.

Do not set a low threshold in production just to "catch everything": it generates noisy false alarms and logs full borrow stack traces. Likewise, do not crank `connectionTimeout` to several minutes to mask a saturated pool—callers will just queue up and blow batch deadlines.

### 7.2. Systematic Diagnostic Steps

1. Identify the timestamp, pool name (`pool-name`), job, and step.
2. Check `active`, `idle`, `pending`, and timeout counts during that window.
3. Check how many jobs, steps, partitions, and replicas ran concurrently.
4. Inspect DB sessions, running SQL, lock waits, and long transactions.
5. Audit cursor/streaming readers, oversized transactions, in-transaction HTTP calls, and unclosed JDBC resources.
6. Fix the root cause, then re-measure throughput, latency, and timeout rates.

If connections are held by lock-blocked queries, **optimizing queries and shortening transactions** works far better than enlarging the pool. Only raise `maximumPoolSize` within your calculated DB budget when the database has spare capacity and pending waits stem from legitimate concurrency.

## 8. Observing HikariCP with Spring Boot Actuator

Add Actuator:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Spring Boot and Micrometer expose Hikari metrics such as:

```text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.max
hikaricp.connections.timeout
hikaricp.connections.acquire
hikaricp.connections.usage
```

Exact metric names and availability depend on Micrometer and registry versions. Inspect exposed metrics at runtime before building dashboards.

Example exposing the metrics endpoint in a secured environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

Querying when Actuator is active and accessible:

```bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
```

If a batch app runs without a web server, export metrics via a Prometheus push/scrape setup, JMX, or another configured telemetry pipeline. HTTP Actuator endpoints are not automatically available in short-lived CLI batch jobs.

**Never expose `/actuator/metrics` publicly just for convenience.** Enforce endpoint security, network controls, access policies, and proper metric retention. When running multiple DataSources, differentiate pools by `pool` tag/name so series never collide.

### 8.1. How to Read the Metrics

| Observation Pattern | Likely Interpretation | Next Step |
| --- | --- | --- |
| `pending=0`, low average active | Pool is probably not the bottleneck | Profile SQL, CPU, I/O, and processor logic |
| `pending` spikes when jobs overlap | Concurrency exceeds budget or transactions run long | Limit concurrent jobs, tune threads/chunks and DB |
| `active=max`, timeouts rising | Pool exhausted or connections held abnormally | Hunt slow queries, locks, cursors, and leaks |
| Pool has spare connections while DB CPU is high | Database compute is saturated | Tune queries/indexes and reduce concurrency |
| High acquire latency without timeouts | Brief contention bursts | Inspect percentiles over time |
| Throughput drops after raising max pool | DB lock contention or I/O thrashing | Compare against baseline and revert if needed |

Acquire and usage timers reveal how long callers wait for and hold connections—far more informative than isolated `active` snapshots. Examine trends and percentiles over time, as brief spikes differ from sustained saturation.

## 9. Example: Inspecting Pool State from Java in Tests

HikariCP exposes `HikariPoolMXBean` for point-in-time pool inspection, useful in diagnostics or focused tests:

```java
package com.example.batch;

import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

public final class PoolSnapshot {

    public record Values(
            int active, int idle, int total, int waiting) {}

    public static Values capture(HikariDataSource dataSource) {
        HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();
        if (pool == null) {
            throw new IllegalStateException(
                    "Hikari pool has not been initialized");
        }

        return new Values(
                pool.getActiveConnections(),
                pool.getIdleConnections(),
                pool.getTotalConnections(),
                pool.getThreadsAwaitingConnection());
    }
}
```

Example usage at a diagnostic checkpoint with a `HikariDataSource`:

```java
PoolSnapshot.Values snapshot = PoolSnapshot.capture(hikariDataSource);

log.info(
        "event=batch_pool_snapshot active={} idle={} total={} waiting={}",
        snapshot.active(),
        snapshot.idle(),
        snapshot.total(),
        snapshot.waiting());
```

These numbers are **approximate snapshots of live state**: immediately after reading, another thread may borrow or return a connection. Never write `while (waiting > 0)` control loops around them or rely on them to prevent exhaustion. In production, time-series metrics and alerts beat continuous snapshot logging.

### 9.1. Simulating Connection Contention in a Test

Using H2 and an isolated test pool:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:pool_test;DB_CLOSE_DELAY=-1
    hikari:
      maximum-pool-size: 2
      connection-timeout: 1000
```

Test scenario:

1. Borrow the first connection and hold it open.
2. Borrow the second connection and hold it open.
3. On another task, attempt to borrow a third connection from the **same DataSource**.
4. After roughly `connectionTimeout`, assert a connection-timeout `SQLException` is thrown.
5. In `finally`, close both held connections and shut down the executor.
6. Re-inspect the pool to verify connections returned to a healthy reusable state.

Do not write tests asserting exact millisecond sleep timings: CI load and thread scheduling vary. Use generous timeout margins, latches for synchronization, and assertions on exception types/messages.

Such a test proves only the **test pool's connection-cap behavior**; it does not validate sizing for a production batch job.

## 10. Optimization Strategies by Workload Type

### 10.1. Read-Heavy, Write-Light Batch

For example, reading 10 million rows to produce a file:

- Cursor readers can hold connections open for a long time.
- If processor CPU is heavy, adding concurrent readers may stress the DB without shrinking runtime proportionally.
- Consider key-range paging/partitioning on stable keys, well-tuned fetch sizes, and bounded active partitions.
- When files are the primary output, measure reader time vs. processor time before resizing the pool.

### 10.2. Write-Heavy Batch with Short Transactions

For example, ingesting millions of events into a database:

- Prefer `JdbcBatchItemWriter` or batched JDBC operations over row-by-row inserts.
- Tune chunk size to balance SQL batch efficiency against transaction length.
- Keep required indexes/constraints while avoiding redundant work inside loops.
- Audit lock contention, transaction isolation, and unique-key conflicts before adding workers.

### 10.3. Batch Calling External APIs During Processing

For example, a processor calling a partner service per item:

- Enforce client-side concurrency limits, timeouts, and policy-driven retries.
- Avoid holding a JDBC connection across slow network calls if consistency requirements allow splitting stages.
- Consider staging: fetch rows, invoke the API, then persist results in groups with explicit status/idempotency tracking.
- Slow API waits are rarely solved by increasing Hikari's `maximumPoolSize`.

### 10.4. Multiple Jobs Sharing a Database

When `dailyImportJob`, `reconciliationJob`, and `monthlySummaryJob` can overlap:

- Cap concurrency at the scheduler/orchestrator level, not only per step.
- Stagger schedules into non-overlapping windows during peak DB hours.
- Sum `maxPoolSize` across all processes and replicas hitting the same database.
- Monitor `JobRepository`, as shared-pool saturation disrupts batch metadata writes too.
- Use workload prioritization and job queues if OLTP online traffic shares the same database.

## 11. Practical Troubleshooting Checklist

Suppose a job fails with `Connection is not available` at peak hours:

| Step | Question | Action |
| --- | --- | --- |
| 1 | Which pool timed out? | Check `pool-name`, DataSource wiring, and borrow stack traces |
| 2 | Are multiple jobs/replicas overlapping? | Audit schedules, executors, and active instances |
| 3 | Are `active`/`pending` climbing? | Inspect Hikari metrics at minute/second granularity |
| 4 | Does the DB have locks or slow queries? | Check slow SQL logs, query plans, and transaction waits |
| 5 | Are cursors/connections held too long? | Inspect reader lifecycles, leak warnings, and step durations |
| 6 | Does pool sizing exceed the DB budget? | Sum max connections across all replicas and other apps |
| 7 | Can connection hold time be cut? | Tune chunks, SQL, batch writes, and move network I/O out of tx |
| 8 | Is there evidence justifying a pool resize? | Adjust carefully within budget; re-measure throughput and timeouts |

When a job fails due to connection-acquire timeouts, **do not blindly retry endlessly**. If every retry launches extra requests or new job instances, overload worsens. Use bounded backoff retries, preserve identifying `JobParameters` when restarting the same instance, and fix the underlying exhaustion cause.

Do not rely on `HikariPoolMXBean.softEvictConnections()` or app restarts as a default fix for high pool usage: evicting connections helps only with stale/broken physical sockets, not long transactions or database overload.

## 12. Practice Exercises

Build an `importOrdersJob` that reads data and writes to PostgreSQL or an H2 test database, then measure behavior as load changes:

1. Start the job with Hikari `maximum-pool-size: 4`, chunk size 100, and one worker. Record runtime, throughput, and active/pending connections.
2. Increase step workers to 4. Monitor CPU, connection acquire latency, SQL waits, and throughput. Use only concurrency-safe readers/writers.
3. Increase workers to 8 while keeping pool size at 4. Verify whether connection-waiting workers rise instead of assuming the job speeds up.
4. Raise pool size to 8 **only if the database has spare budget**. Compare throughput, transaction latency, and DB resource usage.
5. Test chunk sizes 50, 100, and 500. Pick a sweet spot for your data shape based on commit times, rollbacks, and lock waits.
6. Use a cursor reader and measure how long it holds its connection. Compare against a paging reader if business logic and restartability allow.
7. Add a processor calling a stub API with controlled latency. Observe HTTP latency's impact on transaction/connection hold time, then evaluate splitting stages.
8. Simulate pool exhaustion by holding two connections open and requesting a third as in Section 9.1. Ensure all connections close in `finally`.
9. Run two jobs concurrently and observe aggregate demand on the shared pool. Build a dashboard tracking `active`, `pending`, timeouts, throughput, and duration per job.
10. Draft a production configuration recommendation based on max replicas, peak concurrency, DB connection limits, and SLAs, citing measured data to justify your choices.

**Conclusion:** Connection pools are shared resources across workers, readers, writers, transactions, and Spring Batch metadata infrastructure. Optimizing performance requires balancing **pool capacity, concurrent jobs/steps, chunk size, connection hold time, and database capacity**. When metrics show the pool is a bottleneck, eliminate long connection holds and tune concurrency before raising `maximumPoolSize`—and after every change, verify both throughput and batch output correctness.
