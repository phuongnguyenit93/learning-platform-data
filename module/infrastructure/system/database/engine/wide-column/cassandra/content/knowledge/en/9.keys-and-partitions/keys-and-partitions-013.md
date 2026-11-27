# Changing Key Design with a New Table and Migration Plan

In Apache Cassandra, choosing `PRIMARY KEY` does more than determine how a row is identified. The **partition key** determines the token and replica set storing the data; **clustering columns** govern how rows are organized inside a partition and which range queries are supported. Therefore, when a system begins experiencing oversized partitions, hot keys, queries forced into broad filtering, or difficulty bounding history, fixing the key design is usually **a data and traffic migration**, not a simple configuration tweak.

Cassandra **does not support arbitrarily altering the partition key or clustering key of an existing table via `ALTER TABLE`**. The standard, controllable approach is: **create a new table with the proper key, migrate data, synchronize ongoing changes, verify, and then switch read/write traffic**. This process must account for distributed characteristics: replication, consistency levels, retries, late-arriving data, TTL, tombstones, compaction, and repair.

This lesson belongs to the **Keys and Partitions** chapter. A running example migrates a table storing full device history to a new table partitioned by **daily buckets**, illustrating a plan from assessment to *cutover* and *rollback* when deploying with CQL and Java applications.

After this lesson, you will be able to:

- Explain why a **new table** must be created when changing the partition/clustering key combination.
- Compare queries, partition sizes, and load distribution between the old and new schemas.
- Define a **deterministic, repeatable** data mapping function covering keys, buckets, and event identifiers.
- Sequence **dual-write/change capture → backfill → reconciliation → shadow read → cutover**.
- Recognize risks around concurrent updates, deletes, TTL, write timestamps, and retries during copying.
- Establish verification criteria, rollback plans, and post-migration performance monitoring.
- Write a Java Driver 4.x example for paged backfills within bounded data windows.

## 1. Why not just use `ALTER TABLE` to change keys?

Cassandra allows certain schema changes, such as adding or dropping regular columns according to version rules and constraints. However, **primary key components** dictate row identity and how data is distributed across the cluster.

Example legacy table:

```sql
CREATE TABLE events_by_device_old (
    tenant_id   text,
    device_id   uuid,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

This creates one logical partition per **tenant–device pair**. To switch to one partition **per tenant–device–day**, the change is not merely adding a date column: the entire tuple used to compute tokens changes.

```text
Old key:
  partition key = (tenant_id, device_id)
  clustering    = (occurred_at, event_id)

New key:
  partition key = (tenant_id, device_id, event_day)
  clustering    = (occurred_at, event_id)

Consequence:
  same event -> token/replica set of the new partition
                may differ from the old token/replica set
```

**Do not** attempt the following expecting keys to change automatically:

- Running `ALTER TABLE` to "change the primary key" like modifying a regular column.
- Adding `event_day` only as a **regular column** and expecting Cassandra to split data by day automatically.
- Changing `CLUSTERING ORDER BY` to move a partition's placement in the token ring.
- Raising the replication factor, running compaction, or running repair to "split in half" a large partition.
- Adding `ALLOW FILTERING` to avoid redesigning the query path.

With a new key design, you need a **new table** and an explicit plan to transition read/write traffic. You can rename tables or version table names at the application layer, yet **renaming does not redistribute data**; the new table itself holds the new key structure.

## 2. Start from queries and symptoms, not from copying

Suppose an IoT system has these main query patterns:

- **Q1:** fetch the 100 latest events of a device in a day.
- **Q2:** fetch events of a device within a one-hour window.
- **Q3:** look up device history across multiple days, without requiring a single partition lookup.

The legacy table `events_by_device_old` worked fine when each device had few events. Once some devices write continuously, partition `(tenant_id, device_id)` can accumulate months of data, increasing storage cost, compaction, repair, and wide range scans.

Before changing the schema, document evidence:

| Assessment area | Questions |
| --- | --- |
| **Query patterns** | What percentage of queries read 5 minutes, one day, or many months? Are tenant and device always known? |
| **Data size** | What is the row/cell/byte distribution per partition, especially max and p99? |
| **Access skew** | Which devices/tenants generate most reads or writes? |
| **Retention** | Is there a TTL or business deletion? How long must old data be retained? |
| **Mutability** | Is event data immutable, updated in place, or deleted on demand? |
| **Consistency** | What are read-after-write requirements; how do clients retry after timeouts? |
| **Topology** | RF, data centers, replica placement, disk headroom, and background load? |
| **Rollout** | Can writes pause briefly or must migration run zero-downtime? Is there an event source for replay? |

**There is no fixed MB or row-count threshold** valid for every cluster. Goals should be expressed in measurable bounds: e.g., read p99 under SLO, peak-load partition size staying below load-tested warning thresholds, and cross-bucket fan-out staying within service request budgets.

## 3. Designing the new table around target queries

Create a new table splitting each device into partitions by UTC day:

```sql
CREATE TABLE events_by_device_day_v2 (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Comparison:

| Aspect | Old table | New table |
| --- | --- | --- |
| Partition key | `(tenant_id, device_id)` | `(tenant_id, device_id, event_day)` |
| Clustering columns | `occurred_at, event_id` | `occurred_at, event_id` |
| Partition shape | One device accumulates all history | One device has one partition per day with data |
| Reading one day | Slice by `occurred_at` in historical partition | Locate the exact day bucket and slice |
| Reading multiple days | One partition (yet potentially huge) | Multiple partitions; results must be merged |
| Intra-day write cost | All writes for a device hit one partition | All writes for a device **within a day** still hit one partition |

Switching to daily buckets **bounds accumulation duration** per partition, yet **does not guarantee** solving a hot partition if a device writes tens of thousands of events/second within the current day. Under heavy load, hourly/minute buckets or deterministic sharding may be needed, trading off more partitions read.

### Query Q1 on the new table

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_day_v2
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 100;
```

The table declares `occurred_at DESC`, so newer events for **that day** appear first in clustering order.

### Query Q2 within a daily range

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_day_v2
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 200;
```

This is one **partition lookup** and one clustering key slice. For ranges crossing a day boundary, the application must read **all relevant buckets**, then merge by `occurred_at` and `event_id`. `CLUSTERING ORDER BY` does not provide global order across partitions.

## 4. Defining key and payload mapping before migrating

A reliable migration requires a transformation rule **independent of execution time or processing order**.

Suppose source data contains:

```text
tenant_id   = acme
device_id   = 327a71e9-f562-4b54-94b9-2138a9e30b12
occurred_at = 2026-11-21T23:40:10Z
event_id    = 8817a208-1858-4144-86e9-b24d9083e478
event_type  = temperature
payload     = 38.1
```

Mapping rule:

```text
event_day = UTC_DATE(occurred_at)

old_pk = (
  tenant_id, device_id,
  occurred_at, event_id
)

new_pk = (
  tenant_id, device_id, event_day,
  occurred_at, event_id
)
```

No matter how many times the same event is reprocessed, `event_day` and the entire new primary key **must remain identical**. Never derive `event_day` from "the current date on the backfill runner" or an inconsistent default time zone.

### Invariants to verify

1. **Stable identifier:** `event_id` does not change across retries/backfills.
2. **Stable timestamp:** `occurred_at` is the established event time and is never recomputed.
3. **Consistent bucket:** writers, backfills, and readers all use the **UTC date** of `occurred_at`.
4. **Unaltered payload semantics:** target data reflects agreed fields, types, and transformation rules.
5. **No tenant leakage:** all read/write paths bind `tenant_id` from an authorized context.
6. **Uniqueness scope:** two distinct rows in the old table must never accidentally map onto the same full new primary key.

If a transformation maps **two different old keys onto one colliding new key**, Cassandra writes to the same logical row via upsert semantics, potentially losing data. Resolve key collisions **before** copying; do not treat `IF NOT EXISTS` as a fix for a broken mapping.

### Mapping table to catch edge cases

| Case | Risk | Decision |
| --- | --- | --- |
| Event at exactly 00:00 UTC | Misassigning previous/next day bucket | Standardize `[start, end)` intervals and UTC. |
| Event arriving two days late | Writer assigns it to today's write date | Compute from immutable event time. |
| Legacy payload missing columns | `null`/default values differ from expectations | Write explicit transformation rules. |
| Event timestamp edited after write | Target partition key can change | Define delete-old-key plus write-new-key workflow. |
| Account/device changes tenant | Source and target identifiers change | Design an explicit move workflow, not just updating regular columns. |
| Old key allowed the same ID multiple times | Maps to same new key and overwrites | Include required distinguishing column in new schema. |

## 5. Overview of a phased migration plan

For a system that must stay online, a typical framework includes:

```text
Assessment + v2 schema design
             |
             v
Create v2 table, deploy v2 read/write paths in controlled mode
             |
             v
Enable durable change capture (including deletes/updates)
             |
             v
Backfill historical data with checkpoints
             |
             v
Replay / reconcile all changes occurring during backfill
             |
             v
Shadow reads + data and performance verification
             |
             v
Gradual read/write cutover, monitor and keep rollback path
             |
             v
End rollback window, stop depending on legacy table
             |
             v
Drop legacy table per process after formal approval
```

This flow **is not a single transaction**. Many operations happen across different partitions, potentially on different replicas; clients can time out between steps. Thus, **progress checkpoints, replay mechanisms, and phase-gate criteria** are mandatory parts of the plan.

### Phase and gate table

| Phase | Action | Gate criteria to advance |
| --- | --- | --- |
| 0. Design | Finalize queries, new schema, TTL, mapping, capacity | Schema tests satisfy queries and partition size targets. |
| 1. Prepare | Create v2 table, deploy feature-flagged code, metrics | Zero impact on legacy production traffic. |
| 2. Capture | Record all changes needing sync from mark T0 | Mutations and deletes are replayable, with offsets/checkpoints. |
| 3. Backfill | Copy history by key/time window with rate limits | Steady progress, retryable errors, telemetry active. |
| 4. Catch up | Replay deltas from T0, reconcile versions | Lag within acceptable bounds, zero dropped changes. |
| 5. Verify | Shadow reads and result comparisons | Meets completeness, correctness, and SLO criteria. |
| 6. Cutover | Controlled read/write traffic switch | Rollback ready, continuous metric monitoring. |
| 7. Cleanup | Retire old path and clean up data | Rollback window closed, explicit operational sign-off. |

In small systems, a **brief write pause** can capture a quiescent snapshot, copy final deltas, and cut over. That is simpler but creates downtime. In large systems where writes cannot stop, reliable change capture or an event log is needed so no operations are missed during backfill.

## 6. The new table must be ready before data arrives

Deploy the new schema as an independent resource:

```sql
-- Verify the target schema was created in the appropriate keyspace:
DESCRIBE TABLE events_by_device_day_v2;
```

In a real plan, beyond the CQL `CREATE TABLE`, verify:

- **Keyspace replication strategy and RF** suit topology and fault-tolerance requirements.
- Default compaction/compression/TTL settings of the new table, if any, are tuned for the workload.
- Disk headroom suffices for **both data copies coexisting**, temporary SSTables during compaction, repair, and backfill operations.
- CQL permissions for application/backfill accounts are granted with **least privilege** on the new table.
- Drivers and schema metadata recognize the new table before enabling writes.
- Alerts and read/write metrics distinguish old and new tables.

Do not assume two tables in the same keyspace share identical byte distribution or latency. The new partition key changes tokens/replica sets; the cluster may need **time and resources** for compaction, streaming/repair, and cache warm-up.

**Important:** when Cassandra creates a new table, you do not "re-key" old SSTables via metadata. Every row desired in the new table must be **written into the new table** through a proper copy/replay pipeline.

## 7. Capturing live changes during backfill: dual-write and change capture

One of the hardest problems is the **race** between copying historical rows and ongoing writes.

Suppose backfill reads event E from the old table, and then a producer updates or deletes E while the copy stream is still running. If backfill writes the stale copy to the new table **after** that change, target data can become wrong.

### Option A: replayable event / change-data source

In systems with a properly operated event log/outbox/CDC, a safe approach is:

1. At timestamp **T0**, begin durably capturing **all changes affecting source data**, including creates, updates, and deletes.
2. Backfill historical state/rows from the old table in bounded windows.
3. Replay changes from T0 in an order sufficient to reconstruct target state, with **idempotency**.
4. Once caught up, establish a **write barrier** or controlled write handoff confirming processing up to the final **watermark**.
5. Run shadow reads, verify, and only then switch the read path.

**Note:** saying "CDC" does not automatically guarantee all operation types and ordering are captured. Verify the change source captures *deletes*, retries, offsets, and ordering needed by the data model. If only **inserts** are captured while business logic performs deletes/updates, replay will not reconstruct accurate state.

### Option B: application-level dual-write

During transition, writers can send matching mutations to **both old and new tables**:

```text
Business request E
        |
        +--> write old table
        |
        +--> write new table
        |
        +--> record state/offset to handle partial branch failure
```

However, **two independent writes do not form a cross-table atomic transaction**. Possible outcomes:

| Outcome | Situation |
| --- | --- |
| Old succeeds, new succeeds | Both tables accepted the mutation at their respective consistency levels. |
| Old succeeds, new times out | New **may or may not have written**; needs replay/idempotent retry. |
| Old times out, new succeeds | Old may or may not have written; must uphold source-of-truth rules. |
| Both time out | Cannot infer cluster state solely from client responses. |

Naive code like `writeOld(); writeNew();` is **not sufficient** when failures occur between steps. You need a durable event source, replayable outbox/queue, or a write-pause window for final sync. Never claim system-wide "exactly once" merely because Cassandra upserts on the same primary key.

### Defining the authoritative source per phase

An operationally clear convention:

- **Before cutover:** old table or source event log is the **source of truth**; new table is being populated and reconciled.
- **During cutover:** an explicit cutoff defines which writes belong to the new path and how in-flight/legacy requests are handled.
- **After cutover:** new table becomes the source of truth; rollback is permitted only while the old path still receives all required changes.

Never let individual instances decide "which table is right" based on unsynchronized feature flags. That can cause application-layer split-brain.

## 8. Historical backfill: bounded reads and recoverable checkpoints

Backfills must never run an unbounded `SELECT *` across the whole table from one client and hold results in RAM. With Cassandra, **enumerate source partition keys** and **clustering time windows** to read along supported key paths.

Suppose a tenant/device list is provided by the source system. For one device, read one hour from the old table:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_old
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

This query supplies the full old partition key and a clustering column range. The target bucket is computed via `event_day = UTC_DATE(occurred_at)`.

For large backfills:

- Partition work by **tenant/device + time window**; never assume one hour is small for every device.
- Use **driver paging** so entire results are not loaded in one response.
- **Bound concurrency/throughput**, especially on huge source partitions, to avoid degrading live traffic.
- Persist **durable checkpoints** at job/window or cursor level, marking completion only after all records in the window are written and acknowledged per policy.
- When a worker crashes, rerun incomplete windows using the **exact same full primary key**; copying must be identity-idempotent.
- If using paging state, do not treat it as permanent across schema/query/version changes; design an appropriate checkpoint rule.
- Categorize and track errors: invalid keys, serialization, ambiguous timeouts, tombstones, rate limits, schema mismatches.

### Never build the source key list via unbounded full-table scans

On legacy tables with huge partitions or terabyte datasets, finding every partition key via full-table CQL scans can be prohibitively expensive. Obtain worklists from catalogs/business registries, lookup tables, ingestion logs, or an evaluated bulk-export tool. Never assume an arbitrary device list is complete without checking: **worklist completeness is an independent verification requirement**.

A conceptual checkpoint format:

```text
job_id: migrate-device-day-v2
source_partition: ('acme', device-01)
window: [2026-11-21T08:00Z, 2026-11-21T09:00Z)
state: IN_PROGRESS | DONE | FAILED
rows_seen: 15720
rows_written: 15720
retry_attempts: 2
source_watermark: offset/sequence from event log if present
```

This is an illustrative format for operational tracking, **not a mandatory CQL table**. Mark `DONE` only once verification and window replay/reconciliation conditions truly pass.

## 9. Java Driver: example copying one data window

The Java Driver 4.x example below illustrates **key mapping and paged reading**. It suits understanding backfill mechanics for **immutable records without TTL and without concurrent deletes/updates**; it is not yet a complete production migration system.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class DeviceEventBackfill {
    private final CqlSession session;
    private final PreparedStatement readOld;
    private final PreparedStatement writeNew;

    public DeviceEventBackfill(CqlSession session) {
        this.session = session;

        this.readOld = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM events_by_device_old " +
            "WHERE tenant_id = ? AND device_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ?"
        );

        this.writeNew = session.prepare(
            "INSERT INTO events_by_device_day_v2 " +
            "(tenant_id, device_id, event_day, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    // Reads/copies a time slice bounded by the coordinator/orchestrator.
    // Checkpointing and replay source must live outside this illustrative method.
    public long copyWindow(
            String tenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        BoundStatement query = readOld.bind(
            tenantId, deviceId, startInclusive, endExclusive
        ).setPageSize(200);

        long copied = 0;

        for (Row row : session.execute(query)) {
            Instant occurredAt = row.getInstant("occurred_at");
            UUID eventId = row.getUuid("event_id");

            // Standardize bucketing rule: UTC date of event timestamp.
            LocalDate eventDay =
                occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

            session.execute(writeNew.bind(
                tenantId,
                deviceId,
                eventDay,
                occurredAt,
                eventId,
                row.getString("event_type"),
                row.getString("payload")
            ));
            copied++;
        }

        return copied;
    }
}
```

**What the example gets right:**

1. Reads the old table with the **full partition key**, bounded by a time range.
2. Uses `setPageSize(200)` so the query fetches pages through the driver.
3. Computes `LocalDate` from `Instant` using `ZoneOffset.UTC`, preventing timezone bucket shifts.
4. Preserves `event_id` and `occurred_at`; retrying the same data hits the **exact same new primary key**.
5. Uses `PreparedStatement` instead of string concatenation in CQL.

**What the example does not yet solve:**

- Synchronous row-by-row writes have limited throughput; production may need async writes with **bounded concurrency** and backpressure.
- It does not persist durable checkpoints or track up to which watermark a window was replayed.
- It does not preserve **TTL, write timestamps**, nor handle tombstones/deletes and concurrent updates.
- If writing to the new table times out, you cannot assume the write failed; safe retries require proper controls.
- If source data changes between SELECT and INSERT, the target can receive a stale snapshot; a replay phase and ordering rules are required.

**Do not use this method directly to declare migration success** if the source has deletes, TTL, concurrent updates, or strict reconciliation requirements.

## 10. Data correctness risks: TTL, timestamps, and tombstones

Moving a row from table A to table B is not simply reading live columns and running `INSERT`. Cassandra has semantics for **cell TTL**, **write timestamps**, **tombstones**, updates, and conflict resolution.

### 10.1. TTL: copying can accidentally extend lifetime

Suppose a source payload was written with a 30-day TTL and is already 25 days old. If backfill reads the payload and writes to the target without TTL, data can live **forever** in the target. If rewritten with a **30-day TTL from the backfill date**, it lives another 30 days, violating retention policy.

```sql
-- Example inspecting TTL and write timestamp of a regular column at source:
SELECT occurred_at, event_id, TTL(payload), WRITETIME(payload)
FROM events_by_device_old
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

`TTL(payload)` reflects the cell's remaining lifetime when TTL is active and the value is still live; different cells can have different TTLs. Choose a migration policy:

- **Preserve expiration time:** know the source retention deadline, compute remaining TTL at target write time, and skip/handle already-expired values.
- **Explicitly redefine retention:** only when business rules allow extending/shortening lifetime, with documented backfill rules.
- **Never copy expired data** just to match row counts; comparisons must check liveness at a consistent logical point.

Applying `USING TTL` on a new mutation does not automatically preserve per-cell TTLs of a source row. For data with uneven TTLs, plan per-cell handling or an appropriate reconstruction strategy.

### 10.2. Write timestamps: backfill can overwrite newer updates

Cassandra resolves cell value conflicts using **write timestamps** and accompanying rules. An old record backfilled **after** a newer update at the target can carry a higher timestamp and win over newer data, even though its content is older.

```text
08:00  Source has payload = A
08:05  Backfill reads payload = A
08:06  Writer updates payload = B in both tables
08:07  Backfill writes payload = A to new table with a fresh timestamp
       -> Risk of A overwriting B in the new table
```

Therefore, **ordering/fencing or versioning** is needed:

- For **immutable append-only** data without updates/deletes, idempotent copying is much simpler.
- For mutable data, maintain a versioned/offset mutation log and apply the latest version according to defined rules.
- You may need to preserve source timestamps or use business version numbers to prevent stale overwrites; using `USING TIMESTAMP` requires thorough understanding of TTL, tombstones, and conflicts, not blind application.
- The post-backfill delta replay phase must be designed so **business-newer** mutations are never overwritten by older snapshots.

### 10.3. Deletes do not appear as live rows in `SELECT`

When a user deletes a source event, a normal `SELECT` does not return a "deleted row" for backfill to copy the deletion. Tombstones still play their role in replication/repair and compaction.

If the target already holds an event and the source deletes it **during migration**, a backfill scanning only live rows cannot infer it must delete the corresponding target row. You need:

- **Delete capture** from a reliable source, replayed onto the new table.
- Or a **write/delete freeze window** long enough for final reconciliation, plus handling for earlier changes.
- Do not forget **whole-partition deletes**, range/slice deletes, cell deletes, TTL expirations, and business operations that alter primary keys.

Moreover, a stale copy and a tombstone having different write timestamps can prevent the delete from winning as expected. Test for **data resurrection** after replay/repair/compaction, especially if any replica missed a delete.

### 10.4. Static columns, collections, and counters

If the source table has **static columns** shared across an old partition, how is that metadata mapped when splitting one partition into multiple daily partitions?

- If metadata **truly belongs to the device**, a dedicated metadata table keyed by `(tenant_id, device_id)` may be clearer.
- If metadata **belongs per day**, it can be copied to corresponding daily partitions with explicit update rules.
- Multi-element collections or counter columns require specialized plans; **never** treat replaying increments as idempotent like `INSERT`ing an immutable payload.

Complex data types and semantics cannot be declared "correctly copied" merely because row counts look close.

## 11. Consistency, replication, LWT, and transaction limits

Several mechanisms are commonly mistaken as automatic migration guarantees:

| Tool / Mechanism | What it helps with | What it does not guarantee |
| --- | --- | --- |
| **Replication factor** | Maintains multiple copies across replicas per keyspace strategy. | Does not sync two tables or automatically change partition keys. |
| **`LOCAL_QUORUM` / suitable quorum** | Defines read/write acknowledgment level within relevant DC/topology. | Does not create an atomic transaction across two tables. |
| **Read repair / repair** | Helps reconcile replica divergence within Cassandra data. | Does not copy data from an old table to a new table under business mapping. |
| **LWT `IF NOT EXISTS`** | Prevents two clients from concurrently creating a full primary key when absent. | Does not preserve update/delete ordering across partition keys or tables. |
| **Logged batch** | Provides batch atomicity semantics and mutation recovery at operational cost. | Does not replace migration workflows, snapshots, reconciliation, or read cutover. |
| **`LIMIT` / paging** | Bounds responses or paginates the read path. | Does not shrink partitions or verify table-wide data completeness. |

Choose appropriate consistency levels per phase according to topology and SLOs. However, **never explain inconsistency between old and new tables as merely "stale replicas"**: the two tables are independent data structures and do not receive each other's mutations automatically.

If a business code must be created only once, evaluate the **uniqueness scope of the full primary key in the new table**. Adding or removing key components can change both duplication scope and `IF NOT EXISTS` behavior.

## 12. Data verification: multi-layered, not just row counts

A solid migration requires **repeatable reconciliation results** and agreed completion criteria before switching traffic.

### 12.1. Schema and query verification

- Does `CREATE TABLE` have the right column types, primary key, clustering order, and TTL/compaction policies?
- Do Q1/Q2 queries in the new schema provide the **full partition key**?
- Do `[start, end)` intervals and UTC buckets handle end-of-day/end-of-month boundaries accurately?
- Do multi-bucket queries merge with a stable comparator and bounded concurrency?
- Can feature flags route tenants/devices to the selected table version?

### 12.2. Windowed completeness verification

Reconcile using a `(tenant, device, day)` worklist:

| Check | Approach | Limitation |
| --- | --- | --- |
| Event counts per window | Use ingest/backfill stats or controlled counts over small scopes | `SELECT COUNT(*)` on huge partitions can impose heavy load. |
| Full primary key sets | Structured sampling or comparing key sets over a bounded window | Matching counts do not prove matching key sets. |
| Payload checksums | Normalize serialization/NULLs and hash in batches | Must standardize hashing, ordering, and TTL rules. |
| TTL / expiration | Check events near expiration, deleted, or expired via TTL | Liveness state changes over time. |
| Deletes / updates | Replay mutation logs and verify final state | Copying inserts alone is insufficient. |
| Read semantics | Shadow read Q1/Q2 on old/new and compare results | Two paths may differ in cross-bucket ordering; normalize first. |

**Never run `COUNT(*)` across an entire production table** and declare migration complete just because two totals are close. Combine **worklist coverage, change-log watermarks, targeted sample comparisons, and per-window telemetry**.

### 12.3. Shadow reads

The service layer continues returning responses from the old table while **reading the new table in shadow mode** for a sample of requests:

```text
Client query Q1
      |
      +--> old table -> return response to client
      |
      +--> new table -> compare internally, do not return to client
                         |
                         v
               metrics: match / mismatch / timeout
```

Normalize data using consistent logic: if the two tables differ in ordering or pagination boundaries while semantics match, do not compare raw JSON strings blindly. Verification must cover **empty queries, time boundaries, duplicate IDs, deletes/TTL, and late-arriving events**, not just small tenants with simple data.

Shadow reads add load to the cluster; apply sampling and concurrency bounds so testing does not trigger production errors.

## 13. Cutover: switching reads and writes step by step

Once backfill and replay meet criteria, shift traffic by tenant/device cohort or a consistently routable percentage of requests.

### Controlled switchover plan

1. **Confirm sync mark:** change log replayed up to the defined watermark, zero unresolved errors in the cohort being switched.
2. **Drain in-flight writes or use a write barrier:** prevent legacy-configured writes from slipping through after cutover.
3. **Enable the new read path at a small share:** start with a low-risk tenant/device group, watch mismatches and p99.
4. **Ramp up gradually:** increase traffic as metrics and data checks stay green.
5. **Maintain the rollback path:** if reverting to old remains an option, keep syncing changes from new to old or maintain a bidirectional-replayable event source per plan.
6. **Stabilize before cleanup:** retire legacy path, lock checkpoints and rollback retention before dropping old schema/data.

**Note on request percentages:** if requests for the same tenant alternate between old and new reads, pagination/cursor discrepancies can occur. Prefer **sticky routing by tenant, device, or session** and manage open requests rather than random per-request routing.

### Automatic rollout halt triggers

Example halt criteria (values are hypothetical policy, calibrate to SLOs):

- Data mismatches exceed agreed threshold.
- p99 latency or timeouts rise persistently compared to the legacy path.
- Backfill/replay rate falls behind ingestion, causing growing lag.
- Replica I/O, pending compactions, GC, or disk headroom exceed budgets.
- Cross-tenant authorization errors or bucket/shard mapping bugs appear.
- Deleted data resurrects or TTL extends beyond policy.

When a halt signal fires, **stop ramping traffic and investigate**; never hastily drop either the new or old table before understanding data state in each phase.

## 14. Rollback is not just flipping a read flag

Once the new table becomes the primary write target, simply "flipping the read flag back to the old table" can **lose visibility of recent writes** if the old table stopped receiving updates.

Decision matrix:

| State | How feasible is rollback? |
| --- | --- |
| Writes not yet switched; old is still source of truth | Can stop shadow reads / new path; old data was never bypassed. |
| Dual-write active and all mutations remain replayable | Can revert to old after verifying old caught up to watermark. |
| Stopped writing old; only new receives data | Requires reverse delta backfill/replay or a new migration pass. |
| Dropped old data / legacy table | Fast rollback impossible; must restore from snapshots/backups if policy permits. |

A good rollback plan must specify:

- **Who** is authorized to trigger rollback and under what conditions?
- **Which table is source of truth** in each phase?
- **Which watermark/offset** must be reached before switching back?
- Have **TTL/deletes/updates** been synchronized to the rollback path?
- Are **client paging tokens/cursors** compatible when switching read paths?
- When does the rollback window **expire**, permitting cleanup of legacy resources?

The goal is preventing accidental "reading old while writing new" states, or some instances reverting to old while others continue serving the new schema.

## 15. Resource monitoring during migration

In many large migrations, failures stem not just from bad data, but from backfills **overloading the cluster**.

| Metric group | Purpose |
| --- | --- |
| **Source read latency / target write latency** | Detect whether backfill is slowing down live applications. |
| **Backfill rate (rows/s, bytes/s)** | Measure actual copy speed and estimate remaining work. |
| **Checkpoint progress and retry error counts** | Spot stuck workers, repeated reads, or skipped windows. |
| **Change-log / replay lag** | Measure how far the target lags behind the source of truth. |
| **Production p95/p99/timeouts** | Decide whether to throttle backfill or pause rollout. |
| **SSTables per read / tombstone scans** | Detect read amplification and costly deleted data. |
| **Pending compactions / disk headroom** | Monitor backlog and temporary space while both tables coexist. |
| **Per-node/replica CPU/GC/network/I/O** | Detect hot sources or skewed target distribution. |
| **v2 partition size/cell histograms** | Confirm the new schema genuinely shrinks the large-partition tail. |
| **Shadow mismatches / permission failures** | Validate data accuracy and multi-tenant isolation. |

Typical table-level inspection commands (depending on Cassandra version):

```bash
nodetool tablestats app_ks.events_by_device_old
nodetool tablestats app_ks.events_by_device_day_v2

nodetool tablehistograms app_ks events_by_device_day_v2
```

Interpret outputs within **node and version scope**; do not treat histograms as exact instantaneous counts of all live partitions. Backfilling also does not cause Cassandra to automatically move old data from an SSTable into the new table: new mutations create new storage files and undergo compaction later.

### Backpressure and load management

- Bound concurrent windows per tenant/device and per node.
- Start with small tenants first to catch mapping bugs and validate tooling, rather than starting with the hottest tenant.
- Reserve capacity for production queries; automatically throttle down when p99, I/O, or compaction backlog exceed budgets.
- Never use giant batches just to cram more rows per request; benchmark mutation/batch cost and real throughput.
- On network/timeout errors, retries must **preserve the exact full primary key** with backoff, never generating a new ID or bucket.

## 16. Scenario exercise: changing keys to avoid large partitions

An event management platform has a legacy table:

```sql
CREATE TABLE user_events_old (
    tenant_id   text,
    user_id     uuid,
    event_time  timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY ((tenant_id, user_id), event_time, event_id)
);
```

Each user can emit **10 events/second**, logical payload **700 bytes/event**, with **30-day retention**. The system continues receiving writes during migration. The new primary query reads one user within **one day**.

Proposed new table:

```sql
CREATE TABLE user_events_by_day_v2 (
    tenant_id   text,
    user_id     uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        event_time,
        event_id
    )
);
```

**Questions:**

1. Why not just add `event_day` to the old table via `ALTER TABLE ADD`?
2. If a user generates 10 events/second for 24 hours, roughly how many rows and how much logical payload is expected per daily partition?
3. With 30-day retention, how many rows could the old partition accumulate without other limits?
4. If backfill uses the **current date** to compute `event_day` for old events, what bug occurs?
5. If dual-write succeeds on old and times out on new, can you conclude the new table does not have the row?
6. If event E was deleted from old during backfill, does copying only live rows from `SELECT` ensure E is deleted in v2?
7. Why can rewriting a 30-day TTL when backfilling a 25-day-old event be wrong?
8. Do `LIMIT 100` and driver paging prove all rows were migrated?
9. If cutover wrote only to v2 for 2 days and then rolled back reads to old, what could be missing?
10. What conditions must be checked before dropping `user_events_old`?

**Suggested answers:**

1. Because `event_day` must become a **new partition key component**. Adding a regular column does not change tokens/partitions of existing data.
2. `10 × 86,400 = 864,000 rows/day`; payload `864,000 × 700 = 604,800,000 bytes ≈ 576.8 MiB`, excluding overhead and replicas.
3. `864,000 × 30 = 25,920,000 rows` in one user partition without TTL/deletes or another splitting mechanism; this is a calculation exercise.
4. Events get written to the wrong bucket; readers querying the event date miss the partition, or multi-day events pile into today's bucket.
5. **No.** A client timeout can happen after the cluster already applied the mutation; verification/idempotent retry is needed.
6. **No.** `SELECT` does not return delete mutations as live rows; delete replay or controlled reconciliation is required.
7. A fresh TTL from backfill time extends the event's lifetime beyond the intended retention if elapsed age is not subtracted.
8. **No.** They only control response/paging, not worklist coverage, mutational correctness, or absence of missing rows.
9. The old table may miss events from the last two days; rollback requires reverse sync or replay so old catches up.
10. Verify data parity, watermarks/replay, SLOs, all clients switched, zero remaining dependencies, rollback window closed, and approved cleanup sign-off.

### Extended design exercise

Write a plan comprising **one migration task table** and **two feature flags**:

- A flag controlling the source of truth / write path.
- A flag controlling the primary read path and shadow reads.

In the plan, show how to guarantee no **late-arriving events**, **updates**, or **deletes** are lost, and how to measure impact on active tenants' p99 latency. The goal is not picking one CQL statement, but building a process **recoverable after failures**.

## 17. Pre-completion deployment checklist

- [ ] Schema v2 created with proper primary key, clustering order, TTL/compaction, and replication.
- [ ] Old → new mapping function tested for UTC timestamps, day boundaries, and key collisions.
- [ ] Complete source worklist, partition/time windows, and durable checkpoints established.
- [ ] Capture and replay for creates/updates/deletes during backfill; ordering and semantics tested.
- [ ] Clear rules for preserving or transforming TTL, write timestamps, tombstones, and static/collection metadata if used.
- [ ] Backfill uses paging, bounded concurrency, throttling, safe retries, and progress metrics.
- [ ] Reconciled by key/window, shadow-read primary queries, and resolved mismatches.
- [ ] Change stream caught up to required watermark; in-flight writes drained/controlled.
- [ ] Cutover has owner, runbook, timeline, halt thresholds, and p95/p99/timeout monitoring.
- [ ] Rollback path still sees all post-cutover data; not merely flipping a flag.
- [ ] Retention and drop schedule for legacy table approved after rollback window closes.
- [ ] Never treat "copy finished" as sufficient proof that data is accurate or the system is ready.

## 18. Key takeaways

- **Changing a partition key or clustering key** in Cassandra typically requires **creating a new table and migrating**, because keys govern row identity, tokens, replica sets, and query paths.
- **New schemas must start from queries**: e.g., adding a day bucket to the partition key makes partitions shorter, yet requires fan-out and merging for multi-day queries.
- **Immutable identifiers** — tenant, device, event time, event ID, and bucket — are the foundation so retries/backfills do not create duplicate rows.
- **Backfill does not automatically sync concurrent writes**: you need change capture, replay, fencing/watermarks, and verification; naive dual-writes can fail partially.
- **TTL, tombstones, write timestamps, and updates/deletes** are data correctness risks, not minor details to ignore.
- **Consistency levels, replication, compaction, and repair** each have specific roles; they do not turn two tables into one transaction or alter primary keys in place.
- **Cutover and rollback** must rest on the authoritative source of truth, replay progress, and observable criteria, not merely toggling a feature flag.
- **Completing a migration** means data, queries, latency, rollback, and operations all meet agreed criteria; copying visible rows is only one step.

With a migration plan combining a new schema, consistent mapping, controlled backfill, change capture, and data reconciliation, a Cassandra system can improve partition shape while continuing to serve CQL operations and Java applications in a distributed environment. This approach also provides a safe foundation for further optimizing replication, compaction, repair, and error handling after data has moved to the new key design.
