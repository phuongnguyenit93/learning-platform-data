# Slow Query Logging and Version-Specific Tooling in Apache Cassandra

## 1. Why Identify Slow Queries Instead of Looking Only at CPU or Average Latency?

Apache Cassandra is a distributed **wide-column** database that distributes partitions by **partition key**, replicates data according to a **replication strategy**, and lets applications set a **consistency level** per CQL operation. A `SELECT` or `INSERT` can pass through the Java Driver, coordinator, multiple replicas, network, memtables, SSTables, compaction, or a resource-heavy repair task.

When an application reports that **read p99 jumped from 80 ms to 1,500 ms**, looking at cluster-wide average latency cannot reveal which query slowed down, which partitions were affected, or which layer consumed the time. **Slow query logging** records executions exceeding a threshold; **query tracing** reveals the flow of selected requests; **metrics/histograms** show the scale of the problem.

Example scenario:

- An API reading a device's 30 latest events has a p50 of 12 ms.
- 99% of requests remain fast, while roughly 1% take over 800 ms.
- A few device partitions hold many tombstones and span numerous SSTables.
- Relying only on ERROR-level logs or average CPU may miss every clue.

In this **Tracing and Diagnosis** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, we focus on collecting actionable evidence to answer: **which requests are slow, where they are measured, why they are slow, which tools exist in the running Cassandra version, and how to investigate without worsening the incident**.

## 2. "Slow Query Log" Does Not Mean Tracing or Full Query Logging

The term *slow query logging* refers to different mechanisms depending on product and version. When operating **Apache Cassandra**, do not assume there is always a default MySQL-style table or log file containing every CQL statement above a duration threshold.

| Mechanism | Primary Data | When Useful | Key Limitations |
|---|---|---|---|
| **Application/driver slow-query log** | Query ID, latency, outcome, CL, and sanitized metadata | Identifies which real operations exceed thresholds from the client side | Must be instrumented or configured; does not explain replica internals |
| **CQL tracing** | Request execution steps on coordinator and replicas | Detailed analysis of a representative request | Adds overhead, covers only traced requests; trace data has a retention TTL |
| **Histograms / JMX metrics** | Latency distributions, operation counts, timeouts, backlogs | Tracking p95/p99 trends; comparing DCs/nodes/tables | May not pinpoint specific queries and parameters |
| **Full Query Logging (FQL)** | Stream of CQL requests/inputs for capture and replay via supported tools | Investigating workloads; replaying query sequences in controlled environments | **Not a log of slow queries only**; does not include total execution duration by default |
| **Audit logging** | Access and operation events for compliance auditing | Investigating who ran which CQL statement type or admin action | Must not replace histograms or slow-query timers |
| **Server debug/TRACE logs** | Internal events depending on logger and release | Narrow diagnosis per product guidance | Extremely verbose, high overhead and sensitive data; never enable broadly |

**Rule of thumb:** to detect whether requests exceed a latency threshold, prefer **timers at the client or driver boundary**; to learn *why* they are slow, combine with **selective tracing** and **coordinator/replica metrics**. FQL or audit logs can supplement, yet **do not automatically answer p99 questions**.

### 2.1. What Makes a Useful "Slow Query Event"?

A logged event can include:

~~~text
event=cassandra_slow_request
operation=read_device_events
duration_ms=842
threshold_ms=200
outcome=success
keyspace=telemetry
table=events_by_device_day
cl=LOCAL_QUORUM
page_size=50
dc=dc1
attempts=2
trace_id=<correlation ID if actually present>
timestamp=<UTC timestamp>
~~~

The fields above are a **recommended log schema**, not Cassandra's built-in log format. If no trace ID or driver attempt count is available, leave the field blank or omit it; **never invent an ID and treat it as a server trace**.

What to avoid: logging raw partition keys containing personal data, sensitive bind values, full row contents, passwords, tokens, raw parameterized queries, or high-rate repetitive exception stack traces. Use a stable **query template ID** to group incidents; when a specific key is genuinely required, enforce access controls and data-masking policies.

## 3. Which Layer to Measure? Picking Scope-Appropriate Thresholds

### 3.1. One CQL Request Has Multiple Latencies

~~~mermaid
flowchart TD
    A["Java Service: start end-to-end measurement"] --> B["Java Driver: queue, node selection, retry"]
    B --> C["Network to coordinator"]
    C --> D["Coordinator: parse/execute, dispatch to replicas"]
    D --> E["Replica: memtable, SSTable, I/O, or commit log"]
    E --> D
    D --> F["Sufficient responses per consistency level"]
    F --> G["Network back to Java Driver"]
    G --> H["Application receives result / page"]
    I["Compaction, GC, repair, streaming"] -. contends for resources .-> E
    J["WAN, slow replica, topology"] -. impacts .-> D
~~~

For example, two systems might both report `Table.ReadLatency p99=20 ms`, yet one sees `Java request p99=700 ms`. The gap can lie in the coordinator, queues, network, CL, retries, or components outside table-local metrics.

**Do not subtract two percentiles to derive a third:** `p99(client) - p99(table)` is not `p99(network)`, because those p99s may belong to completely different sets of requests.

| Measurement Point | What Scope May Include | Best Used For |
|---|---|---|
| **HTTP/gRPC endpoint** | Entire business flow and dependencies | User-facing SLOs |
| **Application around `session.execute`** | Driver, network, coordinator, responses, relevant data access | Application-perspective slow-query logging |
| **Driver internal metrics** | Request latency, retries, speculative executions, pools/queues per config | Separating client/network from server |
| **Coordinator/client request metrics** | CQL processing path at the Cassandra coordinator | Spotting slow coordinating nodes |
| **Table-level metrics** | Local engine work on a single node | Spotting SSTables/tombstones/I/O and replica load |

### 3.2. Slowness Thresholds Must Be Per Operation

**Illustrative** threshold examples, not Cassandra defaults:

| Operation | Query Pattern | Trial Logging Threshold |
|---|---|---:|
| `read_device_latest` | Single partition, up to 50 rows | 200 ms |
| `write_measurement` | Single small mutation INSERT | 300 ms |
| `read_daily_summary` | Partition query by day | 500 ms |
| `administrative_scan` | Controlled low-throughput job | 3,000 ms |

Do not apply the same threshold to tiny interactive queries and batch/analytics jobs. Set thresholds from **SLOs**, per-operation baselines, load conditions, and sample counts while tracking p50/p95/p99 and timeout rates.

A timed-out request **may not appear in success-only histograms**. To avoid an illusion of healthy p99, record **outcome=timeout/error** and count total requests.

### 3.3. Time to First Result Differs from Full Read Time

In the Java Driver, `session.execute(statement)` for a paged query can complete once the **first page** arrives; iterating subsequent pages triggers additional requests. A timer wrapping only `execute` does not measure fetching millions of rows.

When reporting a slow query, specify whether you are measuring:

- **Time to first page**.
- **One page** or **per driver request**.
- **Time to consume all pages**.
- **Full endpoint** (including business logic).

For async queries, stop the timer **when the completion stage finishes**, not immediately after calling `executeAsync`.

## 4. CQL Tracing with `cqlsh`: Watching How One Request Runs

### 4.1. Enabling Tracing for Targeted Statements

Assume the `telemetry` keyspace exists and the table is partitioned by `(device_id, event_day)`.

~~~cql
TRACING ON;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

`TRACING ON` is a **`cqlsh` command**, not standard CQL syntax for `SELECT` in the Java Driver. When supported and the query generates a trace, `cqlsh` displays the **trace session ID**, chronological activities, and coordinator/replica details.

Use tracing selectively on reproducible, authorized queries. Because generating and storing trace events carries overhead, **never enable it by default for all production queries**.

### 4.2. Reading Traces Through Specific Questions

| Field / Signal | Meaning | Limitation |
|---|---|---|
| **Trace session ID** | Links events belonging to the same execution | Not an application-wide request ID unless explicitly correlated |
| **Coordinator / source** | Which node coordinated or emitted the event | Does not reveal root cause without logs/metrics |
| **Activity** | Processing step such as sending read or receiving response | Wording differs across versions and query types |
| **Source elapsed** | Relative offset within the trace on that source | Should not be summed mechanically into end-to-end latency |
| **Duration** | Recorded duration of the trace session when present | Does not automatically cover HTTP/client-side time |
| **Gaps between events** | Hints at waiting, network transit, or untraced steps | Does not prove exactly which resource bottlenecked |

Look for places where the coordinator waits on replicas, replicas scan SSTables, or abnormal steps appear; correlate with disk latency/CPU and contemporaneous metrics. **Traces are event-based evidence**, not complete flame graphs; a missing event does not prove the step never happened.

### 4.3. Querying Tracing Data in `system_traces`

Cassandra stores trace sessions and events in the tracing system keyspace (on versions supporting this interface).

~~~cql
-- Example: replace UUID with the REAL session_id obtained from tracing.
SELECT *
FROM system_traces.sessions
WHERE session_id = 11111111-1111-1111-1111-111111111111;

SELECT *
FROM system_traces.events
WHERE session_id = 11111111-1111-4111-8111-111111111111;
~~~

The example UUID is a placeholder only; do not expect matching data.

- The `sessions` table holds summary metadata for the trace session.
- The `events` table describes individual steps inside the session.
- Tracing data has a retention TTL and may expire before you query it; failing to find an old session **does not mean the request never ran**.
- Queries against the system keyspace must be authorized and avoid scanning all event data.

In production, prioritize recording the trace ID correlated with the specific slow request under investigation and its UTC timestamp.

### 4.4. Probabilistic Automatic Tracing

Some Cassandra versions support administrative commands like `nodetool settraceprobability` to configure tracing probability on a node. **Do not use this as a default slow query log**: probabilistic sampling picks random queries regardless of speed and can raise CPU/I/O load.

Before using it:

~~~bash
nodetool help
nodetool help settraceprobability
~~~

If your Cassandra version supports it and your runbook permits it, set a **very low, time-bounded sampling rate while monitoring overhead**, then revert to the approved setting. Never copy a command or probability value verbatim from an example onto a heavily loaded cluster.

## 5. Full Query Logging, Audit Logging, and Version Differences

### 5.1. What Is Full Query Logging (FQL)?

In modern Apache Cassandra versions **that support FQL** (such as 4.x and 5.x), this mechanism records the stream of CQL requests for analysis and compatible replay tools.

FQL **is not automatically a slow-query log**:

- It can record **many requests, including fast ones**.
- Persisted data may be in a **custom binary log format**, not plain text files you can grep like application logs.
- Query and bind data can be sensitive.
- It can significantly increase disk throughput and storage consumption.
- A request appearing in FQL does not indicate how slow it was; you still need timers and correlation.

Some versions provide `nodetool` commands for managing FQL, such as `enablefullquerylog` and `disablefullquerylog`. **Check inline help** before running them:

~~~bash
nodetool help
nodetool help enablefullquerylog
nodetool help disablefullquerylog
~~~

Never enable broad FQL during a disk-full incident just to "find slow SQL": writing large additional logs can worsen the outage. Understand storage paths, rotation/quota mechanisms, retention, and sensitive data exposure before enabling it.

### 5.2. Audit Logging Is Not a Slow-Query Timer

Audit logging records access and operational events as supported by specific Cassandra versions/configurations. It can show who executed which CQL pattern or admin operation, yet **it does not replace client-side latency distributions**.

Do not conclude "a query in the audit log was slow" or "absent from the audit log means it didn't run," because audit scopes, filters, and activation state govern what gets logged.

### 5.3. Tool Selection Matrix by Version Line

| Deployment Line | Tools to Start With | Verification Notes |
|---|---|---|
| **Apache Cassandra 3.x** | `cqlsh` tracing, `system_traces`, `nodetool`, JMX, application slow logging | Do not assume FQL commands from newer versions apply |
| **Apache Cassandra 4.x** | Baseline tools, plus FQL/audit where features and config are available | Confirm exact command names, retention options, permissions, and log export |
| **Apache Cassandra 5.x or newer** | Baseline tools plus logging/observability features of that exact release | Do not assume metrics or virtual tables match 4.x structure |
| **Vendor-packaged / alternative distributions** | Exact version and vendor documentation | May add custom slow-query loggers; do not assume they are standard Apache features |

This table **categorizes capabilities**, not an exhaustive feature matrix per patch release. The safe approach is running `nodetool version`, reading `nodetool help`, and checking configuration against approved runbooks.

**Do not assume every Cassandra version has a built-in global "slow query threshold" config parameter** just because other database engines do.

## 6. `nodetool` Commands for Diagnosing Slow Queries

CQL tracing provides detail for a single request; when investigating p99 spikes or many slow requests, inspect node/table statistics as well.

~~~bash
# Verify node version and the actual list of available commands.
nodetool version
nodetool help

# Read/write latency and SSTable health per table.
nodetool tablestats telemetry.events_by_device_day

# Read/write histograms, SSTables per read, and other version-dependent metrics.
nodetool tablehistograms telemetry events_by_device_day

# Coordinator-level request histograms, depending on version.
nodetool proxyhistograms

# Thread pool stages, pending, and dropped messages.
nodetool tpstats

# Active compactions and I/O backlog.
nodetool compactionstats

# Streaming / network transfers during topology changes or repair.
nodetool netstats

# Node UP/DOWN status by datacenter/rack.
nodetool status
~~~

If a syntax fails on your installation, check `nodetool help <command>` instead of guessing. Latency fields may report in **different units** (microseconds, milliseconds, nanoseconds), and histogram window/sampling behavior may differ from Prometheus or client timers.

### 6.1. What Order Should You Inspect?

1. **Application:** slow request rate, p95/p99, timeouts/errors, and operation types.
2. **Coordinator:** proxy/client request latency, pending/dropped counts, required replica ACKs per CL.
3. **Node table level:** read/write latency, SSTables per read, tombstones, partition size, compaction backlog.
4. **Infrastructure:** network, disk I/O latency, CPU, GC, free disk space.
5. **Background / topology tasks:** streaming, repair, bootstrap, hinted handoff, or down replicas.

Healthy **table-local metrics** alongside a slow application do not clear Cassandra: the coordinator, network, or another replica may still be the bottleneck.

### 6.2. Avoid Averaging p99s Across Nodes

To estimate cluster-wide p99, never compute:

~~~text
p99_cluster = (p99_node_A + p99_node_B) / 2  # WRONG
~~~

Percentiles **cannot be added or averaged**. You must aggregate underlying distribution/histogram buckets across the same window and request class, then compute the quantile. In particular, never combine read p99 with write p99, or table-local p99 with client p99.

## 7. Analyzing Slow Query Data Methodically

### 7.1. Group Queries by Shape Rather Than Raw CQL

Consider two requests:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Both share the **same query shape** and differ only in bind values. If the app emits a log event per request, group them by an ID such as `read_device_events_by_day`, rather than creating new metric label values for every UUID.

Then compare slow-request ratios by operation and trace specific anomalies selectively where permitted.

### 7.2. Query Shape Shapes the Read Path

A query supplying the full partition key lets Cassandra route to a specific replica set. Even so, it can still be slow when:

- The partition holds too many rows or spans an overly wide clustering range.
- Numerous tombstones from DELETEs/TTLs trigger a **tombstone scan**.
- One partition is fragmented across many SSTables due to flush/compaction backlogs.
- A hot partition is hammered concurrently by many clients.
- Disk/cache contention or compaction/repair slows down the replica.

Conversely, `ALLOW FILTERING` on a predicate lacking a partition key can trigger unpredictable scans:

~~~cql
-- Anti-pattern illustration: do not use as a default production query.
SELECT device_id, event_time, value
FROM telemetry.events_by_device_day
WHERE value > 80
ALLOW FILTERING;
~~~

Not every slow query can be cured by adding cache, and raising timeouts usually just prolongs waiting instead of fixing the cause.

### 7.3. `LIMIT` Does Not Eliminate Tombstone Scan Cost

A `LIMIT 20` query only bounds **returned rows**, without guaranteeing it only inspects 20 entries on disk. A partition packed with thousands of tombstones may force reading many SSTables and deleted entries before assembling enough live rows.

When certain queries exhibit poor p99, combine query-ID slow logs with `tablehistograms`, tombstone warnings, and selective tracing. Re-evaluate TTL/retention models, partition bucketing, and compaction strategies based on the workload.

## 8. Java Driver 4.x Example: Safe Slow-Query Event Logging

### 8.1. Example CQL and Data Model

Suppose the application reads daily device events:

~~~cql
-- Assumes the telemetry keyspace already exists.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Sample query:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 50;
~~~

In Java, prepare the statement once and pass partition keys as bind parameters rather than concatenating values into CQL strings. Example measuring **the synchronous read path for the first page**, using SLF4J:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class DeviceEventReader {
    private static final Logger LOG =
        LoggerFactory.getLogger(DeviceEventReader.class);
    private static final long SLOW_THRESHOLD_MS = 200L;

    private final CqlSession session;
    private final PreparedStatement readByDay;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.readByDay = session.prepare(
            "SELECT event_time, value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 50"
        );
    }

    public Row readFirst(UUID deviceId, LocalDate day) {
        BoundStatement statement = readByDay.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        long startNs = System.nanoTime();
        String outcome = "success";

        try {
            return session.execute(statement).one();
        } catch (RuntimeException ex) {
            // Avoid logging exception messages that may contain sensitive data.
            outcome = ex.getClass().getSimpleName();
            throw ex;
        } finally {
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs
            );
            if (durationMs >= SLOW_THRESHOLD_MS
                    || !"success".equals(outcome)) {
                LOG.warn(
                    "cassandra_request queryId={} durationMs={} " +
                    "thresholdMs={} outcome={} cl={} pageSize={}",
                    "read_device_events_by_day",
                    durationMs,
                    SLOW_THRESHOLD_MS,
                    outcome,
                    "LOCAL_QUORUM",
                    50
                );
            }
        }
    }
}
~~~

This example times executing `execute` and retrieving the first row; it **does not measure full pagination or HTTP duration**. It intentionally omits `deviceId` and `day` because bind values can be sensitive or blow up cardinality.

**Additional production hardening:**

- Emit histogram metrics for **all requests**, not only those exceeding the threshold; slow logs are investigation signals, while histograms measure distributions.
- Normalize outcomes into a bounded set such as `success`, `timeout`, `unavailable`, `error`.
- Rate-limit and sample slow logs when slow-request rates spike so **logging itself does not degrade p99 further**.
- Ensure logs use UTC formatting, defined retention, and strict access control.
- Attach a **non-PII** request correlation ID; keep it distinct from server trace session IDs.
- To observe retries/attempts, use driver metrics/extensions for your actual version; never assume one `session.execute` call equals one network attempt.
- For asynchronous/Reactive APIs, measure until the future/stream completes per business semantics, not just call submission.

### 8.2. Don't Just Log Slow Queries—Record Histograms

When using Micrometer, OpenTelemetry, or another metrics backend, prefer duration histograms tagged by **stable query ID**, CL, DC, and outcome. Bucket boundaries might cluster around 50, 100, 200, 500, 1,000, and 2,000 ms depending on SLOs.

Never compute `p99_cluster` by averaging pod p99s. Merge histograms accurately across scope and time windows. Also track **request count, timeout rate, and retry rate**; when slow requests time out and drop out of success-only histograms, looking solely at success p99 misleads you.

## 9. Diagnosing Common Causes of Slowness

| Signal from Slow Logs + Metrics | Primary Hypothesis | Evidence to Look For |
|---|---|---|
| Specific SELECT has high p99, rising tombstone scans | TTLs/DELETEs left heavy tombstones | Query range, warning logs, tracing, SSTables per read |
| One partition is slow, other tables normal | Hot/wide partition or token skew | Query pattern, partition size, per-node load |
| Read p99 rises with compaction backlog | Read amplification and disk I/O contention | `compactionstats`, table histograms, disk latency |
| Write p99 high alongside commit log/disk latency | Replicas cannot ACK fast enough due to storage | Coordinator/replica metrics, disk, GC |
| Client p99 high yet table-local low | Driver queues/retries, coordinator, or WAN | Driver metrics, network RTT, `proxyhistograms` |
| LWT p99 uniquely high | Paxos contention or serial consistency path | CQL `IF`, conflict rate, retries, replica health |
| Timeouts/unavailables spike when a DC degrades | CL cannot be satisfied or network partition | Per-DC RF, `nodetool status`, read/write CL |
| Slow requests rise during repair/streaming | Competing background I/O | `netstats`, `compactionstats`, disk/network |
| Huge FQL, disk nearly full | Excessive FQL/audit logging | Log path, quota, retention, I/O metrics |

This table lists **initial hypotheses**, not automatic diagnosis rules. One symptom can stem from multiple causes, and one cause can affect many metrics.

### 9.1. Recognizing Retries and Speculative Execution

A request totaling 800 ms may consist of multiple distinct attempts. If the driver retries on timeout or fires speculative execution per policy, attempts may hit different coordinators/replicas.

Thus, inspecting a trace for a single attempt **cannot be assumed to explain all 800 ms on the client**. Correlate request/attempt IDs where available, retry counts, errors, target hosts, and elapsed times.

Also understand consistency levels: `LOCAL_QUORUM` reads/writes are affected by a slow replica differently than `ONE`; lowering CL to trim p99 changes data consistency and availability guarantees, not merely performance.

## 10. Incident Response Workflow: Read p99 Spikes While Median Stays Fast

Suppose `GET /devices/{id}/events` shows:

~~~text
Before incident:
  p50 = 12 ms, p95 = 45 ms, p99 = 90 ms
  timeout = 0.05%

During incident:
  p50 = 15 ms, p95 = 55 ms, p99 = 1,200 ms
  timeout = 1.5%
~~~

Step 1 — **Pin down the time window and measurement layer.** Confirm whether metrics come from Java/app or server table-local scopes, check request counts per window and recent deployments, and avoid comparing mismatched units or windows.

Step 2 — **Break down by query ID, keyspace/table, DC, and CL.** Find which operation accounts for the largest share of slow requests. If only `read_device_events_by_day` degraded, focus there first.

Step 3 — **Inspect controlled slow events.** Sample representative slow requests and correlate duration, outcome, page size, retries, and timestamps. Avoid logging full payloads or all bind values.

Step 4 — **Correlate node/table telemetry.** Check `tablestats`, `tablehistograms`, `proxyhistograms`, `tpstats`, `compactionstats`, and disk/network metrics for the same timeframe.

Step 5 — **Trace a few reproducible queries.** Enable `TRACING ON` in `cqlsh` when appropriate, target the right partition key/range, inspect session metadata and events, and disable tracing immediately afterward. Protect transcripts/traces per policy if workloads contain PII.

Step 6 — **Evaluate targeted fixes.** E.g., bound clustering ranges, fix bucketing models, throttle backfill/repair rates, clear compaction backlogs, upgrade disk capacity, or tune retry behavior. Avoid raising timeouts or altering CL before understanding consequences.

Step 7 — **Verify after remediation.** Compare p50/p95/p99, timeouts, throughput, slow event counts, and disk/replica health on the same operation with sufficient samples. If p99 drops while timeouts climb, **do not declare improvement**.

### Why Not Enable FQL or Cluster-Wide TRACE Immediately During an Incident?

When disk or CPU is already saturated, writing extra logs for every request consumes the very resources already starved. Prefer **existing metrics**, rate-limited/sampled application logs, and tracing a handful of representative queries. Enable FQL, audit logging, or debug logs only when strictly necessary, after estimating overhead and ensuring a clean rollback plan.

## 11. Security and Overhead of Diagnostic Tooling

Slow query logging can inadvertently capture sensitive information:

- `user_id`, `device_id`, or partition keys acting as personal identifiers.
- Queries containing sensitive literals instead of bind parameters.
- Batch statements carrying multiple mutations.
- Query results, exception messages, or full traces exposing internal structure.
- FQL or audit logs retaining statements sufficient to replay transactions.

A sound policy requires:

1. **Sanitized logs:** use fixed query IDs and omit raw bindings unless strictly needed.
2. **Restricted read access:** limit log/trace visibility to authorized operations staff per policy.
3. **Retention and quotas:** prevent unbounded log growth on Cassandra data volumes.
4. **Sampling/rate limiting:** especially during failure storms logging thousands of times per second.
5. **Overhead tracking:** monitor log volume, free disk, I/O, and p99 shifts after enabling tooling.
6. **Version/config awareness:** document exact versions so on-call engineers don't run renamed or unsupported commands.

**Never put raw CQL containing sensitive values into Prometheus metric labels.** Cardinality explodes and sensitive data leaks across monitoring pipelines. For granular detail, use authorized, controlled traces instead of metric labels.

## 12. Version and Environment Checklist

Before enabling diagnostic tooling, record:

~~~text
[ ] Cassandra edition/distribution and version on each node
[ ] Keyspace, table, partition key, and query pattern
[ ] Read/write consistency level, RF, and relevant datacenters
[ ] p50/p95/p99 and timeout/error rates per operation
[ ] Exact metric names/units from current JMX/exporter
[ ] Does the nodetool command actually appear in nodetool help?
[ ] Are cqlsh tracing or driver logs scoped appropriately?
[ ] Do we genuinely need FQL/audit, or just metrics + a single trace?
[ ] Activation time limit, sampling rate, storage path, quota, retention
[ ] Can the feature be turned off cleanly and overhead verified back to normal?
[ ] Is there any risk of leaking sensitive data in bind values or trace transcripts?
[ ] Re-verified post-fix using the exact same measurement definitions?
~~~

Never see "version 4.x" and assume every node shares identical tooling; patch levels, distributions, exporters, and deployments vary. Cluster configuration changes require standard change-management and rollback procedures.

## 13. Self-Check Exercises

### Question 1 — Slow Logs vs. Tracing

An API has p99 = 800 ms. Operations wants to know **which query** is slow and **which step** of a request is stuck. Which two tool types should they use?

**Answer:** Application/driver slow request logging or per-query-ID metrics to identify the slow operation group; then `cqlsh` tracing or selective query traces to inspect coordinator/replica steps. Histograms measure overall impact scope.

### Question 2 — Does FQL Replace a Slow-Query Timer?

Someone enables Full Query Logging and assumes every CQL statement in FQL is a slow query. True or false?

**Answer:** False. FQL captures the request stream for observation/replay as configured; it does not filter for slow queries above a latency threshold or measure end-to-end duration.

### Question 3 — p99 Gap

Java request p99 is 700 ms, while table-local p99 is 20 ms. Can you conclude network p99 = 680 ms?

**Answer:** No. Percentiles cannot be subtracted like that and the two metrics have different scopes. Inspect coordinator overhead, network, retries, driver queues, and other replica nodes.

### Question 4 — `LIMIT` and Tombstones

A `SELECT` uses `LIMIT 20` yet traverses thousands of tombstones to gather enough rows. Can `LIMIT` guarantee a cheap query?

**Answer:** No. `LIMIT` only caps returned rows; it does not directly bound how many disk entries/tombstones must be scanned.

### Question 5 — Tracing Shows No Data

After one day, an engineer cannot find a session ID in `system_traces.sessions`. Does that prove the query never ran?

**Answer:** No. Traces have a retention TTL; the record may have expired or failed to persist as expected. Check logs/metrics from the incident timeframe.

### Question 6 — Timeouts Making p99 Look "Clean"

After an outage, success p99 drops from 900 ms to 100 ms, yet timeouts jump from 0.1% to 7%. Has the system improved?

**Answer:** You cannot conclude that; slow requests may simply be timing out and dropping out of success metrics. Evaluate good-request ratio, error rate, QPS, and SLOs together.

### Question 7 — Version and Diagnostic Commands

A guide says to run `nodetool enablefullquerylog`, but the running node rejects the command. Should you force config edits to make it work?

**Answer:** No. Check `nodetool version`, `nodetool help`, distribution docs for the exact version, and operational procedures. You can still rely on application timers, tracing, and histograms without FQL.

### Question 8 — Java Async Logging

A developer wraps a timer solely around `session.executeAsync(statement)` and always sees under 2 ms. Did Cassandra actually finish the request in 2 ms?

**Answer:** No. That only times creating/submitting the async call. Measure until the completion stage/future resolves, and distinguish first page from consuming all results.

## 14. Key Takeaways

**Slow query logging identifies requests exceeding a threshold**, while **tracing dissects the execution steps of a single request**. In Apache Cassandra:

- There is no guaranteed **universal built-in slow query log across all versions**; the application/driver is typically the most reliable place to measure per-operation latency.
- `TRACING ON` in `cqlsh` and `system_traces` provide selective detail but incur overhead and have independent TTL retention.
- Full Query Logging and audit logging serve different purposes and **do not replace p99 histograms or slow-query timers**.
- `nodetool` commands, JMX beans, and metrics must be verified **against your specific version and distribution**.
- When queries are slow, correlate **query shape, partition key, CL, tombstones/SSTables, compaction, replicas, WAN, queues, and retries**.
- Never average p99 across nodes, never let timeouts disappear from SLO views, and never log sensitive data.
- Validate optimizations using the **same operation, same measurement window, and sufficient samples** before and after changes.

**Concise workflow:** measure latency distribution → pinpoint slow operation → check node/table metrics → trace selectively → verify root cause → make small measurable changes → verify both p99 **and** error rate. This approach fits distributed wide-column systems, where a single CQL statement passes through multiple layers before the Java application receives a result.
