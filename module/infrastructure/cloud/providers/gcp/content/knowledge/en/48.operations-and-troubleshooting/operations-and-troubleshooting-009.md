# Diagnosing Cloud SQL Connection Exhaustion and Slow Queries

## 1. Lesson Objectives and Scope

A Java/Spring Boot application running on Cloud Run, GKE, or Compute Engine can connect cleanly to Google Cloud SQL under light load, yet suddenly return HTTP 500/503s when traffic surges. Application logs sometimes report `Connection is not available, request timed out`; in other cases, the database returns `too many connections`. Other times, all connections remain active, yet a single query slows from 20 ms to 8 seconds and monopolizes every connection in the pool.

These three symptoms are interconnected yet **do not share the same root cause**:

1. **Database connection exhaustion:** the server has reached or neared its connection/session limit and rejects new connections.
2. **Application pool exhaustion:** every connection in HikariCP is checked out or unreturned; requests queue inside the application even though the database may still have free slots.
3. **Slow queries / long transactions:** SQL execution, locks, I/O, CPU, or network stalls hold connections open longer. As a result, pools fill up and eventually look like "out of connections."

This guide is a **hands-on diagnostic runbook** for the `CLOUD_PROVIDERS_GCP` module, connecting Cloud SQL, IAM, VPC/private networking, Cloud Run/GKE autoscaling, Java connection pools, observability, reliability, and cost.

After this lesson, learners will be able to:

- Isolate whether a fault lives in networking/auth, the Cloud SQL server, the Java pool, or the query itself.
- Collect time-correlated incident evidence using Cloud Monitoring, System Insights, Query Insights, and database engine views.
- Execute **read-only** diagnostic queries for PostgreSQL, MySQL, or SQL Server.
- Calculate connection budgets across multiple replicas, revisions, and background jobs.
- Identify connection leaks, long transactions, blocking locks, bad query plans, and resource saturation.
- Select short-term load-shedding mitigations with impact assessment while avoiding indiscriminate restarts or session kills.
- Improve Spring Boot/HikariCP settings, SQL/indexes, retries, and concurrency controls.
- Write an RCA report and rehearse similar scenarios in an authorized environment.

**Safety scope:** the SQL statements below are strictly read-only status checks—no session-kill commands, flag changes, instance resizes, or data deletions. Any production modification requires formal approval and a rollback plan. Never run commands against an instance outside your authorized scope.

## 2. Quick Glance: Which Symptom Points to Which Investigation Path?

| Observed Symptom | Initial Hypothesis | What to Check |
|---|---|---|
| PostgreSQL reports `remaining connection slots are reserved` or SQLSTATE `53300` | Server near `max_connections` | Cloud SQL connections metric, `pg_stat_activity`, reserved slots |
| MySQL reports `Too many connections` (error 1040) | Server out of connections | `Threads_connected`, `max_connections`, processlist |
| Hikari reports `Connection is not available, request timed out` | Pool occupied, leaked, or slow DB connects | Hikari active/idle/pending, query/transaction duration |
| Cloud Run fails only during scale-out | Aggregate pools exceed budget or cold-start surge | Max instances, pool size, active revisions/jobs |
| One endpoint sees rising p99 latency; DB CPU is low | Locks, N+1 queries, network, or pool wait | Query Insights, wait events, app tracing |
| Query latency rises alongside 90–100% CPU | Insufficient CPU or heavy query plans | System Insights, top queries, `EXPLAIN` |
| Query latency rises alongside high I/O wait | Heavy disk reads/writes, missing indexes, storage bottleneck | Disk IOPS/throughput, waits, query plans |
| Many `idle in transaction` sessions | Uncommitted/unrolled-back transactions holding connections | `pg_stat_activity`, Java `@Transactional`, call graph |
| Timeouts before reaching the DB | VPC, DNS, firewall, IAM, connector/proxy, TLS | Cloud SQL connectivity logs, connector config |
| Latency jumps right after deploy | Changed SQL, migration, pool, or concurrency | Deploy timeline, query fingerprints, config diff |

Never jump to conclusions from a single log line. A Hikari error reports **pool checkout wait time**, which does not by itself prove the server hit its connection ceiling. A pool of 10 active connections held by 10 slow queries will time out the 11th request even when the database still has plenty of spare slots.

## 3. Minutes 0–5 Runbook: Isolating Blast Radius

### 3.1. Identify the Incident Source

Answer in order:

1. What are the project, Cloud SQL instance, region, database engine/version, and environment?
2. When (UTC) did the incident start, and did it coincide with a deploy, migration, traffic spike, or IAM/network change?
3. Is only one service or endpoint failing, or all workloads sharing the database?
4. Primary instance or read replica? Writes only or reads as well?
5. How do error rates and latency compare to SLOs and user impact?
6. Are emergency contacts, data owners, or change freezes active?

Do not spin up or restart multiple services simultaneously before understanding the state—doing so can unleash a connection storm against Cloud SQL.

### 3.2. Collect Minimum Evidence

- Screenshots or exports of **Cloud SQL connections**, CPU, memory, and disk utilization/I/O metrics.
- App metrics: request rate, p95/p99 latency, 5xx rate, Hikari active/idle/pending/timeouts.
- Cloud Run instances/concurrency or GKE pods/rollouts and job states.
- Representative error logs **scrubbed of credentials, PII, and SQL literals**.
- Timestamps of deployments, config changes, schema migrations, backups, and failovers.
- Query Insights snapshots or engine-specific session stats where authorized.

Escalate severity if payments/transactions fail continuously, administrative database logins fail, or data inconsistency risks emerge.

### 3.3. Read Cloud SQL Metadata

Run only against authorized projects/instances:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export INSTANCE="YOUR_CLOUD_SQL_INSTANCE"

gcloud auth list
gcloud config get-value project

gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,databaseVersion,region,state,settings.tier,settings.databaseFlags,settings.ipConfiguration)"
~~~

This command **does not** connect to the SQL engine itself; it reads metadata from the Cloud SQL Admin API. Read permissions on the Cloud SQL instance are required; permission denial does not mean the instance does not exist.

### 3.4. Quick Decision Map

~~~mermaid
flowchart TD
    A[App hits DB errors or high latency] --> B{Can requests open TCP/auth to DB?}
    B -- No --> C[Check VPC / DNS / IAM / connector / TLS]
    B -- Yes --> D{Is database near connection limit?}
    D -- Yes --> E[Analyze session sources, replica count, and max_connections]
    D -- No --> F{Are both Hikari pending and active high?}
    F -- Yes --> G[Check leaks, long transactions, slow queries, pool sizing]
    F -- No --> H{Are query latency and waits high?}
    H -- Yes --> I[Query Insights, locks, CPU/IO, EXPLAIN]
    H -- No --> J[Check network latency, thread pools, app errors]
    E --> K[Mitigate with minimal blast radius]
    G --> K
    I --> K
    C --> K
    K --> L[Verify SLOs, DB headroom, RCA]
~~~

## 4. Understanding the Connection Path

Logical flow when Spring Boot uses Cloud SQL:

~~~mermaid
flowchart LR
    HTTP[HTTP/gRPC request] --> APP[Java/Spring Boot handler]
    APP --> POOL[HikariCP pool]
    POOL --> CONN[Cloud SQL Java Connector / Auth Proxy / direct TCP]
    CONN --> DB[(Cloud SQL PostgreSQL/MySQL/SQL Server)]
    DB --> LOCK[Locks + transactions]
    DB --> CPU[CPU, memory, I/O]
    APP -. traces .-> APM[Application telemetry]
    POOL -. metrics .-> MON[Monitoring]
    DB -. engine stats .-> INSIGHTS[System/Query Insights]
~~~

A request can stall at **any** layer:

- Waiting to check out a connection from Hikari.
- Waiting for the connector/proxy to open a connection or refresh credentials/certificates.
- Waiting for TCP/TLS handshake and database authentication.
- Waiting on CPU, I/O, or locks inside the engine.
- Waiting to transfer large result sets over the network or parse results in the app.

**Cloud SQL Auth Proxy and the Cloud SQL Java Connector secure and establish connectivity to Cloud SQL; they do not automatically provide application connection pooling.** Pooling must be configured in HikariCP or a compatible dedicated connection pooler.

### 4.1. Connections, Sessions, and Transactions Differ

- **Connection:** a link from client to DB, typically backed by a server session consuming resources.
- **Session:** SQL engine connection state, which may hold session variables, prepared statements, or temp objects.
- **Transaction:** a unit of work committed or rolled back; may hold locks for part of a session's lifetime.
- **Pool checkout:** a request borrows a connection from the pool, uses it, and returns it; never hold a connection across unnecessary outbound HTTP calls.

An `idle` session may simply be a pool waiting for requests, whereas `idle in transaction` demands investigation because a transaction remains open.

## 5. Calculating a Connection Budget Instead of Guessing Pool Size

As an application scales out, potential connections multiply by **instance/pod count** and pools per process.

### 5.1. Approximate Formula

~~~text
Potential peak DB sessions ≈
  Σ (max instances of service i × max pool size per instance i)
+ background jobs / migrations / batch clients
+ admin / monitoring / other services
+ overlapping revisions / deployment surge
~~~

Remember multiple Java `DataSource`s in one process or per-tenant pools. Some frameworks also open out-of-pool connections for migrations or health checks; account for actual behavior.

### 5.2. Quantitative Example

Suppose a PostgreSQL instance has a verified `max_connections` of **300**. Operations reserves **60** slots for admin, maintenance, monitoring, other services, and anomalies. A batch job may need **40** connections. Remaining budget for the web service:

~~~text
300 - 60 - 40 = 200 connections
~~~

If Cloud Run caps at **20** instances with Hikari `maximumPoolSize=8`:

~~~text
20 × 8 = 160 connections
Projected total = 160 + 60 + 40 = 260
Planned headroom = 300 - 260 = 40
~~~

However, if a rollout leaves two revisions scaling simultaneously, or autoscaling bumps 20 to 40 instances:

~~~text
40 × 8 = 320 connections for the web service alone
~~~

Thus `maximumPoolSize=8` fits one scaling cap yet breaks when max instances change. Budget across **the entire caller fleet**, including staging if it ever shares a database (which should be avoided), cron/batch jobs, GKE Pods, and sibling services.

The figure `300` is a hypothetical calculation example, **not a universal Cloud SQL default**. PostgreSQL, MySQL, and SQL Server have distinct limits and behaviors by tier, engine, and configuration.

### 5.3. Cloud Run Connection Limits: Read the Exact Scope

For Cloud Run's **built-in Cloud SQL connection**, Google Cloud documents a limit of **100 connections per container instance per Cloud SQL database**. This specific limit **does not apply identically** to every other connection method such as direct IP, sidecar Cloud SQL Auth Proxy, or language connectors.

Even without a built-in limit on certain paths, the Cloud SQL server still enforces `max_connections` and resource limits; opening more connections does not mean the DB can serve them well. Never set Hikari pool size to 100 merely because documentation mentions a 100-connection limit.

## 6. Cloud Monitoring and System Insights

### 6.1. Start with a Timeline

Open **Cloud SQL instance → System Insights** or Cloud Monitoring Metrics Explorer. Align the timezone and time window with application errors. Compare before/after deployments and traffic peaks.

Key metric groups to inspect:

| Group | Interpretation |
|---|---|
| Network/connections and peak connections | Is server connection count approaching its limit? |
| CPU utilization | Heavy SQL processing/sorting/aggregation or undersized tier |
| Memory utilization / pressure | Small cache, memory pressure, query memory spikes |
| Disk utilization, IOPS/throughput | Table scans, temp files, storage capacity limits |
| Query latency, database load | Queries slowed by CPU, I/O, or locks |
| Errors and restarts/failovers | Infrastructure, config, or overload incidents |
| Transactions/QPS and replication lag | Actual workload volume and replica impact |

A common connection-count metric in Cloud Monitoring is `cloudsql.googleapis.com/database/network/connections`; verify exact metric names and labels in Metrics Explorer for your engine and version.

**Note:** when an instance is severely overloaded, some metrics can lag or show gaps; never interpret missing datapoints as a healthy or idle database.

### 6.2. Correlating Application Metrics

In Spring Boot with Actuator + Micrometer instrumentation, Hikari metrics—active, idle, pending, and timeouts—help distinguish:

- High DB connection count + many app pools open: likely aggregate budget overflow.
- Low DB connection count + rising Hikari pending: a single local pool is saturated, likely from leaks or long queries.
- High DB connection count + low CPU + many idle sessions: pools are holding more idle connections than needed.
- High DB CPU/I/O/locks + rising Hikari active/pending: slow queries are holding pooled connections too long.

Metric names/Prometheus series vary by exporter and version, so confirm they are exposed before writing alerts.

### 6.3. Cloud SQL and Cloud Run Logs

Example of reading recent Cloud SQL logs:

~~~bash
gcloud logging read \
  'resource.type="cloudsql_database" AND severity>=WARNING' \
  --project="$PROJECT_ID" \
  --limit=100
~~~

For Cloud Run, query logs for the affected revision by service name/labels and time window. Never paste query texts containing PII, usernames, passwords, or connection strings with secrets into unprotected tickets.

## 7. PostgreSQL: Diagnosing Connection Exhaustion

Run the queries below in `psql` using a database account authorized to view stats. Standard accounts may see limited details for other sessions; ask a DBA to execute under approval if permissions are lacking.

### 7.1. Limits and Current Connection Counts

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;

SELECT count(*) AS all_connections,
       count(*) FILTER (WHERE state = 'active') AS active,
       count(*) FILTER (WHERE state = 'idle') AS idle,
       count(*) FILTER (WHERE state = 'idle in transaction')
         AS idle_in_transaction
FROM pg_stat_activity;
~~~

**Do not treat `max_connections - count(*)` as guaranteed slots for normal users.** PostgreSQL reserves slots for special/administrative roles, and additional reserved slot settings may apply depending on version and Cloud SQL configuration.

### 7.2. Group by Database, User, App, and State

~~~sql
SELECT datname,
       usename,
       application_name,
       state,
       count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC
LIMIT 30;
~~~

`application_name` helps separate `orders-api`, `billing-worker`, and `migration-job`. Set `application_name` in your JDBC configuration to speed up RCA.

### 7.3. Find Long Transactions and Waiting Sessions

~~~sql
SELECT pid,
       usename,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST
LIMIT 30;
~~~

Distinguish `query_age` from how long a transaction has been open, and `active` from `idle in transaction`. When `query_start` is old while `state` is `idle`, it reflects the last executed query, not a query still running.

Avoid dumping the full `query` column containing SQL literals/PII unless authorized; the queries above intentionally omit raw SQL.

### 7.4. Find Blocking Sessions

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE array_length(pg_blocking_pids(pid), 1) > 0
ORDER BY transaction_age DESC NULLS LAST
LIMIT 30;
~~~

If many sessions are waiting on a single blocker, clearing the lock source can free many Hikari connections at once. Never run `pg_terminate_backend` just because a session is old: it could be a migration, import, backup, or large transaction about to commit.

### 7.5. PostgreSQL and `pg_stat_statements`

When supported and enabled, `pg_stat_statements` aggregates execution counts, total time, mean time, row counts, and I/O for normalized queries. Verify configuration, version, and permissions before querying.

Depending on version:

~~~sql
SELECT queryid,
       calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This query is valid only when the extension is enabled and column names match your PostgreSQL version. Never enable extensions or alter database flags mid-P0 without impact assessment and approval.

## 8. MySQL: Diagnosing Connections and Slow Queries

Run these queries using a MySQL account with performance-status viewing privileges. `SHOW FULL PROCESSLIST` can expose sensitive query text; run only in controlled observability environments.

### 8.1. Connection Capacity and Activity

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';

SHOW FULL PROCESSLIST;
~~~

- `Threads_connected`: total current client connections.
- `Threads_running`: threads actively executing (not sleeping).
- `Max_used_connections`: peak since counters started.
- `Sleep`: idle threads; many sleeping threads from app pods often signal oversized pools.

If MySQL returns error **1040 Too many connections**, inspect connection sources, connect rates, and database flags rather than immediately bumping `max_connections`.

### 8.2. Group by User/Client

On supported MySQL versions with appropriate permissions:

~~~sql
SELECT USER, HOST, COUNT(*) AS sessions
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST
ORDER BY sessions DESC
LIMIT 30;
~~~

`HOST` may reflect NAT or a connector/proxy, so it does not always map 1:1 to a Cloud Run instance. Correlate using distinct database users, connection attributes/telemetry, and deploy timelines.

### 8.3. Performance Schema Query Digests

If `performance_schema` is enabled and permissions allow:

~~~sql
SELECT DIGEST,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 2)
         AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 2)
         AS avg_milliseconds,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Performance Schema timers are usually measured in picoseconds; verify units and version before comparing figures. Use digests rather than pasting raw SQL literals into tickets. A query executed frequently at moderate average latency can still dominate total database load.

### 8.4. Slow Query Log

Cloud SQL MySQL can record slow queries when configured with `slow_query_log=on`, `log_output=FILE`, and an appropriate `long_query_time`. Logs flow into Cloud Logging and incur storage/logging costs.

Never leave the general log on or set `long_query_time=0` during a production overload: doing so drives up I/O, storage, and billing. Before changing database flags, verify whether the change triggers a restart, SLA impact, or maintenance event.

## 9. SQL Server: Active Requests and Wait Types

Cloud SQL for SQL Server exposes dynamic management views (DMVs). Permissions such as `VIEW SERVER STATE` or edition/version equivalents may be needed to view other sessions.

### 9.1. Count User Sessions

~~~sql
SELECT COUNT(*) AS user_sessions
FROM sys.dm_exec_sessions
WHERE is_user_process = 1;
~~~

### 9.2. Inspect Running Requests

~~~sql
SELECT TOP (30)
       r.session_id,
       r.status,
       r.command,
       r.cpu_time,
       r.total_elapsed_time,
       r.wait_type,
       r.wait_time,
       r.blocking_session_id
FROM sys.dm_exec_requests AS r
WHERE r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
~~~

Elapsed and wait times are typically in milliseconds. Never run `KILL` solely because a session has run long; rolling back a large transaction can keep holding resources for a long time.

### 9.3. Classifying Waits

Common wait groups:

- `LCK_M_*`: lock waits; inspect the blocking transaction.
- `PAGEIOLATCH_*`: waiting to read pages from storage; often points to I/O or cache pressure.
- `WRITELOG`: waiting on log flushes; relates to transaction/log throughput.
- `SOS_SCHEDULER_YIELD` and CPU-heavy queries: often indicate CPU pressure and query plans.
- Network-related waits: can stem from clients reading rows slowly, not always server CPU starvation.

A wait type is an **investigation hint**, not sole proof of causality. Query Insights and active queries in Cloud SQL for SQL Server add analysis capabilities, though feature availability and session-termination permissions can vary by edition (especially Enterprise Plus).

## 10. Distinguishing Database Exhaustion from HikariCP Exhaustion

### 10.1. Hikari Pool Has Three Key States

- **Active:** connections currently checked out.
- **Idle:** connections waiting in the pool.
- **Pending:** threads waiting for a connection.

Example:

~~~text
Cloud SQL sessions: 110 / max_connections 300
Hikari maximumPoolSize: 10
Hikari active: 10
Hikari idle: 0
Hikari pending: 45
~~~

The database is **not** out of slots, yet this service **has exhausted its local pool**. Causes may be 10 slow transactions, leaked connections, connections held during outbound HTTP calls, or a pool too small for real concurrency.

Conversely:

~~~text
Cloud SQL sessions: ~298 / max_connections 300
Hikari active: 4, idle: 6, pending: 0 (per instance)
Cloud Run instances: 40
~~~

Here, too many **small pools across many instances** each hold idle connections. Increasing `maximumPoolSize` now will make things worse.

### 10.2. Common Java Connection Leaks

Typical causes:

- Unclosed `Connection`, `Statement`, or `ResultSet` objects.
- `@Transactional` wrapping HTTP/gRPC calls to external services.
- Streaming queries/results held across long requests or left unclosed.
- Dead threads or exception paths skipping cleanup.
- ORM/Open Session in View holding sessions open unnecessarily.
- Creating duplicate `DataSource` instances when instantiating beans/clients per request.
- Background tasks consuming the pool while dashboards watch only HTTP traffic.

Use `try-with-resources` for direct JDBC access:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(String orderId) throws SQLException {
        String sql =
            "SELECT 1 FROM orders WHERE order_id = ? LIMIT 1";
        try (Connection c = dataSource.getConnection();
             PreparedStatement statement =
                 c.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setQueryTimeout(2);
            try (ResultSet rs = statement.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

`LIMIT 1` fits PostgreSQL/MySQL, **not SQL Server** (which uses `TOP (1)`). This snippet demonstrates returning connections to the pool even on exceptions, not a universal cross-engine query template.

### 10.3. Transactions Should Never Wrap External HTTP Calls

Avoid:

~~~java
@Transactional
public void processOrder(String id) {
    repository.updateStatus(id, "PROCESSING");
    paymentApi.callRemoteService(id); // can time out slowly
    repository.updateStatus(id, "DONE");
}
~~~

Holding a transaction open across a remote call pins DB connections and locks. Replace it with shorter transaction boundaries and idempotency/outbox/saga patterns where distributed reliability is needed. Never split a transaction blindly if business invariants require consistency without designing a compensating mechanism.

## 11. HikariCP Configuration for Spring Boot

**Illustrative example—must be sized from a measured connection budget**:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db
      maximum-pool-size: 8
      minimum-idle: 0
      connection-timeout: 10000
      validation-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
  jpa:
    open-in-view: false
~~~

Meaning:

- `maximum-pool-size`: caps connections **per Hikari pool in one process**, not across the whole deployment.
- `minimum-idle: 0`: avoids holding idle connections in widely scaled environments; trades off cold checkout latency.
- `connection-timeout`: max wait to borrow a connection from the pool, not the SQL query timeout.
- `validation-timeout`: timeout for validating a connection.
- `idle-timeout`: closes idle connections per Hikari policy when applicable.
- `max-lifetime`: recycles connections periodically; usually set shorter than server/network idle timeouts to avoid stale connections.
- `open-in-view: false`: prevents holding persistence contexts beyond transactions during response rendering.

HikariCP `connectionTimeout` is in **milliseconds**. Do not confuse it with PostgreSQL `statement_timeout`, MySQL statement execution limits, or HTTP request timeouts.

### 11.1. Other Settings Worth Checking

- Connector/driver connect timeout, socket/read timeout, and TLS settings.
- Hikari `keepaliveTime`, `maxLifetime`, and server idle timeouts to prevent stale connections.
- `spring.datasource.hikari.leak-detection-threshold` should only be enabled temporarily with a sensible threshold; legitimate slow transactions can trigger false positives and log sensitive stack traces.
- JDBC `application_name` (PostgreSQL) or supported connection attributes to identify callers.
- Cloud SQL Java Connector refresh strategy for serverless; some guidance recommends `cloudSqlRefreshStrategy=lazy` so background refresh threads are not throttled by CPU allocation.
- Spring `@Transactional(readOnly = true)` is an optimization/intent hint; **it does not guarantee** the database rejects all writes.

Never flip 10 flags simultaneously and then hunt for the cause. Change one setting, record a baseline, and watch metrics.

## 12. Cloud Run/GKE Autoscaling Creating Connection Storms

A serverless deployment can run smoothly at 2 containers yet overwhelm database limits when scaling to 50 containers.

### 12.1. Cloud Run

Factors to check:

1. Service- and revision-level `max instances`.
2. `min instances` holding warm pools open.
3. Request concurrency per instance.
4. Cold starts initializing Hikari pools and connectors concurrently.
5. Two revisions serving traffic concurrently during rollouts.
6. Cloud Run Jobs or batch workers sharing the same DB.
7. Request-based CPU throttling delaying pool maintenance on idle containers.
8. Cloud SQL built-in connection limits versus Java connector, sidecar, or direct IP.

Never lower `maximumPoolSize` without checking concurrency: if an instance handles 80 concurrent requests with a pool of 5 connections, requests queue heavily. Conversely, raising pool size per instance raises peak aggregate DB connections.

Balance max instances, concurrency, request queuing policies, pooled connections, background job autoscaling, and admission control against p95/p99 latency, transaction duration, and database capacity.

### 12.2. GKE

On GKE, total pools ≈ replicas × pools per Pod. Check HPA scale-up, rolling updates with `maxSurge`, CronJobs, and worker concurrency. Simultaneous Pod restarts can trigger a reconnect burst. Node autoscaling does not create sessions directly, yet enables more Pods to schedule.

Design sensible readiness/liveness probes: health checks that continuously open fresh JDBC connections while the DB is already struggling make matters worse. Readiness can reflect serving capability without executing heavy transactions.

## 13. Query Insights: Finding SQL Driving Heavy Database Load

Cloud SQL **Query Insights** surfaces top queries over time, database load, latency, CPU/I/O/lock waits, and—in certain editions—query plans and active queries.

Effective workflow:

1. Select the instance and incident time window, comparing against a healthy baseline.
2. Check total database load against CPU capacity.
3. Filter by database, user, client address, or application tag where available.
4. Pick query fingerprints/digests with elevated **total time** or p95/p99 latency.
5. Separate high-frequency queries (fast individually, huge aggregate load) from rare, very slow queries.
6. Inspect the wait breakdown: CPU, I/O, or locks.
7. Inspect sample/historical query plans if supported.
8. Correlate with commits, index migrations, data growth, and application traces.

Note: Query Insights defaults to aggregating **completed queries**; to see hung queries that have not finished yet, switch to **Active queries** or engine views. Advanced features and retention depend on Enterprise/Enterprise Plus edition, engine, and version.

### 13.1. When Not to Enable Extra Telemetry Mid-Incident

Enabling or modifying Query Insights or database flags can impact instance performance, incur costs, store SQL text, and in some cases pause operations or restart the instance. If not already enabled, rely on existing metrics and SQL views first. Obtain change-management approval before changing production observability settings.

### 13.2. Permissions and Sensitive Data Notes

Raw SQL may contain literals: emails, tokens, PII, or order details. Prefer normalized query fingerprints; restrict viewing permissions, retention, and log exports. Never paste raw SQL text or parameters into public tickets.

## 14. Reading Query Plans Without Risking Production

### 14.1. PostgreSQL

~~~sql
EXPLAIN
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

`123` is a placeholder value; use bind parameters in application code. `EXPLAIN` without `ANALYZE` prints the estimated plan, useful for inspecting scans, joins, sorts, and index selection.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**WARNING:** `EXPLAIN ANALYZE` **actually executes the query**. Never run it unchecked on production—especially for DML, heavy queries, or live data. Prefer a read replica or sandbox with representative data, timeouts, and approval.

### 14.2. MySQL

~~~sql
EXPLAIN
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Inspect access type, estimated rows, chosen key, and extra operations. On supporting versions, MySQL `EXPLAIN ANALYZE` also **executes** the statement; avoid running during peak hours without assessing cost.

### 14.3. SQL Server

Use the **estimated execution plan** in an authorized client. Actual execution plans run the query and add load. Inspect index scans/seeks, cardinality estimates, joins, memory grants, spills, and blocking; verify permissions before viewing other sessions' plans.

### 14.4. A Slow Query Can Have Several Causes

| Plan/Metric | Likely Explanation | What to Inspect |
|---|---|---|
| Full table scan, high rows examined | Missing index or non-selective filter | Indexes, cardinality, statistics |
| Large sort or temp files | Memory/I/O-heavy `ORDER BY`/`GROUP BY` | Index ordering, work memory, pagination |
| Repeated nested loops | Bad join plan or cardinality estimate | Statistics, indexes, join keys |
| Too many rows returned | Query/endpoint fetches excessive data | Pagination, projections, network |
| High lock wait | DML/transaction holding locks | Blocking sessions and transaction duration |
| High CPU and CPU-heavy query | Heavy expressions, joins, or aggregates | `EXPLAIN`, optimized SQL |
| High I/O wait | Heavy data reads/writes or storage limits | IOPS, cache hit ratio, disk metrics |

Never apply every suggested index blindly: new indexes add storage and write overhead, may require online builds or maintenance windows, and can take locks depending on engine/version.

## 15. Locks, Deadlocks, and Long Transactions

A query with an optimal plan will still crawl if blocked behind another transaction.

### 15.1. PostgreSQL

Use `pg_blocking_pids(pid)` to find blockers and `pg_stat_activity` for `wait_event_type` and transaction age. Watch closely for long `idle in transaction` sessions: the connection stopped running SQL, yet its open transaction can still hold locks and block vacuuming.

### 15.2. MySQL

Inspect the processlist and InnoDB transaction/lock views according to permissions and engine version. In MySQL 8, `performance_schema.data_locks` and `data_lock_waits` link blocking and waiting transactions.

~~~sql
SELECT OBJECT_SCHEMA,
       OBJECT_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS
FROM performance_schema.data_locks
LIMIT 30;
~~~

This query returns only lock metadata and may be empty depending on activity and permissions; trace blocking chains via `performance_schema.data_lock_waits` in an authorized environment.

### 15.3. SQL Server

From `sys.dm_exec_requests`, inspect `blocking_session_id` and `wait_type`. `LCK_M_*` waits indicate lock contention. Never run `KILL` without identifying the session owner and rollback impact.

### 15.4. Safe Mitigation

1. Identify the blocker and owner—determine whether it is a migration, DDL, or application transaction.
2. Throttle concurrency or new traffic for the affected query.
3. Check whether the transaction can finish naturally.
4. If intervention is unavoidable, follow **approved procedures** to cancel a query or terminate a specific session.
5. Estimate rollback duration and data impact.
6. Watch lock waits and pool recovery afterward.

Never restart the database just because a lock appeared. Restarts cause extra downtime and connection storms once the instance returns.

## 16. CPU, Memory, and I/O Saturation

### 16.1. CPU

High CPU usually correlates with rising QPS, heavy scan/sort plans, or too many concurrent queries. Inspect **database load by query** alongside request rate rather than upgrading instance tiers immediately if a recent deploy introduced a query regression that can be rolled back.

### 16.2. Memory

Many connections consume RAM; PostgreSQL also incurs per-backend process overhead. Heavy sorts/hash joins, caches, and prepared statements strain memory. Instance memory pressure or OOMs can drop connections and cause metric gaps.

Raising `max_connections` without memory headroom can make the database **less stable**. Usually you should trim pool over-allocation and long transactions first.

### 16.3. Disk I/O

Full scans, missing indexes, temp files, and heavy writes drive up IOPS and throughput. Cloud SQL instance tier, storage technology, and disk size govern I/O limits. Correlate I/O waits in Query Insights with disk metrics rather than diagnosing from p95 latency alone.

### 16.4. Network

Clients placed far from the DB region pay extra round-trip latency. A fast small query executed in an N+1 loop becomes slow overall. Cross-region hops, VPC routing, proxies, and DNS also add overhead; separate **connection wait**, **query execution**, and **result transfer** times.

## 17. Fixing Application- and SQL-Driven Slowness

Sustainable improvements include:

- Adding composite indexes ordered for predicates/joins/sorts after validating query plans.
- Eliminating N+1 ORM fetches via controlled joins or batch loading.
- Enforcing pagination/limits instead of loading entire tables into memory.
- Avoiding `SELECT *` when only a few columns are needed.
- Keeping engine statistics and maintenance up to date.
- Shortening transactions; never hold DB transactions open across external API calls.
- Offloading analytical/reporting queries off the primary where appropriate.
- Adding caching with business-aligned TTLs and invalidation.
- Chunking batch jobs instead of running a single giant transaction.
- Setting SLO-aligned query timeouts with safe retries and idempotency.

**Read replicas** offload some read traffic from the primary, yet cannot fix bad query plans and introduce replication lag. Requests needing read-after-write consistency must route appropriately. Never send payment or order writes to a replica.

## 18. Should You Add an Intermediate Connection Pooler?

### 18.1. Client-Side Pools

HikariCP amortizes connection setup and reuses sessions inside each JVM, fitting most Java services well.

However, with hundreds of serverless instances each holding a separate pool, aggregate connections can still run high.

### 18.2. Managed Connection Pooling for Cloud SQL PostgreSQL

Cloud SQL for PostgreSQL offers **Managed Connection Pooling** on supported configurations (such as Enterprise Plus, compatible network architectures, and maintenance versions). An intermediate pooler reuses server connections and absorbs bursts from many clients.

Check before enabling:

- Applicability to **Cloud SQL PostgreSQL**, edition/region, networking, and connector/proxy version.
- Enabling may **restart the database**.
- `transaction` pool mode may not support session-state features such as `LISTEN`, session advisory locks, temp tables, or certain prepared statement modes.
- Workloads with long transactions may see limited benefit.
- Database `max_connections` still bounds server connections behind the pooler.
- Test compatibility with your Java/JDBC/Hibernate driver, transaction boundaries, and session settings.

Never enable a pooler mid-incident without compatibility assessment and rollback plans. For some long-running workloads, direct connections or session pooling fit better than transaction pooling.

### 18.3. Cloud SQL Auth Proxy Is Not a Pooler

Cloud SQL Auth Proxy simplifies secure connectivity and IAM authentication; **it does not perform pooling** like Hikari, PgBouncer, or Managed Connection Pooling. A container using the proxy can still open many database sessions—a common misconception when Cloud Run uses the Cloud SQL connector.

## 19. P0/P1 Runbook: Mitigating with Minimal Blast Radius

Prioritize **data consistency** and restoring service availability. Before changing anything, confirm the primary symptom and confidence in your hypothesis.

### 19.1. Relatively Safe Mitigations to Consider

| Situation | First Mitigation | What to Watch |
|---|---|---|
| Pool connections spike right after rollout | Halt rollout / roll back service per approval | Instance counts, sessions, 5xx |
| Batch job suddenly opens 100 connections | Pause job or cut worker concurrency | DB headroom, backlog |
| High Hikari pending due to slow queries | Lower request concurrency; mitigate query/blocker | Pending count, p95, lock waits |
| New query saturates CPU/I/O | Roll back feature/query path or rate-limit | CPU/I/O, top queries |
| Connection churn in Cloud Run | Lower max instances; tune pool/`minIdle` | Connection count, error rate |
| DB instance genuinely lacks capacity | Plan tier/HA scale-up appropriately | Restart/downtime, CPU, latency |
| Data migration locks table too long | Pause or resolve migration per runbook | Lock waits, schema state |

**Never raise `max_connections` as a knee-jerk reflex.** A higher limit can exhaust RAM and worsen the overload.

### 19.2. Session Intervention Is a Last Resort

`pg_cancel_backend`, `pg_terminate_backend`, MySQL `KILL QUERY/CONNECTION`, or SQL Server `KILL` can abort user transactions, trigger lengthy rollbacks, drop active sessions, or affect in-flight data. This guide does not prescribe running them directly. When necessary, a DBA must confirm PID/session, owner, and purpose under formal incident approval.

### 19.3. Avoid Triggering a Post-Recovery Connection Storm

After restarts, resizes, or failovers, hundreds of Pods may reconnect simultaneously. Use jitter, exponential backoff, capped concurrency, and staged pool initialization to avoid the loop "DB recovers → flood of connections → DB overloads again."

## 20. Distinguishing Connectivity Errors from Exhaustion

Not every connection failure stems from connection limits.

| Error or Symptom | Investigation Path |
|---|---|
| DNS resolution failed | Hostname, private DNS, connector config |
| TCP timeout / connection refused | Network routes, firewalls, private IP, instance state |
| IAM permission denied | `cloudsql.instances.connect`, service account, IAM DB auth if used |
| Invalid DB user/password | Database user, Secret Manager, credential rotation |
| TLS/CA verification failed | Certificates, connector/driver versions |
| Cloud SQL Auth Proxy Admin API quota | Cloud SQL Admin API quota during scale-out, connector logs |
| Connection pool acquisition timeout | Hikari active/idle/pending and long transactions |
| Server too many connections | Engine sessions vs. `max_connections` |
| Query deadline exceeded | Slow SQL, locks, CPU/I/O, or client timeout |

Separate **Google Cloud IAM** from **database authentication**: `roles/cloudsql.client` permits connecting via connector/proxy per service rules, yet the database user must still authenticate (password or IAM DB authentication). VPC connectivity grants network reachability, not SQL privileges.

With private IP, ensure Cloud Run Direct VPC egress/Serverless VPC Access or the right GKE/VPC path. With the Cloud SQL Java Connector, verify the instance connection name `PROJECT:REGION:INSTANCE` and config—do not confuse it with the database name.

## 21. Designing Preventive Alerts and Dashboards

A minimal operational dashboard:

1. Cloud SQL current/peak connections and ratio to effective limit.
2. CPU, memory, disk, I/O, and engine errors.
3. Query Insights load, top normalized queries, and lock waits.
4. Java Hikari active/idle/pending counts and connection acquire timeouts.
5. Cloud Run/GKE instance/Pod counts, concurrency, and request rate.
6. HTTP/gRPC 5xx, p95/p99 latency, and database dependency span latency.
7. Cloud SQL connector/proxy errors and re-authentication/refresh failures.
8. Deployments, database flag edits, schema migrations, and autoscaling events.

**Illustrative alert thresholds**:

| Alert | Purpose |
|---|---|
| Peak DB connections > 75% of limit for several minutes | Early warning for investigation |
| > 90% with 5xx or acquire timeouts | High-severity incident response |
| Hikari pending rising steadily | Detect pool pressure before timeouts |
| SQL p99 jumps 3x over baseline | Catch slow query regressions |
| Rising lock waits and long transactions | Catch blockers early |
| Cloud Run instance count rising while DB headroom falls | Warn of impending connection storm |

Never deploy one-size-fits-all thresholds across every database. Establish baselines per engine, instance, and tier, ensure metrics filter cleanly by instance label, and add anti-flap logic. Alerts only create value when paired with an owner/on-call and a runbook.

## 22. Safe Lab Rehearsal

In an authorized **sandbox project/database**, generate synthetic data and run two independent exercises. Never intentionally overload production Cloud SQL.

### 22.1. Exercise A — Application Pool Exhaustion

Configure a Spring Boot service with Hikari `maximumPoolSize=2` against a sandbox database. Have two requests run controlled slow transactions concurrently while a third request tries to check out a connection.

Observe:

- Hikari active=2, idle=0, pending rises.
- The third request waits up to `connectionTimeout` and then times out.
- The database remains **well below** `max_connections`.
- Once the two transactions finish, the pool recovers.

Afterward, restore config and close test connections. Never introduce real memory leaks or infinite transactions.

### 22.2. Exercise B — Slow Query

Create a test table with zero PII, run an unindexed query in the sandbox, and use Query Insights/`EXPLAIN` to compare before and after adding an index.

Observe:

- Changes in query latency and rows examined.
- Changes in CPU/I/O and query plan.
- Whether Hikari active/pending drop as queries speed up.
- Whether the new index increases write overhead.

Use small test datasets, set timeouts, and never run `EXPLAIN ANALYZE` on production tables.

### 22.3. Exercise C — Server Connection Budget

Use **calculations and metrics** to model 5, 20, and 40 Cloud Run instances with pool sizes of 5, 8, and 10—without opening hundreds of real connections against a shared database. Identify where theoretical totals cross limits and propose max instances/concurrency caps.

## 23. Case Study: Orders API Slows Down and Throws Hikari Errors

### 23.1. Current State

A Java/Spring Boot app on Cloud Run uses Cloud SQL PostgreSQL. **Hypothetical** baseline:

- Database instance has `max_connections=300`.
- 20 Cloud Run instances at peak.
- Hikari `maximumPoolSize=10`, `minimumIdle=10`.
- A scheduled reporting job opens 40 additional sessions.
- Incident begins right after a release adding an order lookup query.

Post-release, `GET /orders` p99 jumps from 150 ms to 6 seconds, Hikari pending climbs, and HTTP 503s appear.

### 23.2. Investigation

1. Database shows 250 connections—**below** 300.
2. Hikari on multiple instances shows active=10, idle=0, and large pending queues.
3. Query Insights shows one new normalized query dominating total time.
4. `pg_stat_activity` shows many active sessions waiting on I/O, with few lock waits.
5. `EXPLAIN` in sandbox shows massive row scans due to a missing composite index and overly wide column selection.
6. The same release also raised Cloud Run max instances, expanding total potential pool connections.

**Conclusion:** root cause is query regression + connection amplification. Hikari timeouts are an application-side symptom, not proof PostgreSQL ran out of slots.

### 23.3. Mitigation and Fix

- Short-term: roll back the release under approval, cap request burst/max instances if needed, and monitor Hikari pending/5xx.
- Medium-term: optimize the query, index, and pagination using query plans and representative data; re-test p95/p99.
- Long-term: size pools strictly to budget, lower `minimumIdle` for serverless if suitable, alert on peak connections + Hikari pending, and review concurrency whenever changing autoscaling.
- Audit transaction boundaries to confirm no connection stays open across outbound HTTP calls.

After rollback, measure **time until the application serves normally**, not merely when DB connection counts drop.

### 23.4. Sample RCA Template

~~~text
Incident: INC-2026-EXAMPLE
Started at (UTC): YYYY-MM-DD HH:MM
Affected: orders-api GET /orders, Cloud SQL PostgreSQL
Symptoms: p99 increase, Hikari pending, 503
Customer impact: [measured request failures / duration]

Evidence:
- Cloud Run revision and scale timeline
- DB connection count, CPU/IO charts
- Hikari active/idle/pending
- Query Insights normalized fingerprint
- Read-only DB session checks

Root cause:
- Query plan regression + amplified concurrency

Contributing factors:
- Hikari minimumIdle/maximumPoolSize not re-budgeted
- No alert on pending checkouts

Mitigation:
- Approved rollback / rate limit

Long-term actions:
- Index/query optimization
- Pool budget and autoscaling guardrail
- Regression load test
- Runbook/alerts update

Verification:
- 5xx back to baseline
- p95/p99 within SLO
- DB sessions with headroom
- No pending pool timeouts
Owner: [team]
Follow-up date: [date]
~~~

## 24. Common Anti-Patterns

| Mistake | Consequence | Fix |
|---|---|---|
| Raising `max_connections` on seeing Hikari timeouts | Adds memory pressure without fixing leaks | Inspect app pools and DB sessions separately |
| Reusing one pool size across all services | Budget ignores real concurrency and load | Size per workload and replica count |
| Ignoring overlapping Cloud Run revisions and jobs | Connection storms during rollouts | Reserve headroom + rollout guardrails |
| Treating Cloud SQL Auth Proxy as a pooler | Unbounded DB sessions per container | Configure Hikari or a supported pooler |
| Checking `Threads_connected` while ignoring `Threads_running` | Cannot separate idle from active load | Inspect processlist and query latency |
| Wrapping HTTP calls in `@Transactional` | Holds connections and locks open too long | Shorten transactions / use sagas |
| Debugging with raw SQL containing PII | Data exposure | Use normalized queries and redact logs |
| Running `EXPLAIN ANALYZE` on production DML | Executes and mutates live data | Use plain `EXPLAIN` or a sandbox |
| Killing all idle sessions | Breaks pools and triggers reconnect storms | Identify owner and drain cleanly |
| Restarting DB over a single blocker | Unnecessary downtime | Run lock diagnostics and targeted mitigation |
| Raising Cloud Run max instances without checking DB | Blows past connection budget | Coordinate concurrency and pools |
| Blindly using pooler transaction mode with session state | Breaks app/query behavior | Run compatibility tests; use session mode if needed |
| Looking only at CPU while ignoring locks/I/O | Incomplete diagnosis | Check Query Insights + wait breakdowns |
| Checking only completed queries in Query Insights | Misses currently hung queries | Check Active queries and engine views |
| Unbounded retries | Piles load onto a failing DB | Enforce backoff, jitter, and retry budgets |
| Declaring recovery just because DB is "up" | 5xx and high latency persist | Verify SLOs and business flows |

## 25. Production Diagnostic Checklist

### A. Scope and Evidence

- [ ] Identified project/instance/engine/version/region and accountable owner.
- [ ] Recorded UTC timestamps, recent releases/migrations, and business impact.
- [ ] Collected Cloud SQL connections/CPU/memory/I/O and app 5xx/p99 metrics.
- [ ] Collected Hikari active/idle/pending/timeout metrics.
- [ ] Sanitized dashboards/logs/traces of PII and credentials.

### B. Exact Fault Branch

- [ ] Separated network/auth failures from pool checkout waits and server connection limits.
- [ ] Verified actual engine `max_connections`/limits and reserved slots.
- [ ] Counted sessions by app/DB/user and concurrent workloads.
- [ ] Checked long transactions, blockers, and CPU/I/O waits.
- [ ] Verified query fingerprints, plans/indexes, and QPS shifts.
- [ ] Calculated total connection budget across all replicas, revisions, and jobs.

### C. Mitigation and Prevention

- [ ] All changes have approval and a rollback path.
- [ ] Did not kill sessions or restart the DB without understanding impact.
- [ ] Evaluated concurrency caps, query/deploy rollback, or pausing batches.
- [ ] Verified Hikari pool size/`minIdle`/`maxLifetime` against budget.
- [ ] Confirmed retries/backoff and idempotency are sound.
- [ ] Tested database flag or pooler changes in staging first.
- [ ] Assigned owners/on-call to dashboards and alerts.

### D. Recovery Verification

- [ ] 5xx rates returned to normal baseline.
- [ ] Request p95/p99 meets SLO.
- [ ] DB retains healthy headroom with no new connection storms.
- [ ] Hikari pending counts and acquire timeouts dropped.
- [ ] No abnormal blocking transactions remain.
- [ ] Zero data loss or duplicate write side effects.
- [ ] RCA and deadline-tracked action items documented.

## 26. Practice Exercises

### Exercise 1 — Separate Two Types of Exhaustion

Given the following observations:

~~~text
Cloud SQL PostgreSQL connections: 80 / 300
Hikari maximumPoolSize: 6
Hikari active: 6
Hikari idle: 0
Hikari pending: 21
HTTP 5xx: 8%
~~~

Question: is there enough evidence to conclude the server ran out of connections? Which metrics/queries should you check next? State at least three hypotheses.

### Exercise 2 — Connection Budget

A Cloud SQL instance has an effective connection limit of 400, must reserve 80 slots for maintenance/other apps, and serves 25 Cloud Run instances plus 10 GKE Pods. Pick pool sizes for each workload so total projected usage leaves headroom, then model Cloud Run scaling up to 50 instances.

### Exercise 3 — Query Insights

One normalized query runs 50,000 times/hour averaging 40 ms (2,000 seconds total); another runs 10 times/hour at 3 seconds each (30 seconds total). Explain why optimizing only the query with the highest p99 latency can miss the main driver of database load.

### Exercise 4 — Long Transaction

A PostgreSQL session has been `idle in transaction` for 12 minutes while several other sessions sit in `Lock` wait. Outline a **read-only** diagnostic sequence, escalation criteria, and the risks of terminating the session.

### Exercise 5 — Cloud Run Deployment

Before deploy, a service runs 10 instances with Hikari pool size 8; the new release can scale to 40 instances, and a job uses 50 DB connections. Calculate the budget, define release guardrails, and explain why overlapping revisions during rollout must be factored in.

### Exercise 6 — Draft an RCA

Write an RCA covering timeline, symptoms, root cause, contributing factors, mitigation, verification, and preventive action items. Use only sanitized SQL digests and metrics.

## 27. Self-Check Questions

1. Does a Hikari connection acquisition timeout prove Cloud SQL hit `max_connections`?
2. How do `Threads_connected` and `Threads_running` differ?
3. Why are multiple PostgreSQL sessions in `idle in transaction` more dangerous than ordinary `idle` sessions?
4. How do Query Insights top queries differ from active queries?
5. Why can a query with fast average latency still dominate total database load?
6. When is PostgreSQL `EXPLAIN ANALYZE` risky?
7. Why does Cloud SQL Auth Proxy not replace a connection pool?
8. How do Cloud Run max instances affect total database sessions?
9. Why can raising `max_connections` make a database less stable?
10. What problems arise when holding a transaction open across an external payment API call?
11. Why must network/IAM errors be separated from pool exhaustion?
12. When should you evaluate Managed Connection Pooling on PostgreSQL?
13. Which session-based features can transaction pooling break?
14. Do lock waits and CPU saturation share the same remediation?
15. Why must slow query logs be evaluated for cost and sensitive data exposure?
16. Why must retries after a payment write timeout enforce idempotency?
17. Which metrics prove an incident is genuinely resolved?
18. How must a strong RCA distinguish root causes and preventive actions from symptoms?

## References

- [Cloud SQL for PostgreSQL: Diagnose issues](https://docs.cloud.google.com/sql/docs/postgres/diagnose-issues)
- [Cloud SQL for PostgreSQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL for PostgreSQL: Debug connection issues](https://docs.cloud.google.com/sql/docs/postgres/debugging-connectivity)
- [Cloud SQL for PostgreSQL: System Insights](https://docs.cloud.google.com/sql/docs/postgres/use-system-insights)
- [Cloud SQL for PostgreSQL: Query Insights](https://docs.cloud.google.com/sql/docs/postgres/using-query-insights)
- [Cloud SQL for PostgreSQL: Active queries](https://docs.cloud.google.com/sql/docs/postgres/monitor-active-queries)
- [Cloud SQL for PostgreSQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL for PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL: Quotas and limits](https://docs.cloud.google.com/sql/docs/quotas)
- [Cloud SQL for MySQL: Debug connection issues](https://docs.cloud.google.com/sql/docs/mysql/debugging-connectivity)
- [Cloud SQL for MySQL: Query Insights](https://docs.cloud.google.com/sql/docs/mysql/using-query-insights)
- [Cloud SQL for MySQL: Database flags and slow query log](https://docs.cloud.google.com/sql/docs/mysql/flags)
- [Cloud SQL for SQL Server: Query Insights](https://docs.cloud.google.com/sql/docs/sqlserver/using-query-insights)
- [Cloud SQL for SQL Server: Active queries](https://docs.cloud.google.com/sql/docs/sqlserver/monitor-active-queries)
- [HikariCP configuration](https://github.com/brettwooldridge/HikariCP)
- [Spring Boot: Data SQL/JDBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL monitoring statistics](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [MySQL Performance Schema reference](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [SQL Server sys.dm_exec_requests](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)
