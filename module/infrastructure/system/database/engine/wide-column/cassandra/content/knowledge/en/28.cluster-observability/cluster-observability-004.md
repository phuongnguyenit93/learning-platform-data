# Read/Write Latency and Percentiles Instead of Averages Alone in Apache Cassandra

## 1. Why is “good average latency” not enough?

Apache Cassandra is a distributed **wide-column** database management system. Applications route operations by **partition key**, serve queries through tables modeled around access patterns, and choose a **consistency level** to coordinate reads and writes across replicas. A CQL operation may traverse the Java Driver, network, coordinator, replicas, memtables, SSTables, compaction, or active repair work.

A dashboard showing only **average read latency = 100 ms** fails to answer the crucial question: *How many users are waiting several seconds?*

Consider two cohorts, each with exactly 1,000 read requests:

| Latency distribution | Cohort A | Cohort B |
|---|---:|---:|
| Requests completing in 50 ms | 0 | 980 |
| Requests completing in 100 ms | 1,000 | 0 |
| Requests completing in 2,550 ms | 0 | 20 |
| **Mean (average)** | **100 ms** | **100 ms** |
| **p50** | **100 ms** | **50 ms** |
| **p95** | **100 ms** | **50 ms** |
| **p99** (nearest-rank) | **100 ms** | **2,550 ms** |

Both cohorts have **the exact same average**:

~~~text
A: 1,000 × 100 ms / 1,000 = 100 ms

B: (980 × 50 ms + 20 × 2,550 ms) / 1,000
 = (49,000 + 51,000) / 1,000
 = 100 ms
~~~

Yet Cohort B has **2% of requests taking 2.55 seconds**, while Cohort A has zero requests slower than 100 ms. For a user staring at a loading screen during one of those 2% requests, a pretty average offers no comfort.

That is why Cassandra observability requires **percentile/quantile latency**—especially **p50, p95, p99**, and **p99.9** when sample counts permit—alongside throughput, error rates, and resource metrics.

## 2. What do p50, p95, and p99 actually mean?

### 2.1. Defined over completed requests

- **p50 (median):** roughly 50% of observed requests have latency no higher than this value.
- **p95:** roughly 95% of requests do not exceed this value; the slowest group is about 5%.
- **p99:** roughly 99% of requests do not exceed this value; the slowest group is about 1%.
- **p99.9:** focuses on the far tail, where only about 0.1% of requests are slower.

In a sorted ascending sample of `N` latency values, the illustrative *nearest-rank* formula picks position:

~~~text
pX position = ceil((X / 100) × N)

Example N = 1,000:
p50: 500th value
p95: 950th value
p99: 990th value
~~~

Metrics libraries typically use histograms, buckets, or other interpolation/estimation methods, so p99 can differ slightly from nearest-rank. Keep the **method and resolution consistent** when comparing before and after.

### 2.2. A percentile is not “the fraction of time the system is fast”

If p99 = 200 ms over a measurement window, the accurate interpretation is that roughly **99% of observed requests completed within at most 200 ms**. It does not mean the machine ran fast 99% of the time, nor does it guarantee the exact probability for every future request.

A percentile is a **statistic of a sample set over a specific measurement interval**, influenced by load, time of day, query mix, and recording method.

### 2.3. Sample volume determines confidence

With only 50 requests in five minutes, p99 nearly equals the single slowest request; one outlier makes the graph jump wildly. With 100,000 requests, roughly 1,000 requests make up the slowest 1%, giving a much steadier signal for investigation.

Do not draw conclusions from p99 on a low-traffic table without checking:

1. Request count in the window.
2. Calculation window length (one minute, five minutes, one hour).
3. Sampling and outlier filtering behavior.
4. Whether timed-out/errored requests are included.
5. Whether the histogram measures **node, table, driver, or end-to-end** scope.

## 3. Cassandra latency spans multiple layers

A read request can traverse the following components:

~~~mermaid
flowchart TD
    U["Application / HTTP API"] --> A["Java Driver: node selection, connection, queue, retry"]
    A --> B["Network client → coordinator"]
    B --> C["Coordinator: route by token and consistency level"]
    C --> D["Replica: memtable / cache / SSTable / tombstones"]
    D --> C
    C --> E["Enough responses per read consistency"]
    E --> F["Network and driver return data"]
    F --> U
    G["Compaction, repair, GC, I/O, and background load"] -. impacts .-> D
    H["Cross-datacenter WAN"] -. impacts .-> C
~~~

Because multiple layers exist, clearly distinguish **when the stopwatch starts and stops**:

| Measurement level | Includes | Does not necessarily include |
|---|---|---|
| **Application latency** | From starting the Cassandra call until the app receives and processes the result per timer scope | Other HTTP steps outside end-to-end measurement |
| **Driver request latency** | Time observed by the driver, potentially including host selection, connection, request/retries, and network per metric type | Business logic before/after the request |
| **Coordinator/proxy latency** | Request handling on the coordinator node and waiting for relevant responses | Client-side queues or processing outside Cassandra |
| **Table/replica local latency** | Storage-engine read/write work on a single node | Full network round-trip, coordinator, and driver |
| **HTTP/API latency** | Total API serving time including business logic, Cassandra, and other backends | Does not by itself prove Cassandra is the culprit |

**Do not compare metrics of different scopes directly.** For instance, application p99 = 900 ms alongside table-local p99 = 40 ms is not a contradiction: the remaining time may sit in driver queues, coordinator wait, network, another replica, retries, or external dependencies.

You cannot compute `p99(client) - p99(table)` to deduce exact network p99. **Percentiles do not add or subtract like linear quantities**, because different percentiles can correspond to different requests.

## 4. Read and write latency must be separated

### 4.1. Read path

A `SELECT` targeting a specific partition may use the key cache, Bloom filters, memtable, SSTable indexes, and compressed chunks. If a partition spans many SSTables and contains many tombstones, a replica may have to merge numerous versions or scan many deleted rows before returning live rows.

Factors that increase **read latency**:

- Missing partition key or `ALLOW FILTERING` causing broad scans.
- Extremely wide partitions or unbounded clustering ranges.
- Overlapping SSTables when compaction falls behind.
- Heavy tombstones or expired TTL data within the scanned range.
- Disk I/O, low cache hit rate, decompression overhead, or CPU/GC pressure.
- Slow replicas, network/WAN delays, or coordinator waiting for read CL.
- Speculative reads and read-path reconciliation/repair mechanisms (version-dependent).

**A `LIMIT 20` does not guarantee a lightweight read**: Cassandra may still scan through large numbers of tombstones to find 20 live rows.

### 4.2. Write path

Normal writes travel through a coordinator to replicas, appending to commit logs and updating memtables on each replica. The client receives success once write consistency acknowledgements are met; SSTable flushes and compactions happen asynchronously in the background, so writes do not wait for compaction to finish.

Factors that increase **write latency**:

- Target nodes acknowledging slowly due to commit log/disk I/O or memtable pressure.
- Mutation queues, overload, CPU/GC pauses, or backpressure.
- Replication CL requiring more replicas, especially crossing WAN links with `QUORUM` or `EACH_QUORUM` across multiple DCs.
- Oversized mutations or batches; frequent updates/deletes adding write load and future compaction burden.
- Network errors/jitter, hinted handoff, streaming, or repair competing for resources.
- For **LWTs (`IF` / `IF NOT EXISTS`)**, Paxos consensus rounds take a very different path from regular writes and must be measured separately.

Never conclude “high write p99 means SSTable flush is slow” without inspecting commit logs, mutation stage, load, CL, and target nodes. **Normal writes do not wait for SSTable flushes to complete.**

### 4.3. Consistency levels reshape the latency tail

Consider a `NetworkTopologyStrategy` keyspace with RF=3 in the local DC:

- `ONE` requires acknowledgement from one replica per operation rules.
- `LOCAL_QUORUM` requires two of three replicas in the local DC.
- `ALL` requires every required replica.

When more acknowledgements are required, requests become sensitive to the **k-th slowest replica** in the required set. Still, do not assume latency scales linearly with acknowledgement count; coordinators issue requests in parallel and various optimizations govern completion timing.

In multi-DC deployments, `EACH_QUORUM` applies to supported write operations and requires a quorum in every DC; it can pull the latency tail toward the slowest DC or WAN link. `EACH_QUORUM` is **not a CL for standard `SELECT` queries**.

## 5. Reading a percentile chart correctly

A dashboard showing p50 = 8 ms, p95 = 45 ms, and p99 = 900 ms should be read in order:

1. **Which request set?** Read or write, which table/operation, which DC, coordinator or client view?
2. **Time window and sample count?** 500 requests per minute or 50,000 requests per minute?
3. **Spread?** A large p99/p50 ratio signals a long tail; p50 rising alongside p99 points to broader resource/load pressure.
4. **Are timeouts and errors rising?** If the slowest requests time out and drop out of the success histogram, successful-request p99 can actually drop while the system gets worse.
5. **Did throughput, concurrency, and resources** shift at the same time?

### Distinguishing four chart patterns

| Symptom | Initial hypothesis | What to check next |
|---|---|---|
| Flat p50, spiking read p99 | Specific slow partitions/queries, disk stalls, tombstone scans | Hot tables/partitions, SSTables per read, tracing, outlier nodes |
| Both p50 and p99 rising | Broad resource contention or network saturation | Traffic, CPU, GC, compaction, I/O, saturation |
| High driver p99, low table-local latency | Delay in queues, coordinators, retries, or network/WAN | Driver metrics, coordinator metrics, timeouts, network |
| Read/write p99 drops while timeouts rise | **Survivorship bias**: slow requests fail and leave the success sample | Compute SLIs including timeouts/errors, count total attempts |

**Do not watch the p99/p50 ratio alone.** A wide gap is a prompt to investigate, not proof by itself that the system is broken.

## 6. Averaging percentiles is mathematically wrong

A common mistake in multi-node metric aggregation is:

~~~text
p99_cluster = average(p99_node_1, p99_node_2, p99_node_3)
~~~

This is **mathematically invalid**. Percentiles cannot be aggregated via arithmetic mean, even if every node handles identical request counts. Each node's p99 describes only its own distribution and lacks information about the rest of the cluster-wide distribution.

### Simple example

- Node A serves 10,000 requests at p99 = 20 ms.
- Node B serves 100 requests at p99 = 2,000 ms.

The average of the two p99s is 1,010 ms, even though Node A handles almost all traffic. **The true p99 of the combined 10,100 requests must be computed from the merged distribution**, not by averaging 20 and 2,000.

**The right approach:** collect compatible histogram buckets from the nodes/instances being combined, **sum observation counts bucket by bucket**, and compute quantiles from the merged histogram—or use telemetry that supports true global distribution aggregation.

In Prometheus, an **illustrative query for an instrumented standard histogram**:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, operation) (
    rate(app_cassandra_request_duration_seconds_bucket[5m])
  )
)
~~~

This is **not a built-in Cassandra metric name**. It assumes the application exports an `app_cassandra_request_duration_seconds_bucket` histogram with `le` and `operation` labels; actual names depend on your collector. Never run this pattern on Prometheus summary quantiles (like `quantile="0.99"`) or sum/average summary quantiles.

With histograms, p99 accuracy depends on bucket placement; sparse buckets near your SLA yield coarse approximations. Align buckets to target latency thresholds while keeping label cardinality in check.

## 7. Measurement windows, SLOs, and error budgets

### 7.1. One-minute p99 and one-day p99 answer different questions

- **Short windows** (1–5 minutes): catch spikes, but fluctuate heavily under low traffic.
- **Longer windows** (30 minutes–24 hours): reveal trends, yet can smooth out brief multi-minute bursts.
- **SLO window** (e.g., 30 days): evaluates quality against commitments, not a replacement for live incident dashboards.

A 24-hour p99 cannot be accurately reconstructed by averaging 24 hourly p99 values.

### 7.2. Good-request-ratio SLOs

Suppose a backend team defines:

> Over 30 days, at least 99.9% of `getDeviceEvents` read requests must succeed and complete within 150 ms at the application's Cassandra boundary.

With **100,000 requests** in the window, the error budget is:

~~~text
Total requests = 100,000
SLO good ratio = 99.9%
Error budget = 0.1% × 100,000 = 100 requests

Good request:
    succeeded AND duration <= 150 ms

Bad request:
    error, timeout, OR duration > 150 ms
~~~

This formulation prevents timed-out requests from vanishing from the statistics. If a latency timer only records successful requests, pair it with a **parallel error/timeout SLI** or use good/bad counters covering all requests.

An SLO **does not have to be stated solely in terms of p99**. A good-request ratio threshold is easier to interpret and directly yields an error budget, while p50/p95/p99 still guide diagnosis when the SLO degrades.

### 7.3. Avoid confusing server latency with user goals

If the SLO is 300 ms at the HTTP edge while Cassandra server-local p99 is 30 ms, you can still breach the SLO due to driver retries, queues, network, serialization, or other backends. Keep **user-experience SLOs** and **Cassandra-access SLOs** distinct in name, scope, and owner.

## 8. From logs and metrics to a Cassandra dashboard

### 8.1. What to observe together

| Measurement group | Examples | Why it is needed |
|---|---|---|
| **Read latency** | p50/p95/p99 by keyspace/table/query and DC | Detect read tail and hot partitions |
| **Write latency** | p50/p95/p99 by CL and write kind | Spot slow replicas, commit logs, mutation pressure |
| **Throughput** | Reads/s, writes/s, concurrency | Separate traffic growth from efficiency drops |
| **Errors** | Unavailable, timeout, overload, retry attempts | Keep failed requests visible in reporting |
| **Resources** | CPU, GC pauses, disk read/write latency, queues | Pinpoint bottlenecks driving tail latency |
| **SSTable/compaction** | SSTables per read, pending compactions, tombstone scans | Explain read amplification |
| **Replica/topology** | Node UP/DOWN, DC, rack, hints/repair/streaming | Explain waits on slow replicas |
| **Driver/client** | In-flight, connection pool, request duration, retries, speculative executions | Separate client delay from server-local delay |

Never monitor all tables using **one cluster-wide p99 number**. A critical API representing 5% of traffic can become painfully slow while the global chart barely moves. Group by **stable operation**, keyspace/table, datacenter, and request type.

### 8.2. Choosing metric labels with safe cardinality

Reasonable labels:

- `operation=read_latest_events` or `write_measurement`.
- `keyspace=telemetry`, `table=events_by_device_day`.
- `dc=dc1`, `consistency=LOCAL_QUORUM`.
- `outcome=success|timeout|error`.

Never put `partition_key`, `device_id`, `user_id`, raw CQL with bound values, arbitrary exception messages, or request IDs into metric labels: unbounded cardinality consumes memory and storage and can overload your monitoring stack. For granular investigation, use **sampled** logs/traces while protecting sensitive data and PII.

## 9. Direct diagnostic tools in Cassandra

Field/metric names and output formatting vary by Cassandra version, so inspect actual output from your cluster rather than treating examples as fixed formatting.

### 9.1. Nodetool

~~~bash
# Table statistics: read/write latency, SSTables,
# partitions, and version-supported metrics.
nodetool tablestats telemetry.events_by_device_day

# Per-table histograms: read/write latency, SSTables per read,
# partition size, cell counts, etc., depending on version.
nodetool tablehistograms telemetry events_by_device_day

# Latency histograms at the coordinator/proxy layer.
nodetool proxyhistograms

# Compaction tasks and backlog.
nodetool compactionstats

# Thread pools, queues, and dropped messages (version-dependent).
nodetool tpstats

# Topology and node state across DCs.
nodetool status
~~~

`tablehistograms` is especially helpful when **one specific table** exhibits poor read latency distributions or many SSTables per read. `proxyhistograms` captures the request path near the coordinator, whereas table-local metrics differ in scope. Never sum those numbers directly.

You can also scrape metrics via a JMX/Prometheus exporter; **metric names and units** (microseconds, milliseconds, nanoseconds, seconds) must be verified in your exact stack. A 1,000× unit mismatch can trigger false alarms or mask real incidents.

### 9.2. Selective CQL tracing

Assuming the keyspace/table already exists and the application normally queries with the full partition key:

~~~cql
TRACING ON;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

Tracing reveals coordinator/replica execution steps such as which replicas were contacted, read stages, and elapsed times. However, tracing adds overhead; **never leave it continuously enabled across production traffic** to compute percentiles. Percentiles belong in continuous histograms over large request counts, while tracing serves **targeted investigation of representative requests**.

### 9.3. Snapshots vs. timelines

Running `nodetool tablehistograms` at time T is only a snapshot of the tool's internal window/state. To see when a p99 spike started, you need time-series export and sufficient retention.

On dashboards, always place p99 charts alongside traffic rate, timeouts, dropped messages, disk latency, compaction, and GC on the same timeline.

## 10. CQL example: same API, two query shapes with very different latency

Suppose an API fetches recent events by device and day. Schema design:

~~~cql
-- Assumes keyspace telemetry already exists.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Query specifying the full partition key:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

By contrast, filtering by metric value without a partition key:

~~~cql
-- Illustrates a broad-scan query; avoid as a default API pattern.
SELECT device_id, event_day, event_time, metric_value
FROM telemetry.events_by_device_day
WHERE metric_value > 80
ALLOW FILTERING;
~~~

`ALLOW FILTERING` does not turn a scan into a partition-key lookup. If an API truly needs to query by metric value, design a dedicated table for that access pattern or evaluate indexing/search options against your version and real data.

Even so, **a query with the exact partition key can still suffer bad p99** if partitions grow huge, span many SSTables, accumulate tombstones, or hit hot keys. When an API slows down, inspect **both query shape and storage amplification**, rather than merely adjusting `LIMIT`.

## 11. Java Driver 4.x example: timing request duration in the right place

To measure latency in a Java application, use monotonic `System.nanoTime()` and record into a metrics/histogram system capable of computing percentiles. This example uses **Micrometer** (add the appropriate Micrometer dependency to your project) with an application-managed `CqlSession`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class EventReadRepository {
    private final CqlSession session;
    private final PreparedStatement select;
    private final Timer successTimer;
    private final Timer failureTimer;

    public EventReadRepository(CqlSession session, MeterRegistry registry) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_time, metric_value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 50"
        );
        this.successTimer = Timer.builder("app.cassandra.read.duration")
            .tag("query", "events_by_device_day")
            .tag("cl", "LOCAL_QUORUM")
            .tag("outcome", "success")
            .publishPercentileHistogram()
            .register(registry);
        this.failureTimer = Timer.builder("app.cassandra.read.duration")
            .tag("query", "events_by_device_day")
            .tag("cl", "LOCAL_QUORUM")
            .tag("outcome", "error")
            .publishPercentileHistogram()
            .register(registry);
    }

    public List<Row> read(UUID deviceId, LocalDate day) {
        BoundStatement statement = select.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        long started = System.nanoTime();
        Timer timer = successTimer;
        try {
            return session.execute(statement).all();
        } catch (RuntimeException ex) {
            timer = failureTimer;
            throw ex;
        } finally {
            timer.record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

This instruments a **synchronous read** path. The timer spans from before `execute` until up to 50 rows are materialised, capturing driver, network, coordinator, and server handling. It does **not** measure total HTTP API duration if extra processing sits outside this method.

Operational notes:

- Enable `publishPercentileHistogram()` to produce aggregatable bucket data compatible with supported observability backends; tune buckets/SLOs to your needs.
- Separate `outcome=success` and `outcome=error` so failed requests do not vanish; overall SLOs still account for both.
- When distinguishing `timeout`, `unavailable`, and `overload`, map exceptions to a **small, fixed tag set**.
- **Never attach `deviceId`, `event_time`, or bound CQL values to metric tags.**
- For paged queries, decide explicitly whether you are timing **each page/driver request** or **the full multi-page API operation**; the two metrics are not equivalent.
- For async calls, never wrap `executeAsync(...)` in a `finally` block and treat that as query latency; stop the timer only when the completion stage finishes.

### Monitoring writes

For `INSERT`/`UPDATE`, use a similar Timer with `operation=write_measurement` and `cl=LOCAL_QUORUM`, keeping **regular writes** separate from **LWTs**. That reveals write p99 regressions without polluting read measurements.

During benchmarks, avoid logging every request to stdout: heavy logging itself inflates tail latency. Use metrics infrastructure sized for production throughput and monitor recording overhead.

## 12. Production investigation workflow when p99 spikes

Suppose a telemetry service reports **read p99 jumping from 70 ms to 900 ms** while the average barely moves. Resist changing compaction strategy or bumping timeouts immediately. Investigate systematically.

### Step 1 — Verify the signal and scope

Record start time, measurement interval, request count, p50/p95/p99, retries/timeouts, and timer definition. Break down by API, query signature, keyspace/table, DC, and CL. Confirm whether the spike is **client-side** or **storage-local**.

### Step 2 — Compare against load and external shifts

Check QPS/concurrency, traffic surges, Java app deploys, network/WAN changes, node UP/DOWN state, GC, disk latency, streaming/repair, and pending compactions. If every API's p99 jumped together, examine shared infrastructure first.

### Step 3 — Inspect query shape

Verify the query supplies the full partition key, clustering ranges are bounded, and no `ALLOW FILTERING` or new query shipped recently. If only a subset of partitions is slow, check for hot/wide partitions and traffic skew.

### Step 4 — Check read amplification

Cross-check `nodetool tablehistograms`, SSTables per read, tombstone warnings/scans, and compaction backlog. When TTLs or `DELETE`s leave dense tombstone ranges, even `LIMIT 20` can scan large volumes of data.

### Step 5 — Separate coordinator, replica, and driver

If table-local latency is low while client p99 is high, check network, coordinator queues, retries, speculative requests, contact points, connection pooling, and read CL. If one specific node shows slow disk/GC, diagnose that slow replica rather than blindly scaling the entire cluster.

### Step 6 — Test small changes, measure before and after

You might bound clustering ranges, refine the query/data model, throttle bulk import backpressure, drain compaction backlogs, or isolate streaming jobs. Only adjust timeouts, speculative retries, or CL once you understand the impact on correctness, availability, and overload.

### Step 7 — Verify you did not trade errors for a nicer p99

Compare p99 and error/timeout rates over the same interval; recompute the SLO good-request ratio. If p99 fell only because timeouts jumped, the problem is not solved. Keep measurement definitions constant and validate across sufficient sample volume.

## 13. Common mistakes in latency observability

| Misconception | Why it is wrong | Right practice |
|---|---|---|
| “Average under 100 ms means users are fine” | A very slow tail can sit in just 1–2% | Track p95/p99 and SLOs |
| “Averaging per-node p99s gives cluster p99” | Quantiles are not additive | Merge histogram buckets properly |
| “p99 improved after the incident” | Slow requests may be timing out and leaving the sample | Track errors/timeouts alongside latency |
| “Node local latency is small, so Cassandra can't be slow” | Coordinator, other replicas, network, queues, and retries sit outside it | Measure across multiple layers |
| “Every SELECT should share the same p99” | Query shapes, partition sizes, and tables differ | Segment by operation/table/CL |
| “If p99 rises, just add caching” | Cause may be tombstones, SSTables, WAN, compaction, or hot keys | Diagnose root cause before tuning |
| “Trace every request to compute p99” | Tracing adds overhead and cannot replace histograms | Trace selectively, measure continuously with metrics |
| “Switch from QUORUM to ONE to lower p99” | Changes consistency/correctness and read guarantees | Change only if business semantics allow |
| “One metric label per `device_id` helps debugging” | Cardinality explodes with device count | Use bounded tags; use sampled logs/traces |
| “p99 over 10 requests is reliable” | High percentiles need ample samples | Check sample counts and wider windows |

## 14. Self-check exercises

**Question 1.** A table has average read latency 100 ms, p50 50 ms, and p99 2,550 ms. Can you conclude the system is healthy because the average is only 100 ms?

**Answer:** No. A p99 of 2,550 ms means roughly 1% of the tail sits in multi-second territory, likely breaching experience targets; inspect QPS, timeouts, and affected queries.

**Question 2.** Node A has p99=20 ms across 10,000 requests; Node B has p99=2,000 ms across 100 requests. Is cluster-wide p99 equal to 1,010 ms?

**Answer:** No. Averaging per-node p99s is invalid; merge the distributions/histograms before computing the quantile.

**Question 3.** A `SELECT` returns 20 rows yet scans 5,000 tombstones. Why is read p99 high despite `LIMIT 20`?

**Answer:** Cassandra must skip over many deleted/expired entries before collecting enough live rows, causing read amplification on replicas.

**Question 4.** Server-local write latency p99=15 ms, while Java request p99=600 ms. Name at least three layers to inspect.

**Answer:** Driver queues/retries, coordinator queues, WAN/network, another slow replica, GC, pre-success timeouts, or client serialization/logic. Never subtract the two p99s to get network p99.

**Question 5.** After a system change, read p99 drops from 900 ms to 100 ms, while timeout rate rises from 0.1% to 5%. Is this a clear improvement?

**Answer:** No. If percentiles count only successful requests, slow requests simply timed out and vanished from the histogram. The SLO good-request ratio may be much worse.

**Question 6.** In a window with 100,000 requests, the SLO requires 99.9% succeeding under 150 ms. At most how many requests may violate this to still meet the SLO?

**Answer:** At most 100 requests (0.1%); count errors, timeouts, and requests exceeding the latency threshold as violations.

**Question 7.** Why should you avoid putting partition keys into histogram labels?

**Answer:** Partition counts can be enormous; unbounded cardinality makes telemetry expensive and can overload monitoring. Use low-cardinality labels and rely on sampled logs/traces for specific partitions.

## 15. Summary

In Apache Cassandra, **read/write latency is a distribution**, never a single average figure. Tail latency can originate from specific partitions, specific replicas, the network, coordinators, the Java Driver, or background tasks like compaction and repair.

Effective observability means:

1. **Measure p50/p95/p99** and throughput separately for reads and writes; track p99.9 too when sample counts suffice.
2. **Separate measurement layers**: end-to-end app, driver/coordinator, and replica table-local.
3. **Never average percentiles** across nodes; merge histograms or use aggregatable distributions.
4. **Include timeouts and errors**; a p99 over successful requests alone hides true service quality.
5. **Tie percentiles to Cassandra causes**: partition keys, query shapes, CL, SSTables/tombstones, replicas, I/O, and WAN.
6. **Use SLOs and well-sampled windows** to distinguish transient blips from user-impacting degradation.

When the average looks fine while p99 climbs, the right question is not “why hasn't the average crossed the threshold yet?”, but **“which path is the slowest cohort taking, where is it stalling, and what share of users are affected?”**. Answering those three questions lets you optimize Cassandra with evidence rather than guesswork.
