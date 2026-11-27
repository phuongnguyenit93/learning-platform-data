# Tuning JDBC Connections for Short-Lived Tasks

**Spring Cloud Task** builds Spring Boot applications with a finite lifecycle: starting up, performing work, recording status in **TaskRepository**, and exiting. A data-import, report-export, or database-maintenance Task may run for only a few seconds, yet it still needs to acquire JDBC connections to write `TaskExecution`, manipulate business data, and—if **Spring Batch** is used—write checkpoints to `JobRepository`.

For short-lived tasks, JDBC connections represent a noticeable cost: pool initialization, TLS handshakes, authentication, waiting for connection allocation, and resource cleanup can account for a substantial share of total duration. In particular, many CronJobs/Pods starting simultaneously can exhaust PostgreSQL connections even if each Task only runs a handful of queries. This lesson in the **Tuning and Upgrades** chapter guides you through measuring costs, designing a connection budget, configuring HikariCP, optimizing transactions, and managing pool lifecycles without breaking Spring Cloud Task correctness.

**Scope:** Examples use Spring Boot with **HikariCP**, Spring Cloud Task, and PostgreSQL, with additional Spring Batch/Kubernetes scenarios. Illustrative parameters are not universal recommendations for every system; always verify against the actual BOM, JDBC driver, schema, and DB limits of your target version. Every adjustment must be verified through benchmarks and failure testing.

## 1. What to Optimize: Startup, Connections, or SQL?

A Task that reads a small file and writes 500 rows can have this lifecycle:

~~~mermaid
flowchart TD
  A["CronJob or API launch"] --> B["JVM and Spring Context startup"]
  B --> C["DataSource / HikariCP initialization"]
  C --> D["TaskRepository: write START"]
  D --> E["Runner: read, process, write SQL"]
  E --> F["TaskRepository: write END"]
  F --> G["Close Context and Hikari pool"]
  G --> H["Container returns exit code"]
~~~

In this model, runtime consists of multiple parts, not just business SQL:

~~~text
T_total ≈ T_JVM_Context
        + T_first_JDBC_connection
        + T_TaskRepository_START_END
        + T_business_processing
        + T_shutdown
~~~

This summation is merely a way to **break down costs**. Individual phases may overlap or contain multiple queries/connection attempts, so you must measure actual milestones rather than treating them as built-in framework metrics.

**Hypothetical** figures example:

| Phase | Time |
| --- | ---: |
| JVM and Spring Context | 1.8 seconds |
| Acquiring first JDBC connection | 0.8 seconds |
| Writing Task metadata | 0.3 seconds |
| Business processing | 1.1 seconds |
| Resource cleanup | 0.2 seconds |
| **Total** | **4.2 seconds** |

If you only optimize a query to be 20% faster, total duration may decrease very little. But if 30 Pods wait on the DB at the same time, connection acquisition time can jump from sub-second to tens of seconds, or even cause widespread failures.

**Questions before tuning the pool:** Is the Task slow because of startup, waiting on `getConnection()`, SQL/locks, or insufficient backend connections? Each root cause requires a different fix.

## 2. Two JDBC Responsibilities: Metadata and Business Logic

Spring Cloud Task writes a `TaskExecution` at startup and updates the result on completion. Metadata includes execution ID, task name, start/end time, exit code, exit message, and arguments. Therefore, **TaskRepository requires JDBC even when the runner executes no business DB queries**.

If a Task combines Spring Batch, `JobExecution`, `StepExecution`, parameters, and checkpoints are also written to **JobRepository**. These are not the same records.

| Component | JDBC Work | Load Characteristics |
| --- | --- | --- |
| TaskRepository | Create/update `TASK_EXECUTION`, save arguments | Few statements, but critical at lifecycle start and end |
| Spring Batch JobRepository | Record Job/Step status, ExecutionContext | Frequency depends on chunks/steps/restarts |
| Business DAO | Read, process, batch insert/update | Can dominate duration and connection count |
| Migration or schema initializer | Check/create tables on startup | Can cause DDL lock contention if many Pods start together |
| Business listener | Audit, exit summary, outbox | Should not hold connections long when Task is about to exit |

When an application has only **one DataSource**, Spring Cloud Task typically uses that source for TaskRepository. With **multiple DataSources**, you need explicit configuration—such as a `TaskConfigurer` implementation—rather than assuming Spring will pick the right metadata store.

~~~mermaid
flowchart TB
    T["Spring Cloud Task"] --> R["TaskRepository"]
    T --> A["ApplicationRunner"]
    A --> W["Business Writer"]
    A --> B["Spring Batch (if present)"]
    B --> J["JobRepository"]
    R --> D1[("Metadata DB")]
    J --> D1
    W --> D2[("Business DB")]
~~~

The diagram illustrates separating metadata and business databases. **Two DBs or two pools do not automatically improve performance**; they also increase configuration, credentials, transaction managers, and total connection count. If both pools point to the same PostgreSQL instance, the DB budget must count **the sum of connections from both**.

### 2.1. Why Must TaskRepository Be Appropriately Prioritized?

Suppose business data committed successfully, but every connection is held by threads waiting on external APIs. The completion callback cannot borrow a connection to update `TaskExecution.END_TIME`. An operator might see the Task as unfinished, rerun it, and accidentally import data twice.

Therefore, never let long SQL transactions or concurrent threads exhaust the pool across the lifecycle; verify the ability to write final metadata, and also use **idempotency by business key** so retries remain safe.

## 3. HikariCP and Defaults You Must Understand Correctly

Spring Boot prefers **HikariCP** when it is on the classpath; `spring-boot-starter-jdbc` typically brings this library along. HikariCP maintains a connection pool **inside each JVM**, without sharing connections across Pods.

Per HikariCP's documented configuration, common values include:

| Property | Documented HikariCP Default | Meaning |
| --- | --- | --- |
| `maximumPoolSize` | **10** | Maximum connections in one JVM's pool |
| `minimumIdle` | Defaults to `maximumPoolSize` | Pool tries to maintain this many idle connections when possible |
| `connectionTimeout` | **30,000 ms** | Maximum wait time to borrow a connection |
| `validationTimeout` | **5,000 ms** | Maximum time to validate that a connection is alive |
| `initializationFailTimeout` | **1 ms**, after `connectionTimeout` limit | Determines whether the pool fails fast if it cannot create the initial connection |
| `idleTimeout` | **600,000 ms** | Time before retiring idle connections **above** `minimumIdle` |
| `maxLifetime` | **1,800,000 ms** | Maximum lifetime of a connection; never evicts a borrowed connection |
| `keepaliveTime` | **120,000 ms** in current HikariCP README | Checks whether idle connections remain alive to avoid network/DB timeouts |
| `leakDetectionThreshold` | **0** (disabled) | Warns when a connection is borrowed for too long |

The values above are **HikariCP defaults**, not a guarantee that every Spring Boot version leaves them unchanged: applications, profiles, environments, or frameworks may override them.

Do not misinterpret `maximumPoolSize=10` as "immediately create ten connections at startup." It is an **upper limit**, while creation rate and behavior depend on `minimumIdle` and demand. Still, when 30 Pods all try to maintain many idle connections, total DB pressure can be substantial.

### 3.1. Which Settings Have Little Effect on Ultra-Short Tasks?

- **`idleTimeout=10 minutes`:** does not help a Task that lives only 10 seconds. Furthermore, `idleTimeout` has no effect when `minimumIdle` equals `maximumPoolSize`.
- **`maxLifetime=30 minutes`:** has little impact if the process exits after a few seconds. Do not set it too low; HikariCP enforces minimum thresholds.
- **`keepaliveTime=2 minutes`:** does not help a 10-second Task; it only pings **idle** connections sitting in the pool.
- **Increasing `maximumPoolSize`:** does not make sequential SQL run faster; it may only increase connection pressure on the DB.

Prioritize determining **actual concurrent connection demand** instead of mechanically tweaking small properties.

## 4. Pool Sizing Must Be Calculated Across All Pods

Suppose multiple Tasks or workers run concurrently. Define:

~~~text
C_db        = usable connection budget of the DB
C_other     = connections reserved for other applications
C_reserved  = connections reserved for admin, migrations, headroom
N           = number of concurrent Task Pods
P           = maximumPoolSize per Pod
~~~

Capacity screening condition:

~~~text
N × P + C_other + C_reserved ≤ C_db
~~~

If there are **multiple pools connecting to the same database** in each Pod, replace `P` with the sum of those pools' limits; if there are different Task types, sum `N_i × P_i`. This formula computes a **potential upper bound**, not a prediction that all connections are open simultaneously.

### 4.1. Sample Calculation

A PostgreSQL cluster allocates **160 connections** for workloads, of which web services need 40 and 20 must be reserved for admin/monitoring/headroom. That leaves Tasks a budget of 100 connections. If **25 Pods** run concurrently:

| Pool per Pod | Total Max Across 25 Pods | Notes |
| --- | ---: | --- |
| 10 | 250 | Far exceeds the 100 budget |
| 4 | 100 | Hits the limit, lacks safety margin |
| 3 | 75 | Leaves margin for spikes |
| 1 | 25 | Saves connections but may bottleneck threads |

Do not blindly pick `maximumPoolSize=3` for every Task from this table alone. If a Task has four parallel Steps and metadata transactions occur concurrently, a 3-connection pool may be too small. Conversely, a sequential Task with one transaction at a time may need only 2–3 connections.

**How to choose:** (1) calculate the cluster-wide budget; (2) identify concurrent JDBC thread count; (3) check connection-wait p95/p99; (4) tune the pool down/up via real experiments; (5) cross-check total connections and database throughput.

### 4.2. Do Not Confuse Forbid with a Connection Limit

Kubernetes CronJob `concurrencyPolicy: Forbid` only prevents overlapping Jobs of **the same CronJob**. Twenty different CronJobs all scheduled at 02:00 can still spawn twenty Pods. A Spring Batch Job using remote partitioning can also have many workers.

Consider **staggering schedules**, concurrency limits at the scheduler level, thread/partition limits, appropriate pool sizing, and backoff/jitter on DB errors. Do not raise PostgreSQL `max_connections` indefinitely; every backend session consumes resources.

## 5. Reference Configuration for a Short Task Using PostgreSQL

Example `application.yml` for a mostly sequential Task:

~~~yaml
spring:
  application:
    name: invoice-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      pool-name: invoice-import-jdbc
      maximum-pool-size: 3
      minimum-idle: 0
      connection-timeout: 5000
      validation-timeout: 2000
      initialization-fail-timeout: 1
      idle-timeout: 60000
      max-lifetime: 600000
      keepalive-time: 0
  cloud:
    task:
      initialize-enabled: false
      closecontext-enabled: true
~~~

**This is a starting point for experimentation, not a standard configuration for all applications.** The HikariCP timeout values here are in **milliseconds**. Environment variables must be provided via Secrets/proper configuration; never pass DB passwords via CLI arguments because Spring Cloud Task can persist command-line arguments.

| Choice | Why Try It? | What to Verify |
| --- | --- | --- |
| `maximum-pool-size=3` | Lowers maximum connections per Pod | Is it enough for metadata and business logic running concurrently? |
| `minimum-idle=0` | Avoids maintaining unnecessary idle connections | Does it add connection-creation latency when needed? |
| `connection-timeout=5000` | Detects pool exhaustion faster than default | Does it cause false failures when the database is healthy but slow? |
| `validation-timeout=2000` | Bounds validation time | Must be smaller than `connectionTimeout` |
| `initialization-fail-timeout=1` | Keeps fail-fast when the pool is unready | HikariCP adds this on top of `connectionTimeout` |
| `idle-timeout=60000` | Retires extra connections if Task lives long enough | Irrelevant if Task finishes under 60 seconds |
| `max-lifetime=600000` | Caps connection age at 10 minutes | Practically no effect on a 10-second Task |
| `keepalive-time=0` | Disables periodic idle pings in a short Task | Revisit for long-running Tasks |
| `closecontext-enabled=true` | Closes context at the end of the Task | Does not replace proper thread/transaction management |
| `initialize-enabled=false` | Avoids re-running metadata schema init every run | Only use when migrations have already created the schema |

HikariCP allows `minimumIdle=0`, **but that does not mean the pool will never acquire a connection at startup**: the fail-fast check can still attempt an initial connection. You also should not set `initializationFailTimeout=-1` just for "fast startup": that skips the initial connection check, while TaskRepository/runners will still fail when they actually need the DB.

### 5.1. Sample Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

The snippet requires compatible Spring Boot and Spring Cloud release train `parent`/`dependencyManagement`. `spring-boot-starter-jdbc` typically brings in HikariCP. If the application already has the corresponding JDBC starter, do not add a second pool.

## 6. Distinguishing Timeouts — A Very Common Misconfiguration Point

`spring.datasource.hikari.connection-timeout` limits **how long to wait for a connection**, not how long an SQL statement runs. An SQL query holding a connection for 90 seconds will not automatically be canceled just because you set `connection-timeout: 5000`.

| Timeout Type | Applies To | What It Does Not Guarantee |
| --- | --- | --- |
| Hikari `connectionTimeout` | Waiting to borrow a connection from the pool | Does not interrupt running SQL |
| Hikari `validationTimeout` | Checking connection liveness | Does not bound Task duration |
| Hikari `initializationFailTimeout` | Fail-fast during pool initialization | Is not a retry policy |
| Driver `connectTimeout` | Establishing connection to the DB server | Does not cover waiting for an idle pool slot |
| Driver `socketTimeout` | Waiting on JDBC socket operations | Is not an entire Job business timeout |
| Query/statement timeout | A single SQL statement | Does not limit the whole workflow |
| Spring `@Transactional(timeout=...)` | Transaction managed by the matching transaction manager | Does not automatically bound external HTTP calls |
| Kubernetes `activeDeadlineSeconds` | Total Kubernetes Job active time | Does not bound individual connection acquisitions |

Example **PGJDBC properties**, if you also want to control TCP/driver timeouts:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        connectTimeout: 3
        socketTimeout: 30
        ApplicationName: invoice-import-task
~~~

In PGJDBC, `connectTimeout` and `socketTimeout` are specified in **seconds**, unlike Hikari's connection timeout in milliseconds. Values that are too low can cut off legitimate queries; verify against your RDBMS, driver, and network. Do not copy PostgreSQL properties to MySQL/Oracle without consulting their documentation.

### 6.1. Fail-Fast Without Causing a Retry Storm

For Tasks required to write to TaskRepository, a broken database is a real incident. It is usually better to fail promptly with a sensible timeout so the Kubernetes Job/scheduler can manage retries with **caps, backoff, and jitter**.

With `initialization-fail-timeout=-1`, the pool may initialize without checking the DB; the Task will still likely fail on the first JDBC call, sometimes before metadata can even be created. A Task that "starts fast" yet cannot write TaskRepository is not a valid optimization.

## 7. Avoiding Repeated Schema Initialization in Every Pod

Each time a new Task starts, Spring Boot/Spring Cloud Task can execute schema initialization if enabled and conditions are met. In production with many Pods, do not turn every business run into a lock-contending DDL/migration wave.

If the schema is already managed by **Flyway, Liquibase, or a dedicated migration pipeline**, you can configure:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
  sql:
    init:
      mode: never
  batch:
    jdbc:
      initialize-schema: never
~~~

The three flags serve distinct roles:

- `spring.cloud.task.initialize-enabled=false`: disables Spring Cloud Task's schema initializer.
- `spring.sql.init.mode=never`: disables Spring Boot's generic SQL initialization.
- `spring.batch.jdbc.initialize-schema=never`: disables Spring Batch metadata schema initialization via Boot if Batch is present.

**Only disable these after the schema already exists with the right DDL and version.** Turning them off against an empty DB causes missing-table errors for `TASK_EXECUTION` or `BATCH_JOB_EXECUTION`. Use a dedicated migration account with DDL privileges; the runtime account only needs DML privileges.

If using `JdbcTemplate` alone, avoid pulling in full ORM/JPA startup when unnecessary. However, do not rip out JPA that is serving business logic just to save a few milliseconds without verifying all transactions and mappings.

## 8. Avoiding Holding Connections While Waiting on APIs or Doing CPU Work

A connection borrowed from the pool is not necessarily executing SQL. If a transaction opens and then waits 90 seconds for an HTTP call, the connection can remain held the entire time.

~~~text
BEGIN TRANSACTION
  SELECT data
  HTTP call to partner (wait 60 seconds)
  CPU computation (30 seconds)
  UPDATE data
COMMIT
~~~

If three threads all do this against a pool of max 3 connections, a fourth thread will block and potentially time out. The fix is usually not raising the pool size indefinitely, but **narrowing transactions** where business semantics allow:

~~~text
HTTP fetch / CPU transform (no JDBC transaction held)
    → BEGIN TRANSACTION
      write one chunk of data
      COMMIT
    → repeat for next chunk
~~~

Principles:

1. Use short transactions with clear boundaries; never wrap lengthy network I/O or CPU work inside them.
2. Write in batches/chunks to reduce round trips while keeping sensible checkpoints/rollbacks.
3. Close `Connection`, `PreparedStatement`, and `ResultSet` with try-with-resources when using raw JDBC; prefer `JdbcTemplate` to manage resources.
4. Never create a new `HikariDataSource` per file or per row.
5. When using `@Transactional` via Spring proxies, avoid self-invocation that bypasses transaction advice.
6. Do not execute an entire Job inside one giant transaction just to reduce commit count.

### 8.1. Example of `JdbcTemplate.batchUpdate` with Chunk-Scoped Transactions

Below is a PostgreSQL service using `JdbcTemplate` to write multiple rows into a table with a unique key `(source_id, external_id)`.

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderRow(String sourceId, String externalId, BigDecimal amount) {}

@Service
public class OrderBatchWriter {
    private final JdbcTemplate jdbc;

    public OrderBatchWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeChunk(List<OrderRow> rows) {
        if (rows.isEmpty()) {
            return;
        }

        jdbc.batchUpdate("""
            INSERT INTO order_import (source_id, external_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT (source_id, external_id) DO NOTHING
            """,
            rows,
            rows.size(),
            (ps, row) -> {
                ps.setString(1, row.sourceId());
                ps.setString(2, row.externalId());
                ps.setBigDecimal(3, row.amount());
            });
    }
}
~~~

This example assumes the table and constraint already exist, and the application has a `JdbcTemplate` and transaction manager for the right DataSource. `writeChunk` must be invoked through a **Spring-managed bean**, not via `this.writeChunk(...)` from another method in the same class if proxy-based transactions are expected to apply. Chunk row counts must be clearly bounded; here `rows.size()` is simply the size of a pre-bounded chunk.

This method makes no external API calls inside the transaction. To import a 100,000-row file, another service can read/normalize outside any transaction and call `writer.writeChunk(...)` repeatedly. Avoid buffering the entire source in RAM when data volume is large.

### 8.2. Choosing Chunk Size Using Measurements

| Chunk Too Small | Chunk Too Large |
| --- | --- |
| Many round trips and commits | Holds connections/locks for a long time |
| High per-batch overhead | Rolling back and retrying a whole chunk is expensive |
| Simpler partial recovery | Risks hitting timeouts and increasing WAL/CPU |
| May miss batching gains | Can starve JobRepository and other Tasks |

You can test sizes like 100, 500, and 1,000, then measure throughput, transaction duration, connection-acquire p95, and error rate. When using Spring Batch, chunk size and checkpoints directly affect restartability; never drop transactions just to shorten lock duration.

## 9. Small Pools and TaskRepository Needing a Connection at Lifecycle End

A dangerous scenario:

~~~text
Task starts and writes START successfully
    → Runner writes business data and COMMITs
    → Other threads hold all connections / DB loses connectivity
    → TaskRepository fails to write END
    → Scheduler sees failure/uncertain outcome
    → Operator retries
    → Business data may be created a second time
~~~

The **TaskRepository mechanism tracks executions**; it does not guarantee exactly-once writes to business tables. Always use business keys, unique constraints, idempotent upserts, or the outbox pattern whenever side effects exist; never rely on `TaskExecution ID` as a deduplication key.

If metadata DB and business DB are separate, carefully verify transaction boundaries. Two different transaction managers do not automatically form an atomic cross-database transaction. When one side commits and the other fails, you need a recovery/reconciliation procedure.

## 10. External Pooling: PgBouncer, Proxies, and Serverless DBs

When many short-lived Tasks run, opening and closing large numbers of TCP/TLS sessions can put heavy pressure on the database. A proxy like **PgBouncer** can help manage backend connections, though it is not a universal default for every system.

**Evaluate compatibility when using transaction pooling:**

- Session variables, temporary tables, session-level advisory locks, and prepared statements may depend on a stable backend connection.
- The PostgreSQL driver may use server-side prepared statements based on specific thresholds/configs.
- Long transactions reduce backend connection sharing efficiency.
- Application pools still need limits; proxies also have connection/client/queue limits.
- TaskRepository and Spring Batch restart/locking must be tested against the actual proxy configuration.

Do not turn on transaction pooling merely to make connection numbers look nicer. Prove that data stays consistent under retries, session state is not misinterpreted, and queries still run properly under the chosen pooling mode.

If a **serverless** database has cold starts or must wake from sleep, the first connection can be unusually slow. Measure cold and warm startups separately; configure driver timeouts/`connectionTimeout` and bounded retry policies. Do not disable TLS or embed passwords in JDBC URLs to "reduce overhead."

## 11. Ending the Task and Closing the Hikari Pool Properly

Spring Cloud Task supports:

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

After the runner finishes and TaskRepository updates the outcome, closing the `ApplicationContext` triggers destroy callbacks on beans. When the Spring-managed `HikariDataSource` closes, the pool releases its connections.

**Do not call `dataSource.close()` manually inside `ApplicationRunner`** if TaskRepository still needs to record the end state. Closing prematurely can prevent `END_TIME` from being updated. Also do not have the runner submit asynchronous work and return immediately: the context may close while threads are still using JDBC.

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> task = executor.submit(() -> performImport());
        task.get(); // Wait for processing to finish or receive exception.
    };
}
~~~

This is conceptual code only: you must define the executor, `performImport()`, interrupt handling, cancellation, timeouts, and executor shutdown. In production, never wait indefinitely: enforce an appropriate business deadline.

### 11.1. SIGTERM vs. SIGKILL

| Situation | What Can Happen |
| --- | --- |
| Normal exit | Context closes, pool cleans up connections, and Task gets to record END |
| SIGTERM | Graceful shutdown may happen within configured window; must be tested |
| SIGKILL / OOM / node loss | No guarantee `finally`, destroy callbacks, or END write are executed |
| DB network cut | DB side may take time to detect that the peer is dead |

For Kubernetes Jobs, balance `terminationGracePeriodSeconds`, `activeDeadlineSeconds`, transaction durations, and shutdown time. Do not assume "zero connections left in `pg_stat_activity`" is guaranteed instantaneously when a Pod is killed.

## 12. Observing and Measuring the Pool in Finite Tasks

Spring Boot Actuator can expose **DataSource metrics** prefixed with `jdbc.connections` and Hikari-specific metrics prefixed with `hikaricp`, given appropriate registries/instrumentation. Metric names exported to Prometheus/OTLP may be normalized differently.

| Metric | Meaning | Source |
| --- | --- | --- |
| Active/idle/pending connections | Is the pool exhausted or holding too many idle connections? | Hikari/Micrometer |
| Connection acquire time | Wait time to borrow a connection | Hikari metrics |
| Connection creation time | Are cold connections expensive? | Hikari metrics and logs |
| DB connection count | Does fan-out exceed budget? | DB monitoring |
| Task startup/total duration | Does pool tuning help overall? | Task observation and Kubernetes Job timestamps |
| SQL/query/lock wait | Is DB or app the bottleneck? | Database metrics/traces |
| `TASK_EXECUTION.END_TIME`/exit code | Is completion metadata recorded? | TaskRepository |
| Retries/Pod failures | Do pool timeouts trigger Job retries? | Kubernetes Job/Pod |

**Tasks running only a few seconds can exit before Prometheus scrapes the endpoint.** Never conclude "the pool had no connections" just because a dashboard is empty; use logs, verified push telemetry, or out-of-process DB/Kubernetes monitoring.

### 12.1. PostgreSQL: Inspecting Connections by `application_name`

You can supply a non-sensitive application name to PGJDBC via `data-source-properties.ApplicationName`. Then query connection stats:

~~~sql
SELECT application_name,
       state,
       COUNT(*) AS connections
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY application_name, state;
~~~

Run this with an account that has appropriate monitoring privileges. For very short Tasks, a single snapshot can miss peak connections; sample over time or use DB metrics. If multiple Pods share the same application name, total connections per group help spot pressure without separating individual Pods; only add a Pod ID to observability data if doing so exposes no sensitive information.

TaskRepository can be cross-checked separately:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-import-task'
ORDER BY START_TIME DESC
LIMIT 20;
~~~

If `END_TIME` is null, the Task may still be running or may have died before updating; cross-check Pod status, DB connectivity, and logs.

## 13. Before/After Optimization Benchmark Procedure

**Do not conclude a new configuration is better just because connection count dropped.** You must compare data correctness, throughput, and runtime.

### 13.1. Preparing the Test

1. Prepare an environment equivalent to production in PostgreSQL, network, schema, Pod count, data, and JDBC driver version.
2. Pick a fixed workload: e.g., importing 10,000 records across several chunks plus a full TaskRepository START/END cycle.
3. Separate **cold DB/cold JVM** runs from warmed runs.
4. Attach a non-sensitive correlation ID to link Task, Job, Pod, and DB logs.
5. Measure process start, first connection, first query, last business commit, TaskRepository END, and process exit.
6. Run multiple iterations with **one Pod** and **multiple concurrent Pods**; measure p50/p95 and peak connections.
7. Verify total record count, checksums, idempotency, and retry counts did not change unexpectedly.

### 13.2. Test Matrix

| Scenario | Configuration | Concurrent Pods | What to Verify |
| --- | --- | ---: | --- |
| A — Baseline | HikariCP defaults | 1 | Startup/first connection/total Task |
| B — Smaller | max=3, minIdle=0 | 1 | Does the first SQL slow down? |
| C — Fan-out baseline | Defaults | 20 | Peak DB sessions and errors |
| D — Bounded fan-out | max=3, minIdle=0 | 20 | Pool pending, connection count, p95 |
| E — Pool too small | max=1 | 20, parallel workers | Timeouts or blocked END metadata? |
| F — Batch size | max=3, chunk 100/500/1000 | 5–20 | Throughput, lock/transaction wait |
| G — Slow/unavailable DB | max=3 | 10 | Fail-fast, timeouts, backoff |
| H — Pod termination | max=3 | 1 | END_TIME and connection cleanup |
| I — Schema initialization | Auto-init vs. pre-migrated | 20 | Startup time, DDL contention |

A hypothetical result: baseline 20 Pods peaked at 110 connections and 4 failed Tasks; a smaller pool dropped to 48 connections with 0 failed Tasks. That is a good signal **only if** SLAs, throughput, and business data remain accurate. If a 1-connection pool triples runtime, analyze metadata/transaction concurrency rather than forcing the smallest possible pool.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `HikariPool ... Connection is not available` | Pool exhausted or slow DB | Inspect active/pending, long transactions, timeouts |
| `too many clients already` | Multiple Pods/pools exceed DB budget | Limit fan-out and pool size; account for other apps |
| Task fails on startup | DB/TLS/credential/schema error | Check JDBC driver, migrations, real connectivity |
| Fast startup with negative init fail timeout, but JDBC still fails | Moved failure from startup to first borrow | Do not count as a successful optimization; fix DB |
| `minimumIdle=0` slows first SQL | Cold connections created on demand | Benchmark and consider a small minimumIdle below max |
| `idleTimeout` has no effect | minIdle=maxPoolSize or Task too short | Understand scope; avoid pointless tuning |
| Task committed data but metadata lacks END | DB ran out of connections or Pod killed | Reconcile business key and logs before retry |
| Raising pool size lowers throughput | DB lock/CPU/I/O bottleneck | Optimize SQL, lower concurrency, profile DB |
| Task does not exit after runner | Executor/context still alive | Await workers, close context per lifecycle |
| Leak warnings on long queries | Long-held connection or real leak | Narrow transactions, inspect stack traces, test |
| Session errors through PgBouncer | Transaction pooling incompatible with session state | Adjust driver/transaction mode and test |
| Every Pod tries to create Task tables | Schema init not moved to separate migration | Migrate upfront, then disable init |
| Hikari metrics missing | Task exits before exporter/scrape | Monitor DB and logs; test push telemetry |

`leakDetectionThreshold` only logs warnings for long-held connections and can produce **false positives** for legitimate Batch transactions. It does not automatically clean up leaked connections. Enable it during controlled diagnostics, not as a fix.

## 15. Safety and Upgrading JDBC Connections

- Never pass `spring.datasource.password` via command-line arguments because Spring Cloud Task may record it in `TASK_EXECUTION_PARAMS`. Use Secrets/credential providers.
- Separate runtime privileges from migrations: the Task account does not need DDL once the schema is migrated.
- Do not disable TLS to shave off connect time if the environment requires encrypted transport.
- Track compatible JDBC driver, HikariCP, Spring Boot, and Spring Cloud Task versions via BOM; read release notes when upgrading since defaults/bindings may change.
- If swapping pool implementations or DataSource beans, verify **TaskRepository still uses the right database** and history data is preserved.
- Never log raw connection strings, passwords, or entire environment dumps to diagnose pool behavior.
- Run tests for **startup failure**, retries, timeouts, Pod termination, old schemas, and pool exhaustion before production upgrades.
- Sequence migrations and rollouts carefully: compatible schema first, new image second; keep a rollback plan and check TaskExecution/Batch metadata.
- For short-lived Tasks, **connection count must be measured cluster-wide**, not within a single process.

## 16. Practice Exercises

A platform runs **30 Task Pods** concurrently; each Task imports a CSV in roughly 15 seconds and includes a Spring Batch chunk-oriented Step. PostgreSQL allocates a budget of 140 connections across all workloads; web services and monitoring use 70 connections, leaving 70 connections for Tasks and headroom. Each Pod has two threads that may borrow JDBC connections at the same time.

1. Calculate the potential connection ceiling if each Pod uses the default pool max of 10; explain the risk.
2. Calculate the ceiling for max=3 and max=2. Choose an initial test configuration with budget headroom and reasoning for the two threads.
3. Write an `application.yml` containing `maximum-pool-size`, `minimum-idle`, `connection-timeout`, `validation-timeout`, `closecontext-enabled`, and `initialize-enabled`.
4. Explain why `connection-timeout=5000` will not cancel an SQL query running for 12 seconds.
5. Separate HTTP fetch/CPU transform from the JDBC transaction; write a `writeChunk` method using `JdbcTemplate.batchUpdate`.
6. Design a test with 1, 10, and 30 concurrent Pods. Measure pool active/pending, DB connections, total Task duration, and % Task failures.
7. With the DB unavailable at startup, compare fail-fast against `initializationFailTimeout=-1`.
8. Terminate a Pod before TaskRepository writes END; explain why retries require a unique business key.
9. Verify schema initializers are disabled **after** migrations create all Task/Batch tables.
10. Suppose a second DataSource is added for the business DB; recalculate the connection budget and check transaction managers.
11. Test increasing chunk size 100 → 500 → 1,000 and measure transaction duration, throughput, lock wait, and rollback impact.
12. Present a timeout/retry policy when PostgreSQL errors occur, ensuring no retry storm is triggered.

**Passing criteria:** propose pool sizing grounded in Pod count and actual connection budget rather than copying defaults; also demonstrate that TaskRepository/JobRepository update properly, runtime meets SLAs, and business outcomes stay safe under failure.

## 17. Summary

1. **Short-lived Tasks still need JDBC** to write TaskExecution and potentially Spring Batch's JobRepository.
2. **A HikariCP pool lives inside one JVM**, while PostgreSQL serves all Pods. Connection budgets must account for concurrent Pods and all pools/apps.
3. HikariCP defaults to **max=10**, with `minimumIdle` defaulting to max; this default does not automatically suit CronJobs running for a few seconds.
4. `minimumIdle=0` can reduce idle connections at the cost of on-demand connection overhead; do not apply without measuring.
5. **`connectionTimeout` only bounds waiting to borrow a connection**; separate timeouts are needed for driver, SQL, transactions, and Kubernetes Jobs.
6. Big gains usually come from **short transactions, sensible batching, not holding connections during HTTP calls**, and avoiding schema init on every Pod.
7. Closing `ApplicationContext` at the end of a Task releases the pool, but never call `DataSource.close()` before TaskRepository records the final outcome.
8. SIGKILL/OOM can prevent writing `END_TIME`; TaskExecution does not replace idempotency on business tables.
9. **Benchmark both single-Pod and multi-Pod runs**: peak connections, p95 acquire time, total duration, retry counts, data correctness, and metadata state.

### Official References

- [Spring Cloud Task — Features: DataSource and TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Boot — SQL Databases and DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Common Application Properties: Hikari](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [HikariCP — Configuration Knobs, defaults, and caveats](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Actuator Metrics for JDBC and HikariCP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
