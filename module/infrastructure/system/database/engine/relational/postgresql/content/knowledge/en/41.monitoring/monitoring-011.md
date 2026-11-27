# Collecting Metrics with Exporters and Dashboards in PostgreSQL

To operate PostgreSQL reliably, teams need continuous visibility into database health, workloads, capacity, connections, queries, replication, WAL, vacuum, and recoverability. Ad-hoc diagnostic queries help during live incidents, yet they are not enough for ongoing tracking or receiving alerts before users are impacted.

A widely adopted metrics stack pairs PostgreSQL with **postgres_exporter**, **Prometheus**, and **Grafana**. The exporter reads statistics views and system catalogs and exposes metrics over HTTP. Prometheus scrapes that endpoint periodically, stores time series, and evaluates alert rules. Grafana queries Prometheus to render dashboards across clusters, instances, databases, and workloads.

~~~text
             PostgreSQL primary / standby
             ----------------------------
             pg_stat_database
             pg_stat_activity
             pg_stat_replication
             pg_stat_wal
             pg_stat_user_tables
             pg_stat_archiver
                       |
                       | SQL queries
                       v
                postgres_exporter
                -----------------
                /metrics :9187
                       |
                       | HTTP scrape
                       v
                   Prometheus
                   ----------
                TSDB / rules
                  /       \
                 /         \
                v           v
          Grafana       Alertmanager
          --------      ------------
          Dashboards   Route / group
          Explore      Silence / notify
                |
                v
        Operator / on-call engineer
~~~

The exporter, Prometheus, and Grafana carry distinct responsibilities. The exporter collects and translates metrics; Prometheus stores, queries, and evaluates rules; Grafana visualizes data. Alertmanager handles grouping, routing, and dispatching notifications for alerts raised by Prometheus.

This lesson belongs to the **Monitoring** chapter of the *Database Engine Relational PostgreSQL* module and focuses on collecting metrics with exporters, designing actionable dashboards, and operating the monitoring pipeline safely.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the architecture of exporter, Prometheus, Grafana, and Alertmanager.
2. Distinguish metrics, labels, samples, time series, and scrape targets.
3. Deploy `postgres_exporter` for a PostgreSQL instance.
4. Create a monitoring role with least-privilege permissions.
5. Configure exporter connections via DSN or environment variables.
6. Inspect the metrics endpoint and scrape status.
7. Configure Prometheus scrape jobs and target labels.
8. Use service discovery or static targets across multiple instances.
9. Select collectors suited to your workload and PostgreSQL version.
10. Collect metrics for transactions, sessions, cache, I/O, and tuples.
11. Monitor locks, wait events, deadlocks, and long-running transactions.
12. Monitor WAL, archiver, replication, and replication lag.
13. Monitor vacuum, dead tuples, table growth, and index usage.
14. Extend the exporter safely with controlled custom queries.
15. Design stable labels and prevent cardinality explosions.
16. Write PromQL for rates, ratios, gauges, and recording rules.
17. Design overview, workload, capacity, and replication dashboards.
18. Write alert rules and route notifications.
19. Distinguish an exporter outage from a PostgreSQL outage.
20. Secure credentials, metrics endpoints, and sensitive data.
21. Monitor multiple databases, clusters, and HA roles.
22. Handle stats resets, metric gaps, and differences across major versions.
23. Validate dashboard accuracy against direct SQL queries.
24. Build monitoring runbooks and continuous improvements.

## 2. Why Continuous Metrics Matter

PostgreSQL provides rich statistics views, yet numbers become truly actionable only when tracked over time and tied to application impact.

### 2.1. Early incident detection

Connections may approach limits, WAL archiving may begin failing, replication lag may climb, disks may approach exhaustion, or dead tuples may pile up. Dashboards reveal trends before issues turn into outages.

### 2.2. Understanding workloads

Transaction rates, commits, rollbacks, block reads, cache hits, temporary bytes, and active sessions show what kind of workload the system is processing.

### 2.3. Diagnosing bottlenecks

High CPU can come from queries, I/O waits, vacuuming, or excessive backends. Metrics must be combined with `pg_stat_activity`, wait events, OS metrics, and query statistics.

### 2.4. Measuring the effect of changes

After adding an index, tuning connection pools, adjusting autovacuum, or upgrading PostgreSQL, compare before and after over matching workload windows.

### 2.5. Tracking SLAs and SLOs

Availability, latency, error rates, replication freshness, and backup status can translate into appropriate SLIs and SLOs. Database metrics form part of the service picture without replacing application-layer telemetry.

### 2.6. Reducing manual toil

Scheduled Prometheus scrapes and centralized dashboards keep teams from logging into individual servers every day to run the same diagnostic queries.

## 3. Components of the Monitoring Stack

| Component | Responsibility | Question Answered |
| --- | --- | --- |
| PostgreSQL | Exposes internal statistics and runtime state | What is the database doing? |
| postgres_exporter | Queries stats and exposes Prometheus metrics | Which metrics are available to scrape? |
| Prometheus | Scrapes, stores time series, runs PromQL and rules | How do metrics change over time? |
| Grafana | Dashboards, Explore, and visualization | What do operators need to see? |
| Alertmanager | Groups, routes, silences, and notifies | Who needs to be paged? |
| node_exporter | OS-level host metrics | Are CPU, RAM, disk, or network strained? |
| Application instrumentation | Application telemetry | How are end users impacted? |

### 3.1. PostgreSQL statistics

PostgreSQL maintains views such as `pg_stat_database`, `pg_stat_activity`, `pg_stat_replication`, `pg_stat_wal`, and `pg_stat_user_tables`. These views feed the exporter.

### 3.2. Exporter

The exporter runs as a process or container. It connects to PostgreSQL using a monitoring role and serves an HTTP endpoint, commonly on port 9187 by default.

### 3.3. Prometheus

Prometheus polls the exporter endpoint on a configured scrape interval, storing timestamped samples with labels into its time-series database.

### 3.4. Grafana

Grafana uses Prometheus as a data source, executes PromQL queries, and renders results as stat panels, time series, tables, heatmaps, or alert views.

### 3.5. Alertmanager

Prometheus evaluates alert rules and forwards alert state to Alertmanager. Alertmanager groups alerts, deduplicates notifications, applies silences/inhibitions, and routes them to configured receivers.

### 3.6. Node exporter

`postgres_exporter` does not replace `node_exporter`. To monitor CPU, RAM, filesystems, disk I/O, and network on the PostgreSQL host, collect OS metrics separately.

## 4. Metrics, Labels, and Time Series

Prometheus organizes telemetry into time series.

### 4.1. Metric

A metric names a measured quantity, such as committed transactions, active connections, or WAL bytes generated.

### 4.2. Sample

A sample consists of a numeric value and a timestamp. Prometheus stores sequential samples over time for each series.

### 4.3. Label

Labels add dimensional classification, such as `cluster`, `instance`, `database`, or `state`.

### 4.4. Time series identity

A time series is uniquely identified by its metric name plus its exact set of label key-value pairs. Any change in label values creates a distinct series.

### 4.5. Example

~~~text
pg_stat_database_xact_commit{
  cluster="orders-prod",
  instance="db-a",
  datname="orders"
} 125400
~~~

This sample represents committed transactions in the `orders` database on instance `db-a` of cluster `orders-prod` at that sample timestamp.

### 4.6. Counter

A counter rises monotonically until process/statistics reset. Use `rate()` or `increase()` to analyze per-second rate or total change over a window.

### 4.7. Gauge

A gauge can go up or down, such as current connections, estimated dead tuples, or replication lag.

### 4.8. Histogram

A histogram places observations into buckets and exposes counts and sums. Most PostgreSQL exporters do not emit per-query latency histograms by default; application instrumentation or custom collectors are usually required.

### 4.9. Metric type and semantics

A metric's name alone is not enough to know how to query it. Inspect `# HELP` and `# TYPE` on the `/metrics` endpoint and check your exporter version's documentation. Never apply `rate()` to a gauge or sum incompatible units.

## 5. Installing and Running postgres_exporter

`postgres_exporter` is a PostgreSQL exporter commonly distributed within the Prometheus community ecosystem.

### 5.1. Selecting a release

Pick a binary or container matching your OS, CPU architecture, and PostgreSQL version. Record the exporter version in your inventory for upgrade tracking.

### 5.2. Running as a binary

One common deployment installs the binary on the database host or a monitoring host with network access to PostgreSQL, running as a systemd service under a dedicated OS user.

### 5.3. Running in a container

You can run the exporter in a separate container, expose its metrics endpoint to Prometheus, and inject credentials via a secret mechanism.

### 5.4. Default port

The standard HTTP port is `9187`, controlled by the exporter's web listen address configuration.

### 5.5. Metrics endpoint

The default endpoint path is usually `/metrics`:

~~~bash
curl http://127.0.0.1:9187/metrics
~~~

In production, restrict access to the endpoint via firewalls, private networks, or a reverse proxy enforcing authentication and TLS where required.

### 5.6. Health checks

Depending on version, the exporter may expose health or readiness endpoints. Check `--help` and documentation for your binary; Prometheus scrape target health (`up`) remains a critical signal.

### 5.7. Running the exporter separately

Keeping the exporter process separate from PostgreSQL allows independent updates and restarts. Even so, the exporter still depends on database connectivity and opens monitoring connections.

## 6. Creating a Monitoring Role in PostgreSQL

Never use a superuser account as the exporter's default credential. Create a dedicated login role for monitoring.

### 6.1. Creating the role

~~~sql
CREATE ROLE postgres_exporter
    LOGIN
    PASSWORD 'replace-with-secret';
~~~

The password above is purely a lab placeholder. Production deployments should use a secret manager or controlled credential provisioning.

### 6.2. Granting pg_monitor

On PostgreSQL versions providing the predefined `pg_monitor` role:

~~~sql
GRANT pg_monitor TO postgres_exporter;
~~~

This role grants read access to most required monitoring views and statistics without making the exporter a superuser.

### 6.3. Checking version behavior

Predefined roles and statistics view permissions evolve across major versions. On older servers, consult version-specific permission docs and grant narrow privileges matching enabled collectors.

### 6.4. Do not grant write privileges

The exporter only reads telemetry. Never grant `INSERT`, `UPDATE`, `DELETE`, `CREATE`, or unnecessary administrative privileges.

### 6.5. Custom query permissions

If a custom query reads application tables or custom schemas, grant `SELECT` strictly on those exact objects and schemas. Never expose all business data just to emit one metric.

### 6.6. Connection limits

Set a sensible connection limit if exporters or multiple collectors might open excess sessions, while avoiding setting it so low that legitimate scrapes fail.

### 6.7. Verifying the role

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolreplication,
    rolconnlimit
FROM pg_roles
WHERE rolname = 'postgres_exporter';
~~~

## 7. Connecting the Exporter to PostgreSQL

The exporter needs a connection string (DSN) or equivalent environment variables.

### 7.1. DSN

Example connection string:

~~~text
postgresql://postgres_exporter:secret@db-a.internal:5432/postgres?sslmode=verify-full
~~~

The initial connection database may be `postgres` or a dedicated monitoring database. Some collectors read cluster-wide statistics, while others connect to each database individually.

### 7.2. Environment variables

Depending on the `postgres_exporter` version, you can configure `DATA_SOURCE_NAME` or `DATA_SOURCE_URI`, `DATA_SOURCE_USER`, and `DATA_SOURCE_PASS`. Check documentation for your exact version.

### 7.3. Never pass passwords on the command line

Command-line arguments can appear in process listings, shell history, and logs. Prefer secret stores, protected environment files, `.pgpass`, or container secrets.

### 7.4. TLS

Use an appropriate `sslmode`, such as `verify-full` with CA and hostname verification. Never downgrade TLS verification in production as a quick workaround for certificate errors.

### 7.5. pg_hba.conf

Allow connections from the exporter host or subnet:

~~~conf
hostssl postgres postgres_exporter 10.30.0.0/24 scram-sha-256
~~~

If the exporter connects to multiple databases, add rules matching those database names or `all` per security policy.

### 7.6. Network path

Verify routing, firewalls, DNS, security groups, and TLS before debugging collector queries.

### 7.7. Testing connectivity directly

~~~bash
psql "host=db-a.internal port=5432 dbname=postgres user=postgres_exporter sslmode=verify-full" -c "SELECT pg_is_in_recovery();"
~~~

If a direct `psql` connection fails, the exporter will not scrape successfully either.

## 8. Configuring the Exporter and Collectors

The exporter enables default collectors and optionally supports custom collectors depending on version.

### 8.1. Default collectors

Common built-in groups cover database statistics, activity, replication, WAL, archiver, table statistics, locks, and basic system info. The exact list depends on exporter version and build.

### 8.2. Unnecessary collectors

Do not enable every collector just because it exists. Collectors scanning thousands of objects or databases can increase scrape duration and load on PostgreSQL.

### 8.3. Database discovery

Some versions support auto-discovering and connecting to every database. This helps capture per-database metrics while increasing connection counts and scrape duration.

### 8.4. Excluding databases

You can exclude template databases or uninteresting databases if supported by exporter flags. Do not exclude system databases if dashboards or collectors depend on them without verifying first.

### 8.5. Collector flags

Flag names, default collectors, and enable/disable syntax change across releases. Inspect `--help` on your running binary and document tested configs alongside versions.

### 8.6. Scrape duration

Monitor how long scrapes take. If collector queries run longer than `scrape_interval`, scrapes can overlap, time out, or return stale data.

### 8.7. Splitting collectors

Fast core collectors can run at short intervals; heavy collectors such as table/index inventories or query-level stats can run at longer intervals or in separate scrape jobs.

## 9. Important PostgreSQL Metric Groups

No single dashboard fits every workload. Organize metrics around operational questions.

| Group | Typical Data Source | What to Observe |
| --- | --- | --- |
| Availability | exporter scrape, `pg_up` | Are exporter and database reachable? |
| Connections | `pg_stat_activity` | Session counts, states, wait events |
| Transactions | `pg_stat_database` | Commits, rollbacks, transaction rates |
| Cache/I/O | `pg_stat_database`, `pg_stat_io` | Buffer hits, reads, I/O |
| Locks | `pg_locks`, `pg_stat_activity` | Blocking, waiting, deadlocks |
| Replication | `pg_stat_replication`, `pg_stat_wal_receiver` | WAL send/write/flush/replay |
| WAL/archiving | `pg_stat_wal`, `pg_stat_archiver` | WAL generation and archive failures |
| Vacuum | `pg_stat_user_tables`, progress views | Dead tuples, vacuum/analyze |
| Tables/indexes | `pg_stat_user_tables`, `pg_stat_user_indexes` | Scans, tuple changes, index usage |
| Queries | `pg_stat_statements` | Query calls, time, rows, I/O |
| Host | `node_exporter` | CPU, RAM, disk, filesystems, network |

### 9.1. Availability

Monitor both Prometheus scrape health and exporter-to-database connection status. These are two distinct signals.

### 9.2. Workload

Transaction rates, session counts, active queries, and tuple modifications reveal real workload volume.

### 9.3. Capacity

Connections, disk usage, WAL retention, table growth, and dead tuples forecast resource limits.

### 9.4. Performance

Query latency, block I/O, waits, locks, and cache behavior isolate bottlenecks.

### 9.5. Replication

Receive/replay progress, sender states, lag, and slot retention are vital for HA and read replicas.

## 10. pg_stat_database and Transaction Metrics

`pg_stat_database` provides per-database statistics.

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

### 10.1. Transaction commits

`xact_commit` counts committed transactions since the last statistics reset. Because it is a counter, graph rates rather than raw totals.

### 10.2. Rollbacks

`xact_rollback` increments when transactions roll back. Rising rollback rates can reflect application errors, constraint violations, explicit rollbacks, or retry logic.

### 10.3. Transaction rate

Illustrative PromQL:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

Exact metric names depend on exporter version. Verify `/metrics` and `# HELP`/`# TYPE` before building dashboards.

### 10.4. Commit/rollback ratio

Compare commit rate against rollback rate to detect abnormal shifts. Do not assume every rollback is a failure; some applications roll back intentionally.

### 10.5. Temporary files

Rapidly rising `temp_files` and `temp_bytes` point to sort/hash disk spills, insufficient `work_mem` for a query pattern, or changing workloads.

### 10.6. Deadlocks

`deadlocks` is a counter. Alert on rate/delta and impact rather than cumulative totals since cluster startup.

### 10.7. Stats reset

`stats_reset` explains sudden drops in counters. When a server or database resets statistics, rates can dip briefly.

## 11. Connections and pg_stat_activity

`pg_stat_activity` is essential for understanding backend states.

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
WHERE backend_type = 'client backend'
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY sessions DESC;
~~~

### 11.1. Connection counts

Compare client backends against `max_connections` and reserved slots. Leave headroom for administration, replication, and incident response.

### 11.2. Active sessions

Active sessions are executing queries. Many active backends do not automatically mean overload; inspect CPU, I/O, waits, and query duration.

### 11.3. Idle sessions

Idle sessions are waiting for client commands. High idle counts can be normal with connection pools, provided they remain within connection limits and pool budgets.

### 11.4. Idle in transaction

Backends `idle in transaction` can hold locks and snapshots, slowing vacuum or causing contention. Track this state explicitly.

### 11.5. Wait events

`wait_event_type` and `wait_event` indicate whether backends wait on locks, I/O, clients, IPC, or other resources. Wait event names evolve across versions.

### 11.6. Query age

`now() - query_start` measures running query age. Transaction age must be tracked separately because a transaction may stay open far longer than its current query.

### 11.7. Query text

Query text can contain literals or sensitive data. Never export raw query strings as Prometheus labels or expose them broadly on dashboards.

### 11.8. PID cardinality

PIDs change continuously. Never include PIDs in labels for long-lived aggregate metrics without a strong reason; cardinality and series churn explode quickly.

## 12. Connections and Saturation

A database can suffer contention well before hitting `max_connections`.

### 12.1. Connection utilization

Calculate connection utilization relative to `max_connections` minus reserved slots and special roles. Use gauge metrics from `pg_stat_activity` and server settings.

### 12.2. Pool saturation

Collect application pool metrics: active, idle, waiting clients, and acquire latency. A PostgreSQL exporter cannot see requests queued inside application pools.

### 12.3. Connection churn

Rapidly opening and closing connections increases authentication overhead and backend startup cost. Compare connection rates against pool behavior.

### 12.4. Alert thresholds

Set thresholds around headroom and peak patterns—for example, warning above 75% utilization for several minutes and critical above 90%, adjusted for reserved connections and policy.

### 12.5. Do not raise max_connections casually

More backends increase memory pressure and scheduler overhead. Fix pooling, query concurrency, and workload leaks first.

## 13. Cache, Block Reads, and I/O

`pg_stat_database` provides `blks_hit` and `blks_read`.

### 13.1. Buffer hits

`blks_hit` counts blocks found directly in PostgreSQL shared buffers.

### 13.2. Block reads

`blks_read` counts blocks PostgreSQL had to request from the OS/filesystem. Many of these may be served from the OS page cache rather than physical disk reads.

### 13.3. Hit ratio

Reference formula:

\[
\text{Hit ratio} =
\frac{\text{blks\_hit}}
{\text{blks\_hit}+\text{blks\_read}}
\]

### 13.4. Illustrative PromQL

~~~promql
sum by (cluster, instance) (
  rate(pg_stat_database_blks_hit[5m])
)
/
clamp_min(
  sum by (cluster, instance) (
    rate(pg_stat_database_blks_hit[5m])
    + rate(pg_stat_database_blks_read[5m])
  ),
  1
)
~~~

Verify exact metric names emitted by your exporter.

### 13.5. Hit ratio does not capture full I/O health

A high hit ratio does not guarantee fast queries. A workload may hit cache repeatedly while bottlenecked on CPU or locks. Low hit ratios also require inspecting working sets and OS caching.

### 13.6. pg_stat_io

On PostgreSQL versions supporting `pg_stat_io`, inspect I/O by backend, object, and context. Views and columns vary across major versions; use compatible exporters or custom queries.

### 13.7. Node exporter

Pair with disk read/write throughput, latency, queue depth, and filesystem utilization from `node_exporter` to isolate physical storage bottlenecks.

## 14. Locks, Blocking, and Deadlocks

### 14.1. pg_locks

`pg_locks` displays held and awaited locks. Putting individual lock objects into metric labels creates severe cardinality issues.

### 14.2. Blocked sessions

Diagnostic query linking blocked backends to blockers:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.datname,
    blocked.application_name,
    now() - blocked.query_start AS blocked_duration,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_application,
    left(blocked.query, 200) AS blocked_query_sample
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid;
~~~

### 14.3. Blocking duration

Track how long sessions wait on locks. Brief waits can be normal; prolonged or rising waits cause user-visible latency.

### 14.4. Deadlocks

A rising `deadlocks` counter shows PostgreSQL detected deadlocks. Server logging must be enabled/configured to capture details on the transactions involved.

### 14.5. Aggregate dashboards

Dashboards should focus on blocked session counts, maximum wait age, deadlock rates, and top wait categories. Inspect specific PIDs and queries in access-controlled diagnostic views rather than turning every PID into a time series.

## 15. Replication and WAL Metrics

For physical replication, monitor both the sender on the primary and receiver/replay on standbys.

### 15.1. pg_stat_replication

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    sync_state
FROM pg_stat_replication;
~~~

### 15.2. WAL stages

- `sent_lsn`: last WAL position sent.
- `write_lsn`: last WAL position written by the standby.
- `flush_lsn`: last WAL position flushed by the standby.
- `replay_lsn`: last WAL position replayed by the standby.

### 15.3. Byte gap

Measure byte distance from primary current LSN to replay LSN:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_gap_bytes
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

### 15.4. Lag time fields

`write_lag`, `flush_lag`, and `replay_lag` reflect recent delay statistics and do not always equal current catch-up time. When the primary is idle, values can become NULL or stop updating.

### 15.5. pg_stat_wal_receiver

On a standby, this view reports WAL receiver status, sender host, written/flushed LSNs, and latest end LSN. A row exists only when the receiver is active in an appropriate state.

### 15.6. Replication role

Use `pg_is_in_recovery()` to detect whether each instance is primary or standby. Because roles flip during failover, dashboards should track dynamic roles.

### 15.7. Replication slots

Monitor `restart_lsn`, `wal_status`, `active`, and retained WAL. Slots protect WAL for slow consumers, yet can fill the primary disk if unmonitored or uncapped.

## 16. WAL Generation and Archiving

### 16.1. pg_stat_wal

`pg_stat_wal` reports WAL records, full-page images, bytes, writes, syncs, and I/O timings depending on version.

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

### 16.2. WAL bytes rate

When the exporter exposes a WAL bytes counter, apply `rate()` to track WAL generation speed and compare against hourly/daily baselines.

### 16.3. Full-page images

Full-page image rates can surge after checkpoints or workload shifts. Track WAL bytes and FPIs together.

### 16.4. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

### 16.5. Archive failures

Rising `failed_count` signals `archive_command` errors. Inspect logs, destination disk, credentials, network, and write permissions.

### 16.6. Archive age

Track time since `last_archived_time` alongside WAL generation. An aging timestamp during an idle period is not automatically an error; correlate with WAL activity.

### 16.7. Do not count only segment files

An archive holding many old files can still miss the latest required segments. Verify continuity and backup/restore chains separately.

## 17. Vacuum, Dead Tuples, and Table Health

Vacuum maintains MVCC cleanup and transaction ID health. Exporters help surface table churn and lagging vacuum jobs.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 17.1. Dead tuples

`n_dead_tup` is an estimate. Sustained growth suggests autovacuum is lagging or an old transaction horizon pins dead tuples.

### 17.2. Live/dead trends

Track trends per table and database. One large snapshot does not prove bloat because counts are statistical estimates that shift after analyze or vacuum.

### 17.3. Autovacuum timestamps

`last_autovacuum` and `last_autoanalyze` show the most recent statistics-recorded runs.

### 17.4. Vacuum progress

`pg_stat_progress_vacuum` exposes live progress of active vacuum jobs, distinguishing jobs that haven't started, are running smoothly, or cannot keep up.

### 17.5. Table size

Pair `pg_total_relation_size` with filesystem metrics to track growth. Scraping full relation size inventories too frequently adds overhead; scrape them less often or in a separate job.

### 17.6. Transaction ID age

Monitor `age(datfrozenxid)` and database freeze risk. This is a critical availability/capacity signal because transaction ID wraparound can force PostgreSQL into protective shutdown.

### 17.7. Vacuum dashboard

Display dead tuple estimates, autovacuum recency, vacuum progress, transaction ID age, and table growth grouped by database.

## 18. Index Usage and Table Scans

### 18.1. pg_stat_user_indexes

This view provides `idx_scan`, `idx_tup_read`, and `idx_tup_fetch` per index.

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 30;
~~~

### 18.2. Unused indexes

Low `idx_scan` does not prove an index is useless. An index may serve rare critical queries or enforce uniqueness/constraints.

### 18.3. Sequential scans

High `seq_scan` counts can be legitimate for small tables or analytical scans. Evaluate against table size, rows fetched, and query plans.

### 18.4. Index write overhead

Every index adds `INSERT`/`UPDATE`/`DELETE` cost and disk usage. Weigh read benefits against write amplification.

### 18.5. Statistics resets

Index counters reset on stats resets or after restore/restart. Never drop an index based solely on a short post-reset window.

## 19. Query Metrics with pg_stat_statements

`pg_stat_statements` aggregates statistics across executed SQL statements.

### 19.1. Extension setup

On most setups, add `pg_stat_statements` to `shared_preload_libraries` and restart the server before running `CREATE EXTENSION` inside the target databases.

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 19.2. Useful fields

- `calls`: execution count.
- `total_exec_time`: cumulative execution duration.
- `mean_exec_time`: average duration per call.
- `rows`: rows returned or modified.
- `shared_blks_hit`/`read`: buffer accesses.
- `temp_blks_read`/`written`: temporary block I/O.
- `plans`/planning time: available depending on configuration and version.

### 19.3. Top total time

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 19.4. Top mean latency

Sort by `mean_exec_time` to find slow-per-call queries. Pair with `calls`; a rare slow query and a slightly slow query running millions of times carry very different operational impacts.

### 19.5. Top calls

Queries with huge `calls` can dominate total CPU even with low per-call latency. Evaluate `calls`, `total_exec_time`, and `mean_exec_time` together.

### 19.6. Query text and privacy

Query text can expose data or sensitive schema details depending on parameterization. Never put raw queries into Prometheus labels; rely on access-controlled dashboards or expose only `queryid`/fingerprints.

### 19.7. Resetting pg_stat_statements

Statistics can be reset. Record reset timestamps and avoid comparing windows across mismatched baselines.

## 20. Custom Queries in postgres_exporter

Default collectors do not always emit every metric a dashboard needs. `postgres_exporter` supports custom query configurations depending on version.

### 20.1. When are custom queries needed?

- Application-specific business metrics.
- Connection counts by state.
- Replication gaps in bytes.
- Table-level metrics scoped to specific schemas.
- SLO or business metrics sourced directly from the database.

### 20.2. Design principles

Custom queries should:
- Run fast with predictable execution plans.
- Return a stable set of columns and types.
- Use labels with bounded value sets.
- Never return raw SQL, user identifiers, or PIDs as labels.
- Read only required views or tables.
- Require minimal explicit permissions.
- Be tested against production-like data volumes.

### 20.3. Session count query example

An aggregate query grouping backends by database and state:

~~~sql
SELECT
    COALESCE(datname, 'shared') AS datname,
    state,
    count(*)::bigint AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state;
~~~

### 20.4. Query configuration file example

Custom query file format depends on `postgres_exporter` version. A typical YAML definition looks like:

~~~yaml
pg_app_sessions:
  query: |
    SELECT
      COALESCE(datname, 'shared') AS datname,
      state,
      count(*)::bigint AS sessions
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
    GROUP BY datname, state
  metrics:
    - datname:
        usage: "LABEL"
        description: "Database name"
    - state:
        usage: "LABEL"
        description: "Backend state"
    - sessions:
        usage: "GAUGE"
        description: "Current client sessions"
~~~

Verify the custom query schema against your exact exporter version. Never copy configs from another release without validating.

### 20.5. Loading the query file

Some versions use a flag or environment variable such as `--extend.query-path` to point to the query file. Check `--help` for exact flag names and restart/reload the exporter as supported.

### 20.6. Metric naming

Final metric names follow exporter naming conventions and may add prefixes. Inspect `/metrics` to verify exact names, `# HELP`, `# TYPE`, and labels.

### 20.7. Test custom queries independently

Execute the SQL directly as the monitoring role. Measure latency and verify NULL handling, row counts, and permissions before adding it to the scrape path.

## 21. Designing Safe Custom Metrics

### 21.1. Aggregate instead of row-level

Emitting one series per session state total is far better than emitting one series per PID.

### 21.2. Label dimensions

`database`, `state`, application class, or replication `application_name` are good labels when values are bounded and stable.

### 21.3. Avoid raw query labels

Query text varies endlessly, may leak secrets, and explodes cardinality. Use `queryid` or bounded query groups if needed.

### 21.4. Avoid user_id/customer_id

Business identifiers can span millions of values. Never make them metric labels; aggregate into bounded cohorts at the appropriate tier.

### 21.5. Avoid PID and transaction ID

PIDs and transaction IDs churn constantly, creating endless stale series. Keep them in live diagnostic tools rather than long-term time-series labels.

### 21.6. Scrape cost

Custom queries run on every scrape. Heavy full-table/index inventories should run on longer scrape intervals or in separate jobs.

### 21.7. Timeouts

Enforce an appropriate `statement_timeout` on the monitoring role or custom query connection where supported. A metrics query must never hang and pin connections indefinitely.

## 22. Prometheus Scrape Configuration

Prometheus scrape config defines jobs, targets, intervals, timeouts, and labels.

~~~yaml
scrape_configs:
  - job_name: postgresql
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets:
          - db-a.internal:9187
          - db-b.internal:9187
        labels:
          cluster: orders-prod
          environment: production
~~~

### 22.1. Job name

`job_name` groups targets of the same type. Split jobs by environment or role if discovery or policy demands it.

### 22.2. Scrape interval

30 seconds is an example. Choose based on detection latency requirements, scrape cost, and target count.

### 22.3. Scrape timeout

`scrape_timeout` must be less than or equal to `scrape_interval`. If an exporter responds too slowly, Prometheus logs a scrape failure and marks the target down.

### 22.4. Static configs

Static target lists work well for small deployments or fixed node addresses.

### 22.5. Service discovery

In cloud, Kubernetes, or dynamic environments, use service discovery so targets update automatically without manual config edits.

### 22.6. Relabeling

Relabeling standardizes `cluster`, `environment`, `region`, `role`, and `instance` labels. Ensure identical databases consistently carry matching labels.

### 22.7. External labels

`external_labels` identify the Prometheus server/cluster when shipping to remote storage or federation. Do not confuse them with target labels.

### 22.8. Inspecting target status

The Prometheus Targets UI shows whether each endpoint scraped cleanly, last scrape duration, and any recent error.

## 23. Service Discovery and Multiple PostgreSQL Instances

### 23.1. One exporter per instance

A common pattern pairs one exporter endpoint with each PostgreSQL instance, keeping metric provenance clear and avoiding single-exporter bottlenecks.

### 23.2. Centralized exporter

A single exporter can connect to multiple instances or databases in certain setups. This reduces process count at the cost of a central choke point and trickier credential/discovery management.

### 23.3. Kubernetes

In Kubernetes, exporters run as sidecars or dedicated deployments. Prometheus Operator typically discovers them via `ServiceMonitor` or `PodMonitor`, with schemas and labels governed by CRD version.

### 23.4. Stable labels

Use `cluster`, `environment`, `service`, and `instance`. Standardize label names across Prometheus, Grafana, and alert rules.

### 23.5. Primary/standby roles

Roles flip during failovers. Derive roles dynamically from PostgreSQL state rather than hardcoding a hostname as `primary` permanently.

### 23.6. Failover endpoints

Even if application traffic moves to a new primary via a virtual IP or DNS, monitoring must keep scraping each individual node to observe both the old and new nodes.

### 23.7. Duplicate scraping

Avoid scraping the same exporter across multiple jobs with different labels unintentionally. Duplicate series double-count dashboards and waste storage.

## 24. Labels and Cardinality

Cardinality is the total count of unique time series. It directly drives Prometheus RAM, CPU, disk, and query latency.

### 24.1. Cardinality multiplies across combinations

A metric spanning 5 clusters, 10 instances, 20 databases, and 6 states expands multiplicatively across all label combinations.

### 24.2. Stable labels

Good labels include:
- `cluster`
- `environment`
- `instance`
- `region`
- `database` name when database count is bounded
- `application_name` when standardized and bounded

### 24.3. High-cardinality labels

Avoid:
- raw SQL / query text
- PID
- transaction ID
- user/customer ID
- request ID
- varying file paths
- arbitrary client IP addresses on high-fanout workloads

### 24.4. Label churn

Continuously changing label values constantly mint new time series while old ones linger until retention and compaction expire them.

### 24.5. Metric design review

Before adding a custom metric, estimate maximum distinct values per label and total resulting series across all targets and scrape intervals.

### 24.6. Do not stuff metadata into labels

For detailed object inventories, store metadata in an inventory system or query diagnostic tables on demand. Metrics should focus on actionable operational aggregates.

## 25. PromQL Basics for PostgreSQL

PromQL queries scraped time series.

### 25.1. Instant vector

Retrieves the latest value of a metric:

~~~promql
pg_up
~~~

### 25.2. Range vector

Retrieves samples across a time window:

~~~promql
pg_stat_database_xact_commit[5m]
~~~

### 25.3. Rate

Use `rate()` on counters to calculate average per-second rate:

~~~promql
rate(pg_stat_database_xact_commit[5m])
~~~

### 25.4. Increase

Use `increase()` to estimate total increase over a window:

~~~promql
increase(pg_stat_database_deadlocks[1h])
~~~

### 25.5. Sum by

Aggregate across cluster and database:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

### 25.6. Max by

Find the worst instance:

~~~promql
max by (cluster, instance) (
  pg_exporter_scrape_duration_seconds
)
~~~

Verify example metric names against your running exporter.

### 25.7. Clamp

`clamp_min()` and `clamp_max()` prevent division by zero or bound displayed values.

### 25.8. Absent

`absent()` detects missing series, though target availability alerts are usually better built on Prometheus's built-in `up` metric and service discovery state.

## 26. Rates, Counter Resets, and PostgreSQL Statistics

### 26.1. Counter resets

PostgreSQL statistics reset on server/database restarts, explicit stats-reset calls, or version-specific events. Restarting the exporter process can also reset process-local metrics.

### 26.2. Apply rate before aggregating

For counters across multiple instances, compute `rate()` per series before `sum()` so Prometheus handles counter resets properly per series:

~~~promql
sum by (cluster) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

### 26.3. Never apply rate() to gauges

Connection counts, dead tuple estimates, and current lag are gauges. Never wrap them in `rate()` unless intentionally measuring rate of change.

### 26.4. Scrape gaps

When scrapes fail or drop, `rate()` and `increase()` lose precision or miss data. Display target availability alongside workload graphs.

### 26.5. Stats reset markers

Track `stats_reset` in PostgreSQL. Good dashboards annotate restarts and stats resets to explain sudden step changes.

### 26.6. Workload baselines

Transaction rates and I/O follow daily and weekly rhythms. Base alerts on baselines, SLOs, and impact rather than a single static threshold across all hours.

## 27. PostgreSQL Overview Dashboard

An overview dashboard should answer immediately: is the instance up, what is current load, and are any dangerous trends emerging?

### 27.1. Stat panels

Include stat panels for:
- PostgreSQL availability.
- Exporter scrape health.
- Instance role: primary vs. standby.
- Current connections and utilization.
- Transaction rate.
- Replication lag / bytes behind.
- Free disk space.
- WAL archive failures.
- Deadlocks in the recent window.

### 27.2. Time series panels

Display:
- Transaction commit and rollback rates.
- Active, idle, and waiting sessions.
- Block reads and hits.
- WAL bytes per second.
- Replication receive and replay progress.
- Dead tuple trends.
- Disk latency and filesystem usage.

### 27.3. Table panels

Use tables for:
- Top databases by transaction rate.
- Top tables by dead tuple estimates.
- Replicas by state and lag.
- Top query fingerprints by total execution time.

### 27.4. Variables

Dashboard variables filter by cluster, instance, database, and environment. Avoid dropdown variables with tens of thousands of entries.

### 27.5. Thresholds

Tie threshold colors to operational policy. Never color a huge cumulative counter red without converting to a rate or comparing against baseline.

### 27.6. Panel descriptions

Document units, metric sources, formulas, and caveats. On-call engineers must immediately know whether a number represents bytes, seconds, a ratio, or a cumulative count.

## 28. Workload and Connections Dashboard

### 28.1. Transaction throughput

Plot commit and rollback rates by database, and compare against application-layer request rates.

### 28.2. Session states

Stacked time series for `active`, `idle`, `idle in transaction`, and other states, using consistent state label definitions.

### 28.3. Connection utilization

Plot current connections, `max_connections`, and reserved capacity, with low-headroom warnings.

### 28.4. Wait events

Group by `wait_event_type` to spot `Lock`, `IO`, `Client`, `LWLock`, and other categories. Exact event names depend on PostgreSQL version.

### 28.5. Long-running transactions

Diagnostic table listing query age, transaction age, `application_name`, and wait events. Restrict query text visibility to authorized roles.

### 28.6. Connection pools

Include application-side pool metrics alongside database metrics. PostgreSQL cannot see requests queued inside application pools.

## 29. Cache, I/O, and Query Performance Dashboard

### 29.1. Cache hit ratio

Show hit ratio alongside absolute block read rates. Never judge performance from a single standalone percentage.

### 29.2. Disk throughput

Combine `node_exporter` disk metrics with `pg_stat_io` or database block reads.

### 29.3. Query total time

Use `pg_stat_statements` to highlight query fingerprints consuming the most cumulative execution time.

### 29.4. Mean latency

Display mean execution time alongside `calls`. For full latency distributions, use application histograms/instrumentation rather than mean alone.

### 29.5. Temp I/O

Rising temp bytes/files signal spills. Correlate with queries, `work_mem`, and disk capacity.

### 29.6. Index usage

Use table panels to spot rarely scanned indexes without dropping them blindly from dashboard numbers alone. Verify constraints and long-term workloads first.

### 29.7. Query plans

Dashboard metrics point you where to look. Run `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment to inspect execution plans.

## 30. Replication and HA Dashboard

### 30.1. Role

Display `pg_is_in_recovery` state per instance, reflecting role flips after promotions.

### 30.2. Sender state

On the primary, display `state`, `sync_state`, and sent/write/flush/replay LSNs for every standby.

### 30.3. Replay gap

Display bytes behind. If estimating lag seconds, derive it from WAL generation rates or metrics with clear semantics rather than guessing from a raw LSN gap alone.

### 30.4. Receiver state

On standbys, display receiver status, sender host, and `latest_end_lsn`.

### 30.5. Synchronous replication

Show `sync_state` and healthy synchronous standby counts against quorum policy.

### 30.6. Replication slots

Show `active`, `restart_lsn`, `wal_status`, and estimated retained WAL. Alert when slots retain excessive WAL or approach invalidation.

### 30.7. Timelines

Role/replication dashboards do not replace timeline history checks during failovers. Track timelines and system identifiers in incident tooling or inventories.

### 30.8. Standby conflicts

For hot standby read workloads, monitor `pg_stat_database_conflicts` and replay lag to catch query cancellations caused by recovery.

## 31. Vacuum, Storage, and Capacity Dashboard

### 31.1. Database size

Track database sizes over time. Because size queries can be expensive across thousands of objects, use longer scrape intervals.

### 31.2. Table growth

Track top tables and indexes by size and growth rate, annotating application releases to explain schema changes.

### 31.3. Dead tuples

Display per-table and per-database estimates and multi-scrape trends.

### 31.4. Autovacuum activity

Track `last_autovacuum`, vacuum progress, active autovacuum workers, and transaction ID age.

### 31.5. Freeze age

Set alerts aligned with `autovacuum_freeze_max_age` and operational policy—never wait until right at the emergency limit.

### 31.6. Disk capacity

Pull filesystem usage from `node_exporter` or host monitoring. Database size alone does not show remaining filesystem free space.

### 31.7. WAL disk

Monitor `pg_wal` directory usage, replication slots, archive queues, and free disk space. WAL retention climbs rapidly when standbys or consumers lag.

## 32. Alerting: From Metrics to Action

Dashboards help operators explore data; alerts surface conditions demanding action.

### 32.1. Alert conditions

An alert rule defines an expression, pending `for` duration, labels, and annotations.

### 32.2. Severity

Use severities such as `warning` and `critical` mapped to impact and expected response urgency.

### 32.3. For duration

Include `for:` clauses to filter out meaningless transient spikes, sized to required detection speed.

### 32.4. Annotations

Alerts should include `summary`, `description`, `instance`, `cluster`, and an internal runbook URL/path.

### 32.5. Alertmanager

Alertmanager groups related instance alerts into single incidents, routes by cluster/team/severity, and handles maintenance silences.

### 32.6. Alert quality

Every alert needs an owner, a next action, and clear false-positive criteria. Ownerless alerts without runbooks quickly get ignored.

## 33. Illustrative Alert Rules

Exact metric names must be verified against your exporter version. The rules below illustrate structure and must be adapted for your environment.

~~~yaml
groups:
  - name: postgresql-availability
    rules:
      - alert: PostgreSQLExporterTargetDown
        expr: up{job="postgresql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL exporter target is unreachable"
          description: "Prometheus cannot scrape this exporter endpoint."

      - alert: PostgreSQLDatabaseUnavailable
        expr: pg_up{job="postgresql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Exporter cannot collect PostgreSQL metrics"
          description: "Check database connectivity, authentication and exporter logs."
~~~

### 33.1. Exporter target down

Built-in `up == 0` means Prometheus failed to scrape the exporter endpoint due to exporter process failure, network, TLS, or scrape timeout.

### 33.2. Database unavailable

If Prometheus scrapes the exporter cleanly yet `pg_up == 0`, the issue lies in exporter-to-PostgreSQL connectivity or the database itself.

### 33.3. Deadlocks

Example alert when deadlock rate exceeds zero over a meaningful window. Verify exact metric names and types first.

~~~yaml
      - alert: PostgreSQLDeadlocksDetected
        expr: increase(pg_stat_database_deadlocks[10m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL deadlocks detected"
          description: "Review database logs and transaction lock ordering."
~~~

### 33.4. Connection saturation

Alert on connections relative to `max_connections` minus reserved capacity. Emit a dedicated ratio metric if the exporter does not expose `max_connections` with matching labels.

### 33.5. Replication lag

Alert on bytes behind or a clearly defined lag metric, with thresholds tied to RPO and WAL generation rate.

### 33.6. Archive failures

Track deltas of `failed_count` or `last_failed_time`. An old cumulative counter must not keep firing alerts after the underlying error is fixed.

### 33.7. Disk space

Alert on node filesystem free space and growth forecasts. Running out of disk threatens the entire cluster.

## 34. Recording Rules and Dashboard Efficiency

### 34.1. Recording rules

Recording rules precompute frequently used PromQL expressions into new time series so dashboards load fast without re-evaluating heavy queries every view.

~~~yaml
groups:
  - name: postgresql-recording
    interval: 30s
    rules:
      - record: cluster:postgresql_commits_per_second:rate5m
        expr: |
          sum by (cluster, datname) (
            rate(pg_stat_database_xact_commit[5m])
          )
~~~

### 34.2. Reuse shared definitions

Dashboards, alerts, and SLOs can query the same recording metric, keeping panel math consistent.

### 34.3. Do not record everything

Recording rules add stored series. Create them only for expressions queried repeatedly.

### 34.4. Rule evaluation

Align evaluation intervals with scrape intervals and alert latency targets. Do not evaluate alerts faster than data can meaningfully refresh.

### 34.5. Testing rules

Validate syntax with `promtool check rules` and write rule unit tests where supported, testing no-data, counter resets, and label matching.

## 35. Securing the Monitoring Stack

Metrics are not always harmless. They can reveal database names, usernames, application names, query fingerprints, topology, and operational details.

### 35.1. Monitoring role

Use a dedicated role, `pg_monitor` where appropriate, and minimal `SELECT` grants for custom queries.

### 35.2. Network isolation

Allow only Prometheus to reach exporter endpoints. Never expose `/metrics` to the public internet.

### 35.3. TLS and authentication

Protect exporter endpoints using private networks, TLS, authentication, or reverse proxies per threat model. Configure Prometheus to verify TLS certificates when scraping HTTPS.

### 35.4. Secret storage

Store database passwords in secret managers, protected files, or orchestration secrets. Never commit credentials to Git or Grafana dashboard JSON.

### 35.5. Grafana access

Scope dashboard and data source access by team. Restrict Explore access if users could query sensitive telemetry.

### 35.6. Query text

Never export raw SQL or bind values as labels. Where query text is shown, restrict viewer permissions and apply masking.

### 35.7. Auditing

Track who modifies scrape configurations, dashboards, alert rules, credentials, and access policies.

## 36. Monitoring the Exporter and Monitoring Stack

The monitoring system itself must be monitored.

### 36.1. Prometheus up

Monitor the Prometheus process, scrape durations, scraped sample counts, TSDB head series, and disk usage.

### 36.2. Exporter scrape duration

Climbing scrape durations signal slow custom queries, heavy database load, or network latency.

### 36.3. Scrape samples

Sudden jumps in scraped sample counts suggest cardinality explosions or newly enabled collectors.

### 36.4. Scrape errors

Track target `up` status, scrape errors, timeouts, and exporter logs.

### 36.5. Grafana availability

Empty dashboards can stem from Grafana, data sources, Prometheus, or exporters. Monitor each component independently.

### 36.6. Alert delivery

Monitor Alertmanager notification pipelines, receiver health, retries, and active silences. Never assume an alert page went out just because a Prometheus rule fired.

### 36.7. Backing up monitoring configuration and data

If Prometheus drives SLOs or audits, define retention, remote storage, backup, and restore strategies for the monitoring stack itself.

## 37. PostgreSQL and Exporter Version Differences

Available metrics depend on PostgreSQL version, exporter version, enabled collectors, and role privileges.

### 37.1. Changing statistics views

Columns and views are added, renamed, or split across major versions—for example, I/O statistics and checkpoint/background writer stats.

### 37.2. PostgreSQL 16 and later

`pg_stat_io` exists from PostgreSQL 16 onward. Do not query it on older servers without version-compatibility handling.

### 37.3. Checkpoint statistics

Newer versions split checkpoint statistics out of several fields previously in `pg_stat_bgwriter`. Check exact views and columns on your running major version.

### 37.4. Exporter compatibility

Exporters ship version-specific collectors and varying metric names. Never import a dashboard built for another exporter release without verifying metric names.

### 37.5. Feature detection

Inspect view schemas via `information_schema` or system catalogs and maintain version-specific custom queries via a compatibility matrix.

### 37.6. Version labels

Track PostgreSQL versions and exporter versions in inventories/metadata, or emit an info metric if supported by the exporter.

## 38. Troubleshooting Metrics and Dashboards

### Issue 1. Prometheus target down

Check the exporter process, listening port, network, firewall, TLS, DNS, and scrape timeout.

### Issue 2. Exporter running yet pg_up equals 0

Check DSN, database role, `pg_hba.conf`, password, SSL settings, and PostgreSQL availability.

### Issue 3. /metrics endpoint returns query errors

Check exporter logs, failing collectors, PostgreSQL permissions, and custom query compatibility.

### Issue 4. Missing metrics

Verify the collector is enabled, supported by the exporter version, backed by a matching view on that PostgreSQL version, and scraping without errors.

### Issue 5. Metric names differ from dashboard

Inspect `/metrics` directly and update PromQL/dashboards to match actual `# HELP`/`# TYPE` output rather than guessing names from old blogs or templates.

### Issue 6. Dashboard shows No data

Check time range, data source selection, PromQL syntax, label filters, metric existence, target status, and scrape health.

### Issue 7. Counter values drop to zero

Check for PostgreSQL restarts, stats resets, exporter restarts, or target label shifts. Use `rate()` and reset-aware analysis.

### Issue 8. Cache hit ratio is NaN

No block accesses occurred in the window or the denominator was zero. Use `clamp_min` and display “No traffic” when idle.

### Issue 9. Scrape timeouts

Optimize custom query cost, split heavy collectors, raise timeouts within `scrape_interval` bounds, or reduce target load.

### Issue 10. PostgreSQL load rises after enabling the exporter

Count exporter connections and query frequencies. Disable unneeded collectors, lengthen scrape intervals, or move inventory queries to slower jobs.

### Issue 11. Cardinality spikes

Find which metric/label produces excessive series, remove PIDs, raw SQL, or user IDs, and pre-aggregate before exporting.

### Issue 12. Alerts keep re-firing after remediation

Check rule expressions, `for` durations, counter resets, stale series, label matching, and Alertmanager grouping/inhibition.

### Issue 13. Replication dashboard missing standbys

Check exporter targets on standbys, `pg_stat_wal_receiver`, primary `pg_stat_replication`, and service discovery rules.

### Issue 14. Lag metrics stay unchanged while primary is idle

Time-lag fields can stay NULL or frozen without fresh WAL writes. Rely on LSN byte gaps and workload context.

### Issue 15. Table metrics missing a database

Check database discovery, connection permissions, collector configuration, and multi-database scraping setup.

### Issue 16. Query text exposing sensitive data

Strip query text from labels and broad dashboards, tighten permissions, and adjust custom collectors.

### Issue 17. Exporter password expired

Check secret rotation, exporter restart/reload behavior, and PostgreSQL authentication logs.

### Issue 18. Slow Grafana panels

Optimize PromQL, trim cardinality, add recording rules, lower query resolution, or bound dashboard variables.

### Issue 19. Prometheus disk filling up

Check retention, scrape volume, WAL/TSDB compaction, remote storage, and filesystem capacity.

### Issue 20. Metric resets triggering false alerts

Base alerts on `rate()`/`increase()` and reset-aware queries; add `for` durations and check reset timestamps.

## 39. Monitoring Deployment Workflow

~~~text
Inventory
   |
   v
Create monitoring role
   |
   v
Install postgres_exporter
   |
   v
Configure DSN / TLS / secret
   |
   v
Test database access
   |
   v
Inspect /metrics
   |
   v
Configure Prometheus target
   |
   v
Verify scrape and labels
   |
   v
Build Grafana dashboards
   |
   v
Add alert rules / Alertmanager
   |
   v
Validate against SQL and incident scenarios
   |
   v
Document ownership and runbooks
~~~

### 39.1. Inventory

Catalog clusters, instances, primary/standby roles, databases, PostgreSQL versions, exporter versions, and network boundaries.

### 39.2. Role and connectivity

Create the monitoring role, grant `pg_monitor` or required least privileges, and verify TLS and `pg_hba.conf`.

### 39.3. Exporter

Install the exporter, configure secrets, select collectors, set listen addresses, and configure service supervision.

### 39.4. Endpoint validation

Verify `/metrics`, scrape duration, database connectivity, and expected metric families.

### 39.5. Prometheus

Configure scrape jobs or service discovery, labels, scrape intervals, timeouts, and retention.

### 39.6. Grafana

Configure data sources, dashboard variables, panels, units, thresholds, and descriptions.

### 39.7. Alerting

Define alert rules, routes, receivers, grouping, silence policies, and runbook links.

### 39.8. Acceptance testing

Cross-check metrics against direct SQL queries, simulate exporter stops or connection failures in a lab, and verify end-to-end alert delivery.

### 39.9. Handover

Document owners, escalation paths, secret rotation, upgrade cadence, and troubleshooting steps.

## 40. Daily Operations Runbook

1. Check Prometheus targets and scrape errors.
2. Check exporter availability and PostgreSQL connection health.
3. Verify primary/standby roles and replication states.
4. Review connection utilization and active/waiting sessions.
5. Review transaction rates, rollback rates, and deadlocks.
6. Review WAL generation, archive failures, and replication slot retention.
7. Review replication receive and replay lag.
8. Review dead tuples, autovacuum recency, and transaction ID age.
9. Review database filesystem free space and WAL directory usage.
10. Check firing/pending alerts, active silences, and notification delivery.
11. Note major deviations from baselines.
12. Investigate anomalous metrics using SQL, logs, and OS metrics.
13. Document incidents, root causes, impacts, and remediations.
14. Re-verify dashboards and alerts after configuration changes.

## 41. Practice Exercises

Use a PostgreSQL lab and isolated monitoring stack. Never deliberately exhaust disks, kill production exporters, or induce heavy production load just to test alerts.

### Exercise 1. Architecture

Describe the roles of `postgres_exporter`, Prometheus, and Grafana.

### Exercise 2. Alertmanager

What does Alertmanager do after Prometheus fires an alert?

### Exercise 3. Node exporter

Why does `postgres_exporter` not replace `node_exporter`?

### Exercise 4. Metrics

Distinguish metric, sample, and time series.

### Exercise 5. Labels

Which labels are well suited for classifying clusters and instances?

### Exercise 6. Cardinality

Why should PID and raw SQL not be used as metric labels?

### Exercise 7. Monitoring role

Which SQL statements create an exporter role and grant `pg_monitor`?

### Exercise 8. Superuser

Why should superuser not be used for exporter credentials?

### Exercise 9. DSN

What details does a PostgreSQL DSN require?

### Exercise 10. Endpoint

What is the standard metrics endpoint of `postgres_exporter`?

### Exercise 11. Scraping

Does Prometheus actively scrape targets, or do exporters push metrics to Prometheus in the standard model?

### Exercise 12. up

What does Prometheus metric `up == 0` indicate?

### Exercise 13. pg_up

How does `pg_up` differ from `up`?

### Exercise 14. Counters

Why apply `rate()` to a transaction commit counter?

### Exercise 15. Gauges

Is connection count a counter or a gauge?

### Exercise 16. Cache hits

State the reference formula for buffer hit ratio and one limitation of it.

### Exercise 17. Transactions

Which view provides per-database commits and rollbacks?

### Exercise 18. Activity

Which view provides backend states, wait events, and query start times?

### Exercise 19. Locks

Which function locates PIDs blocking a backend?

### Exercise 20. Replication

Which primary-side view exposes sent/write/flush/replay LSNs?

### Exercise 21. Receiver

Which standby-side view shows WAL receiver status?

### Exercise 22. WAL

Which view provides WAL records, bytes, and write statistics?

### Exercise 23. Archiver

Which view provides `archived_count` and `failed_count`?

### Exercise 24. Vacuum

Which view provides per-table dead tuple estimates?

### Exercise 25. Query statistics

Which extension provides aggregated query statistics?

### Exercise 26. Custom queries

List three design principles for custom exporter queries.

### Exercise 27. Scrape intervals

Why can an overly short scrape interval raise database load?

### Exercise 28. Timeouts

How must `scrape_timeout` relate to `scrape_interval`?

### Exercise 29. PromQL rate

Write a PromQL query computing 5-minute commit rate by database.

### Exercise 30. Recording rules

What benefits do recording rules provide?

### Exercise 31. Dashboards

Name five useful panels for an overview dashboard.

### Exercise 32. Alerts

Why should alerts include a `for` duration and a runbook?

### Exercise 33. Security

Name four controls to protect exporter endpoints and credentials.

### Exercise 34. Versions

Why verify metric names against exporter and PostgreSQL versions?

### Exercise 35. Stats resets

What can cause a counter to drop suddenly and affect computed rates?

### Exercise 36. No data

List troubleshooting steps when a Grafana panel displays `No data`.

### Exercise 37. Replication lag

Why does the `replay_lag` time field not always reflect current catch-up duration?

### Exercise 38. Cardinality

What consequences result from a custom query emitting PID and raw SQL as labels?

### Exercise 39. Monitoring validation

Describe how to validate exporter metrics against direct SQL queries.

### Exercise 40. Design

Design a monitoring stack for a cluster with one primary and two standbys, including key dashboards and alerts.

## 42. Reference Solutions

### Exercises 1–6. Architecture and metrics

`postgres_exporter` reads PostgreSQL statistics and exports metrics; Prometheus scrapes, stores, queries, and evaluates rules; Grafana renders dashboards; Alertmanager groups and routes notifications. `node_exporter` collects OS metrics. A metric names a quantity, a sample is a timestamped value, and a time series is a stream of samples sharing metric name and labels. Use `cluster`, `environment`, and `instance` labels. PIDs and raw SQL cause high cardinality, churn, and data exposure risks.

### Exercises 7–13. Role and scraping

~~~sql
CREATE ROLE postgres_exporter LOGIN PASSWORD 'replace-with-secret';
GRANT pg_monitor TO postgres_exporter;
~~~

Superuser grants overly broad privileges. A DSN needs host, port, database, user, authentication, and TLS parameters. The standard endpoint is `/metrics` on port 9187. Prometheus actively scrapes targets. `up=0` means scraping the endpoint failed; `pg_up=0` typically means the exporter failed to query PostgreSQL per exporter metric semantics.

### Exercises 14–18. Counters and activity

`rate()` turns cumulative counters into per-second rates. Connection count is a gauge. Reference hit ratio is `blks_hit/(blks_hit+blks_read)`, though `blks_read` does not strictly equal physical disk reads and the ratio misses other bottlenecks. `pg_stat_database` tracks commits/rollbacks; `pg_stat_activity` tracks backend states, waits, and query timings.

### Exercises 19–25. Locks, replication, and queries

`pg_blocking_pids(pid)` finds blockers. `pg_stat_replication` on the primary provides sent/write/flush/replay LSNs. `pg_stat_wal_receiver` runs on standbys. `pg_stat_wal` provides WAL stats. `pg_stat_archiver` provides archive counts. `pg_stat_user_tables` provides dead tuple estimates. `pg_stat_statements` provides aggregated query stats.

### Exercises 26–30. Custom queries and PromQL

Custom queries should be fast, read-only, return stable schemas, and use bounded labels. Overly short scrape intervals raise query and connection overhead. `scrape_timeout` must be less than or equal to `scrape_interval`. Example:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

Recording rules precompute frequent queries for shared use across dashboards and alerts, reducing repeated query load.

### Exercises 31–35. Dashboards and security

Overview panels cover availability, exporter health, connections, transaction rate, replication lag, disk free space, and deadlocks. Alerts need `for` durations to filter spikes and runbooks to guide action. Secure with network isolation, TLS, secret managers, least-privilege roles, Grafana RBAC, and avoiding raw SQL labels. Metric names vary by version, so verify `/metrics`. Restarts and stats resets can drop counters back toward zero.

### Exercises 36–40. Troubleshooting and design

`No data`: verify time range, data source, PromQL, labels, metric existence, Prometheus target health, and exporter logs. `replay_lag` reflects recent delay statistics and can go NULL or freeze when the primary is idle; cross-check LSNs. PID/raw SQL labels create series churn/cardinality and leak sensitive data. Validate by running equivalent SQL as the monitoring role and comparing timestamps, units, labels, counter/gauge semantics, and reset timestamps.

For one primary and two standbys, deploy exporters on all three nodes, scrape with `cluster`/`instance`/`environment` labels, add `node_exporter` per host, build overview/workload/replication/vacuum/storage dashboards, and alert on exporter/database down, connection saturation, deadlocks, replication lag, slot retained WAL, archive failures, low disk space, and transaction ID age. Track roles dynamically via `pg_is_in_recovery()` and test failovers to confirm dashboards recognize the new primary.

## 43. Quick Reference Table

| Need | Source / Tool |
| --- | --- |
| Export PostgreSQL metrics | `postgres_exporter` |
| Scrape and store time series | Prometheus |
| Dashboards and Explore | Grafana |
| Alert grouping and routing | Alertmanager |
| OS metrics | `node_exporter` |
| Database commits/rollbacks | `pg_stat_database` |
| Backend state and waits | `pg_stat_activity` |
| Blocking PIDs | `pg_blocking_pids()` |
| Locks | `pg_locks` |
| Replication sender | `pg_stat_replication` |
| WAL receiver | `pg_stat_wal_receiver` |
| WAL generation | `pg_stat_wal` |
| WAL archiving | `pg_stat_archiver` |
| Table statistics | `pg_stat_user_tables` |
| Index statistics | `pg_stat_user_indexes` |
| Vacuum progress | `pg_stat_progress_vacuum` |
| Query aggregates | `pg_stat_statements` |
| I/O statistics | `pg_stat_io` (PostgreSQL 16+) |
| Exporter endpoint | `/metrics` |
| Prometheus target health | `up` |
| Database scrape health | `pg_up` (exporter metric; verify version) |
| Counter rate | `rate()` |
| Counter delta | `increase()` |
| Reusable PromQL | Recording rules |
| Rule validation | `promtool check rules` |

## 44. Exporter and Dashboard Implementation Checklist

1. Inventory clusters, instances, databases, and PostgreSQL major versions.
2. Record `postgres_exporter` versions and deployment models.
3. Create a dedicated monitoring role.
4. Grant `pg_monitor` or equivalent least privilege for your version.
5. Never use superuser for the exporter.
6. Configure DSNs/secrets through a secure secret mechanism.
7. Enforce TLS and verify server identity properly.
8. Restrict network access to the exporter endpoint.
9. Select only needed collectors and measure scrape durations.
10. Audit custom query permissions and execution costs.
11. Avoid PID, raw SQL, and user IDs as labels.
12. Inspect `/metrics`, `# HELP`, and `# TYPE` metadata.
13. Configure Prometheus jobs, intervals, timeouts, and stable labels.
14. Verify Prometheus Targets and resolve scrape errors.
15. Scrape every instance individually to retain visibility across failovers.
16. Pair with `node_exporter` for CPU, RAM, disk, and network.
17. Configure Grafana data sources and bounded dashboard variables.
18. Build overview, workload, connection, I/O, replication, and vacuum panels.
19. Document units, metric semantics, and caveats in panel descriptions.
20. Use `rate()`/`increase()` for counters and gauge queries for point-in-time state.
21. Validate metrics directly against SQL.
22. Verify stats reset and server restart behavior.
23. Create alerts for exporter and database availability.
24. Create alerts for connection saturation, deadlocks, and blocking.
25. Create alerts for replication lag, slot retention, and archive failures.
26. Create alerts for disk capacity, WAL usage, and transaction ID age.
27. Add `for` durations, severities, owners, and runbooks to every alert.
28. Configure Alertmanager routing, grouping, silences, and test notifications.
29. Monitor Prometheus, Grafana, and Alertmanager health and storage.
30. Periodically audit cardinality, scrape load, and retention.
31. Re-verify dashboards after failovers and role changes.
32. Rotate credentials and audit access regularly.
33. Track versions, configs, and dashboard definitions in change control.
34. Consider monitoring complete only after end-to-end alert testing succeeds.

## 45. Summary

`postgres_exporter` translates PostgreSQL statistics into Prometheus metrics; Prometheus scrapes and stores time series; Grafana visualizes dashboards; and Alertmanager routes alerts. When combined with `node_exporter` and application metrics, teams connect database health directly to host resources and user-visible service behavior.

An effective metric set covers availability, connections, transactions, cache/I/O, locks, WAL, archiving, replication, vacuum, table/index growth, and query statistics. `pg_stat_database`, `pg_stat_activity`, `pg_stat_replication`, `pg_stat_wal_receiver`, `pg_stat_wal`, `pg_stat_archiver`, `pg_stat_user_tables`, and `pg_stat_statements` serve as core sources. Because views and metric names vary across PostgreSQL and exporter releases, inspect `/metrics` and verify directly with SQL.

Strong dashboards show operators current health, trends, headroom, and where to investigate. Strong alerts fire only on actionable conditions with suitable pending durations, owners, and runbooks. Never plot cumulative counters raw; apply `rate()`/`increase()` to counters, use accurate units for gauges, and track statistics resets.

The monitoring stack itself must also be secured and monitored. Enforce least-privilege roles, secret management, TLS/network isolation, Grafana access controls, and low-cardinality labels. Keep raw queries, PIDs, and business identifiers out of labels. Finally, cross-check metrics against SQL, test exporter and database failures, and verify the notification pipeline so dashboards and alerts perform reliably during real incidents.
