# Simulating Hot Keys, Wide Partitions, or Heavy Tombstones in Apache Cassandra

## 1. Goal: Generate Controlled Load to Isolate the True Root Cause

Apache Cassandra is a distributed **wide-column** database. Data is located via the **partition key**, replicated per the **replication factor (RF)**, and read/written with a **consistency level (CL)**. Query speed depends on query-driven table design, partition size, replica health, SSTables, compaction, repair, networking, and how the Java application submits requests.

In the **Load and Distributed Fault Testing** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, three workload patterns are frequently confused:

- **Hot partition key:** one or a tiny set of partition keys receives most requests. The partition itself may be very **small**, yet QPS is disproportionately high.
- **Wide/large partition:** a partition holds excessive clustering rows/cells or large data volume. The partition may be read infrequently, yet every read consumes heavy I/O, memory, or time.
- **Heavy tombstones:** the read path must traverse large numbers of deletion markers or expired TTL values before finding enough live data. The partition need not have many live rows.

All three conditions can occur **simultaneously**, yet must be simulated separately to isolate causes. For instance, a partition receiving 80% of traffic while holding millions of events and undergoing constant deletes will be slow for multiple reasons; raising timeouts or page sizes before identifying the dominant factor makes evaluating any fix very difficult.

### Expected Outcomes

After this lesson, you will be able to:

1. Create a keyspace and three test tables isolating each load pattern.
2. Run uniform traffic followed by skewed traffic toward one partition key, measuring latency and QPS per key and replica.
3. Grow row counts and byte volume in a partition incrementally under control, observing sizing and read behavior.
4. Generate tombstones via `DELETE`/TTL and inspect read amplification and warnings.
5. Use Java Driver 4.x to issue asynchronous queries with **bounded in-flight concurrency** rather than uncontrolled load.
6. Read p50/p95/p99, successful throughput, timeouts, compaction, GC, and tombstone scan metrics.
7. Validate remediation approaches: **time bucketing**, **controlled sharding**, retention tuning, and query-pattern adjustments.
8. Write reproducible before/after reports and distinguish single-node lab limits from an RF=3 cluster.

## 2. Safety Rules Before Simulating Incidents

**Run these experiments strictly on an isolated lab/staging Cassandra cluster with synthetic data.** This lesson provides CQL and bounded load code for testing purposes; never run it directly against production clusters or real-data keyspaces.

Before running:

- Lock down **endpoints, cluster name, keyspace, and access permissions**. Never use a production superuser role.
- Document node count, datacenter name, Cassandra Server and Java Driver versions, RF/CL, disk quotas, and background jobs.
- Set **hard upper bounds**: partition count, rows/partition, payload bytes, request count, duration, in-flight limit, submission rate, and maximum allowed error rate.
- Define stop conditions: low free disk, surging dropped messages, p99/timeout breaches, prolonged GC, or degraded node health.
- Never disable compaction/repair, drop `gc_grace_seconds`, or raise tombstone thresholds just to "make the test pass".
- Never run heavy data generation alongside backups, repairs, bootstraps, or other tests on a shared cluster.
- When simulating node DOWN, network loss, or slow disks, use a **dedicated multi-node testbed** with a clear recovery plan.

### Suggested Exploratory Lab Load Levels

The levels below are **starting examples for measurement**, not Cassandra configuration rules:

| Test Axis | Low | Moderate | Gated High |
|---|---:|---:|---:|
| Test request count | 200 | 1,000 | 5,000 |
| In-flight requests | 4 | 16 | 32 |
| Share of requests to one hot key | 1–5% | 40% | 80% |
| Rows/partition | 100 | 2,000 | 10,000 |
| `payload` size | 128 B | 512 B | 1 KiB |
| Deleted row share in partition | 0% | 50% | 90% |

Do not blindly apply "high" levels if a container or CI runner has limited RAM or disk. When varying one parameter, keep all others **constant**; e.g., when comparing 5% vs. 80% hot-key skew, do not simultaneously alter RF, CQL, heap, or row size.

## 3. Distinguishing Hot Keys, Wide Partitions, and Tombstones

| Characteristic | Hot Key | Wide Partition | Heavy Tombstones |
|---|---|---|---|
| Core problem | **QPS concentrated** on one partition / replica set | **Many rows/cells/bytes** inside one partition | **Deletion markers / expired TTLs** on the read path |
| Requires many live rows? | No | Typically many cells/bytes | No; live rows can be few |
| Can occur under low traffic? | Rarely meaningful as "hot" at low QPS | Yes | Yes |
| Typical symptoms | Hot-token replicas busy, p99 climbs on one key | p99 grows with partition/fetch size, high read bytes | Reads scan many tombstones, tombstone warnings, even tiny `LIMIT` is slow |
| Does changing page size fix root cause? | No | Only paces fetches; does not shrink wide partitions | No |
| Remediation direction | Distribute load via partitions/shards, proper caching/bulkheads | Time-bucket data, bound retention, query-driven partitioning | Curb delete/TTL anti-patterns, bucket/TWCS where appropriate, proper repair/compaction |
| What to monitor | Per-key traffic, token replicas, queues, p99 | Partition bytes/rows, SSTables, fetch latency | Tombstones scanned, SSTables, compaction, GC |

### 3.1. A Tiny Row Can Still Be a "Hot Key"

If `account_id = A` is read 10,000 times/second, the replicas owning partition A must serve most of that load. Cassandra does not split rows sharing a partition key across multiple tokens just because a partition gets hot. A token-aware driver picks an owning replica, yet **a partition's replica set remains bounded by RF and topology**.

### 3.2. A Large Partition Does Not Mean Every Query Reads All of It

A partition with 100,000 clustering rows queried by a tight clustering range behaves far better than a query scanning the entire partition. Even so, large partitions still threaten compaction, streaming, repair, caches, and unbounded reads—always measure the real workload.

### 3.3. A Tombstone Is Not "A Deleted Row Kept Around Like a Live Row"

Cassandra uses **tombstones** to represent deletions and expired TTLs in a distributed system and prevent deleted data from resurrecting when replicas converge. Tombstones have a lifecycle governed by compaction, SSTable overlap, `gc_grace_seconds`, repair, and server version. They are **not erased from all replicas immediately after a `DELETE` statement**.

## 4. Setting Up an Isolated Cluster and Schema

Commands in this section target keyspace `load_it` on a test cluster with datacenter `datacenter1`.

### 4.1. Keyspace for a Single-Node Lab

```sql
CREATE KEYSPACE IF NOT EXISTS load_it
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 1
}
AND durable_writes = true;
```

If your testbed uses RF=3 in DC `dc1`, create the keyspace to match that cluster instead of copying `datacenter1: 1`. To verify the DC of the connected node:

```sql
SELECT data_center, release_version
FROM system.local;
```

**A single RF=1 node cannot validate RF=3 quorum or failover**, even if you set `CL=LOCAL_QUORUM`: quorum at RF=1 needs only one replica. Measuring slow or disconnected replicas requires a multi-node cluster and separate tests.

### 4.2. Unbucketed Table: For Simulating Hot and Wide Partitions

```sql
CREATE TABLE IF NOT EXISTS load_it.events_unbucketed (
    device_id uuid,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_ts, event_id)
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

In this table:

- `device_id` is the **sole partition key**.
- `event_ts` and `event_id` are clustering columns.
- All events for the same `device_id` belong to **one logical partition**, no matter how many rows accumulate.
- You can query recent events by `device_id`; retaining history forever lets the partition grow unboundedly.
- `event_id` prevents two events with identical timestamps from overwriting each other.

Small read query:

```sql
SELECT event_ts, event_id, payload
FROM load_it.events_unbucketed
WHERE device_id = ?
LIMIT 10;
```

**Never equate** `LIMIT 10` with the cost of reading only 10 physical cells. If 10 live rows sit behind thousands of tombstones, Cassandra may traverse thousands of deletion markers just to return 10 rows.

### 4.3. Bucketed and Sharded Table to Test Remediation

```sql
CREATE TABLE IF NOT EXISTS load_it.events_bucketed (
    device_id uuid,
    event_day date,
    shard int,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (device_id, event_day, shard),
        event_ts,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

This is an **experimental model**:

- `event_day` slices history by UTC day (or a published convention).
- `shard` spreads one device's same-day traffic across multiple partitions.
- `event_ts`/`event_id` preserve ordering **within each shard**, not globally across shards.
- Querying a device's "latest 20 events" requires knowing the target day bucket(s), querying the necessary shards, and **merging results in the application** with bounded fan-out.

Do not blindly choose 8 shards for every workload. Shard count should reflect real QPS/bytes, RF, replica load, read volume, and merge overhead.

### 4.4. Dedicated Table for Tombstone Testing

```sql
CREATE TABLE IF NOT EXISTS load_it.events_delete_heavy (
    device_id uuid,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_ts, event_id)
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

Keep this table separate so `DELETE` statements do not pollute hot-key and wide-partition runs. Never run on production tables and never lower `gc_grace_seconds` solely to make tombstones disappear faster.

### 4.5. Schema Verification Gate

In Java Driver 4.x, after executing DDL:

```java
if (!session.checkSchemaAgreement()) {
    throw new IllegalStateException("Schema agreement not reached");
}

session.refreshSchema();

boolean ready = session.getMetadata()
    .getKeyspace("load_it")
    .flatMap(k -> k.getTable("events_unbucketed"))
    .isPresent();

if (!ready) {
    throw new IllegalStateException("Test table missing from metadata");
}
```

`session` is a connected `CqlSession`. In multi-node clusters, use **bounded polling** for schema agreement rather than failing on the first check; avoid unbounded `Thread.sleep`. Checking table presence alone **does not prove primary keys or table options match expectations**—verify the full structure or run an appropriate migration/test check.

## 5. Simulation 1 — Hot Partition Key

### 5.1. Hold Row Counts Equal, Vary Only Request Distribution

To isolate "hot" from "wide":

1. Seed **64 device IDs**, each with **roughly the same 20 events** and identical payload sizes.
2. Designate one device `HOT_DEVICE`, giving it **no more rows** than any other device.
3. Run baseline: select devices nearly uniformly.
4. Run hot scenario: target **80% of queries** at `HOT_DEVICE`, spreading the remaining 20% across the others.
5. Keep CQL, CL, page size, timeouts, in-flight cap, request count, and duration identical.
6. Collect overall latency and **split metrics by hot key vs. cold keys**.

If the hot scenario runs slower, you have evidence pointing to **traffic skew**, rather than wide partitions or tombstones, since all device fixtures have identical size.

### 5.2. Concrete Probability Distribution

With 2,000 read requests and `hotRatio = 0.80`:

\[
E[\text{reads hitting hot key}]=2000\times0.80=1600
\]

Roughly 400 reads spread across the remaining IDs. Exact counts fluctuate with random sampling. Use a **fixed RNG seed** to reproduce the sequence, while recognizing a fixed seed alone cannot reproduce network or GC jitter.

**With RF=3:** a single hot partition is owned by one replica group per token/topology. Routing through multiple coordinators does not spread that partition's storage across all cluster nodes. In a 12-node cluster, you may observe the owning replicas of that hot token running far busier than other nodes.

### 5.3. Distinguish Hot *Partition* from Hot *Coordinator*

A client without token-aware routing or with skewed contact points/load balancing can overload one coordinator even when partition keys are uniform. When investigating, ask:

- Is traffic **actually concentrated by partition key**?
- Is the overloaded coordinator even a replica for those partitions?
- Are driver token-aware policy, local DC, pools/connections, and node health configured properly?
- Are retries/speculative executions multiplying attempts on the same operation?

**Never diagnose a hot partition solely from high CPU on one node.** Compaction, GC, skewed coordinator routing, disk stalls, streaming, or query fan-out can look identical at a glance.

### 5.4. Expected Observations, Not Mandatory Thresholds

As skew grows, replicas owning the hot partition may show higher latency, pending tasks, and CPU while peers retain headroom. However, if total QPS is modest or caches absorb reads effectively, p99 may **not rise yet**. That is a valid observation: step load up within gates or note it was not triggered at the tested rate—**never force the cluster to crash**.

## 6. Simulation 2 — Wide / Large Partition

### 6.1. Grow Partition Size Step by Step

Use a fresh `device_id` separate from the hot-device fixture. In `events_unbucketed`, load incrementally:

| Milestone | Total Rows in Partition | Example Payload/Row | Approximate Raw Payload |
|---|---:|---:|---:|
| A | 100 | 512 B | 50 KiB |
| B | 2,000 | 512 B | 0.98 MiB |
| C | 10,000 | 512 B | 4.88 MiB |
| D — only with headroom | 50,000 | 512 B | 24.4 MiB |

Actual **on-disk and in-memory sizes differ** from raw multiplication due to clustering keys, metadata, encoding, SSTable compression, indexes, tombstones, and storage overhead. These figures set testing gates, **not measured outputs**.

Reads to compare:

```sql
-- Read only a few latest events.
SELECT event_ts, event_id
FROM load_it.events_unbucketed
WHERE device_id = ?
LIMIT 20;

-- Read a clustering key range (time bound must be supplied).
SELECT event_ts, event_id, payload
FROM load_it.events_unbucketed
WHERE device_id = ?
  AND event_ts >= ?
LIMIT 100;
```

Depending on clustering order and time ranges, the two queries traverse different read scopes. Never turn a benchmark into an unbounded `SELECT *` materialized into a Java `List`.

### 6.2. Observe That Page Size Differs from `LIMIT`

In Java:

```java
BoundStatement query = selectRange.bind(deviceId, startTime)
    .setPageSize(100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);
```

`setPageSize(100)` controls the **target rows per CQL protocol page**, **not** total rows scanned. `LIMIT 100` caps total rows returned per CQL semantics. Smaller page sizes curb memory spikes at the expense of extra network round trips, without changing the partition key.

### 6.3. Measure Two Read Modes

- **Point/range read:** `LIMIT 10/20/100` with partition key and appropriate clustering bounds; measure p99, bytes/query, and SSTables read.
- **Bounded full logical traversal:** page through a fixed number of pages, tracking actual rows and bytes processed; **never** load all 50,000 rows into RAM unnecessarily.

If point reads remain fast while paging, compaction, or repair slows down, state explicitly which workload suffers. Never claim a wide partition makes "every query slow" based solely on partition length.

### 6.4. Never Use `COUNT(*)` as a Routine Health Check

```sql
-- Do not use as a periodic health probe on very wide partitions:
SELECT COUNT(*)
FROM load_it.events_unbucketed
WHERE device_id = ?;
```

Counting can scan huge volumes and create unnecessary load. Rely on dataset manifests, seeded row counts, metadata/table histograms, and controlled checks instead of running `COUNT` every second.

## 7. Simulation 3 — Heavy Tombstones on the Read Path

### 7.1. Prepare a Partition with Live Rows

Use `events_delete_heavy` with a dedicated `device_id`. Seed e.g. 2,000 rows with ascending timestamps from a fixed epoch:

```sql
INSERT INTO load_it.events_delete_heavy (
    device_id, event_ts, event_id, payload
) VALUES (?, ?, ?, ?);
```

After verifying the rows are readable, delete the **1,800 newest rows** using a CQL `DELETE` with the full primary key:

```sql
DELETE FROM load_it.events_delete_heavy
WHERE device_id = ?
  AND event_ts = ?
  AND event_id = ?;
```

Because clustering order is `event_ts DESC`, the query below must step past many deleted entries before reaching older live rows:

```sql
SELECT event_ts, event_id
FROM load_it.events_delete_heavy
WHERE device_id = ?
LIMIT 10;
```

This simulates a **tombstone-heavy read**. The key signal is how many tombstones must be inspected to return **10 live rows**, not just the returned row count.

**There is no guarantee every `DELETE` produces exactly one independently countable trace tombstone.** Cell vs. range tombstones, memtables/SSTables, compaction, and Cassandra versions all affect representation and reporting.

### 7.2. TTL Variant

Instead of `DELETE`, you can generate TTL-expired data:

```sql
INSERT INTO load_it.events_delete_heavy (
    device_id, event_ts, event_id, payload
) VALUES (?, ?, ?, ?)
USING TTL 5;
```

TTL counts seconds from write time, not from a mocked Java `Instant`. Once expired, data follows tombstone semantics. However:

- Waiting `Thread.sleep(5000)` is flaky due to clock, scheduling, GC, and latency variance.
- Use **deadline-bounded polling** and log real server times; TTL cannot be "frozen" via a mocked Java clock.
- To isolate TTL effects, do not mix `DELETE` and TTL variants on the same partition during baseline measurements.
- Never set `gc_grace_seconds` to 0 to "clean up faster": without complete replication/repairs, deleted data risks resurrecting.

### 7.3. When Do Tombstones Actually Cause Slowdowns?

Tombstones sitting in the queried range and SSTables increase the cells inspected. Severity depends on:

- The clustering key range traversed by the `SELECT`.
- How many tombstones reside in memtables and SSTables.
- Number of SSTables consulted, SSTable overlap, and compaction strategy.
- RF/CL: which replicas respond and how data is reconciled.
- Caches, disk latency, GC, and query concurrency.
- Row size and how many live rows `LIMIT` needs.

**A small `LIMIT` does not automatically skip tombstones.** Likewise, raising timeouts simply lets requests wait longer without removing read amplification.

### 7.4. Meaning of Tombstone Warning and Failure Thresholds

Cassandra includes safeguards limiting excessive tombstone scans, whose names and behavior vary by version—for example, `tombstone_warn_threshold` and `tombstone_failure_threshold` in classic configurations.

When breached, the server logs warnings or aborts queries to protect stability. **Never raise these thresholds just to make a benchmark hit 100% success.** Capture warnings/traces and fix the data model, TTL, delete pattern, or compaction. Newer Cassandra releases may feature different limits and protections; check docs for your running version.

## 8. Bounded Fixture Seeding with Java Driver 4.x

Across scenarios, reuse a single `CqlSession` and prepared statements. Never create a session per insert or per HTTP request.

### 8.1. Helper to Seed One Partition

The example below **can be placed in a test-only fixture class**, targeting JDK 11+ and Java Driver 4.x. It intentionally caps rows and payload size to avoid accidentally creating multi-gigabyte partitions.

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class EventFixture {

    private static final Instant BASE =
        Instant.parse("2025-03-01T00:00:00Z");

    public static void seedUnbucketed(
            CqlSession session, UUID deviceId,
            int rows, int payloadChars) {

        if (rows < 1 || rows > 10_000) {
            throw new IllegalArgumentException(
                "rows must be in [1, 10000]");
        }
        if (payloadChars < 1 || payloadChars > 1024) {
            throw new IllegalArgumentException(
                "payloadChars must be in [1, 1024]");
        }

        PreparedStatement insert = session.prepare(
            "INSERT INTO load_it.events_unbucketed " +
            "(device_id, event_ts, event_id, payload) " +
            "VALUES (?, ?, ?, ?)");

        // Uses ASCII so payloadChars equals UTF-8 byte length here.
        String payload = "x".repeat(payloadChars);

        for (int i = 0; i < rows; i++) {
            UUID eventId = UUID.nameUUIDFromBytes(
                ("event-" + deviceId + "-" + i)
                    .getBytes(StandardCharsets.UTF_8));

            session.execute(insert.bind(
                deviceId,
                BASE.plusMillis(i),
                eventId,
                payload));
        }
    }

    private EventFixture() { }
}
```

**Helper characteristics:**

- `rows <= 10_000` and `payloadChars <= 1024` are learning guardrails, not Cassandra hard limits.
- Seeding 64 devices × 20 rows issues 1,280 inserts; loading 10,000 rows into one device forms a separate wide-partition scenario.
- Timestamps and UUIDs are **deterministic** per device and index.
- ASCII `'x'` keeps byte counting simple; real data uses multi-byte UTF-8 and compresses differently.
- This runs **sequentially**, suited for small fixtures. For large seeding, use bounded async/batch workflows with rate limits—never giant multi-partition batches.
- Target a test keyspace only after verifying the cluster. Never copy this helper into production jobs.

### 8.2. Data for the Hot-Key Test

A clean setup:

```java
UUID hotDevice = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

EventFixture.seedUnbucketed(session, hotDevice, 20, 256);

// Create 63 other device IDs distinct from hotDevice, 20 rows each.
// Pass all 64 IDs into the workload driver below.
```

Keep **identical row counts and payloads** across hot and cold keys. If the hot key holds 10,000 rows while cold keys hold one row, you are no longer isolating hot-key skew.

### 8.3. Reproducible Tombstone Test Seed

Follow the same deterministic timestamp/UUID scheme on `events_delete_heavy`. Example helper logic:

```java
PreparedStatement insert = session.prepare(
    "INSERT INTO load_it.events_delete_heavy " +
    "(device_id, event_ts, event_id, payload) " +
    "VALUES (?, ?, ?, ?)");

PreparedStatement delete = session.prepare(
    "DELETE FROM load_it.events_delete_heavy " +
    "WHERE device_id = ? AND event_ts = ? AND event_id = ?");

UUID deviceId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
Instant base = Instant.parse("2025-03-01T00:00:00Z");

for (int i = 0; i < 2000; i++) {
    UUID id = UUID.nameUUIDFromBytes(
        ("tombstone-" + i).getBytes(
            java.nio.charset.StandardCharsets.UTF_8));

    session.execute(insert.bind(
        deviceId, base.plusMillis(i), id, "payload"));
}

// Delete the 1,800 newest rows in DESC clustering order,
// leaving i=0..199 as 200 live rows.
for (int i = 200; i < 2000; i++) {
    UUID id = UUID.nameUUIDFromBytes(
        ("tombstone-" + i).getBytes(
            java.nio.charset.StandardCharsets.UTF_8));

    session.execute(delete.bind(
        deviceId, base.plusMillis(i), id));
}
```

This fixture is **strictly for test tables**, never a production bulk-delete script. In Cassandra, tombstones can linger across resets and compaction cycles. For a genuinely clean baseline, **recreate an isolated container/schema** per scenario rather than assuming `DELETE` or `TRUNCATE` resets SSTable state identically.

## 9. Java Driver 4.x: A Bounded Load Generator for Hot-Key Scenarios

The code below illustrates a **closed-loop asynchronous workload**. It does not launch all futures at once—it dispatches only while an in-flight permit is available, preventing JVM exhaustion before Cassandra is properly measured.

### 9.1. Measurement Design

- Fixed total requests: 1,000 per run.
- Bounded concurrency: max 16 in-flight.
- 64 device IDs seeded with identical row counts.
- Two runs: `hotRatio = 1.0/64` (near-uniform) and `hotRatio = 0.80` (skewed to one key).
- Identical query and `LOCAL_ONE` for an **RF=1 lab**; on multi-node RF=3 clusters, pick the appropriate CL and hold it constant across runs.
- Collect completed count, successes/errors, throughput, and latency percentiles.
- Do not read/serialize every row inside callbacks; simply verify the first page returned.

### 9.2. Example Load Driver

```java
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class BoundedHotReadLoad {

    private static final int REQUESTS = 1_000;
    private static final int MAX_IN_FLIGHT = 16;

    static void measure(
            CqlSession session,
            PreparedStatement read,
            UUID hotDevice,
            List<UUID> allDevices,
            double hotRatio,
            long randomSeed) throws InterruptedException {

        if (allDevices.isEmpty()
                || !allDevices.contains(hotDevice)
                || hotRatio < 0.0 || hotRatio > 1.0) {
            throw new IllegalArgumentException("Invalid workload setup");
        }

        Semaphore slots = new Semaphore(MAX_IN_FLIGHT);
        CountDownLatch done = new CountDownLatch(REQUESTS);
        List<Long> successfulLatencies =
            Collections.synchronizedList(new ArrayList<>());
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();
        Random random = new Random(randomSeed);
        long wallStart = System.nanoTime();

        for (int i = 0; i < REQUESTS; i++) {
            // Producer-side backpressure.
            slots.acquire();

            UUID target;
            if (random.nextDouble() < hotRatio) {
                target = hotDevice;
            } else {
                target = allDevices.get(
                    random.nextInt(allDevices.size()));
            }

            long started = System.nanoTime();

            try {
                session.executeAsync(
                    read.bind(target)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_ONE)
                        .setPageSize(100)
                        .setTimeout(Duration.ofSeconds(2))
                        .setIdempotent(true)
                ).whenComplete((page, error) -> {
                    try {
                        if (error == null && page != null) {
                            succeeded.incrementAndGet();
                            successfulLatencies.add(
                                System.nanoTime() - started);
                        } else {
                            failed.incrementAndGet();
                        }
                    } finally {
                        slots.release();
                        done.countDown();
                    }
                });
            } catch (RuntimeException error) {
                failed.incrementAndGet();
                slots.release();
                done.countDown();
            }
        }

        if (!done.await(90, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Run exceeded deadline; check remaining in-flight requests");
        }

        double wallSec =
            (System.nanoTime() - wallStart) / 1_000_000_000.0;

        Collections.sort(successfulLatencies);

        System.out.printf(
            "hotRatio=%.2f ok=%d fail=%d goodput=%.1f ops/s%n",
            hotRatio,
            succeeded.get(),
            failed.get(),
            succeeded.get() / wallSec);

        if (!successfulLatencies.isEmpty()) {
            System.out.printf(
                "p50=%.2fms p95=%.2fms p99=%.2fms%n",
                percentileMs(successfulLatencies, 0.50),
                percentileMs(successfulLatencies, 0.95),
                percentileMs(successfulLatencies, 0.99));
        }
    }

    static double percentileMs(List<Long> sortedNs, double q) {
        int index = Math.max(0,
            Math.min(sortedNs.size() - 1,
                (int) Math.ceil(q * sortedNs.size()) - 1));
        return sortedNs.get(index) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        UUID hotDevice = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        // Placeholder: supply 64 seeded IDs with equal row/payload
        // fixtures, including hotDevice.
        List<UUID> devices = loadSeededDeviceIds();
        if (devices.size() != 64) {
            throw new IllegalStateException(
                "Need 64 devices with equivalent fixtures");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement read = session.prepare(
                "SELECT event_ts, event_id " +
                "FROM load_it.events_unbucketed " +
                "WHERE device_id = ? LIMIT 10");

            // Separate warm-up; exclude warm-up samples from measurement.
            // Add an appropriate bounded warm-up helper.
            // warmup(session, read, devices, 200);

            measure(session, read,
                hotDevice, devices, 0.0, 42L);
            measure(session, read,
                hotDevice, devices, 0.80, 42L);
        }
    }

    // DEMO stub — replace with the real seeded fixture ID list.
    static List<UUID> loadSeededDeviceIds() {
        throw new UnsupportedOperationException(
            "Supply seeded IDs before running");
    }
}
```

**Boundaries of this illustrative code:**

1. `loadSeededDeviceIds()` is an **intentional stub**: the program cannot benchmark until you supply the 64 seeded IDs. Never claim this snippet is a complete turnkey executable benchmark.
2. `hotRatio = 0.0` picks uniformly from `allDevices` (including the hot key) → hot-key probability ≈ `1/64`. `hotRatio = 0.80` also occasionally picks the hot key in the 20% branch → actual share is closer to **80.3%** across 64 keys; to hit an exact 80%, exclude the hot key from the cold branch.
3. This is **closed-loop** because the producer waits on `slots.acquire()`. It can mask `coordinated omission` when the server slows. Use bounded open-loop arrival scheduling for production SLO testing.
4. Percentiles cover **successful requests only**. Report **failure/timeout rates separately**, and ideally record failed-request latency histograms so tail stalls aren't hidden.
5. `List<Long>` is bounded only because `REQUESTS = 1,000`; for larger loads, use a bounded histogram rather than retaining millions of boxed longs.
6. Timing starts once a permit is acquired before `executeAsync`, **excluding** time waiting for a producer permit. Measure queue/admission wait separately for end-to-end API SLOs.
7. Keep CPU-heavy work out of driver callbacks. If JSON serialization is needed, dispatch to a separate bounded executor and monitor its queue.
8. For write timeouts, **never** auto-retry without proven idempotency; this example is read-only.
9. **Never run against production.** `127.0.0.1`, DC, and CL are lab parameters to verify.

### 9.3. Why Benchmarks Must Report Both Goodput and Errors

Suppose Run A submits 1,000 reads and 997 succeed; Run B submits 1,000 and 650 succeed. If Run B finishes faster because failures fail fast, throughput by **attempts/s** looks high while actual service degraded. Report:

\[
\mathrm{goodput} =
\frac{\text{successful, data-correct operations}}
     {\text{measurement duration}}
\]

\[
\mathrm{error\ rate} =
\frac{\text{failed operations}}
     {\text{completed operations}}
\]

For write workloads, separate **successful CQL responses** from **business-confirmed state**, especially around `WriteTimeout` and retries.

## 10. Observing the Cluster: Do Not Look Only at Java Output

### 10.1. Read-Only Operational Commands

In the **testbed** with proper permissions:

```bash
# Node status and topology:
nodetool status
nodetool describecluster

# Thread pools and pending work:
nodetool tpstats

# Active compactions:
nodetool compactionstats

# Table stats and histograms:
nodetool tablestats load_it.events_unbucketed
nodetool tablestats load_it.events_delete_heavy
nodetool tablehistograms load_it events_unbucketed
nodetool tablehistograms load_it events_delete_heavy
```

Some subcommand names and stat labels vary by Cassandra version. `tablehistograms`/`tablestats` reflect the **queried node's view** and prior SSTables/compactions; never extrapolate cluster-wide truth from one snapshot on one node.

To check which replicas/tokens own a partition, inspect token-map metadata or run `nodetool getendpoints` per your version's syntax. Only by confirming the **hot partition's replicas** can you verify load landed where expected.

### 10.2. What Needs to Be Measured?

| Group | Metrics / Signals | Purpose |
|---|---|---|
| **Java service** | p50/p95/p99, successes/errors, concurrency, queue wait | What end users actually experience |
| **Java Driver** | Request latency, timeouts, retries/speculation, pools/in-flight | Isolate driver, routing, and retry issues |
| **Cassandra node** | CPU, load, disk I/O, network, GC | Identify saturated nodes/replicas |
| **Read path** | Read latency, SSTables per read, tombstones scanned (where exposed) | Detect read amplification |
| **Write path** | Write latency, memtable/commitlog, dropped messages | Track write load and durability |
| **Partition metrics** | Estimated partition size / cell-count distributions | Spot oversized partitions |
| **Compaction** | Pending/running tasks, bytes processed, disk pressure | Spot SSTable/tombstone impact |
| **Topology** | Node UP/DOWN, replica placement, RF/CL | Interpret distributed outcomes accurately |
| **Test generator** | Offered load, admitted load, queues, drops | Avoid saturating the generator itself |

**p99 without error rates and throughput is incomplete.** Likewise, "high CPU" does not prove a hot key if compaction or GC is running simultaneously.

### 10.3. Be Careful with Partition Size Metrics

Partition sizes are typically estimated from SSTable data/histograms over time; they may exclude freshly written memtable data, other replicas, or exact Java row sizes. Always note **flush/compaction timing**, measurement method, and which node was inspected.

## 11. Tracing and Tombstone Diagnostics

### 11.1. Use Tracing Selectively

In `cqlsh` against the test keyspace:

```sql
TRACING ON;

SELECT event_ts, event_id
FROM load_it.events_delete_heavy
WHERE device_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
LIMIT 10;

TRACING OFF;
```

Depending on Cassandra version, traces/logs show live rows/cells, tombstones scanned, or SSTable read/reconciliation steps. Different releases format trace text differently; **never assert exact trace strings** as a stable API.

Tracing adds overhead and metadata writes, so enable it only for **selected lab queries** during diagnostics—never on full traffic. Inspect server logs and metrics for tombstone warnings during test windows.

### 11.2. Valid Conclusions from a Trace

| Observation | Valid Conclusion | Invalid Conclusion |
|---|---|---|
| Trace shows many tombstones scanned before 10 live rows | This query suffers tombstone read amplification | Every partition in the table has the same issue |
| One page is slow yet tombstone count is low | Another slow path needs investigation | A wide partition is necessarily the cause |
| Tombstone warnings jump after `DELETE` | Delete-heavy load is creating pressure in the test | Raising the threshold is the proper fix |
| SSTable overlap and compaction backlog exist | Inspect compaction and read amplification | Immediate `nodetool compact` safely fixes all cases |
| Query speeds up after compaction | Data layout affected latency | Every production compaction should be forced manually |

**Never run tracing or `SELECT COUNT(*)` continuously on wide partitions** to "be sure"; diagnostics themselves become extra load.

## 12. Controlled Experiments: Isolating One Variable at a Time

### 12.1. Run Matrix

| Run | Dataset | Request Distribution | Delete / TTL | Goal |
|---|---|---|---|---|
| `B0` | 64 partitions × 20 rows | Uniform | None | Baseline |
| `H40` | Same as B0 | 40% to one key | None | Early skew observation |
| `H80` | Same as B0 | 80% to one key | None | Concentrated load |
| `W2K` | Fresh partition with 2,000 rows | Bounded reads | None | Moderate width |
| `W10K` | Same setup, 10,000 rows | Equivalent reads | None | Size impact |
| `T0` | Dedicated 2,000-row partition | Top-10 read | Undeleted | Tombstone baseline |
| `T90` | Dedicated scenario partition | Top-10 read | 90% newest rows deleted | Tombstone-heavy read |
| `R` | Bucketed/sharded model | Same skew/volume as H80/W10K | Controlled policy | Validate remediation |

**Keep runs independent:** reusing the same table or partition between `W10K` and `T90` without resetting leaves prior SSTables, tombstones, and compactions that confound results.

### 12.2. Closed-Loop vs. Open-Loop

- **Closed-loop:** at most `C` concurrent requests; if the server slows, the client slows down too. Good for concurrency-bounded exploration.
- **Open-loop:** emits at a target arrival rate independent of completion speed. Good for exposing queue buildup, admission rejections, and overload SLOs.

In open-loop tests, enforce **bounded queues** and backpressure/drop policies. Letting a producer queue 100,000 unfinished futures tests JVM OOM and retry storms rather than Cassandra.

### 12.3. Warm-Up and Repeatability

A trustworthy run requires:

1. Preloading the fixture and verifying correctness.
2. Sufficient warm-up for JIT, connections, and caches—**excluded from primary metrics**.
3. Driving traffic with recorded arrival rates/concurrency.
4. Collecting results over fixed windows with timeouts/deadlines.
5. Allowing idle/cool-down intervals if compaction or GC still interferes.
6. Repeating runs and alternating scenario order when feasible to counter cache advantage.
7. Recording versions, schemas, token distributions, RF/CL, row bytes, generator hardware, GC, and CPU/disk quotas.

A "clean benchmark" often shifts once data hits caches, flushes, or compacts. Record that operational reality rather than deleting inconvenient data points.

## 13. Choosing the Right Remediation per Root Cause

### 13.1. Hot Partition: Distribute by New Keys, Not Just More Threads

If one device drives high QPS, one option is adding a `shard` to the partition key:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class EventPartitioning {
    public static final int SHARDS = 8;

    public static int shardFor(UUID eventId) {
        return Math.floorMod(eventId.hashCode(), SHARDS);
    }

    public static LocalDate dayUtc(Instant eventTime) {
        return eventTime.atZone(ZoneOffset.UTC).toLocalDate();
    }

    private EventPartitioning() { }
}
```

Write:

```sql
INSERT INTO load_it.events_bucketed (
    device_id, event_day, shard, event_ts, event_id, payload
) VALUES (?, ?, ?, ?, ?, ?);
```

**Trade-offs to pay:**

- To look up one event by `event_id`, the app can compute the shard if the algorithm is versioned, **yet still needs `event_day`** or a lookup table.
- To fetch "the latest 20 events of the day", the app must query **up to 8 shards** and merge by timestamp/event ID.
- More shards increase fan-out, partitions/query, and Java requests; enforce concurrency caps so fan-out doesn't create new overload.
- Never blindly change `SHARDS=8` to 16 later: changing the hash routing strands old events in old shards. Plan versioned routing, dual reads, or migration/backfill.
- Read-heavy hot keys may benefit from **TTL caching with invalidation**, subject to consistency and staleness requirements.
- Write-heavy hot keys require checking LWT contention, monotonic counters, and idempotency semantics.

**Never use random shards** if you need point lookups by ID without an index/routing table; deterministic hash sharding preserves locatability when paired with a compatible read path.

### 13.2. Wide Partition: Time Bucketing and Retention Caps

If a device emits events for years, partitioning by `event_day` or `event_week` bounds rows/partition. Size buckets via:

\[
\mathrm{rows/bucket}\approx \mathrm{write\ rate}\times\mathrm{bucket\ duration}
\]

For example, 2 events/second over one day:

\[
2\times86{,}400=172{,}800\ \mathrm{rows/day}
\]

That **may still be too large** depending on row size and workload; hourly buckets or added shards may fit better. Do not pick "daily" out of habit for high-QPS devices.

When applying bucketing:

- Define how every query supplies `event_day` or time bounds.
- Cap how many buckets a single request may fan out across.
- Compute timestamps and buckets using the **exact same timezone/rules** (use UTC dates for UTC events).
- Account for backfills, late-arriving events, and `DELETE`/TTL behavior.
- Match compaction strategy to write-time/TTL patterns—never treat TWCS as a cure-all for wide partitions.
- If an instant "latest event" lookup is needed, consider a separate `latest_event_by_device` projection table, handling denormalization, idempotency, and consistency.

### 13.3. Tombstone-Heavy: Fix Write/Delete Patterns and Read Paths

Common options to evaluate:

1. **Avoid row-by-row deletes** in large partitions. Use bucketed/partition lifecycles to drop expired retention slices cleanly at the partition level while honoring distributed delete semantics.
2. Review TTLs: mixed TTLs interleave expired cells with live data and make reads expensive.
3. For time-series tables with uniform TTLs, evaluate **TimeWindowCompactionStrategy (TWCS)** per version docs and out-of-order write rates; TWCS **does not** magically solve every tombstone issue.
4. Check repair and compaction health before touching `gc_grace_seconds`; never lower it recklessly due to zombie-data resurrection risks.
5. Adjust queries to read tight clustering bounds rather than scanning across deleted regions whenever possible.
6. Monitor tombstones scanned/read, compaction backlogs, and p99 after every change.
7. If bulk historical purges are required, **redesign partitions around data lifecycles** instead of issuing millions of individual clustering-row `DELETE`s.

**Running `nodetool compact` on production as a "quick tombstone cleanup" is discouraged:** forced major compaction consumes heavy I/O and disk and does not guarantee tombstones are eligible to purge. Any compaction/repair intervention needs a runbook and safety checks.

## 14. Before/After Results: Present Without Swapping Workloads

A **purely hypothetical** example table illustrating reporting format, not real Cassandra measurements:

| Scenario | Goodput (ops/s) | p50 | p95 | p99 | Error % | Tombstones/Read |
|---|---:|---:|---:|---:|---:|---|
| Baseline `B0` | 800 | 8 ms | 20 ms | 35 ms | 0.0% | Low |
| Hot `H80` | 770 | 12 ms | 55 ms | 140 ms | 0.2% | Low |
| Wide `W10K`, range read | 650 | 20 ms | 85 ms | 210 ms | 0.5% | Low |
| Tombstone `T90` | 480 | 34 ms | 160 ms | 390 ms | 2.1% | High |
| Bucket/shard `R` | 780 | 10 ms | 29 ms | 60 ms | 0.1% | Query-dependent |

Never declare `R` "best" if queries under `R` only read **one shard** while baseline read **all events**. For a fair comparison, the app must deliver **the exact same business output**, including fan-out and merging, with Java-side overhead included in latency.

### 14.1. When Can You Conclude You Found the Root Cause?

Only when cross-evidence aligns:

- **Hot key:** skewed request distribution + owning token replicas carrying the load + per-key/replica latency shifting with skew.
- **Wide partition:** growing partition size/cell count + query I/O and fetch latency scaling with size or scan span.
- **Tombstone-heavy:** traces/metrics confirm high tombstones scanned + p99 rises reproducibly after controlled deletes/TTLs.
- **Ruling out confounders:** generator network/GC, background compaction/repair, CL/page-size changes, and disconnected nodes excluded.
- **Verified fix:** remediation preserves **identical query semantics**, accounting for real request/byte/fan-out costs rather than one cherry-picked metric.

## 15. Distinguishing Timeout Types Under Load

| Exception / Condition | Meaning | What Not to Infer |
|---|---|---|
| `UnavailableException` | Coordinator lacks enough available replicas to meet CL | Does not mean data is lost |
| `ReadTimeoutException` | Coordinator did not receive enough read responses/data before timeout | Does not mean the partition is absent |
| `WriteTimeoutException` | Write did not receive enough ACKs before timeout | Does not guarantee the mutation failed |
| Driver request timeout | Client received no result before deadline | Unknown whether the server applied the mutation |
| Tombstone-related query failure | Query aborted by tombstone protection limits | Do not "fix" by raising safety thresholds |
| Application deadline exceeded | Full endpoint breached its SLO | Not necessarily a single CQL attempt timeout |

When simulating write or delete loads:

- Never auto-retry every `WriteTimeout`.
- For list appends, counters, or external side effects, replays can duplicate effects.
- Set `setIdempotent(...)` strictly per **operation semantics**, not to chase higher throughput.
- Bound retries with backoff/jitter and preserve a **logical request ID** for reconciliation.
- Never weaken CL just to report fewer errors when production demands stronger consistency.

Especially on hot partitions with LWT contention, raising concurrency can worsen latency without raising business throughput. Separate **contention** from ordinary read/write latency.

## 16. Multi-Node Fault Injection: Scale Out Only After Establishing a Baseline

Hot keys, wide partitions, and tombstones are **workload and data-shape scenarios**, not inherently node failures. To combine them with distributed faults, a multi-node testbed can add:

1. Baseline run at RF=3, `LOCAL_QUORUM`, capturing full health and latency.
2. Controlled hot-key or tombstone-heavy dataset at modest load.
3. Bounded in-flight requests and explicit stop conditions.
4. Slow or isolate **one** partition replica using controlled fault-injection tooling in the lab cluster.
5. Observe `Unavailable` vs. `ReadTimeout` vs. `WriteTimeout`, routing, and replica fallbacks/retries.
6. Restore the node/network, await stabilization, and verify consistency/read-backs at CL.
7. Compare against the same fault under unskewed traffic/data.

### 16.1. What Cannot Be Inferred from a Single RF=1 Node

- Cannot prove RF=3 quorum reads survive one node DOWN.
- Cannot verify anti-entropy repair across replicas.
- Cannot simulate cross-DC latency or `EACH_QUORUM`.
- Cannot extrapolate production compaction/streaming speed from a tiny container.
- Cannot exercise real multi-node token-ring coordinator selection.

### 16.2. Never Put Destructive Cluster Commands in Shared Test Runners

Network faults, node stops, and disk throttling require dedicated environments and authorization. Never build an automated "kill Cassandra node" helper accepting arbitrary user-supplied hosts. Every destructive fault injection must be authorized with allowlists, timeouts, and clear cleanup/rollback.

## 17. Practical Runbook

### Phase A — Preparation

1. Pick an isolated test cluster; record Cassandra/Driver versions and topology.
2. Create `load_it` with NTS and RF matching real nodes/DCs.
3. Create `events_unbucketed`, `events_bucketed`, and `events_delete_heavy`.
4. Verify schema agreement/structure; prepare deterministic IDs, timestamps, and payloads.
5. Select metrics: success goodput, p50/p95/p99, error breakdown, in-flight, CPU/GC/disk, tombstones scanned, partition bytes.
6. Set guardrails: max rows, request count, duration, disk floor, p99, timeouts, and abort/teardown hooks.

### Phase B — Hot-Key Scenario

1. Seed 64 partitions × uniform 20 rows and payloads.
2. Warm up with uniform traffic and record baseline.
3. Run `hotRatio = 0.0`, verifying request counts across hot/cold keys.
4. Run `hotRatio = 0.40` and `0.80` at identical QPS and concurrency.
5. Compare per-key/per-replica p99, attempts, CPU, and network/queues.
6. Do not raise total throughput at the same time as changing distribution without a separate control run.

### Phase C — Wide-Partition Scenario

1. Use a fresh `device_id` and clean schema.
2. Seed 100 → 2,000 → 10,000 rows, keeping payload/row constant.
3. Query `LIMIT 20`, then explicitly bounded ranges.
4. Measure partition size/bytes/fetch latency, SSTables, and client memory.
5. Never use full scans / `COUNT(*)` as a repeated health check.
6. Compare against time bucketing, including fan-out costs if applicable.

### Phase D — Tombstone Scenario

1. Use a dedicated table/partition and seed 2,000 live rows.
2. Measure baseline reads with `LIMIT 10`.
3. Delete the 1,800 newest rows via prepared `DELETE` and wait for writes to finish.
4. Re-run the exact query, observing traces, tombstone warnings, and latency.
5. Do not treat an incidental compaction between runs as a controlled variable; log SSTable/compaction state.
6. Test the TTL variant in a separate clean environment rather than mixing with the `DELETE` run.
7. Never lower `gc_grace_seconds` or thresholds to force results.

### Phase E — Analysis and Remediation Testing

1. Identify hot key, wide partition, tombstones, or their combination using evidence.
2. Select **one** data-model, retention, or routing change to test.
3. If bucketing/sharding, update both write and bounded read/merge paths.
4. Re-run the workload **returning the exact same business data** at the same CL.
5. Compare goodput, p99, errors, bytes/query, request fan-out, CPU/disk/compaction.
6. Stop/rollback if total cost or correctness degrades.
7. Archive the report and safely clean up test containers/schemas.

## 18. Practice Exercises and Guided Answers

### Exercise 1 — Classify the Phenomenon

Three partitions:

- A: 20 rows, receiving 5,000 reads/s.
- B: 200,000 rows, receiving 5 reads/s.
- C: 300 live rows, yet scanning thousands of deletion markers to return `LIMIT 10`.

Classify each as hot, wide, or tombstone-heavy, and pick **two metrics** and one remediation direction for each.

**Hints:**

- A: hot key; per-key QPS, replica CPU/queues; shard or cache where business rules permit.
- B: wide partition; partition bytes/rows, SSTables/range latency; time bucketing and retention caps.
- C: tombstone-heavy; tombstones scanned/read, p99/compaction; reduce delete-heavy patterns and partition by data lifecycle.

### Exercise 2 — Hot-Key Distribution

1,500 reads/s with 80% targeting one partition key.

1. How many reads/s hit the hot key in expectation?
2. On a 12-node RF=3 cluster, can you assume those 1,200 reads/s spread evenly across all 12 nodes?
3. Why does adding coordinator threads not add replicas for that partition?
4. How do you verify the app uses token-aware coordinators?

**Hints:** `1500 × 0.8 = 1200` reads/s. A partition has replicas fixed by RF and topology, not all 12 nodes. Check driver routing policies, token/replica maps, and per-node/per-key metrics.

### Exercise 3 — Wide Partitions and Bytes

A device stores 100,000 events averaging 800 B payload/row.

1. Roughly how many MiB is the raw payload?
2. Why does on-disk size differ?
3. Does `setPageSize(100)` split the physical partition into 1,000 partitions?
4. At 2 events/s, roughly how many rows does a daily bucket accumulate?

**Hints:** roughly `76.3 MiB` raw payload before overhead/compression. Page size is a protocol paging setting, not a partition key split. `2 events/s × 86,400 s ≈ 172,800 rows/day`, which may warrant smaller buckets or shards.

### Exercise 4 — `LIMIT` and Tombstones

You seed 2,000 rows, delete the 1,800 newest rows, and query `LIMIT 10` in `DESC` clustering order.

1. Roughly how many deleted positions may the query traverse before collecting live rows?
2. Why does `LIMIT 10` not guarantee a cheap query?
3. Which metrics and logs should you inspect?
4. Should you raise `tombstone_failure_threshold` so the test passes without errors?

**Hints:** it may traverse a large number of tombstones; measure exact scanned counts. Check tombstones scanned/read, traces, p99, and SSTables/compaction. Never raise thresholds to mask read amplification.

### Exercise 5 — Unfair Comparison

Baseline uses `LOCAL_QUORUM`, 10,000 rows, and 1 KiB payloads. The new run uses `LOCAL_ONE`, 100 rows, and 128 B payloads, reporting an 80% drop in p99.

1. Why can you not conclude the new bucket/shard code is better?
2. Which variables must remain constant?
3. When sharding, what extra cost must be measured to serve "latest 20 events"?

**Hints:** CL, row count, payload size, and query semantics all changed. Hold business workload, CL, and dataset fixed; measure fan-out and merge overhead, not just one shard query.

### Exercise 6 — Retry Storm Under Load

A service at 2,000 requests/s hits 30% timeouts; middleware retries up to 3 times and the driver also retries independently.

1. Why do attempts exceed logical operations?
2. How can retries worsen a hot partition?
3. On `WriteTimeout`, is the mutation guaranteed not to have applied?
4. What safety policies are needed?

**Hints:** retries pile extra load onto servers still processing original requests. Enforce in-flight limits, retry budgets, and backoff/jitter; write outcomes may be uncertain, requiring idempotency and reconciliation.

### Exercise 7 — Choosing Remediation for Skewed Devices

A few `device_id`s generate 10,000 events/minute while most generate only a few events/day. The API queries events by day and fetches the latest 20 events.

1. Is daily bucketing alone enough for the hot devices?
2. How should shard count be chosen, and based on which metrics?
3. How should read fan-out be controlled?
4. When shard counts change later, how does the app read historical shards?

**Hints:** daily buckets may still grow too wide/hot. Inspect bytes/day, QPS/partition, p99, and replica pressure; size shards to load, version the routing logic, and bound merges.

### Exercise 8 — Before/After Report

Build a summary covering:

- CQL, schema/partition keys, dataset size, and TTL/delete ratios.
- RF/CL, driver/server versions, node/DC layout, and generator hardware.
- Arrival rate/in-flight, duration/warm-up, goodput, p50/p95/p99, and error rates.
- Tombstones scanned, partition-size histograms, compaction, disk, and GC.
- Missing evidence, caveats, and rollback criteria.

**Hints:** label real measurements vs. hypothetical numbers, citing metric sources and timing. A p99 drop does not prove overall improvement if errors, bytes, or fan-out climbed.

## 19. Pre-Conclusion Checklist

- [ ] Used an **isolated test keyspace and cluster** with synthetic data.
- [ ] Enforced limits on requests, in-flight count, row count, payload size, disk/duration, and abort conditions.
- [ ] RF/CL match topology; never infer RF=3 quorum from an RF=1 node.
- [ ] Verified partition keys, clustering keys, and real query shapes across all three tables.
- [ ] Hot-key runs keep row counts and payloads equal across hot and cold partitions.
- [ ] Explicit key distribution (uniform/skew) and RNG seed used for reproducibility.
- [ ] Ruled out skewed coordinator routing before diagnosing a hot partition.
- [ ] Wide-partition runs vary rows/bytes under control and measure range/read/paging behavior.
- [ ] Did not confuse driver page size, CQL `LIMIT`, and physical partition size.
- [ ] Did not run `COUNT(*)` / full scans as repeated health probes on large partitions.
- [ ] Tombstone runs include a pre-`DELETE`/TTL baseline and a dedicated test partition.
- [ ] Measured tombstones scanned/read or selective traces rather than relying only on deleted row counts.
- [ ] Did not lower `gc_grace_seconds` or raise tombstone thresholds to hide problems.
- [ ] Tracked compaction/SSTables, repair, GC, disk, and network across compared runs.
- [ ] Collected p50/p95/p99, goodput, timeout/error breakdowns, and failed-request latencies.
- [ ] Java load generator reuses prepared statements and sessions with bounded concurrency.
- [ ] Open-loop tests enforce bounded queues/backpressure instead of unbounded futures.
- [ ] Retries/speculative attempts did not distort logical throughput measurements.
- [ ] For writes, separated response timeouts from unknown mutation outcomes.
- [ ] Bucket/shard remediation tested against the **same business query** with real fan-out/merging.
- [ ] Planned versioned shard routing, late events, retention, and migration/backfill.
- [ ] Ran dedicated multi-node tests when drawing conclusions about failover, quorum, or repair.
- [ ] Performed zero destructive fault injection outside allowlisted testbeds with recovery plans.
- [ ] Report documents versions, dataset, nodes/DC, RF/CL, queries, latency, metrics, and conclusion limits.

## 20. Version-Matched Reference Documentation

- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): primary keys, partition/clustering columns, `DELETE`, TTL, and queries.
- [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/latest/): distributed architecture, compaction, repair, and version-specific monitoring.
- [Apache Cassandra Java Driver — Request Tracking](https://apache.github.io/cassandra-java-driver/4.18.1/core/request_tracker/): client-side statement, retry, and latency tracking.
- [Apache Cassandra Java Driver — Query Options](https://apache.github.io/cassandra-java-driver/4.18.1/core/query_options/): per-statement timeouts, page size, CL, and idempotence.
- [Apache Cassandra Java Driver — Manual Paging](https://apache.github.io/cassandra-java-driver/4.18.1/core/paging/): differences between synchronous and asynchronous paging.
- [Apache Cassandra — nodetool reference](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html): node/table inspection commands and metrics; syntax may vary across versions.

**Conclusion:** In Cassandra, a **hot key** is a request-distribution problem by partition key, a **wide partition** is a per-partition data-volume problem, and a **tombstone-heavy read** is a read-amplification problem caused by deletes or TTL expirations. All three can spike p99, yet isolating the true cause requires **separate fixtures and measurements**. Simulate in an isolated testbed, hold RF/CL/CQL/datasets under control, generate bounded Java load, monitor replicas/SSTables/tombstones, and evaluate **goodput + p99 + error rate + correctness** together. Only with solid evidence should you evaluate bucketing/sharding, retention, compaction strategies, or query-pattern changes—never rely on raising timeouts, page sizes, or unbounded retries as a substitute for sound data modeling.
