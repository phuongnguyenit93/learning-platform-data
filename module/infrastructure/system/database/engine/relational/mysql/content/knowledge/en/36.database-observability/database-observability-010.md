# Cumulative Counters, Measurement Intervals, and Interpreting Data After Restart/Reset

A large counter value alone is not enough to conclude MySQL is under heavy load. Counters typically accumulate from a starting point, so 8 million SELECT statements could reflect a week of normal traffic or a one-minute traffic spike. To understand the current rate, you need at least two snapshots, the exact elapsed interval between them, and confirmation that both snapshots belong to the same server operating cycle.

You must also distinguish counters from gauges and high-water marks. Counters increment with events; gauges represent point-in-time state; high-water marks retain the peak value observed since a reset point. Each requires a different interpretation. After a restart, failover, FLUSH STATUS, or statistics reset, naive subtraction can yield a negative delta or a meaningless rate.

This lesson belongs to the **System Observability** chapter of the **DATABASE_MYSQL** module. Within mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, reading counters over measurement intervals helps detect load trends, compare before/after changes, and avoid false conclusions when statistics are interrupted.

## 1. Three Metric Types to Distinguish

Before performing calculations, determine which category a metric belongs to:

| Type | Characteristics | MySQL Examples | How to Read |
|---|---|---|---|
| Cumulative counter | Increases with events or work; usually never decreases within a statistics cycle | Questions, Connections, Slow_queries, Bytes_received | Compute delta between two snapshots and divide by elapsed time |
| Gauge | Point-in-time state value that can rise or fall | Threads_connected, Threads_running, Innodb_buffer_pool_pages_data | Read current value, trends, and min/max/percentiles over time series |
| High-water mark | Retains the maximum or minimum recorded over a period | Max_used_connections | Compare against limits and reset timestamps; do not compute rates like counters |

A counter such as Questions = 2,000,000 only shows the cumulative total up to capture time. If the previous snapshot was 1,998,000 and the next snapshot 20 seconds later is 2,000,000, the delta is 2,000 and the average rate is 100 questions/second.

A gauge such as Threads_connected = 240 indicates 240 connections were open at that moment. Do not subtract the previous snapshot's connection count from 240 and call the result queries/second. To understand connection load, track current values, averages, peaks, and distribution by user/host.

A high-water mark such as Max_used_connections = 480 indicates the server reached 480 concurrent connections since the latest statistics reset. This is neither the current connection count nor does it tell you when the peak occurred without a historical monitoring system.

Some metrics may carry slightly different semantics across versions or collection sources. Verify each variable's definition in the documentation for your exact MySQL version before putting it into dashboards or alerts.

## 2. Data Sources and Statistics Scopes

MySQL exposes status variables at GLOBAL and SESSION scopes.

~~~sql
SHOW GLOBAL STATUS;
SHOW SESSION STATUS;
~~~

- GLOBAL reflects server-wide statistics per each variable's definition. Many variables aggregate activity across sessions.
- SESSION reflects the current connection's activity. Another session can have different values.
- Once a connection closes, that connection's SESSION metrics are no longer readable from that session.
- Performance Schema provides tables such as performance_schema.global_status and performance_schema.session_status to query status variables with SQL.

Example filtering a subset of variables:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Slow_queries'
);
~~~

Or:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Slow_queries'
)
ORDER BY VARIABLE_NAME;
~~~

Status variables are generally represented as strings in Performance Schema. When computing math, cast types deliberately and verify values are numeric. Do not blindly cast every variable across all of global_status if non-numeric values are included.

Distinguish status variables from Performance Schema summary tables. For example, events_statements_summary_by_digest aggregates counts, timings, and rows examined per digest. Summary tables can be reset via Performance Schema mechanisms such as TRUNCATE TABLE on certain summary tables. Resetting a summary table does not necessarily reset server-wide status variables.

## 3. Common Counters and Practical Meaning

Useful status variables when observing load:

| Counter | General Meaning | What It Can Suggest |
|---|---|---|
| Questions | Statements sent by clients and processed by the server per variable definition | Rate of client-sent statements |
| Queries | Statements executed by the server, including certain statements inside stored programs | Broader statement activity than Questions |
| Connections | Connection attempts made by clients to the server | Rate of new connection attempts, not active connections |
| Slow_queries | Statements logged as slow per threshold and log criteria | Rate of slow query occurrences |
| Com_select | SELECT statements executed | SELECT trend |
| Com_insert / Com_update / Com_delete | Corresponding DML statements executed | Statement-level write share |
| Bytes_received / Bytes_sent | Bytes received/sent by the server per variable definition | SQL protocol traffic rate |
| Created_tmp_tables | Internal temporary tables created | Temporary table creation frequency |
| Created_tmp_disk_tables | Internal temporary tables created on disk | Signal to investigate on-disk temporary tables |
| Innodb_buffer_pool_reads | Times InnoDB had to read a page from disk into the buffer pool | Physical read trend |
| Innodb_buffer_pool_read_requests | Logical read requests to the buffer pool | Read demand volume |
| Select_scan | Full table scans performed for SELECT | Signal that queries may scan large amounts of data |
| Select_full_join | Joins not using indexes per status variable definition | Signal to review join access paths |

Never infer root cause from a single isolated counter. For example, rising Created_tmp_disk_tables may be normal for a workload requiring large sorts/groups; compare the delta against total temporary tables, query digests, latency, and data volume. Rising Innodb_buffer_pool_reads does not automatically mean the buffer pool is too small; it could reflect a shifting working set or reading cold data.

Questions and Queries should not be used interchangeably without understanding their definitions. Questions focuses on client-sent statements; Queries can include statements executed inside stored programs. When computing QPS, document clearly which counter is being measured.

## 4. Common Gauges and High-Water Marks

Variables tracked as point-in-time state:

| Metric | Type | Interpretation |
|---|---|---|
| Threads_connected | Gauge | Currently open connections |
| Threads_running | Gauge | Active threads not sleeping |
| Innodb_buffer_pool_pages_data | Gauge | Buffer pool pages currently containing data |
| Innodb_buffer_pool_pages_free | Gauge | Free pages remaining in the buffer pool |
| Innodb_row_lock_current_waits | Gauge | Active row-lock waits at sample time |
| Max_used_connections | High-water mark | Peak concurrent connections since the statistics baseline |

Gauges can rise and fall. To capture load peaks, monitoring systems must sample frequently enough and store windowed max/min or percentiles. Running a one-off query after load subsides will miss spikes.

High-water marks should be read alongside their corresponding configured limits. For example:

~~~sql
SELECT
    @@global.max_connections AS configured_limit;
~~~

~~~sql
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

If Max_used_connections approaches max_connections, inspect connection history and trends. However, if the server recently restarted, the high-water mark may appear low even if a high peak occurred before the restart. Do not compare post-restart values with pre-restart values without external historical snapshots.

## 5. Taking Snapshots with Timestamps and Server Identity

A comparable snapshot must record at minimum:

- Capture timestamp with sufficient precision for the interval.
- server_uuid and hostname to identify the node.
- Uptime to detect restarts.
- Metric name and metric value.
- Scope (GLOBAL or SESSION).
- Collection source and MySQL version if retained long-term.

Quick snapshot query:

~~~sql
SELECT
    NOW(6) AS captured_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Slow_queries',
    'Com_select',
    'Com_insert',
    'Com_update',
    'Com_delete',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
)
ORDER BY VARIABLE_NAME;
~~~

This query returns one row per variable. The timestamp and server identity repeat on every row so collection pipelines can bind the values to the same snapshot.

When collecting from multiple nodes, never merge counters from different nodes into a single time series. Each server_uuid must have its own time series. After a failover, an endpoint may point to a different node whose counters started from its own baseline; record both node identity and role.

Do not keep only current values in dashboards. Retain raw snapshots or time series long enough to investigate post-incident, compare same hour/day windows, and detect gradual growth trends.

## 6. Computing Deltas and Rates from Two Snapshots

For a monotonically increasing counter within the same statistics cycle:

- Delta = end value - start value.
- Elapsed seconds = end timestamp - start timestamp.
- Rate = delta / elapsed seconds.

Example:

| Timestamp | Questions |
|---|---:|
| 10:00:00 | 1,200,000 |
| 10:00:30 | 1,201,500 |

The delta is 1,500 statements over 30 seconds. The average rate is 50 statements/second.

General formula:

\[
\text{Rate per second} =
\frac{\text{Counter}_{end} - \text{Counter}_{start}}
{\text{Elapsed seconds}}
\]

A rate is an average over the entire measurement interval. It does not reveal second-by-second distribution. A 2,000 QPS spike lasting 2 seconds can be smoothed out when averaged over a 5-minute window. Choose intervals matching your goal: 1–10 seconds for spike detection, 30–60 seconds for operational dashboards, minutes/hours for long-term trends. These are starting guidelines; balance collection cost and sensitivity.

For example, if Bytes_received increases by 12,000,000 bytes in 60 seconds:

\[
\text{Bytes per second} = \frac{12,000,000}{60}
\]

The result is 200,000 bytes/second. To display MiB/second, divide further by 1,048,576. Always state units explicitly—bytes, KB, MB, or MiB—to prevent misinterpretation.

Do not compute rates for gauges like Threads_connected. For gauges, store the value series and compute averages, max, min, or percentiles over windows. Do not compute rates for high-water marks like Max_used_connections; compare the peak against its limit and track when it resets.

## 7. Hands-On Two-Snapshot Practice in One Session

You can use a temporary table to hold two snapshots inside one MySQL session. The example below stores only a set of integer counters:

~~~sql
CREATE TEMPORARY TABLE status_samples (
    sample_label VARCHAR(10) NOT NULL,
    captured_at DATETIME(6) NOT NULL,
    server_uuid CHAR(36) NOT NULL,
    uptime_seconds BIGINT UNSIGNED NOT NULL,
    variable_name VARCHAR(64) NOT NULL,
    variable_value DECIMAL(30, 0) NOT NULL,
    PRIMARY KEY (sample_label, variable_name)
);
~~~

Capture the first snapshot:

~~~sql
SET @sample_label = 'before';
SET @sample_time = NOW(6);
SET @sample_uuid = @@server_uuid;
SET @sample_uptime = (
    SELECT CAST(VARIABLE_VALUE AS UNSIGNED)
    FROM performance_schema.global_status
    WHERE VARIABLE_NAME = 'Uptime'
);

INSERT INTO status_samples (
    sample_label,
    captured_at,
    server_uuid,
    uptime_seconds,
    variable_name,
    variable_value
)
SELECT
    @sample_label,
    @sample_time,
    @sample_uuid,
    @sample_uptime,
    VARIABLE_NAME,
    CAST(VARIABLE_VALUE AS DECIMAL(30, 0))
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
);
~~~

Wait a deliberate interval, then take the second snapshot in the same session:

~~~sql
DO SLEEP(30);

SET @sample_label = 'after';
SET @sample_time = NOW(6);
SET @sample_uuid = @@server_uuid;
SET @sample_uptime = (
    SELECT CAST(VARIABLE_VALUE AS UNSIGNED)
    FROM performance_schema.global_status
    WHERE VARIABLE_NAME = 'Uptime'
);

INSERT INTO status_samples (
    sample_label,
    captured_at,
    server_uuid,
    uptime_seconds,
    variable_name,
    variable_value
)
SELECT
    @sample_label,
    @sample_time,
    @sample_uuid,
    @sample_uptime,
    VARIABLE_NAME,
    CAST(VARIABLE_VALUE AS DECIMAL(30, 0))
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
);
~~~

Compare the two snapshots:

~~~sql
SELECT
    first_sample.variable_name,
    first_sample.variable_value AS start_value,
    last_sample.variable_value AS end_value,
    TIMESTAMPDIFF(
        MICROSECOND,
        first_sample.captured_at,
        last_sample.captured_at
    ) / 1000000 AS elapsed_seconds,
    last_sample.variable_value - first_sample.variable_value AS delta_value,
    ROUND(
        (last_sample.variable_value - first_sample.variable_value)
        /
        NULLIF(
            TIMESTAMPDIFF(
                MICROSECOND,
                first_sample.captured_at,
                last_sample.captured_at
            ) / 1000000,
            0
        ),
        2
    ) AS rate_per_second
FROM status_samples AS first_sample
JOIN status_samples AS last_sample
    ON last_sample.variable_name = first_sample.variable_name
WHERE first_sample.sample_label = 'before'
  AND last_sample.sample_label = 'after'
  AND first_sample.server_uuid = last_sample.server_uuid
  AND last_sample.uptime_seconds >= first_sample.uptime_seconds
  AND last_sample.variable_value >= first_sample.variable_value
ORDER BY first_sample.variable_name;
~~~

The conditions in this example only return variables where server_uuid did not change, Uptime did not decrease, and the counter did not decrease. If a variable reset or the node changed, that row is excluded from rate results; investigate the cause rather than treating the delta as 0.

This query is a single-session exercise. Production monitoring systems typically collect independent snapshots via agents and store them in a time-series database with node identity, timestamps, labels, and metadata. Do not create temporary tables on every scrape when a monitoring platform already handles collection.

Clean up after the exercise:

~~~sql
DROP TEMPORARY TABLE IF EXISTS status_samples;
~~~

## 8. Detecting Restarts, Failovers, and Counter Resets

Not every counter persists monotonically across all events. Scenarios to detect:

| Event | Common Indicators | How to Handle the Interval |
|---|---|---|
| MySQL restart | Sharp drop in Uptime; startup entries in error log; verify process/server identity | Start a new cycle; do not compute deltas across a restart |
| Failover to another node | server_uuid or hostname changes; node role changes | Separate metric series per node |
| FLUSH STATUS | Certain status counters may reset or update per their rules | Treat as a reset boundary if counters drop or history shows the command |
| Performance Schema summary reset | Summary table truncated/reset; counts and timers return to 0 | Start a new baseline for the reset summary table |
| Reconfigure/disable instrumentation | Some metrics stop updating or change values | Record configuration change and mark interval non-comparable |
| Counter rollover | Value wraps around upon exceeding storage type limit, depending on metric | Apply specific rollover logic if documented; otherwise mark invalid |

Uptime is a helpful indicator but cannot catch every reset. FLUSH STATUS can affect certain status variables without restarting the server. Resetting Performance Schema summary tables can also occur independently of uptime.

When you detect that the ending counter is smaller than the starting counter, never compute a negative delta and display a negative rate. Mark the interval as reset/invalid, establish a new baseline, and record the cause if known.

Never run FLUSH STATUS or TRUNCATE summary tables merely to make a production dashboard look clean. Resetting statistics erases comparison baselines and can disrupt other monitoring tools. Reset only with a clear goal, proper authorization, a plan to save before/after snapshots, and operational approval.

## 9. Distinguishing Counter Resets from Workload Drops

Suppose Questions was 900,000 in the first snapshot and 120,000 in the next. At least three possibilities exist:

1. The server restarted and counters began from zero again.
2. Counters were reset by an administrative action or statistics mechanism.
3. The snapshots came from two different nodes after a failover or endpoint change.

Do not conclude that workload dropped by 780,000 statements. Check:

~~~sql
SELECT
    NOW(6) AS checked_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version;
~~~

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections'
);
~~~

Correlate timestamps and server_uuid in your monitoring system, error logs, deploy/failover events, and maintenance logs. If the cause cannot be determined, mark the measurement interval invalid and start a new cycle.

Slowly rising counters also do not prove workload dropped. Instrumentation might be disabled, the agent may have lost read permissions, the exporter may have stopped scraping, or traffic may have shifted to another node. Always monitor both scrape health and metric counts received.

## 10. Interpreting Ratios from Related Counters

Certain ratios help identify trends when calculated over the exact same measurement interval:

**Ratio of internal temporary tables created on disk**

\[
\text{Disk temp ratio} =
\frac{\Delta Created\_tmp\_disk\_tables}
{\Delta Created\_tmp\_tables}
\]

Compute only when the denominator is greater than 0. A high ratio warrants inspecting GROUP BY, ORDER BY, DISTINCT queries, data sizes, and temporary table settings. Do not treat every disk temporary table as an error.

**Ratio of physical buffer pool reads to logical read requests**

\[
\text{Read ratio} =
\frac{\Delta Innodb\_buffer\_pool\_reads}
{\Delta Innodb\_buffer\_pool\_read\_requests}
\]

This is a relative indicator of page reads from disk versus logical read requests over the same window. It is not a complete measure of application latency or cache efficiency. Also inspect I/O latency, working set, and query times.

**Network byte rate**

\[
\text{Bytes per second} =
\frac{\Delta Bytes\_received \text{ or } \Delta Bytes\_sent}
{\text{Elapsed seconds}}
\]

Used to track server-level MySQL protocol traffic. It is not identical to total host network traffic, as the host may run other services and network flows.

**Rate of newly logged slow queries**

\[
\text{Slow query rate} =
\frac{\Delta Slow\_queries}{\text{Elapsed seconds}}
\]

This metric depends on long_query_time, log_queries_not_using_indexes, and related settings. When thresholds or slow log settings change, pre- and post-change series are no longer strictly comparable; record the change timestamp.

When calculating ratios, verify that numerator and denominator come from the same node, same time window, and same statistics cycle. If either counter reset mid-interval, discard the entire calculation depending on it.

## 11. Measuring Statement Rates and Traffic by Workload

Approximate QPS can be computed from the Questions delta:

\[
QPS = \frac{\Delta Questions}{\Delta t}
\]

However, QPS says nothing about query complexity. 1,000 single-row SELECTs differ vastly from 1,000 SELECTs scanning millions of rows. Combine QPS with rows examined, digests, latency, and statement types.

DML mix by statement counters can be examined with snapshots of Com_select, Com_insert, Com_update, and Com_delete. For example:

- Rapidly rising SELECTs may reflect read traffic or polling.
- Sudden spikes in UPDATE/DELETE may stem from batch jobs, retries, or scheduled tasks.
- Rapidly rising Connections without matching Questions growth can indicate connection churn or clients opening connections and barely using them.
- Sharp increases in Bytes_sent may reflect queries returning huge result sets, dumps/exports, or applications fetching excessive data.

These are investigation signals, not root-cause conclusions. Cross-reference application logs, query digests, client hosts, and job schedules.

## 12. Comparing Before and After Configuration Changes or Deployments

When evaluating a change, never take one snapshot before and one snapshot after over incomparable intervals. Keep comparison conditions consistent:

1. Same node or same role and topology.
2. Same workload type and comparable duration.
3. Same metric list, units, and GLOBAL/SESSION scope.
4. Same collection method and instrumentation.
5. Same time definitions, time zone, and measurement window.
6. Record restarts, failovers, FLUSH STATUS, summary resets, and config changes.

For example, comparing QPS before adding an index during peak hours against QPS afterward during off-peak hours leads to false conclusions. Compare deltas over windows with similar request volumes and also inspect p95/p99 latency, rows examined, CPU, I/O, and write overhead.

For buffer pool changes, do not inspect Innodb_buffer_pool_reads alone. Monitor memory pressure, page reads, latency, disk I/O, and workload after warm-up. For max_connections changes, inspect connection peaks, Threads_running, RAM, and error rates.

If a change requires a restart, the counter series breaks. Capture a snapshot before restarting, mark the restart event, and start a fresh baseline once the server stabilizes. Never compute a single delta spanning two different uptimes.

## 13. Designing Dashboards for Counters and Gauges

A readable dashboard categorizes metrics and visualizes reset boundaries:

| Panel | Display Type | Content |
|---|---|---|
| Query throughput | Rate line chart | Questions/s, Com_select/s, DML statements/s |
| Network throughput | Rate line chart | Bytes_received/s, Bytes_sent/s |
| Temporary tables | Rate and ratio | disk temp tables/s, disk temp ratio |
| Buffer pool | Counter rate and gauge | physical reads/s, logical requests/s, pages free/data |
| Connections | Gauge and high-water | Threads_connected, Threads_running, Max_used_connections, max_connections |
| Slow queries | Rate | Slow_queries/s and long_query_time changes |
| Node lifecycle | Event annotation | restarts, failovers, maintenance, FLUSH STATUS |
| Scrape health | Gauge/status | last scrape timestamp, exporter errors, metrics received |

Never plot a cumulative counter as a gauge line when the goal is viewing instantaneous load. A monotonically rising counter hides spikes and misleads viewers. Use rates/deltas, or keep a separate panel for cumulative totals.

Annotate restarts, failovers, and resets on dashboards. When counters restart, metrics systems may compute negative rates or false spikes if unaware of resets. A well-behaved exporter handles counter resets per source semantics; operators still need to inspect node identity and lifecycle events.

For gauges, display current values and windowed percentiles. For high-water marks, display the peak alongside the configured limit. For counters, display rates and put cumulative totals in a separate panel if both are useful.

## 14. Alerting Based on Rates and Reset States

Counter alerts should rely on windowed rates or ratios, not cumulative totals since startup. For example, Slow_queries = 50,000 may be normal over many days, whereas an increase of 500 in one minute may be abnormal against baseline.

A solid alert needs:

- Clearly defined metric and units.
- Measurement window and minimum-data conditions.
- Handling for resets/restarts and node identity.
- Thresholds grounded in baseline or SLO.
- Hold duration (for/pending window) to avoid paging on brief harmless spikes.
- Next actions and a linked runbook.

Never fire negative-rate alerts. If a counter decreases, transition the metric to an unknown/reset state and wait for two valid snapshots to recompute. Never coerce unknown to 0, as that can mask collection failures or restarts.

For gauges like Threads_connected, alert on current value, ratio relative to max_connections, and rate of approach toward the limit. For high-water marks, alert when the historical peak uses most of the limit within the current cycle, accounting for restarts or resets.

## 15. Common Interpretation Mistakes

**Treating current counter as rate.** Questions = 5 million is not 5 million QPS. You need deltas and elapsed time.

**Subtracting snapshots from two nodes.** Counters from different server_uuids belong to independent series. Separate data by node.

**Interpreting a negative delta as workload drop.** A decrease usually signals a reset, restart, rollover, or source change. Mark the interval invalid.

**Ignoring Uptime.** A drop in Uptime signals a restart. Capture both uptime and server identity in snapshots.

**Assuming FLUSH STATUS resets all metrics identically.** Status variables and Performance Schema summary tables follow separate reset rules. Check semantics for each source and variable.

**Treating gauges as counters.** Threads_connected is the current connection count. Do not divide its difference by time and call it QPS.

**Treating Max_used_connections as current connections.** It is a high-water mark. Compare it against max_connections and track resets.

**Computing ratios with a zero denominator.** Do not divide when no events occurred in the interval. Return NULL/unknown or skip the calculation.

**Using overly long windows for spike detection.** Long average rates smooth away brief incidents. Use multiple window sizes and weigh collection cost.

**Ignoring scrape health.** Flat counters may mean workload stopped or the exporter dropped data. Check timestamps and collection status.

**Resetting statistics to tidy dashboards.** Resets destroy baselines and affect other tools. Save snapshots beforehand and log events if a reset is necessary.

## 16. Hands-On Exercise: Detecting Restarts and Computing Valid Rates

Use a test MySQL instance or a read-only environment permitted for observation. Never restart a server or run FLUSH STATUS in production just for exercises.

**Part A — Capture snapshots**

Run the following query twice, about 30 seconds apart:

~~~sql
SELECT
    NOW(6) AS captured_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections'
);
~~~

Record both outputs with timestamps. Classify each variable as a counter, gauge, or high-water mark.

**Part B — Compute deltas**

For Questions, Connections, and Slow_queries, compute delta and rate/second. For Bytes_received and Bytes_sent, compute bytes/second. For Threads_connected, compare the two values as a gauge. For Max_used_connections, compare the peak against max_connections.

**Part C — Validate integrity**

Compare server_uuid and Uptime. If UUID changed, the node changed. If Uptime decreased, the server restarted. If a counter decreased while Uptime did not, investigate statistics resets or collection sources. Never plot that interval on a rate chart as a negative value.

**Part D — Write an alerting rule**

Pick a counter, such as Slow_queries. Define an alert condition specifying windowed rate, baseline, hold duration, reset behavior, and next steps. Document how to handle missed exporter scrapes or a recent server restart.

**Part E — Report**

Write a short summary listing the metric, two timestamps, server identity, delta, elapsed seconds, rate, metric classification, and whether the data is valid for comparison.

## 17. Checklist Before Interpreting a Counter

- Is this metric a counter, gauge, or high-water mark?
- Is the scope GLOBAL or SESSION?
- Do the definition and units match the running MySQL version?
- Do both snapshots have reliable timestamps and elapsed time?
- Do both share the same server_uuid and node?
- Did Uptime increase continuously, or did a restart occur mid-interval?
- Were there any FLUSH STATUS commands, summary table resets, or instrumentation changes?
- Is the ending value smaller than the starting value?
- Is the delta non-negative and the denominator valid?
- Over what window length is the rate averaged?
- Could the window mask brief spikes?
- Can fluctuations be explained by workload, batches, backups, deployments, or failovers?
- Have you cross-checked latency, rows examined, CPU, I/O, and replication?
- Do dashboards annotate reset boundaries and scrape failures?
- Does the alert have an owner, baseline, hold condition, and runbook?

Counters are meaningful only when you know when they began accumulating and within what scope. Gauges reflect point-in-time state; high-water marks record cycle peaks; counters require two valid snapshots to compute deltas and rates. By attaching timestamps, server identity, uptime, and reset events to telemetry, you can separate real workload changes from restart/reset artifacts, make fair interval comparisons, and build reliable alerting for MySQL.
