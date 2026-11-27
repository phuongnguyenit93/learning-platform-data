# Validating the Model with CQL, Representative Data, and Read/Write Metrics

## Lesson Objectives

An Apache Cassandra schema that looks sound on paper is not yet proven production-ready. The CQL may be valid yet queries still lag on the **largest partition**; a time bucket may shrink rows/partition yet multiply the partitions read; a projection table may cut fan-out yet add mutations, tombstones, and drift risks on write failures.

Within the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson builds an **empirical validation workflow**: write query contracts, author CQL for candidates, prepare representative datasets, run controlled read/write workloads, measure throughput and p95/p99, and conclude against pre-agreed acceptance criteria. Related topics include partition keys, clustering, replication, consistency levels, compaction, repair, TTLs, failure handling, and the Java Driver.

After this lesson, you will be able to:

1. Build a **validation matrix** linking each business query to its partition key, CQL statement, sort order, and resource limits.
2. Separate validation of **data correctness**, **access path validity**, **performance at target load**, and **fault tolerance**.
3. Design test datasets featuring skew, hot devices, identical timestamps, late-arriving data, large payloads, TTLs, and tombstones.
4. Compare two Cassandra schemas using reproducible measurements rather than a single `SELECT` timing on a few sample rows.
5. Use CQL and Java Driver 4.x to illustrate write/read paths, paging, and latency instrumentation.
6. Read operational metrics to spot hot partitions, compaction backlogs, replica lag, and model limits.
7. Write a **PASS/FAIL/NEEDS_MORE_EVIDENCE** report backed by clear thresholds and evidence.

## 1. Define Exactly What Must Be Proven

Example of a multi-tenant IoT system recording device events:

```text
tenant_id, device_id, site_id, event_id,
event_time, received_at, event_type, severity, payload
```

APIs under evaluation:

| Code | Query or Operation | Available Inputs | Expected Result |
| --- | --- | --- | --- |
| Q01 | View 50 newest events for a device in one UTC hour | Tenant, device, hour | Newest first, max 50 |
| Q02 | View events in `[09:15, 09:45)` UTC | Tenant, device, range and hour | Exact slice, paginated |
| Q03 | View device events in a 6-hour sliding window | Tenant, device, from/to | Sorted across whole range, bounded fan-out |
| Q04 | View `CRITICAL` alerts across a site on one day | Tenant, site, day | Newest list without probing every device |
| Q05 | Look up one event by event ID alone | Tenant, event ID | One event if still retained |
| W01 | Continuous telemetry ingestion | Data received from gateways | Write exact keys with retries and load limits |
| W02 | Write late-arriving or replayed events | Stable event ID and event time | No data loss or duplication outside contract |

Q01–Q03 point toward partitioning by **tenant + device + time bucket**. Q04 and Q05 are **different read paths**: they are not automatically served by the device/hour table. You may need a site projection or event-ID lookup table; never contort a single table to answer every filter.

### 1.1. Set Validation Criteria Before Benchmarking

Suppose the project team **assumes** the following thresholds to design tests; these are **not default Cassandra SLOs**:

| Validation Check | Illustrative Threshold | Evidence |
| --- | --- | --- |
| Q01 on a normal partition | p95 under 40 ms | End-to-end request latency at target load |
| Q01 on the hottest device | p99 under 150 ms | Latency distribution isolated to hot keys |
| Q03 6-hour window | Reads at most 7 hourly buckets; p95 under 250 ms | Query count/fan-out and request latency |
| W01 | Sustained writes at target load with errors within SLO | Completed throughput, timeouts, CPU/I/O, backlog |
| W02 | Replaying the same event creates no new row key | Exact primary key verification |
| Expired data | Never returns TTL-expired values; disk stays within ops forecast | Result verification, tombstones, compaction |
| One node temporarily down | Predictable read/write behavior per CL/RF | Chaos test and recovery metrics |

Thresholds must be signed off by product/operations owners for real hardware, topology, and traffic. If SLOs do not yet exist, state assumptions explicitly rather than calling a schema "fast."

### 1.2. Four Layers of Evidence

1. **Valid CQL:** tables create cleanly; `SELECT` binds full primary keys; driver maps types properly.
2. **Accurate results:** exact row set, exact order, half-open ranges, duplicate-timestamp handling, and UTC midnight boundaries.
3. **Bounded access cost:** partition count, row/partition sizes, rows/tombstones scanned, and fan-out stay controlled.
4. **Operations meet SLO:** throughput, p95/p99, CPU, disk, compaction, network, retries, repair, and fault tolerance hold under representative data.

A schema passing only layers 1 or 2 **is not ready for production**.

## 2. Lock Environment Details So Measurements Are Comparable

Benchmarks only carry meaning when you know where numbers came from. Two runs with identical CQL yet differing node counts, RFs, or hot-device ratios are not a fair comparison.

| Information Group | What to Record |
| --- | --- |
| Cassandra | Version/distribution, schema, keyspace, compaction, compression, TTL, indexes |
| Topology | DC/node counts, CPU/RAM, disk type, network, placement, RF per DC |
| Client | Java Driver version, instance count, connection/pool config, consistency level, timeouts, retry policy |
| Workload | Reads/writes per second, device/site counts, hot-key distribution, payload sizes, batches/replays |
| Data | Data age, live row count, % TTL-expired records, UPDATE/DELETE rates |
| Measurement | Warm-up, steady-state duration, burst phase, iterations, sampling window |
| Targets | Agreed SLOs, peak traffic level, growth margin, node-failure scenarios |

**Never run saturation stress tests on a production cluster serving live users** without an approved operational plan. Use a staging cluster matching topology and hardware; if measuring in production, run strictly controlled, blast-radius-limited checks.

### 2.1. Recommended Experiment Sequence

```text
Query Contracts + SLOs
          |
          v
Design Schema A / Schema B
          |
          v
CQL correctness tests with a few easily verified rows
          |
          v
Load representative data + TTL/tombstones/hot partitions
          |
          v
Warm-up -> target load -> peak burst -> recovery
          |
          v
Collect latency, QPS, partition sizes, traces, and system metrics
          |
          v
Controlled comparison -> PASS / FAIL / iterate
```

Avoid choosing a schema from a single query that ran fast on a warm cache when the table held only a few dozen rows and zero tombstones.

## 3. Two Candidate Schemas for the Same Workload

We compare **daily buckets** against **hourly buckets**. Both group by tenant/device and share time/ID clustering; the difference lies in partition size and how many partitions must be read for longer windows.

### 3.1. Candidate A — By Device / UTC Day

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Intra-day query:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Candidate A fits day-level APIs if partitions stay neither too large nor too hot. However, Q01 asks for **one hour**, so add clustering-time bounds to read only the target hour rather than applying `LIMIT` across the whole day:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 50;
```

**Note:** `day_bucket` is always the **UTC date of `event_time`**. If an hour window crosses 00:00 UTC, split the range into per-day segments.

### 3.2. Candidate B — By Device / UTC Hour

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Candidate B Q01:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;
```

Candidate B Q02:

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

Assume `hour_bucket` is the **UTC start-of-hour** instant from `event_time`, e.g., `2026-11-21T09:00:00Z`. Q01 reads one exact hourly partition; Q03 over six sliding hours can touch **up to seven hourly partitions** at misaligned boundaries.

### 3.3. What to Compare Between A and B

| Aspect | A — Daily | B — Hourly |
| --- | --- | --- |
| One UTC calendar day | One partition/device | 24 partitions/device |
| One hour for one device | One daily partition + range | One hourly partition |
| 7-calendar-day history | Up to 7 daily partitions | Up to 168 hourly partitions |
| Hot device partition | Can grow massive | Smaller as load splits across hours |
| Multi-bucket paging | Fewer streams | More streams for long ranges |
| Concentrated write load | Daily partition's replica set | Replica set shifts each hour |
| Ability to answer site-wide Q04 | Not direct | Not direct |

**Measure both sides:** shrinking partition size via hourly buckets can trade off higher fan-out and routing overhead. Saying "hourly buckets are always better" or "daily buckets are always better" lacks evidence.

## 4. Verifying CQL with a Small Known-Answer Dataset

Before stress testing, seed a short event set to verify exact boundaries and ordering. The data below is strictly a **functional test seed**, not a representative performance dataset.

### 4.1. Mandatory Test Cases

| Event | `event_time` UTC | `received_at` UTC | Purpose |
| --- | --- | --- | --- |
| E01 | Nov 21 09:10:00.000 | Nov 21 09:10:01 | Normal row inside hour 09 |
| E02 | Nov 21 09:10:00.000 | Nov 21 09:10:02 | Same timestamp as E01, different event ID |
| E03 | Nov 21 09:59:59.999 | Nov 21 10:00:01 | Immediately before hour boundary |
| E04 | Nov 21 10:00:00.000 | Nov 21 10:00:02 | Exact start of next hour |
| E05 | Nov 20 23:58:00.000 | Nov 21 10:10:00 | Late-arriving event from prior day |
| E06 | Nov 21 09:20:00.000 | Nov 21 09:20:01 | Range and TTL verification |

`event_id` must stay stable on replays; identical timestamps are separated by the second clustering column. A random UUID does **not** prove causal order on equal timestamps; it only provides a deterministic key tie-breaker.

### 4.2. Seed CQL for Candidate B

The snippet below uses a valid device UUID and four distinct event IDs. UTC values are **CQL literals for testing**, without `?`.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:10:00.000Z',
    00000000-0000-4000-8000-000000000011,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T09:10:01Z', 'MEASURE', 'INFO', 'E01'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:10:00.000Z',
    00000000-0000-4000-8000-000000000012,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T09:10:02Z', 'MEASURE', 'WARN', 'E02'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:59:59.999Z',
    00000000-0000-4000-8000-000000000013,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T10:00:01Z', 'MEASURE', 'INFO', 'E03'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T10:00:00Z',
    '2026-11-21T10:00:00.000Z',
    00000000-0000-4000-8000-000000000014,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T10:00:02Z', 'MEASURE', 'INFO', 'E04'
);
```

Run a full-key query:

```sql
SELECT event_time, event_id, payload
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001
  AND hour_bucket = '2026-11-21T09:00:00Z'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z';
```

**Expected:** returns E03, E02, and E01; omits E04. E03 comes first because its timestamp is newest. E02 and E01 share the same timestamp and sort by `event_id DESC`. With the literal event IDs above, E02 precedes E01. Querying the 10:00 bucket must return E04 and omit E03.

To verify late E05, seed the event with `event_time = 2026-11-20T23:58Z` and `hour_bucket = 2026-11-20T23:00Z`, even though `received_at` is Nov 21. Similarly seed Candidate A's daily table with `day_bucket = 2026-11-20`; never place E05 into the receipt-day bucket.

### 4.3. Testing Same-Key Replay

Resend E01 with the **exact same** tenant, device, hour bucket, event time, and event ID. Expect **one logical row** for that primary key in the partition; repeating `INSERT` performs an **upsert** rather than creating another row under a different key.

Next, test an intentional bug: regenerate `event_id` on every retry. You should observe two rows for the same business event. Also test the same event ID with a different `event_time` or bucket: since the full primary key differs, Cassandra does not enforce tenant-wide uniqueness on `event_id`.

If the domain requires uniqueness by event ID alone, enforce dedicated ID-generation/deduplication rules or a separate lookup table; never infer it from the timeline table's primary key.

### 4.4. Queries That Must Be Flagged as Invalid Read Paths

For example, the following intent fails to provide the full partition key of the device/hour table:

```sql
-- NOT a key-aligned query path for device_events_by_hour:
SELECT event_time, event_id
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A' AND severity = 'CRITICAL';
```

This is not merely missing `LIMIT 50` or a tuned Java call. To answer site-wide Q04, validate an `alerts_by_site_day` table or an index/search path suited to your selectivity and SLOs. Never treat `ALLOW FILTERING` as a fix: even when permitted, scanning cost at scale can be unpredictable.

**CQL has no universal `EXPLAIN` equivalent across SQL engines.** Inspect schemas, verify predicates, and use tracing and server metrics on a controlled workload instead of assuming short syntax means fast execution.

## 5. Representative Data Must Reflect Real Workload Skew

Seed a few rows to verify correctness; benchmarks must mirror realistic **data distributions**. A uniform dataset hides hot partitions, large payloads, and post-outage event bursts.

### 5.1. Designing Three Device Cohorts

Example hypothetical workload of **1,000 devices**:

| Cohort | Devices | Average Rate per Device | Total Events/Second |
| --- | ---: | ---: | ---: |
| Normal | 900 | 0.02/s | 18 |
| Active | 90 | 0.5/s | 45 |
| Hot | 10 | 25/s | 250 |
| **Hypothetical Total** | **1,000** | — | **313** |

This is an illustrative dataset to show the effect of **skew**, not a default IoT distribution. Sending a uniform 0.313 events/s across all 1,000 devices produces roughly the same 313/s total yet **fails to reproduce the same hotspots**.

### 5.2. Size the Largest Partition Before Running

With one hot device emitting **25 events/second** and raw business payload **600 B/event**:

```text
In 1 hour:
    25 × 3,600 = 90,000 events
    90,000 × 600 B = 54,000,000 B = 54 MB raw

In 1 day:
    25 × 86,400 = 2,160,000 events
    2,160,000 × 600 B = 1,296,000,000 B ≈ 1.30 GB raw
```

Comparing A and B:

- A hot device's daily partition can hold roughly **2.16 million rows** if that rate sustains all day.
- An hourly partition holds roughly **90,000 rows** at the same rate.
- Actual SSTable bytes differ from raw bytes due to primary keys, metadata, compression, TTLs, tombstones, indexes, compaction, and replicas.

There is no universal rule that "a 54 MB partition is always safe" or "1.3 GB always fails" across every cluster. Measure **the largest partition and write rate**, not just cluster totals or averages.

### 5.3. Mandatory Dataset Variations

| Scenario | How to Generate | What to Verify |
| --- | --- | --- |
| Large and small tenants | Skew device counts across tenants | Tenant scope preserved; do not test only tiny tenants |
| Ultra-hot devices | 1% of devices emit most events | Hot partitions, p99, replica CPU/I/O |
| Multi-sized payloads | Mostly small, some very large | p99 row size, network, heap, disk |
| Duplicate timestamps | Multiple events in same millisecond | Clustering tie-break and zero dropped rows |
| Hour/day boundary crossings | 09:59:59.999 → 10:00 and 23:59 → 00:00 | Accurate UTC bucketing; no double/missed boundary items |
| Late-arriving events | Old `event_time`, recent `received_at` | Buckets and TTLs derive from the right timestamp |
| Replays | Rewrite same ID, then test wrong ID | Idempotency across full primary key |
| TTL expirations | Load aged data and let rows expire | Tombstones, latency, and disappearance timing |
| UPDATE/DELETE | Delete/update a defined percentage of rows | Tombstones scanned, compaction, replays |
| Node loss / timeout | Isolate a node in authorized fault tests | Behavior matches RF/CL, error rates, and recovery |

Never load 100 million **brand-new** rows and benchmark once. Production tables hold data spanning multiple TTL, update/delete, and compaction cycles; test an **aged dataset** at steady state. When simulating age via backfill, account for real write timestamps and TTLs so the simulation does not distort semantics.

### 5.4. Know the Provenance of Test Data

Prefer non-sensitive synthetic data that accurately mirrors **key lengths, null ratios, payload sizes, timestamp distributions, and tenant/device skew**. If using real data, follow security policies, anonymize/strip identifiers, and restrict access; performance testing must never leak user data.

## 6. Reproducible Benchmarks: Beyond a Single `cqlsh` SELECT

A benchmark run should have **multiple phases** keeping conditions identical between A and B. For example:

| Phase | How to Run | What to Record |
| --- | --- | --- |
| Setup | Create schema, load data per agreed distribution | Rows, bytes, partition counts, load duration |
| Warm-up | Drive target-like traffic for a set window | Cache/connection stabilization; avoid mixing cold-start with steady state |
| Isolated reads | Q01, Q02 on normal and hot keys | Correctness, p50/p95/p99, bytes, and tombstones |
| Mixed workload | Production-like read/write ratio | Completed throughput, timeouts, p95/p99, and resource usage |
| Burst | Ramp ingest and reads to agreed peak | Queues, backpressure, errors, and recovery |
| Aged-data test | TTLs, DELETE/UPDATE, compaction across windows | Tombstones, SSTables per read, disk, and latency |
| Fault injection | Slow or unreachable node in staging | Availability per CL/RF, timeouts, and repair |
| Cooldown/reconcile | Lower load, reconcile, re-measure | Does state converge cleanly and do resources recover? |

Warm-up minutes, run counts, and phase durations are **experimental parameters** to record; no single duration fits every cluster. Run multiple comparable iterations to isolate noise, skew, and compaction variance.

### 6.1. How to Measure Latency Properly

For each query shape, record:

- **Actually completed throughput** (requests/s), not merely requests submitted.
- `p50`, `p95`, `p99`, and error/timeout rates—never averages alone.
- Client-side end-to-end request latency and, where possible, server-side latency separately.
- Retry rates, speculative/retried requests, partitions/buckets/shards touched, and page fetches.
- Rows **returned** versus rows/tombstones **scanned**.
- Normal keys vs. hot keys separately; cluster-wide p99 can mask hot-key p99.

Client latency can include serialization, network, coordinator, replicas, retries, and paging. If an API returns **only the first page**, never label that measurement "time to load full history."

### 6.2. Bound Load So You Do Not Benchmark an Unrealistic Overload

An unbounded generator spawning endless threads measures **overload collapse**, not SLOs at target traffic. Specify explicitly:

```text
target_ingest_events_per_second
target_Q01_requests_per_second
target_Q02_requests_per_second
target_Q03_requests_per_second
client_concurrency_limit
max_queued_requests
payload_size_distribution
hot_key_distribution
page_size
consistency_level
test_duration
```

Enforce **backpressure** and count rejected/timed-out requests. Uncontrolled concurrency artificially inflates latency, timeouts, and coordinator pressure; schema comparisons must hold input load and retry policies identical.

### 6.3. Verifying Pagination

In Cassandra:

| Concept | What to Check |
| --- | --- |
| `LIMIT 50` | Maximum total rows for the CQL statement |
| Driver `page size = 50` | Target rows per page fetch; supports continuing |
| API `limit = 50` | Rows returned to caller; must be enforced independently |
| Cursor/paging state | Bound to query shape, bind values, tenant, and scope |
| Multiple buckets | Must track per-partition cursors and merge results |

A six-hour sliding query can span **seven hourly buckets**. If each bucket returns a 50-row page and the app collects and sorts all of them, intermediate rows can hit 350 before returning 50 results; control fetch cost and continue/stop logic per your merge design. Never reuse one partition's cursor for a multi-bucket aggregated query.

When data keeps arriving or TTLs expire, multi-page pagination **does not automatically create an immutable snapshot**. APIs must specify semantics: whether shifting lists are acceptable or whether watermarks/fixed-window conditions are required.

## 7. Reading Cassandra Metrics and Targeted Tracing

Beyond client latency, inspect Cassandra itself to understand why a query is fast or slow. Exact command/metric names vary by version and tooling; always record version and scope when running them.

### 7.1. Metrics to Collect

| Group | Reference Tool / Metric | Question Answered |
| --- | --- | --- |
| Data distribution | `nodetool status`, per-node metrics | Which node holds more data or load? |
| Table storage | `nodetool tablestats` | Live space, total space, estimated partition counts |
| Table histograms | `nodetool tablehistograms` | How are partition sizes and latencies distributed? |
| CPU, heap, GC | OS / JVM metrics | Is slowness from CPU/GC rather than CQL alone? |
| Read/write latency | Cassandra and client metrics | How do server and client latencies compare? |
| Tombstones scanned | Supported metrics/tracing | How many deletion markers is the query traversing? |
| SSTables per read | Table histograms/metrics | Does a read touch too many SSTables? |
| Compaction | `nodetool compactionstats`, pending tasks | Is compaction falling behind as TTLs/deletes rise? |
| Thread pools | `nodetool tpstats` and pool metrics | Are queues backing up or dropping tasks under load? |
| Network/streaming | Network, repair/streaming metrics | Are slow nodes or data movement impacting latency? |

`nodetool` exposes the server view, though some metrics aggregate per node/table or sample over windows. Synchronize clocks across clients/cluster and log **test timestamps** to correlate latency spikes with CPU, compaction, and tombstones.

### 7.2. Selective Tracing in `cqlsh`

In a controlled test environment, enable tracing to inspect execution steps for a single query:

```sql
TRACING ON;

SELECT event_time, event_id
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001
  AND hour_bucket = '2026-11-21T09:00:00Z'
LIMIT 10;

TRACING OFF;
```

`TRACING ON/OFF` are **`cqlsh` commands**, not part of a `SELECT` sent via the Java Driver. Tracing adds overhead; never enable it broadly or continuously across production traffic just to benchmark. Use targeted samples alongside server metrics to verify routing paths and execution behavior.

**Never equate "a single fast trace" with system p99.** Query duration depends on load, caches, compaction, network, and replica health.

### 7.3. Tracing Symptoms Back to Modeling Decisions

| Observation | Hypothesis to Test | Next Action |
| --- | --- | --- |
| p99 spikes only on 10 hot devices | Hot partition/replica, large payloads | Check per-key QPS, partition size; test smaller buckets/shards |
| Q03 slow even though Q01 is fast | Multi-bucket fan-out or merge/paging | Count partitions/pages fetched and intermediate bytes |
| Few rows returned yet high latency | Expired TTL tombstones or many SSTables | Check tombstones scanned, compaction, and data age |
| Disk grows even with steady retention | Old SSTables, compaction backlog, snapshots, overwrites | Break down disk components; test steady state |
| All queries slow during bursts | Node CPU/network, client concurrency, or GC | Throttle load; find bottleneck before changing schema |
| Q04 scans every device in a site | Wrong partition key for query shape | Add suitable projection/index/search and measure mutations |
| Queries return wrong day when gateway offline | Reader/writer use different timestamps | Align `event_time`, `received_at`, and UTC bucketing |
| Read/write timeouts rise after node fault | RF/CL and topology recovery behavior | Test fault behavior and repair; do not blame schema alone |

## 8. Java Driver 4.x: Measuring First Page and Validating Binds

The example below measures **time to first result page** for Q02. It uses Java Driver 4.x, reuses a service-scoped `CqlSession`, and calls `executeAsync`. Never mistake this duration for total time to fetch all pages.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

public final class DeviceQueryProbe {
    private final CqlSession session;
    private final PreparedStatement byHourRange;

    public DeviceQueryProbe(CqlSession session) {
        this.session = session;
        this.byHourRange = session.prepare(
            "SELECT event_time, event_id, event_type, severity " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public record FirstPageMeasurement(
        long latencyMicros, int rowsOnFirstPage, boolean morePages
    ) {}

    public CompletionStage<FirstPageMeasurement> probeOneHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        Instant bucket = fromInclusive.truncatedTo(ChronoUnit.HOURS);
        if (toExclusive.isAfter(bucket.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Split range into hour buckets");
        }

        BoundStatement bound = byHourRange.bind(
            tenantId, deviceId, bucket, fromInclusive, toExclusive
        ).setPageSize(50);

        long started = System.nanoTime();
        return session.executeAsync(bound).thenApply((AsyncResultSet page) -> {
            long latencyMicros =
                Duration.ofNanos(System.nanoTime() - started).toNanos() / 1_000L;
            int rows = 0;
            for (Row ignored : page.currentPage()) {
                rows++;
            }
            return new FirstPageMeasurement(
                latencyMicros, rows, page.hasMorePages()
            );
        });
    }
}
```

**Exact scope of this measurement:**

- `System.nanoTime()` measures client monotonic elapsed time, not wall-clock timestamps.
- `executeAsync` completes when **the current result page** arrives, not when all pages are read. `page.hasMorePages()` indicates whether additional pages exist.
- `page.currentPage()` iterates only rows **already in the current page**. This example never calls `fetchNextPage()`, so it does not measure full-range traversal time.
- `setPageSize(50)` is a target page size; Cassandra may return fewer rows due to data boundaries, payload size, or other limits.
- `fromInclusive` and `toExclusive` are validated so queries never silently read the wrong bucket; cross-hour ranges must be split and measured per branch/fan-out.
- Avoid running heavy work inside driver completion callbacks; record minimal telemetry and offload heavy aggregation under high load.

For Java 11 or versions without `record`, replace `record FirstPageMeasurement` with a standard data class. In real benchmarks, use a high-resolution latency histogram, collect enough samples for p99, and log timeout rates—never rely on averages from a handful of calls.

### 8.1. What Else Does a Java Write-Path Benchmark Need?

Write benchmarking is more than calling `session.execute` in a loop:

1. Generate event IDs, event times, and buckets matching the **exact skew distribution** in Section 5.
2. Maintain realistic normal/hot key ratios; inject retries with **identical primary keys** when simulating timeouts.
3. Bound concurrency/queues, allow warm-up, and measure **actual completions/s**.
4. Separate payload/serialization prep time from client request time when profiling components.
5. Track write timeouts and `NoNodeAvailable`/connection errors alongside driver and node metrics; never retry infinitely.
6. If maintaining two projections, measure the extra mutations, lag, and state after partial failures.

One `executeAsync` completing does not prove data sits on **all replicas** or secondary tables. Choose consistency levels per RF/topology/SLA and verify via readbacks and reconciliation.

## 9. Validating TTL, Tombstones, Compaction, and Repair

### 9.1. TTL Policies Must Be Proven with Late-Arriving Events

Suppose events are retained **7 days from `event_time`**. When a gateway goes offline for two days, never apply a flat 7-day TTL at receipt time if business age must match occurrence time.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

```text
expires_at = event_time + 7 days
remaining_seconds = expires_at - clock_now_at_write

remaining_seconds > 0:
    write with remaining TTL within valid bounds
remaining_seconds <= 0:
    do not write to this retention table; apply expired-data policy
```

An event arriving two days late retains roughly **five days of TTL**. During verification, compare expected expiration timestamps against actual reads within agreed clock/second tolerances. Never interpret `TTL 0` as "delete immediately"; guard non-positive TTLs in the application.

### 9.2. Reading Live Rows and Inspecting Remaining TTL

For a TTL-bearing column like `payload`, verify with:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 10;
```

`TTL(payload)` returns remaining seconds for **that specific cell** if it has a TTL and is live; `null` can mean either no TTL or an absent cell. Never infer every cell in the row shares the same TTL from a single column.

TTL attaches to written values and does not instantly delete SSTable files on expiration. During tests, observe tombstones, compaction backlogs, disk used, and read latency **before and after data expires**. Benchmarking only fresh rows without TTL underestimates real churn cost.

### 9.3. Choose Compaction Strategy by Workload, Not Table Name

For largely append-only telemetry with relatively uniform TTLs and rare edits to old rows, **TimeWindowCompactionStrategy (TWCS)** is worth benchmarking. However, TWCS windows follow storage write timestamps, **not** `hour_bucket` directly. Late rewrites, backfills, and mixed TTLs can hinder time-window SSTable expiration.

When comparing A vs. B, keep compaction strategy constant if your goal is comparing buckets. Run a **separate** experiment if comparing compaction strategies, because changing buckets, compaction, and payloads simultaneously obscures which factor drove results.

### 9.4. Replication and Consistency in Fault Tests

Suppose a DC has `RF=3`. You can evaluate reads/writes at `LOCAL_QUORUM` if targets and topology match. Ideally, local quorum at RF=3 requires at least two replicas acknowledging each operation; however, it neither gives multi-table transactions nor prevents concurrency bugs.

To validate:

- Write and read the same partition under the chosen CL while one replica is slow or down.
- Measure timeouts, latency, retry pressure, recovery, and post-fault readbacks.
- Inspect repair/streaming status after the node returns.
- If a site projection exists, explicitly test **missing secondary-table writes** on consumer failures: Cassandra repair will not backfill un-sent business mutations.

Never tune `gc_grace_seconds` down arbitrarily just to reduce benchmark tombstones. Deletion safety depends on missed-delete windows and repair procedures for your cluster version.

## 10. Validating Secondary Queries: Is a Projection Worth It?

Q04 queries CRITICAL alerts by site/day. If the primary schema keys by device/hour, answering Q04 requires knowing all device/hour keys upfront and filtering across many partitions. If Q04 is frequent with strict SLAs, test a projection table:

```sql
CREATE TABLE critical_events_by_site_day (
    tenant_id text,
    site_id uuid,
    day_bucket date,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    device_id uuid,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, site_id, day_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Assuming busy sites use 8 shards, `shard_id` derives from `event_id` via a versioned rule. Each CRITICAL event writes to both the device/hour table **and** the site/day table; Q04 reads up to 8 partitions and merges. For smaller sites, test an unsharded variant to avoid unnecessary fan-out.

### 10.1. Read-Path and Write-Path Tests Must Go Together

| Experiment | What Must Be Proven |
| --- | --- |
| Q04 without projection | How many partitions probed, p95/p99, and bytes read? |
| Q04 with 8-shard projection | p95/p99, bounded merge/paging, and per-shard hotspots? |
| Creating a CRITICAL event | Present in both base and projection with matching keys/TTL? |
| Base succeeds, projection fails | Durable retries and reconciliation recover missing rows? |
| Replayed event or older revision | Final state/copy remains accurate? |
| TTL expiration or deletes | Secondary copy never outlives policy or resurrects expired data? |
| Largest tenant / noisiest site | No overheated partitions; SLAs still hold? |

Compare **read-amplification** savings against extra mutations, replica storage, tombstones, and projection maintenance cost. Raising the consistency level on the site table will not recover an event the consumer never wrote there.

### 10.2. Never Validate Rare Queries with Production Full Scans

An analytical requirement like "count alerts across the whole tenant over two years, grouped by site and month" differs from Q04. It calls for an aggregation pipeline or OLAP store—never pull all device/hour events into a Java service just to `GROUP BY` in memory.

If queries need full-text search, arbitrary multi-filters, and flexible sorting, evaluate a suitable search/index engine rather than adding tables for every UI combination. Still measure freshness, backlogs, tenant ACLs, and reconciliation between source Cassandra and the auxiliary store.

## 11. Analyzing Results and Making the Model Decision

Suppose Candidates A and B are measured on **identical hardware, RF, payloads, hot-device ratios, traffic, and compaction policy**. The table below shows **illustrative hypothetical numbers**, not real Cassandra benchmark results:

| Metric at Target Load | A: Daily | B: Hourly | Interpretation |
| --- | ---: | ---: | --- |
| Q01 p95 | 52 ms | 28 ms | Hourly bucket is faster under assumptions |
| Q01 hot-key p99 | 260 ms | 115 ms | A breaches hypothetical 150 ms hot-key threshold |
| Q03 p95 | 82 ms | 170 ms | A is faster due to lower partition fan-out |
| W01 completed | 300 events/s | 300 events/s | Both meet illustrative throughput |
| Largest hot partition (raw) | ~1.3 GB/day | ~54 MB/hour | Not actual on-disk SSTable bytes |
| Max partitions for Q03 | 1 day, or 2 across UTC midnight | 7 hours | Fan-out depends on actual range |
| Tombstones scanned on aged data | Must measure | Must measure | Cannot infer from raw size alone |

**Do not conclude B wins unconditionally.** If Q01 and hot-key p99 dominate while Q03 stays under its hypothetical 250 ms cap, B fits better. If Q03 dominates at high load, A may work if hot partitions are controlled, or another approach may be needed. Decide **against pre-committed thresholds**, not just "whichever number looks smallest."

### 11.1. Write an Auditable Conclusion

```text
Candidate: device_events_by_hour
Workload: 1,000 devices, skew 90/9/1,
          313 new events/s, payload distribution = ...
Topology: Cassandra version ..., DC/node/RF = ...
CL: read ..., write ...
Compaction: ...
Duration: warm-up ..., steady ..., burst ...

Q01 hot p99: ... ms (target <= ... ms)
Q03 p95: ... ms (target <= ... ms)
W01 completed throughput: ... /s, timeout: ... %
Largest partition: ... rows / ... SSTable bytes
Tombstones scanned / SSTables per read: ...
Compaction backlog / disk headroom: ...

Decision: PASS / FAIL / NEEDS_MORE_EVIDENCE
Open questions: ...
Next action: ...
```

If test data lacked expired events or skipped node-failure tests when production faces both, record **NEEDS_MORE_EVIDENCE**—never mark an overall PASS.

### 11.2. When Must You Go Back to the Drawing Board?

- Primary CQL queries cannot supply the full partition key or force scanning too many partitions.
- The largest/hottest partition breaches latency or resource targets.
- Overly small buckets push multi-bucket fan-out/paging past read SLAs.
- Tombstone and compaction ratios degrade latency as data ages.
- Projections create unsustainable write amplification or lack error recovery.
- Event-time retention/TTL breaks on late arrivals or replays.
- SLOs hold only with zero node faults, while availability requires surviving planned failures.

When evidence is inconclusive, change **one variable at a time** (bucket, shard count, compaction, index, driver settings) and re-measure under identical inputs; never infer root cause from a test that changed multiple variables at once.

## 12. Checklist Before Choosing a Production Model

| Question | Required Validation State |
| --- | --- |
| Does every API have a clear query shape? | Inputs, sort, LIMIT, range, QPS, SLO, and caps documented |
| Is CQL valid with complete partition keys? | Tested CREATE/INSERT/SELECT on real schema |
| Were duplicate timestamps and UTC boundaries tested? | Verified results by event ID, hour, and day |
| Does test data include skew and hot devices? | Real or assumed per-key distributions recorded |
| Are p99 payloads, replays, and late arrivals tested? | Representative cases present with exact outputs |
| Are rows/bytes of the largest partition measured? | Formulas and SSTable measurements, not just JSON bytes |
| Were aged data, TTLs, and tombstones tested? | Measured across multiple write/delete/compaction cycles |
| Were p95/p99 and completed throughput measured? | Checked against pre-set thresholds across multiple runs |
| Are fan-out and paging bounded? | Caps on buckets/shards, bytes, concurrency, and cursors |
| Were hot replicas and nodes observed? | Per-node/table metrics, errors, CPU/I/O, and network |
| Were node faults and consistency levels tested? | Reads/writes/recovery validated under target RF/CL |
| Are projections validated? | Measured write cost, lag, retries, and reconciliation |
| Is operational headroom budgeted? | Disk, compaction, repair, snapshots/backfills accounted for |
| Is the benchmark reproducible? | Schema, seed data, config, workload, and results archived |

## 13. Practice Exercise

A Java service logs parcel status events. Columns:

```text
tenant_id, parcel_id, scan_id, scanned_at, received_at,
site_id, status, payload
```

Business requirements:

- **R1:** 50 most recent scans for a parcel within **one UTC hour**.
- **R2:** Parcel history in a **4-hour** sliding window, max 100 rows in the API.
- **R3:** Find `FAILED` scans for a site on a given day.
- **R4:** Retain scans **7 days from `scanned_at`**, with arrivals up to two days late.

Assumed test data:

- 1,000 active parcels.
- The 10 hottest parcels sustain **30 scans/second** for hours; each scan averages **700 B of raw data**.
- Most remaining parcels have low traffic.
- 5% of scans share identical timestamps with other scans on the same parcel.
- A percentage of scans replay; old records hit TTL and some `DELETE`s occur.

**Tasks:**

1. Write at least two candidate schemas: **daily** bucket and **hourly** bucket, with clustering `(scanned_at DESC, scan_id DESC)`.
2. Write the CQL `SELECT` for R1 on both schemas and explain full partition key/range predicates.
3. Calculate rows and raw size of **one hot parcel** for hourly vs. daily buckets if 30/s sustains continuously. Explain why raw bytes differ from SSTable disk bytes.
4. For a 4-hour sliding window, up to how many hourly buckets can be touched when endpoints miss hour boundaries? How must the app paginate and merge?
5. Design at least six correctness test cases (hour boundary, duplicate timestamp, retry, late event, TTL, delete).
6. Propose a projection table for R3, specifying shard selection criteria and how to handle base succeeding while projection fails.
7. Design two benchmark rounds comparing A vs. B under identical RF, CL, hardware, and workload, covering p95/p99, write throughput, tombstones, largest partition, and disk headroom.
8. State which conditions merit `PASS`, `FAIL`, and `NEEDS_MORE_EVIDENCE`, and why average latency alone is insufficient.

**Reference guidance:**

```text
Daily candidate:
    PRIMARY KEY ((tenant_id, parcel_id, day_bucket),
                 scanned_at, scan_id)

Hourly candidate:
    PRIMARY KEY ((tenant_id, parcel_id, hour_bucket),
                 scanned_at, scan_id)

One hot parcel at 30 scans/s:
    1 hour = 30 × 3,600 = 108,000 scans
    raw 1 hour = 108,000 × 700 B = 75.6 MB
    1 day = 30 × 86,400 = 2,592,000 scans
    raw 1 day = 2,592,000 × 700 B = 1,814.4 MB ≈ 1.81 GB

4-hour sliding window:
    Can intersect up to 5 hourly buckets across boundaries.

Retention:
    A scan arriving 2 days late has roughly 5 days of TTL left
    under a 7-day policy from scanned_at.
```

A candidate passes only when it **returns accurate results** and **satisfies read/write thresholds on representative data**, including skew, tombstones, retries, and required fault tolerance. Never pick buckets from raw capacity math alone; also measure hot partitions, fan-out, and compaction behavior.

## Conclusion

Validating a Cassandra model is a chain linking **query contracts → concrete CQL → representative data → controlled workloads → read/write metrics → evidence-based decisions**. Partition keys and clustering define the read path, yet a schema is only sound when results are accurate, the hottest partition meets SLAs, TTLs/tombstones do not degrade performance, and the system survives committed failure scenarios. Never substitute a handful of sample rows, a `LIMIT` clause, or average latency for real evidence. Keep reports reproducible, state acceptance thresholds, and document any unverified gaps before moving to production.
