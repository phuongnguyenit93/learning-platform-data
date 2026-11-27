# gc_grace_seconds and Tombstone Retention Conditions

In Apache Cassandra, deleting a value does not immediately remove every byte of that value from disk. Old data can still exist in SSTables or on a replica that has not yet received the delete operation. Cassandra uses **tombstones** — deletion markers carrying time information — to shadow those older versions during reads and data merging.

So **how long must Cassandra retain a tombstone?** The `gc_grace_seconds` setting is an important part of the answer, though not the whole story. Once the grace period has passed, a tombstone only **becomes eligible** for reclamation; Cassandra must still consider SSTables containing older data, replica state, compaction, and the garbage collection mechanics of the running version. Cleaning up deletion markers too early can create **zombie data**: deleted data suddenly reappears when an old replica is brought back into the system.

This lesson belongs to the **Tombstones and Reclamation** chapter of the Apache Cassandra module, connecting distributed wide-column architecture, partition keys, replication, consistency levels, repair, compaction, CQL, and Java applications.

After this lesson, you will be able to:

1. Accurately explain the meaning of `gc_grace_seconds` and why it is **not a physical deletion schedule**.
2. Distinguish between **write timestamp**, **local deletion time**, **TTL expiry**, and **compaction time**.
3. Describe how a replica missing a DELETE leads to zombie data risk.
4. Identify conditions that retain tombstones even after the grace period has elapsed.
5. Schedule repairs and manage offline/recovering nodes consistently with tombstone reclamation policy.
6. Evaluate the impact of TTL, compaction, partition size, and queries reading through tombstones.
7. Practice inspecting/modifying settings via CQL, operational monitoring, and using the Java Driver safely.

## 1. Why is a tombstone retention window needed?

Suppose a partition has three replicas **A, B, C** according to the keyspace's replication strategy. Before deletion, all three hold the value:

```text
payload = "temperature=38.1"
write timestamp = 100
```

Replica C loses connectivity. The application sends a `DELETE`; A and B receive and record a deletion marker with write timestamp 200, while C still keeps the old value.

```text
               Before deletion
       A                  B                  C
  payload @100       payload @100       payload @100

               C is disrupted
       A                  B                  C
  DELETE @200        DELETE @200        payload @100
  payload @100       payload @100       (missed DELETE)

               On read/reconciliation of true state
   Tombstone @200 can shadow any still-existing payload @100.
```

If A and B drop the tombstone before C learns about the deletion, and C later comes back, the `payload @100` copy can become a live data version that is visible and propagated. This phenomenon is called **zombie data**.

Cassandra must **preserve deletion information long enough** so that replicas that missed a deletion have an opportunity to synchronize through an appropriate mechanism such as anti-entropy repair. The retention window for this purpose is partially controlled by `gc_grace_seconds` at the table level.

**Conclusion:** tombstones are not useless clutter; they carry **distributed deletion semantics**. Lowering the retention time for deletion markers is a data-correctness decision, not merely disk optimization.

## 2. What is `gc_grace_seconds`?

`gc_grace_seconds` is a **Cassandra table property** representing the duration in seconds related to when a tombstone is allowed to be considered for **garbage collection**. It creates a protection window giving a replica that missed a delete mutation a chance to be repaired before the marker disappears from sources that can shadow the old value.

A commonly seen configuration example in Cassandra is:

```cql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH gc_grace_seconds = 864000;
```

`864000` seconds equals **10 days**. This is a common default seen in many Cassandra versions, but **you must check the actual configuration of your table and running version**, rather than assuming from an example.

### True and false statements

| Statement | Assessment | Explanation |
| --- | --- | --- |
| "`gc_grace_seconds` is measured in seconds." | True. | It is a table option, not a query timeout. |
| "It relates to how long tombstones must be kept." | True. | Tied to deletion safety and the risk of replicas missing mutations. |
| "After 10 days Cassandra definitely deletes tombstones immediately." | **False.** | Still depends on compaction, SSTable overlap, and reclamation conditions. |
| "It can be lowered to fix every tombstone-slow query." | **False.** | Risks zombie data and does not address the source generating tombstones. |
| "Raising consistency level renders `gc_grace_seconds` irrelevant." | **False.** | Consistency neither synchronizes all replicas nor purges tombstones. |
| "Properly scoped and scheduled repair matters for this setting." | True. | Must ensure replicas do not retain old versions when deletion markers are reclaimed. |

**Scope of meaning:** `gc_grace_seconds` does not set a TTL for live cells, does not dictate how long a partition is allowed to exist, and does not guarantee deletion of data from snapshots/backups.

## 3. Four time concepts you must not confuse

When analyzing a tombstone, separate these timestamps:

| Concept | Unit / source | What is it used for? |
| --- | --- | --- |
| **Event time** | E.g., business-defined `occurred_at timestamp` | Time-bucket routing, clustering order, historical queries. |
| **Write timestamp** | Usually microsecond precision; attached to mutation/cell | Reconciling live versions and tombstones, conflict resolution. |
| **Local deletion time** | Deletion/expiration timestamp in tombstone metadata, usually second precision | Checking tombstone age to evaluate garbage collection eligibility. |
| **Compaction time** | When the compaction process actually runs | Opportunity to merge SSTables and reclaim eligible data. |

Conceptual example:

```text
Business event occurred at 08:00 UTC.

Written to Cassandra at 08:03.
  write timestamp: T_write

DELETE at 09:00.
  write timestamp: T_delete, greater than T_write
  local deletion time: time when deletion was recorded

After gc_grace_seconds:
  tombstone may become old enough to consider for reclamation

Later, when eligible compaction runs and conditions are met:
  SSTables can be rewritten to drop data/markers.
```

**Write timestamp decides which data wins**, while **local deletion time** relates to **tombstone age for cleanup**. Never use `occurred_at`, a business clustering column, to calculate tombstone age.

### Clocks and client-specified timestamps

Cassandra allows mutations to carry client-specified write timestamps in supported cases. Using timestamps in the future, unsynchronized clocks, or competing writes/deletes with skewed timestamps can make reconciliation outcomes unpredictable.

Do not arbitrarily set a huge future write timestamp for DELETE intending to "permanently delete." Valid data written later with a lower timestamp could still be shadowed by the marker. Manage clocks and mutation semantics intentionally.

## 4. Distinguishing logical deletion from physical reclamation

A delete command takes logical effect as soon as the tombstone beats relevant versions under read and consistency semantics. However, the tombstone and old data can sit in memtables/SSTables until validly cleaned up.

```text
DELETE / NULL write / TTL expiry
                 |
                 v
        Effective tombstone
                 |
                 +--> Queries do not return shadowed value
                 |
                 +--> SSTables/replicas may still hold old value
                 |
                 v
       Old enough per gc_grace_seconds?
                 |
            No  /  Yes
                 |
            retain / evaluate further
                         |
                         v
        Does an uninvolved SSTable hold old data
        or another safety check block purge?
                         |
                 Yes  /  No
                  |       |
               retain     v
                   Compaction can purge
                   data/marker when safe
```

The flow above is a **conceptual model**, not a literal step-by-step simulation of compaction in all Cassandra versions. Purge conditions depend on SSTable format, compaction mechanics, tombstone type, and version policy.

### Comparison table

| Aspect | Logical deletion | Physical reclamation |
| --- | --- | --- |
| Triggered by | DELETE/NULL/TTL expiry and timestamp rules | Compaction/garbage collection when data is eligible |
| Effect on SELECT | Old value is shadowed, no longer live if deletion wins | Does not necessarily change SELECT results |
| Effect on SSTable bytes | May temporarily **increase** because a marker is written | May decrease after files are merged/cleaned |
| Relation to `gc_grace_seconds` | Does not wait for grace to take logical effect | Grace is one of the conditions checked for purge |
| Replica/repair dependency | Read/reconciliation may need newer replicas | Must avoid zombies when a replica still holds old data |

**A common operational mistake:** seeing `DELETE` succeed yet total `space used` has not dropped, and concluding DELETE is broken. Cassandra may be intentionally holding tombstones and waiting for safe reclamation conditions.

## 5. Types of tombstones `gc_grace_seconds` relates to

Not all tombstones have the same scope. Cassandra can record deletion markers at several levels:

| Marker form | Example | Scope |
| --- | --- | --- |
| **Cell tombstone** | `DELETE payload` with full primary key | One regular cell |
| **Static-cell tombstone** | `DELETE note` with partition key | One static cell of the partition |
| **Collection element tombstone** | `DELETE attributes['source']` | One element of a non-frozen collection |
| **Complex/collection deletion** | `DELETE attributes` on a non-frozen map | One collection and its old elements |
| **Row tombstone** | `DELETE FROM ... WHERE full_primary_key` | One clustering row |
| **Range tombstone** | Deleting a clustering slice supported by CQL/version | Multiple rows in a slice within one partition |
| **Partition tombstone** | `DELETE FROM ... WHERE partition_key` | Rows and static data across the entire partition |
| **Expired cell / TTL tombstone** | Value whose TTL has expired | Cell/data written with the corresponding TTL |

Every scope functions to **shadow older data** using timestamp information and reconciliation rules. `gc_grace_seconds` is a key parameter for evaluating deleted data cleanup, though exact representation and reclamation checks can vary across tombstone forms and versions.

**Do not infer one DELETE statement = one physical tombstone = one deleted row.** One range tombstone can shadow thousands of clustering rows; one non-frozen collection can produce many element tombstones; and multiple delete operations can merge during compaction.

## 6. CQL lab: creating a table, DELETE, and viewing grace settings

The following examples use `app_ks`, a keyspace **assumed to be created appropriately for a lab environment**; all data-modifying statements must run against test tables.

### Create table

```sql
CREATE TABLE app_ks.device_events_by_day (
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
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
) AND gc_grace_seconds = 864000;
```

The partition key consists of `tenant_id`, `device_id`, and `event_day`. If two events belong to the same device on the same day, they belong to the same partition, differing only in `occurred_at` and `event_id`.

### Write sample data

```sql
INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);

INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading',
    'temperature=38.4'
);
```

### Delete one cell

```sql
DELETE payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

After the mutation, the 08:00 row **can still remain live** thanks to `event_type`; only `payload` is deleted at the corresponding write timestamp.

### Viewing table options in cqlsh

```sql
DESCRIBE TABLE app_ks.device_events_by_day;
```

`DESCRIBE` is a **cqlsh** command, not a CQL SELECT statement executed by the Java Driver. It lets you inspect the schema and table options, including `gc_grace_seconds`, in your current environment.

**Controlled practice:** do not lower grace on a production table just to watch tombstones disappear quickly; that operation can alter deletion safety conditions for unsynchronized replicas.

## 7. What does `ALTER TABLE gc_grace_seconds` actually do?

Changing the table value via CQL:

```sql
ALTER TABLE app_ks.device_events_by_day
WITH gc_grace_seconds = 864000;
```

The example sets **10 days**. If the table already had this value, the operation does not change the intended policy.

### What does not happen

- Cassandra **does not automatically move data** to another partition key.
- Tombstones **do not vanish immediately** just because the setting was lowered.
- SSTables **are not all rewritten immediately** after ALTER.
- Repair **does not run automatically** to ensure every replica has received deletions.
- The setting **does not create an SLA** that data is physically erased before an absolute deadline.

What matters is that **purge eligibility evaluation** references the grace period and current state when the reclamation mechanism runs. When you change the setting, existing tombstones can become subject to evaluation under the new condition; therefore **lowering the value is a risky operation**, not a change that only affects future DELETEs.

### If increasing the grace value

Increasing `gc_grace_seconds` can cause more tombstones to be retained longer before becoming eligible for cleanup evaluation, leading to:

- SSTable and tombstone footprints persisting longer.
- Queries over deleted regions potentially having to process more markers/old versions.
- Compaction potentially being unable to purge data even when it runs.

This is a trade-off to establish a safety margin aligned with how long replicas can be disrupted and the repair schedule. Measure impact on your workload; **raising grace does not fix broken repairs by itself**.

## 8. Tombstone reclamation conditions: not just marker age

An oversimplified view is "tombstone age greater than `gc_grace_seconds` means erase from disk." In practice, reclamation also depends on whether older data might still be visible elsewhere.

### 8.1. Tombstone is old enough

Cassandra checks metadata such as deletion/expiration time to determine whether the marker has passed the applicable protection window. If not yet old enough, it generally must be retained.

### 8.2. SSTable overlap and old data not in the compaction

Immutable SSTables can contain older live data for the same partition and clustering range. If you only compact the SSTable holding the tombstone while another **uninvolved** SSTable still holds the old value, purging the tombstone can cause that value to reappear on the next read.

```text
SSTable-A: payload = "old" @100
SSTable-B: tombstone payload @200

Compact only B and drop tombstone:
  A still contains "old" -> risk of resurrecting data

Safe compaction:
  must consider whether A or another source still holds old data,
  and only purge when doing so does not lose needed shadowing info.
```

Thus, **being past grace is not enough** to conclude a tombstone in one SSTable can be purged independently. Cassandra has overlap/safety checks tailored to the compaction mechanism and version; operators should not assume all cases share the same cleanup path.

### 8.3. Which replica still holds an old version?

A replica can miss a delete mutation due to network outage, hardware failure, or restoring from an old snapshot. `gc_grace_seconds` establishes a protection window giving the system time to **synchronize deletions via repair/appropriate update paths**.

Subtle point: compaction on one node **does not by itself prove** that all other replicas received the deletion marker. Therefore, do not conclude cluster-wide deletion safety just because "compaction succeeded on node A."

### 8.4. Compaction must actually happen

Even when a tombstone is eligible, if no suitable compaction has run, the data can remain in SSTables. Compaction schedules, strategy, backlog, disk space, and system load can delay or postpone reclamation.

### 8.5. Repaired/unrepaired SSTables and version policies

In some versions/configurations, the **repaired/unrepaired** state of SSTables and related garbage collection options also affect compaction/purge conditions. Do not blindly apply rules from another version; read the configuration and semantics of the **exact Cassandra version you run** before changing reclamation policies.

**Summary table:**

| Condition | Question to answer |
| --- | --- |
| Deletion age | Has the tombstone passed the applicable grace window? |
| SSTable overlap | Could any old data version appear if the marker is dropped? |
| Replica/repair | Might any replica hold an old version without the deletion? |
| Compaction | Is suitable compaction scheduled and resourced to run? |
| Tombstone type | Do cell/row/range/partition or expired TTL markers have differing conditions? |
| Version/config | How are tombstone garbage collection options and repaired state handled? |

## 9. Three timeline scenarios: safe reclamation and zombie risk

### Scenario A — Replica synchronizes on time

```text
Day 0:   A, B, C hold old value.
Day 1:   C is offline; A, B receive DELETE.
Day 2:   C recovers; repair/sync delivers deletion to C.
Day 11+: Tombstone is old enough per 10-day grace setting,
         compaction can consider purging if other conditions pass.
```

Milestones are illustrative. If repair truly syncs all relevant data so no old version is missed on C, zombie risk from that scenario is mitigated.

### Scenario B — Replica offline too long

```text
Day 0:  C goes offline.
Day 1:  A, B receive DELETE, creating tombstone.
Day 11: 10-day grace since deletion has passed.
Day 12: A/B may purge tombstone when mechanics allow.
Day 20: C returns carrying the old value.
```

C **risks** making old data visible or propagating back because deletion information has disappeared from sources capable of shadowing it. This is what offline/repair policies must prevent.

### Scenario C — Tombstone past grace yet not purged

```text
Day 1:  DELETE creates tombstone.
Day 11: Tombstone is old enough per grace.
Day 14: Another SSTable still has old data; overlap checks
        or compaction state cause the tombstone to be kept.
Day 18: Suitable compaction can finally clean up when safe.
```

**Passing grace does not force physical deletion on day 11.** Any dashboard showing "deletion deadline = tombstone date + grace" must clearly label it as an **eligibility milestone**, not a purge SLA.

## 10. Repair must align with the grace period

Repair synchronizes data across replicas, including discrepancies caused by nodes having been offline or missing mutations. It is a pillar of tombstone management.

### Basic operational rule

In traditional Cassandra models, a common recommendation is ensuring **relevant replicas/ranges are repaired successfully within a window shorter than `gc_grace_seconds`** when the system risks missed deletions. Do not merely schedule a job: **verify the job succeeds across the required scope** and budget for failures, retries, and node outages.

```text
Assumed grace: 10 days

Do not:
  repair once every 10 days right near the deadline,
  ignore failures and assume you are protected.

Do:
  schedule repairs with a safety margin,
  monitor progress/range coverage and failures,
  handle offline nodes before outage duration exceeds the safety window.
```

### Why might one repair run not be enough?

- A repair run might **not cover all token ranges or tables** if job configuration/scope is restricted.
- Jobs can be canceled, time out, hit network errors, or fail to finish on some nodes.
- Special maintenance requirements may apply when a data center disconnects for a long time, a node is replaced, or a snapshot is restored.
- Cassandra has **full/incremental repair** and mechanisms improved across versions; do not infer "repair is enabled" means "all deletions are safe."

### Example command for lab practice

```bash
nodetool repair app_ks device_events_by_day
```

**Do not run large-scale repair commands in production just to practice.** Repair consumes CPU, network, disk I/O, and can impact latency. Exact syntax, default scope, and full/incremental strategies must be verified for your version/topology; establish a dedicated operational runbook before applying.

### Hinted handoff does not replace repair

Hints can forward mutations missed by a replica under certain conditions and configured limits. However, **never rely on hints as a guarantee that a long-offline replica will receive every DELETE**. Hint retention windows, coordinator failures, and other limits can leave them incomplete; anti-entropy repair still has an essential role.

## 11. Do consistency level and replication factor replace grace?

**No.** Replication factor (RF) specifies the number of logical replicas under the replication strategy; consistency level (CL) specifies read/write acknowledgment requirements, not when tombstones can be dropped.

Example with RF = 3 in one data center:

- A mutation at `LOCAL_QUORUM` requires acknowledgment from a quorum of relevant replicas.
- The third replica may **not have received the mutation yet** when the client receives acknowledgment.
- Later, nodes may go offline, hints may be insufficient, or repair may lag.
- Reading at a low CL from a stale replica can show stale state depending on read path and timing.
- Reading and reconciling across replicas at an appropriate CL allows a newer tombstone to shadow an old value, yet that **is not equivalent** to the deletion having reached all replicas or having been safely reclaimed.

| Mechanism | Responsible for | Does not guarantee |
| --- | --- | --- |
| RF | Replica count and durability per topology | Does not split partition keys or purge tombstones |
| `LOCAL_ONE` | Single-replica ack/read in the relevant DC | Not guaranteed to read the latest version |
| `LOCAL_QUORUM` | Quorum level in the relevant DC | Does not immediately sync all replicas |
| Hints | Forwards missed mutations within supported limits | Does not replace repair for long outages |
| Repair | Syncs discrepancies across replicas in covered scope | Does not run automatically just because grace passed |
| Compaction | Reorganizes SSTables, can purge eligible data | Does not repair other replicas on its own |
| `gc_grace_seconds` | Protection window before considering tombstone purge | Not a physical deadline or repair schedule |

**Do not lower grace solely because you use `LOCAL_QUORUM`.** You must prove that topology, failure modes, repair schedules, and recovery policies support the desired safety level.

## 12. Expired TTLs also relate to tombstone retention

TTL (*time to live*) causes data to expire automatically after a number of seconds under the semantics of the written value. Upon expiration, the cell is no longer live in read results; in SSTables, expiration metadata is treated as a deleted state that must be cleaned up when safe.

### Writing TTL with CQL

```sql
INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-after-one-hour'
) USING TTL 3600;
```

One hour after write time under TTL semantics, the values written with TTL are no longer live. However:

1. **No job has to send a new DELETE** at the exact second of expiration.
2. **There is no guarantee SSTables shrink immediately** after TTL expiry.
3. `payload`'s TTL does not implicitly delete other cells without TTL or the entire partition.
4. Rewriting a cell with a new TTL can alter the expiration time of the current version.
5. Late-arriving/backfilled data written with `USING TTL 3600` counts from write time, not automatically from `occurred_at` (event time).

### Viewing remaining TTL

```sql
SELECT occurred_at, event_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` returns remaining TTL when the cell is live and has a TTL; `WRITETIME(payload)` reflects the cell's write timestamp when available. Do not use them as tools to determine **the exact date a tombstone will be purged** or to count all markers in SSTables.

### Does TTL + TWCS allow lowering grace?

Append-mostly time-series data with uniform TTLs can be a candidate to **evaluate** `TimeWindowCompactionStrategy` (TWCS). When SSTables hold data with similar lifecycles, dropping whole expired SSTables can be more favorable than some standard compaction cases.

However, **TWCS does not eliminate the risk of replicas missing deletions**. Late writes, updates to old data, uneven TTLs, and SSTable overlap can complicate reclamation. Do not treat "TWCS is enabled" as sufficient justification for setting `gc_grace_seconds = 0`.

## 13. SSTable overlap: an example of why an old tombstone still persists

One partition can be present across multiple SSTables:

```text
SSTable-1:
  E1.payload = "A"    @100
  E2.payload = "B"    @100

SSTable-2:
  DELETE E1.payload   @200

SSTable-3:
  E1.source_app = "gateway" @150

Today:
  Tombstone @200 is already past grace.
```

If you only dropped the deletion marker in SSTable-2, SSTable-1 still has `E1.payload = A`. On read, value A risks reappearing **on the very same replica**, without even waiting for an offline node to return.

Therefore, safe compaction must account for the possibility that old versions in **uninvolved SSTables** still need to be shadowed. SSTable selection for compaction and overlap checks play a major role. Under appropriate conditions, compaction can merge shadowed data and the marker and then drop both once eligible.

### Why is checking SSTable count alone insufficient?

- A table with few SSTables yet containing a very large partition or many markers can still read slowly.
- A table with many SSTables does not mean every query reads all of them.
- Compare `SSTables per read`, tombstones per slice, partition size, and latency for actual queries.
- Compaction/repaired state of files can also impact reclamation eligibility depending on version.

**The goal is preserving deletion correctness during reclamation**, not erasing the maximum possible bytes in a single compaction.

## 14. Compaction strategies and tombstone retention duration

Compaction strategy affects how SSTables are chosen for merging and how quickly old data/tombstones get opportunities for reclamation.

| Strategy | Commonly considered workload pattern | Relationship to tombstones |
| --- | --- | --- |
| **STCS** (*SizeTieredCompactionStrategy*) | Some write-heavy workloads, varied data sizes | Multiple SSTables can hold versions of a partition before merging. |
| **LCS** (*LeveledCompactionStrategy*) | Some read-heavy workloads needing reduced overlap | Aims to bound overlap per level; has its own write amplification and compaction I/O. |
| **TWCS** (*TimeWindowCompactionStrategy*) | Append-mostly time-series, nearly uniform TTLs | Can favorably drop expired time windows, but sensitive to late writes and updates to old data. |

No strategy **replaces** grace/repair logic by itself. A tombstone past `gc_grace_seconds` that has not been compacted under eligible conditions can still sit on an SSTable. Conversely, forcing compaction too aggressively can spike I/O, consume disk headroom, hurt p99, and fail to deliver expected benefits.

### Beware of "running compaction to fix data errors"

`nodetool compact` (when supported in your version's syntax) requests compaction work; **it does not prove deletions have reached every replica**. If data is inconsistent across replicas, analyze repair and mutation sources; forcing compaction is not an anti-entropy substitute.

Especially when a node just recovered after a prolonged downtime, evaluate data safety before running maintenance operations that could alter tombstone retention.

## 15. How to observe `gc_grace_seconds` and tombstones in operations

There is no simple CQL statement returning "all tombstones in every SSTable with exact purge dates." Combine schema inspection, nodetool, metrics, and logs.

### Inspect table definition

In `cqlsh`:

```sql
DESCRIBE TABLE app_ks.device_events_by_day;
```

Confirm:

- Actual `gc_grace_seconds` of the table.
- Compaction strategy and related options.
- `default_time_to_live` if the table uses a default TTL.
- Partition key and clustering columns to see which queries might hit tombstones across a large partition.

### Inspect node/table status

```bash
nodetool status
nodetool tablestats app_ks.device_events_by_day
nodetool tablehistograms app_ks device_events_by_day
nodetool compactionstats
```

Useful fields, depending on version:

| Metric group | Used to answer |
| --- | --- |
| **Node status and downtime** | Is any replica offline, recently rejoined, or replaced? |
| **Repair completion/range coverage** | Were relevant ranges synced within the safety window? |
| **Tombstones per slice** | Are read queries encountering many deletion markers? |
| **SSTables per read, SSTable count** | Are many sources/versions being merged? |
| **Partition size/cell histogram** | Are there very large or dense partitions? |
| **Pending/active compactions** | Is there a backlog making tombstones hard to clean up? |
| **Disk headroom, CPU/I/O, p95/p99 latency** | Does the system have enough headroom to repair/compact? |
| **Timeouts/errors and warning logs** | Are queries hitting tombstone safety thresholds? |

`tablestats` and `tablehistograms` are generally **table/node-level** metrics, not exact tombstone counts for a specific live key. When comparing across nodes or days, record the **version, node, timestamp, and scope**.

### Tracing a suspect query

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type, payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing can reveal read cost and tombstones inspected when your version provides that data; it **does not replace SSTable inspection**. Tracing adds overhead, so sample sparingly and turn it off after collecting.

## 16. Why a slow SELECT is not necessarily due to grace being too long

A common scenario: an API fetching the 20 latest events is slow despite the query having `LIMIT 20`.

Suppose:

```text
Start of clustering range:
  expired expired deleted deleted deleted ...
  thousands of expired or deleted cells/rows
  ...
  live #1
  ...
  live #20
```

Cassandra must evaluate deletion markers while merging memtable/SSTables to find live rows. `LIMIT 20` constrains **returned rows**, not the number of tombstones scanned.

Tombstone accumulation can relate to a long grace period, or also stem from:

1. Excessive UPDATE/DELETE operations or unnecessary `NULL` writes.
2. TTLs that are too short relative to write rate.
3. Queries reading wide slices or starting in ranges with many expired rows.
4. Very large or hot partitions.
5. Many SSTables holding old data, or compaction backlog.
6. Overloaded replicas/disks/network, or a consistency level waiting on multiple sources.

Therefore, **lowering `gc_grace_seconds` is not the first step**. Diagnose tombstone generation sources, compaction health, partition key design, and query scope first. If repair safety conditions are not met, lowering grace can trade a latency problem for a much more severe data correctness bug.

## 17. When should changing `gc_grace_seconds` be considered?

Changing this value is a **risk-assessed operational decision**, not an automatic optimization trick. Any change should be documented with:

- Cassandra version/distribution and active tombstone garbage collection mechanics.
- Replication factor, number of data centers, and maximum duration a replica can be offline.
- Evidence of repair schedules, completion within grace, and expected failure margins.
- Compaction strategy, TTLs, updates/deletes, and SSTable overlap.
- Requirements that deleted data must never reappear.
- Scenarios for restoring old nodes/snapshots/backups.
- Read/write SLOs, disk capacity, and I/O budget for repair/compaction.
- Monitoring plan, rollback/halt criteria, and incident response if zombie data signs appear.

### Lowering grace

Before lowering, ask:

1. **Are all replicas/ranges repaired frequently and successfully enough?**
2. **Can any node stay offline longer than the new value?**
3. **Is there any chance of restoring old snapshots or old SSTables?**
4. **Are there DELETEs or TTLs in the workload?**
5. **Do version-specific protection mechanisms support safe reclamation?**

Lowering grace on a table with RF greater than 1 and potential long replica outages can increase zombie risk. Specialized deployments with technical reasons to use a short or 0 grace must be evaluated individually; **do not use 0 as a default setting to silence tombstone warnings**.

### Increasing grace

Increasing grace can be a prudent step if repair schedules or failure characteristics require a wider margin. However, it can also keep deleted data and markers around longer, increasing read/disk/compaction costs. You must still fix repair/downtime failures if they exceed even the new window.

### Changes cannot retroactively restore lost data

If tombstones were already purged earlier, **raising `gc_grace_seconds` afterward does not recreate vanished deletion markers**. This is critical during incident response or when evaluating configuration rollbacks.

## 18. Node offline past grace: do not simply turn it back on

A node holding old replica data that was offline longer than the safety window requires a **dedicated runbook**.

Before letting that node serve queries/streaming as a normal replica:

1. Determine the **exact last date/time the node truly synchronized data**, when it went offline, and what DELETE/TTL mutations it may have missed.
2. Check which `gc_grace_seconds` the relevant tables/keyspaces use; do not assume the entire cluster shares one value.
3. Determine which deletions other replicas may have repaired/compacted and purged during the node's absence.
4. Evaluate an approved **node replacement/rebuild/rebootstrap or sync procedure** appropriate for your version/topology; avoid bringing old data straight back if zombie risk exists.
5. Keep the node out of production traffic until operators verify data correctness and safety conditions.
6. Monitor replication health, repairs, read/write latency, and signs of deleted data reappearing after recovery.

No late `nodetool repair` command **automatically guarantees** safe recovery if active replicas have already lost the needed tombstones. Repair syncs existing state; once deletion information has been unsafely purged, specific data assessment and recovery planning are required.

**Do not automatically restart an old node just because `nodetool status` shows the cluster currently lacks full RF.** Data safety depends on mutation and deletion history.

## 19. Java Driver 4.x: DELETE, TTL, and timeouts do not confirm failure

A Java application should make three things explicit:

- Which cell is deleted using the **full primary key**.
- Which TTL is written per the retention policy.
- On timeout, the operation **may already have been applied on some replicas**; retries must not create a different primary key or unintentionally alter retention semantics.

Example using Java Driver 4.x with `app_ks.device_events_by_day`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DeviceEventRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement insertWithTtl;

    public DeviceEventRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM app_ks.device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND occurred_at = ? AND event_id = ?"
        );

        this.insertWithTtl = session.prepare(
            "INSERT INTO app_ks.device_events_by_day " +
            "(tenant_id, device_id, event_day, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public void removePayload(
            String verifiedTenantId,
            UUID deviceId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId) {

        session.execute(deletePayload.bind(
            verifiedTenantId, deviceId, eventDay, occurredAt, eventId
        ));
    }

    public void writeTemporaryEvent(
            String verifiedTenantId,
            UUID deviceId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload,
            int ttlSeconds) {

        if (ttlSeconds < 1) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        // eventDay must be computed consistently by the caller from UTC event time.
        session.execute(insertWithTtl.bind(
            verifiedTenantId, deviceId, eventDay, occurredAt,
            eventId, eventType, payload, ttlSeconds
        ));
    }
}
```

### Operational meaning of the code

1. `removePayload` deletes **one cell**, not a row or an entire partition; other scopes require separate prepared CQL statements.
2. `eventDay` must align consistently with business UTC event time/bucket; do not recompute it from retry time.
3. `eventId` and `occurredAt` must stay constant across retries so they do not create a different full primary key.
4. Retrying an `INSERT` carrying TTL can **shift the expiration time** compared to the initial write if mutation semantics change; control this when retention is strict.
5. A timeout on DELETE/INSERT does not prove the mutation was not written; handle retry/backoff, CL observability, and idempotency.
6. `verifiedTenantId` must come from an authenticated/authorized context, never blindly trusting a client-passed ID.
7. The Java Driver **does not execute repair, compaction, or tombstone garbage collection** on DELETE; that is server/operational responsibility.

**Note:** the illustrative example does not force a specific consistency level. In real systems, CL must be chosen intentionally based on topology, latency, and read/write requirements; however, never treat CL as a substitute for repair schedules when configuring grace.

## 20. Safe lab: observing DELETE and TTL without lowering grace

A good hands-on exercise **does not require setting `gc_grace_seconds` to 0** and does not require waiting 10 days during a study session.

### Step 1 — Prepare the lab table

Create `app_ks.device_events_by_day` as in section 6 and confirm `gc_grace_seconds` with `DESCRIBE TABLE`. Use a keyspace, replicas, and data that are **non-production**.

### Step 2 — Write and read two rows

Run the `INSERT`s from section 6 and read back:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Goal: verify the full partition key and clustering order.

### Step 3 — Delete one cell

Run `DELETE payload` from section 6. Read back: the corresponding row can still appear thanks to `event_type`, while `payload` no longer has a live value.

Goal: observe **logical deletion** without needing to watch immediate disk space fluctuations.

### Step 4 — Write a short TTL

Write an event with a 60-second TTL on a **new full primary key**, check `TTL(payload)` while the cell is live, and read again after TTL expiration.

Goal: see TTL expire the cell **without sending a new DELETE statement**. Do not conclude that the event's timestamp is when TTL starts counting.

### Step 5 — Check stats/tracing

Use `tablestats`, `tablehistograms`, or tracing for a few lab queries. With tiny data, metrics may not change noticeably; that is not a lab error.

To measure read amplification, you need a workload with enough rows, TTLs/deletes, and representative SSTable distribution, tested in an isolated environment with I/O limits and never run against production.

### Step 6 — Answer questions about purge conditions

Before checking or requesting compaction, learners should answer:

- Is the tombstone old enough per grace?
- Is there old data on other SSTables/replicas?
- Could a replica have missed the deletion and not yet been repaired?
- Which compaction type is running and does it have enough resources?
- Would dropping the tombstone right now allow old data to reappear?

Do not run compaction or change grace just to "finish the lab"; understanding **safety conditions** is the primary learning objective.

## 21. Case study: short grace, lagging repair, and resurrected data

An event-history system has RF = 3. Operations notices many tombstones and slow reads. They change `gc_grace_seconds` from **10 days** down to **2 days**, yet still only repair **every 7 days**. One replica loses connectivity for **4 days** during maintenance.

### Possible sequence of events

```text
Day 0: Replica C goes offline; A/B still record DELETEs for several keys.
Day 2: Tombstones on A/B become old enough under the new grace.
Day 3: Compaction may purge some tombstones if local conditions
       and version mechanics allow.
Day 4: C returns, still carrying old values that missed DELETEs.
Day 7: Scheduled repair finally runs.
```

There is a risk that some of C's old values become visible or propagate again if needed deletion markers on A/B were unsafely purged. **Do not claim zombie data definitely happens:** it also depends on which data was purged, which replicas received deletions, SSTable overlap, read/repair timing, and version mechanics.

### Why was the initial action misguided?

- Repair every 7 days is **not within the safety margin** of a 2-day grace if a replica can miss deletes.
- A replica offline for 4 days exceeds the 2-day grace.
- High tombstone counts may stem from short TTLs, per-cell deletions, or collection updates, not a "wrong" grace value.
- Lowering grace does not guarantee fixing p99; tombstones may still remain due to compaction/overlap.

### Remediation and prevention plan

1. Assess data correctness and follow the **post-grace returning-node procedure**; do not automatically rejoin stale data into production.
2. Restore a grace/repair policy with a safety margin matched to the failure model.
3. Identify the cause of tombstone-heavy reads and improve schema/time buckets/TTL/compaction/queries.
4. Verify repair coverage, failures, node outage duration, and alert immediately when risk exceeds thresholds.
5. Monitor p95/p99 latency, tombstones per slice, compaction backlog, and data consistency.
6. Maintain a runbook for node replacement/rebuild/restoring old data by version to prevent zombies.

**Lesson:** a grace value only makes sense when placed within the **entire replication, repair, and incident operations process**.

## 22. Common misconceptions

| Claim | Issue | Correct understanding |
| --- | --- | --- |
| "10-day grace means DELETE waits 10 days to take effect." | Logical deletion and physical reclamation are distinct. | Tombstones shadow data once deletion wins by timestamp/CL. |
| "On exact day 10, Cassandra auto-deletes all tombstones." | Grace only governs age eligibility. | Also depends on compaction, overlap, repair, and version config. |
| "`gc_grace_seconds` is the same as TTL." | TTL applies to live values; grace applies to marker garbage collection. | Two different lifecycles. |
| "Increasing RF prevents zombie data automatically." | A replica can still miss mutations during downtime. | Repair and safe retention are still required. |
| "`LOCAL_QUORUM` guarantees every replica received DELETE." | Quorum is not all replicas. | Manage replicas and repair separately. |
| "Hints are enough; repair is unnecessary." | Hints have limits and can be lost/missed. | Ensure anti-entropy within the grace window. |
| "After grace, just delete SSTables holding tombstones." | Other SSTables may hold old data. | Overlap and purge conditions must be checked. |
| "`nodetool compact` fixes stale replicas." | Compaction is not cross-replica repair. | Distinguish compaction from anti-entropy. |
| "TWCS allows grace = 0 on all TTL tables." | Write patterns, late writes, replica failures, and versions still pose risks. | Change only after thorough evaluation. |
| "Lowering grace always clears tombstone warnings." | Markers may remain uncompacted and queries still scan lots of data. | Fix tombstone sources and the read path. |
| "COUNT(*) gives the number of deletion markers in a partition." | COUNT returns visible logical rows. | Use metrics/tracing/appropriate SSTable tools. |
| "Raising grace after an incident recreates purged tombstones." | Reclaimed data does not reappear on its own. | Assess data recovery and synchronization instead. |
| "A node offline 20 days can restart with grace 2 days unchecked." | The node may hold old deleted versions. | Follow a safe rejoin/replacement runbook. |

## 23. Case study exercise and answers

A Cassandra cluster has three replicas in one data center. Table `events_by_account_day` has `gc_grace_seconds = 432000`, or **5 days**. The application stores events with a 30-day TTL and occasionally deletes events per user request. Periodic repair runs **every 4 days**, though in the past month several jobs failed. Replica C was offline for **7 days**.

**Questions:**

1. How many days is `gc_grace_seconds`? What does it mean for tombstones?
2. Must a DELETE acknowledged today wait 5 days before SELECT stops seeing the old value?
3. Do a 30-day TTL and 5-day grace equal a fixed 35-day data retention limit?
4. If C is offline for 7 days, exceeding the grace period, what risk arises?
5. Does a 4-day repair schedule with some failed runs guarantee safety?
6. If a tombstone is old enough yet another uncompacted SSTable still holds old data, can the marker be dropped arbitrarily?
7. If `nodetool tablestats` reports high tombstones per slice, does that prove the 5-day grace is the sole cause?
8. Why is `LOCAL_QUORUM` insufficient to guarantee C has the DELETE?
9. Does `nodetool compact` replace repair for synchronizing C?
10. If C has old data and A/B already purged the deletion, what can happen when C returns?
11. Is setting grace = 0 a safe solution for every TTL time-series table?
12. If an event occurred last week yet is INSERTed today with a 30-day TTL, does expiration count by default from event time or write time?
13. Does a newly daily-bucketed table automatically eliminate all tombstones?
14. What operational metrics and information should be reviewed before changing grace?
15. Propose a prioritized three-step plan to restore safety and reduce query latency.

**Answers:**

1. `432000 / 86400 = 5` days. This is the protection window related to **considering** tombstone purge, not a guaranteed milestone when data vanishes.
2. **No.** Logical deletion can take effect immediately per write timestamp, replicas, and consistency level; grace governs physical reclamation.
3. **No.** TTL counts under write-value semantics; grace is a condition for cleaning deletion markers. Compaction/overlap can extend physical footprint further.
4. There is **zombie data risk** if C missed DELETEs and tombstones on other replicas were unsafely purged.
5. **Not yet.** You must verify which ranges were successfully repaired within the protection window, accounting for failures and downtime.
6. **No.** Shadowing information must be retained until a safe overlap-aware purge mechanism runs.
7. **No.** Heavy DELETEs, short TTLs, collection replacements, wide range queries, and compaction backlogs can also drive cost.
8. Quorum only requires a subset of replicas; C may not have been in the acknowledging subset.
9. **No.** Compaction within one node does not sync state across replicas.
10. Old data can become visible/propagate again because the necessary tombstone was lost: **zombie**.
11. **No.** You must evaluate version, topology, repair, updates/deletes, TTL, and specialized reclamation mechanics.
12. **From write time**, unless the application proactively calculates remaining TTL from the business deadline.
13. **No.** Bucketing changes partition shape and query scope; it does not erase inherent tombstones or replace repair.
14. Review RF, DCs, node outages, repair coverage, compaction strategy/backlog, SSTable overlap, TTL/update/delete rates, p95/p99, read timeouts, zombie warnings, and version.
15. Priority: **(i)** safely handle the node offline past grace, verifying data/repairs; **(ii)** lock in grace/repair with a margin suited to the failure model; **(iii)** measure and reduce tombstone-heavy reads via load-tested queries/bucketing/TTL/compaction.

### Quantitative problem

A system has `gc_grace_seconds = 604800` and a replica offline for **11 days**. Calculate:

```text
Grace:     604800 / 86400 = 7 days
Downtime:                       11 days
Difference: 11 - 7 = 4 days past grace
```

**Correct conclusion:** the replica exceeded the protection window by 4 days; check the risk of missed deletions and safe recovery procedures. **Wrong conclusion:** "Data will definitely resurrect after 11 days." Zombie data is a **conditional risk**, not a deterministic outcome of subtracting durations.

## 24. Operational checklist before changing grace

- [ ] Verify the **exact `gc_grace_seconds` table option** and Cassandra version.
- [ ] Fully understand the **replication strategy, RF, data centers**, and read/write consistency behavior.
- [ ] Have **completed repair** metrics, not just a schedule on paper; track failures and range coverage.
- [ ] Record the **longest replica offline duration** and the policy for nodes exceeding grace.
- [ ] Check **the possibility of restoring/rejoining from old snapshots or SSTables**.
- [ ] Distinguish deletions from **DELETE, NULL, collection updates, and TTL expiry**.
- [ ] Review compaction strategy, SSTable overlap, repaired state, and version-specific tombstone garbage collection options.
- [ ] Measure tombstones per slice, SSTables per read, partition size, p95/p99, and timeouts.
- [ ] Do not use `COUNT(*)` or live row counts as a physical tombstone count.
- [ ] Have a plan to reduce read amplification at **schema/query/TTL/mutation** levels before lowering grace.
- [ ] Test changes in a production-like environment; have backups and an appropriate rollback procedure.
- [ ] Understand that **raising grace after purging does not recreate deletion metadata**.
- [ ] Do not force massive compactions/repairs without CPU, I/O, network, and disk headroom budgets.
- [ ] Do not bring a replica offline past grace back into production without evaluating zombie risk.
- [ ] Deploy only after validating **data correctness and SLOs**, with an owner, monitoring schedule, and stop thresholds.

## 25. Key takeaways

- `gc_grace_seconds` is a **protection window related to evaluating tombstone garbage collection**, not a TTL and not a guaranteed physical deletion schedule.
- **Logical deletion** takes effect when deletion wins by write timestamp/consistency; **physical reclamation** is a separate process via compaction and safety conditions.
- A replica missing a DELETE can hold an **old data version**; if tombstones are reclaimed too early, that data risks returning as **zombie data**.
- **Complete and timely repair** aligned with grace is critical; hints and consistency levels are not full substitutes.
- Tombstones past grace may still need to be kept due to **SSTable overlap**, compaction backlog, repaired state, or version mechanics.
- TTL expiration creates a deleted state that must be safely cleaned; **TTL expiration does not mean immediate space reclamation**.
- **STCS, LCS, and TWCS** alter how SSTables are merged, without waiving deletion safety requirements.
- Lowering grace to silence tombstone warnings is dangerous without repair/topology evidence and understanding tombstone generation sources.
- Before changing settings, inspect **node health, repair coverage, tombstones per slice, SSTables per read, p99, compaction backlog**, and old-data recovery risks.
- Proper partition key/bucket design, intentional DELETE/NULL/TTL operations, and stable Java retry logic **reduce tombstones read**, working alongside a safe grace policy.

Understanding `gc_grace_seconds` and tombstone retention conditions enables responsible Cassandra operations: reducing read and compaction overhead without trading away the correctness of delete operations in a distributed system. This is the foundation for coordinating replication, consistency, repair, recovery, and Java applications while old data still exists across multiple replicas and SSTables.
