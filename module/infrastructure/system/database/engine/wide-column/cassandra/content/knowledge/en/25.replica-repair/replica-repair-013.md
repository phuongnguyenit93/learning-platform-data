# Before/After Data Reconciliation and Limits Unrecoverable by Repair in Apache Cassandra

> **Chapter:** Repair  
> **Scope:** Distributed Apache Cassandra with multiple replicas; establishing before/after evidence around `nodetool repair`, interpreting replica discrepancies, distinguishing technical convergence from business correctness, and recognizing scenarios requiring backups/restores or independent data sources. Examples use Cassandra 4.x/5.0; verify option syntax against your running release.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what **anti-entropy repair** synchronizes between replicas and what it cannot do.
2. Capture a **pre-repair baseline** across sample keys/partitions, token ranges, tables, and datacenters rather than just running a command and assuming everything is fixed.
3. Use CQL, tracing, `nodetool`, logs, and operational telemetry for **before-and-after reconciliation** without confusing "QUORUM reads look right" with "every replica is right."
4. Distinguish **converged data** from **source-of-truth correct data**; understand why repair cannot recover rows lost across every replica.
5. Analyze limitations involving **purged tombstones, zombie data, clock skew, wrong timestamps, corrupted data, schemas, and denormalized tables**.
6. Design a safe repair runbook complete with success and rollback criteria for Java applications.

Key thread throughout: Cassandra is a **distributed wide-column** database. Partition keys determine tokens and replica sets; reads/writes use consistency levels (CL); immutable SSTables hold multiple versions; compaction purges eligible data. **Repair is a tool to bring replicas of the same data into convergence**, not an engine for determining business truth.

## 2. What Does Repair Actually Do?

With RF=3 in a single datacenter, partition `tenant-a` has three replicas: A, B, and C. If C loses connectivity during an UPDATE, it can retain an older version:

~~~text
                   RF=3, partition tenant-a

                        Coordinator
                             |
                    UPDATE state='PAID'
                    write timestamp = 200
                       /      |      \
                      v       v       x
                  Replica A Replica B Replica C
                  PAID 200  PAID 200   NEW 100
                      \       |       /
                       \   anti-entropy repair
                        \     |     /
                         reconcile
                              |
                  PAID 200 on A, B, and C
~~~

**Anti-entropy repair** compares data among replicas responsible for corresponding token ranges, detects diffs, and streams/fixes data when needed. Cassandra uses structures like **Merkle trees** to compare by range, minimizing full data transfers when most segments already match. The system still relies on **Cassandra's reconciliation rules** (write timestamps, tombstones, TTLs, data structures) to determine the final state.

`nodetool repair` must NOT be treated as:

- A command to recover a lost record **absent from every replica**.
- A tool to retrieve DELETE/UPDATE history already garbage collected.
- A mechanism validating whether data obeys **business rules**.
- A backup copy or PITR (point-in-time recovery).
- A tool automatically fixing hardware faults, unreadable partitions, or corrupted SSTable files lacking any healthy copy.
- A tool to migrate schemas, rebuild secondary indexes, or patch separate tables maintained by application fan-out.

### 2.1. Convergence Does Not Equal Accuracy

| Pre-Repair State | What Can Repair Do? | Is It Business-Correct Yet? |
|---|---|---|
| A/B hold `PAID, ts=200`; C holds `NEW, ts=100` | Sync C to PAID | **Possibly**, if PAID is the intended state |
| A/B/C all hold `PAID`, yet the order was refunded | Detects no replica difference | **No**; the refund event is missing on all three |
| A has the right row, B/C are missing it | Can stream valid data from A to B/C | Must confirm A's row is the right version |
| A/B/C all miss a row due to write failure or data loss | Cannot recreate a row out of thin air | Must consult backups/CDC/audit/independent source |
| A/B/C all hold a value written with an absurd client timestamp | Sees them as already matching | Still wrong; repair does not fix timestamp logic |
| A/B purged tombstones while C holds the old record | May treat old record as live and spread it | Risk of **zombie data** |

**Verification must always be two-layered:** (1) did replicas converge? (2) do outcomes match an **independent source of truth** or verified business invariant?

## 3. Understanding Scope: Partition, Token Range, Replica, and Datacenter

To reconcile accurately, first know **who is being compared against whom**.

~~~text
Keyspace orders
  Replication: NetworkTopologyStrategy
  dc1: RF=3
  dc2: RF=2

A partition key
    |
  partitioner -> token
    |
    +-- dc1: three natural replicas
    +-- dc2: two natural replicas

Repair/reconciliation must specify DC, table, and token range
rather than assuming from a single coordinating node.
~~~

### 3.1. Scopes to Record in the Baseline

| Scope | What Must Be Identified | Common Mistake |
|---|---|---|
| Keyspace | Replication strategy, RF per DC | Assuming one global RF number applies to every DC |
| Table | Schema, `gc_grace_seconds`, TTL, compaction | Repairing one table and declaring all tables fixed |
| Partition key | Key value used to compute token | Reading wrong partition or querying without key |
| Natural replicas | Nodes actually storing the token range | Confusing coordinator with replica-storing nodes |
| Token range | Which ranges repaired, which failed | Running `-pr` on one node and assuming full cluster |
| Datacenter | Which DCs participate in repair | `LOCAL_QUORUM` in `dc1` does not prove `dc2` data |
| Timing | Mutation time, downtime duration, grace | Repairing too late after tombstones are lost |

Useful survey commands:

~~~bash
nodetool status
nodetool describecluster
nodetool version
nodetool getendpoints repair_lab orders tenant-a
~~~

`getendpoints` finds the **natural endpoints of a partition key** per the ring; **it does not prove data on those endpoints matches**. For composite partition keys, verify CLI syntax and key formatting for your exact version.

### 3.2. Consistency Levels Can Mask Differences

Suppose:

~~~text
Replica A: status=PAID, ts=200
Replica B: status=PAID, ts=200
Replica C: status=NEW,  ts=100
~~~

A `SELECT ...` at `QUORUM` can return `PAID`, since RF=3 needs two responses and the newer timestamp wins reconciliation. That **does not prove C is synced**. Conversely, `ONE` might return `NEW` if the read hits C.

Even if you point `cqlsh` at C and set `CONSISTENCY ONE`, Cassandra **does not guarantee** the answer came strictly from C's local disk under every cluster state or query plan. Coordinators may pick another natural replica per read strategies. When needing exact confirmation of a single replica's data, combine **tracing, replica-inspection tools, repair metrics**, or version-specific audit workflows—never pass off a normal SELECT as "reading SSTables directly on node C."

## 4. Preparing a Pre-Repair Baseline

A "succeeded" repair without a baseline is hard to audit. Collect at least three groups of evidence:

1. **Expected record state:** presence/absence, column values, business version, and timestamps/deletes from an event store or audit ledger.
2. **Pre-repair Cassandra state:** read outcomes across a fixed set of primary keys, CL, DC, coordinator node, timestamps, `WRITETIME`/TTL where relevant, logs/tracing, and repair history.
3. **Cluster health and scope:** nodes/racks/DCs, token ranges, keyspaces/tables, prior repair outcomes, tombstone age, compaction, streaming, and disk space.

### 4.1. Building an Intentional Key Inventory

Pick a test set:

- **Keys reported with errors:** e.g., an order that should be PAID yet a client observed NEW.
- **Partitions spread across token ranges:** avoid sampling only hot keys from one tenant.
- **DELETED rows:** verify they **stay absent**, not only live rows.
- **TTL rows:** log expiration timestamps and expected results at check time.
- **Recently INSERTed/UPDATEd rows and cold rows:** catches drift rarely touched by read repair.
- **When applications maintain multiple denormalized tables:** list each table as its own reconciliation target.

Example evidence table **independent of the data being repaired**, kept in an ops ticket or trusted audit system:

| Primary Key | Expected Source | Pre-Repair (Observed) | Post-Repair (Required) |
|---|---|---|---|
| (`tenant-a`, `order-001`) | PAID, business_version=7 | Occasionally NEW | PAID, version 7 |
| (`tenant-a`, `order-002`) | Absent after DELETE | Some reads still return it | Row absent |
| (`tenant-b`, `order-003`) | Total=150 | Total=120 on one read path | Total=150 |
| (`tenant-c`, `order-004`) | TTL expired | Still present on an unsynced replica | No live value |

**The expected source must be genuinely independent** or credibly justified: taking a pre-repair `SELECT QUORUM` and calling it "ground truth" can legitimize a bad value that happened to carry a higher timestamp.

### 4.2. Capturing Schema and Topology Evidence

In `cqlsh`:

~~~sql
DESCRIBE KEYSPACE repair_lab;
DESCRIBE TABLE repair_lab.orders;
~~~

In shell:

~~~bash
nodetool status
nodetool tablestats repair_lab.orders
nodetool compactionstats
~~~

Record capture time, Cassandra version, CL of every query, local DC, and event IDs. `tablestats` provides table stats like SSTable counts and read/tombstone metrics—**not a cell-by-cell list of diffs across replicas**. Avoid misinterpreting aggregate counters.

### 4.3. Do Not Use `COUNT(*)` as Sole Proof

`SELECT COUNT(*) FROM ...` on large datasets can scan broadly, impose heavy load, and still fail to prove two datasets match: identical counts can still **differ in keys, values, or tombstones**.

Better reconciliation practices:

- Compare **the same primary keys** and critical columns, business versions, and write timestamps where applicable.
- Scope queries by partition key; paginate when partitions are large.
- Use application-layer checksums/hashes **only when** data is canonicalized and scope is explicit; matching checksums are a secondary signal, not a replacement for source-of-truth audits.
- State clearly whether reconciliation was **exhaustive**, **sampled**, or **targeted to suspect keys**. Never say "100% of data verified" after checking 20 keys.

## 5. Observing Before-and-After State Without Distorting Results

Some read paths can trigger **read repair**, mutating replicas while you inspect them. Thus define whether your probe is **passive observation** or **testing convergence behavior**.

### 5.1. What Can CQL Show?

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_write_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

CONSISTENCY QUORUM;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_write_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`WRITETIME(status)` returns the **microsecond** timestamp of the **live cell**, not DELETE history or all versions across SSTables. If data is shadowed by a tombstone, a SELECT does not directly expose the tombstone record on each replica.

### 5.2. Tracing Is Useful Within Limits

~~~sql
TRACING ON;

SELECT order_id, status
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Tracing can reveal participating endpoints, digest mismatches, or read repair activity depending on version and query. **Never enable tracing broadly in production** due to overhead; also, a single trace cannot prove an entire token range has converged.

### 5.3. Distinguishing Inspection Methods

| Method | What It Detects | What It Cannot Conclude |
|---|---|---|
| SELECT across CLs/endpoints | Drift symptoms experienced by clients | Cannot guarantee which exact replica served |
| Controlled tracing | Replicas contacted and mismatch signals for that query | Does not cover every row or point in time |
| Repair logs, preview/digest/Merkle trees | Comparison scope and token-range diffs | Does not prove business correctness |
| Audit-source comparison by primary key | Exact discrepancy vs. application expectations | Valid only for audited scope/keys checked |
| Local SSTable inspection per offline runbook | Physical metadata/data on a specific node | Does not evaluate whole cluster at once; carries operational risk |

If you must confirm "what value C currently holds **before** repair touches it," gather evidence prior to any read that could repair mismatches or any repair job; for sensitive data, use **snapshots/offline inspection** in an isolated environment rather than experimenting with topology changes in production.

## 6. Full Repair, Incremental Repair, and Preview Repair

Cassandra offers multiple repair modes. Detailed behavior evolved across 3.x, 4.x, and 5.0, so consult `nodetool help repair` and exact version docs before automating.

| Mode | Goal | Caution |
|---|---|---|
| **Full repair** (`--full`) | Reconciles data in selected scope, not just unrepaired portions | Costs I/O, CPU, network; must specify token ranges and DCs |
| **Incremental repair** | Focuses on data not yet marked repaired; manages repaired/pending repair metadata and anti-compaction per version | Not equivalent to full historical audit; flawed schedules can miss scopes |
| **Preview repair** (`--preview` if supported) | Compares/estimates diffs without streaming data repairs | Diagnostic signal only; does not replace key audits or actual repair |
| **Primary-range repair** (`-pr`/`--partitioner-range`) | Restricts to primary ranges owned by the node | Running on **one** node does not cover the ring |

Example on a test cluster:

~~~bash
# Check options before running per runbook.
nodetool help repair

# Preview before fixing if supported by binary:
nodetool repair --preview repair_lab orders

# Full repair for the target node's primary ranges:
nodetool repair --full -pr repair_lab orders
~~~

Never blindly run those three commands back-to-back in production. Across multiple DCs/nodes, use a **repair orchestrator** or explicit plan covering DCs, racks, concurrency, bandwidth, and disk headroom. If choosing `-pr`, complete the plan across **all eligible nodes** to cover all primary ranges; never measure coverage by counting "repair completed" log lines without knowing which ranges actually finished.

### 6.1. One Finished Repair Job Is Not Enough

Necessary conditions to declare repair useful:

1. Exact scheduled keyspaces, tables, datacenters, and token ranges.
2. Every required session/child task **succeeded**, not merely the coordinator printing start/finish lines.
3. No unreachable nodes, streaming errors, abnormal compaction/pending repair, or ignored disk-full faults.
4. Post-repair reconciliation evidence inside the target scope.
5. Repair finished **before tombstones could be purged** when preventing zombie data.

**A repair session does not judge business right vs. wrong**: it synchronizes strictly based on existing data and timestamps.

## 7. Metrics and Evidence to Retain After Every Repair

| Metric / Log | Pre-Repair | Post-Repair | Interpretation |
|---|---|---|---|
| `UN` / unavailable nodes | Record initial topology | Confirm active participation | `UN` alone does not prove data synced |
| Target ranges | List of token ranges/tables/DCs | List of completed ranges | Prevents "missing a slice of the ring" |
| Repair job status | Prior errors, active sessions | Succeeded/failed, retries | Top-level exit insufficient if child sessions failed |
| Merkle trees/diffs | Expected mismatch | Mismatches reduced/cleared in scope | Identical digests do not prove business accuracy |
| Streaming bytes/errors | Baseline I/O | Bytes transferred and errors | Zero bytes can mean no diffs **or** scope wasn't processed |
| Repaired/pending repair metadata | Version-specific check | Verify no abnormal leftover state | Repair state can impact compaction |
| Live row checks | Value/`WRITETIME`/version | Same keys, CL, and audit source | Watch for concurrent writes between measurements |
| Deleted row checks | Absent? Zombie risk? | Still absent post-repair and post-compaction | Purged tombstones may mean repair ran too late |
| Read latency and tombstones | p95/p99, timeouts | No regressions | Repair load can impact live applications |

Retain a **repair wave ID**, start/end timestamps, scope, Cassandra version, config, per-range outcomes, ops log paths, streaming stats, and sample-key diff reports. These are essential inputs for later investigations.

## 8. Limits That Cannot Be Recovered by Repair

### 8.1. Every Replica Lost the Same Record

Suppose order `order-100` was reported saved by the API, yet due to write-path bugs, accidental deletion, or later ops actions, all natural replicas no longer hold the row:

~~~text
Business/audit source:
    order-100 exists, state=PAID, version=9

Cassandra at repair time:
    A: row missing
    B: row missing
    C: row missing
                   |
             Anti-entropy repair
                   |
       A/B/C still missing the row
~~~

Merkle trees or comparisons will show replicas **match completely**, because no replica holds a valid copy to stream. There is no "hidden history" repair can mine for a record gone everywhere.

**Action:** check backups, snapshots, CDC, event streams, write audits, or systems of record; identify exact keys and versions needing recovery; write/restore under control and run repair if needed to sync replicas.

### 8.2. All Replicas Hold the Same Wrong Value

~~~text
Application expects: status REFUNDED, version=8

Replica A: PAID, ts=9000
Replica B: PAID, ts=9000
Replica C: PAID, ts=9000

Repair: detects no difference to fix.
~~~

Even if one replica held REFUNDED at a lower timestamp, **last-write-wins** reconciliation favors PAID for its higher timestamp. Repair can make a wrong state **more consistent**, rather than "picking the right business intent."

Typical causes: oversized client-supplied timestamps, clock skew, out-of-order event processing, historical replays with bad timestamps, or application bugs.

**Action:** trace the timestamp source, confirm valid events from business audit/versions, and fix the buggy writer before repairing data. Never solve this by writing ever-larger future timestamps: that keeps shadowing future legitimate mutations.

### 8.3. Tombstones Garbage Collected, Creating Zombie Data

Replica C missed a DELETE while A and B held tombstones. If C stays disconnected past `gc_grace_seconds` and A/B **purge tombstones** via eligible compaction, C can reintroduce the old data:

~~~text
T0: A/B/C hold order-200, ts=100
T1: DELETE order-200, ts=200, CL=QUORUM
    A/B hold tombstone, C down holding order-200
T2: Grace expires + eligible compaction on A/B
    A/B lose deletion evidence
T3: C returns carrying order-200 ts=100
T4: Repair/streaming may spread order-200 to A/B
    => DELETED DATA REAPPEARS (zombie)
~~~

At T4, repair no longer has the `ts=200` tombstone to tell C is wrong. Replicas **matching again** is itself a correctness failure.

**Operational lesson:** full-coverage repair schedules must finish **before** grace expires, with margin for retries. Long-down nodes must be evaluated before rejoining/streaming/repairing; node replacement and rebuilding from healthy replicas may be required depending on topology. If zombies already spread, use delete logs or independent truth sources to identify and re-apply valid deletions.

### 8.4. No Readable Replica Remains or Copies Are Corrupted

Repair relies on at least one replica having valid data to exchange. If SSTable corruption, disk failures, or missing files render **all relevant copies unreadable** for that data, repair cannot regenerate contents. If some replicas retain clean copies, recoverability depends on corruption extent, topology, and supported ops workflows.

**Action:** preserve evidence first, verify checksums/disks and backups; use node replacement, backup/SSTable restore, or version-appropriate salvage tools. Never manually delete suspect SSTables to force repair through without confirming clean copies exist.

### 8.5. Missing Schema, Mapping Bugs, or Data in Another Table

If an application writes two tables serving two queries:

~~~text
orders_by_id       PK((tenant_id), order_id)
orders_by_customer PK((customer_id), order_id)
~~~

and code INSERTs into `orders_by_id` while skipping `orders_by_customer`, repairing `orders_by_customer` **has no way to know** rows should be populated from the other table. Each table has its own replica sets, primary keys, and mutations.

Likewise, repair does not:

- Run schema migrations to add missing columns, indexes, or tables.
- Fix Java client encoding/serialization bugs.
- Restore a `DROP`ped column from old source code.
- Rebuild SAI/secondary indexes when the issue is a **local index** (use version-appropriate index rebuild commands).
- Force query output to obey business constraints.

**Action:** distinguish **replica inconsistency**, **schema inconsistency**, **derived-table inconsistency**, and **logical data corruption**; each demands a different workflow.

### 8.6. Snapshots/Backups Have Their Own Limits

Repair cannot replace **point-in-time restore**. If every replica accepted an accidental DELETE, the cluster accurately reflects that DELETE mutation; repair will not "guess" the user wanted to undo it.

Restoring from an old snapshot also requires verifying:

- Whether the snapshot was taken **before or after** desired mutations.
- Whether valid post-snapshot mutations exist that must be replayed from CDC/commit logs/audits.
- Whether the snapshot holds rows deleted **after** the snapshot timestamp—an uncontrolled restore can **create fresh zombies**.
- Compatibility of schema, SSTable format, binary version, encryption, replication, and token ownership.
- Target RPO/RTO and selective key-recovery feasibility.

For selective recovery, prefer normalizing data from a verified source and writing back through CQL/applications with controlled timestamps rather than copying raw SSTable files across live replicas.

## 9. How Repair Differs from Other Sync and Data-Recovery Mechanisms

| Tool / Mechanism | What Does It Actually Do? | Can It Replace Repair? |
|---|---|---|
| **Hinted handoff** | Replays temporarily missed mutations within hint retention | No: hints expire and do not cover all drift |
| **Read repair** | Fixes mismatches on actually queried data per version/config | No: does not scan all token ranges |
| **Anti-entropy repair** | Compares replicas across ranges, streams diffs | Primary replica-sync tool; does not infer business truth |
| **Compaction** | Merges SSTables, purges eligible tombstones/data | No: local compaction never checks a down replica |
| **Snapshot/backup restore** | Brings back data from an earlier point in time | No: can reintroduce deleted data; needs reconciliation |
| **Node rebuild/bootstrap/replace** | Reconstructs a node's data from cluster per topology | Can remediate a dangerous stale node; does not fix buggy source logic |
| **Rebuild index** | Rebuilds local secondary index from table data | No: does not stream missing base data between replicas |
| **CDC / event replay** | Replays independent mutation stream if complete | Can restore logical data, given idempotency, timestamps, and order |
| **App rewrites wrong keys** | Fixes from trusted source of truth | Can resolve business incidents; still verify replica convergence |

### 9.1. Why Compaction and Repair Must Coordinate

Compaction can purge tombstones once grace and **local** safety checks pass. If a remote replica never received the DELETE, local compaction on a healthy node has no way to know about stale data on the down node. Hence repair must propagate tombstones in time.

Conversely, repair triggers SSTable streaming and repaired/pending-repair metadata affecting compaction. Monitor I/O, free disk, and repair/compaction backlogs together, especially on tables with TTLs or continuous updates.

### 9.2. Limits of Merkle Trees and "Clean Preview"

Merkle trees are hash structures efficiently comparing **current contents** across replicas by range. A preview showing zero mismatches only suggests examined replicas/ranges align algorithmically—it **does not** prove:

1. An accidentally deleted row was recovered.
2. Every partition across the entire keyspace participated in that preview.
3. Stored values match billing or transaction systems.
4. No concurrent write is altering state.
5. All secondary indexes, denormalized tables, and backups agree.

Therefore combine **repair status + audited sample checks + ongoing monitoring**, rather than treating a single metric as completion.

## 10. When a Record "Reappearing" Is Not Caused by Repair

Not every unexpected value post-repair is a tombstone-GC zombie.

| Symptom | Possible Explanation | How to Verify |
|---|---|---|
| Old value reappears after UPDATE | Old copy carried a **higher** write timestamp due to clock skew | `WRITETIME`, client timestamp generator, audit |
| DELETEd row shows a new state | An INSERT/UPDATE was **genuinely newer** than the tombstone | Request logs, timestamps, event sequence |
| Row disappears after TTL | Initial write's TTL expired | `TTL(col)` prior to expiry and audit |
| Two SELECT ONEs return different values | Coordinator chose different replicas before convergence | Tracing and range repair |
| Quorum passed before repair and still passes after | C may have been stale beforehand, masked by quorum | Consult logs/repair coverage; never infer C was fixed from SELECT alone |
| Count changes | Concurrent writes/deletes or changed query scope | Fix snapshot boundaries, scope, and versions |
| One table lacks rows another has | App missed dual-write or consumer lagged | CDC/outbox status, two-table audit |
| Old row reappears after very long node restart | Tombstones purged during outage | Downtime timeline, `gc_grace_seconds`, repair history |

**Analyze timestamps carefully:** `WRITETIME` shows a live cell's timestamp, not all tombstones; a row could be deleted by a row/partition/range tombstone with another timestamp. Use writer logs and event IDs to avoid false conclusions.

## 11. CQL Practice: Baseline, Run Repair, Reconcile

**Environment:** lab cluster of Apache Cassandra 4.x or 5.0, three nodes in one datacenter whose **actual** name is `dc1`, `cqlsh`, and `nodetool` access on all three nodes. RF=3 example is for lab; production must match real topology—never create RF=3 on a single-node cluster.

### Step 1 — Create Table for Two Sample Records

~~~sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS repair_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    amount int,
    business_version int,
    note text,
    PRIMARY KEY ((tenant_id), order_id)
) WITH gc_grace_seconds = 864000;
~~~

**Note:** `tenant_id` is the partition key; `order_id` is the clustering key. Two orders under the same tenant can land on the same replica set. When analyzing ring coverage, add tenants whose tokens distribute across different regions.

### Step 2 — Write Data with Deterministic History

To observe `WRITETIME` clearly, in an **empty lab** use fixed microsecond timestamps. Never copy these illustrative timestamps into production logic.

~~~sql
CONSISTENCY QUORUM;

INSERT INTO repair_lab.orders
    (tenant_id, order_id, status, amount, business_version, note)
VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW', 500, 1, 'created'
) USING TIMESTAMP 1700000000000100;

UPDATE repair_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PAID', business_version = 2
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO repair_lab.orders
    (tenant_id, order_id, status, amount, business_version)
VALUES (
    'tenant-a',
    22222222-2222-2222-2222-222222222222,
    'CANCELLED', 100, 1
) USING TIMESTAMP 1700000000000300;

DELETE FROM repair_lab.orders
USING TIMESTAMP 1700000000000400
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

In this example, order `1111...` should show `status='PAID'` and `business_version=2`, while `amount=500` keeps the initial INSERT timestamp. Order `2222...` has a tombstone newer than the live data and **is no longer returned**.

### Step 3 — Establish an Audit Baseline Independent of the Cluster

Before repair, record a table of **business expectations** from a test audit source rather than inferring solely from CQL:

| Key | Expectation | Reason |
|---|---|---|
| `tenant-a/1111...` | PAID, amount=500, business_version=2 | Valid payment update event |
| `tenant-a/2222...` | Row absent | Confirmed DELETE event |

Then read Cassandra, logging CL, timestamp, coordinator, and output:

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_ts,
       WRITETIME(amount) AS amount_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

CONSISTENCY QUORUM;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_ts,
       WRITETIME(amount) AS amount_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, status
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

**Expected in a healthy cluster:** PAID, amount 500, version 2; status timestamp `1700000000000200`, amount timestamp `1700000000000100`; order 2222 returns empty. Running `SELECT ONE` across coordinators returns identical results when healthy; this lab does not require fabricating inconsistency.

### Step 4 — Inspect Replicas and Repair Scope

~~~bash
nodetool status
nodetool getendpoints repair_lab orders tenant-a
nodetool tablestats repair_lab.orders
nodetool help repair
~~~

Record endpoint lists, version, Up/Normal nodes, and token ranges serving the table. In multi-DC labs, although `getendpoints` lists endpoints, do not assume all replicas live in the same DC.

### Step 5 — Preview/Measure First If Binary Supports It

~~~bash
# Command illustrates option only; confirm in "nodetool help repair".
nodetool repair --preview repair_lab orders
~~~

Preview is a **diagnostic** tool, not a substitute for repair having occurred. It can still consume I/O/network to build Merkle trees. If logs show zero differences, that fits a synced lab—yet **does not prove business correctness** of the whole table.

### Step 6 — Repair with Controlled Scope

~~~bash
# On one lab node, once authorized to run repair.
nodetool repair --full -pr repair_lab orders
~~~

To cover **all primary ranges**, schedule the same command pattern across **all required nodes** sequentially rather than firing all at once blindly. With three lab nodes, completing the command on node A alone does not prove B/C's ranges were repaired.

Monitor:

- Command output and per-range/session success or failure lines.
- Node availability, streaming, free disk, compaction.
- Remaining unrepaired token ranges.
- Failed/retried repair state and root causes.

Mark `repair coverage = COMPLETE` only when all planned ranges finish; otherwise mark `PARTIAL` with the missing list.

### Step 7 — Post-Repair Verification

Re-run **the exact same SELECT statements** on the same keys, logging timestamps and CLs. Compare against template:

| Check | Pre | Post (Expected) | Criterion |
|---|---|---|---|
| `order 1111 status` | PAID or possibly stale on lagging replica | PAID | Matches audit, not just replica majority |
| `WRITETIME(status)` | 1700000000000200 or older | 1700000000000200 | Latest mutation per lab model |
| `amount` | 500 | 500 | Value not unintentionally overwritten |
| `business_version` | 2 | 2 | Matches business audit |
| `order 2222` | Possibly present on lagging replica | Absent | No zombie; tombstone stayed valid/propagated |
| Repair range coverage | Unrecorded | Full target scope completed | Not just one node |
| Errors/timeouts | Baseline | No new errors | Monitor Java service too |

**Case with zero initial drift:** Repair still runs normally with near-zero streaming. That is not a failed exercise—the lesson's value lies in **the verification workflow and understanding limits**, not breaking a cluster to fabricate bugs.

### Step 8 — Thought Exercise: C Missed UPDATE

Without actually stopping a node, fill in expected outcomes:

~~~text
A: PAID, ts=200; business_version=2
B: PAID, ts=200; business_version=2
C: NEW,  ts=100; business_version=1

With full repair:
  If data on A/B is intact, C converges to PAID/version 2.

If A/B also lost both mutations or all hold the wrong state:
  Repair has no source to recreate the right event.
~~~

In a lab authorized for fault injection, testing C disconnected requires a dedicated fault plan checking whether C received hints, mutation state post-recovery, scoped repair, and lab rollback. **Never leave a node offline past grace in production to reproduce zombies.**

## 12. Reconciling from a Java Application

A Java app using Cassandra Driver 4.x can read a logical snapshot of a row along with write timestamps for select columns and compare against **a trusted business source**. The driver has no API to "read all three internal copies and automatically pick the right one" in a normal SELECT.

Java 17 example (accepting a reused `CqlSession` configured with local DC):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class RepairVerification {
    public record OrderView(
            String status,
            Integer amount,
            Integer businessVersion,
            Long statusTimestampMicros) {}

    public static OrderView read(
            CqlSession session, String tenantId, UUID orderId) {
        SimpleStatement statement = SimpleStatement.builder(
                "SELECT status, amount, business_version, " +
                "WRITETIME(status) AS status_ts " +
                "FROM repair_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(statement).one();
        if (row == null) {
            return null; // No live row at chosen CL.
        }
        Integer amount = row.isNull("amount")
                ? null : row.getInt("amount");
        Integer version = row.isNull("business_version")
                ? null : row.getInt("business_version");
        Long ts = row.isNull("status_ts")
                ? null : row.getLong("status_ts");
        return new OrderView(row.getString("status"), amount, version, ts);
    }
}
~~~

Business-level verification uses an **expected state** from event logs, never the output of the same SELECT as its ground truth:

~~~java
import java.util.Objects;
import java.util.UUID;

UUID orderId = UUID.fromString(
        "11111111-1111-1111-1111-111111111111");

RepairVerification.OrderView actual =
        RepairVerification.read(session, "tenant-a", orderId);

boolean matchesAuditedState = actual != null
        && Objects.equals(actual.status(), "PAID")
        && Objects.equals(actual.amount(), 500)
        && Objects.equals(actual.businessVersion(), 2);
~~~

The snippet above is **code inside a method that already has `session`**, not a standalone Java program. In production:

1. Read by exact primary key, bounding query size and page size on large partitions.
2. Choose CL matching topology; `LOCAL_QUORUM` does not prove remote DCs are updated.
3. Attach correlation IDs, schema versions, DCs, timestamps, and audit event versions to reconciliation logs.
4. Compare canonicalized data structures; pay close attention to NULLs, TTLs, collections, timestamps, and value encoding.
5. Never auto-backfill data from a single mismatch: verify the expected source and avoid overwriting newer valid mutations.
6. Monitor timeouts and retries; repair can elevate I/O, slowing Java services even when data has already converged.

### 12.1. Why Not Use `SELECT QUORUM` as a Repair Certificate?

With RF=3 in one DC, `LOCAL_QUORUM`/`QUORUM` needs only two replicas. If A/B hold the right copy while C remains unrepaired, the app still receives the right value. Best practice:

- Use higher-CL reads as **an application-experience check**.
- Use **repair completion/coverage** to verify synchronization ran.
- Use **audit/business expected state** to verify correctness.
- Use tracing/specialized checks when investigating one specific replica.

These three layers **complement** each other—none replaces the others.

## 13. Production Before-and-After Repair Reconciliation Runbook

The goal of the runbook is not "command exited," but **knowing which dataset was verified, whether it could be fixed, and what unresolved risks remain**.

### 13.1. Pre-Repair Phase: Confirm Safety

1. **Identify incident:** ticket, detection time, tenant/primary keys, reporter, business impact.
2. **Assess cluster:** nodes/racks/DCs, RF, gossip/schema state, free disk, active streaming/compaction, version.
3. **Assess tombstones:** `gc_grace_seconds` of target tables, node absence duration, last successful repair. If downtime already exceeded grace, **do not blindly push the stale node into repair**.
4. **Capture baseline:** sample primary keys, critical fields, `WRITETIME` where relevant, CL/DC, audit expected state, latency metrics.
5. **Lock coverage:** keyspace, tables, token ranges, replicas/DCs, full vs. incremental, job concurrency, owner.
6. **Backup per runbook:** snapshots/backups ahead of high-risk work; save schemas/configs and rollback/restore plans. Snapshots do not replace anti-entropy repair.
7. **Set STOP conditions:** low free disk, new node down, streaming failures, p99 latency breaching SLA, or invalidated repair scope.

### 13.2. During Repair

~~~text
   Check nodes and scope
             |
     Preview if suitable
             |
     Repair in batches
       /           \
   Succeeded       Failed
      |              |
 Log coverage  Stop/investigate/retry
      |              |
      +-------> Aggregate coverage
                     |
        If coverage incomplete:
        DO NOT report "repair finished".
~~~

Record in the ticket:

- Exact commands and executing nodes, start/end UTC, Cassandra version.
- Range/job IDs, errors or warnings, streamed volume, CPU/network/disk.
- Nodes excluded by faults; scopes still needing retry.
- Concurrent writes, topology shifts, backups/restores, or notable compaction.

Never crank job counts endlessly to "beat a deadline"; aggressive repair can take the cluster down and make data verification harder.

### 13.3. Post-Repair: Three Verification Gates

| Gate | Question | Pass Criterion |
|---|---|---|
| A — Technical | Repaired the right replicas/ranges? | Per-range jobs succeeded with zero missed target nodes/DCs/tables |
| B — Data | Read values match expectations? | Audited keys verified, including DELETE/TTL keys; diffs explained |
| C — Service | Applications still healthy? | CL, p95/p99 latency, timeouts, disk, and repair backlog within ops limits |

**Only when all three gates pass should completion be declared within the documented test scope.** If Gate A passes while Gate B fails, **do not loop repair endlessly**: the root issue is likely bad data on all replicas, wrong timestamps, zombies, bad expectations, or another application table.

### 13.4. Classifying Outcomes into Four Categories

| Outcome | Interpretation | Next Step |
|---|---|---|
| `SYNCED_AND_VALID` | Sufficient repair coverage, audited samples match, SLAs healthy | Close wave; resume periodic repair schedule |
| `SYNCED_BUT_INVALID` | Replicas match each other yet violate business truth | Restore from source of truth—do not just re-run repair |
| `PARTIAL_REPAIR` | Ranges/nodes unrepaired or jobs failed | Retry exact missing scope; keep alerts active |
| `UNKNOWN` | Insufficient audit, topology, or timestamp evidence | Do not claim data is valid; open further investigation |

These categories are a **lesson runbook convention**, not an API status emitted natively by Cassandra.

## 14. Diagnosing Cases Repair Cannot Fix

### Case A: "Repair SUCCEEDED Yet the Order Is Still Missing"

**Symptoms:** API reports order saved, yet all Cassandra read CLs return nothing; repair reports zero diffs.

**Analysis:** The order may never have been persisted to the replica set, was deleted across all replicas, or restore/TTL left current state without the row. Repair **has no live copy to stream**.

**Action:** check audit events, CDC/outbox, backups/snapshots, and CQL queries confirming exact primary key; verify mutations are not shadowed by a newer tombstone. Once the valid record is confirmed, restore through a controlled workflow.

### Case B: "After Repair, a DELETEd Row Reappeared"

**Symptoms:** an old node stayed down a long time; upon returning and repairing, a deleted row reappeared.

**Analysis:** tombstones may have purged on healthy replicas while the old node retained the stale value. Repair **has no knowledge of lost DELETE history**.

**Action:** isolate/assess the recovered node, inspect `gc_grace_seconds` and repair timelines, check delete audits, scope the blast radius, and re-apply verified deletions; review node-rebuild policies for nodes past grace.

### Case C: "Repair Made Every Replica Converge on the Wrong Value"

**Symptoms:** a Java service sent an UPDATE with a future write timestamp, causing that stale/unwanted value to override all subsequent updates.

**Analysis:** LWW compares timestamps; repair propagates the highest-timestamp mutation **among existing data**, unaware of business payment order.

**Action:** fix the bad timestamp emitter, review event history, and plan controlled remediation updates. Avoid writing "infinitely large" timestamps just to force values.

### Case D: "Source Table Repair Succeeded Yet Customer Page Still Lacks Order"

**Symptoms:** `orders_by_id` has the order, while `orders_by_customer` does not.

**Analysis:** these are two separate denormalized tables maintained by the application; anti-entropy repair on each table never moves rows from one table to the other.

**Action:** fix the dual-write/CDC pipeline, replay events by idempotent keys, and reconcile both table models independently.

### Case E: "Preview Was Clean Yet Wrong Rows Still Exist"

**Symptoms:** Merkle comparison reports zero diffs; audit proves stored values are wrong.

**Analysis:** all three replicas may agree on the wrong state, or the preview did not cover the queried scope.

**Action:** verify preview scope, token ranges, and primary keys; once coverage is confirmed, pivot to investigating **logical data corruption** rather than assuming a repair bug.

## 15. Self-Assessment Questions

**Question 1.** A/B hold `status=PAID, ts=200`; C holds `status=NEW, ts=100`. Where does a full repair with intact metadata bring them?  
**Guidance:** PAID wins by timestamp; C converges with A/B.

**Question 2.** A/B/C all miss an order present in the audit log. Will running repair repeatedly recreate the order?  
**Guidance:** No. You must recover from another live source such as backups/CDC/event logs.

**Question 3.** `SELECT QUORUM` returns PAID before repair. Can you conclude C already holds PAID?  
**Guidance:** No; two replicas holding the new copy already satisfy quorum.

**Question 4.** One repair command with `-pr` succeeds on node A. Does that mean the entire keyspace is repaired?  
**Guidance:** No; you must prove coverage of every primary range in the plan.

**Question 5.** Why does identical `COUNT(*)` across two reads not prove data correctness?  
**Guidance:** Equal row counts can still differ in primary keys, values, timestamps, or tombstones.

**Question 6.** If C stays down past grace and A/B purge tombstones, what can repairing after C returns cause?  
**Guidance:** Zombie data: C spreads stale records when no newer deletion marker remains.

**Question 7.** A Java app observes an unexpected `WRITETIME(status)`. Will repair reset timestamps to wall-clock time?  
**Guidance:** No; locate the bad timestamp source and fix the data at the business level.

**Question 8.** Why can't preview repair replace comparing against an audit log?  
**Guidance:** It compares replicas/ranges with one another without knowing whether values satisfy business truth.

**Question 9.** Should you stop repairing because a table uses only `LOCAL_QUORUM` and never `ONE`?  
**Guidance:** No. Tombstones and lagging replicas still risk zombies, and read repair does not cover all ranges.

**Question 10.** A table drifted because a consumer failed to write denormalized rows; will repairing the source table fix it?  
**Guidance:** No. Fix the consumer and replay from an independent mutation source.

**Question 11.** When can a ticket be closed as `SYNCED_AND_VALID`?  
**Guidance:** Repair coverage succeeded, audited samples match, apps are stable, and verified scope is documented.

**Question 12.** What risk can restoring an old snapshot after a DELETE introduce?  
**Guidance:** Reintroducing deleted data unless timelines, tombstones, and truth sources are accounted for.

## 16. Summary

~~~text
                  PRE-REPAIR RECONCILIATION
                     /        |         \
                 Audit   Replica/range  CL/trace
                 truth    & node state  & timestamps
                     \        |         /
                      \       |        /
                            REPAIR
                  Merkle comparison + streaming
                              |
                       COVERAGE CHECK
                         /         \
                    enough        short
                       |            |
                 POST RECONCILE   retry/escalate
                       |
             +---------+----------+
             |                    |
     Replicas converged?   Matches audit truth?
             |                    |
             +---------+----------+
                       |
                  SERVICE HEALTH
                       |
                 Scoped conclusion

Repair cannot recreate:
  - Records lost across every replica.
  - DELETE intent once tombstones have purged.
  - Business-correct values when a wrong timestamp won.
  - Rows skipped by the app in another denormalized table.
  - Corrupted data when no clean copy or backup survives.
~~~

**Key takeaway:** `nodetool repair` makes replicas **converge on surviving mutations**—it does not reconstruct lost history, enforce business constraints, or replace backups/restores. Proper operations follow **audit-backed baseline → covered repair → post-check on same keys + audit → service health verification**, while recognizing early when a task must shift from *replica synchronization* to *data recovery*.

## References

- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, incremental/full repair, Merkle trees, and why periodic repair is needed.
- [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html) — repair options, node/range scopes, and version-specific operation.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — `gc_grace_seconds`, zombie data, and compaction.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — replication, consistency, hinted handoff, read repair.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable, LWW, and compaction.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `WRITETIME`, `USING TIMESTAMP`, TTL, UPDATE, and DELETE.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — replication strategy, primary key, schema, and table properties.
