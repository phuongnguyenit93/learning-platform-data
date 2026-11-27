# Counter Deltas Across Measurement Windows and Restart Effects

> **Chapter:** Cluster Observability  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, distributed wide-column database management system.  
> **Focus:** Accurately reading **cumulative counters** over time intervals; computing deltas, rates, and error ratios; detecting resets from node/JVM/exporter restarts; and avoiding mistakes when aggregating metrics across replicas, nodes, and datacenters.

Many operational Cassandra indicators are **cumulative totals since process start**: requests processed, timeouts, dropped messages, compaction events, or completed stage tasks. If a dashboard reads `1,000,000` at 10:00 and `1,000,300` at 10:01, what usually matters is not “there are one million requests”, but **+300 requests in 60 seconds**.

When a Cassandra node **restarts**, however, in-memory/JMX counters can reset to 0. If a dashboard blindly subtracts `C(t_2) - C(t_1)`, a restart produces “-999,980 requests”, a nonsensical negative spike. Summing counters across multiple nodes before taking a delta lets a single node's drop corrupt the entire cluster graph.

Therefore, distinguish carefully:

1. **Cumulative counters:** monotonically increasing within one lifecycle of the measurement source, resetting when a new lifecycle starts.
2. **Instantaneous gauges:** legitimately rise and fall—e.g., pending compactions, heap used, and `Up` node counts.
3. **Timers/histograms/meters:** expose counts, distributions, or pre-computed rates; each component has distinct semantics.
4. **CQL `counter` columns for business data:** a persisted Cassandra data type, **completely different** from monitoring counters.

This lesson focuses on accurate measurement and operational decision-making across restarts, scrape gaps, node replacements, compaction/repair, and shifting read/write loads.

## 1. Learning objectives

After this lesson, you will be able to:

- Classify Cassandra/JMX/exporter metrics into counters, gauges, timers/histograms, and pre-computed rates.
- Compute **deltas** and **rates** in consistent units over a measurement window.
- Detect resets from Cassandra restarts, JMX exporter restarts, or series ID changes, and recognize what data cannot be reconstructed accurately.
- Use `rate()`, `increase()`, `irate()`, and `resets()` in Prometheus when a metric **genuinely is a counter**.
- Aggregate per-node/per-DC metrics in the right order: **compute rate per series first, then sum**.
- Avoid taking deltas of gauges, averaging per-node p99s, or confusing internal replica tasks with API requests.
- Design dashboards, alerts, and runbooks integrating restarts, node health, GC, compaction, repair, CQL, and Java Driver telemetry.
- Write data-integrity checks that catch negative spikes or fake zeros during resets and scrape gaps.

## 2. Cassandra metric types: reading the name is not enough

### 2.1. Counters (cumulative counts)

A monitoring counter \(C(t)\) represents the **total number of events observed** since the measurement source was initialized.

Conceptual examples:

- Read requests recorded by a coordinator metric.
- Timeouts/unavailable errors for an operation class.
- Dropped messages in a stage.
- Completed tasks or bytes processed by a subsystem, when exported as a counter.

**Property:** within **the same lifecycle** (incarnation) and stable semantics, \(C(t_2)\ge C(t_1)\) for \(t_2>t_1\). Restarts, metric-registry reinitialization, rollovers, or label changes break monotonicity between two samples.

Not every metric containing “total”, “count”, or “completed” in its name is automatically a standard Prometheus counter. Verify actual metric types and exporter sampling on your **running version**.

### 2.2. Gauges (point-in-time values)

Gauges legitimately rise and fall during normal operations:

| Illustrative gauge | Why can it drop validly? |
|---|---|
| Pending compactions | Tasks finish |
| Active thread/stage tasks | Work completes |
| Heap used / off-heap used | JVM GC or memory reclamation |
| Open client connections | Clients close sockets |
| Free disk bytes | New writes lower it; cleanup raises it |
| JVM/node uptime | Restart resets uptime near 0 |

**Never apply `rate(counter)` to a gauge just to plot speed.** If you need a gauge's rate of change, pick a function appropriate to gauges (`delta(gauge[...])` or `deriv()` in Prometheus), understanding noise and unit semantics.

### 2.3. Timers, histograms, and meters

In typical Cassandra/Java metrics stacks (e.g., Dropwizard Metrics over JMX):

- **Timer:** may carry a cumulative count plus latency distribution (min/max/percentiles), depending on JMX export.
- **Meter:** may carry a count plus pre-computed **one-/five-/fifteen-minute rates**.
- **Histogram:** tracks value distributions, counts, and quantiles/buckets depending on exporter conversion.
- **Gauge:** current value, which may hold pre-computed latency, size, or rate.

Specifically:

- `Count` on a timer/meter is typically cumulative since process start.
- `OneMinuteRate` is already a **pre-estimated rate**—never differentiate it a second time.
- `MeanRate` since process start is biased by process uptime; it is not equivalent to a recent 5-minute window rate.
- Per-node p99 latency is a **percentile**, never to be arithmetically averaged across nodes as cluster p99.

### 2.4. Distinguish monitoring counters from CQL `counter` columns

Cassandra has a CQL column type:

```sql
CREATE TABLE IF NOT EXISTS lab_obs.page_views (
    page_id uuid PRIMARY KEY,
    views counter
);

UPDATE lab_obs.page_views
SET views = views + 1
WHERE page_id = 11111111-1111-1111-1111-111111111111;
```

The `views counter` column is **durable business data replicated across replicas** with Cassandra counter-table semantics. It **does not reset when the Cassandra JVM restarts** and is not a JMX monitoring counter. Never apply “since process startup” logic to it.

This lesson covers **observability monitoring counters**, not application schema design with CQL counters.

## 3. Delta and rate formulas within a stable lifecycle

### 3.1. Absolute delta over a measurement window

Let two consecutive samples of a counter be:

- \(C_1=C(t_1)\).
- \(C_2=C(t_2)\).
- \(\Delta t=t_2-t_1>0\), in seconds.

Within **the same process/series, with no reset and consistent semantics**:

\[
\Delta C=C_2-C_1
\]

\[
r=\frac{\Delta C}{\Delta t}\quad
\text{(events/second)}
\]

Example: a metric records `25,000` read requests at 10:00 and `25,900` at 10:03.

\[
\Delta C=25,900-25,000=900
\]

\[
\Delta t=3\times60=180\text{ seconds}
\]

\[
r=\frac{900}{180}=5\text{ requests/s}
\]

**Important:** 5 requests/s is the three-minute average; you cannot infer the 1-second peak within that interval from two samples alone.

### 3.2. Keep units consistent

| Quantity | Preferred unit |
|---|---|
| Total events occurred | requests or events |
| `increase` over 5 minutes | requests / 5 minutes |
| Request `rate` | requests/s |
| Cumulative bytes written and byte delta | bytes or MiB/GiB |
| Byte write `rate` | bytes/s or MiB/s |
| Timeout ratio | Dimensionless percentage |
| Latency | ms or s, chosen consistently |
| Pending compaction | Task count (gauge), not tasks/s |

Distinguish **MB/s** (\(10^6\) bytes/s) from **MiB/s** (\(2^{20}\) bytes/s). Convert units explicitly when comparing NIC throughput, streaming, and SSTable compaction.

### 3.3. Long vs. short windows

A 5-minute window is smoother than 30 seconds because it spans more samples, yet:

- Too **short**: rates swing wildly from bursts or scrape jitter, especially at low traffic.
- Too **long**: masks brief spikes and exact restart timestamps.
- Dashboards need both fast windows for detection and longer windows for trends.
- If a reset occurs inside the window, subtracting endpoints manually is **invalid**; use reset-aware math and accept the limits of inference.

With a 15-second scrape interval, a 5-minute window contains about 20 samples when scraping is healthy—an **example configuration**, not a requirement for every system.

## 4. Crucial example: a restart makes a counter drop

Suppose Node A's read counter is scraped once per minute:

| Time | Value `C` | Illustrative node uptime | What happened |
|---|---:|---:|---|
| 10:00 | 1,000 | 7,200 s | Process running normally |
| 10:01 | 1,120 | 7,260 s | +120 reads |
| 10:02 | 1,250 | 7,320 s | +130 reads |
| 10:03 | 20 | 20 s | **Node restarted** before this scrape |
| 10:04 | 140 | 80 s | +120 reads since 10:03 sample |
| 10:05 | 270 | 140 s | +130 reads |

### 4.1. Blind subtraction produces negative values

Between 10:02 and 10:03:

\[
\Delta C_{\text{naive}}=20-1,250=-1,230
\]

There is no such thing as “minus 1,230 reads”. This is an **in-memory counter reset**, not negative traffic.

If you compute:

```text
delta = current - previous

if delta < 0:
    rate = delta / elapsed  # WRONG across a counter reset
```

dashboards show negative rates, broken charts, and meaningless alerts or comparisons.

### 4.2. After a reset, what do we actually know?

If the counter genuinely reset to 0 on startup and reached 20 at 10:03, we **observed** 20 reads after the restart. However, between the 10:02 scrape and the moment the old process stopped, **additional reads may have happened that were never scraped again**.

Therefore:

- `20` is only the post-reset slice observed by 10:03, not the exact total reads across 10:02–10:03.
- A reset-aware tool can **estimate** the increase from available counter samples.
- **You cannot recover exact lost pre-restart events** from just `1,250` and `20`.
- If you require audit-exact event counts (e.g., billing or compliance), use durable event logs/traces/CDC—not resettable JMX counters.

**Never clamp negatives to 0 and declare zero traffic for that minute.** Doing `max(0, C_2 - C_1)` hides post-restart reads and undercounts total traffic.

### 4.3. What can cause a reset?

| Cause | Signals | Why distinguish it |
|---|---|---|
| Cassandra JVM restart | Uptime drops near 0, process start time changes, node Down/Up | Multiple JMX/process counters reset together |
| Exporter restart | Exporter process start time changes while Cassandra uptime stays continuous | Exporter-synthesized counters may reset while raw JMX counters do not |
| Monitoring/TSDB restart | Scrape gap or broken sample sequence | Cassandra counters themselves kept climbing |
| Node replacement / rebootstrap | Host ID, instance, IP, or labels change | Old series ends, new series begins; not a continuation of the same source |
| Counter wrap / rollover | Value drops small while uptime stays continuous | Must know counter bit-width and exporter handling |
| Exporter/version/mapping change | Metric names, labels, units, or semantics change | Never merge two incompatible definitions as one series |
| Collection/scrape error | Missing, invalid, or stale samples | Insufficient evidence to infer a real restart |

Correlate **process identity, uptime, logs, lifecycle events, and metric types**—never diagnose “node restart” from a single chart dip alone.

## 5. Using Prometheus with counters

In Prometheus, the core functions for counters are `rate()`, `increase()`, `irate()`, and `resets()`.

> **Metric naming warning:** `cass_read_requests_total`, `cass_read_timeouts_total`, `cass_compaction_written_bytes_total`, and `cass_dropped_messages_total` in these examples are **hypothetical normalized names**, *not* guaranteed built-in Apache Cassandra names. A JMX exporter may emit `org_apache_cassandra_metrics_*` or custom names with different types/labels. Inspect `/metrics` or your exporter config first and confirm series are counters.

### 5.1. `rate()`: average per-second rate over a window

```promql
rate(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

Returns **requests/second** for **each matching time series**. `rate()` computes the windowed rate while handling **observed counter resets between samples** and extrapolating to window boundaries—so results can be fractional even for integer counts.

A window lacking enough valid samples may return no data; that is **not equivalent to a verified rate of 0**.

### 5.2. `increase()`: estimated increase over a window

```promql
increase(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

Returns the **approximate 5-minute increase** using Prometheus's extrapolation and reset handling. Never assume the result is always an exact integer or matches exact application event logs.

When traffic is steady:

\[
\operatorname{increase}(C[5m])
\approx\operatorname{rate}(C[5m])\times300.
\]

`increase()` is handy for event totals over a window; `rate()` is ideal for throughput per second. Both remain unable to observe pre-restart increments lost between two scrapes.

### 5.3. `irate()`: instant rate from the last two samples

```promql
irate(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

`irate()` uses only the **last two data points** in the range, making it responsive on high-traffic graphs to catch sharp bursts, yet volatile and unrepresentative of the whole 5-minute window. For stable SLO alerts, prefer `rate()` or `increase()` over sufficient windows.

### 5.4. `resets()`: counting observed counter drops

```promql
resets(cass_read_requests_total{cluster="prod"}[15m])
```

Counts **observed counter decreases** per series within the window. Useful for dashboard annotations, with caveats:

- Does not replace Cassandra restart logs.
- Misses resets if **series labels changed and a brand-new series started**.
- Cannot detect resets missed across unscraped gaps on both sides.
- Also fires on exporter rollovers/restarts; cross-check uptime and process identity.

### 5.5. Why not use `delta()` on counters?

`delta()` is built for **gauges**, not resetting counters. Running `delta(counter[5m])` yields negative numbers across restarts and ignores monotonic reset semantics. Likewise, `deriv()` computes linear gauge slope, not counter rates.

**Rule:** verify the metric type first, then choose the PromQL function.

## 6. Aggregating in the right order across nodes and DCs

### 6.1. One node restart breaks `rate(sum(counter))`

Suppose DC1 has two nodes:

| Time | Node A | Node B | Raw counter sum |
|---|---:|---:|---:|
| 10:00 | 1,000 | 800 | 1,800 |
| 10:01 | 1,120 | 880 | 2,000 |
| 10:02 | **20 after restart** | 960 | **980** |

If you sum cumulative counters first and then subtract:

\[
\Delta\operatorname{sum}(C)
=980-2,000=-1,020.
\]

**Wrong:** DC1 did not experience negative throughput. Moreover, summing raw counters across processes with different uptimes has **no meaning as “total requests since cluster creation”**.

**Right:** compute reset-aware rates per series/node first, then sum the rates:

```promql
sum by (cluster, dc) (
  rate(cass_read_requests_total{cluster="prod"}[5m])
)
```

With `increase`:

```promql
sum by (cluster, dc) (
  increase(cass_read_requests_total{cluster="prod"}[5m])
)
```

Why: **each node has its own lifecycle and resets**. Evaluating per series lets Prometheus detect Node A's reset cleanly without corrupting Node B's rate.

### 6.2. Pitfalls that break cluster sums

| Issue | Consequence |
|---|---|
| Duplicate scrapes of one JVM by two exporters | Double-counting unless deduplicated/filtered |
| One node stops scraping | Summed rate drops artificially due to missing node |
| Replacement node gets a new `instance` label | New series lacks history; creates observation gaps |
| One metric tracks coordinator requests, another tracks replica reads | Not comparable 1:1 |
| Different DCs serve different traffic sources | Cluster sum hides a broken or failed-over DC |
| Mismatched scrape intervals or retention | Distorts short-window rate comparisons |
| Metric relabeled or unit changed | Artificial discontinuities unrelated to traffic |
| Keyspace/table labels dropped during aggregation | Loses ability to separate workloads |

Define **what is being counted**: “client request to coordinator”, “request to a replica”, “internal mutation”, “stage task”, and “streamed bytes” are distinct events. RF=3 does not mean every client write increments every metric exactly three times.

### 6.3. Essential labels

An observability pipeline normally preserves:

- `cluster`: which cluster.
- `dc` and `rack`: failure domains and WAN boundaries.
- `host_id` or stable node identity, plus scrape `instance`.
- `keyspace`/`table` when the metric is genuinely table-scoped.
- `operation` or `scope`: `Read`, `Write`, `RangeSlice`, `CAS`, etc. per exporter.
- `environment`: lab/staging/production.
- `exporter` and version during pipeline migrations.

**Cardinality warning:** never put partition keys, user IDs, request IDs, or event IDs into per-sample Prometheus labels—that explodes series count and overwhelms the TSDB. Use sampled logs/traces for individual keys.

### 6.4. On node replacement, never “stitch” counters as one continuous process

During node replacement, Cassandra host ID or exporter `instance` may change. New series start small with no pre-bootstrap history. Dashboards should:

1. Annotate topology change timestamps.
2. Keep node and process incarnation identities distinct.
3. Read rates on the new series only after sufficient scrape samples arrive.
4. Compare total rate changes against application traffic and node availability.
5. Never conclude “traffic dropped” when a metric source simply stopped being scraped.

Some pipelines attach a logical role label that persists across host replacements—handy for dashboards, provided it **never hides process resets and lifecycles**.

## 7. Error ratios, dropped messages, and traffic scale

### 7.1. Error ratios require matching denominators

A common goal is measuring **timeout ratio among read requests**:

\[
\text{timeout ratio}
=\frac{\text{read timeouts in window}}
{\text{read attempts in same window}}\times100\%.
\]

Requirements:

- Numerator and denominator must measure the **same layer** (client, coordinator, or driver) and request class.
- Identical `cluster/dc/operation` scope.
- Never mix “driver retries” with “node-received requests” without verifying definitions.
- When traffic is 0, the ratio is **undefined**—never treat it as 0% and declare “service healthy”.

Illustrative normalized PromQL:

```promql
sum by (cluster, dc) (
  rate(cass_read_timeouts_total{cluster="prod"}[5m])
)
/
clamp_min(
  sum by (cluster, dc) (
    rate(cass_read_requests_total{cluster="prod"}[5m])
  ),
  0.001
)
```

`clamp_min` prevents division by zero, **yet can skew ratios at very low traffic**. Production alerts should enforce a **minimum volume gate** and verify the timeout metric is a proper subset of the request metric:

```promql
(
  sum by (cluster, dc) (
    increase(cass_read_timeouts_total{cluster="prod"}[5m])
  )
  /
  clamp_min(
    sum by (cluster, dc) (
      increase(cass_read_requests_total{cluster="prod"}[5m])
    ),
    1
  )
) > 0.02
and on (cluster, dc)
sum by (cluster, dc) (
  increase(cass_read_requests_total{cluster="prod"}[5m])
) > 100
```

This is an **illustrative formula**, not a recommended SLO threshold. Replace 2% / 100 requests with business targets, driver observations, and exact exporter semantics.

### 7.2. Dropped messages signal pressure, not necessarily 1:1 request errors

Cassandra stages track dropped messages. Rising counters show messages were discarded per stage semantics, yet:

- Not every dropped message equals a failed API request.
- One request can spawn multiple messages or retries.
- Not every timeout corresponds to exactly one dropped message.
- Exact stage/metric names and counting vary by Cassandra version.

Watch **drop rate per stage** alongside pending/blocked queues, GC, disk I/O, and client p99/timeouts. A restart resetting dropped counters to 0 **does not mean the underlying performance bottleneck is gone**.

### 7.3. p99 latency: never average p99 values

Suppose Node A has p99 = 20 ms and Node B has p99 = 500 ms. Their arithmetic mean `260 ms` is **not** cluster p99. Quantiles are non-linear and depend on per-node request counts and distributions.

If your exporter truly emits **cumulative histogram buckets with matching `le` boundaries**, compute DC-wide p99 by summing bucket rates:

```promql
histogram_quantile(
  0.99,
  sum by (dc, le) (
    rate(cass_read_latency_seconds_bucket{cluster="prod"}[5m])
  )
)
```

**Mandatory condition:** `..._bucket` series must **genuinely exist as cumulative histogram bucket counters**. Never run this on JMX timers that expose only `p99` gauges or snapshot quantiles. For quantile-only JMX timers, display per-node p99 or use an exporter/histogram pipeline supporting distribution aggregation—**never average pre-computed quantiles**.

## 8. Scrape gaps, stale series, and missing observability data

### 8.1. Four cases to distinguish

| Case | What you see | Accurate conclusion |
|---|---|---|
| Real traffic is zero | Counter stays flat while scrapes succeed continuously | Rate in that window is genuinely 0 |
| Node Down | Scrape `up=0` or missing samples; node unavailable | Missing metrics, not necessarily zero cluster traffic |
| Exporter endpoint broken | `up=0`, while Cassandra may still serve CQL | Observability outage; verify via node/logs/clients |
| Node/Pod replaced, labels changed | Old series goes stale, new series starts | Stitch timeline via events; never infer zero traffic |

Prometheus `up` only reports whether **target scraping succeeded**, not that Cassandra is healthy. A node can serve metrics while CQL is unavailable, or serve CQL fine while the exporter is dead.

### 8.2. Why avoid blind `or vector(0)`?

Queries missing samples normally yield **no data**. Coercing missing data to 0 unconditionally makes dashboards display “0 timeouts, 0 reads” during an exporter outage or dead node, hiding telemetry loss.

Good monitoring separates:

1. **Service availability:** driver/CQL SLOs, quorum, errors.
2. **Telemetry availability:** scrape targets, sample freshness, exporter health.
3. **Metric values:** read/write rates, latency, dropped messages, compaction.

Missing telemetry must trigger its own alert whenever that metric matters operationally.

### 8.3. Interpolation cannot accurately reconstruct lost events

Prometheus computes rates from available samples, handles counter decreases, and extrapolates to window edges. Yet if a node processes 2,000 requests and crashes/restarts between two scrapes, the pre-restart count **is gone from memory**. No TSDB can recover those lost increments from a reset counter.

When audit-exact counts are required for billing, transactions, or deletions, **process counters are insufficient**. Use durable event logs, transaction/audit records, or CDC with replay guarantees.

### 8.4. Clock skew and sample timestamps

Because scrapes hit different nodes at slightly staggered times, dashboards summing rates over a shared window are **estimates**, not exact millisecond-aligned counts. NTP synchronization, scrape intervals, jitter, and `remote_write` delays all matter.

In Cassandra, OS clock synchronization also affects data timestamp reconciliation—a **separate concern** from time-series label/metric integrity.

## 9. Detecting restarts reliably

### 9.1. Require at least two corroborating sources

To confirm a Cassandra node restart:

- **JVM uptime** drops near zero, or process start timestamp shifts where exposed.
- **Cassandra logs** record shutdown/startup events for that host ID.
- **Node status** transitions `UN → DN/unreachable → UJ/UN` depending on state.
- Multiple **process-scoped counters** drop simultaneously.
- **Infrastructure/orchestrator** logs a host reboot, Kubernetes container restart increment, or deploy event.

If only one counter drops, suspect an exporter reset or metric relabeling. If only `up=0` fires, suspect a scrape failure.

### 9.2. Illustrative reset-detection queries

```promql
resets(cass_read_requests_total{cluster="prod"}[30m]) > 0
```

With a process start-time gauge **if actually exposed**:

```promql
changes(process_start_time_seconds{job="cassandra"}[30m]) > 0
```

**Warning:** `process_start_time_seconds` from a standalone exporter reflects **the exporter process**, not the Cassandra JVM. Verify which process it tracks before interpreting it. Cassandra JVM JMX uptime or server startup logs are far more reliable when exporters run out-of-process.

### 9.3. A restart is different from a node replacement

**In-place restart:** Cassandra host ID normally stays intact if data/system keyspaces survive; in-process metric registries reset.

**Node replacement:** host ID, IP address, and tokens/roles may change depending on replacement method; old time series terminate and new ones begin. That is a **membership change** requiring RF/replica verification, not merely a restart annotation.

Never “stitch” old-host counters to new-host counters into one continuous cumulative line; the source identity changed.

## 10. JMX and `nodetool`: reading raw values properly

### 10.1. Common inspection commands

In a lab or cluster with authorized access:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats lab_obs.events_by_account
nodetool tablehistograms lab_obs events_by_account
```

Each serves a distinct purpose:

| Tool / indicator | Primary meaning | Proper usage |
|---|---|---|
| `nodetool info` | Node state, uptime, and version-specific summary | Check process lifecycle age |
| `nodetool tpstats` / Completed | Cumulative completed tasks per stage for that process lifecycle | Sample repeatedly and watch for restarts |
| `nodetool tpstats` / Active, Pending | Currently running/queued tasks | **Gauges**, never treat as counters |
| `nodetool tpstats` / Dropped | Dropped messages per stage | When cumulative in your version, compute deltas/rates and watch for resets |
| `nodetool compactionstats` / pending | Pending compaction tasks | Gauge; track trends and context |
| `nodetool tablestats` | Per-table SSTables, disk, read/write stats | Verify metric type and accumulation scope |
| `nodetool tablehistograms` | Per-table latency/size distributions | Never difference quantiles like counters |
| JMX metrics | Count/Rate/Timer/Histogram/Gauge | Inspect MBean/attribute type before querying |

Never assume identical field names or defaults across all Cassandra versions. `nodetool` inspects the queried node only; running `tpstats` on Node A **does not** show Node B's counters.

### 10.2. Limits of manual “table snapshots”

Suppose an operator runs:

```text
10:00  nodetool tpstats  Completed=200000
10:05  nodetool tpstats  Completed=205000
```

For the exact same node and stage with no restart and a genuine counter, the 5-minute average rate is:

\[
r=\frac{205,000-200,000}{5\times60}
=\frac{5,000}{300}\approx16.67\text{ tasks/s}.
\]

If the node restarted during those 5 minutes, subtraction yields a negative or undercounted result. When sampling manually, record **timestamp, node ID, uptime, stage, version, and status** together—never just the raw `Completed` number.

### 10.3. Replica metrics and coordinator metrics are not identical

One Java API read can fan out from a coordinator to one or more replicas depending on CL and topology. Depending on metric:

- Coordinator client-request counts may increment once per received request.
- Replica/internal read-stage counts may increment multiple tasks per request.
- Timeout metrics increment when the coordinator declares a request failed.
- Java Driver retries can hit another coordinator, generating multiple attempts per app action.

Never apply a fixed `×3` RF=3 factor to convert per-node metrics into app requests. Before building any error-ratio panel, confirm **which metrics count attempts, completions, retries, and internal tasks**.

## 11. Restart-aware dashboards and alerts

### 11.1. Divide dashboards into four zones

**Zone A — Load and errors**

- Read/write requests/s by DC, node, and operation.
- Timeout/failure/unavailable rates and ratios with matching denominators.
- Java Driver p95/p99, retry counts, pool/connection health.

**Zone B — Node/replica health**

- `status` and available full replicas per keyspace/DC.
- JVM uptime, process start/restart events, heap/GC, CPU.
- Scrape success, metric staleness, exporter version.

**Zone C — SSTables and background tasks**

- Pending/active compactions, SSTable counts, disk used/free, tombstone warnings.
- Repair/streaming status, bytes/s, backlogs, and failures.
- Dropped messages/stage backlogs, thread-pool saturation.

**Zone D — Observability data quality**

- Active scraped series/nodes vs. true inventory/topology.
- Counter resets per hour/day.
- `no data` gaps, scrape jitter, and exporter rollouts.
- Annotations for deploys/restarts, node replacements, and bootstrap/decommission.

### 11.2. Correlated alerts rather than single-counter triggers

For example, rising read timeout rate paired with client p99 and pending compactions. When a counter resets, alerts must not silently clear simply because the raw timeout count dropped low; rely on `rate()` plus telemetry-health checks.

Decision matrix:

| Signal | Likely cause | Action |
|---|---|---|
| Raw count drops, uptime resets | JVM restart | Annotate restart; verify recovery and rates once enough samples arrive |
| Raw count drops, uptime steady, exporter restarted | Metric pipeline reset | Check exporter mapping and series identity |
| Read rate drops, `up=0` | Scrape/endpoint outage | Troubleshoot telemetry and Cassandra health independently |
| Timeout rate rises, p99 rises, disk near saturation | I/O/compaction contention | Check `compactionstats`, SSTables/tombstones, disk |
| Drop rate rises, pending threads rise | Stage bottleneck | Check GC/CPU/latency and background load |
| Cluster rate dips during node replacement | Series churn or real traffic loss | Compare driver QPS, ring, labels, and restarts |
| `no data` yet dashboard shows “0 timeouts” | Missing data coerced to 0 | Fix query and add telemetry-availability alert |

### 11.3. Choosing alert windows

- Fast signals: 1–5 minutes for acute symptoms (depending on QPS and scrape interval).
- Trend signals: 15–60 minutes for capacity, compaction debt, and sustained error growth.
- SLO/error budget: longer windows per service policy.
- Restart annotations: wide enough to show process replacement and post-recovery stability.

When a window has **too few samples or too few requests**, ratios become noisy. Minimum sample/traffic gates plus missing-telemetry alerts prevent false positives.

## 12. Real-world scenarios: reads/writes, compaction, and repair

### 12.1. “After a restart, dropped messages returned to 0—is the error gone?”

No. Dropped counters reset with the JVM. Check:

1. Cassandra uptime and restart logs.
2. `rate(dropped_messages_total[...])` once enough post-restart samples exist.
3. Pending/active stages, CPU, GC, disk, client timeouts/p99.
4. Whether repair, compaction, or bootstrap is still causing contention.

If the drop rate climbs again minutes later, the underlying load issue was never fixed; seeing raw `0` was merely **a new accumulation baseline**.

### 12.2. “Compaction surged while free disk dropped”

Separate:

- `compaction bytes written total` (counter, if exposed).
- `pending compactions` (gauge).
- `disk free bytes` (gauge).
- SSTable versions/tombstones, snapshots, and temporary output files.

Compaction writes new output files before freeing old inputs, temporarily reducing free disk. Never conclude “higher compaction => matching new user data growth”.

When Cassandra restarts, compaction counters can reset while **on-disk SSTable bytes do not drop to 0**. That is the clearest contrast between process-lifecycle metrics and durable storage state.

### 12.3. “Repair finished right around a restart, yet metrics reset”

A repair job may have aborted or entered a version-specific server state on restart. Raw counters resetting to 0 neither prove repair succeeded nor prove it vanished from schedules.

Inspect job/session history, `nodetool repair_admin` where supported, covered token ranges/replicas, validation/streaming/finalization logs, and final status. **Repair completion comes from workflow/session records**, never from raw `tpstats` `Completed` totals.

### 12.4. “DC-wide average QPS dropped after bootstrapping a new node”

Separate three possibilities:

1. Application traffic genuinely dropped.
2. Load shifted onto the new node, which the dashboard missed due to label/inventory filtering.
3. An old node retired, its series went stale, and aggregate queries lacked coverage.

Cross-check app/driver QPS, per-node rates, DC node inventory, and scrape target health before concluding traffic changed.

## 13. CQL lab for windowed counter observation

### 13.1. Create a standard event table (not a CQL `counter`)

Example for a lab environment with DC `dc1` and enough replicas for RF=3:

```sql
CREATE KEYSPACE IF NOT EXISTS lab_obs
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS lab_obs.events_by_account (
    account_id uuid,
    event_id timeuuid,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
```

### 13.2. Run a small bounded workload

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_obs.events_by_account (
    account_id, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    7c627d5a-a6b0-11ef-8ae8-0242ac120002,
    'created',
    'sample'
);

SELECT event_id, event_type
FROM lab_obs.events_by_account
WHERE account_id = 11111111-1111-1111-1111-111111111111
LIMIT 20;
```

Run safely in the lab a handful of times and watch coordinator/driver read/write metrics. The goal is seeing **counters increment over time**, not benchmarking QPS manually.

### 13.3. Sample before and after a controlled restart

In a **lab where restarts are permitted**:

1. Record timestamp, node, JMX counter, and uptime from your real metric source.
2. Generate light traffic and capture two or three samples over a few minutes.
3. Restart **one** lab node cleanly; **never restart production nodes just for testing**.
4. Capture uptime/process start, raw counter, and logs from that same node.
5. Compare naive subtraction against reset-aware handling, checking Prometheus `rate`/`resets` if available.
6. Verify scrape `up` and whether any series labels changed.
7. Check cluster/RF/CL health after restart to confirm the workload keeps running.

Record sheet:

| Time | Node ID | Uptime | Read counter | Valid delta? | Rate | Notes |
|---|---|---:|---:|---|---:|---|
| T0 | A | 3,600 s | 1,000 | No prior sample | — | Baseline |
| T+60s | A | 3,660 s | 1,150 | Yes: +150 | 2.5 req/s | Same process |
| T+120s | A | 12 s | 15 | **Do not subtract directly** | Estimate / insufficient | Restart |
| T+180s | A | 72 s | 165 | Yes: +150 | 2.5 req/s | New process |

**Numbers are illustrative only**, not fixed `nodetool` output. Look at T+120: the counter drop is a reset, leaving no exact subtraction for total requests across the interrupted window.

### 13.4. Alert tests

Test three cases:

- Counter stays flat with healthy scrapes while workload stops: rate drops cleanly to 0.
- JVM restart: no negative traffic, reset/event annotation appears, no false claim of exact lost-event counts.
- Exporter/scrape outage while Cassandra keeps serving: dashboard shows **no data** and fires a telemetry-health alert instead of faking 0 errors.

## 14. Java: validating two counter samples and detecting restarts

A Java app uses Cassandra Java Driver to send and time requests, while **JMX metrics remain a separate observation stream**. Below is a pure-Java example validating two counter samples before computing a delta—intentionally **not** inventing lost counts across a restart.

```java
import java.time.Instant;
import java.time.Duration;
import java.util.OptionalDouble;

public final class CounterInterval {
    static final class Sample {
        final String nodeId;
        final Instant time;
        final long processStartEpochSeconds;
        final long count;

        Sample(String nodeId, Instant time,
               long processStartEpochSeconds, long count) {
            this.nodeId = nodeId;
            this.time = time;
            this.processStartEpochSeconds = processStartEpochSeconds;
            this.count = count;
        }
    }

    static OptionalDouble ratePerSecond(Sample before, Sample after) {
        long elapsedMillis =
            Duration.between(before.time, after.time).toMillis();

        if (elapsedMillis <= 0 || before.count < 0 || after.count < 0) {
            return OptionalDouble.empty();
        }
        // Different node or process: cannot subtract cumulative totals.
        if (!before.nodeId.equals(after.nodeId)
                || before.processStartEpochSeconds
                   != after.processStartEpochSeconds) {
            return OptionalDouble.empty();
        }
        // A decrease may mean reset, rollover, or measurement pipeline issue.
        if (after.count < before.count) {
            return OptionalDouble.empty();
        }

        double seconds = elapsedMillis / 1000.0;
        return OptionalDouble.of(
            (after.count - before.count) / seconds);
    }

    public static void main(String[] args) {
        Sample s1 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:00:00Z"),
            1795230000L, 1000L);
        Sample s2 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:01:00Z"),
            1795230000L, 1120L);
        Sample s3 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:02:00Z"),
            1795236060L, 20L); // Different process incarnation

        System.out.println(ratePerSecond(s1, s2));
        // OptionalDouble[2.0]

        System.out.println(ratePerSecond(s2, s3));
        // OptionalDouble.empty: the interval crosses a restart
    }
}
```

**Learning point:** this code **deliberately returns `empty`** across a restart instead of fabricating an exact rate. Prometheus `rate()` returns a **reset-aware estimate** over a multi-sample series; the two approaches are complementary—exact two-sample deltas within one process incarnation vs. time-series estimation.

For production use:

- Source `nodeId`/process start time reliably without mistaking an exporter process for the Cassandra JVM.
- Validate value units, timestamps, and duplicate/out-of-order samples.
- Never mix counter sources or metric semantics across versions.
- Return explicit `UNKNOWN/RESET/STALE` states alongside numeric values rather than bare `OptionalDouble`.
- When aggregating, compute per-node rates first, then sum while keeping DC/cluster labels.
- For monotonic metrics persisted across restarts (if any), **do not apply JVM-restart reset rules mechanically**—follow exact metric semantics.

### 14.1. Java Driver: workload vs. telemetry

Java Driver 4.x example issuing a partition-key lookup to pair with request metrics:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class CassandraReadWorkload {
    public static void main(String[] args) {
        UUID accountId = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            PreparedStatement ps = session.prepare(
                "SELECT event_id, event_type FROM lab_obs.events_by_account " +
                "WHERE account_id = ? LIMIT 20");

            BoundStatement stmt = ps.bind(accountId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(stmt);

            // Read client-side driver metrics and Cassandra JMX metrics
            // through separate configured monitoring exporters.
            // One successful execute() does not establish a 1:1 mapping
            // to every internal node counter.
        }
    }
}
```

**Note:** this snippet does not pull JMX counters from Cassandra directly; use an authorized exporter, JMX client, or monitoring stack. One CQL query cannot measure compaction bytes, dropped messages, or peer replica state.

## 15. Practice calculations on a small dataset

### 15.1. Computing rate before a restart

Node A records:

| Time | Reads count |
|---|---:|
| 14:00 | 50,000 |
| 14:05 | 51,200 |

No restart, 300-second window:

\[
\Delta C=1,200,\qquad r=1,200/300=4\ \text{reads/s}.
\]

If the app counted 1,000 logical reads in that window, never force the two numbers to match—retries, internal tasks, and counting boundaries differ.

### 15.2. Rate and ratio need the exact same scope

Suppose DC1 records over 5 minutes:

- 6,000 client read attempts from a trusted metric.
- 120 read timeouts over the same attempt set.
- 5,880 read completions under the same definition.

Then:

\[
\text{Read QPS}=6,000/300=20\text{ requests/s}
\]

\[
\text{Timeout ratio}=120/6,000=0.02=2\%.
\]

If the timeout counter reset mid-window and `120` was an **unadjusted raw difference**, `2%` is untrustworthy. Verify semantics and data continuity before reporting SLOs.

### 15.3. Comparing two nodes with different process ages

| Node | Raw count | 5-minute rate |
|---|---:|---:|
| A, uptime 4 days | 5,000,000 | 80 req/s |
| B, restarted 20 min ago | 15,000 | 60 req/s |

The raw sum `5,015,000` tells **nothing** about current traffic or total traffic since cluster creation. The valid summed rate across matching series is **140 req/s**. Node A's 5 million cumulative count does not mean A is currently carrying “333× B's load”.

### 15.4. Impact of a scrape gap

Over a 5-minute window, one node misses 3 minutes of scrapes. Its rate cannot be computed at the same confidence as healthy peers. Report:

- Nodes with quality telemetry / expected total nodes.
- Sample counts and observation gaps.
- Estimated total QPS paired with **telemetry coverage**.
- An alert when a node goes unscraped for long, even before app SLOs breach.

Never scale a 4/5-node sum up by `5/4` if traffic across nodes is skewed.

## 16. Restart-resilient dashboard design checklist

**Sources and semantics**

- [ ] Every metric is explicitly classified as counter, gauge, timer, histogram, or meter.
- [ ] Metric scope is documented: coordinator, replica, client driver, node, table, DC.
- [ ] Units (events, seconds, bytes), labels, and exporter mappings are verified.
- [ ] Process/host identity and versions are tracked; node restarts are distinguished from exporter restarts.
- [ ] CQL `counter` columns are never confused with monitoring counters.

**Queries and arithmetic**

- [ ] `rate`/`increase` is computed per counter series **before** summing across DC/cluster.
- [ ] Raw counters are never subtracted across restarts, and `delta()` is never used on counters.
- [ ] `resets()` or equivalent signals annotate restarts without assuming every reset is a Cassandra node restart.
- [ ] Windows contain adequate samples; `no data` is never coerced to “0 events”.
- [ ] Error ratios pair matching numerator/denominator scopes and enforce traffic minimums.
- [ ] p99s are never averaged; quantiles are computed only from compatible histogram buckets.

**Operations**

- [ ] Dashboards show node/DC Up/Down, JVM uptime, scrape health, and restart annotations.
- [ ] Compaction/repair/tombstone/disk panels sit alongside error rates for root-cause triage.
- [ ] Bootstrap/decommission streaming/rebalancing is separable from live app load.
- [ ] Alerts are tested against process restarts, exporter restarts, scrape gaps, and label churn.
- [ ] CQL/Java Driver runbooks exist to verify metrics against live symptoms.
- [ ] Data retention, sampling, and label cardinality fit within TSDB capacity.

## 17. Questions and exercises

**Exercise 1 — Simple delta.** A node's read counter grows from 17,000 to 18,800 over 6 minutes with no restart. Compute the delta and average requests/s.

**Exercise 2 — Reset.** 12:00 counter=4,800; 12:01 counter=4,950; 12:02 counter=30 with JVM uptime=20 s. Why is `30 - 4,950` wrong? What cannot be reconstructed accurately?

**Exercise 3 — Aggregation.** Node A climbs 1,000 → 1,100, Node B climbs 800 → 900, then A restarts and reads 15. What breaks with `rate(sum(C))`? What formula should replace it?

**Exercise 4 — Gauge.** `PendingCompactions` drops from 12 to 3 over 5 minutes. Is that a “negative counter event rate”? How should you interpret it?

**Exercise 5 — Choosing PromQL.** You need total read QPS for `dc2`. Pick the valid option: `sum(rate(metric[5m]))` over `dc2` series, or subtracting raw summed counts across two snapshots?

**Exercise 6 — Timeout ratio.** Over 10 minutes there are 2,000 read attempts and 16 timeouts from the same source with clean scrapes. Compute timeout ratio and QPS.

**Exercise 7 — Missing data.** A dashboard reports 0 read errors ever since the exporter stopped scraping, while the Java Driver logs many timeouts. What query/alerting bug caused this?

**Exercise 8 — p99.** One node has p99=10 ms, another has p99=200 ms, with very different request volumes. Why is \((10+200)/2=105\) ms not DC-wide p99? What data is required to compute it?

**Exercise 9 — Simultaneous restarts.** Right after a deploy, all three nodes in one rack show raw dropped counts near 0. What evidence is needed before concluding “pressure is gone”?

**Exercise 10 — Business counter.** A CQL table has a `views counter` column; the JVM restarts. Should you expect `views` to reset to 0 like a JMX request counter? Explain.

### Answer hints

1. Delta `1,800`; interval `360` seconds; rate `5 req/s`.
2. Counter reset in a new lifecycle. Events between the last pre-crash scrape and shutdown went unrecorded, so the exact minute total cannot be recovered.
3. The node reset pulls the raw sum down, creating a negative delta; compute `rate` per series first, then `sum`.
4. No—it is a gauge dropping as backlog drains; check trend and compaction/output rate metrics if available.
5. `sum by(dc)(rate(metric{dc="dc2"}[5m]))` over valid counter series.
6. Ratio `16/2,000 = 0.8%`; QPS `2,000/600 ≈ 3.33 req/s`.
7. “Missing telemetry” was coerced to 0 errors; alert on scrape failures and never mask `no data`.
8. Percentiles do not add or average linearly; you need compatible histogram buckets/distributions or raw samples.
9. Uptime, logs, `resets()`, scrape health, post-restart dropped **rate** after enough samples, pending stages, GC, and client p99.
10. No. CQL `counter` is durable replicated data, not a JVM-lifecycle JMX metric.

## 18. Conclusion

- **Monitoring counters gain meaning from deltas and time windows**, not raw cumulative totals alone.
- Within one lifecycle, \(\Delta C=C_2-C_1\) and \(r=\Delta C/\Delta t\); **restarts break the assumption** behind direct subtraction.
- **`rate()` and `increase()` handle observed resets**, yet remain estimates over available samples—they cannot recover increments lost between scrapes before a crash.
- **Compute rates per series before summing** across nodes/DCs/clusters. Never sum raw counters across processes of different ages to measure throughput.
- **Counters, gauges, timers/histograms, meters, and CQL `counter` columns are distinct types.** Verify metric types before picking calculations.
- **No data does not mean zero traffic.** Monitor telemetry-pipeline health alongside Cassandra and the Java Driver.
- Across restarts, bootstraps, replacements, or repairs, correlate metric shifts with **JVM uptime, logs, tokens/topology, CL, compaction, and client state** instead of guessing from a single line chart.
- A trustworthy dashboard does more than draw smooth lines; it surfaces **scope, units, coverage, and data reliability** to guide sound operational decisions.
