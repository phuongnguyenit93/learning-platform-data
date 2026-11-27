# Designing a New Table When Changing Partition or Clustering Keys

## 1. Scenario: a design that worked initially but outgrew its shape after two years

Suppose an **Apache Cassandra** application stores IoT events. At launch, each device emitted only a few events per day, so the team chose `device_id` as the **partition key** and `event_time` as the **clustering key**. Two years later, some devices emit dozens of events per second. Users have also shifted from viewing full histories to querying **events by day, by type, and by time range**.

Warning signs begin to appear:

- Partitions for long-lived devices grow ever larger, putting pressure on SSTable reads, compaction, and repair.
- Queries for "events of type `ALARM` on a given day" must read and filter many unrelated event types.
- History pagination APIs using `LIMIT` still hit tombstone scans and unpredictable p99 latency.
- A few hot partitions create uneven load across replica sets.
- Historical data must be migrated while the application continues inserting, updating, and deleting rows.

A tempting thought is modifying the primary key via `ALTER TABLE`. **Cassandra does not support changing the partition key or clustering key structure of an existing table in that way.** To change how data is routed and ordered, you typically must **create a new table**, write data under the new schema, migrate old data, switch read/write paths, and validate everything before retiring the old table.

This lesson in the **Migration and Schema** chapter explains that full lifecycle, grounded in Cassandra's wide-column nature: tokens/replicas, query-driven table design, CQL, replication, consistency, SSTables, tombstones, repair, and the Java Driver.

**Learning objectives:**

1. Explain why changing partition/clustering keys is a **storage-model change**, not a simple column rename.
2. Design a **v2** table for the new workload, including when multiple projections are needed.
3. Distinguish **expand → dual-write/CDC → backfill → reconcile → cutover → contract**.
4. Ensure no new events, late-arriving events, updates, or deletes are lost, and understand consistency limits while two tables coexist.
5. Write CQL and a **Java Driver 4.x** example for controlled backfilling.
6. Define metrics, go/no-go criteria, rollback paths, and when it is safe to retire the old table.

**Lab assumptions:** a single datacenter named `dc1`, a keyspace using `NetworkTopologyStrategy` with RF = 3, and enough nodes for `LOCAL_QUORUM`. Java/CQL snippets are for learning and isolated lab testing; Cassandra version, driver, CDC capabilities, and backfill tools must be verified on your real system.

## 2. What do partition keys and clustering keys determine?

A Cassandra primary key has two layers:

~~~sql
PRIMARY KEY ((partition_key_part_1, partition_key_part_2),
             clustering_column_1, clustering_column_2)
~~~

- **Partition key** values are hashed into a **token**. The token ring and replication strategy select the **natural replicas** storing the entire partition.
- **Clustering columns** determine **row identity and sort order within a partition**; efficient range queries must follow clustering-prefix access rules.
- **Regular columns** hold payload data and do not alter tokens or clustering order.

~~~mermaid
flowchart TD
    A["v1 table PRIMARY KEY"] --> B["Partition key = device_id"]
    B --> C["Token and replica set for all device events"]
    A --> D["Clustering = event_time, event_id"]
    D --> E["Event order within device partition"]
    F["v2 table PRIMARY KEY"] --> G["Partition key = device_id + event_day"]
    G --> H["Token/replica set can differ per day"]
    F --> I["Clustering = event_time, event_id"]
    I --> J["Event order within each day"]
~~~

| Desired change | Can `ALTER TABLE` on old table do it alone? | Why? |
| --- | --- | --- |
| Add an independent regular column | Usually **yes**, subject to version/schema rules. | Does not alter partition or row identity. |
| Change `device_id` to `(device_id, event_day)` | **No**. | Data must be redistributed according to the new key's token. |
| Change clustering from `(event_time, event_id)` to `(event_type, event_time, event_id)` | **No**. | Row identity, storage order, and query capabilities change. |
| Change a row's partition/clustering key values | Not a regular-column update. | Logically requires inserting at the new key and handling the old row, carrying consistency/tombstone risks. |
| Rename a key column only | `RENAME` may be conditionally supported by version. | **Renaming does not change primary key components, count, or order.** |
| Add a projection for another query | **Create a new table**. | One primary key layout cannot optimize every query shape. |

**Core consequence:** table metadata cannot "transform" SSTables written under key A into data stored under key B without reading, transforming, and rewriting them. Key changes always require planning for **backfill and synchronization of mutations arriving during the transition**.

## 3. Start from queries, not from columns you want to add

Before defining v2 tables, list the queries **users actually execute**, bounded by time and row count:

| Query pattern | Frequency | Candidate design |
| --- | --- | --- |
| A. Fetch latest 50 events for a device | Very high | `events_by_device_day`; query current bucket, then step back days if needed. |
| B. Read device events in [08:00, 09:00) UTC | High | `(device_id, event_day)` + range on `event_time`. |
| C. Fetch only `ALARM` events for a device on one day | High | Dedicated table by `(device_id, event_day)` with clustering `event_type, event_time, event_id` or suitable projection. |
| D. View all site devices with alerts in an hour | Medium | Table/projection by `(site_id, bucket_hour)`, managing hotspots. |
| E. Daily site alert totals over 12 months | Medium | Dedicated rollup/aggregate table; avoid scanning all raw events. |

**Do not force a single table to solve A–E.** Cassandra designs typically use **one or more query-driven tables**, embracing intentional denormalization and managing consistency in the ingestion pipeline.

### 3.1. Three questions to evaluate the new key

1. **Bounded partitions?** Given peak events/second, average event size, and TTL, how large will each partition grow?
2. **Bounded queries?** How many partitions/buckets must an API open, how many bytes will it return, and how many lists must it merge?
3. **Bounded writes?** Will any single partition become a write hotspot? Do buckets or shards truly distribute writes, and what is the read fan-out cost?

Benchmark every schema change for **read p95/p99, write rate, partition-size distribution, tombstones, SSTable count, and compaction/repair cost**, rather than checking only that a sample query runs fast.

## 4. CQL example: v1 table and two v2 tables

### 4.1. Lab keyspace and v1 table

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_migration
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_migration.events_v1 (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

All events for `device-7` share the partition key `device-7`. Data is time-ordered **inside this partition**, but the partition can grow over multiple years.

### 4.2. v2 table for device/day queries

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_migration.events_by_device_day_v2 (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**The sole primary-key difference from v1:** `event_day` is **inside the partition key**, not a regular column. For the same device, two different days can map to different tokens and replica sets. `event_time` still supports range scans, and `event_id` disambiguates events sharing a timestamp.

### 4.3. Second v2 table when querying by event type

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_migration.events_by_device_day_type_v2 (
  device_id text,
  event_day date,
  event_type text,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_type, event_time, event_id)
) WITH CLUSTERING ORDER BY (
  event_type ASC, event_time DESC, event_id ASC
);
~~~

In this table, `event_type` is the **first clustering column**. Querying by `event_type = 'ALARM'` and an `event_time` range fits naturally. However, "all event types in a day sorted by newest time" no longer has the desired global order if `event_type` is omitted; hence **`events_by_device_day_v2` is still required** for queries A/B.

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_migration.events_by_device_day_type_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_type = 'ALARM'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z';
~~~

You cannot switch between two clustering layouts with **one `ALTER TABLE`**. Two tables are two physical layouts serving two query patterns. If the app rarely needs query C, the second table only adds write/storage/repair overhead; **never create projections without a measured reason**.

## 5. Choosing bucket size and clustering order before migrating

For `events_by_device_day_v2`, compute `event_day` as the **UTC date** of `event_time`:

~~~text
event_time = 2026-11-20T23:59:59.999Z -> event_day = 2026-11-20
event_time = 2026-11-21T00:00:00.000Z -> event_day = 2026-11-21
~~~

If the write service uses local UTC+7 dates while the backfill job uses UTC dates, **the same event can land in two different partitions**. Thus `bucket(event_time)` must be a **versioned data contract** shared consistently across all writers and jobs.

### 5.1. Estimating partition size

Let:

- `λ`: events/second on a **hot device**, not just cluster average.
- `T`: bucket duration in seconds.
- `B`: estimated bytes/event/replica including appropriate overhead.

~~~text
events_per_bucket ≈ λ × T
partition_bytes   ≈ λ × T × B

Sustained peak example: λ = 25 events/s, B = 500 bytes/event.
Daily : 25 × 86,400 × 500 = 1,080,000,000 B ≈ 1.08 GB/partition
Hourly: 25 ×  3,600 × 500 =    45,000,000 B ≈ 45 MB/partition
~~~

This is a **rough estimate**, not exact SSTable size. If daily partitions are still too large, consider hourly buckets or controlled sharding. In return, a three-day query touches roughly 72–73 hourly buckets instead of 3–4 daily buckets; measure **fan-out and p99**.

### 5.2. Reading across buckets without global ORDER BY

For the window `[2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)`, the app must query **two** daily partitions:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:45:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:15:00Z';
~~~

Each result set is sorted **within its own partition**; the Java service must merge/sort by `event_time` (and `event_id` as tie-breaker). `LIMIT 50` per bucket does not automatically equal `LIMIT 50` across both buckets. Before switching schemas, upgrade the application to **handle fan-out, deadlines, pagination, and bucket-count caps**.

## 6. Impact assessment before creating the new table

| Category | Questions to answer |
| --- | --- |
| **CQL/schema** | Which services read/write v1? Which prepared statements hard-code old table/column/primary-key names? |
| **Partition/query** | Do any queries lack `event_day`, span one vs. many devices, or fetch last N vs. time ranges? |
| **Correctness** | Is `event_id` stable? Are there updates/deletes, TTLs, late-arriving events, or timestamp edits? |
| **Synchronization** | Will new mutations reach v2 via dual-write, CDC, event stream, or outbox? Who tracks retries? |
| **Storage** | During coexistence, is there enough disk for v1 + v2 + compaction + snapshots + streaming? |
| **Replicas/CL** | Within the same keyspace, what is RF per DC? Will the new partition key route to different replicas? |
| **Security** | Which role needs `CREATE`/migration privileges, and does the app role have `SELECT`/`MODIFY` on v2? |
| **Downstream services** | Do batch jobs, analytics, dashboards, backups/exports, monitoring, or CDC consumers depend on the old table? |
| **Rollback** | Once reads switch to v2, can we revert to v1 without losing new mutations? |
| **Verification** | What are the criteria for data completeness, latency, replica health, and discrepancy repair? |

**Note specifically:** changing the partition key does not merely rename rows. Cassandra computes tokens from the partition key, so the same event may route to **different natural replicas** after the switch. Never assume "RF = 3 stays the same, so data moves in place without rewriting/streaming."

## 7. Multi-phase strategy: expand, migrate, and contract

The safe approach for live applications is **add first, transition gradually, remove last** (*expand–migrate–contract*):

~~~mermaid
flowchart TD
    A["V1 actively serving reads/writes"] --> B["EXPAND: create V2 table, standardize key mapping"]
    B --> C["Enable capture/dual-write for new mutations"]
    C --> D["BACKFILL: bounded scan of V1 and write V2"]
    D --> E["CATCH-UP: replay unapplied mutations"]
    E --> F["RECONCILE: compare + repair discrepancies"]
    F --> G["SHADOW READ: compare V1/V2 while keeping V1 primary"]
    G --> H{"Cutover criteria met?"}
    H -->|Not yet| D
    H -->|Met| I["Canary shift reads to V2"]
    I --> J["Stabilize, monitor, retain rollback path"]
    J --> K["CONTRACT: stop V1 writes after retention"]
    K --> L["Back up, approve, then drop V1"]
~~~

**What not to do:** stop the app, run `CREATE TABLE v2`, run a few sample `INSERT`s, and immediately `DROP TABLE v1`; likewise, never treat a one-time copy of old data as sufficient while concurrent writes are occurring.

### 7.1. Operational state machine

| Phase | Write path | Read path | Advancement gate |
| --- | --- | --- | --- |
| **V1_ONLY** | V1 | V1 | Baseline and mapping verified. |
| **DUAL_WRITE** | V1 and V2, with retry/durable log on single-branch failure | V1 | New data is not dropped from V2. |
| **BACKFILL** | V1 and V2 | V1 | Historical V1 scope scanned cleanly. |
| **CATCH_UP** | V1 and V2 | V1, silent V2 comparison | Mutation backlog and drift resolved. |
| **V2_CANARY** | Keep V1/V2 | Fraction of traffic on V2, with fallback | p99/errors/data correctness meet SLOs. |
| **V2_PRIMARY** | Keep rollback path | V2 | Pre-defined stabilization window passed. |
| **V2_ONLY** | V2 | V2 | Accept that simple flag rollback to V1 is no longer possible. |
| **RETIRED** | V2 | V2 | V1 backed up and dropped via approved change. |

Exact ordering can vary by workload, yet **correctness criteria and rollback paths** must be defined upfront. Stopping V1 writes too early makes reverting to v1 unsafe once new mutations exist only in v2.

## 8. EXPAND phase: create v2 schema and verify before copying

Creating a new table **does not generate historical data**. Nor does `CREATE TABLE IF NOT EXISTS` guarantee an existing table matches your intended schema if a differently defined table already shares that name.

In `cqlsh` in the lab:

~~~sql
DESCRIBE KEYSPACE telemetry_migration;
DESCRIBE TABLE telemetry_migration.events_v1;
DESCRIBE TABLE telemetry_migration.events_by_device_day_v2;
DESCRIBE TABLE telemetry_migration.events_by_device_day_type_v2;
~~~

`DESCRIBE` is a **`cqlsh`** command, not a CQL statement sent verbatim through the Java Driver. Verify:

1. Column types are compatible with proper nullability and TTL semantics.
2. v2 partition keys and clustering order match read patterns.
3. RF, snitch/DC/rack, and replica states are healthy.
4. App roles have `MODIFY` on v2; canary readers have `SELECT` without unintended over-privilege.
5. Schema agreement and client prepared statements are refreshed/deployed properly.
6. Baseline free disk, CPU/GC, compaction backlog, and read/write p95/p99 are recorded.

**Schema agreement confirms only that schema metadata converged across the cluster**, not that v1's data is inside v2. Moreover, multiple new tables **significantly increase total replica storage** during coexistence; budget for snapshots and compaction headroom.

## 9. New mutations: dual-write must handle single-branch failures

### 9.1. Writing immutable events is simpler than arbitrary updates

If every event is **immutable**, with `event_id` and `event_time` assigned once, and the producer writes to both v1 and v2:

~~~mermaid
sequenceDiagram
    participant App as Ingestion service
    participant Log as Durable mutation log
    participant V1 as Table v1
    participant V2 as Table v2
    App->>Log: Persist event with immutable ID
    Log-->>App: Durable
    App->>V1: Upsert with v1 key
    App->>V2: Upsert with v2 key
    V1-->>App: ACK or error
    V2-->>App: ACK or error
    Note over App: If one branch fails: retain mutation for retry/reconcile
~~~

**Executing two separate `INSERT`s is not a cross-table atomic distributed transaction.** If v1 succeeds and v2 fails, safety requires a **durable retry queue, outbox/event stream, CDC, or reconciliation job** built for that failure mode.

### 9.2. Mutation synchronization options

| Option | Strengths | Limitations / risks |
| --- | --- | --- |
| **In-service direct dual-write** | Straightforward; separate metrics/mapping for v1/v2. | Not atomic across tables; request timeouts leave ambiguous outcomes; needs durable retries. |
| **Durable event stream / outbox** | Provides mutation log with IDs/offsets for replay, lag tracking, and recovery. | Requires stream operations, per-key ordering, and idempotency. |
| **Version-specific Cassandra CDC** | Captures mutations from Cassandra's write path to build projections. | Depends on version/consumer stack, retention, and catch-up speed; not automatically an exactly-once pipeline. |
| **Maintenance write pause** | Gives a clean cut point for small systems and reduces contention during copy. | Downtime may be unacceptable; still requires data validation/rollback. |
| **Two-table logged batch** | Can provide Cassandra batch atomicity in applicable cases. | Not an isolated/snapshot transaction, and multi-partition batches add heavy overhead; never use as default migration tool. |

If the system already has a **durable event source** (message log or another canonical store), rebuilding v2 via **checkpointed replay** is often more reliable than scanning v1. However, you must understand mutation ordering, retention, deletes, and full state reconstruction.

### 9.3. Idempotency rules

~~~text
event_id = stable ID preserved across all retries
event_time = immutable event timestamp normalized to UTC
event_day = UTC_DATE(event_time)

v1 key = (device_id, event_time, event_id)
v2 key = (device_id, event_day, event_time, event_id)
~~~

Rewriting **the same immutable event** under the same key reduces duplicate-row risk during migration. Still, "idempotent" holds only when payload, timestamp, TTL, and concurrent-mutation semantics are clearly defined. Retrying with a fresh TTL can **extend lifetime**, and backfilling with a fresh timestamp can overwrite a newer update on the same cell.

## 10. BACKFILL phase: scan v1 by partition and write v2

### 10.1. Choosing the read source and checkpoint unit

With v1's schema `PRIMARY KEY ((device_id), event_time, event_id)`, efficient reads require knowing `device_id`. If the system has an **authoritative device registry/catalog**, pull IDs from it and backfill per device and time window.

~~~sql
-- One time slice of one V1 partition:
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

**Never assume you can run `SELECT DISTINCT device_id FROM ...` on a huge table as a free directory** or tack on `ALLOW FILTERING` to scan production clusters. Without a catalog, you need a **token-range full-scan plan** using version-compatible export/chunking tools while measuring read pressure, network, tombstones, and replica load.

Checkpoints should represent **data read and successfully written**, for example:

~~~text
job_id              = migration-2026-11-21
source_table        = telemetry_migration.events_v1
target_table        = telemetry_migration.events_by_device_day_v2
device_id           = device-7
window_start_utc    = 2026-11-20T00:00:00Z
window_end_utc      = 2026-11-21T00:00:00Z
last_verified_key   = (event_time, event_id)
source_rows_seen    = 5000
target_writes_ok    = 5000
checkpoint_state    = VERIFIED
~~~

This checkpoint is a **migration-system metadata model**, not a table Cassandra creates automatically. Mark a checkpoint done only once required target writes have been **acknowledged at the target CL** and failures have been retried or queued. With updates/deletes or diverged replicas, additional verification is required; an ACK does not prove all replicas are identical.

### 10.2. Backfill rules to uphold

1. **Chunk the work:** by `device_id`, UTC window, and/or token range; never load a multi-year partition into memory at once.
2. **Use paged reads:** set finite fetch sizes and measure rows/bytes/sec and response latency.
3. **Use bounded concurrency/rate for writes:** never fire unbounded async requests; cap to replica capacity.
4. **Preserve identity:** do not generate a new `event_id` during copy; preserve the original `event_time`.
5. **Populate all required projections:** if v2 includes both daily and by-type tables, process every valid event into each.
6. **Track uncertain failures:** timeouts mean **partial write is possible**; retries must be safe.
7. **Avoid competing with repair/compaction/streaming:** schedule when disk headroom, CPU, and network allow.
8. **Support pause/resume:** rely on independent checkpoints and per-window state, not "whether the process stayed alive."

### 10.3. Important paging behavior

CQL result paging avoids loading all rows into memory at once, but **does not provide snapshot isolation of v1** during the scan. Mutations arriving between pages can change results relative to when the scan began.

Never treat **paging state** as a durable cursor valid across restarts, versions, or schema changes. Reliable resume needs an explicit checkpoint contract, such as fixed windows, last verified clustering keys, and duplicate/gap guards. When using descending clustering on `event_time, event_id`, resume predicates must consider **both columns**; saving only `event_time` can skip rows sharing a timestamp.

## 11. Java Driver 4.x: example backfilling one device for one day

The following example is for a **lab with immutable event data and no concurrent TTL/updates/deletes**. It reads `device-7` rows in one UTC window from v1 and writes them into the daily v2 table. **Do not** use this code as a production migration without adding durable checkpoints, throttling, retries, validation, and concurrent-mutation handling.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class BackfillEventsV1ToV2 {
    public static void main(String[] args) {
        String deviceId = "device-7";
        Instant from = Instant.parse("2026-11-20T00:00:00Z");
        Instant until = Instant.parse("2026-11-21T00:00:00Z");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement source = session.prepare(
                "SELECT event_time, event_id, event_type, payload " +
                "FROM telemetry_migration.events_v1 " +
                "WHERE device_id = ? AND event_time >= ? AND event_time < ?");

            PreparedStatement target = session.prepare(
                "INSERT INTO telemetry_migration.events_by_device_day_v2 " +
                "(device_id, event_day, event_time, event_id, event_type, payload) " +
                "VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement scan = source.bind(deviceId, from, until)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(200);

            long copied = 0;
            for (Row row : session.execute(scan)) {
                Instant eventTime = row.getInstant("event_time");
                UUID eventId = row.getUuid("event_id");
                LocalDate day = eventTime.atZone(ZoneOffset.UTC).toLocalDate();

                BoundStatement upsert = target.bind(
                    deviceId,
                    day,
                    eventTime,
                    eventId,
                    row.getString("event_type"),
                    row.getString("payload"))
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

                // Synchronous and sequential only for readability; production needs
                // bounded concurrency, error/retry handling, and durable checkpoints.
                session.execute(upsert);
                copied++;
            }
            System.out.println("source_device=" + deviceId
                + " from=" + from + " until=" + until
                + " target_writes_acknowledged=" + copied);
        }
    }
}
~~~

### 11.1. What this code gets right

- `PreparedStatement` avoids string-concatenating literals into CQL and cleanly maps `Instant`, `LocalDate`, and `UUID`.
- `event_day` is derived **from the event's UTC timestamp**, not the job's wall-clock run time.
- The source query specifies `device_id` and a bounded clustering range; no `ALLOW FILTERING` needed.
- `setPageSize(200)` streams data in pages instead of buffering unbounded results at once.
- Writes use the event's **stable v2 primary key** instead of generating random IDs during backfill.
- `LOCAL_QUORUM` in the RF = 3 lab requires **two replica responses in `dc1`** per read/write, though it does not replace repair.

### 11.2. What this code **does not** solve yet

| Limitation | Why it matters in production |
| --- | --- |
| Sequential execution without rate/throughput budget | Can be far too slow on large datasets; raising concurrency blindly can overload the cluster. |
| No durable checkpoint | If the process crashes, it is hard to know which windows were verified and what must rerun. |
| Does not handle concurrent deletes/updates | v2 may retain rows deleted in v1 or overwrite newer versions. |
| Does not preserve original TTL/writetime | Data lifetime may shift; a new `INSERT` does not automatically carry old TTLs. |
| No error DLQ/replay handling | One failed write can abort the job, while write timeouts leave uncertain state. |
| Does not compare v1/v2 data | `copied = N` only counts job ACKs, not proof of zero missing or differing rows. |
| Does not populate the by-type v2 table | If a second projection is required, separate mapping/writes must be implemented. |
| No cutover/rollback controls | Copying one window does not suffice to switch all application reads. |

**An already-copied immutable event can be rewritten with the same key** if a job retries, yet if payloads mutate or TTLs run, explicit conflict/expiry rules remain necessary.

## 12. The hardest part: updates, deletes, and TTL during migration

### 12.1. Backfill can "resurrect" deleted data

Suppose:

1. At 10:00, backfill reads event E from v1.
2. At 10:01, the app deletes E in v1 and writes the corresponding delete to v2.
3. At 10:02, backfill runs a fresh `INSERT` into v2 with the same key E.

If the backfill write's timestamp is **newer than the tombstone**, event E can reappear in v2. **No stable `event_id` check automatically prevents this**, because it is a mutation-and-timestamp conflict.

~~~mermaid
sequenceDiagram
    participant BF as Backfill
    participant Old as V1
    participant App as Application
    participant New as V2
    BF->>Old: Read event E (10:00)
    Old-->>BF: E is currently alive
    App->>Old: DELETE E (10:01)
    App->>New: DELETE E (10:01)
    Note over BF: Holds E in job queue
    BF->>New: INSERT E with newer timestamp (10:02)
    Note over New: E may reappear if mutation beats tombstone
~~~

The solution must account for **event sources, mutation ordering, and timestamp policies**:

- For **append-only immutable events with no deletes/edits** during migration, risk drops dramatically.
- With updates/deletes, you need a **durable changelog/CDC** or reconciliation mechanism that replays all mutations with source semantics.
- If using `USING TIMESTAMP` in backfill to preserve ordering, you must know **each cell's original writetime**, delete timestamps, TTLs, and Cassandra constraints; never derive a single timestamp from `event_time`.
- You may need a **temporary update/delete freeze** during an approved cutover window, or rebuild state from another canonical source.

**Never alter last-write-wins mechanics by blindly setting `USING TIMESTAMP` to a business timestamp.** Mutation reconciliation timestamps are distinct from `event_time` columns in a table.

### 12.2. TTL: copying data does not copy expiration time

If v1 uses `default_time_to_live` or `USING TTL`, live cells may have only a **short remaining lifetime**. Copying them with a fresh `INSERT` into v2 (without matching TTL semantics) can:

- Keep data alive **longer** than retention allows if no TTL is set.
- Or, if v2 has a default TTL, reset TTL **from backfill time**, extending the life of old rows.

For multi-cell rows, `TTL(column)` and `WRITETIME(column)` are **cell-level** metadata where supported—not a full snapshot of every deletion/tombstone in a partition. One row can even hold different TTLs across different columns.

Example inspection on live rows:

~~~sql
SELECT event_time, event_id,
       TTL(payload) AS payload_ttl_seconds,
       WRITETIME(payload) AS payload_write_time_us
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

`TTL(payload)` returns `null` when the cell has no TTL. It **does not reveal every past delete**, nor recover purged tombstones. To strictly preserve retention, design a data-appropriate strategy: an event stream carrying `expiry_at`, remaining TTL during replay, or migration with controlled freeze/reconciliation windows. Never assume `SELECT` on current live rows captures full mutation history.

### 12.3. "Moving a row" has no cross-primary-key atomicity

If an event must move from `device_id=old` to `device_id=new`, the operation is **write new key** followed by **delete old key** per procedure. Across tables or keys, those two mutations can land on **different partitions and replica sets**. A plain `UPDATE` cannot edit a partition key in place, and Cassandra provides no fully isolated SQL transaction for moving rows across tables.

**Therefore:** schema migrations need plans for **transitional state**, idempotency, and reconciliation—never assume one command atomically updates both v1 and v2.

## 13. CATCH-UP: new data, late-arriving events, and watermarks

Day-sharded backfill based on `event_time` **does not** automatically catch every new mutation. An event written today can carry last week's `event_time` from an offline device, landing in a **historical bucket** that backfill already marked complete.

### 13.1. Watermarks must track the mutation source, not just event time

~~~text
event_time     = when the event occurred (may be old)
ingested_at    = when the system received the event
stream_offset  = mutation position in an ordered durable source
backfill_range = historical data range already scanned
~~~

If using an event stream:

1. Capture a **starting offset/checkpoint** before enabling v2 writes or before backfilling.
2. Start the consumer updating v2 and persist **successfully applied offsets**.
3. Backfill historical data using consistent keys and semantics.
4. **Catch up/replay** all mutations generated during backfill and resolve retries.
5. Advance to shadow reads only once **lag is small, DLQ errors are resolved, and reconciliation passes thresholds**.

**Never rely solely on `event_time > cutoff` for catch-up.** Late-arriving events, out-of-order backfills, and updates/deletes can all carry old `event_time` values despite being written recently.

### 13.2. Ordering and exactly-once

A stream may guarantee ordering **within a single stream partition**, not necessarily across all devices or stream partitions. Dual-write, CDC, and retries are typically **at-least-once**; you need stable key mappings, idempotent mutations, and clear conflict logic.

Never claim "exactly-once" merely because each message has an ID. With **counters, LWTs, TTL refreshes, read-modify-writes**, or competing deletes, retries can alter outcomes depending on semantics. Choose a clear data contract per mutation class and re-verify during restore/replay.

## 14. RECONCILE: prove v2 completeness instead of trusting copied row counts

No built-in CQL command certifies "all v1 and v2 rows are business-equivalent" across a cluster without reading and comparing data. Reconciliation should combine **multiple layers**:

| Verification layer | Execution | Limitations |
| --- | --- | --- |
| **Schema** | `DESCRIBE TABLE`, compare primary key/order/TTL and permissions. | Does not verify data completeness. |
| **Backfill progress** | Completed windows, rows scanned, writes ACKed, retries/dead-letters. | Can double-count or skip rows; ACKs are not canonical data validation. |
| **Scoped counts** | Counts per device/day or from an independent compute system. | Equal counts do not prove equal contents; large `COUNT(*)` is very expensive. |
| **Key-set comparison** | Extract `(device_id,event_time,event_id)`, map to v2 keys, and diff. | Requires windowed scans, memory/disk, and appropriate CL. |
| **Ordered fingerprint/hash** | Canonicalize keys/payloads and hash per window. | Must define serialization/TTL/null/delete handling; hashes are only as strong as the design. |
| **Sample queries/functional tests** | Query time ranges, last N, ALARM-only from v1/v2 and compare. | Sampling does not replace full-dataset verification. |
| **Health/repair** | Node health, compaction, runbook repairs if replicas diverge. | Internal v2 repair does not compare v1 against v2 logic. |

**Never run unbounded `SELECT COUNT(*)` across massive tables just to verify migration.** In Cassandra, counting reads huge volumes of data and triggers costly scans; use partitioned pipelines, external counting jobs, or scoped, rate-limited statistics.

### 14.1. Concrete query reconciliation

For immutable data without TTL in the lab:

~~~sql
-- V1: same device, same time range.
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z';

-- V2: single day partition.
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z';
~~~

Compare **canonical key sets and values**, not just `LIMIT` or row counts. When writes happen concurrently, the two SELECTs **do not share an atomic snapshot**. Reconcile at a **meaningful watermark**, wait for consumer catch-up, and re-check impacted windows.

### 14.2. What discrepancies should block cutover?

Sample go/no-go criteria tailored to product requirements:

- Zero historical windows in `FAILED` or `UNKNOWN` state.
- Zero **unprocessed mutations** in retry or dead-letter queues within the cutover scope.
- Key sets and payloads between the canonical source and v2 **match per published reconciliation rules**; TTL/delete rules have explicit policies.
- Both DCs/replica scopes verified at proper CL, with healthy repair/streaming status.
- p95/p99 latency, timeout/error rates, and disk/GC/compaction metrics meet SLOs in load tests/canary.

Never treat 99.9% match rate as a universal threshold for every business domain: **losing 0.1% of events can be unacceptable** for financial or security-audit data.

## 15. SHADOW READ and CUTOVER: shifting reads without a shared snapshot

### 15.1. Shadow reads

In shadow mode, the application **continues returning v1 results** to users while sending a small fraction of reads to v2 to measure:

- Results and event ordering: `event_time`, `event_id`, payload, and type filters.
- p50/p95/p99, partitions/buckets opened, page counts, bytes read, and timeouts.
- Consistency across UTC midnight boundaries and late-arriving events.
- Stability during slow nodes/replicas, GC pauses, or active compaction.

Do not immediately mirror 100% of production reads because shadow reads **add load**. Use controlled sampling/canary rates and concurrency limits, and avoid logging sensitive row-level data.

### 15.2. Canary cutover

~~~mermaid
flowchart LR
    A["Application read router"] --> B{"Feature flag by service/tenant"}
    B -->|Majority| C["Read V1 and return result"]
    B -->|Canary| D["Read V2 + merge buckets"]
    C --> E["V1 query metrics"]
    D --> F["V2 query metrics"]
    E --> G["Compare SLOs/errors/data correctness"]
    F --> G
    G --> H["Ramp canary or roll back flag"]
~~~

While keeping a rollback path open, **do not stop writing to v1**. If reads switch to v2 while new mutations go only to v2, flipping the feature flag back to v1 will make the app **lose visibility of new data**.

### 15.3. Bounded read fallback

Falling back to v1 when a v2 read fails can reduce downtime, but requires care:

- **A timeout does not mean no data exists**; never use unbounded fallback that lets both queries consume resources simultaneously.
- v1 and v2 do not share an atomic snapshot, so fallback can return slightly different results while mutations converge.
- Enforce an **overall deadline**, retry budget, and a dedicated `fallback_rate` metric.
- When v2 returns **empty**, do not permanently fall back to v1 for every request; that can mask migration bugs and double read load.

## 16. ROLLBACK and CONTRACT: how long to keep the v1 table?

Successful rollback depends on **keeping the v1 write path active**:

| State | Easy to revert to v1? | Condition |
| --- | --- | --- |
| v2 canary, dual-writing v1/v2 | **Possible**, via controlled feature flag. | v1 still receives all mutations with valid retention/tombstones. |
| v2 primary, still dual-writing | **Possible**, but inspect data drift and single-branch errors. | Bidirectional reconciliation against the canonical source. |
| v1 writes stopped, v2-only writes | **Cannot just flip a flag**. | Requires reverse backfill/catch-up or event-log replay, carrying cost and risk. |
| v1 dropped and backup unverified | **Very high risk**. | No simple rollback; restore from an independent source if available. |

### 16.1. Do not rush `DROP TABLE`

~~~sql
-- WARNING: destroys old table schema and data.
-- DO NOT execute without approval, backups, retention verification, and post-checks.
DROP TABLE telemetry_migration.events_v1;
~~~

In Cassandra, `DROP TABLE` may trigger **auto_snapshot** depending on version/config, but **never rely on auto-snapshot as your sole backup plan**. Maintain independent, restorable backups and required schema/mapping documentation.

Before contracting:

1. All clients, batch jobs, analytics, and automation have migrated to v2.
2. Telemetry confirms zero valid v1 reads/writes, including infrequent consumers like month-end jobs.
3. The rollback window has formally closed after an **approved stabilization period**.
4. v2 data is complete, repair/streaming are healthy, and backup/restore has been tested.
5. Retention, legal compliance, and deletion authorization are verified.
6. Change ticket, approver, snapshots/backups, and pre/post-deletion UTC timestamps are recorded.

**Never manually delete v1 SSTables** to reclaim disk space. Table and file lifecycle management must go through controlled CQL/operations and be verified afterward.

## 17. Monitoring resources and latency during migration

Coexisting v1 + v2 tables can **roughly double logical writes** (or more with multiple projections), while real disk/I/O overhead also depends on compression, RF, backfill, compaction, and snapshots. Watch these side effects together:

| Metric | Migration risk | Action |
| --- | --- | --- |
| **Free disk per node/volume** | Two tables coexist, snapshots pin old SSTables, compaction needs temporary space. | Maintain headroom; throttle rate or reschedule if near thresholds. |
| **Write latency/timeouts** | Dual-write + backfill increase requests and replica I/O. | Bounded concurrency, per-DC rate limits, traffic isolation. |
| **Read p95/p99** | Backfill scans compete with live traffic; v2 fans out across buckets. | Throttle, shadow-sample, inspect query shapes. |
| **Compaction backlog/SSTable count** | v2 produces additional SSTables while both v1/v2 compact. | Monitor `compactionstats`, strategy, and disk I/O. |
| **Heap/GC, thread pools** | Oversized pages, growing queues, heavy payload deserialization. | Tune page sizes, cap in-flight work and batches. |
| **Hints/repair/replica health** | A replica misses mutations or a remote DC lags. | Monitor handoffs, repairs, and per-DC scope. |
| **Migration queue/DLQ** | One dual-write branch fails without retry. | Alert on backlog/oldest mutation age; block cutover if incomplete. |
| **Data drift** | Wrong UTC mapping, differing TTLs, update/delete races. | Windowed reconciliation and root-cause analysis of mismatches. |

### 17.1. Lab observation commands

~~~bash
nodetool status
nodetool info
nodetool tablestats telemetry_migration.events_v1
nodetool tablestats telemetry_migration.events_by_device_day_v2
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool gcstats
~~~

`nodetool` output and flags vary by version. **`tablestats` reports table-level metrics, not a logical v1/v2 data comparison**. Run commands with appropriate operational privileges; never embed admin credentials in public scripts.

### 17.2. Selective tracing

In `cqlsh` in the lab:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

Tracing helps inspect coordinator/replica execution for **a single query**, not statistical SLO compliance. Enabling tracing on 100% of live traffic during a backfill adds significant load and skews measurements.

## 18. Simulated migration incident: from surface symptom to root cause

**Context:** the team enabled dual-write for v1/v2 at 10:00 UTC, then backfilled older days. By 14:00, v2 row counts are ~0.2% lower than v1 in several windows. The team considers increasing read timeouts and proceeding with cutover.

| Time | Evidence | Interpretation |
| --- | --- | --- |
| 10:00 | Dual-write enabled; v1 write success = 100%, v2 = 99.8%. | Some mutations were ACKed only by v1; durable retries are needed. |
| 11:00 | Backfill finished `event_time` windows prior to 10:00. | Does not prove **late events arriving after 11:00** into older windows were captured. |
| 12:00 | v2 DLQ still holds 5,000 un-replayed mutations. | Cannot switch all reads to v2 yet. |
| 13:00 | A device emits an event with yesterday's `event_time`. | `event_time` watermarks can miss it if yesterday's window was already closed. |
| 14:00 | Snapshots/sample queries show v2 missing events. | Raising timeouts will not mask or fix missing data. |

**Probable cause:** the dual-write/catch-up pipeline lagged, and late-arriving events were not reprocessed into already-verified windows. Increasing timeouts **does not create missing rows**. Actions:

1. Halt cutover progression and keep reads on v1.
2. Drain DLQ/retries idempotently and verify mutation-source offsets.
3. Re-scan windows impacted by late writes and compare key sets.
4. Confirm v2 has no tombstone/TTL races or incorrect `event_day` mappings.
5. Enable canary only after data meets criteria and p99/storage remain healthy.

**If v2 has extra rows instead of missing ones**, never blindly delete based on count diffs. Investigate backfill resurrecting deletes, retries generating new event IDs, or extended TTLs—each requires a different fix.

## 19. Especially dangerous anti-patterns

| Claim / action | Problem | Correct approach |
| --- | --- | --- |
| "Change `PRIMARY KEY ((device_id))` to `((device_id, day))` via `ALTER TABLE`." | Cassandra does not support altering primary-key components this way. | Create v2 and migrate data. |
| "Changing clustering order only needs `ALTER TABLE ... RENAME`." | Renaming does not alter physical layout or clustering order. | Create a new table/projection with the new primary key. |
| "Once `CREATE TABLE v2` finishes, data is migrated." | Schema metadata is separate from physical data. | Backfill, catch up, reconcile. |
| "Dual-write uses two `INSERT`s so it is atomic." | One branch can fail or time out. | Durable log/CDC/outbox + retries and monitoring. |
| "Backfilling days prior to today is enough." | Late events carry older `event_time` values. | Watermark by mutation source, catch up/replay. |
| "Retry with a fresh event ID to avoid touching old data." | Creates logical duplicates and breaks reconciliation. | Stable event IDs and conflict policies. |
| "Backfilling with current timestamps is always safe." | Can overwrite newer updates or deletes. | Design ordering/writetime and reconciliation explicitly. |
| "Copying without TTL still preserves retention." | Can extend data lifetime indefinitely. | Preserve expiry/TTL semantics by design. |
| "Matching `COUNT(*)` proves data equivalence." | Different keys can be missing and extra simultaneously. | Compare scoped keys/values and fingerprints. |
| "`LOCAL_QUORUM` on two SELECTs gives a shared snapshot." | Two tables/partitions have no atomic snapshot. | Reconcile at a watermark against a durable mutation source. |
| "Canary v2 and stop v1 writes while still able to flag-rollback." | v1 misses mutations written after v1 writes stopped. | Keep dual-writes active through the rollback window. |
| "More buckets is always faster." | Historical reads can suffer huge fan-out. | Benchmark partition size, bucket count, and SLOs. |
| "`nodetool repair` on v2 syncs it with v1." | Repair syncs replicas within one table's token ranges, not across two schemas. | Dedicated app/migration reconciliation. |
| "A node snapshot is enough to drop v1." | If a node loses a disk, local snapshots are lost too. | Independent backups and tested restores. |

## 20. Exercises with answers

**Exercise 1.** Table v1 has `PRIMARY KEY ((device_id), event_time, event_id)`. The team wants `event_day` inside the partition key. Can they run `ALTER TABLE ADD event_day date` and consider it bucketed?

**Answer:** **No.** `ADD` creates a regular column, not part of the partition key. You must create a v2 table with `PRIMARY KEY ((device_id,event_day), ...)` and migrate the data.

**Exercise 2.** Why can changing the partition key move the same event to a different replica set even if RF stays unchanged?

**Answer:** Tokens are computed from the **partition key**. `device_id` and composite `(device_id,event_day)` produce different tokens, so natural replica placement can differ.

**Exercise 3.** A new table uses clustering `(event_type, event_time, event_id)`. A query specifies only device/day and wants all event types ordered by timestamp DESC. Is partition-wide chronological ordering guaranteed?

**Answer:** **No.** Clustering orders by `event_type` first. You need a table clustered by `(event_time,event_id)` or a separate projection for cross-type chronological queries.

**Exercise 4.** Two hours into backfill, a `DELETE` runs on v1/v2, and the job later writes a stale `INSERT` into v2 with a newer timestamp. What is the risk?

**Answer:** **Resurrecting deleted rows** when the backfill mutation beats the tombstone by timestamp. Preserve mutation ordering via CDC/replay/controlled freeze or appropriate reconciliation.

**Exercise 5.** An event occurred yesterday but arrived at 14:00 today. Why is catching up only where `event_time > 10:00 today` wrong?

**Answer:** Late-arriving events carry an old `event_time` despite being written recently. Watermarks must track the mutation source/ingestion offset, not only event time.

**Exercise 6.** Two `SELECT`s on v1 and v2 both use `LOCAL_QUORUM` and return equal row counts. Is that enough for cutover?

**Answer:** **Not yet.** Counts do not guarantee identical keys or values; the two SELECTs share no atomic snapshot; TTLs, deletes, late events, and DLQs may still diverge. Reconcile against watermarks and SLOs.

**Exercise 7.** Why can backfilling 1 million rows using `INSERT` without TTL into v2 violate retention if v1 rows had 2 days of TTL left?

**Answer:** v2 may retain data longer or reset TTL from copy time. Preserve `expiry_at`/remaining TTL and cell-level semantics rather than copying only live values.

**Exercise 8.** During dual-write, v1 ACKs while v2 times out. Can you assume v2 definitely did not write the row?

**Answer:** **No.** A timeout can occur after some v2 replicas already applied the mutation. The system needs safe retries, stable event identity, and reconciliation—never generate a new ID.

**Exercise 9.** After cutting reads over to v2, the team stopped v1 writes for a week. Can they roll back merely by flipping the feature flag to v1?

**Answer:** **No.** v1 is missing a week of mutations; rollback requires reverse backfill/replay from a canonical source or a dedicated data rollback plan.

**Exercise 10.** Why avoid running full-table `COUNT(*)` to verify a migration on a busy cluster?

**Answer:** Cassandra does not maintain free exact row counts for arbitrary tables; counting can scan vast amounts of data. Use scoped/windowed reconciliation with rate limits and metrics.

**Exercise 11.** A hot device writes 25 events/sec at 500 bytes/event/replica. What is the estimated size of an hourly bucket?

**Answer:** `25 × 3600 × 500 = 45,000,000 bytes ≈ 45 MB` per replica before compression/SSTable/TTL variance. RF multiplies cluster-wide storage, not the logical size of one partition on a single replica.

**Exercise 12.** After creating v2, `DESCRIBE TABLE` looks right and `nodetool status` shows all `UN`. What remains unproven?

**Answer:** Historical backfill completeness, catch-up of new mutations, zero data drift, correct TTL/delete semantics, and read/write p99 SLO compliance. Reconciliation and canary testing are still required.

## 21. Decision checklist before dropping the v1 table

~~~text
[ ] V2 primary key matches queries; ALLOW FILTERING is not masking a bad design.
[ ] Bucket(time) UTC/business timezone matches identically between ingestion and backfill.
[ ] Source inventory covers all devices/token ranges; checkpoints are complete.
[ ] Every required V2 projection has been populated.
[ ] Dual-write/CDC/event log handles retries and mutation ordering with evidence.
[ ] Updates/deletes/tombstones and TTL/expiry policies are explicitly defined.
[ ] Late-arriving events are not skipped by an event_time watermark.
[ ] Backfill windows are VERIFIED; zero UNKNOWN/FAILED windows remain.
[ ] DLQ and retry backlogs were drained before cutover.
[ ] Scoped key/value reconciliation meets business criteria.
[ ] Shadow reads and V2 canary meet p95/p99, timeout, and functional targets.
[ ] Disk headroom, compaction, GC, hints, and repair remain stable.
[ ] RF/CL and DC/replica checks align with availability requirements.
[ ] All clients, jobs, exports, metrics, and schema references moved to V2.
[ ] Rollback window has closed or an alternative data recovery plan exists.
[ ] V1 writes were not halted while V1 was still needed for rollback.
[ ] Independent backups, manifest, restore tests, and change approval exist.
[ ] DROP action records actor/UTC/target audit info and post-drop verification.
~~~

~~~mermaid
flowchart TD
    A["Need to change partition/clustering key"] --> B["Design V2 table from queries and sizing"]
    B --> C["EXPAND: schema, roles, RF/CL, and capacity"]
    C --> D["Enable dual-write or durable mutation capture"]
    D --> E["Backfill with paging/checkpoints/rate limits"]
    E --> F["Catch up new events, late events, updates/deletes"]
    F --> G["Reconcile keys/values/TTL and replica health"]
    G --> H{"Data correctness and SLOs met?"}
    H -->|No| I["Keep V1 primary; fix mapping/lag and re-reconcile"]
    I --> E
    H -->|Yes| J["Shadow/canary read V2"]
    J --> K{"Stable and rollback viable?"}
    K -->|No| I
    K -->|Yes| L["V2 primary; retain V1 for rollback window"]
    L --> M["Contract/back up/retire V1 after approval"]
~~~

**Summary:** Changing a Cassandra **partition key** or **clustering key** is not renaming a field; it changes **identity, token placement, storage order, and read paths**. The standard solution is **creating a new query-driven table**, synchronizing new mutations, backfilling historical data, explicitly handling **timestamps/TTLs/deletes/late events**, reconciling with checkpoints, and **shifting traffic via canary**. Only after verifying data, resources, SLOs, replicas, and rollback safety should you retire the old table. In migrations, **schema agreement does not equal data migration**, **a timeout does not mean no write occurred**, and **command success never replaces post-checks**.
