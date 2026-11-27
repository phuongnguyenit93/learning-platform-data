# Logical Expiration, Tombstones, and Physical Reclamation in Apache Cassandra

## 1. Why Has Disk Usage Not Dropped After TTL Expired?

**Apache Cassandra** is a **distributed wide-column** database management system. A partition can be stored across multiple replicas; data is written to a memtable and subsequently resides in immutable **SSTable** files. Consequently, "expired data" does not mean "data bytes are erased from disk at that exact moment."

Suppose an application stores a token for **60 seconds** using CQL:

```sql
-- Illustrative example in a selected test keyspace.
CREATE TABLE IF NOT EXISTS session_token_by_id (
    session_id uuid PRIMARY KEY,
    token_hash text
);

INSERT INTO session_token_by_id (session_id, token_hash)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'demo-hash-not-a-real-token'
)
USING TTL 60;
```

After roughly 60 seconds, Cassandra no longer returns `token_hash` as a **live** value. However, SSTables may still contain the expired cell, deletion metadata, and older versions. They are only cleaned up **later**, during suitable compaction runs once data-safety conditions are satisfied.

There are **three milestones** to distinguish:

1. **Logical expiration:** the cell is no longer valid to be returned as live data.
2. **Tombstone / deletion metadata:** Cassandra remembers that the value expired or was deleted so older copies from other replicas/SSTables cannot reappear.
3. **Physical reclamation:** expired data/tombstones whose protective role is over are removed from SSTables when compaction can do so safely.

These milestones can be separated by considerable time; in particular, **TTL is not a promise of physical deletion at an exact wall-clock instant**.

## 2. Timeline: From Live Cell to Compaction

For a cell written at `t0` with `TTL = 300 seconds` on a table with `gc_grace_seconds = 864000` (10 days, a common default for Cassandra tables), you can picture:

```text
        t0                  t0 + 300 seconds             After grace + compaction
        |                            |                                |
        v                            v                                v
  WRITE NEW CELL              LOGICAL EXPIRATION            ELIGIBLE FOR RECLAMATION
  - value                     - no longer live              - requires aged tombstone
  - write timestamp           - expiration metadata         - checks overlapping SSTables
  - TTL = 300 seconds         - shadows old versions        - checks replica safety
        |                            |
        +-- ttl() counts down -------+
                                     |
                                gc_grace_seconds
                              is a safety window,
                              NOT extra TTL
```

| Point in time | Normal read result | Possible storage state |
|---|---|---|
| After `t0`, before TTL expires | Cell is live; `ttl(col)` is positive | Memtable or SSTable holds the expiring cell |
| When TTL reaches expiration | Cell is no longer live data | Expired cell is treated like a tombstone |
| During the grace period | Cell still does not appear as live | Deletion metadata still needed for reconciliation |
| After the grace period | Cell still does not appear as live | Tombstone **may be old enough** to purge, not guaranteed purged yet |
| After safe compaction | Cell still does not appear as live | Associated bytes **can be reclaimed** from SSTables |

**Warning on reading the table:** `gc_grace_seconds` does not mean "users can still read the data for 10 more days." TTL-expired data is already **logically invalid** before the tombstone-cleanup eligibility window even starts. And `TTL + gc_grace_seconds` is **not** a date when Cassandra guarantees physical deletion has finished.

## 3. How Metadata of a TTL Cell Is Used

For a regular value, Cassandra must track pieces of information with distinct roles:

| Metadata | Unit | Purpose |
|---|---|---|
| **Mutation timestamp** | Microseconds since Unix epoch | Reconciles versions via **last-write-wins (LWW)** |
| **Assigned TTL** | Seconds | Lifetime duration of the cell version |
| **Expiration time / local deletion time** | Time at second resolution | Determines when the cell expires and when cleanup eligibility applies |
| **Tombstone information** | By deletion scope | Prevents stale records from reappearing during reconciliation |

When writing a cell with TTL, Cassandra establishes expiration metadata from the mutation's processing time and the TTL. **TTL is not computed by adding TTL seconds to the mutation timestamp**. A client can set `USING TIMESTAMP` to a historical instant for version arbitration, yet a value just written with `USING TTL 60` still gets a fresh lifetime of roughly 60 seconds, assuming the mutation wins.

Illustrative example:

```text
value = "active"
write_timestamp = 1700000000000000 µs      # Historical LWW metadata
ttl = 60 seconds
expiration = time Cassandra processed the write + 60 seconds
```

The precision of mutation timestamps (µs) also **differs** from the resolution of TTL (seconds). Clocks on timestamp-generating hosts and Cassandra nodes must be synchronized; clock skew can cause both LWW bugs and unexpected expiration timing.

## 4. What Is a Tombstone and Why Can't It Be Deleted Immediately?

A **tombstone** is metadata marking that a value or data range was deleted. Cassandra needs it because replicas can become temporarily disconnected and data spans multiple **immutable** SSTables.

Example of a partition with an old version in SSTable A:

```text
SSTable A: status = "PENDING" @ timestamp 100
SSTable B: status = "PAID"    @ timestamp 200, TTL 60

At TTL expiration:
  "PAID" is no longer a live value;
  expiration/tombstone of the timestamp-200 version
  must shadow "PENDING" @ timestamp 100.
```

If the system wiped out all record of `PAID@200` without ensuring `PENDING@100` was already safely eliminated/shadowed, the old data could **reappear**. That is why **logical deletion** and **physical reclamation** must remain decoupled.

### Common Tombstone Scopes

- **Cell tombstone:** deletes a regular column or a collection element.
- **Row tombstone:** deletes a row by its full key.
- **Partition tombstone:** deletes an entire partition's scope.
- **Range tombstone:** deletes a range of clustering rows.
- **Expired TTL cell:** a TTL value that expired automatically; expiration metadata participates in reconciliation and garbage collection.

These deletion kinds do not carry the same cost or impact scope. Deleting wide row ranges, deleting many collection elements, or continuously writing short-TTL data can generate substantial metadata that reads and compaction must traverse.

## 5. Expired TTL Cell vs. Explicit `DELETE`: Similarities and Differences

| Characteristic | Expired TTL cell | Explicit `DELETE` |
|---|---|---|
| Trigger | Lifetime of the cell version ends | A delete mutation sent by a client |
| Extra delete request needed at expiration? | **No**, because the deadline is already in metadata | **Yes**, an initial `DELETE` request |
| Acts as a tombstone? | Yes, expiration shadows older versions | Yes, deletion marker shadows older versions |
| How deletion time is determined | From TTL/expiration metadata at write time | From the delete operation and its timestamp |
| Frees bytes immediately? | No | No |
| Observation via `ttl(col)` once no live cell remains | Does not return negative numbers | Tombstone timestamp cannot be read via `ttl()` |

A subtle detail: a replica that **already received the TTL cell** can evaluate that cell as expired on its own from expiration metadata without waiting for a new `DELETE` request. However, if a replica **never received the new TTL version**, that replica may still hold an **old version with no TTL**. Tombstone/expiration metadata from the new version and repair remain vital to stop stale data from coming back.

Therefore, never conclude "TTL doesn't need tombstones" just because it expires automatically. Conversely, never claim every replica must receive a new `DELETE` message when a TTL reaches zero.

## 6. CQL Hands-On: Logical Expiration While the Row Still Exists

Use a **test keyspace** created and selected with `USE <keyspace>;`. These examples do not touch production data; if the table already exists with another schema, use a separate name or inspect the schema rather than assuming `IF NOT EXISTS` changes an existing definition.

### 6.1. Create the Table

```sql
CREATE TABLE IF NOT EXISTS ttl_gc_lab_by_key (
    cache_key text PRIMARY KEY,
    payload text,
    retained_note text
);
```

### 6.2. Keep One Cell Without TTL, Write One Cell with TTL

```sql
-- Table has no default_time_to_live, so retained_note has no TTL.
INSERT INTO ttl_gc_lab_by_key (cache_key, retained_note)
VALUES ('expiry-demo-001', 'Keep row visible for inspection');

UPDATE ttl_gc_lab_by_key
USING TTL 20
SET payload = 'temporary-value'
WHERE cache_key = 'expiry-demo-001';

SELECT cache_key,
       payload,
       ttl(payload) AS remaining_seconds,
       writetime(payload) AS payload_write_us,
       retained_note,
       ttl(retained_note) AS note_remaining_seconds
FROM ttl_gc_lab_by_key
WHERE cache_key = 'expiry-demo-001';
```

Right after updating, `payload` is live; `remaining_seconds` is near 20. `retained_note` still has its value and `note_remaining_seconds` is `null` because it has no TTL.

After the 20-second TTL ends, re-run the `SELECT`. Then:

- The row can still be returned because `retained_note` is live.
- `payload` becomes `null` in the read result; `ttl(payload)` and `writetime(payload)` return no metadata for a live value.
- **You cannot conclude** that the bytes of `temporary-value` have been erased from every SSTable solely from this `SELECT` result.

### 6.3. When Every Data Cell Expires Together

```sql
INSERT INTO ttl_gc_lab_by_key (cache_key, payload)
VALUES ('expiry-demo-002', 'short-lived-only')
USING TTL 10;

SELECT cache_key, payload, ttl(payload)
FROM ttl_gc_lab_by_key
WHERE cache_key = 'expiry-demo-002';
```

Right after writing, the row has live data. After roughly 10 seconds with no other mutations, the query stops returning a live `payload` value; for a row whose only cells expired, the row generally disappears from query results. **Do not mistake the absence of a row in reads for Cassandra having deleted SSTable files.**

**Measurable practice:** wait long enough and confirm with `ttl()` before and after, without writing assertions like "equals exactly 20 or 0 seconds." Second-level TTL resolution, request flight time, and server clocks cause the count to vary.

## 7. CQL Hands-On: A Tombstone Shadows an Older Mutation

This example uses manual timestamps to prove that a tombstone must persist to block an **older** write. Do not apply these simulated timestamps to real data.

```sql
INSERT INTO ttl_gc_lab_by_key (cache_key, retained_note)
VALUES ('delete-demo-003', 'Permanent note');

-- Create the payload cell at a fixed older timestamp.
UPDATE ttl_gc_lab_by_key
USING TIMESTAMP 1700000000001000
SET payload = 'old-value'
WHERE cache_key = 'delete-demo-003';

-- Delete payload with a tombstone carrying a larger timestamp.
DELETE payload FROM ttl_gc_lab_by_key
USING TIMESTAMP 1700000000002000
WHERE cache_key = 'delete-demo-003';

-- A mutation arriving later yet carrying a lower timestamp than the tombstone.
UPDATE ttl_gc_lab_by_key
USING TIMESTAMP 1700000000001500
SET payload = 'stale-retry'
WHERE cache_key = 'delete-demo-003';

SELECT payload, writetime(payload), retained_note
FROM ttl_gc_lab_by_key
WHERE cache_key = 'delete-demo-003';
```

`payload` still has no live value because the tombstone `@1700000000002000` shadows `stale-retry@1700000000001500`. `retained_note` remains so the row stays observable.

**Note:** `writetime(payload)` does not let you see the tombstone's timestamp directly once the cell is deleted. Inspecting actual deletion metadata requires mutation history, logs, or appropriate SSTable tools.

This example also illustrates why **reclaiming a tombstone too early** can be dangerous: on another replica or SSTable, the `old-value` version may still exist.

## 8. What Does `gc_grace_seconds` Do—and What Does It Not Do?

`gc_grace_seconds` is a **table** property, measured in **seconds**, defining the protective grace window before a tombstone becomes eligible for garbage collection. A common default is **864000 seconds (10 days)**; always inspect the actual table configuration and Cassandra version rather than assuming every system keeps that default.

Example creating a test table with explicit configuration:

```sql
CREATE TABLE IF NOT EXISTS ttl_grace_demo_by_id (
    item_id uuid PRIMARY KEY,
    payload text
) WITH gc_grace_seconds = 864000;
```

Accurate understanding:

- **Not TTL:** `USING TTL 60` still causes the cell to expire logically after roughly 60 seconds; `gc_grace_seconds` does not let applications keep reading the cell for 10 extra days.
- **Not a cleanup schedule:** after the grace period, Cassandra **may** consider dropping the tombstone during compaction if safe; there is no guarantee disk usage drops at that exact mark.
- **Not a replacement for repair:** if a replica missed a delete mutation and comes back too late, purging tombstones can allow stale data to be reconciled back into existence.
- **Not a retention window for live data:** a cell without TTL persists until another mutation replaces/deletes it or another lifecycle rule applies.

For **TTL expiration**, the timestamp governing tombstone age eligibility is typically evaluated from **the expiration instant**, not simply "`INSERT` time + grace." For explicit **DELETE**, the deletion timestamp ties to the delete time. Both must be interpreted via internal metadata and system clocks; never take `writetime()` and mechanically add `gc_grace_seconds` to predict a physical cleanup date.

**Never set `gc_grace_seconds = 0` arbitrarily to force Cassandra to clean up immediately.** Doing so shrinks the safety buffer against stale records from replicas—especially hazardous when nodes disconnect, repairs lag, or snapshots/SSTables overlap.

## 9. Zombie Data: Scenario Where One Replica Misses a TTL Update

Consider a partition with **RF = 3** across three replicas A, B, C. Suppose all three initially hold `status = OLD@100` with **no TTL**.

```text
Time t0:
       A: OLD @100            B: OLD @100          C: OLD @100
                                                      |
                                                 C disconnects

Time t1:
       A: NEW @200, TTL 60   B: NEW @200, TTL 60   C: OLD @100

Time t1 + 60 seconds:
       A: NEW expired         B: NEW expired        C: OLD still live
          tombstone @200         tombstone @200

If tombstones are purged unsafely and C returns:
       C can propagate OLD @100, causing old data to reappear.
```

While the `@200` tombstones remain valid and are reconciled, they shadow `OLD@100`. Once they are garbage-collected before C's state has been reconciled, the system may no longer retain enough evidence of the expired newer version to suppress the old copy.

This scenario does not claim **every** TTL cell comes back to life on node loss. Any replica that already received `NEW@200`'s expiration metadata can tell it expired. The risk depends on which mutations replicas received, which older versions persist, outage duration, repair, and tombstone-collection policy.

**Operational principle:** schedule repairs and manage node offline durations so replicas synchronize **before deletion metadata becomes eligible for safe removal under policy**. Never assume hinted handoff alone replaces repair in every situation.

## 10. From Eligibility to Reclamation: What Conditions Does Compaction Need?

Cassandra stores data in **immutable SSTables**. Deleting a value does not immediately edit bytes inside every SSTable; the system relies on compaction to merge versions and drop unneeded data/tombstones.

An **aged** tombstone is not always **purged immediately**:

1. The tombstone must have exceeded the configured grace window.
2. Cassandra must avoid exposing an older version still sitting in **another SSTable with overlapping data ranges**.
3. The compaction strategy and selected SSTables determine when reconciliation and cleanup actually occur.
4. Distributed replicas and repair schedules must operate compatibly with garbage-collection rules.

```text
SSTable 1              SSTable 2                 SSTable 3
old-value @100         tombstone @200             other data
     |                       |
     +----------+------------+
                |
       Eligible compaction
                |
     Reconciles old-value with tombstone
                |
     Only if safe does it drop both the shadowed
     data and the unneeded marker.
```

Purging a tombstone by looking only at SSTable 2 could uncover `old-value@100` in SSTable 1. That is why compaction must evaluate overlaps and safety checks rather than comparing tombstone age alone.

### Related Terms

- **Memtable:** in-memory data before flushing to disk.
- **SSTable:** immutable on-disk data file, never modified in place.
- **Compaction:** merges SSTables and filters out versions/tombstones that can be safely discarded.
- **Repair:** exchanges/compares data across replicas to detect and fix inconsistencies.
- **Tombstone garbage collection:** removing unneeded deletion metadata; distinct from Java GC freeing heap memory.

`nodetool compact` (when supported in your running version) can request compaction work, yet **does not guarantee all expired cells will disappear**. Do not force compactions in production as a harmless test: it generates substantial I/O and can alter SSTable layout for future compactions.

## 11. Compaction Strategies for TTL-Heavy Workloads

A table with heavy TTL writes can generate substantial tombstones/expired cells. Choosing a suitable **compaction strategy** helps SSTables that expire together get reclaimed more efficiently.

| Strategy / workload pattern | Key points to understand |
|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Merges by size tiers; fits some write-heavy workloads, though expired cells can linger in overlapping SSTables for a long time |
| **LeveledCompactionStrategy (LCS)** | Controls overlap across levels; often fits many read-heavy patterns, with higher write/compaction overhead |
| **TimeWindowCompactionStrategy (TWCS)** | Often helpful for **time-series/append-only** data with fairly uniform TTL, limiting mixing of different time periods into the same SSTable |

Schema example geared toward sensor data by device and day:

```sql
CREATE TABLE IF NOT EXISTS sensor_events_by_device_day (
    device_id text,
    event_day date,
    event_time timeuuid,
    reading double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC)
  AND default_time_to_live = 604800
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
```

Here the default TTL is **604800 seconds = 7 days**, and TWCS groups into one-day windows in the example. **This is not a universal configuration**; evaluate late-arriving data, update/delete rates, SSTable sizes, and TTL distribution.

TWCS works best when writes carry timestamps matching the current window and data is mostly **append-only** with uniform TTL. **Very old backfills, out-of-order writes, random updates**, or widely varying TTLs can make expired-SSTable cleanup ineffective and keep tombstones around longer.

**Choose clustering keys around queries**, such as `event_time`, not `writetime(reading)`; mutation timestamps serve LWW, not event-history querying. For high data volumes, tune time buckets so partitions stay bounded.

## 12. Diagnostics: When Should You Suspect Tombstone Pressure?

Common symptoms on TTL-heavy or DELETE-heavy tables:

- **Slow reads** even when few rows are returned: queries must scan past many deleted/expired cells.
- **High compaction backlog**, growing disk I/O and SSTable footprint despite short TTLs.
- **Queries triggering tombstone warnings** or hitting configured Cassandra safety thresholds.
- **Prolonged replica repairs** or offline nodes making safe tombstone purging problematic.
- **Data disappearing from SELECT while disk usage fails to drop** as operators expected.

Gather evidence by table, partition, and time rather than guessing:

| Question | Investigation path |
|---|---|
| Is the cell still live? | `SELECT value, ttl(value), writetime(value) ... WHERE partition_key = ...` |
| Was a TTL actually set? | `USING TTL` in CQL, table `default_time_to_live` |
| Are there continuous DELETEs/overwrites? | Application logs, tombstones/query latency, and mutation history |
| How long are tombstones retained? | `gc_grace_seconds`, schema, replica downtime, repair schedule |
| Is compaction backed up? | Metrics and `nodetool compactionstats` per version |
| What is the tombstone-to-read ratio? | Table stats, query metrics, tombstone warnings |
| Are overlapping SSTables delaying purges? | Compaction strategy and appropriate SSTable inspection tools |
| Are snapshots/backups holding disk space? | Snapshot/backup policies and how disk usage is measured |

Common operational check commands—**do not run in production without authorization and understanding impact**:

```bash
# Run in an appropriate Cassandra administration environment.
nodetool status
nodetool compactionstats
nodetool tablestats my_keyspace.ttl_gc_lab_by_key
```

Output, metric fields, and syntax depend on the Cassandra version. `nodetool tablestats` is helpful for table-level statistics, yet does not output a date saying "when all tombstones will be purged." Deep investigations may require offline SSTable/metadata tools matching the exact version or controlled tracing.

## 13. Java Driver: Distinguishing No Live Data from No Bytes on Disk

Java applications using **Apache/DataStax Cassandra Java Driver 4.x** can read TTL and write timestamps. The repository example below queries strictly by partition key without scanning tables:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TtlGcReader {
    private final CqlSession session;
    private final PreparedStatement putTemporary;
    private final PreparedStatement get;

    public TtlGcReader(CqlSession session) {
        this.session = session;
        this.putTemporary = session.prepare(
            "UPDATE ttl_gc_lab_by_key USING TTL ? " +
            "SET payload = ? WHERE cache_key = ?"
        );
        this.get = session.prepare(
            "SELECT payload, ttl(payload) AS ttl_s, " +
            "writetime(payload) AS write_us, retained_note " +
            "FROM ttl_gc_lab_by_key WHERE cache_key = ?"
        );
    }

    public void write(String key, String value, int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        session.execute(putTemporary.bind(ttlSeconds, value, key));
    }

    public void inspect(String key) {
        Row row = session.execute(get.bind(key)).one();
        if (row == null) {
            System.out.println("No live row visible");
            return;
        }

        String payload = row.getString("payload");
        Integer remaining = row.isNull("ttl_s")
            ? null : row.getInt("ttl_s");
        Long writeTimestampMicros = row.isNull("write_us")
            ? null : row.getLong("write_us");
        String note = row.getString("retained_note");

        System.out.printf(
            "payload=%s, ttlSeconds=%s, writeMicros=%s, note=%s%n",
            payload, remaining, writeTimestampMicros, note
        );
    }
}
```

**Accurate interpretation:**

- `row == null` means the query returned no matching live row at that instant/consistency level. You cannot conclude SSTables hold zero bytes from this.
- `payload == null` with `note != null` can occur because `payload` was never written, expired via TTL, or was deleted. `ttl(payload)` and `writetime(payload)` do not expose tombstone info.
- `ttl_s` is **remaining seconds**, not an epoch timestamp; `write_us` is **epoch microseconds**, not physical deletion time.
- If different replicas temporarily hold different versions, consistency level and reconciliation affect reads. Do not treat `ONE` and `ALL` as tools that override LWW rules.

If business logic must enforce strict deadlines (tokens, vouchers, or access grants), also store **`expires_at` in UTC** and validate it in the application. TTL helps Cassandra clean up data automatically; **it does not replace business-layer expiration and security checks**.

## 14. Safe Operations: Repair First, Do Not Lower Grace to "Free Disk"

An operational workflow should address the actual root cause:

1. **Confirm data is logically expired.** Read the exact partition key and column, compare `ttl()` before/after, watching for columns written without TTL or overwritten later.
2. **Verify table settings and compaction strategy.** Inspect `default_time_to_live`, `gc_grace_seconds`, compaction strategy, overwrite/delete rates, and partition sizes.
3. **Check replica health.** Review downed nodes, out-of-sync replicas, repair schedules, backups, and topology changes.
4. **Identify why bytes remain on disk.** It could be uncompacted SSTables, tombstones not yet past grace, overlapping SSTables, or snapshots/backups holding files.
5. **Assess impact before making changes.** Switching compaction strategies, changing grace periods, or forcing compactions requires evaluating I/O, write amplification, and data safety.
6. **Monitor after changes.** Track tombstone warnings, read latency, pending compactions, disk usage, and repair runs.

### Why Shouldn't You Arbitrarily Set `gc_grace_seconds = 0`?

Lowering the grace period does not make TTL cells expire "faster": cells already expired at their TTL deadline. It only **shortens the safety window** before tombstones become eligible for purging. In multi-replica environments with prolonged node outages or unverified repairs, that is a severe trade-off carrying the risk of stale data resurfacing.

Certain specialized architectures or operational conditions may allow a lower grace setting, yet only after thoroughly verifying workload semantics, node-failure tolerance, repair SLAs, and recovery procedures. Never copy a "speed up tombstone cleanup recipe" blindly across clusters.

### Why Doesn't Forcing Compaction Guarantee Immediate Reclamation Either?

Even when a tombstone is old enough, Cassandra must ensure no older version in overlapping SSTables could be exposed; compaction is I/O-intensive and may not include all SSTables simultaneously. Furthermore, snapshots, backups, or other versions can occupy disk space. Measure the actual reclaimable footprint rather than equating directory size with live row count.

## 15. Designing Tables to Minimize TTL Cost Up Front

In Cassandra, **query-driven table design** is key. If the data model forces Cassandra to scan past large amounts of expired data to return very few live rows, even a properly configured TTL can slow down the system.

Design directions to consider:

| Workload pattern | Direction to consider | What to avoid |
|---|---|---|
| Time-series data with uniform retention | Time buckets + relatively uniform TTL + TWCS where suitable | Random backfills mixing compaction windows |
| Latest state updated repeatedly | Dedicated latest-state table, control TTL/retries | Rapidly overwriting the same cell with tiny TTLs unnecessarily |
| Append-only event history | One row per event, time-based clustering key | An unbounded list/map inside a single partition |
| Data "valid until an exact deadline" | `expires_at` in business logic, TTL for storage support | Believing TTL dictates exact physical deletion hours |
| Lookup by specific keys | Query with explicit partition key | `ALLOW FILTERING` / full scans to locate expired rows |

**TTL creates future compaction work**. When assigning a 1-hour retention to millions of cells per minute, size storage for live data, uncollected expired data, tombstone overhead, temporary compaction headroom, and replicas/snapshots. Never use a naive "write rate × TTL" as an absolute ceiling for disk usage.

## 16. Misconceptions to Eliminate

| Misconception | Accurate understanding |
|---|---|
| "When TTL expires, data vanishes from disk." | TTL expiration makes the cell **logically non-live**; bytes can remain until safe compaction |
| "TTL 60 with 10-day grace means readable for 10 days + 60s." | Grace protects **tombstone** safety, not live data readability |
| "Once `gc_grace_seconds` passes, cleanup happens on the dot." | Tombstones only become **eligible by age**; compaction and safety conditions are still needed |
| "Running compaction removes all tombstones immediately." | SSTable overlap, tombstone age, strategy, and data safety all govern purging |
| "TTL needs no tombstones because each replica expires independently." | Replicas holding expiration metadata expire on their own; stale copies on other replicas may still need shadowing |
| "`writetime()` tells when the tombstone was purged." | It is the write timestamp of an observable **live cell** |
| "Repair automatically fixes a wrong TTL policy." | Repair converges replicas; it does not alter TTL definitions or business semantics |
| "Dropping grace to 0 is always safe." | Can raise **zombie data** risk if replicas have not converged |
| "No row in SELECT means no data left in backups." | Live-data queries do not reflect SSTables, snapshots, or backups |

## 17. Scenario Exercises and Answers

**Question 1.** A cell is written with `USING TTL 60`. After 65 seconds, `SELECT` no longer shows the value, yet disk usage has not changed. Is this a TTL bug?

**Answer:** Not necessarily. The cell has **logically expired**; bytes/tombstones may remain in SSTables awaiting compaction and safe reclamation conditions.

**Question 2.** A table has `gc_grace_seconds = 864000`. Will a cell with a 30-second TTL remain readable for another 10 days?

**Answer:** No. The cell expires logically after roughly 30 seconds; grace does not add to user-visible lifetime.

**Question 3.** Once `gc_grace_seconds` has elapsed, is expired data guaranteed to be physically deleted immediately?

**Answer:** No. It still depends on compaction, overlapping SSTables, replicas/repair, and snapshots/backups outside the live dataset.

**Question 4.** A replica missed the new `VALUE@200 TTL 60` version and still holds `OLD@100` with no TTL. Why does expiration/tombstone metadata of the `@200` version matter?

**Answer:** It prevents `OLD@100` from returning when replicas reconcile. If the marker is purged unsafely before fixing the divergence, **zombie data** can appear.

**Question 5.** `writetime(payload) = null` after `payload`'s TTL expired. Can you conclude the tombstone has been purged?

**Answer:** No. `writetime()` does not display tombstones; `null` only indicates there is no live cell write timestamp in that read result.

**Question 6.** Why doesn't lowering `gc_grace_seconds` hide expired data from `SELECT` faster?

**Answer:** **TTL/expiration** rules already hide expired data from live reads on schedule. Grace only governs the protection window before tombstones can be garbage-collected.

**Question 7.** For a daily append-only workload with 7-day retention, should TWCS be considered?

**Answer:** Possibly, if write patterns and TTLs align, data mostly follows time order, and out-of-order/backfill writes are minimal. Verify partition sizes, update rates, and actual operational strategy.

**Question 8.** A row has `retained_note` without TTL and `payload` with a 10-second TTL. After 10 seconds, must the entire row vanish?

**Answer:** No. `payload` is no longer live, yet `retained_note` can keep the row visible in query results.

**Question 9.** An application must ensure a token cannot be used after `12:05:00`. Should it rely solely on Cassandra TTL?

**Answer:** No. Enforce **`expires_at`/business deadline** during validation while using TTL for expiration and storage lifecycle management.

---

**Key takeaway:** In Cassandra, **logical expiration → tombstones/expiration protecting correctness → eligible compaction performing physical reclamation** are three separate stages. `gc_grace_seconds` neither extends live data lifetime nor schedules fixed-hour byte deletion; it protects replica reconciliation against zombie data. Query-driven table design, suitable TTL/compaction choices, regular repairs, and metric monitoring are what ensure expired data is cleaned up **accurately and safely**.
