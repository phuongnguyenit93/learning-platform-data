# Metrics by Node, Keyspace, Table, and Application Request in Apache Cassandra

## 1. Why observe Cassandra across multiple layers?

**Apache Cassandra** is a **distributed wide-column** database. A CQL request from a Java application passes through the driver, a coordinator, multiple replicas, and the storage engine consisting of memtables/SSTables. Therefore, the question “Where is Cassandra slow?” cannot be answered by a single CPU or latency number.

Suppose the API `GET /devices/{id}/latest` sees response times jump from 30 ms to 700 ms. Possible causes include:

- A **node** is running out of free disk space, experiencing garbage collection (GC), or accumulating pending tasks.
- A **keyspace** is experiencing a surge in reads/writes because multiple tables are serving a new traffic wave.
- A **table** has oversized partitions, heavy tombstones, or many SSTables that must be read per query.
- An **application request class** is slow due to retries, consistency level, timeouts, pooling, or an inefficient query pattern.

Looking only at cluster-wide aggregate metrics can let healthy nodes mask an overloaded node. Looking only at application metrics shows user impact, but does not reveal whether the bottleneck sits in a replica, disk, or the Java layer itself.

**Objective:** organize metrics into four levels—**node → keyspace → table → application request**; learn how to interpret rate, latency, errors, and saturation; distinguish coordinator from replica; choose suitable dashboards and alerts; and measure accurately without confusing units or double-counting traffic from replication.

> Specific metric names in Cassandra/JMX, drivers, and exporters vary across versions, distributions, and metric collectors. Metric names shown in this lesson are **illustrative examples**, not an API contract guaranteed for every cluster. Always verify the actual metrics emitted in your deployment.

## 2. Request journey and measurement points

```text
 Java application / API
      |  API latency, error, retry, connection pool
      v
 Cassandra Java Driver 4.x
      |  driver request metrics / per-node metrics
      v
 Cassandra coordinator (Node A)
      |  client-request latency, timeout, pending, throughput
      +-------------+--------------+
      |             |              |
      v             v              v
  Replica A     Replica B      Replica C
  node metrics  node metrics   node metrics
  Table/Ks      Table/Ks       Table/Ks
      |             |              |
      +---- memtable, SSTable, cache, disk ----+
                   compaction, repair
```

A coordinator may also be a replica. Not every request contacts all replicas: that depends on the **replication factor (RF)**, **consistency level (CL)**, topology, request type, and Cassandra's internal execution path.

Metrics at each layer answer different questions:

| Observation layer | Grouping unit | Core question | Example indicators |
|---|---|---|---|
| **Node** | Cassandra host/instance | Is the node healthy or resource-constrained? | CPU, heap/GC, disk, network, pending tasks, dropped messages |
| **Keyspace** | Keyspace on a node or defined aggregate | Which data group is generating load? | Read/write count, latency, pending flushes, per-keyspace data/traffic |
| **Table** | Keyspace + table + node | Which table causes expensive reads or large storage footprint? | SSTables, live/total disk, partitions, tombstones, memtable, compaction |
| **Application/request** | Service + operation/query template | What impact are users experiencing? | Request rate, success/error/timeout, p95/p99, retries, pool/acquisition latency |

**Important distinction:** Cassandra metrics exposed via JMX are typically **per-node metrics**, even when the name includes `Keyspace` or `Table`. Cluster-wide aggregation is done by your collector/dashboard; never treat a single value scraped from Node A as the “entire cluster's keyspace”.

## 3. Metric types: counter, gauge, timer, histogram

Before building charts, know what type each metric is:

| Type | Meaning | Proper usage | Common mistakes |
|---|---|---|---|
| **Counter** | Cumulative event count since process/series start | Compute `rate()`/`increase()` over a time window | Plotting the raw counter as “requests/s” |
| **Gauge** | Current state that can go up or down | Track current value, trend, and saturation level | Applying `rate()` to free disk or pending queue length |
| **Timer** | Count and timing distribution of operations | Latency in proper units, count, matching percentiles/histograms | Confusing microseconds with milliseconds or seconds |
| **Histogram** | Distribution of observations across buckets or snapshots | Inspect buckets, or quantiles if supported by structure | Averaging multiple percentiles together |
| **Meter/rate** | Event frequency tracked by a library | Check `mean`/`m1`/`m5`/`m15` and window semantics | Comparing rates across mismatched windows without noting it |

Some JMX exporters expose percentiles as **gauge snapshots**, while others emit **Prometheus histogram buckets**. These two formats are not equivalent: `histogram_quantile()` is valid only when the exporter genuinely provides valid `*_bucket` series. From `p99_node_A` and `p99_node_B`, **you cannot take an average** to derive cluster-wide p99.

### Unit consistency

- **Latency:** confirm microseconds, milliseconds, or seconds before setting thresholds.
- **Throughput:** requests/second, mutations/second, and bytes/second are three distinct quantities.
- **Storage:** bytes, MiB/GiB, disk usage percentage; also check capacity per mount point.
- **GC:** pause duration versus GC frequency; total GC time and max pause are different metrics.
- **Tombstones:** can mean cells scanned, per-query warnings, or total tombstones; do not treat them all as the same metric.

## 4. Node metrics: resources and process health

The node level is the first place to check when suspecting **an unhealthy replica or coordinator**.

| Group | Metrics/observations to collect | Warning signs |
|---|---|---|
| **Topology/availability** | Node up/down, joining/leaving/moving state, schema agreement | Disconnected node; requests rerouting to other replicas |
| **CPU** | Process/host CPU, load per core | Sustained CPU near saturation alongside rising latency |
| **Heap and GC** | Heap used/max, pause duration, GC rate | Long pauses coinciding with latency/timeout spikes |
| **Disk** | Free/used per volume, throughput, latency, IOPS | Reads/writes disk-bound or volume nearly full |
| **Network** | Bytes/s, errors, retransmits, connection saturation | Timeouts during data center or link congestion |
| **Memtable** | Memtable live data, pending flushes | Write-buffer flush/disk pressure |
| **Compaction** | Pending tasks, completed tasks, bytes compacted | Compaction falling behind writes or TTL tombstones |
| **Thread pools/queues** | Active/pending tasks, blocked/dropped tasks if available | Continuously growing queues, saturated coordinator/replica |
| **Hints/repair/streaming** | Pending hints, repair/stream status | Replicas imbalanced or out of sync |

There is **no single universal CPU threshold** proving Cassandra is broken: high CPU under healthy load with stable latency may simply mean efficient resource utilization. Always evaluate saturation, latency, errors, and trends **together**.

### Quick inspection with `nodetool`

On a host authorized for Cassandra administration:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
```

`status` shows topology and node states; `tpstats` surfaces thread-pool queues/execution and dropped-message counters; `compactionstats` shows compaction progress; `netstats` helps inspect streaming and related network activity. These are **diagnostic snapshots**, not a substitute for time-series monitoring.

Exact command names and output formats vary across Cassandra versions. Do not run **state-mutating** `nodetool` commands (such as repair, flush, compact, cleanup) just to “check metrics”; they generate I/O and can impact the cluster.

## 5. Coordinator metrics: client-facing requests

A Java Driver request typically targets a **coordinator**. At this layer, **ClientRequest** metrics (JMX names usually follow similar semantics) track `Read`, `Write`, and additional request scopes depending on version.

Look at:

1. **Throughput:** client read/write requests per second at each coordinator.
2. **Latency:** request-processing distribution using p50/p95/p99 instead of mean alone.
3. **Timeout/unavailable/failure:** distinguish request timeouts, insufficient replicas for CL, and other server failures.
4. **Pending or overloaded state:** scheduler, thread pools, and dropped messages in the same timeframe.
5. **Impact of raising CL:** `ONE`, `LOCAL_QUORUM`, and `ALL` impose different acknowledgement requirements and affect latency/availability differently.

Example incident timeline:

```text
10:00  API p99 rises
10:01  Coordinator A: read p99 spikes sharply
10:02  Node A CPU normal; Node B has long GC pauses
10:03  Reads needing Replica B frequently time out / retry
10:04  CL LOCAL_QUORUM becomes harder to satisfy as B misses deadlines
```

Looking only at Coordinator A's CPU would miss the issue on Replica B. **A slow coordinator does not prove that the coordinator node itself is the sole bottleneck.**

### Do not double-count throughput from replication

A single client write arriving at a coordinator can fan out into **multiple replica operations** depending on RF and CL. The metric “coordinator client writes/s” is **not equal** to total disk/replica writes/s across the cluster. Summing table write counts across all replicas and calling that API request volume **overcounts** the same mutation multiple times.

Similarly, driver retries and speculative executions generate **multiple attempts** for one business request. Clarify whether you are measuring **logical requests**, **driver attempts**, **coordinator requests**, or **replica operations** before comparing rates.

## 6. Keyspace metrics: isolating which data group drives load

A **keyspace** is a logical scope containing tables and replication settings. Keyspace-level metrics help narrow down which workload is surging before drilling into individual tables.

For example, suppose a cluster holds:

- `telemetry_ks`: write-heavy, short TTL, daily event tables.
- `accounts_ks`: primary-key lookups, longer-lived data.
- `sessions_ks`: heavy short-lived reads/writes and tombstones.

When `sessions_ks` p99 spikes while `accounts_ks` stays normal, evidence points to the **session data path**, not necessarily the entire cluster.

| Keyspace observation | How to use it |
|---|---|
| Read/write count or rate | Identify which workload group increased |
| Latency/read-write distribution if exporter supports it | Compare access quality across keyspaces |
| Pending flushes/memtable and related disk footprint | Spot write/storage pressure |
| Aggregated errors/timeouts per system convention | Scope impact; verify whether metric source actually separates keyspaces |
| Replication strategy/RF | Explain replica traffic and CL constraints |

**Limitation:** Cassandra does not guarantee that **all** coordinator-level metrics carry a keyspace label; a metric with only `type=ClientRequest,scope=Read` does not by itself attribute timeouts to `sessions_ks`. When you need per-query-template or per-keyspace attribution, combine application instrumentation with controlled tracing/log analysis.

When aggregating across nodes, explicitly note that `sum by (keyspace)` is the **sum of per-node local series**, not automatically “unique logical requests for the keyspace”.

## 7. Table metrics: finding hotspots, large partitions, and tombstones

In Cassandra, **query-driven table design** directly shapes metrics. Partition keys distribute data across token ranges, and clustering keys govern intra-partition ordering. A table with oversized partitions or queries that do not constrain the partition key often incurs high cost even at modest overall traffic.

Important metric groups at the table level:

| Group | Meaning / signal |
|---|---|
| **Read/write count, latency** | Which table carries load or suffers slow reads/writes |
| **Live disk space, total disk space** | Estimated live data size and local total storage; verify exporter semantics |
| **SSTable count / SSTables per read** | SSTable fragmentation; reads touching many files |
| **Memtable live data / pending flush** | Write buffer and flush pressure |
| **Partition size histogram/estimates** | Detect abnormally large partitions |
| **Tombstones/live cells scanned** | Queries scanning large numbers of non-live cells |
| **Compaction bytes/tasks** | Per-table data cleanup and SSTable pressure |
| **Read repair / consistency-related counters** | Helps diagnose replica divergence, depending on version |

### Example: “returning 10 rows while scanning many tombstones”

Suppose `events_by_account_day` writes 100,000 cells per day with a 10-minute TTL. Querying the 10 latest events in a partition may still traverse a large number of tombstones, especially if the clustering key design or query pattern touches expired ranges.

```text
Returned live rows:          10
Cells/tombstones scanned:  far higher
SSTables touched:            many
API read p99:                elevated
```

Application “rows returned” alone cannot explain execution cost. Compare table metrics, slow-query logs, and sampled traces against the schema and partition sizes. **Do not** immediately raise timeouts to hide a data-modeling issue.

### Table inspection commands

```bash
# Replace keyspace/table names with real values.
nodetool tablestats demo_ks.events_by_account_day
nodetool tablehistograms demo_ks events_by_account_day
```

These commands inspect table summaries/histograms when supported by the version; verify syntax and output fields against your deployment. They provide diagnostic evidence, not a replacement for query testing.

## 8. Distinguishing keyspace/table metrics at a single replica scope

Because a table is replicated across multiple nodes, each node can report **different** table metrics:

```text
                         Keyspace telemetry_ks
                        Table readings_by_device_day

 Node A                       Node B                      Node C
 Table ReadCount=...          Table ReadCount=...          Table ReadCount=...
 DiskBytes=...                DiskBytes=...                DiskBytes=...
 Tombstones=...               Tombstones=...               Tombstones=...
       |                            |                          |
       +--------------- collector scrape ---------------------+
                                    |
                          Cluster-wide dashboard
```

Different aggregations carry different meanings:

- **`sum`:** suitable for certain total work or local byte counts, though for replicated data, **summed disk size is not unique logical data size**.
- **`max`:** finds the hottest node, largest observed partition size, or highest pending queue.
- **`min`:** useful for free disk space to spot the most constrained node.
- **`avg`:** shows broad trends, but can **hide a single anomalous node**.
- **Quantiles:** percentile gauges cannot be summed or averaged; use proper distribution/histogram data or per-node views.

For keyspaces using **NetworkTopologyStrategy**, RF differs by datacenter, so dashboards should preserve `datacenter`/`rack` labels where useful to avoid hiding regional differences. Never assume every node holds every partition.

## 9. Collecting metrics: JMX, exporter, Prometheus, and dashboards

Cassandra exposes many internal metrics over **JMX**; a common monitoring pipeline looks like:

```text
 Cassandra node
     |
     +-- org.apache.cassandra.metrics (JMX)
     |
     +-- JVM/OS metrics
     v
 JMX exporter / collection agent
     |
     v
 Prometheus / equivalent time-series store
     |
     +-- recording rules / alerts
     |
     v
 Grafana / dashboards
```

JMX families are commonly organized by `type` and `scope` such as **ClientRequest**, **Table**, **Keyspace**, **ThreadPools**, **Compaction**, **Cache**, **Storage**, and **DroppedMessage**. ObjectName strings, attributes, units, and exporter mappings can change across Cassandra versions.

**Never expose administrative JMX to the public Internet.** Enforce network isolation, authentication, and authorization per deployment standards. Exporters should publish only required metrics and never expose secrets or unprotected admin endpoints.

### Choosing scrape intervals and metric retention

- Scraping too infrequently misses GC/pending spikes; scraping too aggressively adds load and storage cost.
- Distinguish **Prometheus metric retention** from **Cassandra data TTL**: the two systems have independent policies.
- Keep labels and metric names stable across exporter upgrades, or maintain mapping rules so dashboards do not “go blank”.
- Monitor `up`/scrape error status: an empty chart can mean a **dead collector**, not zero traffic.

## 10. PromQL examples: querying counters and histograms properly

Names such as `cass_client_requests_total` below are **illustrative names defined by exporter/recording rules**, not mandatory built-in Cassandra names. Map them to your real metrics before use.

### 10.1. Request rate by operation

```promql
sum by (datacenter, operation) (
  rate(cass_client_requests_total{operation=~"read|write"}[5m])
)
```

Valid only if `cass_client_requests_total` is a per-coordinator **counter** and labels do not duplicate the same request. Use `rate()` rather than the raw counter to get requests/second.

### 10.2. Error ratio

```promql
sum by (service, operation) (
  rate(app_db_request_errors_total[5m])
)
/
clamp_min(
  sum by (service, operation) (
    rate(app_db_requests_total[5m])
  ),
  1
)
```

In this example both numerator and denominator must count **the same logical request type**. If the denominator counts application requests while the numerator counts driver retry attempts, the ratio is wrong. `clamp_min(..., 1)` avoids division by zero here, though at very low traffic it can understate the ratio; for alerting, apply a minimum volume threshold and explicit rules.

### 10.3. p99 when the exporter emits Prometheus histogram buckets

```promql
histogram_quantile(
  0.99,
  sum by (le, service, operation) (
    rate(app_db_request_duration_seconds_bucket[5m])
  )
)
```

Valid only if `*_bucket` is a genuine cumulative histogram and bucket boundaries match across series. If an exporter exposes only `p99_latency`/`Mean` gauges, **do not use this formula** and never average p99 gauges to synthesize cluster p99.

### 10.4. Nodes with the highest pending compactions

```promql
topk(5, cass_compaction_pending_tasks)
```

`cass_compaction_pending_tasks` is an **illustrative gauge**, not a counter. Preserve the node label so you can pinpoint the exact bottlenecked host.

### 10.5. Disk exhaustion risk

```promql
100 * (
  1 - node_filesystem_avail_bytes{mountpoint="/var/lib/cassandra"}
      / node_filesystem_size_bytes{mountpoint="/var/lib/cassandra"}
)
```

`node_filesystem_*` typically comes from a **host exporter**, not Cassandra JMX. Mountpoints for data, commitlog, caches, or backups vary; do not assume `/var/lib/cassandra` fits every system.

## 11. Java application metrics: measuring what users actually experience

Node metrics do not know whether your API is “reading a cart”, “listing sensors”, or “writing a token”. Therefore, the Java application should emit **metrics keyed by stable query template/operation**, tied to business SLOs.

A minimal metric set:

| Application metric | Recommended labels | Purpose |
|---|---|---|
| Request count | `service`, `operation`, `outcome` | Total logical requests; error ratio |
| Request duration | `service`, `operation` | Service-tier p50/p95/p99 latency |
| Retry attempt count | `operation`, `cause` | Detect timeouts and retry storms |
| In-flight requests | `service`/`operation` | Unfinished concurrency load |
| Driver pool/request metrics | `node` or stable host-id | Spot slow connections/coordinators |
| Application timeout count | `operation`, `timeout_kind` | Separate client budget expiry from server timeouts |

### Java Driver 4.x: example of instrumenting a query

This example uses an abstract sink interface so no specific telemetry library installation is assumed. In practice, `RequestMetricsSink` is implemented with Micrometer, OpenTelemetry Metrics, or your monitoring SDK.

```java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeviceEventReader {
    public interface RequestMetricsSink {
        void recordDuration(String operation, String outcome, long nanos);
        void countRequest(String operation, String outcome);
    }

    private final CqlSession session;
    private final PreparedStatement selectLatest;
    private final RequestMetricsSink metrics;

    public DeviceEventReader(CqlSession session, RequestMetricsSink metrics) {
        this.session = session;
        this.metrics = metrics;
        this.selectLatest = session.prepare(
            "SELECT event_time, temperature_c " +
            "FROM observability_readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 1"
        );
    }

    public Row getLatestInDay(String deviceId, LocalDate day) {
        final String operation = "device_readings_latest_by_day";
        long start = System.nanoTime();
        String outcome = "success";
        try {
            return session.execute(selectLatest.bind(deviceId, day)).one();
        } catch (RuntimeException error) {
            outcome = "error";
            throw error;
        } finally {
            long nanos = System.nanoTime() - start;
            metrics.recordDuration(operation, outcome, nanos);
            metrics.countRequest(operation, outcome);
        }
    }
}
```

**Measurement notes:**

- `System.nanoTime()` measures **elapsed time** inside the JVM process; do not use it as a Cassandra epoch timestamp.
- `operation` is a **bounded template name**, never containing `deviceId` or runtime keys, avoiding millions of time series.
- `outcome` uses a small standardized set like `success/error/timeout`, never arbitrary exception messages.
- This snippet times **the application call around `session.execute(...)`**: it covers synchronous client/driver/coordinator time, not a single replica's internal timer.
- Returning a `null` row can still be a **technical success**; if business logic needs to distinguish “not found”, define a separate outcome or metric.

If driver-level metrics are also enabled, avoid double-counting attempts and logical requests; use driver metrics for deep diagnosis and app metrics for **user SLOs**. Metric configuration in Java Driver 4.x varies by driver version/config and metrics integration; only rely on metric groups confirmed to be enabled.

## 12. Avoiding cardinality explosion and sensitive data leaks in labels

A time series is uniquely identified by **metric name + label set**. Attaching `device_id`, `user_id`, `session_id`, `partition_key`, raw CQL, or `exception_message` as labels can grow series count nearly proportionally to requests or rows.

```text
Safe labels:
  service="device-api"
  operation="device_readings_latest_by_day"
  outcome="success"
  datacenter="dc1"

Dangerous labels:
  device_id="one string per device"
  cql="SELECT ... WHERE token=..."
  session_token="..."
  exception="full stack trace varying per request"
```

Prefer:

1. `service`, `environment`, `datacenter`, `node`, `keyspace`, `table` when cardinality is bounded and genuinely needed.
2. `operation` as a **query template name**, never full parameterized CQL.
3. `outcome` or `error_class` from a finite enum.
4. Put specific IDs/events into **controlled, sampled traces/logs**, never metric labels.
5. Budget collection cost across `nodes × tables × metric types × application labels`.

Query parameters can contain personal data or secrets, so never enable broad full-CQL value logging/tracing in production. For correlation, use standardized request/event IDs compliant with security policies.

## 13. Four-layer diagnosis: from SLO down to a table or node

Suppose a history-read API shows **p99 900 ms**, up from 100 ms. A structured investigation flow:

| Step | Question | Metrics/evidence |
|---|---|---|
| 1. Application | Which API, region, and error types? | App request rate, p95/p99, timeouts, retries |
| 2. Driver/coordinator | Which coordinator is slow; are connection acquisition or retries rising? | Driver per-node latency/errors/pool, client request metrics |
| 3. Node | Is any node hitting disk/GC/thread-pool/compaction bottlenecks? | CPU, disk latency, GC pauses, pending tasks, dropped messages |
| 4. Keyspace | Which workload group spiked? | Keyspace read/write metrics, topology/RF |
| 5. Table | Which table produces heavy SSTables/tombstones/large partitions? | Table read latency, SSTables/read, tombstones scanned, partition histograms |
| 6. Query/schema | Does the query constrain the partition key and bound its range? | CQL template, sampled tracing, schema, query plan |
| 7. Mitigation | Did the fix work without side effects? | Compare before/after p99/errors and node/table metrics |

### Example 1 — Only one node is hot

The app reports rising retries; the node dashboard shows **Node B** with elevated pending tasks and disk latency while other nodes are normal. Check token/replica placement, query distribution, and Node B specifically before scaling the entire cluster.

### Example 2 — One table under tombstone pressure

`sessions_ks.session_by_id` has few live rows yet rising tombstones scanned per read and climbing read p99. Check TTLs, overwrites/deletes, partition design, and compaction; do not assume `gc_grace_seconds = 0` is a safe fix.

### Example 3 — Application is slow while Cassandra nodes look normal

App p99 rises while coordinator `ClientRequest` latency remains flat, and driver acquisition/retries or app thread pools grow. Shift investigation to **client connection pools, network, serialization, Java service GC, and upstream load** instead of forcing Cassandra compaction.

## 14. Alerting matrix: thresholds must come from SLOs and baselines

Never copy one set of absolute thresholds across every cluster; workloads, hardware, CL, and data sizes differ. Design alerts around **actionable signals**:

| Suggested alert | Conceptual condition | First action |
|---|---|---|
| **API error budget burn** | Error rate continuously exceeds SLO over windows with sufficient traffic | Scope affected service/operation and coordinator |
| **Read/write p99 degradation** | p99 > SLO with meaningful request rate | Check retries, node/table p99, disk/GC |
| **Cassandra node unavailable** | Node genuinely down with RF/CL impact | Check topology and recovery plan |
| **Disk headroom low** | Free space drops toward operational reserve | Analyze SSTable/snapshot/compaction growth |
| **Compaction backlog sustained** | Pending tasks grow continuously alongside disk/latency pressure | Check workload, disk bandwidth, and strategy |
| **Read tombstone scan high** | Tombstones scanned per query rise alongside latency | Inspect table and query range |
| **Dropped messages/timeout spike** | Sharp jump above baseline with client errors | Inspect thread pools, network, GC, replicas |
| **Metrics missing** | Scrape/exporter stops reporting past grace period | Fix monitoring before assuming nodes are healthy |

**Combine multiple windows:** a 10-second spike may belong on a dashboard rather than paging on-call. For critical SLOs, pair fast and slow burn-rate alerts; for disk/compaction, alert on trends and forecasts rather than single samples.

**Every alert needs a runbook**: verification steps, relevant dashboards, customer-impact thresholds, and safe actions. An alert saying only “p99 high” without naming service/table/node slows down incident response.

## 15. Evidence-based CQL lab to verify metrics

In a test keyspace already selected with `USE <keyspace>;`, create a table queried with explicit partition and clustering keys:

```sql
CREATE TABLE IF NOT EXISTS observability_readings_by_device_day (
    device_id text,
    event_day date,
    event_time timeuuid,
    temperature_c double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO observability_readings_by_device_day (
    device_id, event_day, event_time, temperature_c
)
VALUES ('sensor-lab-01', '2026-11-21', now(), 29.8);

SELECT event_time, temperature_c
FROM observability_readings_by_device_day
WHERE device_id = 'sensor-lab-01'
  AND event_day = '2026-11-21'
LIMIT 10;
```

### Controlled observation workflow

1. **Before testing:** capture baseline app latency, coordinator read/write rate, node CPU/disk/GC, and table metrics.
2. **Run a small, bounded batch** of requests on known keys from the app/driver—never run full table scans.
3. **After testing:** check whether app request counts increased proportionally, whether coordinator counts correlate, and which nodes recorded local table reads/writes.
4. **Explain discrepancies:** RF, CL, coordinator placement, retries, caches, and exporter scrape intervals can cause counts across layers to differ.
5. **Check latency:** compare app duration against coordinator latency and table metrics if available, without naively subtracting two differently scoped timers to claim “network equals the exact difference”.

When higher load is needed, use a **dedicated test environment and approved load-testing tools**, capping concurrency and preserving baselines. Never fire thousands of requests at a production partition just to watch a chart move.

### Is `TRACING ON` needed?

`TRACING ON` in `cqlsh` is useful when investigating a few specific queries:

```sql
TRACING ON;
SELECT event_time, temperature_c
FROM observability_readings_by_device_day
WHERE device_id = 'sensor-lab-01'
  AND event_day = '2026-11-21'
LIMIT 10;
TRACING OFF;
```

Tracing adds overhead and generates internal trace writes. Use **brief sampling in an appropriate environment**, never leaving tracing broadly enabled as a substitute for continuous metrics. Correlate trace events with client timestamps, CL, and serving nodes.

## 16. How replication, consistency level, repair, and compaction affect metrics

Keep these distributed parameters in mind when interpreting any dashboard:

- **RF (replication factor):** more replicas increase storage copies and inter-node operations; never infer logical writes by summing table writes across all replicas.
- **CL (consistency level):** `ONE`, `LOCAL_QUORUM`, `QUORUM`, and `ALL` require different acknowledgements; always state CL and topology when comparing latency.
- **Repair:** generates disk/network/CPU and streaming/compaction load independent of application traffic. Spikes during repair do not necessarily reflect higher user traffic.
- **Compaction:** runs in the background and competes for disk I/O with reads/writes; prolonged backlogs or forced compactions can degrade latency.
- **TTL/tombstones:** logically expired data can still occupy SSTables; tombstones scanned and compaction pressure may rise before disk usage drops.
- **Coordinator vs replica:** coordinator request latency and replica-node table metrics measure **different scopes** and must not be added or compared 1:1 mechanically.

During repairs or rolling upgrades, **annotate deployment events on dashboards**. When p99 shifts, configuration/CL changes, topology events, or compaction-strategy edits are critical clues.

## 17. Four-layer dashboard checklist

A useful dashboard does not need hundreds of panels. Organize it around the decision flow:

1. **Service/SLO overview:** logical request rate, p95/p99, success/error, timeouts, and retries.
2. **Cluster & topology:** node up/down, datacenter, schema/repair status; traffic mapping across coordinators and replicas.
3. **Node health:** CPU, heap, GC, disk free/latency, network, pending thread pools, dropped messages.
4. **Coordinator requests:** read/write rates, latency distributions, timeouts/unavailable/failures.
5. **Keyspace:** throughput/latency and footprint per data group, preserving node/dc labels where needed.
6. **Table:** read/write latency, SSTables, memtable, tombstone scans, partition sizes, disk, and compaction.
7. **Dependencies/annotations:** app deployments, schema changes, repairs, compactions, topology changes.
8. **Metric data quality:** exporter health, missing series, unit conversions, counter resets, label cardinality.

On every chart, specify **unit, scope, and aggregation**. For example: “Coordinator read requests/s — sum across nodes in dc1” differs from “Table local read count/s — max node per table”.

A solid investigation starts from **user-impact panels**, then drills down along `service → operation → coordinator/node → keyspace → table`. Never start by picking a random table just because it is large.

## 18. Self-check exercises

**Question 1.** Why can you not take `p99` from three Cassandra nodes and average them as the cluster p99?

**Answer:** Percentiles are non-linear. You need aggregatable histograms/distributions or per-node views; averaging p99 gauges does not produce cluster-wide p99.

**Question 2.** An API sends 100 logical write requests with RF = 3. Can you assume total cluster table write count will always equal 100?

**Answer:** No. Replica operations, coordinators, retries, and write mechanics cause node/table-level counts to differ from logical request counts.

**Question 3.** `ClientRequest.Read` latency rises while coordinator CPU is low. Can you rule out Cassandra?

**Answer:** No. Another replica may be experiencing disk/GC or network congestion, and the coordinator must wait for responses to satisfy CL.

**Question 4.** A table shows rising tombstones scanned alongside rising read p99. What should you inspect first?

**Answer:** Schema/partition design and query patterns, TTL/DELETE usage, SSTables/compaction; never lower `gc_grace_seconds` blindly just to silence the symptom.

**Question 5.** Why is `node_filesystem_avail_bytes` not a Cassandra JMX table metric?

**Answer:** It typically comes from an OS/host exporter reflecting host filesystem capacity. Always distinguish its source and mountpoint from Cassandra's internal storage metrics.

**Question 6.** When application timeouts spike while coordinator request latency stays normal, where should you investigate next?

**Answer:** Driver pool/acquisition, network, retries, service JVM, concurrency, and upstream API; compare metrics of matching scope before concluding.

**Question 7.** Should you attach each `device_id` as a Prometheus label for Cassandra latency?

**Answer:** Usually no. It creates massive cardinality; use stable operation/query template labels and put specific IDs into controlled logs/traces.

**Question 8.** Is `rate()` appropriate for a total-requests counter or a pending-tasks gauge?

**Answer:** For the **total-requests counter**. Pending tasks is a gauge; read its current level and trend rather than applying counter `rate()`.

**Question 9.** Does `nodetool tablestats` tell you the exact timeout rate of a specific Java API?

**Answer:** No. It provides per-table/node snapshots and statistics without knowledge of business API operations. Use application and driver/coordinator metrics instead.

**Question 10.** Why does a dashboard showing a request rate of 0 not guarantee the system is idle or healthy?

**Answer:** The collector/exporter may have lost connectivity or metric names may have changed. Check scrape health and missing-data intervals before drawing conclusions.

---

**Remember:** Effective Cassandra observability combines **application metrics** (what users experience), **coordinator request metrics**, **node health**, **keyspace**, and **table metrics**, each within its proper measurement scope. Distinguish **counters/gauges/histograms**, units, coordinators vs replicas, and logical traffic vs replica-level traffic. Use JMX/exporters and `nodetool` for evidence, bound label cardinality, cross-check RF/CL, tombstones, and compaction/repair, and start every investigation from **application request SLOs** before drilling down to nodes and tables.
