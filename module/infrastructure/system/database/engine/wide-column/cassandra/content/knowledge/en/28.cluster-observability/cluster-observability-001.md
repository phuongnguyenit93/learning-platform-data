# Baseline Performance, SLI/SLO, and Alert Thresholds for an Apache Cassandra Cluster

## 1. Why establish a baseline before setting alerts?

**Apache Cassandra** is a **distributed wide-column** database: data is spread across multiple nodes, and requests are handled by a coordinator that contacts replicas according to the **replication factor (RF)** and **consistency level (CL)**. Query latency can spike due to poor partition design, heavy tombstone reads, GC, compaction, inter-replica networking, disk I/O, or shifting application load.

A dashboard showing “CPU 75%” or “p99 150 ms” is **not enough to conclude whether the system has a problem**. You need to know what load the cluster normally runs under, which query classes are executing, what commitments were made to users, and when to page an on-call operator.

This lesson distinguishes four concepts:

| Concept | Question to answer | Example |
|---|---|---|
| **Baseline** | What is normal system behavior at a specific load, configuration, and time? | Read p99 95–130 ms at 2,000 req/s during peak hours |
| **SLI** (*Service Level Indicator*) | How is actual quality measured, by what definition and window? | Ratio of valid read requests that succeed; ratio of reads completing ≤ 250 ms |
| **SLO** (*Service Level Objective*) | What is the minimum desired quality over a time period? | 99.95% successful reads over 30 days |
| **Alert threshold** | When is there risk of violating an objective or need for human intervention? | High error-budget burn across both 1-hour and 5-minute windows |

**A baseline is an empirical observation; an SLO is a service target.** Do not turn a terrible p99 into an SLO simply because it is the “normal” state of an unoptimized system. Conversely, an overly ambitious SLO that cannot be measured or is not agreed upon with users will not help operations.

Throughout the examples, assume a Java service queries Cassandra to look up device state by `device_id`, writes events into a time-series table, and requires separate availability/latency targets for these two request classes. All illustrative numbers below **are hypothetical for learning purposes**, not default threshold recommendations for every cluster.

## 2. Where to measure along the request path?

A request from a Java application is not identical to an internal Cassandra operation:

```text
         User / API
             |
             v
       Java Service
     [pool, queue, retry, timeout]
             |
             v
      Java Driver 4.x
        [load balancing]
             |
             v
      Coordinator node  ----> Replica A
             |          ----> Replica B
             |          ----> Replica C
             |
      [CL/RF, read repair,
       network, memtable/SSTable]
             |
             v
      Response to app
```

Distinguish three observation layers:

1. **User/API:** end-to-end latency and the outcome the user actually receives. This is usually the right place to measure product-level SLIs.
2. **Application/Java Driver:** Cassandra operation latency from the client perspective, timeout/unavailable errors, retries, pool usage, and queued requests. Suitable for SLIs of the **application's Cassandra dependency**.
3. **Cassandra node/cluster:** server-side client request latency, request rate, queues, dropped messages, compaction, GC, disk, tombstones, and repair. These are **causal indicators** for diagnosis.

A failed API request caused by application logic errors is not necessarily a Cassandra failure. Conversely, a write request that returns success from the coordinator may still fail to meet **all business expectations**, for example when an older mutation timestamp loses to last-write-wins. For an SLI to be meaningful, you must precisely define **a successful event**, **measurement boundaries**, **request classes**, and **statistical windows**.

### Do not mix consistency levels

`ONE`, `LOCAL_QUORUM`, `QUORUM`, and `ALL` have different execution paths, replica wait behaviors, and failure characteristics. Tag at least `operation`/`query_class`/`consistency` during analysis, while avoiding partition keys or user UUIDs as metric labels because they cause **cardinality explosion**.

## 3. How to collect a reliable baseline?

A useful baseline is a **contextual set of reference profiles**, not a single once-captured “average latency” number.

### Minimum context dimensions

- **Workload:** point reads by partition key, intra-partition range queries, writes, LWTs, batches; separate lightweight requests from multi-row scans.
- **Traffic:** requests/second, concurrency, payload size, row size, number of accessed partitions, and hot key distribution.
- **Topology:** node count, data centers, RF, CL, whether any node is down or all are healthy.
- **Data:** table size, SSTable count, tombstone count, TTL, partition size, cache hit/miss.
- **Time:** peak/off-peak hours, weekdays/weekends, backfill runs, and compaction/repair windows.
- **Versions and changes:** Cassandra, Java Driver, JVM, OS, schema, compaction strategy, and timeout settings.

### Establishment process

1. **Select a healthy window** long enough to capture load cycles, e.g., 14–28 days if data is available and not dominated by incidents.
2. Identify the **critical query classes** for the service and their corresponding CLs.
3. Simultaneously collect request rate, success/error counts, p50/p95/p99 client latency, server latency, saturation, compaction/GC, and disk metrics.
4. Record the **configuration versions and load conditions** of the baseline, annotating deployments, repairs, node outages, and anomalous events.
5. For a new system without history, run **load tests on a comparable staging environment**, then calibrate with production metrics once available.
6. Separate baselines **by hour/load tier**; update periodically, but never let a prolonged incident silently become the new “normal”.

**HYPOTHETICAL baseline example** for a steadily running service (not a Cassandra benchmark):

| Query class | Observed load | App p50 | App p99 | Error rate | Notes |
|---|---:|---:|---:|---:|---|
| `read_device_by_id` | 1,500 req/s | 12 ms | 110 ms | 0.01% | `LOCAL_QUORUM`, hot keys controlled |
| `write_event` | 800 req/s | 9 ms | 75 ms | 0.02% | Append-only, 7-day TTL |
| `read_device_day` | 80 req/s | 38 ms | 310 ms | 0.03% | More rows, single partition only |
| `lwt_update_state` | 25 req/s | 75 ms | 520 ms | 0.05% | CAS/Paxos, not grouped with normal writes |

These numbers are comparable only if **measured under the same definition**. When reading p99, always check both sample count and measurement window; a query class with only a few requests in 5 minutes produces a very noisy p99.

## 4. The four golden signals: latency, traffic, errors, and saturation

The **four golden signals** model applies well to Cassandra, provided it is mapped to concrete metrics.

| Signal | Application layer | Cassandra/node layer | Diagnostic question |
|---|---|---|---|
| **Latency** | CQL request duration, p50/p95/p99, % under threshold | ClientRequest read/write latency, server histogram, coordinator activity | Is the client slow or is the server slow? |
| **Traffic** | Requests/s by query class and CL, bytes | Read/write operations, network I/O, request rate | Is load up due to users or a retry storm? |
| **Errors** | Timeout, unavailable, driver error, deadline exceeded | Failure/unavailable/timeout metrics if exposed by version; dropped messages | Which requests are failing, and to what extent? |
| **Saturation** | In-flight/queued requests, driver pool pressure | CPU, GC pauses, heap, disk I/O, disk free, compaction backlog, thread-pool pending tasks | Which resource limit is being approached? |

Do not watch only a single “high CPU” metric. A cluster can have moderate CPU yet **very high disk latency**, or p99 spikes caused by **tombstones** in a few partitions. Conversely, higher CPU during compaction while latency stays within SLO may not require paging someone immediately.

A useful rule of thumb:

- **SLIs/SLOs** prioritize symptoms experienced by the application/users.
- **Node metrics** help pinpoint root causes and forecast degradation.
- **Alerts** combine real user impact with early signs of imminent capacity exhaustion or data-safety risk.

## 5. Define SLIs with clear numerators, denominators, and units

### 5.1. Availability SLI

For a Cassandra point-read request class by partition key:

```text
availability = valid requests with outcome "success"
               -------------------------------------
                  total valid requests executed
```

You must specify:

- **Denominator:** one application logical operation or each network attempt to a coordinator? Usually use **logical operation** so retries do not inflate the denominator and distort the SLI.
- **Success:** the query executes successfully, including returning **zero rows** if that is a valid business outcome.
- **Failure:** timeout at deadline, unavailable, unrecovered server/driver error within budget, or a result failing defined requirements.
- **Excluded:** synthetic test requests or invalid client-input errors may be excluded, but the exclusion list must be defined upfront; do not exclude timeouts just because “a replica might still have persisted the write”.

### 5.2. Latency SLI

A less ambiguous definition than “good latency”:

```text
fast_read_ratio =
  successful logical reads completing within <= 250 ms
  ----------------------------------------------------
               successful logical reads
```

This is a **ratio of requests under a threshold**, not p99. You can use p99 for diagnostic analysis, while the SLO should have an explicit numerator and denominator. Specify whether latency is measured from when the **application calls the driver** until the response returns, and whether pool wait/retry time is included. If measuring end-to-end API latency, the 250 ms threshold applies to the entire API, not just the database.

### 5.3. Freshness and correctness if required by the application

For sensor data, you may also define SLIs for:

- **Freshness:** % of active devices whose latest reading is no older than 2 minutes according to a trusted time source.
- **Completeness:** % of expected event IDs ingested on time, measured at the pipeline/broker rather than relying solely on Cassandra rows.
- **Correctness:** % of state transitions obeying business versioning or free of duplicate writes; requires business-level instrumentation.

Never use `CL = QUORUM` as the definition of “100% latest data”: consistency level does not guarantee business ordering or clock accuracy.

## 6. Set SLOs by query class and error budget

An SLO requires a **target entity, metric, threshold, window, data source, and owner**. The table below is a **HYPOTHETICAL** proposal for learning:

| Service / query class | SLI | 30-day SLO | Dimension |
|---|---|---:|---|
| `read_device_by_id` | Successful logical reads / total valid reads | **99.95%** | Availability |
| `write_event` | Logical writes acknowledged per CL / total valid writes | **99.9%** | Write-path availability |
| `read_device_by_id` | Successful reads ≤ 250 ms / total successful reads | **99%** | Latency |
| `read_device_day` | Successful reads ≤ 750 ms / total successful reads | **99%** | Query-class-specific latency |

**Error budget** is the acceptable amount of non-SLO-compliant outcomes within the window:

```text
allowed_bad_fraction = 1 - SLO
allowed_bad_requests ≈ eligible_requests × allowed_bad_fraction
```

Example with 1,000,000 valid reads over 30 days:

- Availability SLO of **99.95%** allows about **500** failed reads.
- Latency SLO of **99%** allows about **10,000** successful reads exceeding 250 ms if the latency denominator is also 1,000,000.
- If only 900,000 reads **succeeded**, the 99% latency budget is **9,000 slow reads**, not 10,000: **the denominator is different**.

### Error-budget policy

SLOs should not merely sit on a dashboard. You can establish rules such as:

1. When burn rate spikes: prioritize error reduction, roll back risky changes, pause non-urgent load tests/backfills.
2. When most of the monthly budget is consumed: review deployment risk and capacity expansion plans.
3. Post-incident: identify affected request classes, budget consumed, and improvement actions with assigned owners.

Do not try to “protect” an SLO by stripping difficult requests from the denominator after failures occur. Any change to SLI definitions must be versioned and agreed upon.

## 7. Percentiles, histograms, and measurement windows: avoid misinterpretation

**Average latency** routinely hides the long tail. In Cassandra, a few hot partitions or queries scanning many tombstones can drive p99 high even when p50 looks healthy.

| Statistic | Meaning | Limitation |
|---|---|---|
| p50 | Median: half of samples do not exceed this value | Does not reflect the slowest requests |
| p95 | 95% of samples do not exceed this value | Can miss an important top 5% tail |
| p99 | 99% of samples do not exceed this value | Noisy at low sample counts and sensitive to bursts |
| Mean | Arithmetic average | Masked by skewed distributions or outliers |
| % ≤ threshold | Share meeting a deadline | Well suited to a clearly defined latency SLI |

If one node has a p99 of 50 ms and another has a p99 of 500 ms, **never average the two p99 values** to infer cluster p99. To aggregate properly, use **histogram buckets** or compute quantiles across the combined distribution in your metrics system.

### Choose the right window for the purpose

- **5 minutes:** detect spikes; noisy during low traffic.
- **1 hour:** check sustained degradation and fast burn.
- **6 hours / 24 hours:** detect slow degradation and prolonged compaction backlogs.
- **7 or 30 days:** evaluate long-term SLOs and trends.

Every chart should state **timezone, time range, aggregation, request volume, CL, and query class**. Adding nodes or changing retry policies between periods can change the meaning of “total requests” if left unannotated.

### Histograms need buckets aligned with the SLO

If the latency SLO is 250 ms, the application histogram needs a bucket at **`0.25` seconds** (or an equivalent ratio metric). If the nearest buckets are 0.1 and 0.5 seconds, `histogram_quantile` interpolation cannot accurately recover the count of requests ≤ 250 ms.

## 8. Collecting Cassandra metrics: server, exporter, and Java Driver

Cassandra typically exposes metrics over **JMX**, grouped under categories such as **ClientRequest**, **Table**, **ThreadPools**, **Compaction**, **Storage**, **Cache**, and JVM indicators. Exact MBean names, `scope` fields, meter/timer types, and **exported units** vary across Cassandra versions/distributions and JMX exporter configurations.

Key observation groups:

| Group | Signals to collect | Issues indicated |
|---|---|---|
| **ClientRequest Read/Write** | Request latency, timeouts, failures, unavailable (if exposed) | User-facing failures, overloaded coordinators |
| **ThreadPools** | Active/pending/completed tasks, dropped tasks/messages | Growing queues, dropped requests |
| **Compaction** | Pending tasks, bytes compacted, compaction workload | Backlogs, I/O and disk-space pressure |
| **Table** | Read/write latency, SSTable count, tombstones scanned, partition-size metrics if available | Schema/partition/tombstone tail latency |
| **Storage** | Load, streaming/hints, node state | Node imbalance, bootstrap/repair |
| **Cache** | Hit/miss, evictions across available caches | Cache churn and read amplification |
| **JVM** | Heap/non-heap, GC frequency/pauses | Stop-the-world GC, memory pressure |
| **OS/Disk/Network** | CPU, disk capacity, disk latency/queue, network retransmits | Hardware and network saturation |

**Never assume a Prometheus metric name from an article exists out of the box on your cluster.** Cassandra exposes metrics via JMX; Prometheus JMX exporter, Jolokia, or agents may rename metrics, convert units, and alter labels. Always verify actual MBeans and exporter mappings on your **exact version** before writing alerts.

### Layer your operational dashboards

A minimal dashboard set includes:

1. **Service overview:** availability, latency SLI, error-budget burn, and request volume.
2. **Cassandra cluster:** status/up/down, RF/CL context, per-node read/write rates, latencies, failures.
3. **Bottlenecks:** pending thread pools, dropped messages, GC, disk, compaction, hints/repair.
4. **Hot tables/partitions:** read/write skew, tombstones, partition sizes, and heavy query classes.
5. **Change context:** deployments, schema alterations, topology changes, compaction/repair, and backfill workloads.

Avoid collapsing everything into a single aggregate chart. **A single node** suffering severe disk latency can be masked by the cluster average even as `QUORUM` queries begin timing out.

## 9. Instrument the application for accurate SLIs

**Application-defined metrics** let you measure each *logical operation*. Example naming for Prometheus/Micrometer (these are **illustrative application-emitted metrics**, not built-in Cassandra metrics):

- `app_cassandra_requests_total{operation, outcome, consistency}` — counter tracking logical operations.
- `app_cassandra_request_duration_seconds_bucket{operation, outcome, le}` — histogram buckets of completed logical operations by latency.
- `app_cassandra_request_duration_seconds_count{operation, outcome}` — sample count for the same histogram.
- `app_cassandra_inflight_requests{operation}` — gauge of currently executing requests.

Use only labels with **bounded value sets**: `operation=read_by_id|write_event|read_day`, `outcome=success|failure`, `consistency=LOCAL_QUORUM|ONE`. **Never** put `device_id`, `order_id`, `query_text`, or `exception_message` into metric labels: cardinality can grow unbounded.

Key conventions:

- Record exactly one outcome per **logical operation** after its retry sequence finishes, if the SLI is defined on logical operations.
- Categorize exceptions: timeout, unavailable, server failure, client validation error; keep full exception details in traces/logs and only low-cardinality categories in metric labels.
- Use `System.nanoTime()` to measure **elapsed duration**, not `System.currentTimeMillis()`.
- Attach trace IDs to logs/traces, never push every trace ID into a Prometheus label.
- Include driver pool/retry wait time if the chosen SLI boundary covers application-side Cassandra operation duration.

## 10. Sample PromQL to query SLIs (only for the declared application metrics)

The queries below assume the application **actually exports** the metrics/labels defined in Section 9 in seconds. They **will not run out of the box on a freshly installed Cassandra cluster** without instrumentation.

### 10.1. Logical read failure ratio over 5 minutes

```promql
sum(rate(app_cassandra_requests_total{
  operation="read_by_id",outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(app_cassandra_requests_total{
    operation="read_by_id"
  }[5m])),
  1e-9
)
```

A value of `0.002` means **0.2% errors** in that window. Availability SLI = `1 - error_ratio`, assuming every logical request is tagged with exactly one `success` or `failure` outcome.

### 10.2. Ratio of successful reads completing in ≤ 250 ms

```promql
sum(rate(app_cassandra_request_duration_seconds_bucket{
  operation="read_by_id",outcome="success",le="0.25"
}[5m]))
/
clamp_min(
  sum(rate(app_cassandra_request_duration_seconds_count{
    operation="read_by_id",outcome="success"
  }[5m])),
  1e-9
)
```

To be valid, the histogram must define a **`0.25` bucket** and count **once per successful logical read**, even when the driver retried internally.

### 10.3. p99 for performance investigation, not automatically an SLO

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(app_cassandra_request_duration_seconds_bucket{
      operation="read_by_id",outcome="success"
    }[5m])
  )
)
```

This is an estimate from histogram buckets, not an exact per-request measurement. If you use native histograms or another exporter format, adjust the syntax accordingly. Across all three queries, low-traffic windows should have a **volume gate** or insufficient-data marker to avoid treating `0/0` clamped to zero as a “healthy” system.

## 11. Alert thresholds: distinguish page, ticket, and dashboard

An alert is only useful if the recipient has a **concrete action to take**. Separate severity tiers:

| Tier | Signal type | Example (illustrative, must calibrate) | Action |
|---|---|---|---|
| **Page / P1** | Fast SLO burn, widespread request failures, imminent disk exhaustion | High burn rate in two windows; down nodes breaking CL availability | Investigate immediately via runbook |
| **Page / P2** | Sustained SLO degradation or near-term risk | High burn over 6h and 30m; capacity projected to exhaust within hours | On-call responds per severity |
| **Ticket** | Worsening trend with time to act | Free disk below reserve threshold, compaction pending growing for hours | Plan capacity/tuning |
| **Dashboard/info** | Fluctuation without current impact | Brief GC spike not affecting SLIs | Monitor, do not wake on-call |

Thresholds suitable for **capacity** but not standalone pages:

- Warning when **free disk drops below 20%** and growth rate projects exhaustion within days.
- Urgent alert when **free disk drops below 10%** or exhaustion is imminent, especially on imbalanced nodes or during compaction needing temporary scratch space.
- **These 20%/10% numbers are illustrative only.** Cassandra compaction, streaming/repair, and snapshots can require substantial headroom; capacity planning must account for SSTable sizes, node skew, compaction strategy, and data growth rate.

**Do not page on “CPU > 70% for 1 minute” as a standalone condition.** High CPU while latency and availability meet SLO can simply be legitimate traffic. Conversely, rising disk latency causing timeouts even at low CPU requires action.

## 12. Error-budget burn rate and multi-window alerting

Burn rate expresses how many times faster the system is consuming its error budget compared to a steady pace:

```text
budget_fraction = 1 - availability_slo
burn_rate = observed_error_fraction / budget_fraction
```

With a **99.95%** read availability SLO:

```text
budget_fraction = 1 - 0.9995 = 0.0005 = 0.05%
If observed error = 0.72%:
burn_rate = 0.0072 / 0.0005 = 14.4
```

Sustaining a **14.4** burn rate for **1 hour** against a 30-day SLO window (720 hours) consumes roughly **2% of the monthly budget in a single hour**: `14.4 × 1 / 720 = 0.02`.

### Multi-window, multi-burn-rate alerting (example configuration)

One starting option, **not a universal default**:

- **Fast burn:** error ratio exceeds `14.4 × budget_fraction` over **both 1 hour and 5 minutes**, with sufficient request volume. Used to page on rapid incidents.
- **Medium burn:** exceeds `6 × budget_fraction` over **both 6 hours and 30 minutes**. Used to catch sustained degradation.
- **Slow burn:** exceeds `1 × budget_fraction` over longer windows such as 3 days and 6 hours; can create a ticket instead of a page.

Gate alerts on both **error ratio** and **request volume**. At 2 requests/hour, one timeout yields a 50% error ratio, whose system significance differs from an incident affecting 100,000 requests/hour. Conversely, critical low-traffic services need complementary signals such as synthetic probes or event-freshness checks.

### Illustrative Prometheus alert rule

The rule below assumes the `app_cassandra_requests_total` application metric from Section 9 and a 99.95% read SLO; adapt `operation`/labels to your real system:

```yaml
groups:
  - name: cassandra-dependent-service-slo
    rules:
      - alert: CassandraReadFastBurn
        expr: |
          (
            sum(rate(app_cassandra_requests_total{
              operation="read_by_id", outcome="failure"
            }[1h]))
            /
            clamp_min(sum(rate(app_cassandra_requests_total{
              operation="read_by_id"
            }[1h])), 1e-9)
          ) > (14.4 * 0.0005)
          and
          (
            sum(rate(app_cassandra_requests_total{
              operation="read_by_id", outcome="failure"
            }[5m]))
            /
            clamp_min(sum(rate(app_cassandra_requests_total{
              operation="read_by_id"
            }[5m])), 1e-9)
          ) > (14.4 * 0.0005)
          and
          sum(increase(app_cassandra_requests_total{
            operation="read_by_id"
          }[1h])) >= 1000
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Read error budget is burning rapidly"
          description: "Check logical read failures and Cassandra runbook"
```

This rule is an **educational template**: it is only valid if counters carry the assumed labels, requests are counted exactly once, Prometheus scrapes reliably, and metric names match. In production, use recording rules for readability, partition by service/region/DC, and monitor for missing telemetry (*no data*). The 1,000 requests/hour volume gate here is not a universal default.

## 13. Causal alert thresholds on Cassandra nodes

Some situations require alerting before error rates breach the SLO because they signal **imminent loss of availability or data safety**.

| Signal | Warn when... | Page when... | What to cross-check |
|---|---|---|---|
| **Node unavailable** | One node is down while RF/CL still serves | Enough replicas are lost to break CL or severely cut redundancy | `nodetool status`, DC, RF, CL, topology changes |
| **Disk free / growth** | Headroom is low, growth rate is abnormal | Exhaustion is imminent or node cannot write/compact | SSTables/snapshots/compaction |
| **Dropped messages / request failures** | Deviates from baseline alongside latency | Sustained rise impacting availability | Thread pools, saturation, network |
| **Compaction pending tasks** | Queue grows continuously across windows | Backlog causes severe disk/latency pressure | Disk IOPS, throughput, TWCS/STCS/LCS |
| **GC pauses** | p95/p99 GC pause rises alongside tail latency | Long pauses, request failures, or unresponsive node | Heap, allocation, GC logs |
| **Tombstones scanned** | Tail reads rise on a specific table | Query failures or latency SLO breach due to tombstones | Schema, TTL, DELETE, read pattern |
| **Repair overdue** | Scheduled repair window missed | Risk of stale data surviving past tombstone grace window | RF, offline nodes, `gc_grace_seconds` |

**Absolute thresholds must be calibrated against your baseline and configuration.** For example, `PendingTasks > 0` at a point in time is not an incident on its own; the problem is **continuous growth without draining alongside secondary symptoms**. Likewise, an occasional dropped message may not warrant a page, whereas rising drops with load and timeouts are a critical signal.

### By node and by data center

At a minimum, distinguish `cluster`, `datacenter`, `node`, and `role` (if applicable). Alerting when one node diverges several-fold from the median of peer nodes in the same DC can catch a “straggler” before the cluster average deteriorates. However, differences from heterogeneous hardware or nodes currently bootstrapping/repairing should be annotated rather than assumed to be faults.

## 14. Practical diagnostic commands when an alert fires

The following commands are **read-only by intent** and commonly used in Cassandra administration. Exact syntax and output fields vary by version; run from a host with `nodetool`/CQLSH and appropriate permissions, preferring read-only observer credentials.

```bash
# Overview of node status and distribution by DC/rack.
nodetool status

# Queues/thread pools/dropped messages.
nodetool tpstats

# Active and pending compactions.
nodetool compactionstats

# Table statistics (replace with real keyspace/table names).
nodetool tablestats telemetry_ks.readings_by_device_day

# Streaming, bootstrap/rebuild state if relevant.
nodetool netstats

# General heap/GC statistics if supported by the version.
nodetool gcstats
```

For a slow query class, inspect the schema/query:

```sql
-- Read only by known partition key.
SELECT event_at, event_id, temperature_c
FROM telemetry_ks.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 100;
```

If using CQL tracing or driver-side tracing, **enable it selectively** on sample requests because broad tracing adds significant overhead. Do not log or export sensitive full partition keys, payloads, or tokens into logs/metrics.

When a cluster is unstable, avoid running `nodetool compact`, bulk `flush`, cluster-wide `repair`, or unbounded table scans **just to gather signals**. Those operations add I/O and can worsen the incident.

## 15. Java Driver 4.x: measuring latency and outcome of a logical query

The Java example below uses **Apache/DataStax Cassandra Java Driver 4.x**. A small recorder abstraction allows integration with Micrometer/Prometheus/OpenTelemetry later without coupling to a specific metrics library.

In a test keyspace already selected with `USE <keyspace>;`, create a scalar table for partition-key lookups (do not run on a production table containing live data):

```sql
CREATE TABLE IF NOT EXISTS device_state_by_id (
    device_id text PRIMARY KEY,
    state text
);
```

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ObservedDeviceRepository {
    public interface RequestRecorder {
        // Export counters/histograms by query class, never by deviceId.
        void record(String operation, String outcome, double durationSeconds);
    }

    private final CqlSession session;
    private final PreparedStatement select;
    private final RequestRecorder recorder;

    public ObservedDeviceRepository(CqlSession session, RequestRecorder recorder) {
        this.session = session;
        this.recorder = recorder;
        this.select = session.prepare(
            "SELECT state FROM device_state_by_id WHERE device_id = ?"
        );
    }

    public String findState(String deviceId) {
        long started = System.nanoTime();
        String outcome = "failure";
        try {
            Row row = session.execute(select.bind(deviceId)).one();
            // Returning no row is still a successful query outcome.
            outcome = "success";
            return row == null ? null : row.getString("state");
        } finally {
            double seconds = (System.nanoTime() - started) / 1_000_000_000.0;
            recorder.record("read_by_id", outcome, seconds);
        }
    }
}
```

**Explanation:**

- `System.nanoTime()` is suitable for elapsed duration; it is not an epoch timestamp for Cassandra `USING TIMESTAMP`.
- `row == null` is not necessarily a Cassandra error; it can mean “no data for key”, depending on the business contract.
- `finally` records the metric even when `execute` throws an exception; the exception still propagates to the caller.
- This snippet records **one sample per `findState` call**. If the caller retries by invoking the method again, that produces multiple samples; for an accurate logical-operation SLI, place instrumentation **outside the application retry loop** or use a shared request context.
- If `recorder.record(...)` can throw exceptions, design the recorder so it never breaks the business request; in production, test failure modes of the telemetry pipeline.

This is a short example for understanding instrumentation; it omits metric export libraries, trace context, async execution, timeouts, and exception classification. In real deployments, manage these pieces carefully to avoid **double-counting** requests.

## 16. Case study: p99 rises while availability stays healthy

Suppose the `read_by_id` baseline is p99 110 ms at 1,500 req/s, but the dashboard now shows p99 jumping to 400 ms for 20 minutes while availability remains 99.98%. This **does not by itself prove** the cluster is down, but it can threaten the latency SLO.

A sound investigation sequence:

1. **Quantify impact:** how far did the latency SLI “% ≤ 250 ms” drop, and how many requests were slow?
2. **Scope the issue:** all query classes or a single table; one DC or both; one node or the whole cluster?
3. **Compare load:** requests/s, payload/row size, concurrency, recent deployments, backfills, or retry storms.
4. **Analyze Cassandra:** server read p99, pending tasks, GC pauses, disk read latency, tombstones scanned, SSTable count, compaction backlog.
5. **Inspect queries:** is the partition key sufficient, is there a hotspot or wide intra-partition scan, did the client change CL?
6. **Isolate the layer:** if app latency increases while server latency stays flat, check the driver pool, network, and application queues/retries before tuning compaction.

Sample analysis (**hypothetical** numbers):

| Signal | Before | During incident | Hypothesis |
|---|---:|---:|---|
| App p99 read | 110 ms | 400 ms | Tail latency increased |
| Server read p99 | 85 ms | 350 ms | Server-side time also rose |
| Compaction pending | 2–5 | 900 and rising | Severe backlog |
| Disk read p99 | 5 ms | 70 ms | Disk may be saturated |
| Read failures | 0.02% | 0.02% | Availability not yet degraded |
| Latency SLI ≤ 250 ms | 99.6% | 96.5% | Violating 99% SLO |

An **evidence-aligned** conclusion is “compaction/disk correlates with tail latency; investigate I/O causes”, **not** “compaction is definitely the culprit” before checking the timeline and workload.

## 17. Case study: availability drops suddenly when a node goes down

Suppose an `RF = 3` cluster serves application reads/writes at `LOCAL_QUORUM` in one DC. Losing one node still lets the cluster satisfy quorum for many partitions if the other two replicas are healthy, but **remaining fault tolerance shrinks**. If another replica becomes unavailable or a network partition occurs, timeouts/unavailable errors can spike rapidly.

Initial checklist:

- How many nodes are down **in which DC**, and what are the actual replication strategy/RF of the keyspace?
- Are failing requests **reads** or **writes**; is CL `ONE`, `LOCAL_QUORUM`, or `ALL`?
- Are network, disk, or GC issues making an “up” node too slow to respond in time?
- Are clients retrying aggressively, shifting extra load onto the surviving replicas?
- Are hints, pending repairs, and compaction backlogs building up after the node returns?

**Do not hastily lower CL to “restore the SLO”** if doing so breaks business consistency guarantees. Failover or CL changes must follow data contracts and approved runbooks. Likewise, “node up” does not mean “all replicas have converged” after a long outage.

## 18. Establishing baselines and testing alerts in a staging environment

Never manufacture incidents by shutting down production nodes or forcing compactions on a live cluster. A lab workflow:

### Step A — Prepare the environment

1. Use a staging cluster with matching topology, RF, CL, and Cassandra version, or document exact differences.
2. Create tables matching simple query patterns; load data with realistic row and partition sizes.
3. Connect the Java Driver and metrics stack across app, Cassandra JMX exporter, and JVM/OS collectors.
4. Verify labels, units, histogram buckets, and clock synchronization in the monitoring stack.

### Step B — Collect a controlled baseline

Generate stepped load levels (e.g., 25%, 50%, 75%, 100% of expected load). Hold each step long enough for latency/queues to stabilize; never treat overly short intervals as a “baseline”.

Record at each tier:

| Target load | Actual throughput | Error rate | Client p95/p99 | CPU/disk latency | Compaction pending |
|---|---|---|---|---|---|
| 25% | Measure, do not assume | Measure | Measure | Measure | Measure |
| 50% | Measure | Measure | Measure | Measure | Measure |
| 75% | Measure | Measure | Measure | Measure | Measure |
| 100% | Measure | Measure | Measure | Measure | Measure |

Watch out for **coordinated omission** in load tests: if the load generator pauses sending requests when the server slows down, measured latency looks artificially good. Use an open-loop load model and measure client queueing/timeout delays too.

### Step C — Test alerts

In staging, inject **controlled faults** such as adding latency to a mock dependency or lowering success traffic in a metric generator to verify:

- Fast-burn alerts fire when error ratio breaches thresholds across **both long and short windows**.
- Alerts do not page when traffic is below the minimum-volume gate, while synthetic probes/separate signals still cover quiet periods.
- Latency SLI alerts fire when the ratio of requests ≤ threshold drops; do not rely solely on p99.
- Runbooks, dashboards, and on-call responders receive enough context to pinpoint the affected DC/query class/node.
- After recovery, alerts auto-resolve cleanly without flapping.

**Testing an alert means more than testing a PromQL expression.** Validate notification routing, deduplication/grouping, escalation, detection latency, and remediation steps.

## 19. Response runbook: from alert to safe action

A concise, actionable runbook should help on-call answer:

1. **Impact:** Which SLI is breaching? What is the error-budget burn? How many requests/minute and services are affected?
2. **Scope:** Which query class, data center, and node, and since when? Is it tied to a deploy or schema change?
3. **Cluster state:** node up/down, CL/RF, pending tasks, timeouts, compaction, disk/GC, network.
4. **Low-risk mitigations first:** pause non-essential backfills/analytics, curb retry storms, roll back load-increasing deployments, isolate a bad query per procedure.
5. **No destructive shortcuts:** do not lower `gc_grace_seconds`, delete SSTables manually, force cluster-wide compaction/repair without assessing impact, or arbitrarily downgrade CL.
6. **Confirm recovery:** availability and latency SLIs return to normal across multiple windows, queues drain, disk/GC stabilize, and repair/topology follow-ups are scheduled if needed.
7. **Postmortem:** timeline, root cause, budget spent, threshold adjustments, action owners, and recurrence prevention.

### An actionable alert template

```text
Alert: CassandraReadFastBurn
Severity: page
Service: device-api
Query class: read_by_id
Consistency: LOCAL_QUORUM
SLO: 99.95% availability over 30d
Current: error ratio exceeds fast-burn in 1h and 5m
First checks: dashboard read errors, driver timeouts,
  nodetool status/tpstats, disk/GC, recent deploy
Runbook: internal link maintained by operations team
```

Never embed **raw query parameters**, sensitive partition keys, tokens, or credentials in alerts. Runbook and dashboard links must point to real internal systems; the lines above illustrate formatting only.

## 20. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Watching only **CPU** or node status | Misses tail latency and driver errors | Combine end-to-end SLIs + server diagnostics |
| Using **average latency** as the entire SLO | Masks the long tail | Use % under deadline and supporting percentiles |
| Averaging **per-node p99s** | Aggregate misrepresents the true distribution | Aggregate histograms from samples/aligned buckets |
| Mixing point lookups with LWTs/range scans | Unfair baselines and SLOs | Separate by query class and CL |
| Counting **every retry attempt** as an independent request | Inflates or skews error ratio/traffic | Compute SLIs at the logical-operation boundary |
| Using partition keys as Prometheus labels | Cardinality explosion overloads monitoring | Use bounded labels and separate trace IDs/exemplars |
| Paging on every 1-minute spike | Alert fatigue | Multi-window burn, volume gates, `for` |
| Static disk thresholds ignoring growth rate | Alerts too early or too late | Forecast + compaction/snapshot headroom |
| Looking only at cluster averages | Hides unhealthy nodes/DCs | Per-node/zone dashboards and comparative alerts |
| Letting baselines auto-update during incidents | Treats prolonged outages as “normal” | Pin baselines to healthy periods, review changes |
| Changing CL during timeouts without checking semantics | Can violate consistency | Follow RF/CL and business-contract procedures |
| SLOs without owners or runbooks | Pages produce no clear action | Pair every SLO with an owning team and runbook |

## 21. Self-check questions and answers

**Question 1.** Your baseline read p99 is 120 ms, and your latency SLO is 99% ≤ 250 ms over 30 days. If p99 over the **last 5 minutes** rises to 180 ms, has the monthly SLO been breached?

**Answer:** **You cannot conclude a 30-day SLO breach from a 5-minute p99 alone.** You must measure the **ratio of successful logical reads ≤ 250 ms** over the full SLO window. Even if p99 is accurately computed over the same sample set and window, p99 = 180 ms being below 250 ms actually indicates at least roughly 99% of samples in that window met the threshold; either way, it is **not** a conclusion for the entire month.

**Question 2.** An application executes 1,000,000 logical reads/month with a 99.95% availability SLO. Roughly how many failed requests exhaust the budget?

**Answer:** About **500 requests**, assuming the denominator is 1,000,000 and all are eligible requests.

**Question 3.** With a 99.95% availability SLO, what burn rate corresponds to a 0.72% error ratio?

**Answer:** `0.0072 / 0.0005 = 14.4`.

**Question 4.** Why should you not average the p99 values of three nodes to report cluster p99?

**Answer:** Percentiles are properties of a **distribution**, not linearly additive or averageable. You need histograms or proper aggregation across all samples.

**Question 5.** A service executes point lookups, range scans, and LWTs. Should all three share one p99 latency threshold?

**Answer:** **Not by default.** They have different costs and semantics; define SLIs/SLOs per query class and user need.

**Question 6.** Should you page if one node's CPU hits 80% for 30 seconds while application SLIs remain normal?

**Answer:** Usually **not from CPU alone**. Check normal load, other saturation signals, trends, and SLI impact; a dashboard note or ticket may suffice.

**Question 7.** A request times out at the client, but one replica successfully wrote it. Should it count as an availability SLI success for the application?

**Answer:** If the **logical request was not acknowledged as successful within the deadline** per the application contract, it is a **failure** for the client-side SLI even if a replica received the mutation. Data reconciliation is handled separately.

**Question 8.** Why can a “disk below 10%” threshold not serve as a universal safety standard for every cluster?

**Answer:** You must factor in **compaction temporary space, streaming/repair, snapshots, data growth rate, configuration, and topology**. 10% is only an example and may already be too late.

**Question 9.** Server ClientRequest latency alerts look normal while Java Driver duration jumps sharply. What should you check?

**Answer:** Check driver pools/queues, retries, DNS/network, coordinator routing, application thread pools, and differences in measurement scope before blaming Cassandra nodes.

**Question 10.** Why does `histogram_quantile` over 0.1 s and 0.5 s buckets fail to give the exact share of requests ≤ 0.25 s?

**Answer:** Without an `le="0.25"` bucket, you do not know how many samples lie between 0.1 and 0.25. To base an SLI on a 250 ms threshold, design matching buckets from the start.

**Question 11.** When `nodetool compactionstats` shows pending tasks steadily rising, should you force a major compaction immediately?

**Answer:** **No.** Check disk I/O, SLI impact, traffic drivers, compaction strategy, and headroom before acting. Forcing compaction can overload the node further.

**Question 12.** Why does an RF 3 / CL QUORUM cluster not automatically prevent a late-arriving event from rolling back state?

**Answer:** CL governs how many replicas must respond, whereas Cassandra reconciles versions by **mutation timestamp**. Business ordering requires explicit versioning/CAS or suitable coordination.

---

**Remember:** For Cassandra, measure **baselines by workload, CL, topology, and time**, define **SLIs with explicit numerators and denominators**, choose **SLOs reflecting user needs**, and use **error-budget burn plus saturation signals** to create **actionable** alerts. Observe **Java Driver, Cassandra JMX, JVM/OS, and replication/compaction/repair** together; never equate server metrics with user experience. A good alert always includes context, an owner, a runbook, and a way to verify recovery.
