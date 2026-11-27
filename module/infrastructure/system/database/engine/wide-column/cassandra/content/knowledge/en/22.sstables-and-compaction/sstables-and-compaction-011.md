# Conditions for Dropping Obsolete Versions or Tombstones

> **Chapter:** SSTables and compaction  
> **Scope:** Apache Cassandra, a distributed *wide-column* database. This lesson explains how Cassandra merges versions across SSTables, tombstone reclamation conditions, **zombie data** risks, and how to evaluate them using CQL, operational tools, and Java applications.

## 1. Why Does “Replaced” or “Deleted” Data Still Remain on Disk?

Cassandra uses an **LSM-tree** architecture. New writes enter the commit log and memtable; when the memtable flushes, data is written into **immutable SSTables**. Cassandra does not modify an old SSTable in place every time an `UPDATE` or `DELETE` runs.

Therefore:

- Writing `city = 'Hue'` after `city = 'Hanoi'` can leave **two versions of the same cell** existing in different SSTables.
- A `DELETE` statement typically writes a **tombstone** — a deletion marker with a timestamp — so older replicas or SSTables are not treated as live data.
- On `SELECT`, Cassandra reconciles the values and deletion markers seen on the read path to return the latest logical state according to timestamp rules.
- **Compaction** reads input SSTables, merges relevant versions, and writes new SSTables, thereby dropping redundant data if dropping it is safe.

The hard part is not “when can Cassandra delete files?”, but:

> **When is an obsolete version definitely shadowed, and when can a tombstone disappear without resurrecting old data?**

These two questions **do not share the exact same condition**.

## 2. Data Model and Two Types of “Old Data”

A value in Cassandra carries a microsecond-level timestamp; normally, the mutation with the higher timestamp wins when reconciling the same cell. For ease of learning, assume time moves forward and no two mutations share the same timestamp.

```text
At the same key user_id='u-42', column city

SSTable A: city='Hanoi'   @ timestamp 100
SSTable B: city='Hue'     @ timestamp 200

SELECT city  ->  'Hue' (the winning timestamp version)
```

The `'Hanoi'` version in SSTable A is a **shadowed/obsolete version**. It is no longer returned by queries while the `'Hue'` version is valid and reconciled.

If the user subsequently deletes the column:

```text
SSTable C: DELETE city    @ timestamp 300
           (tombstone)

SELECT city  ->  null / no live value
```

The tombstone at timestamp 300 **must continue shadowing** both the 200 and 100 versions wherever they still exist. If the deletion marker is purged too early, Cassandra might “see” an old value again and treat it as live.

### Comparison Table

| Object | Meaning | Safety condition for removal |
| --- | --- | --- |
| Old data version, e.g., `city='Hanoi' @100` | Shadowed by newer version `@200` | When compaction has enough context to prove the old version is no longer needed for reconciliation; depends on whether other data remains in SSTables outside the compaction run |
| Tombstone, e.g., `DELETE city @300` | Deletion marker for values in the same scope with older timestamps | Besides reaching GC eligibility age, must prove dropping the marker will not let older data in other SSTables or other replicas return |
| New live value, e.g., `city='Da Nang' @400` | Written after deletion marker `@300` | The old marker does not shadow this new data, yet may still be needed to shadow unmerged `@100`/`@200` values |

**Do not use a blanket “10 days have passed” milestone to decide removing all old versions.** `gc_grace_seconds` mainly governs eligibility to reclaim **tombstones**, whereas overwritten live versions are handled by compaction's merge and shadowing logic.

## 3. What Does Compaction See, and What Remains Outside?

Suppose a partition appears across three SSTables:

```text
SSTable S1                 SSTable S2              SSTable S3
city='Hanoi' @100          city='Hue' @200         DELETE city @300
          \                      |                        /
           \                     |                       /
            +---- read & merge by timestamp ------------+
                                    |
                         Logical state: deleted
```

If compaction selects **all of S1, S2, and S3**, it can examine the versions and deletion marker in the same merge pass. Once GC-eligible and proven no shadowed data remains outside the input set, Cassandra can reclaim the obsolete values along with the tombstone.

If compaction **selects only S3**, then:

- S1 and S2 remain outside that compaction run.
- Dropping the tombstone in S3 would leave the old values in S1/S2 uncovered.
- When reading the partition again, an old value could surface as the result if no deletion marker protects it.

Thus Cassandra cannot rely solely on tombstone age or the fact that “S3 was compacted” to conclude it may drop the deletion marker. Checking **overlapping SSTables / potential presence of old data** is a vital part of the reclamation decision.

### “Overlap” Is Not Just Visually Matching Partition Names

The system must check metadata covering token ranges, keys, timestamps, and SSTables that could contain data shadowed by the deletion marker. A tombstone can apply to:

- **Cell**: deletes a single column.
- **Row**: deletes an entire row.
- **Range**: deletes a slice of clustering rows.
- **Partition**: deletes data across an entire partition within the marker's scope.

Because scopes differ, a single-cell example cannot substitute for safety checks on row, range, or partition tombstones. Specific mechanisms for choosing input/output SSTables and GC thresholds vary by version and compaction strategy.

## 4. Conditions for Dropping Overwritten Data Versions

When compaction simultaneously reads an old value and a new value for the same cell, Cassandra reconciles timestamps and can omit the old version from the output SSTable.

Example:

```text
Before compaction:
  S1: nickname='An'   @100
  S2: nickname='Binh' @200

Compaction S1 + S2:
  Output: nickname='Binh' @200
  Version 'An' @100 does not need to be kept in output.
```

However, “older can be dropped” holds only when **the context is complete**:

1. Both values truly belong to the same key/cell and have a defined timestamp ordering.
2. The merge saw the data needed to confirm the version is shadowed.
3. No data/deletion markers or constraints outside the input SSTable set make dropping the version unsafe.
4. Compaction completes successfully; the output SSTable is created and replaces the inputs per storage protocol.

Overwritten records do not have a rule requiring them to “wait `gc_grace_seconds` like tombstones” solely because they are old. Yet physical removal can still be **delayed indefinitely** if no eligible compaction runs. SSTables are immutable, so without compaction, multiple versions can sit on disk even though `SELECT` returns only one value.

### Timestamps Are Not Absolute Wall-Clock Time

CQL allows specifying mutation timestamps; the timestamp dictates reconciliation order, which does not always match request arrival order. Large clock skew on clients or nodes can create records with unexpected timestamps. Therefore:

- A later `UPDATE` is not guaranteed to beat an earlier `UPDATE` if its timestamp is smaller.
- A tombstone with an incorrect timestamp can shadow data unexpectedly.
- Never equate “newest” with “last request received” if the application sets custom timestamps.

When two mutations share the exact same timestamp, Cassandra has tie-breaking rules, including prioritizing deletion markers in certain cases. For hands-on exercises, use distinct timestamps so you do not depend on tie-breaking.

## 5. How Are Tombstones Generated?

Tombstones do not come solely from `DELETE` statements. They can be produced by:

| Source | Example | When is the logical state deleted? |
| --- | --- | --- |
| Column delete | `DELETE city FROM ...` | When the delete mutation takes effect by timestamp |
| Row/partition delete | `DELETE FROM ... WHERE ...` | When the deletion marker shadows data in scope |
| Clustering range delete | `DELETE ... WHERE clustering >= ... AND ...` in matching schema/syntax | When the range marker shadows rows in the slice |
| TTL expiration | `INSERT ... USING TTL 60` | When TTL expires; data becomes dead and requires expiration metadata |
| Writing `null` into an eligible column via driver/CQL | Deletes corresponding cell in supported cases | Can create a tombstone rather than writing a live `null` value |

Distinguish **logical read results** from **physical storage reclamation**. Immediately after a `DELETE` takes effect, `SELECT` may stop returning old data. Yet the tombstone may need to remain on disk for days to protect the distributed system.

### Two Important Times Inside a Tombstone

A tombstone carries metadata serving two roles:

- **Deletion timestamp** (often called `markedForDeleteAt` in internal descriptions): used during reconciliation to decide whether the deletion marker shadows a data version.
- **Local deletion time** (in seconds): used to evaluate tombstone age against the GC threshold during compaction.

For TTL data, expiration time also marks when data becomes dead and eligible for GC aging. **Do not confuse microsecond mutation timestamps with the `gc_grace_seconds` counter in seconds.**

## 6. What Does `gc_grace_seconds` Actually Protect?

`gc_grace_seconds` is a table-level property defining the minimum duration Cassandra retains deletion metadata before considering a tombstone a **candidate** for reclamation. Example:

```cql
CREATE TABLE lab.profile_by_user (
    user_id text PRIMARY KEY,
    nickname text,
    city text
) WITH gc_grace_seconds = 864000;
```

Here `864000` seconds equals 10 days, used as an **illustrative configuration**, not a recommendation to set every system to 10 days.

Once a tombstone passes the grace threshold, that only answers:

> “Is the deletion marker **old enough to be considered** for removal?”

It **does not** guarantee:

- The tombstone vanishes the instant the clock crosses the mark.
- Old data in other SSTables is completely shadowed.
- Every replica has received or been repaired to learn of the deletion.
- Every table in the cluster shares the same `gc_grace_seconds`.
- `SELECT` stops encountering tombstones as soon as grace expires.

A **subsequent compaction** and corresponding safety checks must occur before the deletion marker can be purged from SSTables.

### Three Conceptual Conditions for GC'ing a Tombstone

| Condition | Question to ask |
| --- | --- |
| **Old enough** | Has the tombstone exceeded the GC threshold per `gc_grace_seconds`/version GC mechanics? |
| **Safe within the node's SSTables** | If the marker is dropped, does an older version still reside in another SSTable that it was shadowing? |
| **Safe across replicas** | Could absent or unrepaired replicas still reintroduce the old version after the deletion marker is purged? |

The first two conditions are node-level checks/paths; the final condition is a **distributed-system operational responsibility**. Cassandra cannot deduce that all offline replicas received a delete purely from a tombstone's age on a live node.

Some versions add mechanisms or configs for repair-aware tombstone GC. Do not assume identical behavior across all Cassandra 3.x/4.x/5.x versions or CQL-compatible services; always check docs and configs for your real cluster.

## 7. Why Can Dropping Tombstones Early Create “Zombie Data”?

Consider a keyspace with RF=3 and replicas A, B, C:

```text
Time T0
  A: city='Hanoi'      B: city='Hanoi'      C: city='Hanoi'

T1 — C goes down
  A, B are online; C is offline

T2 — DELETE city, acknowledged by A and B
  A: tombstone @200    B: tombstone @200    C: old value @100

T3 — Tombstone grace period passes without successful repair to C
  A/B compact and purge tombstone; deletion evidence is gone
  C still holds old value @100

T4 — C comes back and syncs/reads data
  Old value @100 can be streamed back or win because
  no tombstone remains representing the delete
              -> ZOMBIE DATA (deleted data resurrected)
```

At T2, if the client uses a consistency level allowing success while one replica is offline, C can miss the delete. Afterward, **hints** can help replay mutations, yet hints expire and do not replace periodic repair. If C stays down too long, it can still hold the stale value.

A valid repair within the grace window delivers the deletion marker to the missing replica or reconciles state before the marker is purged. Once tombstones are purged from healthy replicas before C syncs, it is nearly impossible to distinguish C's stale value from a live value using current data alone.

**Therefore, managing `gc_grace_seconds` is tied to repair schedules and maximum replica downtime.** Shrinking grace to reclaim space early without guaranteeing repair/node recovery is a high-risk decision.

### Distinguishing Repair, Compaction, and Consistency Level

- **Compaction:** merges SSTables **on one node** and can drop redundant data per rules.
- **Repair:** compares/synchronizes data between **replicas** for the corresponding token range.
- **Consistency level (CL):** specifies how many replica responses are required for a request to succeed; does not prove every replica received a DELETE.
- **Hinted handoff:** helps deliver mutations to absent replicas within a bounded window; does not replace repair during extended outages.

A `QUORUM` query may be sufficiently consistent for a specific read/write, yet **does not guarantee deletes reached all replicas over long periods**. Consequently, high CL alone cannot justify setting a very low grace period.

## 8. Overlapping SSTables Condition: The “Old Enough = Deleted” Trap

Suppose a tombstone in SSTable S2 is old enough:

```text
S1: order.status='PENDING' @100
S2: DELETE order.status    @200  (past gc_grace)
S3: order.total=150000     @150

Compaction picks only S2:
  If tombstone @200 is purged while S1 stays outside compaction:
  SELECT order.status could return 'PENDING' @100 again.
```

The grace condition **does not handle this automatically**. Cassandra must check SSTables that could contain data shadowed by the tombstone, key ranges, and timestamps when deciding to purge.

Scenarios to distinguish:

1. **Tombstone and all shadowed values are in the same compaction, with no dangerous older sources outside:** once GC-eligible, the marker and shadowed data can be omitted from the output.
2. **Tombstone is old enough, yet an SSTable outside compaction might still hold older values:** must retain the marker or rely on corresponding safety checks; cannot purge mechanically.
3. **Tombstone is not yet old enough:** usually retained to support replica sync even if current reads return no live value.
4. **No eligible compaction runs:** both tombstones and obsolete versions can stay on disk longer than grace.

**An SSTable disappearing from the directory after compaction does not mean the tombstone is gone.** A new output SSTable may still preserve the required tombstone.

## 9. Impact of Each Compaction Strategy

Compaction strategies govern **which SSTables are picked to merge** and **when opportunities arise to drop old data**, without bypassing tombstone safety rules.

| Strategy | How it looks in this problem | What to watch |
| --- | --- | --- |
| **STCS — SizeTieredCompactionStrategy** | Groups similarly sized SSTables; multiple generations can keep overlapping | Tombstones in files outside the compacting tier may remain unpurged even past grace |
| **LCS — LeveledCompactionStrategy** | Organizes SSTables into levels and bounds inter-level overlap | Per-level merges create chances to drop redundant data, yet do not guarantee instant tombstone GC |
| **TWCS — TimeWindowCompactionStrategy** | Groups SSTables by time windows, commonly used for time-series with TTLs | Helpful when data shares uniform lifetimes; late arrivals and rewrites of old data break window assumptions |
| **UCS — UnifiedCompactionStrategy (supported versions)** | Tunes compaction priorities by workload and storage choices | Must still respect shadowing and tombstone age; no shortcut guarantees instant deletion |

### TWCS and TTL: Easy to Optimize, Easy to Get Wrong

With **append-only** event streams, fairly uniform TTLs, and no updates to old data, SSTables in a time window gradually hold only expired data. Once safety conditions are met, dropping an entire expired SSTable saves work compared to processing individual cells.

However, never conclude:

> “TTL expired and one TWCS window passed, so the file can be deleted right away.”

If new records are written to old partitions, data arrives late, TTLs vary, or timestamps are skewed, the SSTable may still contain live data. Moreover, tombstones tie into repair and replica safety. Settings that aggressively force dropping expired SSTables without full safety checks can cause data loss or resurrect old values; use them only when proven safe for the workload.

## 10. CQL Practice: Observing Logical State After UPDATE and DELETE

Assume keyspace `lab` already exists and is used strictly in a learning environment. Use a single-partition/row table to focus on cell versions:

```cql
CREATE TABLE IF NOT EXISTS lab.profile_by_user (
    user_id text PRIMARY KEY,
    nickname text,
    city text
) WITH gc_grace_seconds = 864000;
```

### Step A — Write One Version, Then Replace It

```cql
INSERT INTO lab.profile_by_user (user_id, nickname, city)
VALUES ('u-42', 'Lan', 'Hanoi');

UPDATE lab.profile_by_user
SET city = 'Hue'
WHERE user_id = 'u-42';

SELECT user_id, nickname, city
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

After both mutations, Cassandra normally returns `city='Hue'` if the `UPDATE` timestamp exceeds the old timestamp. That **does not prove the old SSTable was physically deleted**.

You can check the logical timestamp of the live cell:

```cql
SELECT city, WRITETIME(city)
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

`WRITETIME(city)` returns the mutation timestamp of the selected cell value, without telling you which memtable or SSTable currently holds it.

### Step B — Delete a Cell

```cql
DELETE city
FROM lab.profile_by_user
WHERE user_id = 'u-42';

SELECT user_id, nickname, city
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

`nickname` can remain live while `city` is treated as having no value. The `DELETE` writes appropriate deletion metadata, and logs/compaction handle physical storage later.

A common mistake is seeing `city=null` from `SELECT` and assuming SSTables no longer contain `'Hue'`. In reality, both the old value and the tombstone may exist in separate SSTables.

### Step C — TTL Creates Data That Will Expire

To observe TTL without manual deletion:

```cql
INSERT INTO lab.profile_by_user (user_id, nickname, city)
VALUES ('u-ttl', 'An', 'Da Nang')
USING TTL 120;

SELECT nickname, TTL(nickname), WRITETIME(nickname)
FROM lab.profile_by_user
WHERE user_id = 'u-ttl';
```

Right after writing, `TTL(nickname)` reflects approximate remaining seconds of life. Once TTL expires, data is no longer logically live, yet expiration/deletion metadata can remain in SSTables until GC eligibility and compaction occur.

Do not treat TTL expiration as the moment files must vanish: **TTL expiration**, **`gc_grace`**, and **physical compaction** are three distinct concepts.

### Step D — Controlled Flush and Compaction Observation

In a lab environment on a suitable node:

```bash
nodetool tablestats lab.profile_by_user
nodetool compactionstats
```

These statistics help observe SSTable counts, tombstones/reads, data sizes, and running compaction tasks depending on Cassandra version.

If you need to experiment with SSTables, you can flush the table in the **lab**:

```bash
nodetool flush lab profile_by_user
```

Repeat writes/updates/deletes, flushes, and observations over time to create multiple SSTable generations. **Do not expect a fixed SSTable count or immediate tombstone disappearance**; background compaction and automatic policies cause outputs to vary across runs.

You can use tools like `sstablemetadata` or `sstabledump` **on a lab copy for specific files**, following version docs, to inspect metadata. That distinguishes physical on-disk data from `SELECT` results. Avoid manually editing/deleting SSTable files actively used by Cassandra.

## 11. From the Java Application Perspective

The Java driver sends mutations and queries by partition key; the driver **does not control tombstone purging**. For query-driven writes and read/write consistency, applications should:

1. Use proper partition keys to avoid broad scans hitting many tombstones.
2. Distinguish “delete succeeded at consistency level” from “physically deleted on all replicas”.
3. Be careful retrying `DELETE`/`UPDATE` under custom timestamps and concurrency; verify business-logic idempotency.
4. When strict legal or security deletion deadlines apply, design proper deletion/retention/backup workflows; never rely solely on `DELETE` or `gc_grace` as a guarantee of immediate physical erasure.

Java Driver 4.x example:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ProfileService {
    private final CqlSession session;
    private final PreparedStatement deleteCity;
    private final PreparedStatement readCity;

    public ProfileService(CqlSession session) {
        this.session = session;
        this.deleteCity = session.prepare(
            "DELETE city FROM lab.profile_by_user WHERE user_id = ?"
        );
        this.readCity = session.prepare(
            "SELECT city FROM lab.profile_by_user WHERE user_id = ?"
        );
    }

    public String removeAndReadCity(String userId) {
        BoundStatement delete = deleteCity.bind(userId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(delete);

        Row row = session.execute(
                readCity.bind(userId)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        return row == null ? null : row.getString("city");
    }
}
```

The example assumes keyspace/table exist, the session has proper topology config, and RF is appropriate. Returning `null` after `DELETE` does not mean commit logs, SSTables, or all replicas have purged the tombstone. It is strictly the logical read result under the chosen consistency level and state visible at read time.

## 12. Diagnosing Lingering Tombstones or “Resurrected” Data

| Symptom | Check first | Action direction |
| --- | --- | --- |
| Old `DELETE`, tombstones still seen in reads/tracing | Tombstone age, `gc_grace_seconds`, SSTable overlap, compaction schedule | Identify eligible compaction and shadowed data volume; avoid unconditional forced GC |
| High tombstone count scanned per query | Partition key, clustering range, TTL/data model, deleted cell count | Narrow read scope, adjust schema/TTL, and refine access patterns |
| Disk does not shrink despite heavy TTL expiration | SSTables still holding live data, compaction policy, overlapping SSTables | Measure reclaimable portion and compaction strategy before changing configs |
| Deleted value reappears after node downtime | Node downtime duration, repair, hints, gc grace, timestamps | Investigate zombie data and sync replicas per recovery runbook; never manually delete logs or SSTables |
| Repair fails to finish before grace | Repair window, token range, absent nodes, and repair errors | Restore reliable repair schedules before considering shorter grace |
| Compaction tombstone cleanup causes high I/O | Disk headroom, pending compactions, read/write p99 | Schedule compaction carefully, prioritize cluster stability, and measure impact |

### Safe Diagnostic Steps

1. Identify **keyspace, table, partition key**, and tombstone type (cell, row, range, partition, TTL).
2. Read **`gc_grace_seconds`** from the live schema; never rely on word-of-mouth defaults.
3. Measure data and deletion-marker ages, TTL distribution, SSTable counts, and compaction tasks.
4. Review node downtime/repair/hinted-handoff history and RF/CL topology.
5. Test on a lab or equivalent-load replica before tuning compaction/GC in production.

**Never delete SSTable files or force `gc_grace_seconds = 0` as a disk-cleanup trick.** If replicas are not yet synced or tombstones still shadow old data, such interventions can corrupt consistency and cause zombie data.

## 13. Commonly False Statements

**“The new value won in SELECT, so the old value was deleted from disk.”** False. Obsolete versions can remain until SSTables are suitably compacted.

**“Once a tombstone passes `gc_grace_seconds`, it gets deleted immediately.”** False. That is an eligibility age threshold, not a scheduled deletion alarm; compaction and safety checks are required.

**“Tombstone GC only needs to inspect the single SSTable being compacted.”** False. Older data outside the input set could be exposed if the tombstone vanishes.

**“Repair and compaction are the same step.”** False. Compaction merges files on a node; repair synchronizes replicas. Both relate to safe deletion yet play different roles.

**“Using QUORUM consistency for DELETE guarantees every replica received the delete.”** False. QUORUM does not require every replica to respond; long-absent replicas may need repair.

**“When TTL expires, data is physically deleted immediately.”** False. TTL makes data logically dead; tombstones/metadata and GC still follow their own lifecycles.

**“Old data with a low timestamp can never come back.”** False. If newer tombstones are purged while a replica still holds the old version, zombie data can occur.

**“More aggressive compaction always clears every tombstone.”** False. Compaction cannot bypass data-safety checks, and forcing compaction can consume heavy I/O and disk.

## 14. Analytical Exercises

1. SSTable S1 has `nickname='A' @100`, S2 has `nickname='B' @200`. When compaction selects both and no related data exists elsewhere, what happens to version `'A'`?
2. S1 has `city='Hanoi' @100`, S2 has tombstone `DELETE city @200` past grace. Why is compacting S2 alone insufficient to conclude the tombstone can be dropped?
3. RF=3: replica C is offline when A and B receive a DELETE. If A/B purge the tombstone before C is repaired, what scenario can occur when C returns?
4. Explain the difference between *a tombstone no longer appearing in SELECT* and *a tombstone being physically removed from SSTables*.
5. Why must `gc_grace_seconds`, repair frequency, and maximum node downtime be considered together?
6. TTL data expired on a TWCS table yet disk usage has not dropped. State at least three plausible causes before editing configs.
7. If queries scan many tombstones, how would you review partition keys, TTLs, delete patterns, and compaction?
8. In a Java application, after a `DELETE` returns successfully, what can you assert about logical read results? What can you **not** yet assert about SSTables and replicas?

## 15. Decision Summary

```text
Want to drop an OBSOLETE VERSION?
    |
    +-- Does a newer version shadow the same cell?
            |
            +-- Does compaction have full context to reconcile safely?
                    -> Can omit the obsolete version from output SSTable

Want to drop a TOMBSTONE?
    |
    +-- Old enough per GC policy?
            |
            +-- No dangerous older data in other SSTables?
                    |
                    +-- Handled risk of replicas missing deletes
                         (repair/outage/hints within safe window)?
                             -> Can reclaim during eligible compaction
```

**Key Takeaway:** Overwritten live versions can be dropped once compaction proves they are no longer needed. Tombstones must be kept longer because they are **proof of deletion** against both older SSTables and distributed replicas. `gc_grace_seconds` is only one piece of the decision; **SSTable overlap, compaction, repair schedules, and replica health** together establish safe reclamation.
