# Finalizing Dashboards, Alerts, and Runbooks for a PostgreSQL Practice Environment

A PostgreSQL practice environment becomes truly valuable only when learners can observe the system, recognize warning signs, and handle incidents following a repeatable workflow. Dashboards reveal what is happening; alerts notify when a metric demands attention; runbooks guide root-cause verification and service recovery.

All three components must share identical metric definitions and reflect the same operational model. For example, if a dashboard plots active connections while an alert counts idle sessions too, operators will get paged prematurely. If an alert warns a filesystem is nearly full but the runbook fails to identify which volume holds WAL, learners will struggle to diagnose the issue.

This practice establishes an observability and incident-response workflow for a PostgreSQL instance running in a lab environment. It applies equally to bare-metal PostgreSQL, Docker Compose, or VMs; exact metric names and exporter configuration must be verified against your deployed tool versions.

## 1. Objectives and Scope of the Practice Environment

A complete lab should help learners answer:

- Is PostgreSQL running and accepting connections?
- How are read/write load, transaction counts, and connection counts changing?
- Which queries are long-running, waiting on locks, or consuming heavy resources?
- Do RAM, CPU, I/O, and filesystem capacity remain sufficient?
- Are WAL, checkpoints, backups, and replication operating normally?
- During an incident, what evidence must be gathered, which actions taken, and how is recovery verified?

The baseline scope covers one PostgreSQL primary, one load-generating application, a metrics collector, a dashboard, and an alerting target. If your lab includes a standby, add replication metrics and a dedicated failover runbook. Do not include failover procedures in a generic runbook if the lab lacks primary/standby role management.

You can set tiered goals across three levels:

| Level | Target Outcomes |
|---|---|
| Basic | Health checks, connections, CPU, RAM, disk usage, and database-down alerts |
| Intermediate | Transaction rates, latency, wait events, deadlocks, WAL, backups, and scenario runbooks |
| Advanced | Replication lag, capacity forecasting, alert testing, noise reduction, and recovery drills |

You do not need to deploy every tool at once. Start with metrics tied to clear actions, then expand as learners master how data is collected and interpreted.

## 2. Reference Observability Architecture

A common stack uses PostgreSQL Exporter, Prometheus, and Grafana:

~~~mermaid
flowchart LR
    APP["Application / pgbench"] --> PG["PostgreSQL"]
    PG --> EXP["postgres_exporter"]
    EXP --> PROM["Prometheus"]
    NODE["node_exporter"] --> PROM
    PROM --> GRAF["Grafana Dashboard"]
    PROM --> RULE["Alert Rules"]
    RULE --> AM["Alertmanager / Grafana Alerting"]
    AM --> DEST["Lab notification channel"]
    GRAF --> OP["Learner / Operator"]
    OP --> RUN["Runbook"]
    RUN --> PG
~~~

Role of each component:

- PostgreSQL stores data and exposes statistics views such as `pg_stat_activity`, `pg_stat_database`, `pg_stat_replication`, and `pg_stat_wal`.
- `postgres_exporter` queries permitted statistics views and exports metrics for Prometheus to scrape.
- `node_exporter` exposes OS metrics such as CPU, RAM, filesystem usage, and disk I/O on Linux.
- Prometheus stores time series and periodically evaluates alert rules.
- Grafana renders dashboards and can manage alert rules, contact points, and notification policies.
- Alertmanager or Grafana Alerting groups, routes, and dispatches notifications.
- Runbooks document verification, mitigation, rollback, and recovery confirmation steps.

You can substitute cloud provider monitoring or existing metrics platforms. What matters is knowing where each metric originates, its scrape interval, whether counters reset, and collection delay.

### 2.1. Choosing Collection Intervals

For a lab, a 15–30 second scrape interval is usually enough to observe normal shifts. Shorter intervals increase sample counts, query overhead, and storage usage; longer intervals risk missing brief spikes. Pick an interval suited to learning goals and machine capacity.

Document explicitly:

- Prometheus scrape interval.
- Metrics retention period.
- PostgreSQL log retention period.
- Dashboard SQL refresh interval if running direct queries.
- Display time zone and timestamp conversion conventions.

Avoid setting ultra-short scrape intervals and assuming instantaneous accuracy. Many PostgreSQL statistics are cumulative counters; computing rates requires taking deltas across scrapes.

## 3. Preparing PostgreSQL Monitoring Privileges

Exporter and dashboard accounts require read-only statistics access. Never use an application or superuser account to scrape metrics.

Create a dedicated monitoring role:

~~~sql
CREATE ROLE monitoring LOGIN;
GRANT pg_monitor TO monitoring;
~~~

The built-in `pg_monitor` role grants read access to many monitoring views and functions. Exact privileges depend on your PostgreSQL version; check documentation for your version and grant additional permissions only with clear justification.

If the exporter authenticates via password, configure it securely and store it in a secret manager or restricted credential file. Never commit passwords into Git, dashboard JSON, URLs, lesson examples, or logs.

Core principles:

- Restrict monitoring account connections strictly to the exporter host or monitoring subnet.
- Enforce TLS across untrusted networks.
- Limit business data access; dashboards should not require `SELECT` on every application table merely to read system stats.
- Use separate credentials per environment.
- Rotate credentials regularly and verify exporter health afterward.
- Never grant write privileges, `CREATE`, or `SUPERUSER` to monitoring accounts.

Verify role and privileges:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_roles
WHERE rolname = 'monitoring';
~~~

If the exporter cannot read a specific view, inspect exporter logs and grants on that view. Never "fix" it by granting `SUPERUSER`.

## 4. Choosing Which Metrics to Track

A good dashboard focuses on metrics that inform operational decisions. Do not crowd every available metric onto a single screen.

### 4.1. Health and Availability

| Metric | Meaning | Operational Question |
|---|---|---|
| Exporter scrape success | Can Prometheus scrape the exporter? | Are metrics missing or is the database actually down? |
| PostgreSQL up/readiness | Is the instance accepting connections? | Should we inspect the service and startup logs? |
| Connection success | Do client login attempts succeed? | Is the failure in DNS, network, TLS, or auth? |
| Restart/start time | Last instance start timestamp | Did an unexpected restart occur? |
| Last successful backup | Most recent valid backup timestamp | Can we still recover within our RPO? |

Never equate an exporter scrape failure with PostgreSQL being down. The exporter itself may have crashed, lost network access, lacked permissions, or expired credentials while PostgreSQL continues serving traffic. Monitor both database endpoint reachability and collector health.

### 4.2. Workload and Connections

- Backend counts by state: `active`, `idle`, `idle in transaction`, and other states.
- Transaction commits and rollbacks per second.
- Active query counts and long-running query durations.
- Block hit/read rates and temporary file usage.
- Deadlock counts.
- Connection usage relative to `max_connections`.
- Wait events grouped by type and event name.

Total connections do not equal concurrently executing queries. A pool holds idle sessions ready for reuse; always plot `active`, `idle`, and `idle in transaction` separately.

### 4.3. Host Resources and Storage

- CPU utilization and VM CPU steal.
- Available RAM, swap usage, and OOM indicators.
- Filesystem available bytes and percentage used.
- Read/write IOPS, throughput, latency, and queue depth.
- Network throughput and connection errors.
- Directory sizes for data, WAL, logs, and local backups.

A nearly full filesystem is usually a more urgent risk than a brief CPU spike. Monitor filesystems hosting `PGDATA` and `pg_wal` separately whenever they live on distinct volumes.

### 4.4. PostgreSQL Maintenance and Reliability

- WAL bytes generated over time.
- Archive successes/failures and latest archive timestamp.
- Checkpoints and checkpoint write/sync durations.
- Replication state and write/flush/replay lag when standbys exist.
- Autovacuum and manual vacuum progress.
- Backup duration, backup age, and restore test status.
- Top query statistics from `pg_stat_statements`.

These metrics catch trouble before users experience errors, provided each links to a clear action. For instance, replication lag must be interpreted relative to standby role and RPO; a reporting standby tolerates different lag than a failover standby.

## 5. Collecting Metrics Directly from PostgreSQL

You can validate queries directly in SQL before wiring them into dashboards. The queries below target standard PostgreSQL statistics views; required permissions vary slightly by role and version.

### 5.1. Sessions by State and Wait Event

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY session_count DESC;
~~~

This breaks down client backends by database, user, application, state, and wait event. If many sessions sit in `idle in transaction`, check whether the application leaves transactions open too long. Never judge by count alone; inspect transaction age and impact on vacuum, locks, and resources.

### 5.2. Long-Running Queries

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    LEFT(query, 300) AS query_preview
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

`query_start` records when the current query began. A long-running query may be a legitimate analytical report; compare against baseline runtime, wait events, execution plan, and user impact. Be cautious with query text that might expose sensitive literals.

### 5.3. Transaction and Block Statistics

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY datname;
~~~

Counter fields accumulate monotonically since `stats_reset`. Never plot raw `xact_commit` as a throughput rate. Compute rates from deltas between samples or using Prometheus `rate()`. Whenever `stats_reset` shifts, begin a fresh measurement interval.

Reference buffer hit ratio:

~~~sql
SELECT
    datname,
    ROUND(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname IS NOT NULL;
~~~

This measures blocks found in `shared_buffers` relative to total blocks requested. It is not the full OS cache hit ratio, nor does it prove every `blks_read` hit physical disk. Always pair it with storage metrics and query latency.

### 5.4. Database and Table Sizes

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Largest tables in user schemas:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_indexes_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 20;
~~~

`pg_database_size` and `pg_total_relation_size` measure PostgreSQL object sizes. They do not replace filesystem metrics: volumes also hold WAL, logs, temp files, filesystem metadata, and potentially non-PostgreSQL files.

### 5.5. Tracking WAL and Archiver

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal;
~~~

`pg_stat_wal` is available on supporting PostgreSQL versions. Counters are cumulative; compute rates using deltas. Timing columns depend on `track_wal_io_timing` in your deployed version.

Archiver status:

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

A climbing `failed_count` warrants investigation. One failed archive attempt does not immediately stop the database, yet sustained failures cause unarchived WAL to accumulate until disk exhaustion.

### 5.6. Tracking Replication When Standbys Exist

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;
~~~

This view displays standbys currently connected to the primary. Zero rows means either the lab has no standby, the standby has not connected yet, or replication broke. Never enable replication alerts on a single-node lab.

`write_lag`, `flush_lag`, and `replay_lag` measure elapsed lag under active write load; when the primary is idle, they can show `NULL`. `replay_lag_bytes` compares current WAL position against `replay_lsn` to reveal un-replayed WAL volume, though interpret it alongside write throughput and connection status.

### 5.7. Tracking SQL Statement Statistics

If `pg_stat_statements` is installed and enabled:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    LEFT(query, 250) AS query_preview
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This view surfaces query patterns consuming the highest cumulative time, highest mean latency, or heavy temp disk spills. Exact column names and types vary slightly by version; verify view schema before embedding into dashboards.

Avoid exposing raw unredacted query text broadly if SQL statements may contain sensitive literals. Operational dashboards generally need only `queryid`, total time, call count, and sanitized previews.

## 6. Building Dashboards in Grafana

Maintain one overview dashboard and several topic-specific drill-down dashboards. Learners start at the overview, then drill down to the relevant page during root-cause analysis.

### 6.1. PostgreSQL Overview Dashboard

Recommended panel rows:

| Row | Panels | Visualization |
|---|---|---|
| Status | PostgreSQL up, exporter up, start time | Stat / status |
| Workload | Transactions/s, active sessions, connections | Time series |
| Queries | Long-running queries, wait events, deadlocks | Table / time series |
| Resources | CPU, RAM, swap, I/O latency | Time series |
| Capacity | Filesystem used %, database size, WAL size | Gauge / time series |
| Reliability | Backup age, archive failures, replication lag | Stat / time series |
| Alerts | Currently firing alerts and recent history | Alert list |

Every panel should include:

- Clear metric title, units, and data source.
- Sensible default time range, e.g., 1 hour or 6 hours.
- Consistent time-axis timezone.
- Legends distinguishing instance, database, or application where relevant.
- Explained threshold lines—never rely on color alone.
- Links or notes pointing to the corresponding runbook.

Avoid cramming dozens of tiny panels onto one screen. A panel is useful only when learners know what it measures and what action to take when it shifts.

### 6.2. Workload and Query Dashboard

Break down into:

- Transaction rate: `commit/s` and `rollback/s`.
- Connections: `active`, `idle`, `idle in transaction`, and total backends.
- Query duration: longest active query and top queries from `pg_stat_statements`.
- Wait events: waiting backends grouped by `wait_event_type`.
- Temporary files: rate of `temp_files` and `temp_bytes`.
- Deadlocks: occurrences over time.
- Cache behavior: `blks_hit` and `blks_read` rates with caveats noted.

### 6.3. Capacity and Storage Dashboard

Display:

- Filesystem usage per mountpoint.
- Free space in GB.
- Daily/weekly database growth rate.
- WAL generated per minute or hour.
- WAL archive failures.
- Backup footprint and retention age if tracked.
- Volume IOPS, throughput, latency, and queue depth.

Database size and filesystem usage are distinct metrics. A database may grow slowly while the filesystem fills up due to WAL pinned by replication slots, logs, temp files, or local backups.

### 6.4. Replication and Backup Dashboard

When the lab includes a standby, display:

- Standby connection status.
- `sync_state` and `application_name`.
- Replay lag in bytes and time.
- WAL sender/receiver states if collected.
- Timestamp of latest successful backup.
- Backup duration and backup size.
- Outcome of the latest restore verification test.

A successful backup does not guarantee a successful restore. Include a periodic exercise restoring into a separate database or instance to prove recoverability.

## 7. Connecting Prometheus and Exporters

When using `postgres_exporter`, pin the exporter version in your lab and consult documentation for that exact version. Default metrics, metric names, and custom queries change across releases and configs.

Basic scrape config example:

~~~yaml
scrape_configs:
  - job_name: postgres
    scrape_interval: 15s
    static_configs:
      - targets:
          - postgres-exporter:9187

  - job_name: node
    scrape_interval: 15s
    static_configs:
      - targets:
          - node-exporter:9100
~~~

This snippet covers only the Prometheus scrape config. The exporter services must be deployed in Docker Compose or your host setup with network routes to PostgreSQL and secure credentials.

After startup:

1. Open the Prometheus Targets page.
2. Confirm both `postgres` and `node` targets show `UP`.
3. Query a baseline metric to confirm ingestion works.
4. Inspect the exporter's `/metrics` endpoint on the admin network and check PostgreSQL metrics.
5. Verify exact metric names for your running exporter version.
6. Check exporter logs if a target shows `UP` yet database metrics are missing.

An `UP` target only proves Prometheus scraped the HTTP endpoint. It does not prove the exporter logged into PostgreSQL successfully or that custom queries succeeded. Verify both database health metrics and exporter logs.

### 7.1. PromQL Examples

Common `node_exporter` metrics:

Approximate CPU busy percentage (excluding idle; adjust for `iowait` per dashboard goals):

~~~promql
100 * (1 - avg by (instance) (
  rate(node_cpu_seconds_total{mode="idle"}[5m])
))
~~~

Filesystem used percentage:

~~~promql
100 * (
  1 -
  node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}
  /
  node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}
)
~~~

Add mountpoint filters to monitor specifically the volumes holding PostgreSQL data. Do not trigger alerts across ephemeral filesystems like `tmpfs`, `overlay`, or scratch mounts outside operational scope.

For `postgres_exporter`, metric names vary by version and query mappings. Exporters commonly emit a database health gauge such as `pg_up` alongside `pg_stat_database` metrics. Before embedding PromQL into dashboards or alert rules, inspect `/metrics` to verify exact metric names, labels, and counter vs. gauge types.

For example, if `pg_up` exists in your running exporter version:

~~~promql
pg_up == 0
~~~

If your exporter uses a different health metric name, substitute the exact metric name. Never copy queries from dashboards built for a different exporter version without verifying them.

### 7.2. Distinguishing Counters, Gauges, and Histograms

- A counter only increases until the process restarts or stats reset. Use `rate()` or `increase()` to compute rates or deltas.
- A gauge can rise or fall, such as current connections or free disk bytes.
- A histogram tracks bucketed distributions, typically used to compute latency quantiles via `histogram_quantile()` when appropriate buckets exist.

For example, apply `rate()` to transaction counters for commits per second; never apply `rate()` to current connection gauges. Plot filesystem available gauges directly to show free space.

Prometheus `rate()` handles counter resets within a window cleanly in many cases. Nevertheless, verify exporter restarts, PostgreSQL `pg_stat_reset()` calls, and `instance` labels so distinct sources are never merged accidentally.

## 8. Designing Actionable Alerts

A solid alert rule answers four questions:

1. What condition counts as abnormal?
2. How long must the abnormality persist before alerting?
3. What should the responder inspect first?
4. What severity warrants immediate action?

Never fire alerts on a single-scrape spike. Use `for` durations, workload-informed thresholds, and exclusion filters to prevent flapping alerts.

### 8.1. Severity Levels

| Level | Meaning | Examples |
|---|---|---|
| Info | Informational for learning or tracking | Backup finished, checkpoint spike that self-recovered |
| Warning | Needs investigation soon | Filesystem above threshold, connections climbing quickly |
| Critical | Service impact or imminent operational failure | PostgreSQL down, volume nearly full, backup past RPO |
| Resolved | Condition cleared | Target returned `UP`, disk usage dropped below recovery threshold |

In a lab environment, route alerts to a sandbox contact point or view them inside Grafana. Never route practice alerts to production paging channels.

### 8.2. Database Unreachable Alert

Example condition: database health metric reports down continuously for 1 minute.

~~~yaml
groups:
  - name: postgres-availability
    rules:
      - alert: PostgreSQLUnavailable
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL is unreachable"
          description: "Exporter cannot verify PostgreSQL status for {{ $labels.instance }}."
          runbook: "runbooks/postgresql-unavailable.md"
~~~

Use this rule only after verifying `pg_up` in your exporter. If the scrape target vanishes completely, `pg_up` may produce no sample rather than `0`; pair it with a rule for `absent()` or target scrape failure so exporter-down and database-down are clearly distinguished.

### 8.3. Filesystem Nearly Full Alert

Example alerting when filesystem usage exceeds 85% for 10 minutes:

~~~yaml
- alert: PostgreSQLFilesystemUsageHigh
  expr: |
    100 * (
      1 -
      node_filesystem_avail_bytes{mountpoint="/var/lib/postgresql"}
      /
      node_filesystem_size_bytes{mountpoint="/var/lib/postgresql"}
    ) > 85
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "PostgreSQL filesystem nearly full"
    description: "Mountpoint {{ $labels.mountpoint }} on {{ $labels.instance }} is over 85% used."
    runbook: "runbooks/postgresql-disk-capacity.md"
~~~

Replace the example mountpoint with your lab's actual path. When WAL, logs, or backups sit on separate volumes, create dedicated rules per volume. Use available bytes (`avail_bytes`) rather than raw free bytes when filesystems reserve blocks for root or metadata.

Add a higher critical threshold, such as 95%, sized according to the lead time required to expand storage and your data growth rate. On small volumes, 95% may already be too late; on huge, slow-growing volumes, a different threshold may make sense.

### 8.4. High Connection Usage Alert

If your exporter exposes backend counts and `max_connections`, create a percentage rule:

~~~promql
100 *
pg_stat_activity_count
/
pg_settings_max_connections
> 80
~~~

Exact metric names vary by exporter version and custom query config. Verify metric names, `instance` labels, and how backends are counted. If unavailable, configure a custom exporter query or SQL dashboard panel.

Never look at total connections alone. When ratio climbs, inspect `active`, `idle`, `idle in transaction`, reserved superuser slots, and app pool counts. Alerts should guide learners to inspect pool sizing, connection leaks, and backend limits.

### 8.5. Overdue Backup Alert

Backup age must come from the backup system's last verified completion timestamp—not inferred from whether PostgreSQL is up. For example, if the lab mandates daily backups, alert if time since last valid backup exceeds 26 hours.

Assuming a backup job exports an epoch timestamp metric:

~~~promql
time() - postgresql_backup_last_success_timestamp_seconds > 26 * 3600
~~~

This sample metric must be emitted by your backup job or a custom exporter. Ensure the job updates the timestamp strictly after the backup completes and passes verification—never when the job merely starts.

### 8.6. Replication Lag Alert

Enable only when the lab runs a standby. Base thresholds on RPO, workload, and standby purpose. You can alert on byte lag or replay time, but never treat `NULL` replay lag during an idle primary period as an outage.

Pair the alert with a runbook checking:

- Whether the standby is connected.
- WAL sender and receiver states.
- Whether replication slots are pinning WAL.
- Network health between primary and standby.
- Whether WAL generation rate spiked abnormally.
- Whether long standby queries are delaying replay.

### 8.7. Missing Data Alerts

A vanished target can cause an alert expression to return zero series. Depending on the alerting engine, missing data may evaluate as OK, NoData, or Error. Explicitly configure no-data handling and add dedicated alerts for exporter or Prometheus scrape failures.

Never allow "missing samples" to be interpreted as a healthy database. At the same time, avoid flooding operators with duplicate alerts when a single host outage drops all exporter metrics at once.

## 9. Grouping Alerts and Reducing Noise

When multiple alerts fire together, group by instance, cluster, or environment so responders see one coherent incident instead of dozens of duplicate pages.

Core practices:

- Name alerts clearly by component and symptom.
- Attach labels such as `severity`, `environment`, `service`, and `instance`.
- Include descriptions, current values, and runbook links in annotations.
- Tune `for` durations to match metric volatility.
- Configure recovery thresholds or hysteresis to stop flapping.
- Group related alerts belonging to the same incident.
- Never route lab alerts to production contact points.
- Log firing, acknowledged, and resolved timestamps alongside actions taken.

Every alert needs a clear owner or on-call role. In lab drills, learners act as on-call responders; specify clearly who investigates, who confirms recovery, and who is authorized to run destructive commands.

## 10. Designing Runbooks

A runbook is a scenario-driven action guide. It must be specific enough for another operator to follow, while discouraging state-mutating commands before verifying root cause.

Every runbook should include:

| Field | Contents |
|---|---|
| Incident Name | Short title matching the alert name |
| Objective | Service or metric to restore |
| Scope | Instance, database, environment, version |
| Severity | Warning/Critical and business impact |
| Trigger Condition | Alert expression and `for` duration |
| Initial Checks | Metrics, logs, SQL queries, and timestamps |
| Common Causes | Testable root-cause hypotheses |
| Remediation Steps | Ordered steps and preconditions to proceed |
| Rollback | How to revert configuration changes |
| Recovery Verification | Metrics and smoke tests confirming health |
| Escalation | When to involve senior admins or other teams |
| Incident Log | Timestamps, responder, changes applied, outcomes |

Runbooks must clearly mark which commands are read-only, which mutate state, and which risk downtime or data loss. Never put passwords in examples. Use placeholders for hostnames, database names, and paths, instructing learners to pull actual values from lab config.

## 11. Sample Runbook: PostgreSQL Unreachable

**Alert:** `PostgreSQLUnavailable`

**Objective:** Determine whether the database is down, the exporter is down, or a network fault sits between collector and database; restore verified connectivity.

### Initial Checks

1. Record the alert timestamp and target instance.
2. Open the overview dashboard to check exporter target health and PostgreSQL status.
3. Inspect exporter, Prometheus, and PostgreSQL logs.
4. Determine whether only the exporter fails or applications also cannot connect.

On the PostgreSQL host:

~~~bash
systemctl status postgresql
~~~

Service names vary across distros and installation methods. Under Docker:

~~~bash
docker compose ps
docker compose logs --tail=100 postgres
~~~

Check readiness:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

Check listening socket:

~~~bash
ss -lntp | grep 5432
~~~

### Triage Branches

- If the service stopped: read PostgreSQL startup logs and OS logs before restarting. Check causes such as full disk, bad config, permissions, or crash.
- If the service runs but is not listening: check port and `listen_addresses`, then confirm reload/restart status.
- If local connections succeed while remote connections fail: check routing, firewalls, security groups, and `pg_hba.conf`.
- If the exporter is down while the app still works: check exporter service, DNS, network, secrets, and `monitoring` role grants.
- If the service crash-loops: stop looping restarts; capture logs and inspect resources, config files, disk space, and OS errors.

### Recovery Verification

- `pg_isready` reports accepting connections.
- Application connects cleanly from its runtime environment.
- Exporter target returns `UP` and fresh metrics appear.
- Dashboard shows no further data gaps.
- Repeated errors stop in logs.
- Document root cause and actions taken.

## 12. Sample Runbook: PostgreSQL Filesystem Nearly Full

**Alert:** `PostgreSQLFilesystemUsageHigh`

**Objective:** Identify which volume is filling up, locate what is consuming space, and safely free or expand capacity.

### Initial Checks

~~~bash
df -h
df -i
du -xhd1 /var/lib/postgresql
~~~

These commands apply to Linux; adjust paths to match your actual `PGDATA`. `df -i` checks inode exhaustion, since a filesystem can run out of inodes even with spare bytes.

Inside PostgreSQL:

~~~sql
SHOW data_directory;
SHOW log_directory;
SHOW archive_mode;
~~~

Check largest databases and tables with `pg_database_size` and `pg_total_relation_size`. Check WAL archiver:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_failed_time,
    last_failed_wal
FROM pg_stat_archiver;
~~~

If replication slots exist:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

### Triage Branches

- If logs grew rapidly: identify log type, repeating error messages, and rotation policy. Never delete an actively written log without understanding file descriptor handling.
- If WAL grew rapidly: check archive failures, replication lag, and slots pinning WAL. Fix the consumer or archiving pipeline per runbook.
- If backups share the same volume: check retention and relocate verified backups to external storage per policy.
- If legitimate business data grew: expand the volume or execute approved archiving/partitioning/retention jobs.
- If a table or index ballooned unexpectedly: inspect workload, bloat, recent migrations, and index builds.

**Never manually delete files inside `pg_wal` or the data directory to reclaim space.** Doing so can render PostgreSQL unrecoverable or unbootable. Never run `VACUUM FULL` casually on a nearly full volume because it requires extra temporary disk space and acquires heavy table locks.

### Recovery Verification

- Filesystem free space returns to target headroom.
- WAL archiving and replication resume cleanly if applicable.
- PostgreSQL accepts connections and executes baseline queries.
- Alert transitions to `Resolved` after its recovery window.
- Root cause and preventive actions are documented.

## 13. Sample Runbook: High Connections or Connection Exhaustion

**Alert:** `PostgreSQLConnectionsHigh`

**Objective:** Distinguish genuine traffic spikes, misconfigured connection pools, `idle in transaction` sessions, and connection leaks.

### Checks

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Break down sessions by application:

~~~sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    COUNT(*) AS sessions,
    MAX(now() - xact_start) AS oldest_transaction
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name, usename, client_addr, state
ORDER BY sessions DESC;
~~~

Check against configured limit:

~~~sql
SELECT
    current_setting('max_connections')::integer AS max_connections,
    COUNT(*) FILTER (
        WHERE backend_type = 'client backend'
    ) AS client_backends
FROM pg_stat_activity;
~~~

### Mitigation

- Identify which application or pool opens the most connections.
- Multiply app instance count by max pool size; verify total does not exceed PostgreSQL limits.
- Check for `idle in transaction` sessions and long-running transactions.
- Check for retry storms triggered by database slowness or transient drops.
- Lower pool sizes or bound concurrency when app config is the root cause.
- Terminate individual sessions only after verifying owner, impact, and authorization.

Never mass-terminate sessions merely to silence an alert. Never raise `max_connections` without evaluating RAM and per-backend overhead.

### Recovery Verification

- Connection counts return within normal operating range.
- Applications open connections and process requests cleanly.
- No abnormal hung transactions remain.
- Pool sizes stop climbing uncontrollably.
- No new `connection refused` or `too many connections` errors appear.

## 14. Sample Runbook: Slow Queries, Locks, and Deadlocks

**Alert:** `PostgreSQLLongRunningQuery` or `PostgreSQLDeadlocks`

### Inspecting Queries and Wait Events

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    LEFT(query, 300) AS query_preview
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND (
      state = 'active'
      OR state = 'idle in transaction'
  )
ORDER BY query_start NULLS LAST;
~~~

Identify blocking sessions using `pg_blocking_pids`:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_duration,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    LEFT(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocking_pid.pid
ORDER BY blocked.query_start;
~~~

### Mitigation

- Determine whether the query is actively running or blocked waiting on a lock.
- If waiting on a lock, identify the blocker and transaction owner.
- Check whether application code holds transactions open too long.
- Run `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment to spot expensive scans, sorts, or joins.
- For deadlocks, read PostgreSQL logs to identify competing transactions and lock acquisition orders.
- Cancel or terminate a backend only after evaluating impact and obtaining approval.

`pg_cancel_backend` sends a query cancellation request; `pg_terminate_backend` kills the entire session. They carry different impact and can roll back application transactions. Never use `terminate` as your reflexive first step.

### Recovery Verification

- Wait events and blocked session counts drop.
- Query latency returns to normal range.
- Deadlock rate stops climbing abnormally.
- Applications complete transactions without data errors.

## 15. Sample Runbook: Backup or WAL Archiving Failures

**Alert:** `PostgreSQLBackupOverdue` or `PostgreSQLArchiveFailures`

### Checks

- Inspect backup job output logs and exit codes.
- Identify the latest backup that genuinely completed.
- Check target storage free space, permissions, network reachability, and credentials.
- Inspect `pg_stat_archiver` and PostgreSQL logs.
- Check accumulating WAL and active replication slots.
- Verify retention schedules and backup execution windows.

### Mitigation

- Fix credential, permission, network, or disk capacity issues per root cause.
- Re-run the backup following standard procedure; never overwrite the latest known-good backup prematurely.
- For archive failures, restore archive destination health and confirm archiver catches up.
- Never delete WAL segments still needed for archiving or replication.
- Post-backup, run checksum verification or a scheduled restore test as supported by your tools.

### Recovery Verification

- Fresh backup job exits cleanly.
- Last-success timestamp updates only after completion.
- Backup files/artifacts exist and are readable.
- Scheduled restore test succeeds in an isolated environment.
- WAL archiving advances steadily and disk usage stabilizes.

## 16. Organizing Runbooks in a Repository or Lab

You can structure observability assets as follows:

~~~text
observability/
├── prometheus/
│   ├── prometheus.yml
│   └── alerts/
│       ├── postgres-availability.yml
│       ├── postgres-capacity.yml
│       └── postgres-workload.yml
├── grafana/
│   ├── dashboards/
│   │   ├── postgres-overview.json
│   │   ├── postgres-workload.json
│   │   └── postgres-capacity.json
│   └── provisioning/
├── exporter/
│   └── README.md
└── runbooks/
    ├── README.md
    ├── postgresql-unavailable.md
    ├── postgresql-disk-capacity.md
    ├── postgresql-connections.md
    ├── postgresql-locks-and-slow-queries.md
    └── postgresql-backup-and-wal.md
~~~

This layout is a starting suggestion. Adapt it to match your repository and lab deployment structure. Every dashboard JSON, alert rule, and runbook should have versioning, an owner, and test verification.

Never commit secrets inside the `observability/` directory. Commit sanitized config templates with placeholders while keeping passwords, private keys, webhook URLs, and tokens in a secret store or git-ignored local config files.

## 17. Testing Dashboards and Alerts in the Lab

An alert that has never fired cannot be trusted to work properly. Simulate controlled failure scenarios and test the entire pipeline from metric emission to notification delivery.

### 17.1. Testing Dashboards

1. Start PostgreSQL and confirm the exporter target shows `UP`.
2. Run a light read/write workload.
3. Observe transaction rates and connection counts moving.
4. Run a moderately long query in the lab and observe it under active queries.
5. Insert sample rows to observe table growth.
6. Confirm dashboard refreshes within the expected scrape interval.
7. Briefly stop the exporter and verify the dashboard surfaces missing metrics clearly.

Never generate destructive load or intentionally fill a shared host's disk. Every chaos test must have strict bounds, a time limit, and a tested recovery step.

### 17.2. Testing Alert Rules

For each alert:

- Confirm the expression returns expected baseline series during healthy state.
- Trigger the threshold breach in the lab.
- Confirm the alert transitions from `Pending` to `Firing` after the `for` duration.
- Verify labels, annotations, and runbook links render cleanly.
- Confirm notification arrives at the designated lab contact point.
- Remediate the fault and confirm the alert transitions to `Resolved`.
- Test metric disappearance to confirm no-data handling.

For disk alerts, never fill up a real volume. Use a synthetic test metric or a temporary rule with a lower threshold to verify the notification pipeline. Afterward, delete the temporary rule and confirm main lab/production configs match desired state.

### 17.3. Testing Runbooks

Have someone who did not write the runbook execute it step by step. Record:

- Which steps lacked clear details?
- Which commands failed in the current environment?
- Did any step require privileges the responder lacked?
- What criteria governed moving to the next step?
- What proof confirmed full recovery?
- When should the responder stop and escalate?

Update runbooks after every drill. A runbook is truly useful only when another operator can resolve the exact same incident without guessing.

## 18. Security and Limiting Observability Exposure

Dashboards and exporters can expose infrastructure topology, users, database names, and SQL queries. Protect:

- Monitoring role accounts and exporter credentials.
- `/metrics` endpoints, Prometheus UI, and Grafana UI.
- Dashboards displaying query text, usernames, client IPs, or database names.
- Webhooks, tokens, and notification contact points.
- Logs containing literals, personal data, or application payloads.

Enable Grafana authentication, enforce dashboard RBAC, and bind exporters strictly to management networks. Never expose PostgreSQL exporters or Prometheus to the public Internet. When sharing dashboards with learners, use read-only accounts and sanitized datasets.

Metrics also carry cardinality costs. High-cardinality labels like raw query text, request IDs, or user IDs can blow up Prometheus cardinality. Never attach full SQL strings as Prometheus labels; use `queryid` or a controlled top-queries table inside dashboards instead.

## 19. Lab Completion Checklist

- [ ] PostgreSQL exposes health checks and accessible logs.
- [ ] Monitoring role holds least privilege and secrets are protected.
- [ ] Exporter and node metrics scrape cleanly.
- [ ] Prometheus targets accurately reflect status.
- [ ] Overview dashboard covers health, workload, capacity, and reliability.
- [ ] Counters render via `rate()` or `increase()` where appropriate.
- [ ] Dashboards separate `active`, `idle`, and `idle in transaction`.
- [ ] Filesystems holding data, WAL, and backups are clearly mapped.
- [ ] Database-down, disk-usage, and core alerts are tested.
- [ ] No-data and exporter-down cases are handled distinctly.
- [ ] Every alert includes severity, description, and a runbook link.
- [ ] Lab contact points are tested without ever paging production.
- [ ] Runbooks document verification, remediation, rollback, and recovery confirmation.
- [ ] Backups undergo scheduled restore tests.
- [ ] Dashboards, alert rules, and runbooks are version-controlled.
- [ ] Zero passwords, private keys, or tokens appear in Git or dashboard exports.

## 20. Post-Drill Incident Report Template

After each drill, document findings using this template:

~~~text
Incident ID:
Start time:
Detection time:
Recovery time:
Environment / instance:
Alert:
Severity:
User symptoms:
Relevant metrics and logs:
Root cause:
Ruled-out hypotheses:
Actions taken:
Rollback (if any):
Recovery verification results:
Data impact:
Downtime duration:
Runbooks to update:
Preventive actions:
Responder / verifier:
~~~

Distinguish detection time from incident start time to compute Mean Time to Detect (MTTD). Distinguish detection time from recovery time to compute Mean Time to Recover (MTTR) per team definitions. Never declare root cause from a single alert alone; substantiate with logs, metrics, or reproducible tests.

## Conclusion

Dashboards give operators visibility into state and trends; alerts highlight conditions needing attention; runbooks turn those signals into controlled actions. A strong lab tests the entire chain end-to-end: PostgreSQL emits stats, exporters collect them, Prometheus stores and evaluates rules, Grafana visualizes them, alerts reach the right responders, and runbooks confirm full recovery.

Start with foundational metrics, document each metric's source and semantics, craft actionable alerts, and rehearse every failure scenario. When dashboards, alerts, and runbooks are tested together, the practice environment teaches both how to observe PostgreSQL and how to operate it reliably under incident pressure.
