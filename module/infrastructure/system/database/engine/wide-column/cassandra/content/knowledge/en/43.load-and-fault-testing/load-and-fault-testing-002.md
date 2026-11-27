# Representative Data for Size, Partitioning, TTL, and Update Ratio

> **Chapter:** Load and Distributed Fault Testing  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — learning distributed Apache Cassandra and the wide-column model, partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, error handling, and Java application connectivity.

Suppose a team benchmarks Cassandra by writing 1 million rows, each containing the string `"hello"`, with uniformly random partition keys and no TTLs or UPDATEs. The test reports a great p99. Meanwhile, the real system stores device events by day, 1% of devices generate nearly half the traffic, payloads range from tens of bytes to tens of KiB, part of the data expires after 7 days, and some rows are updated multiple times. When a replica fails, read latency and tombstone scans on aged data spike sharply. **The test dataset missed the exact characteristics that make the real system slow.**

This lesson guides you in designing a **representative dataset** for load testing and fault testing on Apache Cassandra. The goal is neither to copy user data nor to chase the highest QPS number at all costs. The goal is a repeatable, measurable, and explainable model covering:

- **Size:** byte distributions of rows, payloads, collections, partitions, and on-disk footprint after compression and replication.
- **Partitioning:** partition counts, rows per partition, hot/cold keys, token locality, and imbalance across replicas.
- **TTL/age:** proportions of live, near-expiry, and expired data; tombstones and compaction state over time.
- **Update ratio:** how many INSERTs create new rows, UPDATEs touch existing rows, DELETEs, LWTs, PK/range reads; along with temporal locality and bursts.
- **Load and faults:** testing on the **same data state** before, during, and after injecting node/network/disk faults—without arbitrarily changing the workload and attributing the result to the fault.

> **Scope:** Cassandra 4.x–5.x, CQL and Java Driver 4.x, `cassandra-stress` user mode for illustration; verify tool, compaction, and metric configurations against the actual server version. All numbers in "lab profile" tables are **hypothetical data for test design**, not collected production telemetry or universal SLA thresholds.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Build a **data/workload profile** from realistic distributions instead of merely specifying total row counts and QPS.
2. Estimate preliminary sizing across logical bytes, replication factor, compression, and storage amplification without confusing wire bytes with SSTable bytes.
3. Generate partition keys following uniform, skewed/hotset, and time-bucketed distributions, and ensure UPDATEs actually hit existing keys.
4. Generate payloads across multiple sizes, entropy levels, and nullable/collection fields suitable for measuring compression, codecs, GC, and network cost.
5. Construct TTL cohorts and tombstone pressure **with real age**, understanding why backdating `event_time` does not make a TTL expire automatically.
6. Orchestrate controlled INSERT/UPDATE/DELETE/READ ratios; distinguish single-column updates from whole-row upserts and LWTs.
7. Write a Java generator with reproducible seeds, prepared statements, backpressure/concurrency limits, rate control, and manifests.
8. Use `cassandra-stress user` or custom workload runners for their intended purpose while recognizing the limits of generic profiles.
9. Design prefill, warm-up, steady-state, fault, and recovery/soak phases and compare them against the same baseline.
10. Read `EstimatedPartitionSizeHistogram`, `TombstoneScannedHistogram`, SSTables/read, compaction, and p95/p99 metrics—and reject any run whose data violates the profile.

## 2. What Does "Representative" Mean?

### 2.1. Large Volume Does Not Equal a Realistic Workload

| Dataset | What It Tests | What It Easily Misses |
|---|---|---|
| 10 million uniform keys, 1 row per key | Hashing/network throughput on "skinny" data | Wide partitions, hot keys, clustering ranges |
| 1 key containing 10 million rows | Extreme wide-partition behavior | Token/replica balance, normal multi-partition distribution |
| 1 KiB payload repeating the letter `A` | A single **highly compressible** case | Disk/network ratio with high-entropy JSON/blobs |
| Every INSERT has a 60 s TTL | Short-TTL path | Mixed long/no-TTL data and real SSTable lifecycle |
| New INSERTs only, no UPDATE/DELETE | Write ingestion throughput | Write amplification, tombstones, list read-before-write |
| 99% reads on a single key | Hot-key behavior | Mostly cold keys and fan-out |
| 5-minute test after truncate | Startup/short burst | Stabilized LSM, compaction/repair pressure, aged tombstones |

Results must be labeled: **microbenchmark**, **capacity baseline**, **workload realism**, **failure-recovery**, or **soak**. Never use an 8 B payload microbenchmark to predict p99 for a real API with 2 KiB JSON/row and hot partitions.

### 2.2. A Representative Dataset Has at Least Four Distributions

~~~mermaid
flowchart TD
    A["Real workload signals / labeled assumptions"] --> B["Partition distribution"]
    A --> C["Row & payload bytes / entropy"]
    A --> D["TTL / age & tombstone cohorts"]
    A --> E["Mutation & query mix"]
    B --> F["Seeded generator + manifest"]
    C --> F
    D --> F
    E --> F
    F --> G["Prefill & aging"]
    G --> H["Measure baseline snapshot"]
    H --> I["Load + fault injection"]
    I --> J["Validate fidelity, p95/p99, errors, recovery"]
~~~

**Distributions must be correlated**, not four independent histograms: for instance, hot devices may emit more events, larger payloads, or different TTLs; reads typically skew toward recent data, and UPDATEs target recently created existing rows. Generating all variables independently and uniformly can produce combinations that never happen in practice—or miss the worst-case combinations.

### 2.3. Real Data Must Not Be Copied Directly

To build a profile from production telemetry, **use only approved aggregate statistics**:

- Payload byte histograms (without retaining raw content).
- Rows/partition percentiles and maximums (with keys anonymized).
- Top-k hot keys **by irreversible hash**, without logging real tenant/device IDs.
- TTL policies by record type, expired/deleted ratios.
- Request counts by query type/CL/consistency, update/delete ratios.
- Hourly/daily arrival patterns; peaks/bursts and recovery times.

Never bring raw PII, secrets, access tokens, personal IPs, or payment data onto a lab cluster. When high fidelity is needed, use **privacy-preserving aggregate statistics** or synthetic data following observed distributions, with controlled access and retention in the lab.

## 3. Write a "Data Profile" Before Running Any Test

A profile can be expressed as follows; **all numbers below are hypothetical examples**:

| Variable Group | Illustrative Profile | Why Measure |
|---|---|---|
| Key scale | 200,000 devices; each key scoped to a day | Determines logical partition count |
| Rows/partition | p50=12, p95=250, p99=1,000, max=5,000 | Captures long tail and wide partitions |
| Payload | 55% 128–512 B; 35% 1–4 KiB; 10% 8–32 KiB | Network, compression, GC |
| Payload entropy | 40% JSON-like, 50% high-entropy, 10% low-entropy | Avoids all-`A` payloads |
| TTL on event writes | 20% no TTL; 60% 7 days; 20% 30 days | Mixed expiration and tombstones |
| Overall operation mix | SELECT 55%, INSERT 25%, UPDATE 15%, DELETE 5% | Business read/write pressure |
| Hot/cold skew | Top 1% of partition keys receive 40% of *requests* | Replica skew, caching |
| Read recency | 80% read the most recent 48 hours | Cache and range/read locality |
| Update recency | 85% of UPDATEs hit events created in the last 24h | Existing rows, not hidden upserts |
| Fault phase | 1 replica lost in RF3 local DC in lab | Ability to sustain CL and recover |

**Never conflate a hypothetical profile with conclusions about a production environment.** Document the source of estimates, sample sizes, collection window, peak hours, confidence, and unmeasured dimensions.

### 3.1. Distinguish Request Ratios from Row and Byte Ratios

One `SELECT` might read 1 row or 1,000 rows. One 8 KiB INSERT can cost far more than multiple 128 B INSERTs. Therefore, "55% SELECT" is solely a **request** ratio, not 55% of rows or 55% of bytes processed.

Record simultaneously:

- **ops/s** by CQL type and started/succeeded/failed request counts.
- **rows/op** and **bytes/op** (application-estimated) by type.
- **pages/op** on paginated queries.
- **hot-key request share** and hot-key byte share separately.
- **retries/speculative executions** separately, because one business request can generate multiple driver executions.

### 3.2. Partition Width Distribution

With partition `(device_id, event_day)`, row count depends on both the device's traffic rate **and** the bucket duration. Record histograms for **rows/partition**, **live bytes/partition**, and **tombstones/partition**, rather than only total device count.

If one device emits 500,000 events/day, a daily bucket may be too wide; consider hourly buckets or a deterministic shard component in the partition key after measuring and reviewing queries. **Do not add a random shard solely to balance tokens** while forgetting that reads will then need to fan out across shards.

### 3.3. "Hot" Distribution Has Two Meanings

1. **Hot by size:** certain partitions store many rows/bytes, making compaction and read scans heavy.
2. **Hot by requests:** certain partitions are queried continuously, concentrating load on a replica set.

These two sets may overlap or be disjoint. A tiny partition with only one row queried 100,000 times/minute is still hot. Conversely, a rarely read 50 MiB partition can still cause poor p99 when read in full.

## 4. Query-Driven Lab Schema: Events and State

### 4.1. Assumed Topology

The CQL examples assume an **isolated test cluster** with three nodes in a real datacenter named `dc1`, RF=3. Before creating the schema:

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

If your lab has only a single node, adjust to RF=1 and matching CL for basic codec/sizing exercises. **One node cannot verify RF3/`LOCAL_QUORUM` fault tolerance**; node-down testing requires a real multi-node topology or a validated network-simulation environment.

~~~sql
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

### 4.2. Device-Day Events Table

~~~sql
CREATE TABLE IF NOT EXISTS load_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload blob,
    event_type text,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Key explanation:**

- Partition key is `(device_id, event_day)`: bounds a device's data within a single day.
- Clustering `event_time DESC` matches "fetch newest events first"; `event_id` acts as tie-breaker.
- An event can be UPDATEd when the **full primary key** is known; no index on `status` is needed to read by device/day.
- `payload blob` is used to generate controlled sizes/entropy without uncontrolled JSON encoder overhead. In real applications, this could be text/UDTs/collections.
- Do not pick a compaction strategy arbitrarily in DDL. On Cassandra 5.x, UCS is recommended for many workloads; TWCS suits certain time-series/TTL patterns but requires validating out-of-order and mixed-TTL scenarios. Use the strategy explicitly chosen for your test.

Reading by the designed pattern:

~~~sql
SELECT event_time, event_id, event_type, status
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

### 4.3. State Table for Single-Key UPDATEs

~~~sql
CREATE TABLE IF NOT EXISTS load_lab.device_state_by_id (
    device_id uuid PRIMARY KEY,
    current_state text,
    revision bigint,
    updated_at timestamp,
    attributes map<text, text>
);
~~~

PK-based UPDATE query:

~~~sql
UPDATE load_lab.device_state_by_id
SET current_state = 'ACTIVE', revision = 2,
    updated_at = '2026-11-21T12:00:00Z'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

This is a normal **upsert**: without prefilling state, UPDATE creates a new row. Thus the generator must maintain a **catalog of existing keys**, and tests must verify the ratio of true INSERTs vs. true UPDATEs instead of merely counting "requests containing the word UPDATE".

If the business requires optimistic concurrency, a separate workload using `IF revision = ?` triggers LWT/Paxos; **never mix it silently** into the regular UPDATE ratio because latency and concurrency semantics differ.

### 4.4. Row Shape and Columns Must Match Reality

In a real schema, you may have:

- Columns frequently NULL/UNSET or optional fields.
- Small collections/UDTs if the business uses them, not just a single blob.
- Multiple event types with distinct payloads and null-field ratios.
- Per-column/per-row TTLs, deletes/range tombstones, and schema history.

To keep the example runnable, this lesson uses one blob plus two text fields. **Do not claim this simplified schema represents every Cassandra application**: when building a real profile, add complex mappings/codecs if they contribute significantly to CPU, network, or GC.

## 5. Size: From Payload to Partition and Disk

### 5.1. There Are at Least Four Size Units

| Unit | Components | Used to Answer |
|---|---|---|
| **Application payload** | Raw bytes of blob/text/JSON content | Client marshaling/network payload |
| **Serialized CQL row** | Columns, PK/CK, type encoding, protocol framing | Network request/response and codec cost |
| **Logical partition** | Multiple clustering rows + static/metadata/tombstones | Wide partitions, scans/paging |
| **Physical SSTable/replicas** | Compression, index/Bloom, fragments, compaction, RF | Disk capacity and actual I/O |

`rows × average payload` is a **baseline estimate**, not actual SSTable bytes. Cassandra includes compression chunks, metadata, partition indexes, SSTable components, tombstones, multiple uncompacted SSTables, snapshots/hints/commitlog, and replica copies.

### 5.2. Example: 1 Million Rows × 1 KiB

~~~text
1,000,000 rows × 1,024 B payload = 1,024,000,000 B
≈ 0.954 GiB of logical payload data (excluding row/partition overhead).

RF = 3:
≈ 2.861 GiB theoretical total payload copies across replicas
  BEFORE compression, indexes, compaction, tombstones, and overhead.
~~~

**Do not** treat 2.861 GiB as the final disk provision. If the payload compresses well, live SSTable bytes may be smaller; however, during flushes, compactions, or snapshots, peak disk usage can be several times the live size. Measure actual ratios on the tested hardware/network/configuration and reserve headroom rather than copying a "×3 is enough" rule of thumb.

### 5.3. Percentiles Matter More Than the Mean

Consider two profiles with the same 1 KiB average row size:

| Profile | Size Distribution | Key Difference |
|---|---|---|
| A | 100% at 1 KiB | No large tail |
| B | 90% at 128 B, 9% a few KiB, 1% tens of KiB | The p99 tail impacts GC, serialization, network, paging |

Never just hardcode `payload = new byte[1024]`. At minimum, measure/report:

~~~text
row_payload_bytes: p50, p90, p95, p99, max
partition_rows:    p50, p95, p99, max
partition_bytes:   p50, p95, p99, max
query_result_rows: p50, p95, p99, max
payload_entropy:   low / medium / high or a defined metric
~~~

If observed data only provides buckets (`[0–1KiB, 1–4KiB, 4–32KiB]`), the generator must choose an **intra-bucket distribution** and document the assumption. Do not fabricate an "exact p99" when the source data cannot support it.

### 5.4. Entropy and Compression

Cassandra typically compresses SSTables according to table settings. Two payloads of identical wire size can compress very differently:

~~~text
low entropy:
  AAAAAAAAAAAAA... (highly compressible)

medium entropy:
  {"type":"sensor","temperature":...,"tags":[...]} 
  (repeated JSON keys, varying values)

high entropy:
  randomly generated byte[] / compressed binary / ciphertext
  (barely compressible further)
~~~

Do not use **100% zeros/`A`** to compare speed against production JSON or compressed images. Conversely, 100% cryptographically random bytes can underestimate compression savings on real data. Choose entropy ratios from telemetry or labeled estimates, then **measure `SSTableCompressionRatio`** and disk footprint directly. Never assume a fixed compression factor from entropy labels alone.

### 5.5. Partition Size Depends on Rows × Columns, Not Just Payload

Per Apache Cassandra documentation, the number of cells/values per partition can be estimated as:

\[
N_v = N_r (N_c - N_{pk} - N_s) + N_s,
\]

where `N_r` = clustering rows, `N_c` = total columns, `N_{pk}` = primary key columns, and `N_s` = static columns. This is a **rough data-model estimate**; non-frozen collections and tombstones complicate cell layout.

A partition with 3,000 rows × 1 KiB payload is not equivalent to 3,000 rows × 16 KiB payload. If the data model puts all events under one `device_id` without a time bucket, the partition can grow unboundedly with retention/growth.

**A "large" partition threshold is not a magic constant.** Classic Cassandra documentation cites guidelines around **under 100 MB and under 100,000 cells/partition** as design heuristics—these are evaluation rules of thumb, not SLAs valid across every release, hardware tier, or workload. Measure actual p95/p99/max and read latencies; keep a tiny fraction of "intentionally oversized" stress cases separate to locate failure boundaries.

## 6. Partition Distribution: Uniform, Skewed, and Hot Keys

### 6.1. How Many Partitions Are Actually Live?

With primary key `((device_id, event_day), event_time, event_id)`, the actual partition count is not always `devices × days`. A device that emits no events on a given day **has no partition for that day**; active devices across many days have multiple partitions, and TTLs may expire rows.

Define separately:

~~~text
device_population             = total devices in the model
active_device_days            = (device_id, event_day) pairs with events
live_partitions_at_T          = partitions still holding live data at time T
rows_per_active_partition     = row distribution within each device-day
request_weight_per_partition  = probability that a query/UPDATE hits that partition
~~~

**Do not multiply `200,000 devices × 30 days` and claim exactly 6 million partitions exist** if only a subset of devices are active daily or many rows have expired via TTL. In the manifest, record the **actual partitions created** along with the verification method.

### 6.2. Uniform Token Distribution ≠ Uniform Access

A UUID/hashed partition key may spread tokens fairly evenly via Murmur3 and vnodes, yet **fail to spread request load evenly** if the same keys are queried repeatedly.

~~~mermaid
flowchart TD
    A["200k devices, UUIDs distribute tokens"] --> B["Replicas/token ranges"]
    C["Top 1% device IDs receive 40% of requests"] --> D["Only a few replica sets serve hot keys"]
    B --> D
    D --> E["CPU/queue/read latency skew"]
    E --> F["Timeouts & overload when a replica fails"]
~~~

A uniform profile tests load distribution across tokens, not skew. Add both a **realistic skew** profile and a **worst-case hotset** profile to find saturation limits when requests concentrate on a small key set.

### 6.3. A Simple Hot/Cold Sampler

Example configuration where **the top 1% of devices receive 40% of visits**, and the remaining 99% receive 60%:

~~~java
import java.util.SplittableRandom;

static int chooseDeviceIndex(
        SplittableRandom rng, int devices, int hotDevices) {
    if (devices <= 1 || hotDevices <= 0 || hotDevices >= devices) {
        throw new IllegalArgumentException("Invalid hotset");
    }
    if (rng.nextDouble() < 0.40) {
        return rng.nextInt(hotDevices);
    }
    return hotDevices + rng.nextInt(devices - hotDevices);
}
~~~

Setting `devices=200_000` and `hotDevices=2_000` creates **that exact hotset structure on device IDs**. If a single device spans multiple `event_day` partitions, the top 1% of *devices* need not equal the top 1% of *partitions*: re-measure request share at the actual partition-key level. You can also use a Zipf/Zipf-like distribution or weighted alias sampler for a continuous long tail rather than just two hot/cold buckets.

### 6.4. Temporal Hotness and Shifts During Faults

Do not keep one static hotset forever if the real product exhibits trending bursts or shift-based usage. You can split runs into:

- **Static hotset:** models persistently prominent accounts/tenants.
- **Hourly rotating hotset:** models work shifts, campaigns, or trending topics.
- **Post-failure hotset shift:** client failover or coordinator selection can suddenly funnel traffic onto another replica.
- **Bursty hot keys:** 40% of requests arrive within a few minutes; average QPS stays flat while peak intensity spikes.

During fault tests, maintain the **exact same hotset generation process** across baseline and fault phases, or explicitly declare any intentional change; otherwise, you cannot tell whether p99 shifted due to the outage or a moving hotset.

### 6.5. Validate Skew Instead of Trusting Configuration

After generating data and requests, emit **aggregate validation stats**:

~~~text
distinct partition keys
requests per hashed partition key: p50/p95/p99/max
top 1% keys share of read/write requests
top 1% keys share of bytes transferred
rows per partition: p50/p95/p99/max
token range / node coordinator requests share
~~~

To inspect hot partitions on a node, `nodetool toppartitions` can be used on supported versions; it is a sampler, **not** a complete 100% workload inventory. Never export raw tenant/device identifiers into Prometheus labels or public logs.

## 7. TTL, Data Age, and Tombstones

### 7.1. TTL Is Measured from Write Time, Not `event_time`

In Cassandra, `INSERT ... USING TTL 604800` gives written cells a TTL of **604,800 seconds = 7 days** from the **moment Cassandra processes the mutation**, not anchored to an `event_time` 7 days in the past.

~~~sql
INSERT INTO load_lab.events_by_device_day
    (device_id, event_day, event_time, event_id,
     payload, event_type, status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    0x0001AABB,
    'telemetry',
    'NEW'
) USING TTL 604800;
~~~

**Important:** if you load data today with an `event_time` from 30 days ago and `USING TTL 604800`, it still has roughly **7 days of TTL from write time**, not "expired 23 days ago". Therefore, **backdating event timestamps does not create an SSTable with genuine TTL history**.

### 7.2. Checking Remaining TTL

~~~sql
SELECT event_time, event_id,
       TTL(payload), TTL(status)
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

`TTL(column)` returns remaining seconds or null when the column has no TTL (or is no longer live); it **does not return** "data age since `event_time`". Seeing TTL count down while `event_time` stays fixed is normal. When `payload` and `status` are inserted together with `USING TTL`, they start with the same TTL; updating `status` separately later can give `status` a different TTL from `payload`.

### 7.3. Building TTL Cohorts and Tombstone Age

| Cohort | Target State | Safe Way to Create in Lab |
|---|---|---|
| No TTL | Long-lived live cells | INSERT without TTL |
| Long TTL, fresh | 7/30-day retention per profile | INSERT with matching TTL |
| Near expiry | Created earlier and aged via elapsed time; or short-TTL lab | **Do not** merely edit `event_time` |
| Just expired | Wait for short TTL to expire naturally, verify column no longer live | Creates tombstones / logical expiration |
| Aged tombstones | Wait/soak across flush/compaction cycles in an isolated lab | Do not force flush/snapshot and call it aged |
| Post-reclamation | Observe after appropriate GC grace/compaction/repair conditions | Never assume disk is freed immediately when TTL=0 |

A long-term test can span **7 real days** using snapshots/preloaded SSTables built over time; a short lab may use **90 s / 300 s / 900 s** TTLs to observe the phases, but **that is only a scale model**. It does not reproduce the fragmentation and repair history of 7–30 days.

### 7.4. Lifecycle of a TTL Cell

~~~mermaid
flowchart LR
    A["INSERT cell with TTL"] --> B["Cell is live"]
    B --> C["TTL expires"]
    C --> D["Tombstone / logically deleted"]
    D --> E["Grace + safety conditions"]
    E --> F["Compaction can purge"]
    F --> G["Old cell no longer stored"]
~~~

Tombstones require time and safety guarantees so resurrected data does not reappear when an offline replica returns. Passing `gc_grace_seconds` **does not mean bytes are immediately erased from disk**; compaction purges only when safety conditions hold, and repaired/unrepaired state or overlapping SSTables can prevent purging.

**Do not arbitrarily shorten `gc_grace_seconds` just to make a benchmark reclaim tombstones faster**, as it can break recovery safety if repairs or replica availability are not guaranteed. Any change must belong to a risk-assessed policy test, not a trick for cleaner charts.

### 7.5. Mixed TTLs and Compaction

In the example profile, 20% of events have no TTL, 60% have a 7-day TTL, and 20% have a 30-day TTL. When the same table/SSTable mixes fresh and old cells, differing TTLs, and late updates, SSTables **cannot simply be dropped whole-file** when only part of the data expires.

That is why:

- **TWCS** is often useful for time-series TTL workloads, with caveats when late/out-of-order writes mix timestamps and ages within the same SSTable.
- **UCS** in Cassandra 5.x is broadly recommended for many workloads, yet still must be benchmarked on your specific data model.
- No single compaction strategy is "best" for every case; the choice depends on update ratio, TTL mix, and read amplification.

When evaluating TWCS, avoid setting arbitrary historical timestamps via `USING TIMESTAMP` to fake age: this often causes more problems than a genuinely aged workload, especially with out-of-order data.

### 7.6. TTL 0, UPDATEs, and Idempotency

An UPDATE with a new TTL applies **to the mutated cells written**, rather than necessarily preserving old TTLs on overwritten columns. Retrying `INSERT ... USING TTL 604800` after a timeout can also **extend** the retention deadline relative to the first attempt.

Key testing rules to note:

- `USING TTL 0` means **no TTL / remove TTL** under CQL semantics, **not immediate deletion**.
- To enforce a fixed expiration date, store the business deadline and compute **remaining** TTL on each mutation; strictly prevent remaining ≤ 0 from turning into TTL 0.
- CQL `UNSET` skips mutating a column; `NULL` deletes the column and can create a tombstone. Distinguish these when generating partial updates.
- Do not use ultra-short TTL writes during prefill and then let rows vanish before measuring update hit ratios.

### 7.7. Measuring Tombstones in the Right Phase

Track `TombstoneScannedHistogram`, `TombstoneWarnings`, `TombstoneFailures`, compaction backlog, SSTables/read, and disk usage. Never assume "10,000 expired cells means every query scans 10,000 tombstones": it depends on the queried partition/range, coverage, compaction, and SSTable layout.

If a benchmark starts right after **truncate and fresh prefill**, it is measuring a "young" table and cannot prove p99 after the first month of accumulated TTLs and deletes.

## 8. INSERT, UPDATE, DELETE, and True Mutation Ratios

### 8.1. Same CQL Write Count, Different Cost

| Operation | Behavior | What Must Be Modeled in the Dataset |
|---|---|---|
| INSERT new PK | New row/cells, grows dataset | Fresh identity, true insert rate |
| INSERT same PK | Cassandra upserts existing cells | Update/timestamp history, row count need not grow |
| Single-column UPDATE | Appends a new cell version to LSM | Pick an **existing** PK so writes do not become pure inserts |
| Multi-column UPDATE | Appends mutations for multiple cells | Column mix, null/unset, TTL reset |
| Column/row/range DELETE | Tombstones | Delete ratio and tombstone age |
| LWT `UPDATE IF ...` | Paxos CAS, may return false | Conflict rate, serial CL, extra network round trips |
| Counter increment / list append | Non-idempotent writes, distinct semantics | Never blind-retry, never lump into "normal UPDATE" |

**Cassandra does not update SSTables in place.** An UPDATE appends a new mutation to the write path; compaction merges versions and tombstones later. A test that only INSERTs new rows misses the read and compaction cost of update-heavy workloads.

### 8.2. Update Ratios Must Target Real Keys

Suppose 15% of the workload is UPDATE:

~~~text
100,000 operations:
  SELECT 55,000
  INSERT 25,000
  UPDATE 15,000
  DELETE  5,000
~~~

If the generator picks a globally random UUID for every UPDATE, nearly every UUID does not exist → **Cassandra still upserts**, and the test fails to generate actual "update hits".

Maintain a catalog of prefilled keys, select update targets from that catalog, and verify statistics:

~~~text
intended UPDATE request share          = 15%
verified update-target-exists share    ≈ 100% in this profile
actual row count delta due to UPDATE   ≈ 0 if PK unchanged
cells touched/update                   = 1 or a few per profile
status updates vs payload overwrites   = separate ratios
~~~

Note that rows can **expire via TTL**, so a key from yesterday's catalog is not guaranteed to be live today. Update-target hit ratio must be verified against aged live state, not merely against an append-only insert log.

### 8.3. Updating Hot Rows and Conflict Semantics

You can configure:

- 80% of updates touch recently created rows, 20% touch older rows.
- 70% of updates modify `status` only, 30% overwrite `payload`.
- 10% of updates target hot devices, though overall request skew may be steeper.
- A small LWT `IF revision = ?` cohort to measure CAS contention **separately**, never combined with unconditional writes.
- A small late-arrival update cohort targeting older time-bucket partitions to evaluate TWCS/compaction behavior.

Use **explainable ratios** and verify them directly at both generator and DB levels. If an UPDATE and INSERT on the same row carry arbitrary CQL timestamps, last-write-wins may resolve differently than the test intended; in time-series tests, never assume arrival order automatically equals write-timestamp order.

### 8.4. UPDATEs Can Increase Tombstone Pressure

Overwriting a non-null value with NULL causes Cassandra to write a deletion marker. A PATCH missing a field whose serializer binds NULL instead of UNSET creates "unnecessary" tombstones. Tests should represent:

~~~text
update_existing_non_null -> new_non_null
update_existing_non_null -> NULL (delete column)
update_with_UNSET         -> preserve column
DELETE entire row         -> row tombstone
expire_by_TTL             -> TTL-based tombstone
~~~

Measure these groups separately; they impact read latency and compaction differently and cannot be collapsed into a single "writes/s" metric.

### 8.5. Mixed Read/Write Creates Different Pressure Than One-Way Prefill

In a mixed run, inserts and updates trigger memtable flushes, shifting SSTable counts and compactions **while SELECTs are reading**. A 100%-write run followed by a 100%-read run is not equivalent to concurrent reads and writes.

Run:

1. **Read-only profile** on a prefilled dataset.
2. **Write-only profile** to find ingestion ceiling.
3. **Mixed realistic profile** matching target ratios and skew.
4. **Mixed + fault profile** when a replica/network link fails.

Compare them for diagnostic insight; never extrapolate mixed-load throughput from read-only throughput.

## 9. Read Patterns Must Share the Same Data Distribution

### 9.1. Four Important `SELECT` Patterns

| Read Pattern | Illustrative CQL | Cost and What to Simulate |
|---|---|---|
| Point lookup | `WHERE device_id=? AND event_day=? AND event_time=? AND event_id=?` | Exact clustering row, usually few bytes |
| Latest-N | `WHERE device_id=? AND event_day=? LIMIT 100` | Locality when partition uses clustering `DESC` |
| Intra-day range | `WHERE ... AND event_time>=? AND event_time<?` | Wide variance in row and page counts |
| Read miss | `WHERE device_id=? AND event_day=?` for an absent partition | Bloom filters/indexes; differs from read hits |

**Never** build a 50%-SELECT profile where every SELECT fetches a single "just-written" row if the real system performs historical range reads, read misses, cache misses, and pagination.

### 9.2. Read Recency Shapes Cache Behavior

Assume 80% of reads query events from the past 48 hours:

- 60% of SELECTs access the newest partitions (frequently hot-cached).
- 20% are range queries over partitions from a few days ago.
- 15% are point queries into historical data.
- 5% are miss/negative lookups.

These illustrative ratios **decompose 100% of READ operations**, not total requests. When combined with a 55% overall read share, multiply conditionally when aggregating.

### 9.3. Paging Changes Latency and Response Size

~~~sql
SELECT event_time, event_id, payload
FROM load_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 1000;
~~~

If Java Driver uses `pageSize=100` and the query matches 1,000 rows, consuming the full result triggers multiple page requests. The proportion of queries **iterated to the end** versus queries **reading only the first page** must be modeled accurately. A test that calls `session.execute` without **iterating the results** fails to measure the cost of a consumer paging through the full result set.

`pageSize=100` is a page-size target, **not** a guarantee of exactly 100 rows/page or 100 total rows/query. A read encountering many tombstones can return few live rows while scanning many cells.

### 9.4. Negative Reads and Data Age

If most reads query TTL-expired events, the hit/miss ratio drifts during the test. A workload reading 30 days of history on a 7-day retention table generates many misses; that is a different business workload from "80% reading the last 48h" and must be documented and modeled explicitly.

**Every SELECT in a load run must use a key/bucket distribution compatible with the prefilled dataset.** If SELECT uses random UUIDs disjoint from loaded keys, the benchmark mostly measures misses while still reporting deceptively high throughput.

## 10. Reproducible Data Generation: Seeds, Identity, and Entropy

### 10.1. Manifest Required Before Generating Data

An **illustrative** manifest, not necessarily tied to a specific tool's config format:

~~~yaml
dataset_version: "load-lab-v1"
seed: 20261121
schema_version: "events_by_device_day-v1"
device_count: 200000
event_count: 1000000
hot_device_fraction: 0.01
hot_request_share: 0.40
day_start_utc: "2026-11-01"
days: 20
payload_mix:
  small_128_512_bytes: 0.55
  medium_1024_4096_bytes: 0.35
  large_8192_32768_bytes: 0.10
ttl_write_mix:
  none: 0.20
  seven_days: 0.60
  thirty_days: 0.20
operation_mix:
  read: 0.55
  insert: 0.25
  update: 0.15
  delete: 0.05
~~~

In a real manifest, also record: generator commit/build hash, Cassandra and Java Driver versions, RF/CL/DC, compaction/compression options, client threads, rate, start/end timestamps, prefill steps, test phase, and faults. **Never** store credentials, access tokens, or raw production keys.

### 10.2. Seeds Enable Reproducibility, Not Identical Numbers

The same PRNG seed reproduces the **logical sequence of choices** if the code and RNG call order remain unchanged. Yet Cassandra's distributed execution, background compaction, GC, OS scheduling, and token/vnode placement still cause p99 to vary across runs. Therefore:

- Use fixed seeds for data and workload in A/B comparisons.
- Separate deterministic **row IDs** from **workload arrival order**, which may vary.
- Avoid calling `UUID.randomUUID()` inside deterministic paths without recording it.
- In parallel runs, partition seeds deterministically by worker/shard and ensure workers **do not collide on keys unintentionally**.
- Record **actually generated statistics** to verify the manifest; a seed alone does not prove the resulting distribution matched.

### 10.3. Generating Deterministic UUIDs for Devices and Events

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

static UUID stableDeviceId(long seed, int index) {
    String key = "load-device:" + seed + ":" + index;
    return UUID.nameUUIDFromBytes(
        key.getBytes(StandardCharsets.UTF_8));
}

static UUID stableEventId(long seed, long sequence) {
    String key = "load-event:" + seed + ":" + sequence;
    return UUID.nameUUIDFromBytes(
        key.getBytes(StandardCharsets.UTF_8));
}
~~~

`UUID.nameUUIDFromBytes` produces deterministic UUIDs from bytes, ideal for **synthetic fixture identities**. Never treat it as a cryptographic/secret UUID or assume it safely "anonymizes" production identifiers. Name-based/v3 UUIDs distribute sufficiently well across token hashes for this lab, though you should still verify token ranges and PRNG properties.

### 10.4. Payload Generator Across Entropy Classes

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;

static int choosePayloadSize(SplittableRandom rng) {
    double r = rng.nextDouble();
    if (r < 0.55) {
        return rng.nextInt(128, 513);
    } else if (r < 0.90) {
        return rng.nextInt(1024, 4097);
    }
    return rng.nextInt(8192, 32769);
}

static byte[] syntheticPayload(SplittableRandom rng, int size) {
    byte[] out = new byte[size];
    double kind = rng.nextDouble();

    if (kind < 0.10) {
        // Low entropy: highly compressible.
        Arrays.fill(out, (byte) 'A');
    } else if (kind < 0.50) {
        // Medium entropy: repeating random 64-byte dictionary.
        byte[] dictionary = new byte[64];
        rng.nextBytes(dictionary);
        for (int i = 0; i < size; i++) {
            out[i] = dictionary[i % dictionary.length];
        }
    } else {
        // High entropy: less compressible.
        rng.nextBytes(out);
    }
    return out;
}
~~~

Here the entropy mix is **10% low, 40% medium, 50% high** (matching the profile table above). This is a *synthetic approximation*, not real JSON. If the service processes JSON/Avro/Protobuf, include real encode/decode paths because random byte blobs do not measure JSON parsing, allocation, and canonicalization costs.

### 10.5. Generating Consistent `event_time` and Buckets

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.SplittableRandom;

static LocalDate chooseDay(SplittableRandom rng) {
    return LocalDate.of(2026, 11, 1)
        .plusDays(rng.nextInt(20));
}

static Instant chooseTimeInsideDay(
        SplittableRandom rng, LocalDate day) {
    return day.atStartOfDay(ZoneOffset.UTC)
        .toInstant()
        .plusSeconds(rng.nextLong(86_400));
}
~~~

In this generator, `event_day` aligns with `event_time` in UTC. If production uses device-local timezones/day buckets, model timezones and DST per real business rules; never arbitrarily convert UTC to a local date and shift the partition key.

**TTL reminder:** this is solely the "event timestamp recorded in the row". Running the generator today still starts the TTL from the **time of the INSERT**, not from Nov 1–20, 2026.

## 11. Java Driver 4.x: Sample Prefill with TTL Cohorts

### 11.1. Prepared Statements for TTL and No-TTL

An INSERT with TTL requires a CQL statement with `USING TTL ?`; non-TTL rows use a separate statement. Never use `TTL=0` to represent an "expired row".

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.LocalDate;
import java.util.SplittableRandom;
import java.util.UUID;

static void prefillDemo(CqlSession session,
                        long seed, int events, int deviceCount) {
    String columns = "(device_id,event_day,event_time,event_id," +
                     "payload,event_type,status)";
    String values = " VALUES (?,?,?,?,?,?,?)";
    String prefix = "INSERT INTO load_lab.events_by_device_day " +
                    columns + values;

    PreparedStatement noTtl = session.prepare(prefix);
    PreparedStatement withTtl = session.prepare(
        prefix + " USING TTL ?");

    SplittableRandom rng = new SplittableRandom(seed);
    int hotCount = Math.max(1, deviceCount / 100);

    for (int sequence = 0; sequence < events; sequence++) {
        int deviceIndex = chooseDeviceIndex(rng, deviceCount, hotCount);
        UUID device = stableDeviceId(seed, deviceIndex);
        LocalDate day = chooseDay(rng);
        Instant eventTime = chooseTimeInsideDay(rng, day);
        UUID eventId = stableEventId(seed, sequence);
        byte[] bytes = syntheticPayload(rng, choosePayloadSize(rng));

        double ttlClass = rng.nextDouble();
        BoundStatement stmt;
        if (ttlClass < 0.20) {
            stmt = noTtl.bind(device, day, eventTime, eventId,
                ByteBuffer.wrap(bytes), "telemetry", "NEW");
        } else {
            int ttlSeconds = ttlClass < 0.80
                ? 7 * 86_400 : 30 * 86_400;
            stmt = withTtl.bind(device, day, eventTime, eventId,
                ByteBuffer.wrap(bytes), "telemetry", "NEW",
                ttlSeconds);
        }

        session.execute(stmt
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false));
    }
}
~~~

**Explicit limitations:** this function is an **illustrative, synchronous, sequential prefill generator** to demonstrate schema/TTL/cohorts; **it is not a high-QPS load generator**. It does not enforce the `rows/partition` histogram (`p50=12/p99=1,000`), because random device/day selection may produce a different shape. For high fidelity, **allocate row counts per partition from the target histogram first**, then generate rows up to each partition's quota; finally measure actuals and tune.

The demo conservatively sets `setIdempotent(false)`: even though the INSERT has fixed primary keys and payload, **TTL means a replay after timeout can extend retention time**, making it non-idempotent with respect to a retention deadline. For prefills requiring absolute expiry, use operation IDs, store deadlines/remaining TTL, and apply controlled retry policies. When a test aims to measure the application's actual replay behavior, set the flag to match true semantics rather than copying the demo.

### 11.2. Verify Data Before Running the Workload

After prefill:

~~~sql
SELECT event_time, event_id, event_type, status
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

The device UUID above is just an example; the deterministic generator **is not guaranteed to produce that exact UUID**. In real tests, pull a device/day **from the manifest or the key set written by the generator**, rather than picking an illustrative UUID and concluding data loading failed because the query returned empty.

Verify:

- Total successful inserts and client errors.
- Actual distinct partition keys (obtained via a separate sample/index; avoid full table scans on production).
- Payload byte histogram **on the generator side** and compressed SSTable footprint on Cassandra.
- Ratio of records with TTL vs. null TTL by sampling the key catalog.
- No random "update-only" keys that were never inserted.
- Local replicas Up, schema agreement, and correct RF/CL.

### 11.3. Scaling from Prefill to a Multi-Worker Generator

For real load generation:

1. Partition the `sequence` range or key catalog into disjoint shards.
2. Derive each worker's seed deterministically from the master seed + worker index.
3. Use `executeAsync` with bounded concurrency rather than sequential `session.execute`; **never** create unbounded futures.
4. Apply an open-loop target arrival rate to measure overload behavior; track offered vs. achieved QPS.
5. Enforce deadlines/request timeouts, idempotency, and **never stack independent retries across layers**.
6. Record successes/timeouts/errors, completed bytes, and partition histograms per phase.
7. When a worker cancels at deadline, record mutation outcome as **UNKNOWN** if it may already have reached Cassandra.

**Never open a new session per record.** Keep Java Driver `CqlSession` long-lived, reuse prepared statements, and do not log every payload or query value. Bounded queues/throttling and token-aware routing keep the workload runner from becoming the bottleneck itself.

## 12. `cassandra-stress` User Mode and Model Limitations

Apache Cassandra includes `cassandra-stress` with **user mode**: a YAML profile describes the schema, column distributions, custom SELECT queries, and operation weights. It is useful for preliminary baselines on a schema, but **cannot fully simulate** every business workflow or TTL aging pattern on its own.

### 12.1. Draft Profile for `events_by_device_day`

Illustrative format showing how declarations work; check `cassandra-stress help user` and your exact tool version before running:

~~~yaml
specname: realistic_events
keyspace: load_lab
table: events_by_device_day

columnspec:
  - name: device_id
    population: uniform(1..200000)
  - name: event_day
    population: uniform(1..20)
  - name: event_time
    cluster: gaussian(1..1000,3)
  - name: payload
    size: gaussian(128..32768,8192)

queries:
  latest:
    cql: SELECT event_time, event_id, event_type, status
         FROM events_by_device_day
         WHERE device_id = ? AND event_day = ? LIMIT 100
    fields: samerow
~~~

This is a **starter profile for learning syntax**, not guaranteed to run verbatim on every `cassandra-stress` release: generation of CQL types like `date`/`uuid` and `cluster` fields can depend on version constraints. Verify the real schema, codecs, and generated values. A `gaussian(128..32768,8192)` distribution differs from the **three-bucket 55/35/10 mix** defined earlier; matching an exact histogram requires multiple profiles, a custom runner, or a Java generator.

**There is no `USING TTL` in the implicit INSERT of this example**, so this profile does not reproduce TTL cohorts or age-based updates unless supplemented by another workflow or tool. Never report "TTL-realistic" results from this profile alone.

### 12.2. Running User Mode with Illustrative Weights

~~~bash
# LAB CLUSTER ONLY. Do not use truncate=once on data you need to keep.
cassandra-stress user profile=./realistic-events.yaml duration=10m \
  "ops(insert=3,latest=7)" -node 10.0.0.11 -rate threads=20
~~~

Those weights represent 30% INSERT / 70% SELECT **within the tool's operation mix**, not the 55% SELECT / 25% INSERT / 15% UPDATE / 5% DELETE business workload. `cassandra-stress user` has its own rules for insert/query operations, batching, and key reuse; always verify the actual observed operation output. The command omits `truncate=once` because it is a **destructive option that wipes the lab table**.

For UPDATE/DELETE/CAS targeting existing keys, TTL cohorts, and complex temporal locality, a custom Java runner or a reviewed NoSQLBench/custom workload script is usually more suitable. Regardless of the tool, report the **observed op mix** rather than treating YAML weights as proof.

### 12.3. Common Stress-Tool Biases

| Bias | Symptom | How to Check |
|---|---|---|
| Tool generates uniform keys while app skews heavily | Benchmark QPS looks unrealistically good | Top-k key share |
| Tool INSERTs in batches while app writes single rows | Write overhead/batch latency differs | Batches/op, partitions/batch |
| Tool creates new rows instead of updates | Partition/row count grows unexpectedly | Partition/row count delta |
| Tool omits TTLs | Artificially low tombstones | TTL sample, expired cohort |
| Tool queries only cached hot rows | Artificially low read p99 | Read age, misses, SSTables/read |
| Tool payloads compress too easily | Artificially small disk/I/O footprint | Compression ratio vs. real data |
| Tool runs only short durations | Compaction and aging never appear | Longer soak runs, pre-aged datasets |
| Tool sends all traffic to one DC | Differs from real routing/WAN | Session local DC, coordinator metrics |

### 12.4. Splitting Models When One YAML Cannot Express Everything

You can split the test across phases and tools:

~~~text
Tool A: seeded schema + rows/partitions profile prefill
Tool B: aged TTL/deletes on a clear timeline
Tool C: mixed reads/inserts/updates/deletes from existing-key catalog
Tool D: fault orchestrator (approved clusters only)
Tool E: metrics collector + workload fidelity validator
~~~

These can be unified in one program, provided they **share the same manifest/`run_id`, clock timeline, and ID catalog**. If prefill uses different device IDs from the load runner, the benchmark will measure misses and upserts instead of the intended workload.

## 13. Prefill, Aging, Steady-State: Execution Order Determines Results

### 13.1. Why Prefill Before Measuring?

A freshly initialized Cassandra cluster has no historical SSTables, compaction overlap, or expired cells. Sending UPDATEs and SELECTs immediately typically causes:

- UPDATEs to hit **nonexistent** keys, turning into upserts.
- SELECTs to return mostly misses.
- Fresh caches that behave differently from steady-state hot caches.
- Zero tombstones from expired TTLs or aged DELETEs.
- Disk and compaction backlogs that do not reflect steady state.

Therefore, you must populate **a dataset large enough for read/write paths to have real targets**, and allow enough time for background states to emerge. Prefill is only the starting step, **not the entire load test**.

### 13.2. A Reproducible Timeline

| Phase | Contents | What to Record |
|---|---|---|
| **P0 — Validate** | Check schema, RF/CL/DC, node health, free space, seed | Cluster/version/manifest |
| **P1 — Prefill** | Load partitions, rows/payloads/TTLs per target distributions | Successful rows, key catalog, histograms |
| **P2 — Aging** | Run deletes/updates/TTL cohorts and let real time pass | Remaining TTL, tombstones, SSTable counts |
| **P3 — Warm-up** | Moderate read/write traffic to stabilize caches/JIT/connections | Cache hits, compaction, latency trends |
| **P4 — Baseline** | Measure mixed workload without faults at steady rate | QPS, p50/p95/p99, errors, resources |
| **P5 — Fault** | Keep same offered workload, inject one controlled fault | Exact fault events, errors, availability |
| **P6 — Recovery** | Remove fault, keep load running to measure recovery | Hints, repair/compaction, p99 recovery |
| **P7 — Verify** | Validate final state, fidelity, missing/duplicate effects | Acceptance report, run artifacts |

Phases need not share a fixed number of minutes. **Phase duration** depends on TTL/compaction time horizons and real SLOs. A 20-minute lab with 90 s TTLs can demonstrate expiration mechanics; it **does not** substitute for a multi-day soak when production retention is 30 days.

### 13.3. Warm-Up Must Not Erase the State You Want to Measure

Warming connection pools, JIT, and caches before taking a baseline is valid. However, if the benchmark goal is **cold-start or recovery**, warm-up can mask the problem. Run two distinct experiments:

- **Cold-ish state:** cluster started/restored per scenario, measured before warming.
- **Warm steady state:** sufficient traffic and warmed caches, baseline captured before fault.

Do not run `nodetool flush`, major compaction, `truncate`, or node restarts arbitrarily between runs, as they alter SSTable layout, caches, and disk state. If used as an experimental variable, record it as an explicit phase and perform it only on lab clusters.

### 13.4. Aging Data Without Fake "Time Travel"

Three sound approaches, ordered by cost:

1. **Real-time soak:** ingest TTL mixes, run daily/hourly UPDATE/DELETEs, monitor SSTables and tombstones. Highest fidelity to real lifecycle, but time-consuming.
2. **Pre-aged lab copy:** restore snapshots/data volumes **from an approved lab environment with matching version and topology**, ensuring zero PII; verify repair/ownership/metadata before testing.
3. **Short TTLs to model mechanics:** use 30/90/300 s TTLs, wait for cohorts to expire, and observe. Fast and repeatable, yet **not equivalent** to 7/30 days of compaction, repair, and SSTable aging.

**Do not** simulate tombstone age merely by backdating `event_time` 90 days in CQL. That column is distinct from write timestamps/TTLs and does not age SSTables. Avoid tampering with a node's system clock or manipulating production SSTable files to "create age", as it easily breaks cluster semantics and safety.

### 13.5. Even at Constant Target QPS, the Dataset Keeps Changing

In a mixed workload, INSERTs add rows/partitions, DELETE/TTLs reduce live cells, UPDATEs create new cell versions, and compaction reshapes on-disk layout. A 6-hour run at 5,000 ops/s **is not testing a static dataset**.

Track:

~~~text
estimated net live row growth =
    new_key_inserts
    - whole_row_deletions
    - rows becoming fully expired
    + reinserted/previously missing rows

estimated logical cell churn =
    cells updated + cells expired + cells deleted
~~~

Measure both directly rather than relying solely on formulas, because Cassandra uses liveness markers, cell-level TTLs, and timestamps. When A/B testing compaction from an identical starting state, use **verified** snapshots/recreation to prevent dataset drift from confounding results.

## 14. Fault Testing Against the Same Data Before and After Failure

### 14.1. Fault Injection Does Not Replace Workload Fidelity

A node-down run over 1,000 uniform keys with zero TTLs and zero UPDATEs measures fault survival **for that trivial workload**—it does not prove the system survives a node failure when hot keys hammer one replica set or tombstone scans surge after 30 days.

To compare baseline against fault:

- **Identical schema/RF/CL/compaction/compression** (except the tested variable).
- Identical dataset seed or starting snapshot.
- Identical hot/cold distribution and query mix by phase.
- Identical target offered QPS and concurrency/backpressure limits.
- Identical timeout/retry/idempotency rules.
- Change **only one primary fault** in a single experiment before exploring labeled combined faults.

### 14.2. Fault Matrix for a Single-DC RF=3 Lab

| Fault Tested | Conditions | What to Observe | Do Not Conclude |
|---|---|---|---|
| One node stopped | RF3, local DC has 3 nodes, `CL=LOCAL_QUORUM` | Availability, coordinator shifts, p95/p99, hints, backlog | "Timeouts never happen" |
| Network latency to one replica | Lab proxy/network emulator | Read latency distribution, retries/speculation, queues | A single ping RTT represents CQL |
| Brief packet loss | Clear traffic and fault windows | Driver timeouts, unknown writes, recovery | Timeout = mutation uncommitted |
| Disk I/O throttling on one node | Controlled throughput/latency, disk headroom present | Flush/compaction backlog, GC, p99 | Client QPS alone tells the whole story |
| Compaction backlog | Realistic ingestion/update/TTL mix | Pending compactions, SSTables/read, disk used | One major compaction "fixes the benchmark" |
| Burst TTL expiration | Cohorts expiring together | Tombstone scans, read p99, disk reclaim lag | TTL expired = bytes immediately freed |
| Hot-key burst during failure | Keys with significant replica overlap | Per-node skew, client errors | Uniform key load reflects this |

**Never perform fault injection on production** without an explicit runbook, approval, and rollback plan. The safest path is a dedicated test cluster with full permission to stop/restore nodes and isolated disk/network budgets.

### 14.3. RF3 + `LOCAL_QUORUM` Does Not Make Every Failure "Seamless"

In an RF=3 DC, `LOCAL_QUORUM` requires **two replica responses** by CL rules. When one replica goes down, theoretically the two remaining replicas can satisfy requests, yet:

- Coordinators may not yet have updated Down-node status.
- One of the two remaining replicas may become slow or overloaded.
- The driver may retry another coordinator within policy limits.
- Hints/repair and compaction can add recovery load.
- In-flight writes when a link breaks may end with an **unknown outcome**.

Therefore, report **actual availability and timeouts**, rather than using quorum arithmetic to claim zero errors. On an RF1 / 1-node setup, stopping the node naturally halts reads and writes—that is **not** an RF3 fault-tolerance experiment.

### 14.4. Measuring Recovery After Bringing the Node Back

Record timestamps:

~~~text
t0  stable baseline
t1  fault injected
t2  fault detected by client/driver/cluster
t3  fault cleared
t4  cluster nodes Up/Normal in required state
t5  offered QPS and p99 meet recovery criteria continuously
t6  data/repair/hints/compaction meet integrity/recovery conditions
~~~

**`t4 ≠ t6`**: `nodetool status` showing a node Up does not prove all replicas hold identical data; monitor hints, repair state, consistency checks, and workload outcomes per runbook. Measure **time-to-recover** for both client SLOs and data integrity.

### 14.5. Verifying Data Correctness Under Retries

An UPDATE setting `status='ACTIVE'` with a consistent timestamp tolerates retries better than counter increments or list appends; however, TTLs and concurrent writes still complicate semantics.

During fault injection:

- Attach an `operation_id`/request ID to reconcile intended vs. observed transitions.
- Separate `SUCCESS`, `FAILED`, and `UNKNOWN_TIMEOUT`.
- Never treat a timeout as a rollback.
- Never treat LWT `wasApplied=false` as a network error to retry.
- Count duplicate inserts/side effects and lost updates by auditing the key catalog post-recovery.
- Keep the required consistency level; never lower CL to make error dashboards look cleaner.

A representative dataset must include enough updates and TTLs to **expose idempotency bugs** that insert-only tests never catch.

## 15. Observing Both the Driver and Cassandra Properly

### 15.1. Minimum Dashboard

| Source | Metric | Why Needed |
|---|---|---|
| Load generator | Offered operations/s vs. completed/s | Detects tool failing to sustain load when backend slows |
| Load generator | Actual operation mix: read/insert/update/delete | Verifies profile adherence |
| Load generator | End-to-end p50/p95/p99, timeouts, error codes | Reveals tail latency and failures |
| Load generator | Read-hit/update-target-hit, rows/op, bytes/op | Prevents silently measuring misses/upserts |
| Driver | Requests, retries, speculative executions, in-flight, pool saturation | Separates business requests from actual CQL executions |
| Cassandra Table metrics | `EstimatedPartitionSizeHistogram`, `EstimatedColumnCountHistogram` | Measures partition width and overall shape |
| Cassandra Table metrics | `TombstoneScannedHistogram`, `TombstoneWarnings`, `TombstoneFailures` | Measures TTL/delete pressure |
| Cassandra Table metrics | `SSTablesPerReadHistogram`, `ReadLatency`, `WriteLatency` | Read amplification / local latency |
| Cassandra Table metrics | `LiveDiskSpaceUsed`, `TotalDiskSpaceUsed`, `CompressionRatio` | Capacity, SSTables, and compression |
| Cassandra | `PendingCompactions`, `PendingFlushes`, CPU, GC, disk I/O/network | Background workload and overload |
| Cluster | Node Up/Down, hints, repair/recovery progress | Separates detection from recovery |

Metric names may vary across Cassandra 4.x/5.x and exporters. The table metrics above are documented by Apache Cassandra, but always verify actual exporter mappings and units. Cassandra JMX metrics are typically **per-node**; cluster dashboards must aggregate properly instead of summing or averaging node-level p99s like counters.

### 15.2. Verification Tools

In the **lab**:

~~~bash
nodetool status
nodetool tablestats load_lab.events_by_device_day
nodetool tablehistograms load_lab events_by_device_day
nodetool tpstats
nodetool compactionstats
~~~

Some versions also provide `nodetool toppartitions` for sampling hot partitions; `sstablemetadata`/`sstablepartitions` inspect data and partition characteristics **at the SSTable level** when run under proper procedures and permissions. These tools can induce I/O or require version-specific file formats; **never run full-disk scans while measuring load** and treat the run as noise-free.

`nodetool tablehistograms` reports estimated distributions of partition size, cell count, SSTables per read, and latency; do not treat **approximate** percentiles as byte-exact numbers. Combine them with generator histograms and sampled CQL verification.

### 15.3. `CompressionRatio` Alone Cannot Predict Storage Capacity

A table with a great compression ratio can still suffer heavy tombstones or compaction work. Measure **all** of:

~~~text
payload bytes generated
logical live cells / rows estimated
SSTables live disk bytes
total disk bytes including obsolete SSTables
snapshot disk bytes / backup overhead
commitlog volume & flush counts
compression ratio
read p99, SSTables per read, tombstones scanned
~~~

If snapshots or incremental backups are enabled, actual disk usage diverges from table `LiveDiskSpaceUsed`; document the backup policy in the manifest. Never take a compression ratio measured on 1,000 identical rows to forecast hundreds of GB of varied-entropy payloads.

### 15.4. Measuring Tail Latency Without Hiding Errors

Report:

- p50/p95/p99/p99.9 latency **of successful requests**.
- Error/timeout rates and time-to-failure **separately**, rather than dropping exceptions from histograms and boasting about low p99.
- Offered vs. achieved throughput to spot **closed-loop throttling** when the cluster slows.
- Per-operation/class p99: latest-read, range-read, insert, update, delete, and LWT differ.
- Replica/coordinator reroutes, hotset skew, and disk queues.
- Rolling windows aligned to fault injection `t0–t6`, not a 30-minute average hiding a 5-minute outage.

## 16. Validation Gates: If the Dataset Is Wrong, the Run Is Invalid

### 16.1. Data Fidelity Acceptance

Set thresholds **before the run**, scaled to sample size and histogram granularity. Illustrative lab gates for discussion:

| Metric | Hypothetical Target | Illustrative Gate |
|---|---:|---|
| Distinct devices generated | 200,000 | Verified against manifest if all devices prefilled |
| Event rows | 1,000,000 | Successful inserts/verification close to target |
| Payload bucket 128–512 B | 55% | Within 53–57% |
| Payload bucket 1–4 KiB | 35% | Within 33–37% |
| Payload bucket 8–32 KiB | 10% | Within 9–11% |
| Hot 1% devices request share | 40% | Within 38–42% |
| TTL none/7d/30d at write time | 20/60/20% | Each bucket within ±2 percentage points |
| Read/Insert/Update/Delete requests | 55/25/15/5% | Within sample-size-appropriate tolerance |
| UPDATE targets are live rows | Near 100% for this profile | Measure real hit ratio; report all misses |
| Rows/partition p99/max | Per locked histogram | Within agreed tolerance; not a single mean |
| Disk compression and compaction | Measured, not guessed | Baseline/comparison logged per hardware & strategy |

These gates **are not universal Cassandra standards**. With only 100 requests, you cannot expect a 5% bucket to match within 1% error as it would over 10 million operations. If a profile requires **all** 200,000 devices to have events, purely random device ID selection might **fail that requirement** even with 1 million events; pre-assign at least one event per device first before applying skew.

### 16.2. Temporal Distributions Must Be Verified

Check across **actual phases and timestamps**:

~~~text
event_time distribution           : business days/hours
write_arrival_time distribution   : when requests actually executed
TTL_seconds_at_write             : no TTL, 7d, 30d per mix
remaining_TTL_at_baseline         : actual remaining TTL distribution
expired/deleted cell cohorts      : real tombstone age
update_age_delta                 : time from insert to update
read_age_delta                   : time from write to read
~~~

If the generator merely sets `event_time` in the past while every `remaining_TTL_at_baseline ≈ 7 days`, it is **not a TTL-aged dataset**. Fault tests may still be valid for a **fresh-data profile**, but must not be labeled "aged 30d TTL realism".

### 16.3. Run Results Must Be Auditable

Store as a manifest/summary **in the benchmark system outside this lesson**:

~~~yaml
run_id: "example-20261121-a"
profile_hash: "<checksum of approved profile>"
seed: 20261121
schema_version: "events_by_device_day-v1"
cassandra_version: "record-actual-version"
driver_version: "record-actual-version"
topology: "record-node-count-dc-rf-cl"
compaction: "record-actual"
compression: "record-actual"
warmup: "record-duration-and-traffic"
fault: "record-type-window-target-node"
fidelity_checks: "PASS-or-FAIL-with-reasons"
metrics_artifact: "path-to-run-report"
~~~

**Never** mark `PASS` in a report without running the validator. If a fidelity gate fails, the run still has value under an **accurate alternative label** (e.g., "uniform microbenchmark"), but must not be published as a "representative workload benchmark".

### 16.4. Separating Workload Drift from Fault Effects

When p99 rises during a fault phase, compare simultaneously:

1. Offered QPS and operation mix: did they stay constant?
2. Hot-key share: did traffic shift to different keys?
3. Payload-size distribution: did >p99 payloads spike during the fault?
4. TTL/expired cohorts: did a scheduled expiration burst coincide?
5. Compaction/repair: did backlog grow from earlier traffic or from the fault?
6. Replica availability/coordinators: does the impact truly align with the injected fault?

If target rate doubles at the exact moment the hotset shifts, you cannot attribute **all** latency changes to stopping a node. Repeat single-variable runs before testing combined factors.

## 17. Practice Lab: Comparing Three Datasets with the Same Row Count

### 17.1. Lab Preparation

Use a **lab cluster** and the schema in section 4. Prepare three datasets with the **same total logical rows** but different distributions; use isolated lab keyspaces/tables or restore valid starting snapshots between runs. Never copy production data.

| Dataset | Size | Partition Access | TTL/Updates | Purpose |
|---|---|---|---|---|
| **A — Uniform fresh** | 100% 1 KiB payloads | Uniform, skinny | No TTL, mostly INSERT | Control / microbenchmark |
| **B — Representative** | 55/35/10 mix per profile | Top 1% devices get ~40% requests | 20/60/20 TTL mix; 15% UPDATE, 5% DELETE | Fidelity comparison |
| **C — Adversarial** | 10% very large + pronounced long tail | Tighter hotset, wider partitions | Burst TTL expirations, heavy updates/deletes | Find limits near worst-case |

**Do not** change five variables simultaneously and claim one specific variable caused the effect. Dataset C is a composite "stress boundary" test; to isolate root causes, run smaller A/B comparisons varying **one factor at a time**: size, hotset, TTL, or update ratio.

### 17.2. Establishing a Quantified Baseline

1. Check `nodetool status`, version, keyspace RF, and local DC.
2. Create the section 4 schema on an appropriate lab; inspect `DESCRIBE KEYSPACE load_lab` to verify CQL.
3. Create a manifest and fixed seed.
4. Prefill data matching target row counts and distributions; do not mark PASS until histograms are verified.
5. If the profile requires aged TTLs, execute a real-time aging phase or a clearly labeled short-TTL lab phase.
6. Run warm-up with the same arrival pattern, then capture baseline long enough for statistically meaningful tail latency.
7. Save per-node metrics, offered/achieved rates, op mix, errors, p95/p99, and compression/disk stats.

**Never** run a SELECT 10 times and publish p99 as a benchmark. Sample sizes must be large enough, duration and workload stable, and latency reported with clear error/timeout coverage.

### 17.3. Testing a Hotset at Nearly Constant QPS and Data Bytes

Keep payload distribution, TTL, and op mix identical; change only partition visitation:

~~~text
Run U: 200,000 devices selected uniformly
Run H: top 2,000 devices receive 40% of visits

Keep offered QPS, CL, page size, driver timeouts,
client concurrency, and phase duration identical.
~~~

Record:

| Metric | Run U | Run H | Meaning |
|---|---|---|---|
| Offered/achieved ops/s | _fill in_ | _fill in_ | Did the client sustain the target? |
| p95/p99 latest-read | _fill in_ | _fill in_ | Hot partition impact |
| p95/p99 update | _fill in_ | _fill in_ | Contention on hot keys |
| Errors/timeouts | _fill in_ | _fill in_ | SLO and tail health |
| Top 1% key request share | _fill in_ | _fill in_ | Validate actual skew |
| Per-node CPU/IO/queue | _fill in_ | _fill in_ | Replica-set hotspots |
| SSTables/read & tombstone scans | _fill in_ | _fill in_ | Separate scan cost from skew |

If p99 barely changes, the cluster may still have ample headroom, hot keys may not overlap on the same replica sets, or offered load may be too low. **Never** rush to conclude "Cassandra is immune to hot partitions" from a single run.

### 17.4. Testing TTLs and UPDATEs Under Control

Run three scenarios with the same prefill size:

- **T0:** 0% TTL + 0% UPDATE/DELETE, append-only new data.
- **T1:** TTL mix without updates, letting cohorts approach expiration.
- **T2:** TTL mix + 15% UPDATE + 5% DELETE, including updates to existing rows and expired TTL cohorts.

These ratios do not need to match production; the purpose is **isolating effects**. Measure p99, SSTables/read, tombstones scanned, pending compactions, live/total disk size, write bytes, and read hit rate per phase.

### 17.5. Testing Node Failure After the Profile Passes Gates

In an RF3/`LOCAL_QUORUM` lab cluster:

1. Run baseline B and record configuration/metrics.
2. Inject **one selected node Down** for a fixed window with a recovery runbook ready.
3. Keep the target arrival rate and profile B, without **forcing unbounded client retries** while the node is Down.
4. Measure unavailable/timeouts, p99, offered vs. completed ops, and coordinator distribution.
5. Restore the node, monitor hints/repair/compaction, and track time to SLO stabilization.
6. Audit a sample of inserted/updated/deleted rows and timed-out operations against the ledger.
7. Repeat with profile A to observe how **dataset realism alters fault-test outcomes**.

If you lack permission to inject faults on an isolated cluster, **never run them on production**. You can still complete the distribution, TTL, and sizing exercises on a single-node lab; mark fault tests **`NOT_EXECUTED`** rather than fabricating results.

## 18. Common Mistakes and Applied Questions

### 18.1. Anti-Patterns Table

| Mistake | Consequence | Fix |
|---|---|---|
| Specifying total rows only, ignoring partition histogram | Misses wide partitions | Design rows/partition and max explicitly |
| Random UUID per read | Mostly misses, falsely "fast" benchmark | Key catalog matching loaded data |
| Uniform across all keys | Hides hot partitions/replica skew | Hot/cold, Zipf-like, bursts |
| All-zero/`A` payloads | Unrealistically high compression | Mix entropy and measure real disk usage |
| All-random-byte payloads | Hides JSON serialization and real compression | Match application encoding/distribution |
| INSERTs only; UPDATEs miss existing keys | No real churn/version history | Update from existing-key catalog |
| Old `event_time` = aged TTL | Wrong: TTL starts at write time | Soak/aged fixtures/labeled short-TTL labs |
| TTL expired = immediate free disk | Tombstones/grace/compaction take time | Measure live/total disk and pending compaction |
| Updating all columns when app updates status only | Unrepresentative I/O, tombstones, TTL resets | Simulate accurate partial mutations |
| Ignoring CANCEL/timeouts/unknown writes | Inflated success counts and corrupted data | Ledger, reconciliation, error breakdown |
| `truncate=once` outside an isolated environment | Risk of unintended data loss | Only run destructive commands on verified labs |
| Triggering manual GC/major compaction between runs | Destroys SSTable history comparability | Keep starting state identical; log all interventions |
| Measuring one minute right after prefill | No TTL aging or steady state | Target-driven warm-up and soak phases |
| Looking only at successful client p99 | Hides timeouts and overload | Report error rates and offered vs. achieved |
| Using single-node RF1 to claim node-Down tolerance | Replication never tested | Proper multi-node RF3/CL |
| Changing QPS, payload, hotset, and fault at once | Root cause unknown | Single-variable A/B tests first |

### 18.2. Exercise 1 — Two Workloads with Identical Row Counts

Two tables both contain 1 million rows. Table X has 1 row/partition; Table Y has 10,000 rows/partition. The team concludes both tables have equivalent load capacity. Is that right?

**Answer:** No. Token distribution, partition indexes, clustering ranges, tombstones, and paging differ substantially; you need size/rows-per-partition histograms and matching query patterns.

### 18.3. Exercise 2 — 1 KiB of Repeated `A`s

A 10-million-row dataset where every payload is 1 KiB of `'A'` achieves an impressive compression ratio. What must be evaluated before using this for production sizing?

**Answer:** Compare payload entropy/format with real data, and measure SSTable disk usage, wire bytes per row, metadata/replication, and compaction overhead. Equal average payload size does not imply equal cost.

### 18.4. Exercise 3 — Past-Dated TTL

On Nov 21, 2026, you run an INSERT with `event_time='2026-10-01'` and `USING TTL 604800`. Is the row "long expired"?

**Answer:** No. TTL is computed from when the mutation is written, not from `event_time`. Age must be simulated via real elapsed time, pre-aged fixtures, or labeled short-TTL lab runs.

### 18.5. Exercise 4 — UPDATE Hitting the Wrong Targets

A test targets 15% UPDATEs, but each UPDATE calls `UUID.randomUUID()` and sets `status`. Why does row count surge?

**Answer:** Cassandra UPDATE is an upsert; random UUIDs usually do not exist. Use an existing-key catalog and measure the update-target-exists share against live data.

### 18.6. Exercise 5 — Top 1% Keys

The top 1% of keys receive 40% of requests. Does that mean 40% of disk capacity resides in those keys?

**Answer:** No. Request heat differs from storage size; measure bytes/partition and requests/partition separately. Small keys can still be hot.

### 18.7. Exercise 6 — TTL Expired but Disk Usage Does Not Drop

After 50% of rows pass their TTL, disk usage has not fallen proportionally. Is TTL broken?

**Answer:** Not necessarily. Expired data becomes tombstones; compaction reclaims space only when safety conditions and SSTable layouts allow. Check live reads, `TTL()` samples, tombstone metrics, repaired/unrepaired SSTables, and compaction status.

### 18.8. Exercise 7 — Read-Miss Benchmark

A generator prefills 100,000 UUIDs, while the read sampler draws randomly from an unrelated 128-bit space. Why is read throughput high yet untrustworthy?

**Answer:** Nearly all reads are misses, failing to represent latest-N/range/hit application reads. Use keys matching the dataset and telemetry-driven hit/miss mixes.

### 18.9. Exercise 8 — Single-Replica Failure

A 3-node RF3 cluster at `LOCAL_QUORUM` has one node Down. Why can clients still receive timeouts even though two nodes are Up?

**Answer:** The remaining replicas may be slow or overloaded, coordinator membership/connections may still be settling, or network/GC/compaction pressure may interfere. Quorum arithmetic does not guarantee zero errors or flat latency; measure actuals and recovery.

### 18.10. Exercise 9 — Faulty p99 Analysis

After a fault, p99 of successful requests drops from 90 ms to 70 ms while timeout rate climbs from 0% to 20%. Can you conclude the fault made the system faster?

**Answer:** No. The p99 histogram only reflects successful requests; slow requests timed out and were excluded. Always evaluate error rate, time-to-error, offered vs. achieved throughput, and end-to-end SLOs.

### 18.11. Exercise 10 — Reproducible Yet Wrong Data

Two runs share the same seed and produce very similar p99s; however, the generated dataset has zero partitions with >20 rows, while the profile required `p99=1,000 rows/partition`. Does the run pass the fidelity gate?

**Answer:** No. Reproducibility of *an invalid dataset* does not make it representative. Allocate rows according to the partition histogram and validate before load/fault testing.

### Checklist Before Publishing a Benchmark

- [ ] Manifest/version/seed and permitted data scope documented.
- [ ] Logical payload, serialized CQL bytes, partition size, and physical disk distinguished.
- [ ] p50/p95/p99/max rows/partition and bytes/partition measured, not just total rows.
- [ ] Hot keys/skew included, querying the true partition/keyspace/bucket structure.
- [ ] Payloads cover realistic size and entropy distributions with verified compression ratio.
- [ ] TTL cohorts reflect **actual write time/age**, not merely `event_time`.
- [ ] Expired/tombstone cohorts and compaction history match the test objective.
- [ ] Updates/deletes target existing keys at measurable ratios.
- [ ] LWTs, counter/list appends, and standard upserts are not lumped into one "UPDATE" bucket.
- [ ] Read misses/hits/ranges/latest-N, rows/op, pages/op, and query recency modeled accurately.
- [ ] Prefill, aging, warm-up, and baseline captured **before** fault injection.
- [ ] Fault injection performed only on approved labs with defined windows, rollback, and stop conditions.
- [ ] Driver retries/speculative executions counted against actual offered load.
- [ ] p95/p99 reported **alongside** error rates, unknown outcomes, and offered/achieved QPS.
- [ ] Cassandra node/table metrics collected: tombstones, partition histograms, compaction, disk.
- [ ] Validation gate compares **actual** data/workload against the manifest before drawing conclusions.
- [ ] Baseline and fault compared under identical workloads and starting states, or differences explicitly stated.
- [ ] Never mark PASS or report benchmark figures without actually executing the run.

## 19. References

1. Apache Cassandra — [Cassandra Stress](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html): user mode, YAML profiles, column distributions, query weights, and running workloads.
2. Apache Cassandra — [Evaluating and refining data models](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_refining.html): calculating partition cells/bytes and evaluating wide partitions.
3. Apache Cassandra — [Data modeling introduction](https://cassandra.apache.org/doc/3.11/cassandra/data_modeling/intro.html): historical guidance on partition size/cell count; verify against your release and workload.
4. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): tombstones, TTL, grace period, and distributed deletion logic.
5. Apache Cassandra — [Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): TTLs, compaction, repaired/unrepaired SSTables.
6. Apache Cassandra — [TWCS](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/twcs.html): TTL/time-series workloads, out-of-order writes, and window-expiry issues.
7. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): `EstimatedPartitionSizeHistogram`, `TombstoneScannedHistogram`, `SSTablesPerReadHistogram`, compaction/disk metrics.
8. Apache Cassandra — [nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) and [Use nodetool](https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/use_nodetool.html): measuring partition/read histograms and table health.
9. Apache Cassandra — [sstablemetadata](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablemetadata.html) and [sstablepartitions](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablepartitions.html): SSTable-level data and partition statistics when used under proper procedures.
10. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): prepared/bound statements, bind markers, and immutable execution options.
11. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/) and [Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): page size/consumption, retry safety, and TTL operations.
12. Apache Cassandra — [CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) and [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): partition keys, clustering, TTL, UPDATE/upsert, DELETE/LWT.
13. Oracle Java 17 — [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): PRNG seeds, splitting, and `nextBytes` for fixture generation.
