# Monitoring Slow Queries, Connections, and Database Resources

> **Chapter:** RDS and Aurora Databases  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem from Regions/Availability Zones (AZs), IAM, and VPC to compute, storage, databases, integration, and serverless; develop skills in service selection, secure application deployment, monitoring, recovery, and cost control.

## Learning objectives

After this lesson, learners will be able to:

1. Build an observability strategy for **Amazon RDS and Amazon Aurora** across four layers: application experience, database load/queries, operating system, and storage/replication.
2. Read and accurately interpret **CloudWatch `AWS/RDS` metrics**: `CPUUtilization`, `DatabaseConnections`, `FreeableMemory`, `FreeStorageSpace` where applicable, IOPS, latency, queue depth, throughput, replica lag, and Aurora Serverless metrics.
3. Explain **CloudWatch Database Insights**, DB Load measured in **Average Active Sessions (AAS)**, top SQL/waits/locks/plans analysis, and differences between Standard and Advanced modes.
4. Configure and inspect **slow query logs** for PostgreSQL, MySQL, and Aurora via parameter groups, accounting for log overhead and the risk of exposing SQL parameters.
5. Use **`pg_stat_activity`, `pg_stat_statements`, `pg_locks`** for PostgreSQL and **`performance_schema`, `SHOW PROCESSLIST`, `EXPLAIN`** for MySQL to isolate slow SQL.
6. Distinguish **connections, active queries, idle connections, connection churn, and pool exhaustion**; calculate pool capacity for Spring Boot/HikariCP, Lambda/ECS, and RDS Proxy.
7. Diagnose **CPU, RAM, I/O, storage, locking, autovacuum, and replication** bottlenecks without jumping to conclusions from a single metric.
8. Design CloudWatch dashboards/alarms, runbooks, IAM/KMS/CloudWatch Logs permissions, and monitoring budgets.
9. Run diagnostic checks using **read-only AWS CLI** commands and non-mutating SQL queries.
10. Make optimization decisions backed by before/after metrics: indexes, query plans, pools, instance classes, storage, reader endpoints, or RDS Proxy.

## 1. Real-world scenario: Java API is slow—what is wrong with the database?

A **Spring Boot Orders API** service runs on Amazon ECS/EC2 or Lambda, connecting to **Amazon RDS for PostgreSQL** or **Amazon Aurora PostgreSQL**. Users report:

- **`GET /orders`** latency jumped from 200 ms to 3 seconds.
- HikariCP logs show **`Connection is not available, request timed out`**.
- CloudWatch shows **`DatabaseConnections`** climbing while CPU sits around 45%.
- Occasionally, orders update slowly or transactions time out.
- Scaling up ECS tasks / Lambda concurrency makes the issue worse.

You cannot conclude “the DB lacks CPU” or “just upgrade the instance size” from those symptoms alone. Competing hypotheses include:

1. A query lacks an index and scans millions of rows.
2. A long transaction holds locks, forcing other queries to **wait** even though CPU is free.
3. The Java app opens too many DB connections; each worker/task maintains its own pool.
4. Database storage latency or queue depth is rising.
5. A DB proxy lacks connection headroom or suffers from session pinning.
6. Replica lag causes the read API endpoint to return stale data.
7. DNS/TLS/IAM/SG issues or connection churn create heavy connection setup overhead.
8. Logging tools write excessively, driving up CPU and I/O.

The goal of database observability is not merely **seeing a red line on a graph**, but connecting evidence to answer: **where is it slow, why, how many requests are affected, and which layer needs fixing?**

~~~mermaid
flowchart TB
    CLIENT["Users"] --> API["API Gateway / ALB"]
    API --> JAVA["Spring Boot / ECS / Lambda"]
    JAVA --> POOL["HikariCP / RDS Proxy"]
    POOL --> WRITER["RDS/Aurora writer"]
    WRITER --> STORAGE[("EBS or Aurora storage")]
    WRITER --> READER["Aurora readers / RDS read replica"]
    JAVA -.-> APPMET["App metrics: p95, errors, pool wait"]
    WRITER -.-> CW["CloudWatch AWS/RDS"]
    WRITER -.-> DBI["CloudWatch Database Insights"]
    WRITER -.-> EM["Enhanced Monitoring / Logs"]
    READER -.-> CW
    CW --> DASH["Dashboards and alarms"]
    DBI --> DASH
    EM --> DASH
    APPMET --> DASH
~~~

This diagram is a **reference architecture**. Standard RDS uses a different storage architecture than Aurora; not every RDS instance has read replicas, RDS Proxy, or Enhanced Monitoring.

### 1.1. Defining observability targets

For the Orders API, you might choose:

| SLI/SLO | Reference example | Signals to watch |
| --- | --- | --- |
| **API latency p95** | Under 500 ms for normal read requests. | Spring Actuator/APM and ALB/API Gateway latency. |
| **DB query latency p95** | Critical queries under 100 ms per real workload data. | Tracing, Database Insights, slow query logs, `pg_stat_statements`. |
| **Connection acquisition wait** | Most requests acquire connections without waiting. | HikariCP pending/wait metrics and RDS Proxy borrow latency. |
| **Transaction correctness** | No duplicate inventory deductions or orders on retry. | Business audits, DB constraints, idempotency. |
| **Replica freshness** | Read data does not lag beyond threshold. | Replica lag and read-after-write consistency rules. |
| **Availability** | DB endpoints and application remain healthy. | Failover events, connection errors, app error rates. |
| **Cost/efficiency** | Cost per 1,000 valid orders. | DB instance/ACU/storage/I/O/logs/Proxy and throughput. |

These thresholds are examples only; they are not AWS defaults.

## 2. Understanding RDS, Aurora, instances, clusters, and replicas accurately

### 2.1. RDS DB instance vs. Aurora DB cluster

| Aspect | **RDS MySQL/PostgreSQL DB instance** | **Aurora MySQL/PostgreSQL DB cluster** |
| --- | --- | --- |
| Compute | DB instance. | One or more DB instances in a cluster; writer and optional readers. |
| Storage | RDS-managed EBS storage volume per engine/storage type. | Aurora shared cluster volume distributed and replicated by the service. |
| HA | Multi-AZ DB instance or Multi-AZ DB cluster per choice. | Storage HA by cluster design; writer fails over to an eligible reader/instance. |
| Read scaling | Read replicas per engine/configuration. | Aurora Replicas reading shared cluster volume via reader endpoint. |
| Metrics | `AWS/RDS` instance metrics, DB Insights, logs. | `AWS/RDS` **instance-level and cluster-level metrics**, plus Aurora-specific metrics. |
| Capacity | DB class and storage type/IOPS/throughput. | Provisioned instances or **Aurora Serverless** in ACUs per config. |
| Cost | Instances, storage/IOPS/backups/network/logs. | Instances or ACUs, storage/I/O or I/O-Optimized, backups/network/logs. |

**Do not equate** an RDS Multi-AZ **standby** with a **read replica** that serves `SELECT`s. In a traditional Multi-AZ DB instance deployment, the standby is for HA, not an application read endpoint. Multi-AZ DB clusters and Aurora have different read topologies that must be verified specifically.

### 2.2. Monitor writer and readers separately

A cluster has:

- **Writer endpoint** for writes and queries needing immediate consistency.
- **Reader endpoint** for offloading reads across readers when appropriate.
- **Instance endpoints** for diagnosing a specific member.

If you look only at the writer's CPU/`DatabaseConnections`, you can miss an overloaded reader or high replica lag. If you look only at cluster averages, a bottlenecked reader can be masked.

~~~mermaid
flowchart LR
    APP["Java application"] -->|"Writes / read-after-write"| WEP["Cluster writer endpoint"]
    APP -->|"Reads tolerating replica lag"| REP["Reader endpoint"]
    WEP --> W["Writer instance"]
    REP --> R1["Reader AZ-1"]
    REP --> R2["Reader AZ-2"]
    W --> S[("Aurora shared cluster volume")]
    R1 --> S
    R2 --> S
~~~

**The reader endpoint does not guarantee every read sees fresh writes immediately.** Read-after-write flows may need to route to the writer or use an explicit consistency mechanism.

### 2.3. Regions/AZs in monitoring

- **CloudWatch metrics, RDS/DB Insights, and logs** are viewed in the Region where the DB runs.
- An RDS/Aurora cluster can span multiple AZs, which is **not** multi-Region DR by default.
- During failover, the writer role/endpoint shifts members; a dashboard pinned to an **old DB instance identifier** continues measuring the member that became a reader.
- Aurora Global Database has separate cross-Region replication metrics and settings; monitor **replication lag** per Region rather than relying on a single local graph to declare the whole system healthy.

## 3. Four layers of database observability

| Layer | Tools / signals | What it answers | Limitations |
| --- | --- | --- | --- |
| **Application** | Java p95/p99, HikariCP pools, traces, errors, transaction outcomes. | Which API is slow for users? | Cannot pinpoint exact DB wait events without instrumentation. |
| **Database activity** | **CloudWatch Database Insights**, DB Load/AAS, top SQL/waits/plans, SQL views. | Which query, lock, or CPU consumer is keeping the DB busy? | Subject to supported features and retention. |
| **Infrastructure/OS** | **CloudWatch `AWS/RDS`**, **Enhanced Monitoring**, OS process metrics. | Are CPU, RAM, disk queue, network, or storage saturated? | A single metric does not identify the offending SQL. |
| **Logs/events** | PostgreSQL logs, MySQL slow logs, CloudWatch Logs, RDS events. | Which SQL statements were slow; did DB restarts/failovers happen? | Incurs overhead and may contain sensitive data. |

**Correct diagnostic order:** confirm user impact → identify DB instance/cluster and time window → inspect DB Load/waits/connections → examine SQL plans/logs → correlate CPU/memory/I/O/replica lag → test changes in a controlled environment.

## 4. CloudWatch `AWS/RDS`: essential metrics to know

RDS/Aurora emit metrics into **`AWS/RDS`**. Basic CloudWatch typically has **1-minute** granularity, organized by timestamps and dimensions such as **`DBInstanceIdentifier`** or **`DBClusterIdentifier`** depending on the metric.

### 4.1. Compute and memory

| Metric | Meaning | When abnormal |
| --- | --- | --- |
| **`CPUUtilization`** | % CPU used on the DB instance. | Sustained high CPU, exhausted CPU credits, CPU-bound SQL, background work. |
| **`FreeableMemory`** | Reclaimable/available memory; does not mean completely unused RAM. | Cache/connection/`work_mem` pressure, swapping, OOM risk. |
| **`SwapUsage`** | Bytes of swap in use, where supported. | Memory pressure; inspect trends and OS metrics. |
| **`CPUCreditBalance`** | Remaining CPU credits on supported burstable DB classes. | Performance throttles once credits hit zero, even if earlier CPU peaked. |
| **`DatabaseConnections`** | Number of client network connections to the DB per engine/service semantics. | Pool bloat, connection storms, `max_connections`, idle churn. |

Low **`FreeableMemory`** is not automatically an error, since databases use memory for caching. Check trends, swap, DB Load, errors, and Enhanced Monitoring memory metrics before concluding RAM is insufficient.

### 4.2. Storage, I/O, and network

| Metric | Meaning | Watch out for |
| --- | --- | --- |
| **`FreeStorageSpace`** | Remaining DB instance storage **where applicable**, critical for provisioned RDS storage. | Aurora shared cluster storage uses different metrics/mechanics; do not reuse RDS EBS `FreeStorageSpace` alerts blindly. |
| **`ReadIOPS` / `WriteIOPS`** | Read/write I/O rate per engine/storage metric. | High IOPS alone is not a failure; compare against baseline and latency. |
| **`ReadLatency` / `WriteLatency`** | I/O operation latency per service definition. | Correlate with queue depth/throughput; do not confuse with SQL query latency. |
| **`DiskQueueDepth`** | Outstanding I/O requests per service/engine. | Rising queue depth alongside latency indicates an I/O bottleneck. |
| **`ReadThroughput` / `WriteThroughput`** | Bytes read/written per second. | Compare against storage bandwidth and workload profile. |
| **`NetworkReceiveThroughput` / `NetworkTransmitThroughput`** | Bytes across the DB instance network interface. | Check read fan-out, replication, and client fetch sizes. |
| **`BurstBalance`** | Burst credits on storage types like gp2 where applicable. | Does not apply to all storage types (e.g., gp3 does not use gp2 burst buckets). |
| **`EBSByteBalance%` / `EBSIOBalance%`** | Throughput/IO credit balances for applicable DB classes/storage. | Depends on instance/storage/engine; not necessarily emitted for every Aurora engine. |

**Units matter hugely.** The AWS/RDS Console may display MB while CloudWatch returns **Bytes**. Never set an alarm threshold of `1000` thinking of “GB” if the underlying metric is in Bytes.

### 4.3. Connections are not running queries

Suppose `DatabaseConnections = 250` while DB Load is only `4 AAS`. That usually means **many connections are idle**, with only a few active sessions. Conversely, if CPU is 80% and DB Load is `20 AAS`, you likely have CPU-bound queries or heavy waits; inspect top wait types.

Likewise, `DatabaseConnections = 30` with `DB Load = 25 AAS` mostly waiting on locks indicates a transaction/locking bottleneck rather than running out of connection slots.

**`DatabaseConnections` ≠ Concurrent SQL queries ≠ DB Load.** These are three distinct quantities.

## 5. CloudWatch Database Insights: observing DB Load, top SQL, and waits

**CloudWatch Database Insights** is the primary CloudWatch observability experience for RDS/Aurora. AWS has transitioned the **Performance Insights console** experience into Database Insights; per current CloudWatch documentation, standalone Performance Insights end-of-life is **July 31, 2026**. Some API and metric names still contain **`PerformanceInsights`** for backward compatibility; do not confuse legacy API names with the modern console UI.

### 5.1. Standard vs. Advanced

| Capability | **Standard** | **Advanced** |
| --- | --- | --- |
| DB Load, top dimensions (SQL, waits, host, user) | Supported for eligible engines. | Included. |
| Detailed retention | Typically **7 days** with no retention fee; longer paid options available. | Longer retention per configuration and pricing plan. |
| Per-query statistics and guided slow SQL analysis | More limited. | Included, per engine and **CloudWatch Logs export** where needed. |
| Guided lock/plan analysis | Not as comprehensive as Advanced. | Available on supported engines (e.g., Aurora/RDS PostgreSQL lock and execution plans). |
| OS process breakdown / fleet analytics | Limited. | Advanced capabilities when Enhanced Monitoring / matching features are enabled. |
| Cost | Standard baseline feature; extended retention/add-ons may incur fees. | Mode/retention and CloudWatch/logs carry dedicated pricing. |

AWS may update retention and pricing; when deciding for production, verify **Database Insights pricing and engine compatibility in your Region** rather than treating this table as a fixed price contract. Do not enable Advanced just to check `CPUUtilization` when basic CloudWatch metrics suffice.

### 5.2. DB Load = Average Active Sessions (AAS)

Database Insights uses **DB Load** as its core signal: the number of **active** sessions—either running on CPU or waiting on resources like locks or I/O—measured as **average active sessions** over a time window.

\[
\text{DB Load (AAS)}
=\frac{\text{Total active time of all sessions}}{\text{Observation window duration}}
\]

For example, over 60 seconds, sessions accumulate **480 session-seconds** of active work/waiting:

\[
\text{AAS}=480/60=8
\]

`AAS = 8` means an equivalent of **8 continuously active sessions**, not “8 queries were called.” If load is mostly CPU on a 4-vCPU DB, `DBLoadCPU` exceeding ~4 suggests CPU contention; if load is mostly lock waits, adding CPU probably will not fix it.

### 5.3. DB Load by wait group

~~~mermaid
flowchart TD
    LOAD["DB Load (AAS) rises"] --> Q{"Top wait type?"}
    Q -->|"CPU"| CPU["Inspect CPUUtilization, hot SQL, execution plans"]
    Q -->|"Lock"| LOCK["Find blocking sessions and transaction duration"]
    Q -->|"I/O"| IO["Inspect storage latency, cache hit ratio, scans, IOPS"]
    Q -->|"Client/network"| NET["Inspect client fetch, network, connection pooling"]
    Q -->|"Commit/log"| COMMIT["Inspect write pressure, WAL/redo, storage"]
~~~

**Learn wait event names for your specific database engine.** PostgreSQL uses `wait_event_type`/`wait_event`, which differ from MySQL Performance Schema events. A `DBLoad = 12 AAS` with 10 AAS waiting on Locks is completely different from 12 AAS burning CPU.

### 5.4. Top SQL and dimensions

Database Insights can slice DB Load by:

- **SQL** or SQL digest/normalized statement.
- **Waits** (CPU, Lock, I/O, commit, etc.).
- **Host**, **User**, **Database**.
- **Blocking session/SQL/object**, where supported by engine/mode.
- **Execution plan**, when advanced plan analysis is enabled on supported engines.

For instance, if DB Load jumps from 5 to 20 and 15 AAS concentrate on **`SELECT orders WHERE customer_id = ? ORDER BY created_at DESC`**, check indexes, customer cardinality, and execution plans instead of jumping from 4 to 16 vCPUs.

### 5.5. `DBLoad`, `DBLoadCPU`, `DBLoadNonCPU`

Several metrics can be published to CloudWatch, such as **`DBLoad`**, **`DBLoadCPU`**, **`DBLoadNonCPU`**, and **`DBLoadRelativeToNumVCPUs`**. They are useful for alarms, with important caveats:

- Per docs, these metrics may emit only when the DB has load.
- Use **Average** to read DB Load; **Sum** is not a total count of SQL queries.
- **`DBLoadCPU`** reflects AAS consuming CPU; do not equate it with **`CPUUtilization` %**.
- `DBLoadNonCPU` reflects waiting load; it does not mean the server is idle or healthy.
- On Aurora Serverless v2, available vCPU/memory scales with ACUs, so correlate load against current allocated capacity.

## 6. Enhanced Monitoring: OS processes, memory, and I/O

**RDS Enhanced Monitoring** exposes granular OS-level processes/threads and memory/disk/network metrics on DB instances.

- Configurable intervals: **1, 5, 10, 15, 30, or 60 seconds**.
- Enhanced Monitoring data goes to **CloudWatch Logs**, typically in log group **`RDSOSMetrics`**, rather than standard `AWS/RDS` metrics with the same retention.
- Log streams are keyed by **`DbiResourceId`**, not necessarily the display DB instance name.
- Requires **`MonitoringRoleArn`** for an IAM role assumable by RDS with matching permissions.
- Shorter intervals generate more log volume and can increase CloudWatch Logs costs.

### 6.1. When is Enhanced Monitoring needed?

| Symptom | How Enhanced Monitoring helps |
| --- | --- |
| `CPUUtilization` rises, yet DB Load waits don't fully explain it | Inspect OS processes, system vs. user CPU, and background tasks. |
| `FreeableMemory` drops, swap rises | Inspect page cache, RSS, dirty pages, swap pressure, and per-process memory. |
| High storage latency | Inspect disk I/O await/utilization and device-level metrics where supported. |
| Connections feel slow while CPU is low | Inspect network/OS stats alongside DB locks and connections. |
| Maintenance/analyze/vacuum activity | Distinguish background OS processes from app workload. |

**Enhanced Monitoring does not replace a SQL profiler.** It shows OS-level bottlenecks, whereas identifying the exact SQL to fix still requires Database Insights, slow query logs, or engine views.

## 7. PostgreSQL slow query logging (RDS and Aurora PostgreSQL)

PostgreSQL logging is driven by parameters such as:

- **`log_min_duration_statement`**: logs statements reaching this duration threshold, in **milliseconds**.
- **`log_statement`**: `all`/`ddl`/`mod`/`none`; **`none`** avoids logging every routine statement unnecessarily.
- **`log_destination = stderr`**: configuration used for RDS/Aurora PostgreSQL log export.
- **`log_lock_waits`** and **`deadlock_timeout`**: aids investigating lock waits per configuration.
- **`log_connections` / `log_disconnections`**: diagnoses connection churn, though increases log volume.
- **`log_min_duration_sample` / `log_statement_sample_rate`**: samples slow statements on supported versions.

### 7.1. Parameter-group example for slow SQL

Reference values:

~~~text
log_min_duration_statement = 1000
log_statement = none
log_destination = stderr
log_lock_waits = on
~~~

- **1000 ms = 1 second**: logs sufficiently slow SQL statements.
- **`log_statement = none`**: avoids logging all normal DML/queries.
- **`log_lock_waits = on`**: surfaces lock waits exceeding the configured deadlock timeout.
- Manage most settings in an engine-appropriate **custom DB parameter group** or **DB cluster parameter group**; dynamic/static behavior and reboot needs depend on parameter and version.

**Never edit production parameters directly without approval, a baseline, and a rollback plan.** Some settings use AWS RDS managed controls, so verify you are editing the right instance/cluster parameter group.

### 7.2. Exporting PostgreSQL logs to CloudWatch Logs

In the RDS Console/CLI/IaC, enable **CloudWatch log exports** for log type **`postgresql`** where supported. Once enabled, CloudWatch Logs receives **new logs** going forward; it does not backfill all historical logs by default.

Example log groups:

~~~text
/aws/rds/instance/orders-postgres/postgresql
/aws/rds/cluster/orders-aurora/postgresql
~~~

Exact paths depend on RDS/Aurora instance/cluster names and service conventions.

### 7.3. Performance and security impact of logging

**Never** set `log_min_duration_statement = 0` and `log_statement = all` across production long-term without measuring the impact:

- The database must format and write massive volumes of log lines.
- Exporting to CloudWatch Logs consumes extra CPU and I/O.
- Log lines can expose SQL text, literals, PII, and passwords/tokens if the app concatenates values directly into SQL.
- CloudWatch Logs bills grow across ingestion, storage, and Logs Insights scans.
- Application error logs may also duplicate the same statement repeatedly.

An **AWS Database Blog post (November 2026)** warns about verbose logging impacts on Aurora PostgreSQL: excessive query/audit logs can become a bottleneck themselves. Use **intentional thresholds and sampling**, measure before/after performance, and bound retention.

### 7.4. Distinguish SQL execution duration from lock waits

A slow query might use only 20 ms of CPU while waiting 3 seconds on a lock. Slow logs record elapsed wall-clock time without explaining why.

Workflow:

1. Grab the statement, timestamp, and available session identifiers from the slow log.
2. Compare against Database Insights **top waits**.
3. Check `pg_stat_activity`/`pg_locks` around that timestamp.
4. If Lock waits dominate, locate the **blocking transaction** and code holding transactions too long.
5. If CPU/I/O dominates, inspect **`EXPLAIN`, indexes, table stats, and buffer cache**.

## 8. MySQL and Aurora MySQL slow query logging

MySQL/Aurora MySQL use these parameters:

- **`slow_query_log = 1`**: enables the slow query log.
- **`long_query_time`**: query duration threshold in **seconds**, e.g., `1.0` = one second.
- **`log_output = FILE`**: required to export the slow query log to CloudWatch Logs.
- **`log_queries_not_using_indexes`**: logs queries not using indexes; can produce far more logs than expected.
- **`min_examined_row_limit`**: minimum rows examined threshold, depending on engine/version.

### 8.1. Sample parameters

~~~text
slow_query_log = 1
long_query_time = 1.0
log_output = FILE
log_queries_not_using_indexes = 0
~~~

A query taking **0.8 seconds** will **not be logged** when `long_query_time = 1.0`. That does not mean the query is fast relative to a 200 ms API p95 SLO.

RDS for MySQL may default to `log_output = TABLE`, whereas Aurora MySQL versions default to `FILE`; **check actual parameter values** rather than assuming all engines match.

### 8.2. `FILE` vs. `TABLE`

| Log type | Advantages | Risks |
| --- | --- | --- |
| **`FILE`** | Works with CloudWatch Logs export; easy centralized analysis. | File/log volume and CPU/I/O overhead still require control. |
| **`TABLE`** | Query `mysql.slow_log` directly in SQL per engine. | Adds write load, grows log table, and does not feed CloudWatch slow log exports. |
| **`NONE`** | No slow/general logs written. | No slow logs available for analysis. |

To get slow logs into CloudWatch Logs for RDS/Aurora MySQL, you must configure all of the following:

1. Enable **`slow_query_log`**.
2. Set **`log_output = FILE`**.
3. Enable **`slowquery`** log export to CloudWatch Logs per engine.
4. Ensure queries exceed **`long_query_time`**.
5. Verify Region, log group, and IAM log-read permissions.

### 8.3. Detecting unindexed queries

**`log_queries_not_using_indexes = 1`** helps catch full scans, yet never leave it on indefinitely in high-volume small-query workloads: it floods logs even for fast queries on tiny tables. Not every unindexed query is bad; scanning a few dozen rows is often cheaper than an index lookup.

### 8.4. Illustrative MySQL slow log

~~~text
# Time: 2026-11-20T03:10:00.123456Z
# User@Host: app_user[app_user] @  [10.0.2.42]
# Query_time: 3.240000  Lock_time: 0.010000
# Rows_sent: 20  Rows_examined: 1500000
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**This data is an example**, not a real production log. Notice **`Rows_examined` is vastly larger than `Rows_sent`**: likely a missing composite index on `(customer_id, created_at)` or a suboptimal optimizer plan. Before adding an index, confirm data distribution, write costs, and actual `EXPLAIN` output.

## 9. PostgreSQL: diagnosing sessions, slow SQL, and locks with SQL

The SQL below is for **reading state and statistics**. Run only on authorized databases; even diagnostic `SELECT`s consume CPU/I/O and can expose other sessions' SQL text if the principal has broad privileges.

### 9.1. Inspect current sessions via `pg_stat_activity`

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname IS NOT NULL
GROUP BY datname, usename, application_name,
         state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

From this, distinguish:

- **`active`**: session currently executing a query.
- **`idle`**: session not running a query while holding an open connection.
- **`idle in transaction`**: open transaction waiting on client; may hold locks and snapshots.
- **`wait_event_type = Lock`**: waiting on a lock.
- **`wait_event_type = IO/Client/...`**: wait category per PostgreSQL version/engine.

**Risk:** many `idle` sessions are not necessarily a bug if pools are sized intentionally; **long `idle in transaction`** sessions are far more dangerous because they hold locks and block vacuuming.

### 9.2. Top running queries by age

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start ASC
LIMIT 20;
~~~

**`query_age`** can include wait time (locks/I/O/network), not exclusively CPU time. SQL text may contain sensitive data; restrict access and redact logs before sharing.

### 9.3. Identify long-open transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
~~~

If a Java request opens a transaction and then makes a multi-second external HTTP call, the transaction holds locks unnecessarily. Fix transaction boundaries in the application rather than just increasing DB pool size.

### 9.4. Find blockers safely

PostgreSQL provides **`pg_blocking_pids(pid)`** to identify which sessions are blocking a PID:

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.usename,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS wait_or_query_age
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY wait_or_query_age DESC;
~~~

Use the output to investigate the **blocking transaction**. Never reflexively run **`pg_terminate_backend`** in production—it mutates state, rolls back transactions, and can disrupt customers.

### 9.5. Cumulative statistics with `pg_stat_statements`

If the **`pg_stat_statements`** extension is enabled with sufficient privileges:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_ms,
    round(mean_exec_time::numeric, 2) AS avg_ms,
    round(max_exec_time::numeric, 2) AS max_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Notes:

- **High `total_exec_time`** can stem from a query called millions of times, not necessarily slow single executions.
- **`mean_exec_time`/`max_exec_time`** separate steady hot paths from outliers.
- **High `shared_blks_read`** relative to hits suggests disk/storage reads; check caching and intervals.
- Query text is typically **normalized**, so it does not replace raw literal logs when exact parameters are needed.
- `pg_stat_statements` works only if the extension/shared preload library is installed; enabling preload may require a restart per engine/version.
- Cumulative counters reset on restart or explicit stats reset; always check the measurement interval rather than comparing raw lifetime numbers.

### 9.6. `EXPLAIN` and `EXPLAIN ANALYZE`

Example:

~~~sql
EXPLAIN
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**`EXPLAIN` without `ANALYZE`** shows only the estimated plan without executing the `SELECT`. Use it to spot Seq Scans, Index Scans, Sorts, and row estimates.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**`EXPLAIN ANALYZE` ACTUALLY EXECUTES the query**, consuming CPU/I/O, taking locks, and triggering functions with side effects. **Never run `EXPLAIN ANALYZE` on DML** in production without assessing impact. Even for large `SELECT`s or queries calling volatile functions, control load carefully. Best practice is testing on staging or a snapshot with representative data first.

### 9.7. Index planning example

If the API frequently runs:

~~~sql
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

A candidate index:

~~~sql
-- Design illustration only; do not run during a read-only observation exercise.
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

Rationale: filters by `customer_id` and returns newest `created_at` first. However, evaluate selectivity, write volume, storage footprint, MVCC, planner usage, and locking/online `CONCURRENTLY` requirements. **`CREATE INDEX` mutates the database** and is not part of read-only SQL diagnostics.

## 10. MySQL: Performance Schema, processlist, and execution plans

### 10.1. Inspect connection state

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW VARIABLES LIKE 'max_connections';
~~~

- **`Threads_connected`**: currently open connections.
- **`Threads_running`**: threads actively executing (not sleeping), distinct from total connections.
- **`Connections`**: cumulative connection attempts since server start/reset.
- **`Aborted_connects`**: failed connection attempts per server semantics.
- **`max_connections`**: configured cap, with reserved slots for maintenance/admin depending on engine.

Remember that cumulative Global Status counters require computing **deltas over time**, never treating lifetime totals as requests per second.

### 10.2. `SHOW PROCESSLIST`

~~~sql
SHOW FULL PROCESSLIST;
~~~

Shows threads in **`Sleep`**, **`Query`**, lock-wait, or sending-data states. Only users with appropriate privileges can view all other sessions.

**Never automatically `KILL`** active production sessions just to lower `Threads_connected`; classify the transaction, blast radius, and connection owner first.

### 10.3. Performance Schema top SQL digests

If **`performance_schema`** and its statement summary tables are enabled:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1e12, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1e12, 3) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

**Timer units** in `TIMER_WAIT` columns are typically picoseconds, though verify for your exact engine/version/plugin. The table may be absent or empty if Performance Schema instruments/consumers are disabled. Never copy this MySQL query directly onto PostgreSQL.

### 10.4. MySQL Explain

~~~sql
EXPLAIN FORMAT=JSON
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Inspect the plan for:

- Full table scan vs. index range/ref lookup.
- Row estimates and filtered percentages.
- Filesort or temporary table operations.
- Join order and join method.
- Chosen index vs. expected index.

**`EXPLAIN ANALYZE`** in supported MySQL versions also executes the query; never assume it is zero-impact just because it starts with `EXPLAIN`.

## 11. Slow SQL is not only caused by missing indexes

~~~mermaid
flowchart TD
    S["Query latency rises"] --> Q{"DB Insights top wait / plan?"}
    Q -->|"CPU"| CPU["Query plan, scans/joins/sorts, data/hot SQL"]
    Q -->|"Lock"| LOCK["Blocking transaction, isolation level, idle-in-transaction"]
    Q -->|"I/O"| IO["Cache misses, storage throughput, query access patterns"]
    Q -->|"Network/client"| NET["Returned rows, client fetch, pools, DB driver"]
    Q -->|"Commit/log"| WAL["WAL/redo pressure, checkpoints, write workload"]
    CPU --> VERIFY["Re-measure p95, DBLoad, CPU, business correctness"]
    LOCK --> VERIFY
    IO --> VERIFY
    NET --> VERIFY
    WAL --> VERIFY
~~~

### 11.1. Missing indexes and suboptimal plans

Symptoms: **huge `Rows_examined`**, I/O-heavy sequential scans, large `ORDER BY` sorts. Analyze:

- Query predicates and composite index column order.
- Table statistics (PostgreSQL `ANALYZE`/autovacuum or MySQL optimizer stats).
- Index selectivity against actual data skew.
- ORM/Hibernate N+1 query patterns.
- Fetching too many columns/rows instead of paginating.

Adding indexes carries trade-offs: write amplification, storage, maintenance, and potential deployment locks.

### 11.2. Lock contention

Symptoms: **`DBLoadNonCPU` rises, top wait = Lock, CPU stays modest**.

Common causes:

- Long-running transactions from a Java **`@Transactional`** method wrapping an external HTTP call.
- Concurrent updates contending on the same hot row.
- DDL/schema migrations blocking table access.
- Deadlocks or lock timeouts.
- Overly strict transaction isolation levels.

Fixes: shorten transactions, enforce consistent lock ordering, move external calls outside transactions, shard hotspots, add idempotent retries, and use safe migration windows. Never assume adding vCPUs resolves locks.

### 11.3. Storage I/O

Symptoms: **`ReadLatency`/`WriteLatency`/`DiskQueueDepth`** climb alongside p95 query latency and I/O waits.

Inspect:

- Storage type and actual **IOPS/throughput** limits.
- RDS gp2 burst credits vs. gp3 provisioned performance.
- Read/write access patterns and buffer cache hit ratios.
- Aurora I/O semantics (distinct from RDS EBS) and Aurora I/O-Optimized vs. Standard.
- Impact of maintenance, backups, and long table scans.
- Cross-AZ/Region transfers or network congestion.

### 11.4. Low DB server CPU yet slow responses

Low CPU happens when:

- Sessions are **waiting on locks**.
- Connection pools fail to hand out connections to the app.
- Queries wait on network responses or storage I/O.
- Replica lag or application retry loops occur.
- The Java service waits on external dependencies outside the DB while users blame “slow database.”

**Do not upgrade the DB instance just because API p95 is high.** Trace endpoint → pool → SQL → backend waits first.

## 12. Database connections: the backbone of Java performance

### 12.1. Every connection consumes real resources

Each DB connection/session allocates network sockets, memory, authentication/session state, and transaction structures. PostgreSQL spawns backend processes per engine architecture; MySQL allocates threads and server buffers.

Too many connections cause:

- **`too many clients already`** (PostgreSQL) or **`Too many connections`** (MySQL) errors.
- Rising RAM usage, context switching, and contention.
- Slow connection setup due to TLS and auth overhead.
- Rising **HikariCP connection acquisition wait times** and request timeouts.
- **Connection storms** when many app instances reconnect after a failover.

### 12.2. Pool size is not requests/second

In Spring Boot/HikariCP:

- **`maximumPoolSize`** is the max DB connections maintained by **one application instance**, not system-wide.
- **`minimumIdle`** sets the target idle connections retained.
- **`connectionTimeout`** caps how long a thread waits to borrow a connection.
- **`maxLifetime`/`idleTimeout`/`keepaliveTime`** govern connection lifecycle and must align with server/Proxy timeouts.
- **`leakDetectionThreshold`** helps catch connection leaks, though avoid overly noisy logging in production without evaluating impact.

### 12.3. Initial formula for connection capacity

Assume:

- 12 ECS tasks.
- Each task has **`maximumPoolSize = 15`**.
- 2 admin/maintenance apps each hold up to 10 connections.
- Database **`max_connections = 300`**.

Upper bound from app pools:

\[
12\times15+2\times10=200
\]

Leave headroom for RDS/admin tasks, ETL, BI, failover, RDS Proxy/internal sessions, and bursts. If Auto Scaling scales from 12 to 24 tasks:

\[
24\times15+2\times10=380
\]

This can **exceed 300** even while each individual task looks healthy. That is why scaling compute without bounding DB connections can trigger severe outages.

**Never allocate `max_connections - 0` to apps.** Leave operational headroom per DB engine and maintenance needs.

### 12.4. Little's Law and connection occupancy

Estimate **concurrent DB query load**:

\[
L \approx \lambda\times W
\]

Where:

- \(\lambda\): DB operations per second.
- \(W\): average time an operation holds a connection, in seconds.
- \(L\): average concurrent active operations.

For example, 200 queries/second averaging 50 ms connection hold time:

\[
L\approx200\times0.05=10
\]

This does not mean production needs literally 10 connections: bursts, multi-query transactions, CPU/lock tail latency, driver overhead, pool acquisition, and failovers all demand headroom. Rely on **p95 pool pending/wait metrics** and load tests rather than a formula alone.

### 12.5. Diagnose before raising pool size

When **`HikariPool - Connection is not available`** occurs:

1. Inspect **HikariCP active, idle, pending, max** and **connection acquisition p95**.
2. Inspect DB **`DatabaseConnections`**, engine `max_connections`, and DB Load.
3. Look for long queries/transactions, connection leaks, or `idle in transaction` sessions.
4. Check network/TLS/auth errors and DNS endpoint validity.
5. Check application instance count and multiplicative pool scaling.
6. Increase pool size only if **the database has spare capacity** and load tests prove it helps.

Bumping pool size from 10 to 50 across 20 ECS tasks lets the DB hit **1,000 connections**, worsening saturation.

## 13. RDS Proxy: reducing connection churn and protecting the database

**Amazon RDS Proxy** is a managed connection proxy tier between apps and supported RDS/Aurora engines/Regions. It is especially helpful when:

- Lambda experiences **burst concurrency** with many execution environments opening connections simultaneously.
- Rapid ECS/EKS/EC2 scale-outs cause connection storms.
- Workloads can share database connections across client sessions.
- Failovers occur and you want smoother resilience via proxy routing/connection management.
- DB `max_connections` must be shielded from bursts.

~~~mermaid
flowchart LR
    subgraph APPS["Applications"]
      L1["Lambda #1"] --> P["RDS Proxy"]
      L2["Lambda #2"] --> P
      ECS["ECS tasks"] --> P
    end
    P -->|"Pooled DB connections"| W["RDS/Aurora writer"]
    P -->|"Reader role if supported"| R["Aurora readers / Multi-AZ DB cluster readers"]
    W --> MET["AWS/RDS DatabaseConnections"]
    P --> PROXYMET["AWS/RDS Proxy metrics"]
~~~

**RDS Proxy does not grant infinite database connections.** It pools and multiplexes backend connections within pool limits; session-state-dependent operations trigger **connection pinning**, reducing multiplexing efficiency.

### 13.1. RDS Proxy metrics

| Metric | What to know | Interpretation |
| --- | --- | --- |
| **`ClientConnections`** | Client connections to the Proxy. | Sudden jumps indicate app scale-out or reconnect storms. |
| **`DatabaseConnections`** | Backend connections from Proxy to DB. | Compare with `ClientConnections` to measure reuse. |
| **`MaxDatabaseConnectionsAllowed`** | Backend connection ceiling allowed to Proxy for the target. | Usually below engine `max_connections` due to reserved/internal headroom. |
| **`DatabaseConnectionsBorrowLatency`** | Time for Proxy to acquire a DB connection for a client. **Unit: microseconds** per metric. | Spikes indicate pool contention or pinning. |
| **`DatabaseConnectionsCurrentlyBorrowed`** | Backend connections currently borrowed by clients. | Staying near ceiling drives up borrow latency. |
| **`DatabaseConnectionsCurrentlyInTransaction`** | Connections inside an active transaction. | Long transactions block multiplexing. |
| **`DatabaseConnectionsCurrentlySessionPinned`** | Connections pinned to session state. | High pin ratios force 1:1 backend connections per client. |
| **`ClientConnectionsSetupFailedAuth`** | Client auth/TLS setup failures. | Inspect Secrets Manager, IAM auth, TLS, and configuration. |
| **`QueryResponseLatency`** | Proxy time from request receipt to response. | Compare against DB query latency and network latency. |

Metric names, statistics, and dimensions vary by proxy config, target group, and engine; verify against CloudWatch **RDS Proxy metrics** docs before creating alarms. AWS recommends **`Sum`** per minute/dimension for certain Proxy gauges—do not mechanically apply `Average` to every gauge.

### 13.2. What causes high `DatabaseConnectionsBorrowLatency`?

Possible causes:

- `MaxConnectionsPercent` set too low for traffic.
- Backend DB sessions holding transactions too long.
- Many sessions **pinning**.
- DB hitting `max_connections` or resource saturation.
- Reconnects/failovers or auth/TLS timeouts.
- Longer query/transaction durations delaying connection return to the pool.

**Diagnosis:** correlate `BorrowLatency` + `CurrentlyBorrowed` + `MaxDatabaseConnectionsAllowed` + `SessionPinned`, then inspect Database Insights top waits/SQL. Do not immediately raise `MaxConnectionsPercent` to 100%: AWS recommends leaving ~**30%** headroom above peak usage so the Proxy can rebalance connections.

### 13.3. Session pinning

Commands modifying **session state** prevent the Proxy from safely reusing a DB connection for another client. Depending on engine/protocol, pinning relates to:

- Temporary tables.
- Session variables or `SET` statements.
- Prepared statements and session state.
- Transaction duration and locks.
- Specific SQL statements or driver behaviors.

Never apply a MySQL pinning list verbatim to PostgreSQL. Review engine-specific **pinning limitations and query patterns**. If pinning stays high, the Proxy may not deliver expected DB connection reductions.

### 13.4. IAM auth and secret rotation

RDS Proxy supports **AWS Secrets Manager** and **IAM authentication** in supported configurations. Ensure:

- Proxy's IAM role can access the secret.
- KMS decrypt permissions if using a customer managed key.
- Security Group ingress/egress from app → Proxy and Proxy → DB.
- Matching TLS certificates and client driver settings.
- Secret rotation handling and connection lifetimes.

**The Proxy does not fix a DB missing indexes, lock contention, or bad SQL.** It is a connection/failover management tool, not a query optimizer.

## 14. Aurora: monitoring writer, readers, replication, and Serverless

### 14.1. Aurora-specific metrics

| Metric | Applies to | How to interpret |
| --- | --- | --- |
| **`AuroraReplicaLag`** | Aurora read replica instance. | Replication lag, typically reported in milliseconds. |
| **`AuroraReplicaLagMaximum`** | Cluster/writer per supported dimension. | Highest lag across all replicas. |
| **`ServerlessDatabaseCapacity`** | Aurora Serverless. | Current compute capacity in **ACUs**. |
| **`ACUUtilization`** | Aurora Serverless. | Ratio of current ACU to configured **maximum ACU**. |
| **`VolumeBytesUsed`** | Aurora cluster storage. | Consumed cluster volume storage. |
| **`VolumeReadIOPs`** | Aurora storage read I/O. | I/O usage; informs Standard vs. I/O-Optimized pricing. |
| **`VolumeWriteIOPs`** | Aurora storage writes. | I/O usage; do not read identically to RDS EBS `WriteIOPS`. |
| **`BufferCacheHitRatio`** | Eligible engines/instances. | Fraction of reads served from buffer cache; interpret in workload context. |
| **`FreeLocalStorage`** | Emitted on eligible engines/instances. | Local temporary storage free space—**not** shared Aurora cluster storage. |

**Do not copy RDS instance `FreeStorageSpace` alerts blindly to Aurora.** Aurora uses a shared storage model with distinct local temp vs. cluster volume metrics.

### 14.2. Aurora replica lag

An API reading from a reader right after writing to the writer can briefly see stale state. As replication lag climbs:

- Apps show un-updated order statuses.
- Reports/dashboards fall behind the writer.
- Failover and read routing grow more complex.
- Clients may retry and amplify load.

**Adding readers is not the only fix.** Check write rates, reader load, queries blocking replication apply, transaction semantics, instance classes, and replication config. For flows requiring read-after-write, route reads to the writer or use a consistency-aware pattern.

### 14.3. Aurora Serverless v2 ACUs and bottlenecks

**Aurora Serverless** adjusts compute capacity in ACUs within **`MinCapacity`/`MaxCapacity`**.

Example:

- `Min = 2 ACU`, `Max = 16 ACU`.
- At peak, **`ServerlessDatabaseCapacity = 16`**.
- **`ACUUtilization = 100%`**: capacity has hit its configured ceiling.
- DB Load, CPU/waits, and p95 latency rise together → scaling is capped; examine both queries and max ACUs.

If ACUs hit max while DB Load waits mostly on **row locks**, raising max ACUs may not help. If ACUs remain low while API latency spikes, look at connection pools, networking, or query waits.

### 14.4. Tuning Aurora goes beyond picking ACUs or instance classes

- Separate hot write transactions from heavy reporting reads where supported.
- Validate reader endpoint distribution and routing consistency.
- Measure DB Load/top SQL on **the writer and each reader**.
- Index properly to avoid full scans thrashing reader storage/caches.
- Evaluate Aurora I/O-Optimized when I/O dominates spend per Pricing Calculator.
- Monitor global replication lag for Aurora Global Database separately from in-Region `AuroraReplicaLag`.
- Enforce backups/restores, failover drills, and DR targets (RPO/RTO).

### 14.5. RDS Multi-AZ: availability differs from performance

Multi-AZ protects availability during instance/AZ failures, without automatically boosting app query throughput. Specifically, in a traditional **RDS Multi-AZ DB instance** deployment, the standby does not serve read queries; Multi-AZ DB clusters offer readable members under a different model.

During failover, monitor:

- **RDS events** for failover/reboot.
- DB endpoint DNS resolution and JDBC reconnect times.
- HikariCP stale connections.
- RDS Proxy target health/borrow latency if used.
- Transaction retries and idempotency (never double-charge/double-process payments).

## 15. Dashboards and alarms: minimal yet focused

A well-structured production dashboard for Orders separates into clear panels:

~~~mermaid
flowchart TB
    SLO["API SLIs: p95, error rate, successful orders"] --> DASH["RDS/Aurora dashboard"]
    DBI["DB Insights: DBLoad, top SQL, waits"] --> DASH
    CONN["Connections, pool pending, Proxy borrow latency"] --> DASH
    HOST["CPU, memory, IOPS, latency, storage"] --> DASH
    HA["Replica lag, events/failover, backups"] --> DASH
    COST["ACUs/instances, I/O, logs, Proxy cost"] --> DASH
    DASH --> ALARM["CloudWatch Alarms + SNS/incident runbook"]
~~~

### 15.1. Suggested alarms (illustrative thresholds)

| Metric | Example threshold | Action when breached |
| --- | --- | --- |
| **API p95** | > 500 ms for 10 minutes. | Isolate app vs. DB latency via traces. |
| **`CPUUtilization`** | > 80% continuously for 10–15 minutes. | Inspect `DBLoadCPU`, top SQL, CPU credits, background tasks. |
| **`FreeableMemory`** | Sustained drop below safe baseline. | Inspect Enhanced Monitoring, swap, connections/caches. |
| **`DatabaseConnections`** | > 80% of effective connection limit. | Check pool fan-out, long transactions, app scaling. |
| **`DBLoad` / vCPU** | Exceeds vCPU capacity alongside CPU waits. | Check hot SQL, CPU, query plans before resizing instance. |
| **`ReadLatency` / `WriteLatency`** | Elevated above baseline/SLO across multiple periods. | Check storage/IOPS/queue depth and query patterns. |
| **`FreeStorageSpace`** | Below 15–20% or growth-adjusted floor **on applicable RDS instances**. | Plan storage/autoscaling/cleanup before hitting full. |
| **`AuroraReplicaLag`** | Exceeds freshness SLO. | Inspect readers, write workload, read routing. |
| **`ACUUtilization`** | Sustained near 100% with rising latency. | Inspect Max ACU, DB Load/waits, cost. |
| **RDS Proxy borrow latency** | Multiples above baseline or exceeding SLO. | Check pinning, pool usage, DB `max_connections`. |
| **Slow-query count** | Rising alongside degraded response times. | Find top SQL by total time, locks/plans. |
| **RDS failover events** | Any production-impacting event. | Run reconnect runbook, verify multi-AZ health and data consistency. |

No single threshold like **`DatabaseConnections = 100`** fits every instance. `max_connections` varies by engine, instance memory, parameter groups, users, and app topology.

### 15.2. Choose the right statistic

- **`CPUUtilization`:** `Average`/`Maximum` depending on goal.
- **`DatabaseConnections`:** usually `Average`/`Maximum` to see open connection count; never use `Sum` as “total connections per hour.”
- **IOPS/throughput:** `Average`/`Maximum` matching time series and units.
- **`FreeStorageSpace`:** `Minimum` to catch near-exhaustion.
- **Replica lag:** `Maximum` when freshness SLOs care about worst-case lag.
- **DB Load:** `Average` (AAS); compare `DBLoadCPU` against vCPU count.
- **RDS Proxy metrics:** follow each metric's official statistic guidance rather than forcing one pattern across all gauges.

Depending on engine, a metric lacking datapoints may be **not emitted / not applicable** rather than guaranteed zero.

### 15.3. Missing data handling and alarm actions

For low-traffic workloads, CloudWatch metrics may have gaps. Set **`treatMissingData`** intentionally:

- “No traffic” may be normal for a sleeping dev DB.
- “DB must serve continuously” should pair with health checks and heartbeats.
- Do not treat `DBLoad` not emitting while idle as proof of failure.

Every alarm needs an owner, severity, runbook, rollback path, and review cadence. **Never wire alarms directly to auto-scale databases/storage or reboot RDS without guardrails.**

## 16. Spring Boot/HikariCP: instrumenting connection pools and queries

### 16.1. Reference configuration

~~~properties
spring.datasource.url=jdbc:postgresql://orders-db.internal.example:5432/orders
spring.datasource.username=orders_app

# Password injected via secret injection / Secrets Manager; never commit.
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.idle-timeout=600000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.leak-detection-threshold=0

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=orders-api
management.metrics.tags.environment=prod
~~~

This is an **example for Spring Boot**, not a universally safe default. Protect **`metrics`/`prometheus` endpoints** with networking and authorization; never expose internal metadata to the Internet. Test Hikari settings against DB connection lifetimes, NAT/proxies, failovers, readiness probes, and app replica counts.

### 16.2. Common HikariCP metrics

With Micrometer/Spring Boot Actuator, metrics include:

- **`hikaricp.connections.active`**: connections currently borrowed.
- **`hikaricp.connections.idle`**: idle connections in the pool.
- **`hikaricp.connections.pending`**: threads waiting for a connection.
- **`hikaricp.connections.max`**: maximum pool size.
- **`hikaricp.connections.acquire`**: time spent acquiring a connection.
- **`hikaricp.connections.usage`**: duration a connection stays borrowed.
- **`hikaricp.connections.timeout`**: count of connection acquisition timeouts.

Exact names/tags depend on Micrometer/Spring Boot versions and registries. Comparing p95 `acquire` and `pending` reveals whether **the app is waiting on the pool** or **already holds a connection waiting on SQL execution**.

### 16.3. Tagging applications on DB sessions

PostgreSQL supports the **`ApplicationName`** JDBC connection parameter on compliant drivers. Lab URL example:

~~~text
jdbc:postgresql://orders-db.internal.example:5432/orders?ApplicationName=orders-api
~~~

`pg_stat_activity` can then group by **`application_name`**, pinpointing which service opens too many connections.

Never put customer or user IDs into `application_name`: it causes high cardinality, leaks data, and degrades monitoring.

### 16.4. Connection leaks and long transactions

If Hikari `active` stays pinned at `max` and `pending` climbs while DB CPU stays low, suspect:

- Code failing to return connections after exceptions (e.g., raw JDBC missing try-with-resources).
- Transactions holding connections while waiting on HTTP calls.
- Queries blocked by locks or missing timeouts.
- Streaming JDBC `ResultSet`s held open too long.
- Pool timeouts too short for workload or an ongoing DB failover.

Clean raw JDBC example:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(String orderId) throws Exception {
        String sql = "SELECT 1 FROM orders WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setQueryTimeout(2);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

This illustrates **try-with-resources**, guaranteeing the JDBC connection returns to the pool when exiting the block, even on exceptions. Do not run queries without a matching table, schema, and authorized DB credentials. With Spring Data JPA, the framework manages connections/transactions per context—still audit transaction boundaries carefully.

### 16.5. ORM N+1 problem

A Spring Data/JPA endpoint might execute:

1. One `SELECT` fetching 100 orders.
2. 100 `SELECT`s fetching `orderItems` for each order.
3. 100 `SELECT`s fetching `customer` for each order.

Total: **201 queries** for a single request. Even at 5 ms each, network and DB round trips exceed 1 second. Fixes include **join fetch, batch fetching, or projections**, alongside pagination and memory checks. Database Insights top SQL highlights a digest with massive call counts and high total execution time.

**Optimize the whole request**, not just the single query with the highest `max` duration.

## 17. Securing monitoring, logs, and diagnostic queries

### 17.1. Boundary between IAM and DB privileges

| Principal | Needed permissions | Restrictions |
| --- | --- | --- |
| **App runtime role** | Secrets Manager/KMS, required business AWS APIs; least-privilege DB user. | Never grant `rds:*` or DB `SUPERUSER`. |
| **Monitoring read-only role** | Scoped `rds:Describe*`, `cloudwatch:GetMetricData`, `logs:GetQueryResults`, `pi:GetResourceMetrics`. | Never grant `ModifyDBInstance`, `StartDBInstance`, or `DeleteDBInstance`. |
| **DB monitoring SQL user** | Diagnostic views and permitted `EXPLAIN`s. | Do not grant broad read access to business PII unless needed. |
| **DBA/operator** | Authorized to adjust parameters/indexes/queries via change management. | Separate from read-only metric viewing and initial triage. |
| **Security/Audit** | CloudTrail, log retention, KMS, IAM role reviews. | Never expose SQL literals or user PII. |

**Read-only AWS IAM does not grant SQL `SELECT` access inside the database.** Diagnostic SQL requires an appropriate DB login/role; **`rds:DescribeDBInstances`** does not let you run `SELECT` over JDBC.

### 17.2. SQL text can contain secrets and PII

Unsafe SQL example:

~~~sql
SELECT * FROM users
WHERE email = 'customer.private@example.invalid'
  AND password = 'plain-text-example';
~~~

This is an **anti-pattern to avoid**. If an app concatenates literals directly, slow logs, Database Insights top SQL text, `pg_stat_activity`, and error logs can capture sensitive data.

Best practices:

- Use **prepared statements / bind parameters** to prevent SQL injection and avoid literal leaks.
- Avoid logging full query parameters in apps or proxies.
- Share only normalized SQL digests and redacted plans.
- Enforce CloudWatch Logs retention, access controls, encryption, and auditing.
- Restrict access to views exposing other sessions' SQL text.
- Never download production logs to unapproved personal laptops.

### 17.3. Log overhead can worsen an incident

Setting `log_statement = all` or `long_query_time = 0` forces the database to format and export huge log volumes, spiking CPU, I/O, and CloudWatch ingestion—**making a performance incident worse**. In production:

1. Start with a 1-second threshold or an SLO-aligned value.
2. Try sampling first.
3. Monitor query p95 and DB CPU/IO while enabled.
4. Time-box debugging and cap log group retention.
5. Dial verbosity back down once the incident ends.
6. Secure log access and sharing.

### 17.4. CloudTrail and RDS events are not SQL audit logs

- **CloudTrail** records AWS control-plane API calls per configuration, such as `ModifyDBInstance` or `RebootDBInstance`.
- **RDS events** record lifecycle events like failover, maintenance, backups, and parameter changes per engine.
- **Slow query logs** capture SQL exceeding duration thresholds.
- **Database audit logs / `pgAudit` / MySQL audit** serve operational SQL auditing with their own overhead.
- **App audit/business events** record business actions, actors, and tenants per policy.

Never assume CloudTrail automatically logs **every SQL `SELECT` query** in the database.

## 18. Cost: Database Insights, logs, storage, and proxies

### 18.1. Cost drivers to track

| Item | Drivers |
| --- | --- |
| **RDS/Aurora compute** | Instance class, instance count, running hours, Aurora Serverless ACUs. |
| **Storage and I/O** | EBS size, gp3/provisioned IOPS, Aurora volume/I/O pricing model, snapshots. |
| **CloudWatch Database Insights** | Standard vs. Advanced mode, retention, per-query/advanced features per current pricing. |
| **Enhanced Monitoring** | OS metric interval shipped to CloudWatch Logs; log ingest/storage. |
| **Slow query/general/audit logs** | Log volume, CPU/I/O overhead, CloudWatch Logs ingestion/queries. |
| **CloudWatch alarms/dashboards** | Metrics/alarms, custom metrics, Logs Insights query scans. |
| **RDS Proxy** | Proxy capacity/usage per rate card, plus networking and Secrets Manager. |
| **Data transfer** | Cross-AZ/Region paths and replication per service; verify exact pricing tables. |
| **Backups/snapshots** | Storage retention and cross-Region copies when configured. |

**Never assume “1-second Enhanced Monitoring is always free.”** Higher sampling rates increase CloudWatch Logs charges. Database Insights Standard has a baseline retention, whereas Advanced and extended retention bill per feature plan and Region.

### 18.2. Do not optimize costs by turning off all monitoring

A business-critical production DB suffers heavily when you:

- Cannot identify which SQL caused an outage.
- Miss storage nearing exhaustion.
- Miss replica lag causing stale reads.
- Miss failures and surging connection counts.
- Lack before/after baselines when sizing instances.

Prioritize **cost-effective observability**: keep core metrics and alarms always on, tune retention and log verbosity, enable deep profiling selectively, and reserve Advanced mode for critical databases.

### 18.3. Cost-per-transaction example

Suppose over one month a service incurs:

- DB compute + storage + I/O: 500 cost units.
- Monitoring/logs: 40 units.
- RDS Proxy: 60 units.
- Successfully processes **2,000,000 orders**.

\[
\text{Cost per 1000 orders}
=\frac{500+40+60}{2{,}000{,}000}\times1000
=0.3\ \text{cost units}
\]

If query tuning lowers DB compute/storage demand without raising error rates while meeting SLOs, that is a measurable optimization. **These numbers are not AWS unit prices**, purely an illustrative KPI.

## 19. Read-only AWS CLI: RDS and Aurora

The examples below **describe/read metrics and logs** without creating or modifying resources. Verify IAM principal, Region, and DB identifier first. **Do not run `modify-db-instance`, `reboot-db-instance`, or `modify-db-parameter-group` in this exercise.**

### 19.1. Account and Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

If a DB is missing, check account, Region, and permissions before assuming it was deleted.

### 19.2. Inspect RDS DB instances

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query "DBInstances[].{Name:DBInstanceIdentifier,Engine:Engine,Class:DBInstanceClass,Status:DBInstanceStatus,AZ:AvailabilityZone,Cluster:DBClusterIdentifier,ResourceID:DbiResourceId,MonitoringInterval:MonitoringInterval,DatabaseInsights:DatabaseInsightsMode,PerfInsights:PerformanceInsightsEnabled}"
~~~

Key fields:

- **`DbiResourceId`** is the resource identifier passed to **`pi:GetResourceMetrics`** or `DescribeDimensionKeys`.
- **`DBClusterIdentifier`** shows which cluster an instance belongs to.
- **`MonitoringInterval = 0`** means Enhanced Monitoring is disabled.
- **`DatabaseInsightsMode`/`PerformanceInsightsEnabled`** vary by engine and CLI version.

### 19.3. Inspect cluster members and endpoints

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --query "DBClusters[].{Cluster:DBClusterIdentifier,Engine:Engine,Status:Status,Endpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Members:DBClusterMembers,Capacity:ServerlessV2ScalingConfiguration,Insights:DatabaseInsightsMode}"
~~~

Check **`IsClusterWriter`** in `DBClusterMembers` when diagnosing failover. Never watch an old reader's metrics assuming it is still the writer after roles shift.

### 19.4. Parameter groups and log exports

~~~bash
aws rds describe-db-parameters \
  --db-parameter-group-name orders-postgres-custom \
  --region ap-southeast-1 \
  --query "Parameters[?contains(['log_min_duration_statement','log_statement','log_lock_waits','shared_preload_libraries'], ParameterName)].{Name:ParameterName,Value:ParameterValue,Apply:ApplyType,Source:Source}"

aws rds describe-db-cluster-parameters \
  --db-cluster-parameter-group-name orders-aurora-custom \
  --region ap-southeast-1 \
  --query "Parameters[?contains(['log_min_duration_statement','log_statement','slow_query_log','long_query_time','log_output'], ParameterName)].{Name:ParameterName,Value:ParameterValue,Apply:ApplyType,Source:Source}"
~~~

Whether a parameter belongs in a **DB instance** or **DB cluster** parameter group depends on the engine and parameter; these commands return **configured parameter group values**, not guaranteed active runtime values if status is `pending-reboot`. Cross-check `PendingModifiedValues`/`DBParameterGroups.ParameterApplyStatus` or query `SELECT current_setting` / `SHOW VARIABLES` in the engine.

### 19.5. Read RDS logs via API

~~~bash
aws rds describe-db-log-files \
  --db-instance-identifier orders-postgres-prod \
  --region ap-southeast-1
~~~

For an available DB log, use **`download-db-log-file-portion`** to read a slice:

~~~bash
aws rds download-db-log-file-portion \
  --db-instance-identifier orders-postgres-prod \
  --log-file-name "error/postgresql.log" \
  --number-of-lines 100 \
  --region ap-southeast-1
~~~

**The log file name is a placeholder**; take the exact name from `describe-db-log-files`. This API reads logs whose output may contain SQL text or PII; never share raw output without authorization.

### 19.6. CloudWatch CPU and `DatabaseConnections`

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=orders-postgres-prod \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1

aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=orders-postgres-prod \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

The time window is an **illustrative UTC example for 2026-11-19**; substitute your actual incident window. CloudWatch does not sort `Datapoints` chronologically by default—sort by timestamp when analyzing.

### 19.7. CloudWatch Database Insights / PI API

Depending on engine and Database Insights mode, AWS continues using the **Performance Insights API namespace (`pi`)** to retrieve detailed DB load metrics.

~~~bash
aws pi get-resource-metrics \
  --service-type RDS \
  --identifier db-EXAMPLEDBRESOURCEID \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period-in-seconds 300 \
  --metric-queries '[{"Metric":"db.load.avg"}]' \
  --region ap-southeast-1
~~~

**The identifier is `DbiResourceId`**, not `DBInstanceIdentifier` like `orders-postgres-prod`. This command returns data only when mode, engine, permissions, and retention match. If the CLI returns `InvalidParameter`/`AccessDenied`, verify Identifier, Region, IAM, and mode rather than jumping to DB-modifying commands.

### 19.8. RDS events/failover

~~~bash
aws rds describe-events \
  --source-type db-instance \
  --source-identifier orders-postgres-prod \
  --duration 1440 \
  --region ap-southeast-1
~~~

RDS events surface reboots, maintenance, failovers, and low-storage events depending on source. They complement—not replace—CloudWatch metrics, traces, and database engine logs.

### 19.9. Read-only RDS Proxy inspection

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1

aws rds describe-db-proxy-target-groups \
  --db-proxy-name orders-db-proxy \
  --region ap-southeast-1
~~~

Inspect **`RequireTLS`, `Auth`, `VpcSubnetIds`, `VpcSecurityGroupIds`**, and target-group connection pool configs; avoid exposing secret ARNs or internal identifiers in public tickets.

### 19.10. CloudWatch Logs

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/rds/" \
  --region ap-southeast-1

aws logs describe-log-groups \
  --log-group-name-prefix "RDSOSMetrics" \
  --region ap-southeast-1

aws cloudwatch describe-alarms \
  --alarm-name-prefix "orders-db-" \
  --region ap-southeast-1
~~~

Log groups will not exist if log exports or Enhanced Monitoring have not been enabled. Select the exact log group and time range before querying SQL text, and obey data-handling policies.

## 20. Ordered runbook for investigating a slow DB

~~~mermaid
flowchart TD
    A["API latency / DB errors rise"] --> B{"Is the app waiting on the pool?"}
    B -->|"Yes"| C["Hikari active/pending/acquire; RDS Proxy BorrowLatency"]
    B -->|"No"| D{"DBLoad top wait?"}
    C --> D
    D -->|"CPU"| E["Top SQL, EXPLAIN, indexes, CPU credits"]
    D -->|"Lock"| F["Blocking sessions, xact age, transactions"]
    D -->|"I/O"| G["Read/WriteLatency, throughput, queue, cache"]
    D -->|"N/A or low"| H["Network/DNS/TLS, API tier, tracing"]
    E --> I["Optimize and load-test; compare p95/DBLoad/cost"]
    F --> I
    G --> I
    H --> I
~~~

### 20.1. Step 1: define scope and impact

Record:

- AWS **Account/Region**, DB instance/cluster/endpoint, writer vs. reader.
- App/version/deploy timestamp, request path, p95/p99, and error rate.
- UTC time window and traffic baseline.
- Recent DB failover/maintenance events.
- Hikari pool active/pending counts and connection acquisition times.
- ECS task count / Lambda concurrency / web instance count.

### 20.2. Step 2: correlate metrics

- `DatabaseConnections` climbs alongside app count → pool fan-out.
- `DBLoad` CPU climbs with high `CPUUtilization` → CPU pressure.
- `DBLoad` Lock is high with low CPU → lock waits / transaction issues.
- `ReadLatency`/queue depth rises → storage I/O.
- `FreeStorageSpace` drops → storage capacity.
- Aurora `ACUUtilization` hits 100% → max ACU may be capping scale, though still check waits.
- `AuroraReplicaLag` climbs → stale reads / replication apply issues.

### 20.3. Step 3: top SQL and execution plans

- Identify the SQL digest contributing the **largest total load/time**.
- Read slow logs and `pg_stat_statements` / Performance Schema.
- Compare rows examined vs. rows returned, predicates, sorts, join orders, and indexes.
- Never add an index based on one sample query while ignoring write overhead.
- For locks, trace blockers and transaction boundaries before changing indexes.

### 20.4. Step 4: choose safe remediation

| Root cause | Remediation |
| --- | --- |
| Hot query scanning many rows | Add appropriate index, rewrite query, paginate, eliminate N+1. |
| Lock waits from long transactions | Shorten transactions, add idempotent retries, fix migration workflows. |
| Connection storm | Reduce Hikari pool fan-out, reuse connections, add RDS Proxy, cap concurrency. |
| DB CPU-bound | Tune top CPU SQL first, then evaluate instance scaling. |
| EBS/storage latency | Inspect IOPS/throughput/storage tier and query access patterns. |
| Replica lag | Check reader load/write rate, routing consistency, and replication metrics. |
| Log flood | Lower verbosity / apply sampling while keeping essential diagnostic logs. |
| Credential/network error | Check SG/DNS/TLS/secrets/IAM; never open DB publicly. |

### 20.5. Step 5: verify after changes

Every optimization requires **before/after measurements**:

- p95/p99 API and query latency.
- Error rate, pool acquisition wait, and retries.
- DB Load (AAS) by wait type.
- CPU, memory, `Read/WriteLatency`, IOPS.
- Business correctness / transaction outcomes.
- Instance/ACU/logging/Proxy costs.
- Zero regressions under peak traffic and failover.

## 21. Real-world scenario A — HikariCP overload when ECS scales out

**Context:** 5 tasks, each with max pool 20. During a sale, ECS scales to 20 tasks; DB `max_connections` is 250.

Before scaling:

\[
5\times20=100\text{ theoretical connections}
\]

After scaling:

\[
20\times20=400\text{ theoretical connections}
\]

Symptoms:

- Hikari pending/acquire times climb.
- `DatabaseConnections` climbs and hits the ceiling.
- DB CPU may remain low because the app cannot acquire connections to send queries.
- As clients repeatedly open and fail connections, TLS/auth overhead spikes.

**Fix:** shrink per-task pools to fit real capacity, enforce concurrency/backpressure, evaluate RDS Proxy, and verify actual utilization and DB `max_connections` before editing. Never raise `max_connections` indefinitely, because DB memory is finite.

## 22. Real-world scenario B — Low CPU yet orders API times out

**Context:** `DatabaseConnections` is steady, CPU is 35%, DBLoad is `22 AAS` concentrated in `Lock`; one SQL `UPDATE orders` holds locks for a long time.

**Investigation:**

1. Database Insights highlights `Lock` as the top wait.
2. `pg_stat_activity` identifies sessions with high `transaction_age`.
3. `pg_blocking_pids` pinpoints the blocker.
4. App traces reveal a `@Transactional` method calling an external payment API before committing.
5. Shorten the transaction, move the external call outside, and implement payment idempotency and outbox if needed.

**Avoid:** upgrading instance RAM/vCPU when the bottleneck is lock hold duration.

## 23. Real-world scenario C — Aurora reader lag after month-end reporting

**Context:** Reporting queries run on an Aurora reader; read latency climbs, `ReplicaLag` increases, and customers see stale order statuses.

**Investigation:**

- Compare **`AuroraReplicaLag`** per individual reader rather than only cluster averages.
- Inspect top SQL and I/O load on the reader running reports.
- Check whether queries run full scans, huge sorts, lack indexes, or hold long transactions.
- Compare writer write workload/CPU and reader topology.
- Route flows needing read-your-writes to the writer endpoint per policy.
- Offload reporting workloads or add verified read capacity.

**Avoid:** claiming “Aurora storage is shared, so all replicas are always instantly consistent.”

## 24. Real-world scenario D — Slow-query logging slows the DB further

**Context:** Investigating slow queries, the team sets PostgreSQL **`log_statement = all`** and **`log_min_duration_statement = 0`**, exporting logs to CloudWatch. CPU and log bills jump sharply.

**Likely cause:** logging nearly every statement creates formatting/disk/export overhead, while potentially exposing SQL literals.

**Fix:** switch back to **`log_statement = none`** and appropriate duration/sampling settings under change control, monitor CPU/p95 and log volume, and set proper retention/IAM. Use verbose debug logging only short-term with an owner and rollback plan.

## 25. Real-world scenario E — RDS Proxy does not reduce connections

**Context:** Lambda connects through RDS Proxy, yet Proxy **`ClientConnections`** and **`DatabaseConnections`** are nearly equal, and `BorrowLatency` rises.

**Likely cause:** many sessions are **pinning**, or transactions hold connections open too long.

**Investigation:** check `SessionPinned`/`Borrowed`/`MaxAllowed`, query patterns, long transactions, session variables, and prepared statements for your engine. Fix application session state and transaction boundaries. Never assume the Proxy automatically multiplexes every query.

## 26. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “CPU is 40%, so the DB cannot be the bottleneck.” | Locks, I/O, connection pools, and replication can stall requests even at low CPU. |
| “`DatabaseConnections` = number of running SQL queries.” | Includes idle connections; does not equal active query count. |
| “DB Load = `CPUUtilization`.” | DB Load is **AAS** (CPU + waits); `CPUUtilization` is a percentage. |
| “`DBLoad = 10` means exactly 10 requests in that minute.” | No; it is the average number of active sessions over the time window. |
| “`FreeableMemory` near 0 always means out of RAM.” | Account for buffer/cache, swap, OS metrics, and trends. |
| “All RDS/Aurora deployments share the same `FreeStorageSpace`.” | Aurora shared volumes use different storage metrics than RDS EBS. |
| “A Multi-AZ standby always serves `SELECT`s.” | A traditional RDS Multi-AZ DB instance standby is not a read replica. |
| “The Aurora reader endpoint guarantees reading fresh writes immediately.” | Replica lag and read routing still apply. |
| “The Performance Insights console is the only tool to learn.” | Current direction is **CloudWatch Database Insights**. |
| “Leave `log_statement=all` on permanently to catch slow queries.” | Excessive logging adds overhead, cost, and data exposure risk. |
| “PostgreSQL `log_min_duration_statement` is in seconds.” | It uses **milliseconds**. |
| “MySQL `long_query_time` is in milliseconds.” | It uses **seconds**. |
| “MySQL `log_output=TABLE` works for CloudWatch slow log exports.” | CloudWatch slow log exports require **`FILE`** per RDS/Aurora docs. |
| “`EXPLAIN ANALYZE` only reads the plan and is harmless.” | It executes the query; it consumes resources and can trigger side effects. |
| “`pg_stat_statements` is a verbatim log of every call.” | It holds cumulative/normalized SQL stats, not raw execution logs. |
| “Raising Hikari `maximumPoolSize` always speeds up the app.” | Can exceed `max_connections` and worsen saturation. |
| “RDS Proxy fixes queries missing indexes.” | Proxy manages connections; it does not optimize execution plans. |
| “RDS Proxy eliminates database connections.” | It manages a connection pool; session pinning and long transactions still limit reuse. |
| “Missing CloudWatch metric = healthy DB.” | May be non-applicable, un-emitted when idle, or queried with the wrong dimension. |
| “CloudTrail automatically logs every SQL query.” | CloudTrail logs AWS API actions; SQL logging/auditing is a separate layer. |
| “Just raise ACUs whenever Aurora Serverless hits max.” | Inspect DB Load/waits/locking and workload first before deciding. |
| “1-second Enhanced Monitoring is always free.” | CloudWatch Logs ingestion/storage and operational costs increase. |

## 27. Practice exercises with answer hints

### Exercise 1 — Distinguishing DBLoad and connections

**Prompt:** RDS PostgreSQL shows `250 DatabaseConnections`, `DB Load = 3 AAS`, and `CPUUtilization = 20%`.

**Question:** Can you conclude the database is running 250 queries concurrently?

**Answer:** No. Many connections are likely idle, with only ~3 sessions active on average. Check `pg_stat_activity` by **`state`**, HikariCP active/idle counts, and memory usage. Without pool waits or connection churn, 250 open connections may not require immediate changes—compare against `max_connections` and trends.

### Exercise 2 — Low CPU, high lock waits

**Prompt:** API p95 jumps 10×, DB CPU is 25%, `DBLoadNonCPU` is `18 AAS`, and top wait is `Lock`.

**Answer:** Focus on blocking transactions; inspect `pg_stat_activity`, `pg_blocking_pids`, `transaction_age`, and Java `@Transactional` code. Do not blindly add vCPUs. Shorten transactions, add idempotent retries, and fix hot-row update patterns.

### Exercise 3 — PostgreSQL vs. MySQL thresholds

**Prompt:** You want to log queries running 750 ms or longer.

**Answer:** PostgreSQL uses **`log_min_duration_statement=750`** (milliseconds). MySQL uses **`long_query_time=0.75`** (seconds), along with **`slow_query_log=1`** and **`log_output=FILE`** when exporting to CloudWatch Logs.

### Exercise 4 — HikariCP and ECS Auto Scaling

**Prompt:** DB `max_connections = 500`, each ECS task has max pool 24, and peak scales to 30 tasks.

**Calculation:**

\[
30\times24=720
\]

**Answer:** The upper bound from app pools already exceeds `max_connections`, before counting admin/maintenance. Size pools against max tasks/concurrency, shorten queries/transactions, add RDS Proxy where appropriate, or resize DB capacity. Never raise `max_connections` to 1,000 if instance RAM cannot support it.

### Exercise 5 — Slow SQL due to high call volume

**Prompt:** Database Insights shows query A averaging 8 ms called 100,000 times/minute, and query B averaging 2,000 ms called once/minute.

**Answer:** Query A accumulates ~**800,000 ms/minute** of theoretical execution time before concurrency, compared to ~**2,000 ms/minute** for query B. A is likely the bigger throughput/cost optimization win—check ORM N+1, caching, and batching. B still needs fixing if it breaks a specific endpoint's tail-latency SLO.

### Exercise 6 — Slow query log missing from CloudWatch

**Prompt:** RDS MySQL has `slow_query_log=1`, yet no `slowquery` log stream appears.

**Answer:** Verify **`log_output=FILE`**, `long_query_time`, that queries actually exceed the threshold, **`EnabledCloudwatchLogsExports`** includes **`slowquery`**, right account/Region/log group, and IAM log-read permissions. `TABLE` logs are not exported automatically.

### Exercise 7 — Distinguishing `EXPLAIN` and `EXPLAIN ANALYZE`

**Prompt:** A DBA wants to run `EXPLAIN ANALYZE` on a production `UPDATE` currently locking many rows.

**Answer:** Stop and assess change risk; `EXPLAIN ANALYZE` **executes the `UPDATE`** with real side effects. Start with plain `EXPLAIN`, logs/Database Insights, and test on staging with representative data and an approved rolled-back transaction if technically appropriate.

### Exercise 8 — `FreeStorageSpace` on Aurora

**Prompt:** A dashboard applies a `FreeStorageSpace < 20 GiB` alarm uniformly across all RDS instances and Aurora clusters.

**Answer:** Differentiate storage models. RDS EBS instances emit **`FreeStorageSpace`**; Aurora shared cluster volumes require monitoring **`VolumeBytesUsed`** and relevant local temp/cluster capacity metrics. Never apply one alarm blindly.

### Exercise 9 — Aurora Serverless hits max ACUs

**Prompt:** Aurora Serverless max is 16 ACU, `ACUUtilization` is 100%, DB Load is high, yet 80% of session time is waiting on `Lock`.

**Answer:** Raising Max ACUs likely will not resolve lock contention. Find blockers/long transactions, fix concurrency/hot-row patterns, then load-test to see if genuine CPU/I/O shortages remain.

### Exercise 10 — RDS Proxy pinning

**Prompt:** Proxy `DatabaseConnections` nearly equals `ClientConnections` despite connection pooling being enabled.

**Answer:** Check `DatabaseConnectionsCurrentlySessionPinned`, `BorrowLatency`, transaction/session state, and engine-specific pinning rules. Session variables or long transactions are likely pinning backend connections. The Proxy cannot guarantee multiplexing for every client pattern.

### Exercise 11 — Replica lag and consistency

**Prompt:** After a user updates their shipping address, an API reading from an Aurora reader returns the old address for several hundred milliseconds.

**Answer:** Likely replication lag; check `AuroraReplicaLag` and read routing. Flows needing **read-after-write** must read from the writer or use an appropriate consistency pattern. Never assume the reader endpoint is strongly consistent.

### Exercise 12 — Identifying metrics needing alarms

**Prompt:** A database has normal CPU, yet **`FreeStorageSpace`** drops steadily by 3 GiB/day with 18 GiB left.

**Calculation:** 18 / 3 ≈ **6 days** assuming steady growth.

**Answer:** Beyond static thresholds, configure a **capacity forecast alarm** and execute a storage expansion or cleanup plan for the storage type—never wait until disk fills. Check storage autoscaling, backup/retention, and large objects/log tables.

### Exercise 13 — Logging and PII

**Prompt:** A team debugging a customer-email `SELECT` wants to enable verbose SQL logging across the entire database.

**Answer:** Prefer Database Insights SQL digests, parameterized app logs, and time-boxed thresholds/sampling. Enforce access controls, redaction, and CloudWatch retention/KMS; never enable `log_statement=all` long-term because SQL text can expose PII and add heavy overhead.

### Exercise 14 — Failover breaks connections

**Prompt:** An Aurora writer failover causes Java API errors for tens of seconds despite multi-AZ deployment.

**Answer:** HA does not keep existing TCP connections alive. Handle stale JDBC connections, DNS endpoint refresh, bounded retries with backoff/idempotency, RDS Proxy where appropriate, transaction failures, and app readiness. Monitor RDS events/role shifts and run controlled failover drills regularly.

### Exercise 15 — Explaining a Cost Explorer spike

**Prompt:** The database instance class did not change, yet the AWS bill jumped after enabling logs/Advanced insights and adding RDS Proxy.

**Answer:** Costs likely come from **Database Insights mode/retention, CloudWatch Logs ingestion/storage/queries, Enhanced Monitoring intervals, and RDS Proxy**. Break down Cost Explorer/CUR by Service and Usage Type aligned with change timestamps and metrics—never assume instance pricing changed without data.

## 28. Self-check questions

**Q1.** In what unit is DB Load measured?  
**Answer:** **Average Active Sessions (AAS)**.

**Q2.** True or false: `DatabaseConnections` equals `DBLoad`?  
**Answer:** False; connections include idle sockets, while DB Load measures active/waiting sessions.

**Q3.** What does `DBLoadCPU` represent?  
**Answer:** AAS consuming CPU; not the same unit as `CPUUtilization` %.

**Q4.** When CPU is low yet DB Load `Lock` is high, what should you do?  
**Answer:** Identify blockers and long-running transactions.

**Q5.** What is the standard CloudWatch metric namespace for RDS/Aurora?  
**Answer:** **`AWS/RDS`**.

**Q6.** Where does Enhanced Monitoring send OS metrics?  
**Answer:** **CloudWatch Logs**, typically in log group **`RDSOSMetrics`**.

**Q7.** Can Enhanced Monitoring sample every 1 second?  
**Answer:** Yes, at supported granularities, though log volume, cost, and display limits apply.

**Q8.** What is the main difference between CloudWatch Database Insights Standard and Advanced?  
**Answer:** Advanced adds deeper SQL/waits/plans/locks analysis and fleet/per-query views depending on engine, with different retention and pricing.

**Q9.** Why shouldn't you rely solely on `Average CPUUtilization` to find root cause?  
**Answer:** A database can be bottlenecked on locks, I/O, connections, or replica lag even when CPU is low.

**Q10.** What unit does RDS for PostgreSQL `log_min_duration_statement` use?  
**Answer:** **Milliseconds**.

**Q11.** What unit does MySQL `long_query_time` use?  
**Answer:** **Seconds**, accepting fractional values depending on log destination/engine.

**Q12.** Which `log_output` is needed for MySQL slow logs to appear in CloudWatch?  
**Answer:** **`FILE`**, alongside enabling `slow_query_log` and log export.

**Q13.** What is `pg_stat_activity` used for?  
**Answer:** Inspecting sessions, states, wait events, and query/transaction ages.

**Q14.** What does `pg_stat_statements` show?  
**Answer:** Cumulative statistics by normalized SQL, call counts, and execution times.

**Q15.** Does `EXPLAIN ANALYZE` execute the SQL statement?  
**Answer:** Yes; assess resource impact and side effects before running.

**Q16.** How does MySQL `SHOW PROCESSLIST` help?  
**Answer:** Displays active/waiting sessions/threads and their current states.

**Q17.** What causes Hikari `pending` connections to rise?  
**Answer:** Pool exhaustion from slow SQL, long transactions, leaks, traffic bursts, or backend errors.

**Q18.** 10 ECS tasks, each with max pool 30 → what is the upper bound?  
**Answer:** **300 DB connections**, excluding other apps.

**Q19.** Does RDS Proxy automatically fix queries missing indexes?  
**Answer:** No; it pools/manages connections and failover, not SQL query plans.

**Q20.** How does RDS Proxy session pinning affect multiplexing?  
**Answer:** It reduces multiplexing, often requiring more backend connections.

**Q21.** What unit does RDS Proxy `DatabaseConnectionsBorrowLatency` use?  
**Answer:** **Microseconds** per metric definition.

**Q22.** Is a traditional RDS Multi-AZ standby a read replica?  
**Answer:** No. A Multi-AZ DB instance standby serves HA, not read scaling.

**Q23.** What is `AuroraReplicaLag` used to evaluate?  
**Answer:** Replica lag, which affects read freshness.

**Q24.** Which metric tracks current ACU capacity in Aurora Serverless?  
**Answer:** **`ServerlessDatabaseCapacity`**, paired with **`ACUUtilization`**.

**Q25.** Should you copy an RDS EBS `FreeStorageSpace` alarm to every Aurora cluster?  
**Answer:** No, because Aurora shared storage uses different metrics.

**Q26.** When a query runs hundreds of thousands of times, which metrics matter most?  
**Answer:** **Calls and total execution time**, not just maximum single-query duration.

**Q27.** Does CloudTrail log every SQL `SELECT`?  
**Answer:** No; CloudTrail primarily logs AWS API activities, while SQL logging/auditing is a separate layer.

**Q28.** Why can verbose logging slow down a database?  
**Answer:** Increases CPU/I/O for log formatting/exporting and inflates CloudWatch Logs costs.

**Q29.** When RDS Proxy `BorrowLatency` spikes, what should you inspect?  
**Answer:** Backend pool utilization/headroom, session pinning, transactions, and max DB connections.

**Q30.** Why verify business KPIs after tuning a query?  
**Answer:** Speed gains must never trade off correctness, transaction consistency, or availability.

## 29. Summary and production checklist

A healthy RDS/Aurora system cannot be proven by **`CPUUtilization = 30%`** alone. Connect:

- **Application:** p95/p99, HTTP errors, transaction outcomes, HikariCP pool acquisition.
- **Database Insights:** DB Load/AAS, top SQL/waits, blocking, and plans per supported engine/mode.
- **Infrastructure:** CPU, `FreeableMemory`, I/O latency/queue/throughput, storage headroom.
- **Connections:** `DatabaseConnections`, engine `max_connections`, RDS Proxy client/backend pools and pinning.
- **Aurora:** writer/reader topology, replica lag, Aurora Serverless ACUs, and dedicated storage metrics.
- **Logs:** PostgreSQL slow logs / MySQL `slowquery` with thresholds, sampling, privacy, and retention.
- **Recovery:** RDS events, failover/reconnects, backups/restores, RPO/RTO, and regression tests.
- **Cost:** DB class/ACUs/I/O, Database Insights, Enhanced Monitoring, Logs, and Proxy.

### Operational readiness checklist

1. Confirm exact **account, Region, engine, DB instance/cluster, and writer/reader roles**.
2. Maintain CloudWatch **`AWS/RDS`** dashboards and Database Insights **`DBLoad`/waits** views.
3. Instrument **Hikari metrics, traces, transaction latencies, and business SLOs** in the app.
4. Compute **pool capacity = app instances × `maximumPoolSize`** plus other services and headroom.
5. Configure **slow-query logging** with sensible thresholds/sampling—never log all SQL indefinitely.
6. Protect SQL text/credentials in CloudWatch Logs with retention and IAM/KMS controls.
7. Periodically review **top SQL by total time, avg/p95, waits, rows examined, and execution plans**.
8. Monitor RDS Proxy metrics and pinning if using Proxy.
9. Track **storage/I/O/replica lag/ACUs** tailored to RDS, Aurora, and engine specifics.
10. Assign alarms owners, severities, runbooks, and proper missing-data handling.
11. Test failover/reconnects and database migrations; never rely on a single connection living forever.
12. Back every optimization with before/after benchmarks covering performance, business correctness, and cost.
13. Prevent read-only metric viewers from holding DB reboot/modify permissions or broad customer data access.
14. Review Cost Explorer/CUR to govern Database Insights, Enhanced Monitoring, logging, and RDS Proxy spend.

**Conclusion:** Detecting a “slow database” is only the starting line. To resolve it effectively, trace from **user symptoms** to **DB Load/wait classes**, pinpoint the **offending SQL, transaction, connection pool, or resource**, and deploy changes only after measuring against a representative workload. That is how you operate RDS/Aurora safely, resiliently, and without runaway costs.

### Official AWS documentation

- [Amazon RDS metrics reference](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html) — CPU, `DatabaseConnections`, storage, IOPS, and latency.
- [Monitoring RDS with CloudWatch](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html) — standard metrics monitoring.
- [CloudWatch Database Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Database-Insights.html) — Standard/Advanced, DB Load, and observability tooling.
- [Database Insights for RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DatabaseInsights.html) — RDS metrics and query analysis.
- [Database Insights slow SQL configuration — RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DatabaseInsights.SlowSQL.html) — PostgreSQL/MySQL slow SQL settings.
- [Database Insights slow SQL configuration — Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_DatabaseInsights.SlowSQL.html) — parameter groups for Aurora.
- [Enhanced Monitoring OS metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.html) — OS processes, sampling, CloudWatch Logs details.
- [Enhanced Monitoring OS metric access](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.CloudWatchLogs.html) — `RDSOSMetrics` logs.
- [RDS PostgreSQL database logs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_LogAccess.Concepts.PostgreSQL.html) — CloudWatch export, SQL query logging.
- [Aurora PostgreSQL query logging](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_LogAccess.Concepts.PostgreSQL.Query_Logging.html) — parameters and logging risks.
- [RDS MySQL slow query logs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_LogAccess.MySQL.LogFileSize.html) — `long_query_time`, `FILE`/`TABLE`, and export.
- [Aurora MySQL logging](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_LogAccess.MySQL.LogFileSize.html) — slow query logging and defaults.
- [RDS Proxy metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.monitoring.html) — `BorrowLatency`, pinning, client/backend connections.
- [RDS Proxy connection considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connections.html) — connection headroom, `MaxConnectionsPercent`.
- [Aurora CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html) — `AuroraReplicaLag`, `ServerlessDatabaseCapacity`, `ACUUtilization`.
- [Aurora Serverless v2 monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-administration.html) — capacity metrics and autoscaling.
- [AWS Database Blog — Performance impact of excessive logging in Aurora PostgreSQL](https://aws.amazon.com/blogs/database/performance-impact-of-excessive-logging-in-amazon-aurora-postgresql/) — logging impact study published 2026-11-19.
