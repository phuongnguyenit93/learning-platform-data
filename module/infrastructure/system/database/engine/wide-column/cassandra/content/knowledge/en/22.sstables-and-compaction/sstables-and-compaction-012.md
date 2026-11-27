# Fully Expired SSTables and Data That Still Blocks Reclamation

## 1. The Problem: TTL Expired Yet Disk Isn't Free

In **Apache Cassandra**, a value with a TTL (*time to live*) stops being valid for queries once it expires. However, **data is not necessarily deleted physically right away**. SSTables are immutable files; old versions, deletion markers, and metadata can remain on disk until compaction allows safe removal.

One particularly important case is a **fully expired SSTable**: Cassandra can **drop the entire file** instead of reading and rewriting every row if it determines that dropping the file neither exposes stale data nor violates deletion correctness.

This lesson belongs to the **SSTables and compaction** chapter, focusing on three practical questions:

1. When is **all data in an SSTable** considered expired and past the tombstone protection period?
2. What in **other SSTables**, or inside that SSTable itself, prevents Cassandra from **reclaiming** the file yet?
3. How do you design TTLs, `TimeWindowCompactionStrategy` (TWCS), partition keys, repair, and observability so reclamation is both efficient and safe?

This knowledge is essential when operating a distributed wide-column model: data maps to replicas via partition keys/tokens, appends across multiple SSTables, reconciles versions by timestamp on reads, and must propagate deletes/TTLs across replicas.

**After this lesson**, you will be able to explain the conditions to reclaim an SSTable, analyze an example with shadowed stale data, diagnose why disk usage stays flat even after TTL expiration, and verify using CQL/`nodetool`.

> Scope: regular **full replicas**, TTLs/tombstones, and compaction mechanics. Specific optimizations and internal checks of the expired-SSTable evaluator can vary by Cassandra version; diagrams are explanatory models and do not replace verifying on your running version.

## 2. Reviewing SSTables, TTL, and Tombstones

### 2.1. Why Are There Multiple SSTables for the Same Partition?

Replicas accept mutations, write them to the **commit log**, and update the **memtable**. When the memtable flushes, Cassandra creates **immutable SSTables**. Subsequent writes do not edit old SSTables in place, instead creating new data in memtables and other SSTables; compaction later merges eligible files.

~~~mermaid
flowchart TD
    C["Client INSERT / UPDATE / DELETE"] --> K["Coordinator picks replicas"]
    K --> R["Replica: commit log + memtable"]
    R --> F1["Flush → SSTable A"]
    R --> F2["Later flush → SSTable B"]
    R --> F3["Next flush → SSTable C"]
    F1 --> Q["Read: reconcile versions/tombstones"]
    F2 --> Q
    F3 --> Q
    F1 --> P["Compaction: check droppable data"]
    F2 --> P
    F3 --> P
~~~

A single partition can appear in multiple SSTables. During reads, Cassandra uses timestamps and tombstones to determine the visible logical state. **An SSTable sitting on disk** does not mean every value inside it is still returned to clients.

### 2.2. TTL Is Not an Instant File Deletion Operation

`TTL` specifies a value's lifetime from write time per CQL semantics. Once TTL expires, data is treated as deleted, leaving expiration metadata to reconcile older records. Tombstones also come from `DELETE` and certain deleting update operations.

| Stage | Logical state | Storage state |
| --- | --- | --- |
| Newly written with TTL | Value readable under chosen CL | May be in memtable/commit log; later written to SSTable |
| TTL expires | Value no longer returned as live data | Deletion/expiration metadata and data bytes may remain in SSTable |
| Safety period and compaction conditions met | Deletion markers/old data eligible for removal | Compaction may drop parts or the entire SSTable |
| File safely reclaimed | That SSTable is no longer in the table's active file set | Filesystem usage still depends on snapshots/backups and open references |

**Two kinds of “expiration” must be separated:**

- **Logical expiration:** past TTL, clients should not see the old value in normal queries.
- **Physical deletion eligibility:** Cassandra has a safe basis to drop bytes/tombstones; it may still wait for compaction, overlap checks, and grace periods.

### 2.3. What Does `gc_grace_seconds` Protect?

`gc_grace_seconds` is a table-level duration controlling how long **tombstones are retained** so a temporarily absent replica still has a chance to receive deletion info via sync/repair. In a simple example with a 30-day TTL and 10-day grace, **do not assume** files vanish right on Day 30; tombstone protection windows and other conditions must also be checked.

`gc_grace_seconds` is **not** a TTL, nor does it run repair automatically. Shortening grace while a replica was offline for a long time or repair hasn't run on schedule can cause **deleted data to reappear** (*zombie data*). Never lower this value solely to free disk fast.

## 3. What Does a “Fully Expired SSTable” Mean?

Consider an SSTable X containing only TTL-bound data. If all liveness-bearing data has expired and deletion markers have passed their reclaim threshold, X is a **candidate** for whole-file removal. However, **“candidate” does not equal “allowed to delete”**.

In practice, ask at least three questions:

1. **Is any data still live?** One unexpired TTL value, one non-TTL value, one valid liveness marker, or other live data in X can force keeping the file.
2. **Is deletion info safe to discard?** Tombstones that haven't passed the safety threshold, along with risks of replicas missing deletes, prevent reclamation.
3. **Does data in this file shadow an older version in another file?** If dropping X could let an older record from another SSTable resurface, Cassandra must retain the information needed to preserve correct read results.

The **general safety logic** can be expressed as:

~~~text
Eligible to drop entire SSTable
    = all contents expired
    + tombstones eligible for GC by time/policy
    + does not expose older shadowed data in other SSTables
    + compaction/check pass identifies and reclaims the file.
~~~

This is **not a substitute for internal algorithms**: Cassandra relies on SSTable summary metadata and checks involving time, timestamps, token/partition ranges, other existing SSTables, and compaction strategy. Exact conditions depend on version and compaction type.

### 3.1. Distinguishing “Some Rows Expired” vs. “Entire File Expired”

| SSTable contents | Can the whole file be dropped as soon as some TTLs expire? | Reason |
| --- | --- | --- |
| 100% TTL data expired, tombstones past grace, no threat from other files | **Potentially yes**, once Cassandra's checks confirm eligibility | No data left in the file that needs retaining |
| 99% data expired, 1% still within TTL | **Cannot drop whole file yet** | Live portion must still be stored |
| Many TTL values mixed with one **non-TTL** value | **File cannot be treated as fully expired** | Non-TTL value may still be needed by reads |
| All TTLs expired, yet tombstones not yet GC-eligible | **Not yet** | Obligation to keep deletion markers remains |
| All TTLs expired, yet data in this file shadows older version in another SSTable | **Cannot safely conclude** | Dropping file could expose stale data |

Key point: **a high tombstone ratio does not mean the whole SSTable is safe to delete**. Even a few bytes of live data or an overlap relationship requiring protection can pin a very large file.

## 4. How Can Data in Another SSTable Block Reclamation?

### 4.1. Example of “Old Data Coming Back to Life” After TTL

Suppose on **the same replica** there are two SSTables containing the same partition key and cell:

- **SSTable A:** older write `status = 'ACTIVE'` with no TTL, smaller write timestamp.
- **SSTable B:** newer write `status = 'INACTIVE'` with TTL. While B is live, B shadows A because it has a newer timestamp.
- When B's TTL expires, B's expiration/deletion info still needs to **shadow A** under timestamp semantics if A still sits in another file.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant A as SSTable A
    participant B as SSTable B
    participant R as Replica read
    App->>A: Write status=ACTIVE (timestamp t1, no TTL)
    App->>B: Write status=INACTIVE (t2 > t1, TTL)
    Note over B: TTL expires; expiration marker remains
    R->>A: Read old data ACTIVE
    R->>B: Read expiration marker of newer value
    B-->>R: Shadows t1 version
    R-->>App: Does not return old ACTIVE
    Note over A,B: Dropping B too early risks resurrecting ACTIVE
~~~

Thus, **even after every live value once stored in B has expired**, reclaiming **all of B** must still consider other SSTables. If B were deleted prematurely while A still existed, a later read would see only `ACTIVE` from A, violating the logically expired/deleted state.

**Two SSTables sharing a token range do not automatically imply a zombie conflict.** Overlap is just a signal to inspect. Safety checks can use timestamps, tombstone ages, metadata, and compaction context to decide whether the file still shadows any data.

### 4.2. Other Forms of Overlap to Consider

| Data / situation | Why is it a potential blocker? | Reasonable action |
| --- | --- | --- |
| Older SSTable holds the same partition/cell | Markers in the expired file may still shadow old values | Let compaction evaluate overlap; never delete manually |
| Range tombstone or `DELETE` in candidate file | Delete may shadow multiple rows/versions in another SSTable | Retain tombstones until purge conditions are safe |
| One SSTable mixes widely differing write times/TTLs | Late writes or long TTLs outlive the rest | Avoid mixing out-of-window data under TWCS |
| One non-TTL regular/static cell | Part of the data can live indefinitely | Align schema/TTL policy consistently with table lifecycle |
| Replica was offline long, repair missed | Dropping markers too early lets stale data from that replica return | Review `gc_grace_seconds`, repair schedules, and recovery steps |
| Snapshots/backups pin old files | File left active SSTable set yet still consumes disk | Check snapshot retention per backup policy; never delete recklessly |

The last two points differ: **SSTable overlap** governs **correctness of read data**; **snapshots/backups** govern **when physical disk space is actually freed**. An SSTable removed from the active set by compaction can still consume disk bytes via snapshot file links.

## 5. TWCS: A Fitting Strategy When Data Has a Time-Based Lifecycle

**TimeWindowCompactionStrategy (TWCS)** organizes compaction around **time windows**. It generally fits time-series tables with steady fresh writes and fairly uniform TTLs, such as telemetry, logs, metrics, or retention-bounded events.

Idea:

1. SSTables holding data written within the same window are compacted per TWCS rules.
2. Once a window closes, files in that window stay relatively stable if the app rarely modifies old data.
3. Once **all data in an SSTable** expires and safety checks pass, Cassandra has the chance to **drop the whole SSTable**, avoiding reading/rewriting every row just to strip expired entries.

~~~mermaid
flowchart LR
    W1["Window D1: SSTable A"] --> E1["TTL expired; safety check"]
    W2["Window D2: SSTable B"] --> E2["Some rows not yet expired"]
    W3["Window D3: SSTable C"] --> E3["Live data remains"]
    E1 --> X{"No dangerous overlap and eligible?"}
    X -->|Yes| D["Can drop entire A"]
    X -->|No| K["Keep A / other compaction"]
    E2 --> Y["Keep B"]
    E3 --> Z["Keep C"]
~~~

**TWCS does not guarantee “one window passes and the file is deleted”.** Compaction windows differ from TTLs. Data inside the file still must expire per actual write clocks/TTLs and pass reclamation checks.

### 5.1. Lab: Table with TTL and TWCS

Example retaining measurements for 30 days, 1-day compaction window, replication factor 3 in DC `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
~~~

`2592000` seconds = **30 days**, `864000` seconds = **10 days**. This is a teaching example, **not a universal setting for every system**. `gc_grace_seconds` must fit repair capacity, maximum replica downtime, and data safety requirements.

**Why is the partition key `(sensor_id, event_day)`?** Each sensor gets a daily partition to bound partition size and speed up sensor/day queries. It **does not directly force SSTables to split by day**: SSTables come from memtable flushes and are organized by TWCS according to write time/timestamps.

### 5.2. Illustrating Time Without Promising a Deletion Date

Suppose a value is written on **Day 0** with an exact **30-day** TTL, no late writes, and no other live data in the SSTable:

~~~text
Day 0             Day 30                 Day 40                 Afterward
  |------------------|----------------------|----------------------|
  Written with TTL   Logical TTL expires    +10-day illustrative   Eligible for
  currently live     marker appears         gc_grace passes        compaction reclaim
~~~

On Day 30, `SELECT` no longer sees the TTL-expired value. **You cannot conclude the file is deleted precisely on Day 40**, because other entries' expiration times, deletion markers, SSTable overlap, and compaction schedules still matter. `gc_grace_seconds` is not a file-deletion timer.

### 5.3. Write Patterns That Make TWCS Struggle to Drop Whole Files

- **Late writes/backfills:** mutations with past timestamps written today can mix data generations unfavorably for windowing; watch out especially with client-supplied timestamps.
- **Non-uniform TTLs:** some cells with 7-day TTL and others with 90-day TTL in the same SSTable force the file to wait for the longest-lived portion.
- **Non-TTL data:** a single persistent cell can pin an entire file even after hordes of other cells expire.
- **Updates/deletes into old partitions:** new versions and deletion markers can span multiple SSTables/windows, raising overlap and reconciliation work.
- **Mismatched compaction and reckless manual major compaction:** can merge data from different epochs into one large file, delaying whole-file drop opportunities.

For workloads with heavy updates or mixed TTLs, reconsider compaction strategy and table design. TWCS excels for **mostly append-only** writes and predictable lifecycles, not as an automatic fix for every CQL table.

## 6. What Happens When a File Is Not Eligible?

There are two separate paths:

1. **Whole-SSTable drop:** if the entire file is expired and safe, Cassandra can remove the file from the active SSTable set without rewriting every row.
2. **Selective compaction:** the system reads/merges selected SSTables and can strip **purge-eligible** data/tombstones while keeping live data and still-needed deletion info.

If even one live cell or required marker remains, the whole file cannot drop yet; however, compaction can still **reclaim partial space** if row/cell-level purge conditions are met. Do not equate “file hasn't dropped” with “Cassandra never reclaims any bytes”.

### Why Doesn't “Running a Huge Compaction” Always Solve It?

- Compaction creates read/write I/O and uses temporary CPU/disk space; forcing compaction in production can cause major disruption.
- Tombstones that are too young or still needed to shadow stale data cannot be dropped arbitrarily.
- TWCS relies on keeping windows separate; mixing old and new data can create longer-lived SSTables.
- After compaction, **snapshots or hard links** can still pin bytes from old files.

**The right target is lifecycle design and purge safety**, not hunting for an “erase all expired SSTables” command to run on every node.

## 7. CQL Practice: Checking Live Data and TTL

### 7.1. Writing Data with TTL and Reading Remaining TTL

On a lab cluster with DC `dc1` and enough nodes for RF = 3, using the table from Section 5:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.75);

SELECT event_time,
       reading,
       TTL(reading) AS remaining_seconds,
       WRITETIME(reading) AS write_time_us
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';
~~~

`TTL(reading)` reports **remaining seconds for the column** while live. `WRITETIME(reading)` reports the cell's write timestamp (microseconds), **not** the date Cassandra will delete the SSTable. After the cell expires, `SELECT` stops returning that row; `TTL()` cannot tell whether tombstones have been purged.

`CONSISTENCY` is a **cqlsh** command, not raw CQL sent through the Java Driver. RF = 3 determines partition placement; `LOCAL_QUORUM` requires two replica responses in the local DC for reads/writes, **without forcing SSTable drops across all replicas simultaneously**.

### 7.2. Creating a Scenario Where One Value Lives Longer

In the same table with a 30-day default TTL, write a record with a longer explicit TTL:

~~~sql
INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T03:05:00Z',
     123e4567-e89b-42d3-a456-426614174002, 22.10)
USING TTL 7776000;
~~~

`7776000` seconds equals **90 days**. Even though most other values in the SSTable have a 30-day TTL, **if** this 90-day value lands in the same SSTable, the SSTable **is not fully expired** at the 30-day mark. This illustrates why checking only the table's default TTL is insufficient.

A write with `USING TTL 0` can omit TTL for new writes per CQL semantics and config; non-TTL cells are another reason a containing file cannot be considered fully expired. Never mix indefinitely retained data into a TTL time-series stream if whole-SSTable expiration is your goal.

### 7.3. Limitations of CQL-Only Testing

`SELECT` shows data **still logically visible** at the chosen consistency level; it **does not show** which SSTable files exist on disk or why a file wasn't dropped. Conversely, a “high tombstone ratio” metric **does not guarantee** every partition/marker in the SSTable is purge-eligible.

Diagnosis requires combining query data, table metadata/configuration, SSTable metrics, write/TTL times, and compaction/repair status.

## 8. Practical Observation: When TTL Expires Yet Disk Keeps Growing

On a Cassandra node with permission to run `nodetool`, common commands:

~~~bash
nodetool tablestats telemetry_lab.readings_by_sensor_day
nodetool compactionstats
nodetool status
~~~

**How to read:**

- `tablestats` shows metrics such as SSTable count, disk space used, estimated tombstones/droppable tombstones, and read stats; exact field names depend on version.
- `compactionstats` shows running or pending compactions, helping distinguish “no processing opportunity yet” from “processed yet not eligible”.
- `status` shows which nodes and datacenters are up/down. If a replica has missed repair for a long time, that signals revisiting **tombstone deletion safety**, not just disk cleanup.

Beyond `nodetool`, admins can use **SSTable metadata** tools shipped with the exact Cassandra version to inspect timestamps, local deletion times, and existing files. Follow safe operational runbooks; never edit or delete SSTables manually to experiment on production nodes.

### Ordered Diagnostic Procedure

1. **Confirm storage contract:** does the table have a default TTL; are there writes with custom TTL, TTL 0, static columns, or old updates?
2. **Compare timestamps:** have both the TTL of the **latest-written value** and tombstone safety threshold passed? Do not infer from the partition key's date if write timestamps differ from event dates.
3. **Check compaction strategy:** does TWCS have fitting windows or is it mixing data across generations? Is old data frequently updated/backfilled?
4. **Check overlap:** could the candidate SSTable shadow data in another SSTable? Never treat tombstone ratio alone as a drop trigger.
5. **Check repair and replica status:** is grace aligned with repair schedules, maximum outage duration, and node replacement procedures?
6. **Check snapshots/backups:** did files leave the active SSTable set while filesystem usage remained high due to snapshots, backups, or open file handles?
7. **Re-measure over time:** are SSTable counts, live/total disk usage, compaction backlog, and read/write performance shifting as expected?

### Cause-and-Action Reference Table

| Symptom | Hypothesis to verify | Action direction |
| --- | --- | --- |
| Most data expired via TTL, SSTable count stays flat | A few cells live longer or lack compaction opportunities | Check actual TTLs, SSTable count, windows, and backlog |
| TWCS retains very old files | Late writes, mixed TTLs, markers shadowing other data, or overlap | Inspect write patterns, timestamps, metadata, and window sizing |
| Disk usage stays flat despite fewer live SSTables | Snapshots/backups still pin files | Check retention/backup policies; clean up only per approved policy |
| A replica was disconnected for a long time | Tombstones cannot be safely purged yet or repair overdue | Execute repair/recovery procedures properly before touching grace |
| Heavy tombstone reads, high latency | Dense TTLs/deletes and overlapping SSTables | Review partition design, TTLs, compaction, and tombstone metrics |
| Forced compaction yet new file remains large | Unexpired data or live subset merged with old portion | Stop forcing endlessly; fix data/lifecycle model first |

## 9. Java Perspective: TTL, Prepared Statements, and Application Expectations

Java applications often attach TTLs per event or rely on the table's `default_time_to_live`. The example below uses **Apache Cassandra Java Driver 4.x** to write a measurement with a 30-day TTL:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class WriteReadingWithTtl {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                    "INSERT INTO telemetry_lab.readings_by_sensor_day " +
                    "(sensor_id, event_day, event_time, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?) USING TTL ?");

            BoundStatement write = insert.bind(
                    "sensor-9",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:10:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    new BigDecimal("22.35"),
                    2_592_000)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
        }
    }
}
~~~

**Points to understand:**

1. `USING TTL ?` sets the TTL **for the written data**, not a promise that “the SSTable will be deleted after exactly 30 days”.
2. `LOCAL_QUORUM` requires sufficient replica acknowledgments for the write in the local DC; it **does not control** compaction, grace periods, or file drop timing.
3. The partition key comprises **`sensor_id` and `event_day`**. Adding a bucket column bounds partition size, while TTL and compaction strategy govern per-replica file lifecycles.
4. Writing with old event timestamps, varying TTLs, or editing old keys can leave SSTables/windows holding multiple generations; applications should enforce clear timestamp and TTL conventions.
5. `127.0.0.1` and `dc1` are lab placeholders only. Real systems need proper contact points, local DC, authentication, TLS, and retry limits.

When applications need to **query TTL-expired rows for auditing**, you cannot count on SSTables/tombstones remaining readable via CQL. Preserve history/backups per business requirements before data expires, or use appropriate long-term archival storage.

## 10. True and False Statements

| Statement | Verdict | Reason |
| --- | --- | --- |
| “TTL = 30 days means the SSTable file vanishes on Day 30.” | **False** | TTL expires logically; file removal also depends on grace, other data, overlap, and compaction. |
| “99% expired data means the whole file can be deleted.” | **False** | Even one live cell or required marker blocks whole-SSTable drop. |
| “No CQL rows returned means the SSTable is empty and safe to delete.” | **False** | Tombstones and old data may remain on disk, still obligated to shadow older versions. |
| “A tombstone in a newer SSTable can prevent old data in another file from resurrecting.” | **True** | Deletion info must stay until purging is safe. |
| “Increasing RF makes SSTables on each node expire TTL faster.” | **False** | RF increases replica copies; TTL/compaction run per replica. |
| “TWCS enables dropping whole SSTables when data has uniform time cohorts.” | **True, conditionally** | The file must be fully expired and pass safety checks. |
| “`gc_grace_seconds = 0` is always safe when TTL is short.” | **False** | Risks resurrecting stale data from replicas or other SSTables if markers vanish too early. |
| “Major compaction definitely deletes all tombstones.” | **False** | Ineligible tombstones must stay; compaction also incurs I/O and temp disk usage. |
| “Disk usage not dropping can be caused by snapshots pinning old SSTables.” | **True** | Filesystem usage differs from active SSTable set size. |

## 11. Self-Check Exercises with Solutions

**Exercise 1.** An SSTable contains 10,000 rows with a 30-day TTL and **one row with a 90-day TTL**. After 45 days, can the file be considered fully expired?

**Solution:** **No.** As long as the 90-day row remains in the file, the file holds live data. Even though almost all other rows expired, the whole file cannot be dropped yet.

**Exercise 2.** SSTable A has `value = 'OLD'` without TTL at timestamp `t1`. SSTable B has `value = 'NEW'` with TTL at timestamp `t2 > t1`. B's TTL has expired. Why must A be considered before dropping B?

**Solution:** B carries expiration/tombstone metadata shadowing the `OLD` version. Dropping B prematurely while A still exists could let `OLD` resurface. Compaction must verify overlap safety.

**Exercise 3.** A TWCS table has a 7-day TTL and `gc_grace_seconds = 10 days`. Can you guarantee all old files are deleted on Day 17?

**Solution:** **No.** Even taking 7 + 10 days as an illustrative time bound, there may be differing TTLs, differing write times, tombstones, overlaps, compaction schedules, and snapshots/backups.

**Exercise 4.** A team lowers `gc_grace_seconds` to 0 to free disk while a replica has been offline for days and repair has not run. What is the risk?

**Solution:** Deletion markers may be purged before the offline replica learns of deletions; when the replica returns, stale data can propagate and **resurrect**. Evaluate repair schedules, replica recovery, and failure modes before altering grace.

**Exercise 5.** Metrics show active SSTable count dropped after compaction, yet filesystem usage barely decreased. What should you check?

**Solution:** Check **snapshots, backups, hard links**, open file references, and whether other data grew simultaneously. Never manually delete data outside organizational retention/backup policies.

**Exercise 6.** Why does a mostly append-only, uniform-TTL time-series table typically get better reclamation with TWCS than a table constantly modifying old rows?

**Solution:** When data is rarely edited and shares similar ages, older-window SSTables expire together in cohorts with minimal overlap against fresh data. Historical updates/backfills and mixed TTLs scatter live versions across files/windows, extending how long files must be kept.

## 12. Decision Model Before Concluding “The File Must Be Deleted”

~~~mermaid
flowchart TD
    A["Old SSTable and disk usage hasn't dropped"] --> B{"Has all data in the file expired / lost liveness?"}
    B -->|No| C["Live data remains: cannot drop whole file"]
    B -->|Yes| D{"Are tombstones eligible for purge?"}
    D -->|No| E["Keep to protect deletes/repair"]
    D -->|Yes| F{"Does data in file shadow data in another file?"}
    F -->|Yes / unclear| G["Overlap check needed; do not delete manually"]
    F -->|No| H["May qualify for whole-SSTable drop"]
    H --> I["Wait for eligible compaction/cleanup pass"]
    I --> J{"Did filesystem usage drop?"}
    J -->|Yes| K["Re-measure performance and retention"]
    J -->|Not yet| L["Check snapshots/backups/file references"]
~~~

**Key Takeaway:** `TTL` governs **when data stops appearing**; `gc_grace_seconds` and tombstone/repair mechanics help ensure **deletions are never reversed**; compaction and overlap checks govern **when SSTable bytes on disk can be reclaimed**. An SSTable can be dropped as a whole file only when **no data needs preserving and no stale data in other files requires shadowing**. That matters far more than any simplistic math like “TTL elapsed so the file must have vanished”.
