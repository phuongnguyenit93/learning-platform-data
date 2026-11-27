# Alert Thresholds, Sampling Intervals, and Reducing False Positives

PostgreSQL monitoring is not just about collecting metrics and picking a number as a threshold. A useful alert must detect a meaningful condition early enough for operators to act, while avoiding pages caused by brief spikes, normal load fluctuations, missing data, or an isolated anomalous sample. Three high-impact design decisions are **alert thresholds**, **sampling intervals**, and **how a condition is confirmed before firing an alert**.

For example, CPU spiking to 95% in a single scrape may just be a short-lived query. CPU staying at 95% for 15 minutes accompanied by rising query latency, growing pool queues, and dropping throughput may indicate a real incident. Similarly, replication lag increasing for a few seconds is not necessarily alarming; lag rising steadily and exceeding the target RPO requires intervention.

This lesson guides alert design for PostgreSQL based on impact and metric behavior. Topics include static/dynamic thresholds, scrape interval, evaluation interval, range window, pending period, hysteresis, no-data handling, severity, Prometheus/Alertmanager examples, SLO-based alerts, and techniques to reduce false positives while preserving incident detection capability.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish metric, threshold, condition, alert, and notification.
2. Choose thresholds based on SLOs, capacity, RPO/RTO, and baselines.
3. Distinguish static thresholds from dynamic/anomaly thresholds.
4. Choose a sampling/scrape interval suited to how fast a metric changes.
5. Distinguish scrape interval, evaluation interval, range window, and pending duration.
6. Use `rate`/`increase` for counters instead of alerting directly on cumulative counter values.
7. Design sustained-breach conditions, hysteresis, and recovery thresholds.
8. Handle no data, stale samples, scrape failures, and counter resets.
9. Distinguish symptom alerts from cause alerts.
10. Design severity, routing, grouping, inhibition, and maintenance windows.
11. Write alert rules for PostgreSQL connections, replication lag, disk, locks, WAL, and backups.
12. Use multi-window/multi-burn-rate alerts for SLOs.
13. Measure false-positive rate and improve alert quality.
14. Build runbooks, escalation paths, and alert tests.

> **Scope:** Examples use PostgreSQL and common Prometheus/Alertmanager patterns. Syntax, features, and metric names depend on versions and tools. Always verify documentation for your exact version and actual exporter metric names before deploying configurations to production.

## 2. How Do Metric, Threshold, and Alert Differ?

- **Metric**: a measurement over time, such as CPU utilization, active connection count, WAL bytes, or replication lag.
- **Threshold**: a boundary used to evaluate a metric, such as disk utilization greater than 85%.
- **Condition**: an expression defining a state, which may combine multiple metrics and multiple time windows.
- **Alert**: the state created when a condition is satisfied according to a rule.
- **Notification**: the message sent to a person or handling system.

Not every metric crossing a threshold needs to page an on-call engineer. An alert is only useful when it describes a meaningful risk and the recipient knows what action to take.

### Example

An alert might state:

> PostgreSQL primary has less than 10% filesystem space remaining; at the current data growth rate, the disk is projected to fill within 30 minutes. Check WAL retention, replication slots, archiving, and data growth.

This message includes the metric, threshold, sustained duration, impact, and initial action. An alert that merely says "disk high" is far less actionable.

## 3. Alert on Impact, Not Just on Metrics

A metric is a signal; impact is the reason to act. Before configuring an alert, determine:

1. What impact occurs if the metric continues to worsen?
2. How much lead time is available to respond before users are affected?
3. Who can act and what actionable steps exist?
4. Can the same incident be detected via a symptom closer to the user?
5. Which conditions are severe enough to page immediately?

For example, 90% CPU is not automatically an incident. If throughput is steady, latency is healthy, and CPU has appropriate headroom, a dashboard may be sufficient. If 90% CPU persists, request latency breaches the SLO, and pool queues grow, an alert is warranted.

### Symptom and Cause Alerts

- **Symptom alert:** API latency breaches SLO, connection acquisition timeouts increase, replication falls behind.
- **Cause alert:** CPU saturation, disk pressure, lock contention, blocked autovacuum.

Symptoms typically indicate that users are currently affected. Causes help pinpoint the root issue. Keep both, while avoiding paging multiple independent alerts for the same incident.

## 4. Define Objectives Before Setting Thresholds

Sources for choosing thresholds:

- Service SLOs/SLIs.
- RPO and RTO.
- Connection budget and `max_connections`.
- Filesystem capacity and growth rate.
- WAL generation rate and retention policy.
- Acceptable replication lag for the workload.
- Backup window and restore objective.
- Query latency/throughput baselines.
- Peak-hour capacity headroom.

### RPO Example

If a DR standby must maintain a 60-second RPO, a replication lag alert should detect the issue earlier than the 60-second breach point, accounting for scrape/evaluation/notification delays and responder reaction time. Setting the threshold right at 60 seconds can detect the problem too late.

### Thresholds Must Have an Owner

Each alert should have an owner responsible for explaining the threshold, verifying it remains appropriate after capacity/workload changes, and keeping the runbook up to date.

## 5. Static Thresholds

A static threshold is a fixed value:

```text
disk_used_percent > 85
active_connections > 180
replication_lag_seconds > 30
```

### Advantages

- Easy to understand and test.
- Easy to explain to on-call responders.
- Well-suited to hard limits or clear policies.
- Does not require long historical data to compute a baseline.

### Limitations

- Can be overly sensitive to workloads that vary by hour.
- Can be too loose on small systems and too strict on large systems.
- A single value does not reflect the rate of change.
- Prone to flapping when a normal metric oscillates near the threshold.

Static thresholds fit resource limits, SLO boundaries, or well-defined policies. They must be calibrated to capacity and workload.

## 6. Relative Thresholds and Dynamic Baselines

Relative thresholds compare a current metric against a baseline or a related metric. For example:

- Query rate drops 70% compared to the same time window last week.
- WAL generation increases 4x compared to the 30-day baseline.
- Connection usage exceeds 90% of the pool budget.
- p95 latency is 3x higher than baseline.

Dynamic baselines can use moving averages, medians, percentiles, seasonal baselines, or anomaly detection models.

### Caution with Baselines

- A baseline polluted by a prolonged incident can mistakenly learn the degraded state as normal.
- Workloads that vary by day/hour require seasonal baselines.
- New systems lack sufficiently long history.
- Metrics with heavily skewed distributions may not suit mean/stddev approaches.
- Dynamic thresholds are hard to interpret if baseline and confidence bands are not displayed.

Do not rely on anomaly detection as the sole safeguard for hard capacity limits.

## 7. Ratio vs. Absolute Thresholds

Disk alerts often require both percentage and remaining free space:

- 90% on a 20 GB volume leaves only 2 GB free.
- 90% on a 10 TB volume leaves 1 TB free.

Conversely, 95% utilization on a small volume can fill very quickly. Combine free bytes and growth rate.

Connection alerts should also use ratios:

\[
\text{connection utilization} =
\frac{\text{current connections}}{\text{usable connection budget}} \times 100\%
\]

Usable budget must subtract reserved connections, admin headroom, replication, and other pooler/backend consumers. Never assume `max_connections` is entirely available to applications.

## 8. Rate-of-Change Thresholds

A metric at 80% may be safe if stable, yet dangerous if rising 5% per minute. Rate-of-change alerts can detect problems before hitting hard limits.

Examples:

- Disk free bytes drop by more than 2 GB in 10 minutes.
- WAL retained distance increases continuously.
- Connection count rises rapidly after a deploy.
- Replication lag climbs across consecutive evaluation windows.

### Time-to-Exhaustion

Estimate:

\[
\text{time to full} =
\frac{\text{free capacity}}{\text{positive consumption rate}}
\]

This is only an approximate forecast. Growth rates can shift abruptly; apply smoothing, enforce a minimum positive rate floor, and verify sufficient sample points.

## 9. What Is a Sampling Interval?

The sampling interval is the spacing between metric collections. In Prometheus, the scrape interval is the cadence at which Prometheus scrapes a target. In other agents or monitoring services, this may be called the collection interval or polling interval.

Examples:

- 5 seconds: collect metrics every 5 seconds.
- 15 seconds: collect every 15 seconds.
- 60 seconds: collect every minute.

### Sampling Too Infrequently

- Can miss short spikes.
- Delays incident detection.
- Leaves rate calculations with few sample points.
- Makes it harder to distinguish a brief outage from stale metrics.

### Sampling Too Frequently

- Increases load on exporters, agents, and the monitoring backend.
- Increases network, storage, and cardinality costs.
- Generates many data points without necessarily improving decisions.
- Makes query and rule evaluation more resource-intensive.

Choose the interval based on how quickly the metric changes and the required response time, rather than forcing every metric onto a single cadence without review.

## 10. Distinguishing Scrape, Evaluation, and Notification Intervals

The following intervals serve distinct roles:

| Interval | Meaning |
|---|---|
| Scrape/collection interval | How often a new sample is collected |
| Evaluation interval | How often alert rules are evaluated |
| Range window | Historical lookback used in an expression, e.g., 5 minutes |
| Pending duration / `for` | How long the condition must remain true continuously before firing |
| Notification `group_wait` | Wait time to batch related alerts before sending |
| `group_interval` | Spacing between update notifications within an existing group |
| `repeat_interval` | Spacing before re-sending notifications for unresolved alerts |

For example: scrape every 15 seconds, evaluate every 30 seconds, expression uses a 5-minute range, and `for` is 3 minutes. This does not guarantee the alert fires exactly 3 minutes after the metric degrades; scrape/evaluation alignment, pending state, and notification delay also contribute.

## 11. Choosing a Scrape Interval

The scrape interval should be fast enough to capture significant changes without creating unnecessary load.

Starting reference ranges:

| Metric class | Reference sampling interval | Rationale |
|---|---:|---|
| Node/DB availability | 5–15 seconds | Relatively fast outage detection |
| Connections, CPU, memory | 15–30 seconds | Track saturation |
| Replication lag | 5–15 seconds for tight RPO; longer if workload allows | Respond within RPO |
| Backup completion/status | 1–5 minutes or event-driven | No need for aggressive polling |
| Capacity growth | 1–5 minutes | Focus on trend rather than spikes |
| Configuration inventory | 5–15 minutes or event-driven | Changes infrequently |

These are starting points, not universal rules. Exporter scrape duration, target count, and backend capacity also constrain practical intervals.

## 12. Choosing an Evaluation Interval

The evaluation interval controls how often the alerting engine evaluates rule expressions. If you scrape every 15 seconds but evaluate every 2 minutes, alerts may detect issues later than expected.

### Practical Guidelines

- Evaluation interval should not be overly long relative to the response objective.
- There is little benefit in evaluating many times faster than new samples arrive.
- Related rules can share an appropriate evaluation group interval.
- Account for query cost when rules run across many series or high cardinality.

An alert detecting imminent disk exhaustion might evaluate every 30–60 seconds; a long-term capacity trend might evaluate every few minutes.

## 13. Range Windows and Rolling Aggregation

A range window is the historical span an expression calculates over. For example, a counter `rate` over a 5-minute window computes the average per-second rate across those 5 minutes.

Short window:

- Reacts quickly.
- Sensitive to noise and bursts.
- May lack sufficient samples if scrapes are sparse or have gaps.

Long window:

- Smooths out noise.
- Reflects more durable trends.
- Can mask short spikes or delay detection.

### Choosing a Window

Select based on metric behavior and impact. API query latency may use a 5-minute window alongside longer SLO windows; disk capacity requires 15–60-minute or multi-hour trends; replication lag may combine instant values with a sustained window.

## 14. Pending Duration and Sustained Conditions

Pending duration requires the condition to stay true for a specified period before the alert transitions to firing.

Prometheus example:

```yaml
groups:
  - name: postgres-capacity
    rules:
      - alert: PostgresDiskUsageHigh
        expr: postgres_filesystem_used_ratio > 0.85
        for: 10m
        labels:
          severity: warning
```

The condition must persist across the pending period before firing. If the metric drops below the threshold earlier, the pending state resets according to the rule engine's semantics.

### Do Not Set Pending Too Long

If a disk has only 2 minutes left before filling, a 15-minute `for` duration is far too late. Pending duration must factor in deterioration speed and response lead time.

### Do Not Set Pending Too Short

Having no pending period can cause alerts to flap rapidly when metrics oscillate. Use sustained conditions for noisy signals, while keeping fast-triggering alerts for hard failures requiring immediate intervention.

## 15. Use `rate` for Counters

Monotonically increasing counters such as transaction commits, WAL bytes, or query counts should not be compared directly against absolute thresholds over time. Use `rate` or `increase` to measure velocity or total change over a window.

PromQL example:

```promql
rate(pg_stat_database_xact_commit[5m])
```

Counting commits over 5 minutes:

```promql
increase(pg_stat_database_xact_commit[5m])
```

### Counter Resets

PostgreSQL restarts or stats resets can drop a counter back to 0. Prometheus `rate` handles counter resets according to its semantics; do not naively subtract the previous sample from the current sample.

### Gauges vs. Counters

CPU utilization, active connections, disk free bytes, and replication lag are typically gauges. They can go up or down; use appropriate comparisons and aggregations rather than defaulting to `rate`.

## 16. Percentiles and Averages

Average latency can hide tail latency. A system with many fast requests and a smaller set of extremely slow requests can still show an acceptable mean.

Track:

- p50: typical experience.
- p95: common tail latency covering most requests.
- p99: more severe tail latency.
- Error rate and throughput for additional context.

With Prometheus histograms, compute `histogram_quantile` over bucket rates. Do not compute fleet percentiles by averaging per-instance p95 values; aggregate bucket counts first, then compute the quantile.

## 17. Role-Aware and Node-Aware Thresholds

Do not apply identical alerts to primaries and standbys when their operational meanings differ.

Examples:

- High connection utilization on a primary can threaten write ingestion.
- High connection utilization on a standby may affect read traffic without directly blocking writes.
- Replay lag on a primary is not a standard signal like standby replay lag.
- WAL receiver down on a standby means something very different from having no WAL receiver on a primary.

Attach labels such as `cluster`, `node`, `role`, `environment`, and `service`. Alert expressions should filter/group by the appropriate role; do not infer role from hostnames when topology can change after failover.

## 18. Thresholds for PostgreSQL Connections

`pg_stat_activity` shows active sessions; `max_connections` is a configured limit, though applications should never consume all of it.

Inspect:

```sql
SELECT
    count(*) AS current_connections,
    current_setting('max_connections')::integer AS max_connections,
    count(*) FILTER (WHERE state = 'active') AS active_connections,
    count(*) FILTER (WHERE state = 'idle') AS idle_connections,
    count(*) FILTER (
        WHERE state = 'idle in transaction'
    ) AS idle_in_transaction
FROM pg_catalog.pg_stat_activity;
```

### Suggested Thresholds

- Warning when utilization exceeds roughly 70–80% of usable budget for several minutes.
- Critical when exceeding roughly 90% of usable budget or when connection failures occur.
- Separate alerts for prolonged `idle in transaction` sessions and unusual spikes in count.

These are starting points. Calculate usable budget after accounting for reserved slots, monitoring, replication, poolers, and admin reserve. Track application-side connection acquisition timeouts to detect direct impact.

## 19. Thresholds for Replication Lag

Replication lag should be anchored to RPO and workload. You can measure:

- WAL byte distance between primary and standby.
- Receive lag: WAL not yet received/flushed.
- Replay lag: WAL received but not yet applied.
- Timestamp of the most recently replayed transaction.
- WAL receiver status and last message receipt time.

On a standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_last_wal_receive_lsn(),
            pg_last_wal_replay_lsn()
        )::bigint
    ) AS receive_replay_distance,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

### RPO-Based Alerting

For a maximum RPO of 60 seconds, a warning might trigger at 20–30 seconds sustained, and critical at 45–50 seconds or based on remaining reaction time. Factor measurement and notification delays into thresholds; never wait until RPO is breached before paging.

### Idle Primary Caveat

`pg_last_xact_replay_timestamp()` can appear stale when the primary produces no new transactions. Combine LSN positions, WAL receiver timestamps, and workload activity to avoid false lag alerts during idle periods.

## 20. Thresholds for Disk and Filesystem

Disk alerts should combine utilization, free bytes, growth rate, and time-to-full.

Example:

| Severity | Reference condition |
|---|---|
| Warning | Used > 80% sustained for 10 minutes, or free space below capacity buffer |
| Critical | Used > 90–95%, or projected full sooner than response time |
| Immediate page | Filesystem read-only, write failures, or PostgreSQL unable to write WAL |

Thresholds depend on volume size, data growth rate, and the time needed to expand or clean up storage.

### PostgreSQL Directories

Monitor separately:

- `PGDATA`.
- `pg_wal`.
- Tablespaces.
- WAL archive staging/cache.
- Backup destination.
- Filesystems holding logs/temp files.

A single filesystem can fill up even when overall host disk utilization remains low. Scope alerts by mount point and service role.

## 21. Thresholds for Replication Slots and WAL Retention

Replication slots retain WAL when a consumer is slow or inactive. A long-inactive slot can cause `pg_wal` to grow until the disk fills.

On the primary:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Some columns such as `wal_status` and `safe_wal_size` are only available in newer PostgreSQL versions; adapt the query to your version.

### Alert Design

- Alert when a slot expected to have an active consumer remains inactive too long.
- Alert when retained WAL distance grows rapidly.
- Alert when `safe_wal_size` drops low on versions supporting this column.
- Alert on free disk / time-to-full for the filesystem hosting `pg_wal`.

Do not alert merely because a slot is inactive for a few seconds if brief disconnects are normal in its workflow. Associate each slot with an owner, expected activity, and retention policy.

## 22. Thresholds for Locks and Blocking

Brief lock waits can be normal. A long-lived blocker holding up multiple transactions and driving up request latency is a critical signal.

Query to find lock-waiting sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 200) AS query_text
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### Suggested Thresholds

- Warning when lock wait duration exceeds the workload SLO for several minutes.
- Critical when a single blocker stalls multiple sessions or grows the transaction queue.
- Separate alerts for long-running transactions and `idle in transaction` sessions.

Do not page on every lock wait. Consider waiter count, blocker age, query impact, and lock type.

## 23. Thresholds for Query Latency and Errors

Query latency should be measured at the application or database instrumentation layer with sufficient context. Use p95/p99 per endpoint or workload class rather than a single cluster-wide average.

Alerts can combine:

- p95/p99 latency breaching SLO.
- Error rate exceeding budget.
- Throughput dropping while request volume stays steady.
- Pool acquisition time rising.
- Concurrent spikes in DB CPU/locks/I/O pressure.

### Query-Level Metrics

`pg_stat_statements` helps analyze total execution time, calls, rows, and block I/O per normalized query. Stats can reset on restarts or manual resets; compute deltas/rates properly and avoid alerting on cumulative totals.

## 24. Thresholds for Autovacuum and Bloat Signals

No single simple metric accurately measures all forms of bloat. Track:

- Dead tuple estimates.
- Transaction / XID age.
- Autovacuum activity and duration.
- Tables that have gone long without vacuuming.
- Long-running transactions pinning old snapshots.
- Abnormal table/index growth.
- Transaction ID wraparound risk.

A table showing a high dead tuple ratio briefly after a bulk update can be normal. Alerts should weigh trends, XID age, autovacuum progress, and impact on disk or query latency.

### XID Age

Transaction ID age approaching the wraparound limit is a severe risk. Because this is a hard safety boundary, alert on thresholds with generous headroom rather than relying solely on anomaly baselines.

## 25. Thresholds for Backups and Archiving

Backup monitoring should detect:

- A backup job failing to start on schedule.
- A backup failing or exiting abnormally.
- Backup duration exceeding the backup window.
- WAL archive failures or growing archive backlogs.
- No recent valid backup within the retention policy.
- Overdue restore verification/drills.

### Missing Success Events

Do not alert only on explicit job failures. If a job never runs or monitoring receives no completion event, alert past the expected schedule/deadline.

### Backup Freshness

Alert based on the timestamp of the last successful backup combined with WAL archive continuity. A "green" backup job is insufficient if subsequent WAL segments are missing or the restore chain is invalid.

## 26. Thresholds for CPU, Memory, and I/O

CPU:

- Sustained high utilization.
- CPU steal/pressure in virtualized environments.
- Growing run queue.
- Impact on query latency/throughput.

Memory:

- Low available memory.
- Rising swap activity.
- OOM events.
- PostgreSQL memory pressure correlated with connection count/workload.

Disk I/O:

- Rising latency / read-write await times.
- Increasing queue depth.
- Throughput hitting volume limits.
- Checkpoint / WAL write pressure.

Do not page merely because CPU or I/O touches a high percentage briefly. Pair saturation duration with user-facing symptoms and workload context.

## 27. Workload-Baseline Thresholds

Workloads exhibit seasonality: daytime traffic differs from nighttime, weekends differ from weekdays, and batch windows differ from API peak hours.

Baselines can be segmented by:

- Time of day / day of week.
- Service / workload class.
- Primary / standby role.
- Region / environment.
- Deployment version.

### Avoid Learning Incidents as Normal

If a baseline updates continuously during an active incident, the system can gradually accept degraded behavior as normal. Freeze baselines during incidents or exclude anomalous periods from training windows.

### Use Robust Statistics

Medians and percentiles are generally more resilient than means when metrics contain spikes. A band like median ± k×MAD can serve as an anomaly signal, provided distribution shape and seasonality are checked.

## 28. Hysteresis and Recovery Thresholds

Hysteresis uses two distinct thresholds for firing and recovery to prevent rapid toggling around a single boundary.

Example:

- Fire when disk utilization > 85%.
- Resolve when disk utilization < 80%.

The gap creates a deadband for stability. Your alerting engine may support dedicated recovery thresholds or require equivalent expression/state logic.

### State Machine Example

```text
NORMAL
  | metric > 85% sustained
  v
FIRING
  | metric < 80% sustained
  v
NORMAL
```

### Why Is This Useful?

A metric fluctuating across 84.9%, 85.1%, 84.8%, 85.2% will not repeatedly fire and resolve. Hysteresis reduces notification noise and keeps alert states stable.

## 29. Multi-Condition Alerts

A single condition can produce false positives. You can require multiple corroborating signals together:

- High CPU AND high query latency.
- High replication lag AND stale WAL receiver.
- High connection utilization AND rising pool acquisition timeouts.
- High disk usage AND dangerous free-space burn rate.

### Do Not Over-Correlate

If every signal must hold simultaneously, an alert can miss an incident when one exporter fails or another metric is unavailable. Use multi-condition logic for symptom confidence, while keeping hard-limit alerts independent.

## 30. No Data Is Not Zero

Having no samples does not mean a metric equals 0. A crashed exporter, scrape timeout, network partition, or removed target can make metrics disappear.

Distinguish:

- Zero: samples exist and their value is 0.
- No data: no samples exist in the window.
- Stale: series is no longer updated or has been marked stale.
- Scrape failure: Prometheus cannot collect metrics from the target.

### Alerting on the Monitoring Pipeline

Track `up`, scrape duration, scrape sample counts, and target discovery. If the PostgreSQL exporter vanishes, an alert reading "connections = 0" is misleading; maintain dedicated alerts for exporter/target unavailability.

### Missing-Data Policy

Every alert should define whether no data represents:

- Unknown / insufficient evidence.
- Target down requiring a page.
- A metric inapplicable to this role.
- A monitoring pipeline failure.

Never silently coerce no data into healthy.

## 31. Scrape Gaps and Sample Freshness

Scrapes can fail for one or several cycles. A query using a sufficiently wide range window may still return results from older samples. While helpful for smoothing, this can mask a target that has stopped updating.

### Design Practices

- Monitor scrape success independently of database metrics.
- Alert when last sample age exceeds a limit.
- Choose appropriate range windows and verify sample counts.
- Distinguish an intentionally absent target from an unexpected disappearance.
- Do not casually use `or vector(0)` in ways that conceal missing series.

## 32. Scrape Timeouts and Exporter Overload

Scrape timeouts should be shorter than the scrape interval and appropriate for how long the exporter takes to query metrics. An exporter querying many catalogs/views or `pg_stat_statements` on a large cluster can take significant time.

Monitor:

- Scrape duration.
- Scrape timeout / failure counts.
- Exporter CPU and memory.
- Exported metric/series counts.
- PostgreSQL load generated by monitoring queries.

If scrape duration persistently approaches the interval, widen the interval, tune exporter collectors, or reduce cardinality before merely raising the timeout.

## 33. Cardinality and Alert Noise

High label cardinality increases storage/query costs and can spawn thousands of alert instances.

Avoid labeling by:

- Raw SQL text or query parameters.
- User ID / request ID.
- Unbounded dynamic table names.
- Session PID on long-lived alerts.
- Full error messages that vary continuously.

Keep labels stable, such as `cluster`, `node`, `role`, `environment`, `service`, and `severity`. Leave per-query or per-session details for dashboards and diagnostic runbooks.

## 34. Severity and Actionability

A simple model:

| Severity | Meaning | Action |
|---|---|---|
| Info | Notable change, no intervention needed yet | Dashboard/log |
| Warning | Growing risk, address during business hours | Ticket/chat |
| Critical | User impact or imminent risk | Page on-call |
| Emergency | Service outage or immediate threat to data safety | Incident response |

Severity must reflect impact and urgency of response, not metric names. For instance, 80% disk might be Warning; a read-only filesystem on the primary can be Emergency.

### Alerts Need Runbooks

Every paging alert should include:

- Triggered condition.
- Cluster / node / role.
- Start time and duration.
- Relevant dashboard links.
- Diagnostic queries/commands.
- Safe initial mitigation steps.
- Escalation owner.

## 35. Alert Grouping and Deduplication

A single incident can emit many alert instances: every database, node, or replica may report the same symptom. Grouping consolidates notifications by cluster/service/alertname.

### Group by Stable Labels

For example, group by:

- `alertname`.
- `cluster`.
- `environment`.
- `service`.

Do not group so broadly that two unrelated incidents merge, nor so narrowly that each node triggers a separate page.

### Deduplication

Your notification system should recognize identical alert fingerprints to prevent duplicate sends. Repeat notifications can remind responders about unresolved alerts, but at reasonable intervals that avoid spam.

## 36. Inhibition and Dependency Suppression

If both a PostgreSQL node and its exporter go down together, an exporter scrape failure alert may simply be a consequence of the node outage. Inhibition suppresses downstream alerts when a higher-level root alert is firing.

Examples:

- Cluster unavailable suppresses per-database query latency alerts.
- Node down suppresses node CPU/disk alerts caused by missing samples.
- Primary failover in progress suppresses expected transient connection churn warnings.

### Do Not Suppress Too Broadly

Overly broad inhibition can hide independent incidents. Suppress only when the source alert truly explains the target alert and matching scope labels align.

## 37. Maintenance Windows and Silences

A maintenance silence mutes notifications for a scheduled window without eliminating the underlying metric or alert condition.

A silence should specify:

- Explicit start and end times.
- Exact scope labels.
- Owner.
- Ticket/change reference.
- Reason.

### Never Silence Indefinitely

Silences without expiry can mask real incidents long after maintenance ends. Enforce automatic expiration and audit active silences regularly.

### Maintenance Is Not a Fix for False Positives

If an alert repeatedly false-alarms outside maintenance, fix its threshold, window, or condition. Do not create recurring silences to hide alert noise.

## 38. Prometheus Alert Rule: CPU and Connections

Illustrative example:

```yaml
groups:
  - name: postgres-saturation
    interval: 30s
    rules:
      - alert: PostgresConnectionsHigh
        expr: |
          postgres_connections_used
          / postgres_connections_usable > 0.80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL connection budget is high
          description: |
            Connection usage has exceeded 80% for five minutes.
            Check pool queues, idle transactions and connection leaks.

      - alert: PostgresConnectionsCritical
        expr: |
          postgres_connections_used
          / postgres_connections_usable > 0.92
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL is close to connection exhaustion
          description: |
            Check connection acquisition failures and preserve admin headroom.
```

Metric names here represent normalized exporter or recording-rule series; substitute your actual metric names. Guard against zero denominators or missing metrics, and maintain separate rules verifying metric availability.

## 39. Prometheus Alert Rule: Replication Lag

Example using a metric expressing lag in seconds:

```yaml
groups:
  - name: postgres-replication
    interval: 15s
    rules:
      - alert: PostgresReplicaLagWarning
        expr: postgres_replication_lag_seconds > 20
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL replica lag is increasing
          description: |
            Replica lag has remained above 20 seconds.
            Check WAL receiver, network and replay capacity.

      - alert: PostgresReplicaLagCritical
        expr: postgres_replication_lag_seconds > 45
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL replica is near the RPO limit
          description: |
            Check primary WAL generation, standby replay and slot retention.
```

Values of 20 and 45 seconds illustrate a system with roughly a 60-second RPO. Adjust based on your RPO, scrape/evaluation delay, notification latency, and response time.

## 40. Prometheus Alert Rule: Scrape Health and No Data

Example:

```yaml
groups:
  - name: postgres-monitoring
    rules:
      - alert: PostgresExporterDown
        expr: up{job="postgres-exporter"} == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL exporter is unavailable

      - alert: PostgresExporterTargetMissing
        expr: absent(up{job="postgres-exporter"})
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL exporter target is missing
```

`absent` semantics depend on label selectors and target discovery. Across multiple clusters or targets, evaluate per-cluster series or recording rules so alerts do not conflate clusters. A missing target alert often signals service discovery issues, distinct from an exporter returning `up=0`.

## 41. Prometheus: Rates and Multi-Window Expressions

Counter error-rate example:

```promql
sum(rate(api_requests_total{status=~"5.."}[5m]))
/
sum(rate(api_requests_total[5m]))
```

This measures the 5xx ratio over 5 minutes. Guard against zero denominators and scope by service labels.

### Multi-Window Conditions

You can require the error ratio to breach thresholds across both short and long windows:

```promql
(
  sum(rate(api_requests_total{status=~"5.."}[5m]))
  /
  sum(rate(api_requests_total[5m]))
) > 0.05
and
(
  sum(rate(api_requests_total{status=~"5.."}[1h]))
  /
  sum(rate(api_requests_total[1h]))
) > 0.02
```

The short window catches active incidents quickly; the long window confirms sustained impact. In production, add zero-denominator guards, service labels, and low-traffic rules.

## 42. SLO Burn-Rate Alerts

An error budget is the allowed error allowance over an SLO window. Burn rate measures how fast the error budget is being consumed relative to the sustainable rate.

For example, a 99.9% availability SLO over 30 days gives a 0.1% error budget. If errors run many times faster than budget rate, the budget exhausts prematurely.

### Why Use Burn Rate?

- Ties alerts directly to user-facing reliability.
- Detects high-impact incidents even when raw error rates look modest.
- Enables multi-window alerting balancing speed and precision.
- Cuts noisy infrastructure alerts that cause no user impact.

### Multi-Burn-Rate

A common pattern pairs short and long windows with distinct burn-rate thresholds for fast-burn vs. slow-burn incidents. Choose windows and thresholds from your SLO window, page budget, and response model rather than copying universal numbers.

## 43. Notification Timing in Alertmanager

Alertmanager grouping/routing introduces timings such as:

- `group_wait`: wait before sending the initial notification for a new alert group.
- `group_interval`: wait before sending updates for an existing group.
- `repeat_interval`: interval before re-notifying an unresolved alert.

These timings add to end-to-end notification latency without changing rule pending durations.

Example:

```yaml
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

Tune timings to incident urgency. Critical pages need a short `group_wait`; warnings/tickets can batch longer.

## 44. Separating Alert Evaluation Delay from Response Delay

Elapsed time from metric degradation to an on-call page includes:

1. Waiting for the next scrape sample.
2. Waiting for the evaluation cycle.
3. Pending duration (`for`).
4. Alertmanager `group_wait` and routing.
5. Notification provider delivery.

Estimate:

\[
\text{detection-to-page} \approx
\text{scrape delay} +
\text{evaluation delay} +
\text{pending duration} +
\text{notification delay}
\]

This is an approximation; phases can overlap or drift out of phase. Measure real end-to-end latency with synthetic test alerts.

### RPO Headroom

With a 60-second RPO, a rule pending for 60 seconds plus scrape, evaluation, and notification delays pages after the objective is already breached. Leave headroom in both thresholds and pending durations for detection and mitigation.

## 45. Reducing False Positives with Sustained Conditions

A single sample spike rarely justifies paging. Use:

- `for` duration.
- Moving averages or rates.
- Minimum sample counts.
- Window percentiles.
- Corroborating conditions.

For example, CPU above 90% sustained for 10 minutes is far more reliable than a single 95% sample. However, hard failures like service outages or read-only filesystems should not wait 10 minutes.

### Choosing Duration by Failure Mode

- Outage: fast detection, short or zero pending duration.
- Connection saturation: a few minutes to filter brief bursts.
- Disk exhaustion: base on time-to-full rather than sustained percentage alone.
- Missed backup: trigger past the scheduled deadline.
- Capacity trends: longer evaluation windows.

## 46. Reducing False Positives with Hysteresis

When firing and recovery thresholds are identical, metrics hovering near the boundary cause flapping. Separate firing and recovery thresholds or add recovery durations where supported.

Example:

- Fire when lag > 30 seconds for 2 minutes.
- Resolve when lag < 15 seconds for 3 minutes.

This prevents immediate resolve-and-refire loops when lag hovers around 30 seconds.

### Observe Recovery Too

Do not resolve immediately on a single good sample before the system stabilizes. Use a recovery window, while ensuring alerts do not stay open long after impact clears.

## 47. Reducing False Positives with Context

Combine related signals:

- High CPU + high latency.
- High disk utilization + low free bytes.
- High lag + stale WAL receiver.
- High connections + pool acquisition timeouts.
- High query error rate + meaningful request volume.

### Low Traffic

One failed request out of two gives a 50% error ratio. Add minimum request volume or minimum error count guards alongside ratios. For low-traffic critical services, synthetic probes are often more effective.

## 48. Reducing False Positives with Maintenance and Deployment Context

Deployments, backups, index builds, vacuuming, failovers, and planned maintenance naturally produce metric spikes.

Practices:

- Annotate dashboards with deployment and change events.
- Scope silences tightly by labels with explicit expiry times.
- Inhibit downstream symptom alerts once a higher-level root alert fires.
- Alert separately if maintenance exceeds its expected window.
- Never suppress hard safety alerts like disk exhaustion or XID wraparound risk.

### Keep Silences Narrow

Target the exact cluster, node, and alert name with a strict end time. Never silence all PostgreSQL alerts globally for a single node maintenance window.

## 49. Reducing False Positives with Seasonal Baselines

If a nightly batch job at 02:00 creates expected WAL and CPU spikes, a static threshold will page daily. You can:

- Define explicit batch/maintenance windows.
- Compare against same-hour historical baselines.
- Build workload-specific alert rules.
- Alert when batch duration or volume exceeds expected bounds.

Do not suppress the entire batch window blindly; you still need to detect abnormally slow batches or user-facing SLO degradation.

## 50. False Negatives and Overly Loose Thresholds

Cutting false positives must never blind detection. Overly high thresholds, excessive pending durations, or broad suppressions create false negatives.

Audit for:

- Incident history: did alerts fire before user impact?
- Synthetic failures: do alerts fire under injected test faults?
- Threshold margins: is there enough lead time before hard limits?
- No-data behavior: is a missing exporter mistakenly treated as healthy?
- Maintenance suppressions: are critical unrelated alerts hidden?

Test every alert for both firing and recovery behavior.

## 51. Alert Flapping

Flapping occurs when an alert toggles repeatedly between firing and resolved over short spans.

Causes:

- Threshold set too close to normal baseline.
- Scrape gaps or noisy samples.
- Evaluation running too fast relative to metric smoothing.
- Missing hysteresis.
- Alert expressions tied to shifting series cardinality.
- Node roles swapping during failover.

Reduce flapping with sustained durations, recovery thresholds, robust aggregations, stable labels, and role-aware rules.

## 52. Alert Fatigue and Notification Policy

Alert fatigue sets in when responders receive too many low-actionability notifications, causing critical alerts to be ignored or delayed.

Reduce fatigue:

- Page only for issues requiring after-hours action.
- Route Warnings to tickets or chat instead of pages.
- Group related alerts belonging to one incident.
- Deduplicate by fingerprint.
- Inhibit redundant downstream alerts.
- Remove or fix alerts lacking owners or runbooks.
- Review false positives and false negatives in post-incident reviews.

Never treat alert fatigue by muting everything or raising thresholds indiscriminately.

## 53. Alert Quality Metrics

Track alert quality as part of your observability program:

- False-positive rate: share of alerts requiring no action.
- False-negative count: incidents lacking timely alerts.
- Precision: share of alerts indicating genuine issues.
- Time to detect (TTD).
- Time to acknowledge (TTA).
- Time to mitigate/resolve.
- Pages per on-call shift.
- Repeated/flapping alert count.
- Alerts missing owners or runbooks.

Define false positives consistently: no impact, no action needed, or auto-resolved transient noise? Record alert dispositions after every incident and periodic review.

## 54. Reviewing and Tuning Thresholds

Thresholds are not set-and-forget configurations. Review after:

- Workload growth or traffic pattern shifts.
- Changes to `max_connections`, storage, or replica topology.
- Migrations or exporter upgrades.
- Failover/restore drills.
- Real incidents or recurring false alarms.
- Updated SLO, RPO, or RTO targets.

### Tuning Workflow

1. Gather alert history and raw metric timelines.
2. Identify why the alert fired.
3. Cross-check user impact and response timing.
4. Adjust threshold, range window, `for` duration, or hysteresis.
5. Replay historical data if supported.
6. Test against synthetic conditions.
7. Deploy versioned rule changes and monitor.
8. Document owner and rationale.

Avoid changing many thresholds simultaneously when you cannot tell which adjustment improved behavior.

## 55. PostgreSQL Exporters and Monitoring Load

Exporters query catalogs and views to gather metrics. Expensive collectors running too often can add load to an already stressed database.

Track:

- Exporter query duration.
- Scrape duration and timeouts.
- Exported metric/series count.
- PostgreSQL CPU spent on monitoring queries.
- Locks/waits involving the monitoring role.

### Least Privilege

Use a dedicated monitoring role with only required privileges, avoiding superuser whenever unnecessary. Some metrics require predefined monitoring roles or specific grants; follow exporter and PostgreSQL version documentation.

## 56. Prometheus Recording Rules

Recording rules precompute frequent expressions so dashboards and alerts do not recalculate across huge series sets on every query.

Example:

```yaml
groups:
  - name: postgres-recording
    interval: 30s
    rules:
      - record: postgres:connection_utilization:ratio
        expr: |
          postgres_connections_used
          / postgres_connections_usable

      - record: postgres:replica_lag:max_seconds
        expr: max by (cluster) (postgres_replication_lag_seconds)
```

Recording rules must preserve essential labels and handle missing/zero denominators. Never aggregate away `node` or `role` labels needed for diagnosis.

## 57. Testing Alert Rules

Test alerts using controlled data or scenarios:

- Unit test PromQL/rule expressions.
- Replay historical time series.
- Inject synthetic metrics crossing thresholds.
- Deliberately simulate an exporter outage in staging.
- Induce replication lag in a lab.
- Safely simulate disk pressure.
- Verify firing, notification routing, and resolution.

### Never Run Destructive Tests in Production

Never fill production filesystems, kill a production primary, or delete WAL just to verify an alert. Use staging, bounded fault injection, or synthetic series.

## 58. Alert Rule Lifecycle

Every alert should have:

- A clear, searchable name.
- Description of symptom and impact.
- Labels for severity, cluster, role, and service.
- Annotations linking runbooks and dashboards.
- An explicit owner.
- Threshold rationale.
- Test coverage.
- Review dates or change history.

When retiring an alert, confirm it is no longer routed or is cleanly superseded. Never leave old rules silently firing into dead routes.

## 59. Runbook: Investigating False Positives

1. Record alert fingerprint, labels, and start/end timestamps.
2. Inspect raw metric samples around the firing window.
3. Check scrape gaps, exporter logs, and staleness.
4. Compare with workload, deployment, and maintenance timelines.
5. Inspect threshold, range window, and pending duration.
6. Confirm whether real user impact or action occurred.
7. Identify the noise driver: spike, seasonality, missing data, cardinality, or threshold.
8. Prototype adjustments in staging or historical replay.
9. Test both firing and recovery paths.
10. Update owner, runbook, and rationale.

## 60. Runbook: Alert Failed to Fire During an Incident

1. Identify user symptom/impact and incident start time.
2. Check whether the metric was scraped during the window.
3. Check target labels and series identity.
4. Evaluate the alert expression directly at the incident timestamp.
5. Inspect range window and sample counts.
6. Inspect pending duration, evaluation interval, and rule group errors.
7. Inspect no-data/staleness behavior.
8. Inspect inhibition, silences, and routing.
9. Replay the incident timeline if historical data exists.
10. Fix the rule and add a synthetic test proving it fires.

## 61. Runbook: Replication Lag Alert

1. Identify affected cluster, primary, and standby.
2. Inspect `pg_stat_wal_receiver` status and last message timestamp.
3. Compare receive LSN vs. replay LSN.
4. Inspect WAL senders via `pg_stat_replication` on the primary.
5. Check network, CPU, I/O, and long-running standby queries.
6. Check replication slot retained WAL and free disk.
7. Compare lag against RPO and alert thresholds.
8. Escalate immediately if RPO is breached.
9. Verify lag drops and the alert resolves per recovery thresholds.
10. Check whether sampling or pending delays slowed detection.

## 62. Runbook: Disk Capacity Alert

1. Identify the filesystem/mount point and PostgreSQL directory.
2. Check free bytes, utilization, and growth rate.
3. Check `pg_wal` and replication slots.
4. Check archive backlogs and failed archive jobs.
5. Check tablespace/data growth and temporary files.
6. Estimate time-to-full.
7. Execute cleanup or expansion steps per approved runbook.
8. Never delete WAL or database files manually.
9. Monitor free space and PostgreSQL write health afterward.
10. Adjust warning thresholds if headroom proved insufficient.

## 63. Runbook: Alert Flapping

1. Review state transition history and raw samples.
2. Check whether the threshold boundary sits too close to baseline.
3. Review scrape and evaluation intervals.
4. Check whether series or labels vanish and reappear.
5. Add hysteresis or explicit recovery durations.
6. Use smoother aggregations or wider range windows.
7. Keep hard-failure alerts fast-reacting.
8. Test firing and recovery via replay.
9. Monitor notification volume after deployment.
10. Document any trade-off in detection delay.

## 64. Runbook: No Data or Exporter Down

1. Confirm whether the target was expected to exist at that time.
2. Check Prometheus target discovery and scrape status.
3. Check network, DNS, TLS, and the exporter process.
4. Check exporter connectivity to PostgreSQL.
5. Inspect exporter query durations and permissions.
6. Distinguish database down from exporter down.
7. Restore metric collection.
8. Confirm downstream alerts were not suppressed improperly.
9. Verify sample freshness returns to normal.
10. Assess the monitoring blind spot during the incident.

## 65. Alert Design Checklist

### Meaningfulness

- Alert ties to impact, SLO, RPO, or capacity.
- Owner and recipient are defined.
- Specific actions and runbooks are linked.
- Severity matches required response urgency.

### Thresholds and Timing

- Static/dynamic threshold choice has clear rationale.
- Sampling interval is fast enough without overloading targets.
- Evaluation interval aligns with detection objectives.
- Range window matches metric behavior.
- Pending duration preserves response headroom.
- Hysteresis or recovery conditions prevent flapping.

### Data Integrity

- Counters use `rate`/`increase` properly.
- No data is distinguished from zero.
- Scrape failures and staleness are monitored.
- Counter resets and missing labels are handled.
- Label cardinality is bounded.

### Notifications

- Grouping and deduplication are tuned.
- Inhibition never masks independent incidents.
- Silences carry expiry times and owners.
- Critical alerts are not delayed excessively.

### Operations

- Firing and recovery paths are tested.
- Alert history is reviewed regularly.
- False positives and false negatives are tracked.
- Thresholds are updated after capacity or workload changes.

## 66. Practice Exercises

### Exercise 1 — Metrics and alerts

Distinguish metric, threshold, condition, alert, and notification using PostgreSQL connection usage as an example.

### Exercise 2 — Impact

Primary CPU hits 95% for 20 seconds while latency stays normal. Why should this not necessarily page? What corroborating signals make an alert more reliable?

### Exercise 3 — Static thresholds

List advantages and limitations of a fixed 85% disk usage threshold.

### Exercise 4 — Dynamic baselines

A batch job creates a daily WAL spike at 02:00. Design a baseline approach that catches abnormal spikes without paging every night.

### Exercise 5 — Relative thresholds

Query rate drops 70% vs. baseline while overall traffic also drops 80%. Why is extra context required before paging?

### Exercise 6 — Absolute and ratio

Two volumes are both at 90% used: one has 2 GB free and the other has 1 TB free. Design an alert combining percentage, free bytes, and growth rate.

### Exercise 7 — Time-to-full

A filesystem has 12 GB free and grows by 600 MB every 5 minutes. Estimate time-to-full and propose a warning threshold with headroom.

### Exercise 8 — Sampling intervals

Choose scrape intervals for availability, replication lag, backup status, and capacity growth. Explain the trade-offs.

### Exercise 9 — Evaluation intervals

Prometheus scrapes every 15 seconds yet evaluates every 2 minutes. How does this affect detection delay?

### Exercise 10 — Range windows

Compare `rate` of a counter over a 1-minute vs. 15-minute window in terms of responsiveness and noise.

### Exercise 11 — Pending duration

A disk alert uses `for: 20m` while the disk can fill in 10 minutes. Why is this configuration unsafe?

### Exercise 12 — Counter resets

A PostgreSQL restart resets stats counters. Why use `rate`/`increase` instead of subtracting two raw samples?

### Exercise 13 — Percentiles

Mean latency is 50 ms while p99 is 2 seconds. Why can an average-latency alert miss user impact?

### Exercise 14 — Role-aware thresholds

Design distinct connection saturation alerts for primary vs. standby instances.

### Exercise 15 — Connections

Write SQL computing current connections, active, idle, `idle-in-transaction`, and utilization against usable budget.

### Exercise 16 — Replication lag

A system has a 60-second RPO. Propose warning/critical thresholds, pending durations, and notification headroom.

### Exercise 17 — Idle primary

Why does an old `pg_last_xact_replay_timestamp` not always mean replica lag? Which metrics should be combined?

### Exercise 18 — Replication slots

Design alerts for inactive slots, rising retained WAL, and low `safe_wal_size`.

### Exercise 19 — Disk directories

List PostgreSQL filesystems to monitor individually and explain why host-wide total disk usage is insufficient.

### Exercise 20 — Locks

Write a query finding lock-waiting sessions, blocker PIDs, and query ages. Propose paging conditions.

### Exercise 21 — Autovacuum

Design alerts for slow autovacuum and high XID age. Distinguish normal noise from wraparound risk.

### Exercise 22 — Backup freshness

Design alerts for missed/overdue backups and rising WAL archive backlogs.

### Exercise 23 — No data

Distinguish zero values, no data, stale samples, and scrape failures. Write a policy for disappearing exporters.

### Exercise 24 — Scrape timeouts

An exporter scrape takes 12 seconds under a 15-second interval. Which metrics should you inspect before tightening the interval?

### Exercise 25 — Cardinality

Why should raw SQL or request IDs never appear in alert labels? Propose stable labels instead.

### Exercise 26 — Severity

Classify severity for: 80% disk, 95% disk, read-only primary filesystem, 20-second replica lag under a 60-second RPO, and exporter down.

### Exercise 27 — Hysteresis

Design an 85% firing threshold and 80% recovery threshold. Explain how it prevents flapping.

### Exercise 28 — Multi-condition

Create an alert firing on high connection utilization combined with rising pool acquisition timeouts. Note the risk of requiring both signals.

### Exercise 29 — Error ratios

A service has 1 failed request out of 2 total requests. Why should a 50% error ratio not page immediately? Design a minimum-volume guard.

### Exercise 30 — Maintenance silences

Draft a 30-minute maintenance silence policy specifying owner, scope, and expiry. Which alerts must never be suppressed?

### Exercise 31 — Grouping

A cluster has 10 replicas all reporting lag. Design Alertmanager `group_by` rules to cut notification noise while preserving node visibility.

### Exercise 32 — Inhibition

When a cluster goes down, both exporter-down and query-latency alerts fire. Design inhibition rules without hiding independent incidents.

### Exercise 33 — Prometheus rules

Write an alert rule for connections > 80% for 5 minutes (warning) and > 92% for 2 minutes (critical).

### Exercise 34 — Multi-window SLO

Design an error-rate alert using 5-minute and 1-hour windows. Explain how the two windows complement each other.

### Exercise 35 — Detection-to-page

Given 15s scrape, 30s evaluation, 3m pending, and 30s `group_wait`, estimate delay components and explain phase alignment effects.

### Exercise 36 — False positive review

A CPU alert fires nightly during a batch window with zero user impact. Outline the investigation and tuning process.

### Exercise 37 — False negatives

A disk fills up without alerting because the exporter dropped metrics. Design no-data and monitoring-pipeline alerts.

### Exercise 38 — Alert flapping

Replication lag oscillates around 30 seconds, causing continuous fire/resolve transitions. Design pending and recovery hysteresis.

### Exercise 39 — Alert quality

Design a dashboard measuring false-positive rate, TTD, pages per shift, flapping, and alerts missing runbooks.

### Exercise 40 — End-to-End PostgreSQL Alerting Design

A system includes:

- One primary and two physical standbys.
- 60-second DR RPO.
- 99.9% 30-day API availability SLO.
- Primary `max_connections` = 300.
- 500 GB remaining on the `PGDATA`/`pg_wal` disk.
- Strong hourly variation in WAL generation.
- Nightly backups with continuous WAL archiving.
- Exporter scrapes occasionally taking multiple intervals during peak database load.
- Reporting workloads potentially causing lag on one standby.

Design:

1. Metric inventory and labels for cluster/node/role/workload.
2. Scrape/evaluation intervals per metric class.
3. Warning/critical thresholds for connections, disk, WAL slots, and replication lag.
4. Range windows, pending durations, and hysteresis.
5. No-data, staleness, and exporter availability alerts.
6. SLO burn-rate alerts for the API.
7. Grouping, inhibition, severity, and maintenance silences.
8. Runbooks for lag, disk, backups, and pool saturation.
9. Synthetic tests/replays validating both firing and recovery.
10. A process for reviewing false positives/negatives and retuning after capacity growth.

## Conclusion

**A strong alert reflects real risk or user impact, carries justified thresholds and timing, and guides the recipient to concrete action.** Static thresholds suit hard limits; dynamic baselines help seasonal workloads without replacing safety boundaries. Sampling, evaluation, range windows, pending durations, and notification delays are distinct pieces that must be engineered together so detection is neither sluggish nor overly twitchy.

For PostgreSQL, build role-aware alerts for primaries and standbys covering connection exhaustion, replication lag, WAL slot retention, disk pressure, locks, autovacuum, backups, and exporter health. Convert counters with `rate`/`increase`, evaluate gauges by threshold and trend, and distinguish no data from zero. Hysteresis, sustained conditions, multi-signal context, grouping, inhibition, and tightly scoped silences keep notification noise under control.

Finally, alert tuning is a continuous cycle. Track false positives, false negatives, time to detect, and page volume; replay past incidents; test both firing and recovery; and revisit thresholds whenever workloads, capacity, or SLOs evolve. **The goal is detecting problems early enough to protect the service without eroding on-call trust in alerts.**
