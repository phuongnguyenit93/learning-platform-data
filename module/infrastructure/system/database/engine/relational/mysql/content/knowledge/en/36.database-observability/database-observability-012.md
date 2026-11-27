# Exporting Metrics, Setting Alerts, and Establishing Performance Baselines

A MySQL system can still accept connections while degrading: waiting sessions pile up, queries gradually slow down, the buffer pool reads from disk more frequently, replication falls behind, or disk capacity nears exhaustion. To detect those shifts before users report errors, operations teams must turn internal MySQL and host state into metrics that can be collected, stored, visualized, and alerted on.

This lesson frames observability within MySQL operations: choosing metric sources, understanding metric types, exporting metrics via an exporter, building dashboards, configuring alerts, and establishing performance baselines. Examples use MySQL 8.0/8.4 and the Prometheus model; exact metric names vary by MySQL version, exporter version, and enabled collectors. Before deploying rules to production, verify against your environment's actual `/metrics` endpoint.

## 1. Learning Outcomes

After this lesson, learners can:

- Describe the pipeline from MySQL instrumentation to time-series storage and alerting.
- Distinguish counters, gauges, and histograms; know when to compute rates of change instead of reading cumulative totals.
- Choose metrics reflecting availability, load, latency, errors, and resource utilization.
- Use Performance Schema, the sys schema, and global status to investigate metrics.
- Configure a least-privilege monitoring account and deploy a MySQL exporter securely.
- Build dashboards from service, database, InnoDB, and OS perspectives.
- Write alerts with clear evaluation windows, severities, and remediation actions.
- Establish baselines across workloads, time of day, and growth trends.

## 2. Metric Collection Architecture

A metric observability pipeline typically has six components:

1. **Data sources**: MySQL status variables, Performance Schema, sys schema, replication status, and OS metrics.
2. **Exporter/collector**: reads these sources, normalizes them into metrics, and exposes an endpoint for monitoring systems to scrape.
3. **Scraper**: Prometheus or an equivalent platform periodically queries the exporter's endpoint.
4. **Time-series store**: stores metric samples by timestamp and labels such as instance, job, and environment.
5. **Dashboards and queries**: Grafana or an equivalent UI visualizes trends, ratios, and correlations.
6. **Alerting and incident response**: evaluates alert conditions, groups notifications, routes to on-call engineers, and links runbooks.

With Prometheus, the common model is pull-based: the exporter exposes an HTTP endpoint and Prometheus actively scrapes it. The exporter does not push individual samples into Prometheus. This model lets Prometheus manage scrape intervals, target labels, and scrape health status.

~~~mermaid
flowchart LR
    A[MySQL Server] --> B[mysql exporter]
    C[Node exporter] --> D[Prometheus]
    B --> D
    D --> E[Time-series]
    E --> F[Grafana dashboard]
    E --> G[Alert rules]
    G --> H[Alertmanager]
    H --> I[On-call / Runbook]
~~~

MySQL exporter and node exporter observe two different layers. MySQL exporter provides database state such as connections, queries, InnoDB, and replication. Node exporter provides CPU, RAM, filesystems, network, and disk I/O of the host running MySQL. Looking only at database metrics can miss OS-level root causes; looking only at CPU and RAM cannot explain which queries are slow.

Never treat a dashboard as the entirety of an observability system. Metrics show what is changing; logs show discrete events that occurred; traces or APM show which components a request traversed. For MySQL, the slow query log and Performance Schema supply context that aggregated metrics cannot show.

## 3. Metric Sources Inside MySQL

### 3.1. Global Status and System Variables

<code>SHOW GLOBAL STATUS</code> returns server counters and state values. You can inspect a subset using:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Uptime',
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Aborted_connects',
  'Questions',
  'Queries',
  'Slow_queries',
  'Created_tmp_tables',
  'Created_tmp_disk_tables',
  'Innodb_buffer_pool_read_requests',
  'Innodb_buffer_pool_reads',
  'Innodb_row_lock_waits',
  'Innodb_row_lock_time',
  'Innodb_log_waits'
);
~~~

On versions with Performance Schema, you can query <code>performance_schema.global_status</code> and <code>performance_schema.global_variables</code>. This is convenient for automation tooling. <code>SHOW GLOBAL VARIABLES</code> or <code>performance_schema.global_variables</code> retrieves settings like <code>max_connections</code>, <code>innodb_buffer_pool_size</code>, and <code>slow_query_log</code>.

Not all status variables share the same semantics. <code>Threads_connected</code> is the number of currently open sessions, so it is a gauge. <code>Connections</code> is the number of client connection attempts since server startup, so it is a counter. <code>Uptime</code> is how long the server has been running. Reading a counter once does not reveal current load; compute its rate of increase over a time window.

### 3.2. Performance Schema

Performance Schema captures internal server activity: statements, wait events, table I/O, file I/O, locks, memory, and threads. It answers deeper questions than aggregate status variables:

- Which SQL digest consumes the most total time?
- Which table experiences the most reads or writes?
- Which resource type are threads waiting on?
- Which file exhibits high I/O latency?
- Is a metadata lock blocking DDL?

Notable tables:

| Performance Schema Table | Purpose |
|---|---|
| <code>events_statements_summary_by_digest</code> | Aggregates statements by digest, execution counts, and timings |
| <code>events_statements_current</code> | Statements currently executing at observation time |
| <code>events_waits_summary_global_by_event_name</code> | Aggregates waits by event type |
| <code>table_io_waits_summary_by_table</code> | Logical I/O by table and index |
| <code>file_summary_by_instance</code> | File-level I/O activity |
| <code>memory_summary_global_by_event_name</code> | Instrumented memory allocations by event |
| <code>threads</code> | MySQL threads and instrumentation flags |
| <code>metadata_locks</code> | Held or pending metadata locks |

Consumers and instruments can be toggled via configuration. If a required instrument is disabled, summary queries may miss data or reflect only partial activity. Check configuration state before concluding the server has no waits or statements:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
   OR NAME LIKE 'wait/io/%'
ORDER BY NAME
LIMIT 30;

SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
~~~

Enabling broad instrument groups can add overhead and expand internal memory usage. Pick only the needed groups, measure impact in a test environment, and follow your system's operational policy.

### 3.3. sys Schema

The sys schema provides readable views over Performance Schema. Useful views include:

- <code>sys.statement_analysis</code>: statement digests, execution counts, total/avg latency, rows examined, rows sent, and temporary tables.
- <code>sys.schema_table_statistics</code>: per-table read/write activity and latency.
- <code>sys.io_global_by_file_by_bytes</code>: file I/O by byte volume.
- <code>sys.io_global_by_file_by_latency</code>: file I/O by latency.
- <code>sys.innodb_lock_waits</code>: InnoDB lock wait details.
- <code>sys.user_summary</code> and <code>sys.host_summary</code>: activity grouped by user or host.

Example finding statements with high total latency:

~~~sql
SELECT
  db,
  exec_count,
  total_latency,
  avg_latency,
  rows_examined,
  rows_sent,
  tmp_disk_tables,
  query
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

sys views assist investigation after metrics flag anomalies. Never turn full query texts, connection IDs, or individual threads into high-cardinality time-series labels. Keep detailed query text in Performance Schema, the slow log, or log-query systems; metrics should retain only bounded summary groupings.

## 4. Understanding Metric Types Correctly

### 4.1. Counter

A counter is a cumulative value that generally only increases during a server's lifecycle and can reset to 0 on restart or reset. Examples: connections received, queries executed, physical reads, lock wait counts.

To measure activity over an interval, use delta or rate:

~~~promql
rate(mysql_global_status_questions[5m])
increase(mysql_global_status_aborted_connects[10m])
~~~

<code>rate</code> estimates the per-second growth rate while handling counter resets appropriately for time series. <code>increase</code> estimates total growth over the window. Never treat a raw counter value as current QPS or errors in the last 5 minutes.

### 4.2. Gauge

A gauge can rise or fall. Examples: current connections, running threads, memory usage, active transactions, and free filesystem space.

Gauges are usually observed directly or compared against limits:

~~~promql
mysql_global_status_threads_connected
mysql_global_status_threads_running
100 * mysql_global_status_threads_connected
  / mysql_global_variables_max_connections
~~~

Gauge values can fluctuate rapidly. Alerting on a single sample can cause false positives; usually apply a sustained <code>for</code> duration condition.

### 4.3. Histogram and Quantile

Histograms bucket observations to analyze distributions, such as query latency. From histograms you can estimate p95 or p99. A low mean does not guarantee good tail latency: most requests may be fast while a small cohort suffers severe delays.

Not all metrics exposed by mysqld_exporter are latency histograms. If an endpoint provides only total execution count and total elapsed time, you cannot derive an exact p95 from those two values alone. To track percentiles, use an appropriate histogram source such as application instrumentation, APM, or a collector designed to export buckets. When aggregating histograms across instances, buckets must align.

## 5. Foundational Metric Set for MySQL

Start with metric groups tied to service symptoms, then add internal metrics to explain root causes.

| Group | Common Metrics or Sources | Operational Question |
|---|---|---|
| Availability | Prometheus <code>up</code>, exporter scrape success, MySQL uptime | Can Prometheus scrape the exporter? Did the server just restart? |
| Connections | <code>Threads_connected</code>, <code>Threads_running</code>, <code>Max_used_connections</code>, <code>Connections</code>, <code>Aborted_connects</code> | Is the pool exhausted? Are there connection storms or auth failures? |
| Throughput | <code>Questions</code>, <code>Queries</code>, <code>Com_select</code>, <code>Com_insert</code>, <code>Com_update</code>, <code>Com_delete</code> | How are traffic and read/write ratios shifting? |
| Slow queries | <code>Slow_queries</code>, digest summary, slow query log | Did slow queries rise due to query mix or load? |
| Buffer pool | <code>Innodb_buffer_pool_read_requests</code>, <code>Innodb_buffer_pool_reads</code>, dirty pages, and buffer pool size | Are physical reads or cache pressure rising? |
| Locks | <code>Innodb_row_lock_waits</code>, <code>Innodb_row_lock_time</code>, deadlocks from InnoDB status/monitoring | Are transactions contending on data? |
| Temporary tables | <code>Created_tmp_tables</code>, <code>Created_tmp_disk_tables</code>, sort counters | Are queries spilling excessive temporary tables to disk? |
| Redo/log | <code>Innodb_log_waits</code>, redo/checkpoint metrics by version | Are writes stalled by redo logging or flushing? |
| Replication | Replica status, receiver/applier state, lag, and replication errors | Is the replica keeping up with the source? |
| Operating system | CPU, memory, swap, disk latency, free space, network | Is the database constrained by host or storage? |

Exact metric and exporter names may differ. Check metric descriptions, units, counter/gauge types, and labels on the endpoint before writing queries. Never infer units solely from metric names.

### 5.1. Connections and Saturation

- <code>Threads_connected</code>: number of currently connected clients at sample time.
- <code>Threads_running</code>: threads not sleeping; sustained high values can reflect many active queries or resource waits.
- <code>Max_used_connections</code>: peak concurrent connections since server startup.
- <code>max_connections</code>: configured connection limit.
- <code>Connections</code>: client connection attempts over the server lifecycle.
- <code>Aborted_connects</code>: failed connection attempts as defined by the server.

The ratio <code>Threads_connected / max_connections</code> shows limit utilization, though not how many useful connections remain in pools. A server with many idle connections can still exhaust workers or resources under rising load. Monitor <code>Threads_running</code>, timeout rates, application latency, and pool wait counts together.

### 5.2. Buffer Pool and Disk Reads

The InnoDB buffer pool keeps data and index pages in memory. <code>Innodb_buffer_pool_read_requests</code> counts logical read requests; <code>Innodb_buffer_pool_reads</code> reflects reads requiring disk access into the buffer pool. You can estimate cache hit ratio over a window as:

<code>1 - (physical reads / logical read requests)</code>

Use deltas/rates of both counters over the exact same interval, and guard against division by zero. This ratio is only a high-level signal: a high cache hit ratio does not prove queries are fast, and a drop may be normal after a restart or when workloads shift to a new dataset.

Read it alongside disk read latency, bytes read, buffer pool size, dirty pages, query mix, and working set. Expanding the buffer pool makes sense only when host RAM is available and evidence shows cache pressure; never tune settings merely to make a ratio look pretty.

### 5.3. Locks, Temporary Tables, and Redo

<code>Innodb_row_lock_waits</code> and <code>Innodb_row_lock_time</code> help detect row-lock contention. They do not replace investigating specific transactions: when alerted, inspect lock-holding transactions, transaction age, table access ordering, and blocking statements.

Rapidly rising <code>Created_tmp_disk_tables</code> can signal queries spilling temporary tables to disk. Compare against total temporary tables and query throughput, then examine digests, sorts, group-bys, joins, and relevant settings. Not every disk temporary table indicates a bug.

Rising <code>Innodb_log_waits</code> can indicate transactions waiting for redo log space. Correlate with redo generation rate, checkpoint age, write latency, and write workload. Exact names and availability of detailed redo metrics depend on version.

### 5.4. Replication

Monitoring replication requires more than a single lag number. At minimum check:

- Whether receiver/I/O and applier/SQL threads are running.
- Whether there are errors reading relay logs, applying transactions, or connecting to the source.
- Whether lag is climbing steadily or only spiking briefly during bursts.
- Whether large transactions or DDLs are stalling the applier.
- Whether the replica has sufficient disk, CPU, and I/O capacity to keep up.

On MySQL 8.0, prefer modern commands and column names like <code>SHOW REPLICA STATUS</code> where supported; older environments may still use <code>SLAVE</code> naming. <code>Seconds_Behind_Source</code>/<code>Seconds_Behind_Master</code> is not always an exact gauge, especially when threads stop, the source sends no events, or clocks drift. Read thread state and errors alongside lag. Exporter replication metric names can vary by version, so verify on your endpoint.

## 6. Tracking Query Quality

Aggregate metrics show query counts or total time, yet usually do not identify which digest to tune. Combine Performance Schema and the sys schema to pinpoint load-generating query groups:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  COUNT_STAR,
  ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
  ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_milliseconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_CREATED_TMP_DISK_TABLES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Performance Schema timers are typically stored in picoseconds; verify conversions against your version's column units. Use <code>sys.statement_analysis</code> for quick reading, while always checking column definitions and units before comparing.

Never rank solely by average latency. A digest running millions of times with low average latency can consume far more server time than a rare, very slow query. Inspect at least:

- Execution count and total latency.
- Average latency and tail latency distributions where measurable.
- Rows examined versus rows sent.
- On-disk temporary tables, full scans, and sorts.
- Shifts over time, across schemas, and across application releases.

The slow query log is valuable for capturing real sample statements, though you must manage disk size, permissions, and sensitive data. Weigh the <code>long_query_time</code> threshold, log output destination, and rotation policy. Setting thresholds too low on high-traffic systems can create heavy I/O and log volume. Performance Schema digests help group statements structurally without storing every literal value.

## 7. Exporting Metrics with mysqld_exporter

### 7.1. Monitoring Account

The exporter needs a dedicated account allowed to connect only from the monitoring host or subnet. The example below illustrates creating the account; exact privileges depend on exporter version and enabled collectors:

~~~sql
CREATE USER 'metrics'@'10.20.30.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT PROCESS, REPLICATION CLIENT
  ON *.* TO 'metrics'@'10.20.30.%';

GRANT SELECT
  ON performance_schema.* TO 'metrics'@'10.20.30.%';
~~~

Some collectors need to read additional metadata or specific schemas. Grant extra privileges only after verifying which collector requires them and what read scope is necessary. Never reuse application or admin accounts for the exporter. Store passwords in a secret manager or protected config file; never commit secrets to Git or pass passwords on command lines visible in process lists.

If exporter setup docs ask for broader <code>SELECT</code> privileges, evaluate each collector and narrow scope wherever possible. A monitoring account still accesses production; enforce password rotation, TLS, network policies, and auditing like any other service account.

### 7.2. Connection Configuration

A client option file can look like:

~~~ini
[client]
user=metrics
password=REPLACE_WITH_SECRET
host=127.0.0.1
port=3306
protocol=tcp
~~~

Save the file readable only by the OS user running the exporter. If the exporter runs on a separate host, configure the MySQL address and TLS per internal policy. Never expose exporter or MySQL ports to the public Internet.

Run the exporter via a service manager or managed container. A common setup listens over HTTP on port 9104; ports, flags, and config formats can vary across versions. Pin image/binary versions, read release notes, and verify supported flags before upgrading.

### 7.3. Verifying the Endpoint

After starting, test the endpoint from the monitoring network:

~~~bash
curl -s http://127.0.0.1:9104/metrics | head
~~~

Locate representative metrics and verify:

- The endpoint returns HTTP success.
- Scrape health metrics and expected database metrics are present.
- Values have sensible units, types, and labels.
- The exporter connects to the intended instance, not another environment by mistake.
- Exporter logs show no permission errors, timeouts, or TLS failures.

The `/metrics` endpoint can reveal database names, settings, or operational state. Restrict access with firewalls, private networks, authentication proxies, or equivalent controls. Expose the endpoint only inside trusted monitoring zones.

## 8. Configuring Prometheus Scraping

Minimal example in `prometheus.yml`:

~~~yaml
scrape_configs:
  - job_name: mysql
    scrape_interval: 15s
    scrape_timeout: 10s
    static_configs:
      - targets:
          - db-a.internal:9104
          - db-b.internal:9104
~~~

<code>scrape_interval</code> sets sampling frequency; <code>scrape_timeout</code> must be less than or equal to the interval. A 15-second interval is an example, not a universal default for every system. Higher frequencies raise scrape, storage, and processing costs; lower frequencies risk missing brief events. Choose based on rate of change, detection requirements, and real load.

After updating configuration, validate Prometheus config and check target status. A target showing DOWN could stem from DNS, routing, firewalls, a stopped exporter, TLS issues, or slow MySQL causing exporter timeouts. Distinguish scrape failures from MySQL unavailability: the exporter might be unable to reach the database even while the exporter process stays alive.

When running multiple environments, add controlled labels such as <code>environment</code>, <code>region</code>, <code>cluster</code>, and <code>role</code>. Use labels to group dashboards and alerts. Never place secrets, SQL literals, emails, or user IDs into labels.

## 9. Controlled Metric and Label Design

Each time series is a metric combined with a unique label set. If a label takes hundreds of thousands of continuously changing values, series cardinality explodes, consuming excessive RAM, CPU, disk, and slowing dashboard queries.

Use labels with bounded, stable value sets:

- <code>environment</code>: dev, staging, production.
- <code>cluster</code>: managed cluster identifier.
- <code>instance</code>: stable hostname or instance identifier.
- <code>role</code>: primary, replica, or equivalent role.
- <code>job</code>: scrape job name.

Avoid high-cardinality or volatile labels:

- Full SQL text or statement literals.
- Connection IDs, thread IDs, or transaction IDs.
- Request IDs, user IDs, emails, or session tokens.
- Filenames generated unboundedly by date or request.

When investigating a specific request, use logs or traces with proper querying capabilities. Metrics should answer aggregated questions and trigger alerts. For SQL digests, export only top-N groups or cardinality-bounded summaries; consider digest hashes and avoid raw query text as labels.

Set retention based on investigative needs and cost. High-resolution data helps analyze recent incidents; long-term data can be downsampled or stored via recording rules. Never extend retention without calculating cardinality, instance count, scrape interval, and projected storage.

## 10. Operational Dashboards

Dashboards should help on-call engineers quickly answer: is the service healthy, how is load shifting, which resource is saturating, and when did the issue begin?

A practical MySQL dashboard can be organized into rows:

| Row | Charts | How to Read |
|---|---|---|
| Service | Target up, uptime, restarts, replication role | Verify instance is scraping and check for recent restarts |
| Load | QPS, read/write rate, connections, threads running | Compare current load against same-hour baseline |
| Latency | Query latency, application DB latency, p95/p99 if available | Spot tail latency and when degradation started |
| InnoDB | Buffer pool reads, dirty pages, redo/log waits, row lock waits | Spot cache pressure, write stalls, and contention |
| Queries | Slow query rate, top-N digests, rows examined | Identify resource-heavy query groups |
| Replication | Thread states, lag, apply rate, errors | Detect replicas falling behind or stopped |
| Host | CPU, RAM, swap, disk latency, free space, network | Separate database bottlenecks from infrastructure bottlenecks |

Align time zones and time formatting across dashboards, MySQL, exporters, and logs. Annotate deployments, configuration changes, backups, DDL, and failovers. Annotations tie changes directly to metric shifts.

Panels should have clear units, readable legends, sensible default time ranges, and links to runbooks. Do not add panels merely because a metric exists. Any panel not tied to a concrete operational question or decision creates noise.

## 11. Alerting Principles

A good alert describes a meaningful service-level symptom, persists long enough to filter noise, and links to a clear next action. Alerts should not fire merely because a metric crossed an arbitrary number.

Before creating an alert, define:

1. **Impact**: which users, transactions, or service objectives are affected?
2. **Signal**: which metric reliably reflects that impact?
3. **Condition**: what threshold, evaluation window, and sustained duration apply?
4. **Severity**: critical, warning, or informational?
5. **Action**: what should the responder check first?
6. **Scope**: single instance, cluster, or entire service?

Prioritize symptom-based alerts such as database unable to serve requests, rising application latency, exhausted connection pools, replication exceeding business limits, or disks nearing full. Cause-oriented metrics like dropping buffer pool hit ratios belong in diagnostic supporting alerts unless proven directly tied to outages.

### 11.1. Evaluation Windows and Scrape Latency

The <code>for</code> clause requires an expression to stay true continuously over a duration before firing. Choose this duration based on scrape interval, harmful event duration, and desired response speed. Availability alerts typically require faster response than gradual capacity alerts.

If a query range window is much shorter than the scrape interval, results may lack samples or oscillate. If <code>for</code> is too long, alerts arrive late. If too short, normal bursts trigger noisy pages. Test rules against historical data before enabling paging.

### 11.2. Severity Classification

- **Critical**: service unavailable, errors directly impacting transactions, or imminent loss of service capacity. Requires immediate on-call response.
- **Warning**: saturation or degradation trends likely to become incidents if unaddressed. Investigate during business hours or per agreed SLOs.
- **Info**: operational changes worth recording without paging.

Do not mark every metric alert as critical. If every threshold breach wakes on-call engineers, responders lose the ability to distinguish urgent signals. Use Alertmanager grouping, inhibition, and deduplication to suppress duplicate noise.

## 12. Example Prometheus Alert Rules

The following examples illustrate syntax and reasoning. Metric names like <code>mysql_global_status_*</code> and <code>mysql_global_variables_*</code> are typical for mysqld_exporter; verify exact names in your live environment.

~~~yaml
groups:
  - name: mysql-availability
    rules:
      - alert: MySQLExporterScrapeFailed
        expr: up{job="mysql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Failed to scrape MySQL exporter"
          description: "Check exporter, network, target, and MySQL status."

  - name: mysql-capacity
    rules:
      - alert: MySQLConnectionsNearLimit
        expr: |
          100 *
          mysql_global_status_threads_connected
          / mysql_global_variables_max_connections > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "MySQL connection usage near limit"
          description: "Check pools, connection leaks, and Threads_running trends."

  - name: mysql-errors
    rules:
      - alert: MySQLAbortedConnectionsIncreasing
        expr: increase(mysql_global_status_aborted_connects[10m]) > 20
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "MySQL failed connections increasing"
          description: "Check auth errors, timeouts, network, and server logs."
~~~

An exporter scrape failure rule does not prove MySQL is down. It only shows Prometheus could not fetch the endpoint. Pair with an independent signal or database connection probe to distinguish exporter, network, and server failures.

### 12.1. Monitoring Query Rates and Slow Queries

~~~promql
rate(mysql_global_status_questions[5m])
rate(mysql_global_status_slow_queries[5m])
~~~

Both expressions are suitable for trend charts. To alert on them, compare against baselines or service objectives and correlate with latency/error rates. A QPS surge may be a legitimate campaign; rising slow queries without latency impact may simply reflect a workload shift.

### 12.2. Monitoring Lock Waits

~~~promql
rate(mysql_global_status_innodb_row_lock_waits[5m])
rate(mysql_global_status_innodb_row_lock_time[5m])
~~~

These indicate the rate of lock waits and accumulated lock wait time. Units of time metrics depend on the exporter. Verify units before setting thresholds. When firing, use <code>sys.innodb_lock_waits</code>, open transactions, and the process list to find blockers.

### 12.3. Buffer Pool Read Pressure

You can compute the ratio of physical reads to logical reads via a recording rule after confirming metric and counter names:

~~~yaml
groups:
  - name: mysql-derived
    rules:
      - record: mysql:innodb_physical_reads_per_logical_read:ratio_rate5m
        expr: |
          rate(mysql_global_status_innodb_buffer_pool_reads[5m])
          /
          clamp_min(
            rate(mysql_global_status_innodb_buffer_pool_read_requests[5m]),
            1
          )
~~~

This approximates the ratio of storage reads to total logical read requests. Never make it a standalone critical page. Correlate with disk latency, throughput, query latency, working set, and restart events. <code>clamp_min</code> avoids division by zero, though it does not turn tiny denominators into meaningful data; dashboards should handle low-traffic/missing-data windows separately.

### 12.4. Never Alert on a Single Metric Without Context

For example: rising <code>Threads_running</code> may reflect valid load growth, slow queries, lock waits, or CPU throttling. Rising <code>Created_tmp_disk_tables</code> may come from a scheduled report. Brief <code>Seconds_Behind_Source</code> spikes may recover automatically. Combine multiple signals, apply sustained windows, and verify impact before paging.

## 13. Establishing Performance Baselines

A baseline is a quantitative description of normal system behavior under known workloads and conditions. It helps separate normal variation from degradation, estimate capacity, and evaluate the impact of changes.

A useful baseline must document:

- MySQL version, key configuration, instance type, CPU/RAM/storage, and topology.
- Data size, indexes, buffer pool size, and data growth rate.
- Application version, connection pools, query mix, and client count.
- Throughput, latency, error rates, lock waits, and replication metrics.
- Measurement timestamps, time zone, weekday/weekend, batch windows, or peak hours.
- Deployments, backups, batch jobs, and maintenance occurring during measurement.

Never use one short benchmark run as a production baseline. Measure across multiple business cycles, including peak hours and scheduled jobs. Collect enough history to cover daily/weekly variance while separating periods where architecture or workload changed.

### 13.1. Statistical Levels

For continuous metrics, record:

- Median (p50) to describe typical behavior.
- p95 and p99 to capture tail latency or tail utilization.
- Min/max to spot boundary anomalies, without treating them alone as targets.
- Growth rates over time for counters.
- Peak levels per business window, such as 5 minutes or 1 hour.

For latency, prefer application-layer distributions or histogram sources. If only averages exist, document that limitation clearly. Averages can mask a slow subset of requests.

### 13.2. Comparing Under Matching Conditions

Comparing QPS at 10:00 AM Monday against the same-hour baseline is far more meaningful than comparing against a weekly average. When query mix changes, identical QPS does not mean identical cost. An index-lookup workload differs completely from full scans or write-heavy transactions.

When comparing before/after deployments, keep duration and load as consistent as possible; document differences in dataset, cache warm-up, replica count, and configuration. If load cannot be held constant, normalize per request, transaction, or rows processed.

### 13.3. Baselines and Capacity

Capacity is not merely average CPU utilization. Identify the point where latency, error rates, or queues begin rising sharply as load grows. Run controlled load tests to find true limits while observing CPU, disk latency, memory, connection pools, locks, and replication.

Leave headroom for bursts, failovers, and rolling maintenance. A primary may absorb extra traffic when a replica is upgraded or a node goes offline. Never operate right at the limit merely because a synthetic benchmark still met throughput.

### 13.4. Example Baseline

Suppose an OLTP system has peak hours from 09:00 to 11:00. After multi-day measurement, a baseline might record:

| Metric | Peak-Hour Baseline | How It Is Used |
|---|---:|---|
| QPS | 2,000–2,600 | Compare same time window and query mix |
| Application DB latency p95 | 35–55 ms | User experience signal |
| Threads_connected | 180–240 | Track pool behavior and headroom |
| Threads_running | 12–28 | Read alongside CPU and latency |
| Connection limit | 600 | Set warning threshold based on trend |
| Replica lag | typically under 2 seconds | Evaluate against replica read SLAs |
| Disk utilization | 45–65% | Read alongside disk latency and queue depth |

These numbers are hypothetical examples illustrating baseline documentation, not universal recommendations for every MySQL server. Every system must measure its own baseline based on actual hardware, query mix, SLOs, and topology.

## 14. Choosing Alert Thresholds from Baselines and SLOs

A sound approach combines three layers when setting thresholds:

1. **SLOs or business targets**: e.g., request success rate, p95/p99 latency, maximum replica sync lag.
2. **Baseline**: normal behavior observed over time and workload.
3. **Technical limits**: max_connections, disk capacity, memory, replication limits, or service quotas.

Thresholds need safety buffer before hitting hard limits. For instance, alerting on connection utilization at 80–85% can serve as an investigation trigger, though it must be validated against pool sizing, bursts, and scaling lead time. Disk free alerts must factor in data growth rate and time required to provision storage, not just a generic percentage.

Distinguish level-based alerts from burn-rate/degradation-rate alerts. A filesystem at 30% free may be fine if growing slowly; at 30% free while growing 5% per hour requires immediate action. Use growth rates for counters; use levels, trends, and forecasts for gauges.

Never tweak <code>max_connections</code>, buffer pool, or redo log sizes automatically just to silence an alert. Configuration changes require a hypothesis, RAM/CPU/I/O assessment, rollback plan, and post-change verification.

## 15. Validating Alert Quality

Before enabling production paging:

- Backtest rules against historical data to inspect firing times and false positives.
- Test missing-metric, server-restart, and counter-reset edge cases.
- Verify instance/cluster labels so pages route to the right team.
- Verify Alertmanager grouping, inhibition, deduplication, and routing.
- Include dashboard links, runbook links, and diagnostic queries in annotations.
- Run a controlled game-day drill in staging or a test environment.
- Periodically prune alerts that are no longer actionable or lack owners.

Every alert should have an owner, severity, resolution criteria, and remediation guide. Alerts without runbooks or owners inevitably turn into alert fatigue noise.

## 16. Investigation Workflow When an Alert Fires

When a MySQL alert fires, trace from impact down to root cause:

1. Identify the instance, role, cluster, start time, and affected user scope.
2. Check target health (`up`), exporter logs, MySQL error log, and connection status.
3. Correlate application latency/error rates with QPS and connection pools.
4. Check CPU, memory, swap, disk latency, filesystems, and network.
5. Check Threads_running, lock waits, SQL digests, slow logs, and temporary tables.
6. Check buffer pool, redo/log waits, and I/O.
7. If it is a replica, check receiver/applier threads, errors, and apply rate.
8. Identify recent changes: deployments, DDL, batch jobs, backups, failovers, or config edits.
9. Choose a mitigating action, preserve evidence, and monitor post-action recovery.

Do not rush to restart MySQL simply because latency rose. Restarting destroys transient diagnostic state, flushes warm caches, and can prolong outages. Collect status, process lists, digests, lock waits, and logs before performing disruptive actions on an instance, unless an emergency runbook explicitly dictates otherwise.

## 17. Common Scenarios

### 17.1. Exporter Is Up but MySQL Metrics Are Missing

Check exporter logs, account credentials, Performance Schema privileges, enabled collectors, and timeouts. HTTP 200 from the endpoint proves only that the exporter process responded; it does not guarantee every collector queried the database successfully. Compare available metrics with <code>SHOW GLOBAL STATUS</code> and Performance Schema queries run as the monitoring user.

### 17.2. Prometheus Reports Target DOWN

Check DNS, routing, firewalls, exporter port, TLS, service status, and timeouts. Test connecting to the endpoint from the Prometheus host. If the exporter runs while MySQL is slow or unreachable, check exporter logs and test database connectivity independently.

### 17.3. QPS Rises While Latency Remains Stable

Correlate with peak hours, batch schedules, business campaigns, and query mix. If SLOs hold, this may simply be normal traffic growth. Monitor CPU, connection, disk, and replica headroom to catch emerging capacity risks.

### 17.4. Latency Rises While CPU Remains Low

Inspect lock waits, disk latency, fsyncs, networking, metadata locks, and waiting threads. Low CPU does not mean the database is idle; threads may be stalled on storage, locks, or external dependencies.

### 17.5. Buffer Pool Hit Ratio Drops

Check for recent restarts, shifting datasets/working sets, new queries, large scans, and memory pressure. Compare physical read rates against disk latency and application latency. Never enlarge the buffer pool before checking available RAM and host limits.

### 17.6. Replica Lag Increases

Check receiver/applier states, SQL errors, large transactions, DDL, primary write load, replica CPU/I/O, and networking. Determine whether lag grows steadily or spikes in bursts. If the replica serves read traffic, assess stale-read impact before shifting traffic away.

### 17.7. Alerts Fire Repeatedly After a Restart

Counters may have reset and the buffer pool needs warm-up. Use <code>rate</code>/<code>increase</code> properly, handle missing-data periods, and account for post-restart stabilization windows. Never mute all alerts long-term; suppress only known transient conditions while keeping availability checks active.

## 18. Hands-On Practice: Deploying Metrics and Alerts for a MySQL Instance

### Step 1: List Operational Questions

For a primary instance, answer:

- Can the exporter be scraped?
- How much of the connection limit is in use?
- How are QPS and read/write rates changing?
- Are slow queries and lock waits rising?
- Is the buffer pool incurring heavy physical reads?
- Do CPU, RAM, disk, and filesystems still have headroom?

Pick one metric per question, documenting its source, metric type, unit, and collection frequency.

### Step 2: Create the User and Verify Privileges

Create a dedicated monitoring account following Section 7. Log in with that exact account and test reading status variables and required Performance Schema tables. If a collector hits permission errors, verify which collector needs extra privileges before granting them.

### Step 3: Install the Exporter and Verify the Endpoint

Deploy the exporter with a pinned version, protected credentials file, and restricted network policy. Query `/metrics` and locate connection, query, and InnoDB metrics. Compare several values against <code>SHOW GLOBAL STATUS</code> to verify instance identity and units.

### Step 4: Add the Prometheus Target

Declare the scrape target, validate configuration, reload per deployment procedures, and confirm the target is UP. Check scrape duration, scrape errors, and total time series created.

### Step 5: Build the Dashboard

Create panels for availability, QPS, connections, threads running, slow query rate, buffer pool read rate, lock waits, replication, and host metrics. Align time ranges to correlate database and OS shifts.

### Step 6: Create Your First Two Alerts

Start with exporter scrape failed and connection utilization near limit. Define <code>for</code>, severity, summary, description, owner, and runbook. Test rules against staging or historical data before enabling paging.

### Step 7: Collect a Baseline

Gather metrics across multiple days and business cycles. Record p50/p95/p99 where supported, QPS, query mix, connections, latency, host utilization, and deployment events. Derive alert thresholds from the baseline combined with SLOs and headroom.

### Step 8: Run a Drill

Generate controlled test load or simulate an unreachable exporter in staging. Confirm alerts fire, notifications reach the right responder, dashboards display full context, and runbooks guide useful actions. Afterward, stop test load and verify alerts resolve.

## 19. Self-Check Exercises

1. Why does <code>Connections</code> require <code>rate()</code> while <code>Threads_connected</code> is usually read directly?
2. Does a Prometheus target showing UP prove MySQL is healthy? Explain what gaps remain.
3. Why should SQL text or connection IDs never be used as labels?
4. If QPS doubles while latency and error rates stay flat, what should you check before declaring an incident?
5. Is a sharp rise in <code>Innodb_buffer_pool_reads</code> enough to conclude the buffer pool is too small?
6. Why can average latency not replace p95/p99?
7. A replica reports rising lag while the applier thread is stopped on an SQL error. What must metrics and runbooks surface?
8. Design a disk capacity alert. What do you need to know about growth rate, headroom, and provisioning lead time?
9. If the exporter lacks Performance Schema metrics while status metrics still work, what will you check?
10. Propose a baseline plan for a workload with midnight batch jobs and morning peak hours.

## 20. Production Readiness Checklist

- [ ] Metrics have documented sources, units, counter/gauge types, and meanings.
- [ ] Exporter runs under a dedicated account with least privilege and protected secrets.
- [ ] Endpoint is reachable only from authorized monitoring networks.
- [ ] Prometheus scrapes the intended instance with appropriate timeout and interval.
- [ ] Dashboards cover both database and host, with synchronized time zones and deployment annotations.
- [ ] No labels contain SQL literals, request IDs, or personal data.
- [ ] Alerts tie to service impact with evaluation windows, severities, owners, and runbooks.
- [ ] Thresholds align with baselines, SLOs, and technical limits.
- [ ] Counter resets, missing data, restarts, and scrape failures are handled.
- [ ] Alerts have been drilled and notification routing verified.
- [ ] Retention, cardinality, and storage cost reviews are in place.

## 21. References

- [MySQL 8.4 Reference Manual — Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual — Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [MySQL 8.4 Reference Manual — sys Schema](https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html)
- [MySQL 8.4 Reference Manual — Replication Monitoring](https://dev.mysql.com/doc/refman/8.4/en/replication-monitoring.html)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus Community — mysqld_exporter](https://github.com/prometheus/mysqld_exporter)

Collector names, metrics, and MySQL privileges must be verified against the exact exporter version deployed. References here are a starting point for checking real behavior and do not replace release notes or environment-specific configuration.
