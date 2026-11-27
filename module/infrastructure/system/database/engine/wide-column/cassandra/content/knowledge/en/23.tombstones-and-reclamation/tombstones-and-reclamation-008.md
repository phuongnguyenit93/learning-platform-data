# Mixed-TTL Data and Hard-to-Reclaim SSTables

> **Chapter:** Tombstones and Reclamation  
> **Scope:** Apache Cassandra — a distributed *wide-column* database — focusing on TTL lifecycle, tombstones, SSTables, and compaction. Examples use CQL, node administration tools, and Java Driver 4.x.

## 1. Scenario: TTL expires yet disk usage does not drop

A device event-collection system stores two record types:

- Detailed events: needed for only **1 day** for live display and immediate investigation.
- Important events: needed for **30 days** for customer support.

Both types are written into **the same Cassandra table**, sharing the same partition key by device and day. The system sets `USING TTL 86400` for short-lived records and `USING TTL 2592000` for long-lived records.

After two days, queries no longer return the one-day TTL events. However, SSTable counts and disk usage remain high. "Being expired" and "being deleted from SSTable files" are **two different events**.

Suppose two mutations were flushed into the same SSTable:

```text
SSTable S1 (illustrative example)
┌─────────────────────────────────────────────────────────┐
│ event A  | TTL 1 day   | expires Day D+1  | expired     │
│ event B  | TTL 30 days | expires Day D+30 | still live  │
│ event C  | TTL 1 day   | expires Day D+1  | expired     │
└─────────────────────────────────────────────────────────┘

Day D+2:
- SELECT no longer returns A, C per TTL rules.
- B is still live -> S1 cannot be dropped wholesale just because A, C expired.
- Reclaiming A, C requires eligible compaction to rewrite an SSTable
  with only retained data; grace and tombstone safety also apply.
```

Here is the core point of this lesson:

> **An SSTable holding data with different lifetimes may fail to reach the "completely expired" condition for a very long time.** Even when most bytes inside the file have expired by TTL, Cassandra cannot delete the entire file while live data still sits inside.

Do not conclude "TTL is not working" solely because the data directory size has not decreased.

## 2. At what level does TTL operate in Cassandra?

Cassandra uses TTL (*time to live*) to bound the lifetime of data. A mutation's TTL is counted in **seconds** and applies to the valued cells written by that mutation, according to supported structures/data types. The primary key identifies the row; do not assume each primary key component is an independent cell that expires the same way a data column does.

Example:

```cql
INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111, 'detail')
USING TTL 86400;
```

With `payload` written with a one-day TTL, after expiration the value is no longer treated as live data in read results. Expiration creates **logical deletion** semantics; TTL/expiration metadata must continue to be handled as deleted data until eligible for physical reclamation.

A mutation does not always expire every column in a row. For example, if only `payload` is updated with a TTL, columns not rewritten in that mutation can retain a different TTL or no TTL at all.

### Three milestones to distinguish

| Milestone | Meaning | Does disk space drop immediately? |
| --- | --- | --- |
| **Write time** | Cassandra accepts the mutation, attaches appropriate TTL/expiration metadata | No |
| **TTL expiration time** | Cell is no longer logically live; normal reads do not return that value | **No** |
| **GC/compaction reclamation time** | SSTable is rewritten or a fully expired file is dropped when safety conditions hold | **May** reduce space, depending on snapshots/backups, compaction, and filesystem |

For example, event A is written at 10:00 on Day D with a one-day TTL. A logically expires around 10:00 on Day D+1; it does not necessarily vanish from the SSTable then. `gc_grace_seconds`, other write versions, overlapping SSTable sets, and compaction continue to affect reclamation timing.

### What do `TTL(column)` and `WRITETIME(column)` check?

In CQL, you can view the remaining TTL seconds and write timestamp of a column:

```cql
SELECT payload, TTL(payload), WRITETIME(payload)
FROM lab.telemetry_mixed_ttl
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21';
```

While the cell is live, `TTL(payload)` shows the remaining seconds (approximately at read time); for a cell without TTL, the TTL result is typically `null`. Once the cell expires, it is not returned as a live value, so **you cannot use `TTL(column)` after expiration to inventory all physical tombstones**.

`WRITETIME` is the timestamp of the cell value being read; it does not tell you which SSTable holds the cell or which compaction will clean it.

## 3. Why does mixing TTLs make SSTables hard to reclaim?

### 3.1. SSTables are immutable files

Data in memtables is flushed into immutable SSTables. One SSTable can hold millions of cells from many partitions, cells with varying TTLs, and data with no TTL at all. Cassandra **does not erase individual bytes inside an SSTable the moment a cell expires**.

When live cells and expired cells coexist in the same SSTable, there are generally two paths:

1. **Keep the SSTable** awaiting compaction, because it still contains live data.
2. **Compact the SSTable** with related files, drop data eligible for GC, and write a new SSTable; old files are freed only after the new file safely replaces them.

The second path costs read and write I/O, CPU, temporary disk space, and can put pressure on query performance during compaction.

### 3.2. Conditions for *whole-SSTable expiration*

With uniform and suitable TTL workloads — especially using **TimeWindowCompactionStrategy (TWCS)** — Cassandra can detect when an entire SSTable has expired and drop the file without rewriting every row.

However, "completely expired" is a stronger condition than "most rows expired":

- **No live data left to retain** in the SSTable.
- Required deletion markers/TTLs are eligible for reclamation under the version's and configuration's GC rules.
- Dropping the file is safe with respect to data/versions that may remain in other SSTables, as well as repair/replica conditions.
- The file is not held by another mechanism such as storage-level snapshots/hard links.

Therefore, even a single 30-day TTL cell mixed into an SSTable composed mostly of 1-day TTL data can push the time that SSTable qualifies for whole-file deletion far into the future.

**Do not confuse "eligible to drop file" with "file definitely deleted right now."** Actual cleanup time also depends on compaction strategy, check schedules, node state, and SSTable management mechanics.

### 3.3. Quantitative example

Suppose SSTable S1 is created on Day D with data:

| Component in S1 | Illustrative size | TTL | Logical expiration |
| --- | ---: | ---: | --- |
| Detailed events | 900 MiB | 1 day | D+1 |
| Important events | 100 MiB | 30 days | D+30 |
| **Total** | **1,000 MiB** | **Mixed TTL** | **No single shared expiration date** |

On Day D+2, **90% of the data in the example has expired**, yet 100 MiB of live data can prevent the entire 1,000 MiB file from being dropped whole. The 900 MiB portion can only be reclaimed when suitable compaction runs, deletion conditions are met, and it completes safely.

These numbers are illustrative, not an optimal ratio or real performance forecast. If compaction is not triggered early, physical storage can approach the lifetime of the longest-lived data, plus grace/operational overhead.

## 4. What write patterns produce a mixed SSTable?

Mixed TTLs do not necessarily come from two different tables. Common causes:

| Cause | Example | Consequence |
| --- | --- | --- |
| Two record groups in the same table | Normal events `TTL 1 day`, important events `TTL 30 days` | SSTable receives mutations with vastly different expiration times |
| Same row, columns with different TTLs | `summary` has short TTL, `audit_ref` lives long | One row holds live cells mixed with expired cells |
| Different default TTL vs. explicit TTL | Table `default_time_to_live=86400`, some mutations written with another TTL per version/syntax | Data gets scattered across multiple lifetimes |
| Presence of **non-TTL** data | Most events have TTL, a few records never expire | SSTable holds very long-lived live data, never qualifying for whole expiration |
| Updates, late writes, or backfills | Writing new data to old partitions, late-arriving timestamps | Data generations end up in non-uniform compaction files/groups |
| Repair/streaming | Data or SSTables streamed across replicas | Must re-evaluate SSTable layout and overlap; never assume files stay pure to one TTL range |

In particular, a table with `default_time_to_live` does not guarantee all records actually expire together. Different write times produce different expiration times; adding explicit TTLs different from the default stretches the distribution even further.

## 5. Tombstones, `gc_grace_seconds`, and old versions

When a TTL expires, the cell is no longer logically live. Yet in distributed Cassandra with **multiple replicas** and immutable SSTables, deletion metadata still serves to prevent old values from being seen as live data.

### `gc_grace_seconds` is not a file deletion time

`gc_grace_seconds` is a table-level setting creating a **protection window** for tombstone reclamation. Example:

```cql
CREATE TABLE lab.telemetry_mixed_ttl (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
```

The value 864000 seconds is an **illustrative 10 days**, not a default mandate for every cluster. A one-day TTL record can expire logically on Day D+1, yet deletion/expiration metadata must still be retained per GC policy.

However, tombstones past grace **only become reclamation candidates**: compaction or an appropriate SSTable-drop mechanism must still run, while ensuring old data in other SSTables/replicas cannot reappear.

### Why retain deletion markers?

Suppose RF=3 and replica C is offline when a row is deleted on A, B:

```text
T0  A, B, C all hold row v1
T1  C offline; DELETE received by A, B -> tombstone
T2  A, B purge deletion marker before C is synced
T3  C returns, still holding row v1
T4  Read/repair may bring row v1 back -> zombie data
```

This is the classic risk of purging tombstones before all necessary replicas have been reconciled. Hinted handoff has a time limit and does not replace repair; a command's CL does not prove every replica received the marker either.

With **pure TTL**, any replica that received the cell with the right TTL can determine its expiration independently; hence immutable write-only workloads with uniform TTLs have better reclamation optimization opportunities than arbitrary deletes/updates. Still, if replicas miss mutations, have overwritten versions, clock/timestamp skew, or manual deletes, you must maintain safety based on grace, SSTable overlap, and repair. Never set `gc_grace_seconds=0` as a blanket rule merely because a table uses TTL.

### Why does SSTable overlap still matter?

Suppose you have:

```text
SSTable S_old: payload='v1' @timestamp 100
SSTable S_new: DELETE payload @timestamp 200 (already past gc_grace)
```

If compaction only processes `S_new` and drops the tombstone while `S_old` still holds v1, v1 can become exposed again. Cassandra must consider information about **other SSTables that might hold shadowed values** before deciding to purge.

Mixed-TTL cases complicate this in two directions: live cells block whole-SSTable drops; expired data/markers must wait for eligible compaction to be cleaned at the cell level.

## 6. Role of compaction strategy

### STCS — SizeTieredCompactionStrategy

STCS typically groups SSTables of similar size. Mixed-TTL SSTables are retained until they participate in an eligible compaction or fully expire under safety conditions.

**Notable point:** when a file is picked for compaction depends primarily on size and file-count policies, not the wish to "clean right when TTL expires." An SSTable already full of dead cells may not be selected yet, keeping disk usage from dropping as expected.

### LCS — LeveledCompactionStrategy

LCS manages SSTables in levels, reducing overlap within levels and potentially improving the number of files read. However, LCS still has to rewrite SSTables during compaction and obey safe deletion rules. It **does not** guarantee data with different TTLs is cleaned on the exact expiration day.

### TWCS — TimeWindowCompactionStrategy

TWCS organizes compaction into time windows, suited to **time-ordered, mostly append-only time-series streams with relatively uniform TTLs**.

When data in the same window shares similar lifetimes, all SSTables in the window can expire around the same time. This increases the chance of dropping **whole files** at low cost.

Conversely:

```text
Window W1: data written the same day
  95% TTL 1 day
   5% TTL 30 days

All of window W1 still has live data until around D+30.
TWCS cannot drop the SSTable just because 95% of rows expired.
```

Time-based compaction windows **do not separate data by retention policy**. If business logic mixes short and long TTLs in mutations falling into the same window, TWCS still receives mixed SSTables.

### Late-arriving data issues

TWCS makes key assumptions about write time/timestamps. Late-arriving data, updates to old rows, backfills, or mutations with widely differing timestamps can put data of different windows/ages into the same SSTable. Therefore:

- Do not evaluate TWCS solely because an `event_time` column exists.
- Verify the workload is mostly append-only, with low update/delete rates and relatively uniform TTLs.
- Have a separate strategy for backfills and late-arriving events.
- Measure actual SSTable expiration, compacted bytes, and tombstone reads.

### Comparison summary

| Strategy | Under mixed TTLs | Operational meaning |
| --- | --- | --- |
| STCS | SSTables may hold TTL-expired records until joining an eligible compaction | Monitor tombstones and unreclaimed space |
| LCS | Can reconcile versions across levels; still must process live cells | Trade-off among read/write/space amplification |
| TWCS | Strong when one window has uniform data age/TTL; poor if mixing short and long TTLs | Prioritize separating retention and avoiding late writes that break assumptions |

No compaction strategy turns an SSTable still containing live data into a safely droppable file just because most cells expired.

## 7. CQL practice: creating mixed-TTL data

The commands below use an **existing `lab` keyspace** on a test cluster; data, timestamps, and UUIDs are illustrative. Never run TTL/compaction changes in production without evaluating capacity, repair, and SLOs.

### Step A — Create table

```cql
CREATE TABLE IF NOT EXISTS lab.telemetry_mixed_ttl (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
```

Partition key `(device_id, event_day)` supports querying events by device/day. It **does not** guarantee data within a partition shares the same TTL.

### Step B — Write two different lifetimes

```cql
INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111, 'short-lived')
USING TTL 86400;

INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:01:00Z',
   22222222-2222-4222-8222-222222222222, 'long-lived')
USING TTL 2592000;
```

Note that `event_time` is business data; **TTL counts from mutation write time / TTL mechanics**, not directly from the `event_time` column. If you run this test many days after the date in the example, both rows **still receive fresh TTLs starting from your test write time**.

### Step C — Observe remaining TTL

```cql
SELECT event_time, event_id, payload, TTL(payload)
FROM lab.telemetry_mixed_ttl
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21';
```

Initial results should show two rows with different TTLs. After more than a day, the `short-lived` row is no longer considered live and usually disappears from results; the `long-lived` row lasts nearly 30 days from write time.

**Read results do not tell you which SSTable files are eligible to drop.** To inspect how data was flushed and grouped, use metrics/SSTable tools on the test node.

### Step D — Observe memtables, SSTables, and compaction

Example inspection commands on a lab node:

```bash
nodetool tablestats lab.telemetry_mixed_ttl
nodetool compactionstats
```

Metrics vary by version, but generally check SSTable count, disk space used, flush counts, pending/active compactions, and tombstones scanned. Cross-reference metrics/JMX, controlled CQL tracing, and SSTable metadata if your version provides suitable tools.

To demonstrate data getting flushed:

```bash
nodetool flush lab telemetry_mixed_ttl
```

There is no guarantee these two mutations land in a single separate file: replicas, flush timing, background compaction, and other SSTables can change the layout. The hypothesis "mixed TTLs in the same SSTable" should be **verified using node metadata/tools**, never assumed from two `INSERT` statements alone.

Do not run `nodetool compact` repeatedly to "force-clean TTL." Compaction can generate heavy I/O and temporary space usage while GC conditions or long-lived data still block full reclamation.

## 8. Redesigning around retention policies

When you have two vastly different TTL groups, a useful approach is **separating retention classes into distinct tables**, or at least separating write streams so each SSTable has a more uniform lifecycle.

### Option A — Two tables by retention

Example separating 1-day detailed data and 30-day important data:

```cql
CREATE TABLE lab.telemetry_recent (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 86400
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'HOURS',
      'compaction_window_size': '6'
  };

CREATE TABLE lab.telemetry_retained (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
```

Both `compaction_window_size` values are **illustrative test values**. Optimal windows depend on write rate, TTL, SSTable size, traffic, and late-arriving data. With multiple retention classes, separate tables let you design and operate each class for its access pattern.

For important events that must also show up on the real-time screen, the application can write them to **both tables**, if both read paths require it. When dual-writing, handle idempotent retries, partial failures where one table succeeds and the other fails, and reconciliation. Cassandra does not automatically sync independent business tables.

### Option B — Do not duplicate if unnecessary

If you only need to query important events for 30 days, you can write **only** to `telemetry_retained` and have the application query two tables depending on the screen. Duplicating every event is not always required.

Define the read contract clearly: does "display all events in 24 hours" require merging both streams? If so, weigh reading two tables and merging in the application versus writing an extra projection.

### Option C — Time bucketing to control partition size

The partition key `(device_id, event_day)` in the example bounds partition size by day. However, bucketing **does not replace separating retention**: if each bucket still contains both 1-day and 30-day TTLs, an SSTable holding that bucket's data can still carry mixed TTLs.

For devices emitting millions of events/day, hourly buckets or sharding may be needed to avoid hot/oversized partitions. The rule remains choosing keys for **queries and load distribution**, not solely for GC wishes.

### Decision comparison

| Option | Pros | Cost / risk |
| --- | --- | --- |
| Single table, different `USING TTL` per row | Simple implementation, single read source | Mixed TTLs; compaction must rewrite to drop dead cells; can retain SSTables long |
| Two tables by retention | SSTables easily achieve uniform lifecycles; independent TWCS tuning | More tables and read/write ops; may require reconciliation across projections |
| Single table with uniform TTL and pre-aggregation | Can reduce bytes and GC complexity | Loss of detail or requires aggregation pipeline / different data architecture |
| Partition by bucket and retention class | Bounds partitions, routes queries cleanly | Multi-bucket/class queries may require application-side merging and paging |

**Practical rule:** When TTLs differ by **orders of magnitude** (for example, hours vs. months), measure storage and compaction costs of the single-table design before adopting it by default.

## 9. Java Driver 4.x example: writing by retention class

A Java application can determine retention by business event rather than letting callers pass an arbitrary uncontrolled TTL.

Example using `lab.telemetry_mixed_ttl` when illustrating the distinction:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TelemetryWriter {
    public enum Retention {
        QUICK(86_400),
        IMPORTANT(2_592_000);

        private final int ttlSeconds;

        Retention(int ttlSeconds) {
            this.ttlSeconds = ttlSeconds;
        }

        public int ttlSeconds() {
            return ttlSeconds;
        }
    }

    private final CqlSession session;
    private final PreparedStatement insert;

    public TelemetryWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO lab.telemetry_mixed_ttl " +
            "(device_id, event_day, event_time, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public UUID write(
            String deviceId,
            LocalDate eventDay,
            Instant eventTime,
            String payload,
            Retention retention) {

        UUID eventId = UUID.randomUUID();
        BoundStatement statement = insert.bind(
                deviceId,
                eventDay,
                eventTime,
                eventId,
                payload,
                retention.ttlSeconds())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(statement);
        return eventId;
    }
}
```

The code assumes `CqlSession` is configured for the right keyspace/cluster and the table already exists. `LOCAL_QUORUM` is just an example consistency level; choose in practice based on replication factor and system requirements.

If business logic needs retries after timeouts, generate `eventId` **before** executing and keep the same ID across retries of **the same event**. Generating a new UUID on every retry as in this simple method can create duplicate logical rows. Also note that rewriting the same cell with a TTL can **shift the cell's expiration time**; business idempotency cannot be inferred simply from reusing the same key. When TTL must be measured from the original event time, define clear policies for retries/backfills and timestamps/expiration.

When splitting into two tables with `default_time_to_live`, Java can use two prepared statements targeting fixed tables rather than dynamically interpolating table names in one prepared CQL statement. This structure prevents callers from picking TTLs outside the agreed retention policy.

## 10. Measuring storage and causes of unreclaimed space

To pinpoint the real issue, answer these questions in order:

1. **Has the data logically expired?** Inspect sample rows via `SELECT`/`TTL` before expiration and verify TTL policies.
2. **Do SSTables contain unexpired TTL or non-TTL data?** Measure write lifetime distributions and check metadata in an appropriate environment.
3. **Has the GC threshold passed and has suitable compaction run?** Inspect `gc_grace_seconds`, compaction strategy, pending compactions, and SSTable creation times.
4. **Do other SSTables hold versions shadowed by tombstones?** Evaluate overlap and update/delete workloads.
5. **Are there absent/unrepaired replicas?** Do not change GC assuming all replicas are always synced.
6. **Is disk space being held by snapshots/backups?** On filesystems supporting hard links, snapshots can keep old files even after Cassandra replaces SSTables on the active data path.

### Metrics to measure

| Signal | Interpretation |
| --- | --- |
| `Live disk space used` and `Total disk space used` per table (if emitted by version) | Distinguish active data from retained storage footprint |
| Number of SSTables, size of each SSTable | See if many uncompacted files or huge files exist |
| Tombstones scanned on read | Identify read cost from dead data even when queries return few rows |
| Pending/active compactions, bytes compacted, write amplification | See whether the cluster has opportunity and resources to clean data |
| Short/long TTL ratio and bytes written/day | Estimate how much short-lived data is "kept alive" by long-lived data |
| Repair schedule, offline nodes, hints, and I/O errors | Ensure distributed reclamation conditions hold |
| Snapshot/backup retention and disk headroom | Explain why OS has not returned free space yet |

Observe multi-day trends and compare against TTL schedules. For instance, if 30-day data is still live, on day three you cannot expect all SSTables holding it to be dropped.

### Estimating storage by retention class

Suppose you write 100 GiB/day at 1-day TTL and 2 GiB/day at 30-day TTL:

- In terms of **live data**, near steady state there is roughly `100 × 1 + 2 × 30 = 160 GiB` before accounting for replicas, compression, tombstones, and operational overhead.
- If both classes are interleaved and many SSTables stay alive until the long TTL's lifecycle, **physical** disk usage can be far higher than 160 GiB while compaction/GC has not yet reclaimed the short-lived portion.

This is a model to reveal risk, **not an exact formula to forecast Cassandra disk usage**. Actual capacity also depends on RF, compaction strategy, gc grace, tombstones, compression, snapshots, backups, and write cadence. When sizing clusters, always distinguish logical bytes from per-replica bytes and OS-retained bytes.

## 11. Safe diagnostic workflow when disk grows

### Case A — Reads do not see 1-day TTL records yet disk does not shrink

**Likely explanation:** records expired logically; SSTables still hold 30-day TTL data or have not been compacted/GC'd yet.  
**What to do:** check retention distribution, SSTable metadata, compaction, and snapshots. Never delete SSTables manually.

### Case B — High tombstones scanned and rising read p99

**Likely explanation:** queries traverse many expired cells; partition or clustering range is too wide.  
**What to do:** fix access patterns/partition bucketing, consider separating retention classes, evaluate suitable compaction, and re-measure p95/p99.

### Case C — Using TWCS yet SSTables persist very long

**Likely explanation:** short/long TTLs mixed in the same window, late-arriving data, updates to old data, or files holding non-TTL data.  
**What to do:** analyze write groups, window size, timestamps, backfills, and live data ratio; TWCS does not solve mixed TTLs on its own.

### Case D — Tempted to lower `gc_grace_seconds` to clean fast

**Risk:** purging tombstones too early in a system where replicas missed deletes, repairs are incomplete, or overlapping SSTables remain can cause zombie data.  
**What to do:** prove safety using RF, potential replica offline duration, repair schedules, and workload traits before changing policy; never apply 0 arbitrarily.

### Case E — Compaction finishes yet OS disk usage does not drop

**Likely explanation:** files are held by snapshots/backups, compaction still outputs large files due to live data, or other files continue receiving writes.  
**What to do:** inspect live/total stats, snapshot retention, and disk headroom per operational procedures; never delete Cassandra files by hand.

## 12. Architecture choices for production systems

Use the decision table below before choosing one table vs. multiple tables:

| Question | If the answer is "yes" | Direction to take |
| --- | --- | --- |
| Do TTLs differ vastly, e.g., hours vs. months? | Many rows expire much earlier than the rest | Prioritize testing table separation by retention |
| Is workload append-only with relatively sequential timestamps? | Opportunity to group SSTables by time window | Evaluate TWCS and suitable window sizes |
| Are there many updates/deletes/backfills on old data? | Overlapping SSTables and hard-to-align TTL milestones | Try STCS/LCS or redesign streams; benchmark carefully before TWCS |
| Must queries merge both event classes? | Splitting tables may complicate APIs | Evaluate merge/read models or projections; document paging constraints |
| Does data expire by TTL while partitions still keep live rows? | Part of SSTable cannot drop whole-file | Monitor compaction and consider separating retention |
| Are repairs / replica offline handling unstable? | Cannot safely shorten grace | Fix repair/recovery processes first |
| Are write SLOs sensitive to compaction I/O? | Rewriting mixed SSTables causes write amplification | Design data to make whole-SSTable drops easier |

Separating data by retention must be evaluated alongside Cassandra's **query-driven table design**. Do not spawn dozens of tables just for "easy garbage collection" if APIs would have to fan out across many tables, buckets, and datacenters; balance read, write, operational, and data consistency costs.

## 13. Misconceptions to avoid

**"TTL expiration means bytes vanished from SSTables."** False. Expiration stops logical liveness; physical reclamation can lag far behind.

**"90% of data in the SSTable expired by TTL so the whole file can be deleted."** False. If 10% remains live, deleting the whole file loses data that must be kept.

**"TWCS always solves multi-TTL tables."** False. TWCS groups by time window; it does not split by TTL length.

**"Partitioning by day ensures each SSTable holds only that day's data."** False. One SSTable can hold many partitions and many days; partition keys and SSTable boundaries are separate layers.

**"`gc_grace_seconds` is the mandatory time files get deleted."** False. It governs GC eligibility for deletion metadata; compaction and SSTable overlap still decide when reclamation occurs.

**"Once repair finishes, all tombstones disappear."** False. Repair synchronizes replicas; it does not force compaction to erase all metadata in SSTables right away.

**"If a table has `default_time_to_live`, all records expire together."** False. TTL is computed per mutation/cell from write time; values can also be overwritten with different TTLs.

**"Forcing compaction always reclaims all expired portions."** False. Cells ineligible for GC, live data, overlapping files, or snapshots can still retain space; forced compaction also adds heavy load.

**"Rewriting the same key with TTL makes retries completely idempotent."** False if a retry generates a new timestamp/expiration time or alters values and business semantics.

## 14. Self-check questions and exercises

1. An SSTable contains 95% 1-day TTL data and 5% 90-day TTL data. After day three, why can it not yet be deleted as a whole file?
2. Explain the difference between `TTL(payload)=null` when the cell never had a TTL, when the cell expired, and when the column no longer has a live value.
3. If using TWCS with a 1-day window yet writing both 1-day and 30-day TTLs inside the same window, does TWCS automatically separate them into two distinct SSTables? Why?
4. Analyze three milestones: mutation write, TTL expiration, tombstone/SSTable GC. Which milestone is determined by `USING TTL`?
5. Why must offline replicas and repair schedules still be considered after `DELETE` or TTL expiry before changing `gc_grace_seconds`?
6. An application retries a record after timeout by generating a new UUID and using a 1-day TTL. What risks arise regarding duplicate data and expiration timing?
7. When designing two retention tables, how do you satisfy an API to "view all events in 24 hours" if both event types must be shown?
8. List four signals sufficient to distinguish "TTL was not applied" from "TTL expired yet physical data has not been reclaimed."
9. An SSTable is no longer listed in active data yet the disk remains full. Why might snapshots or backups be the cause?
10. With 100 GiB/day at 1-day TTL and 2 GiB/day at 30-day TTL, why is forecasting disk solely from 160 GiB of live data incomplete?

## 15. Timeline summary

```text
WRITE with different TTLs
        |
        v
Memtable -> flush -> SSTable has both short-TTL and long-TTL cells
        |
        +--> Short TTL expires: no longer appears as live data
        |                  |
        |                  +--> expiration metadata may still sit in SSTable
        |
        +--> Long TTL stays live: SSTable cannot drop whole-file yet
                           |
                           +--> safe compaction can drop eligible cells
                           |
                           +--> when whole file expires and passes GC/overlap:
                                opportunity to delete entire SSTable
```

**Conclusion:** Mixing very short and very long TTLs in the same table can leave **SSTables alive due to a small fraction of long-lived data**, preventing large volumes of expired bytes from being reclaimed quickly. TTL controls **logical visibility**, whereas compaction, `gc_grace_seconds`, SSTable overlap, repair, and storage policies control **physical removal**. For time-series workloads, evaluate separating retention classes and using TWCS when data shares uniform lifecycles; validate choices with actual storage metrics, tombstone counts, and read/write p99.
