# Last-Write-Wins When Merging Data from Multiple Replicas in Apache Cassandra

> **Chapter:** Replica Synchronization  
> **Focus:** How Apache Cassandra reconciles differing values returned by multiple replicas, the **last-write-wins (LWW) rule by write timestamp**, the effects of read/write consistency levels, tombstone deletions, repair, clocks, and Java applications.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Explain accurately why **"last write" in Cassandra means the mutation with the larger write timestamp**, not necessarily the request that arrived at a node later or the response returned last.
2. Distinguish the states of a **replica**, **partition**, **row**, and **cell**, and why columns in the same row can come from different mutations.
3. Illustrate read reconciliation when some replicas hold newer data and others hold stale values; evaluate the implications of `ONE`, `QUORUM`, and `LOCAL_QUORUM`.
4. Explain how DELETE, TTL, tombstones, compaction, and repair interact with LWW.
5. Reproduce timestamp ordering using CQL `USING TIMESTAMP` and inspect `WRITETIME`; identify clock skew or wrong timestamp units.
6. Choose the appropriate conflict-handling approach between LWW and **lightweight transactions (LWT)**, and apply it from the Cassandra Java Driver.

In a **distributed wide-column** database like Cassandra, the partition key determines the token and replicas per the replication factor (RF). Applications design tables around queries and choose consistency levels (CL); those choices determine **which replicas are written/read**, while LWW determines **which value wins when replicas disagree**.

## 2. What Problem Does LWW Solve?

Suppose a keyspace has RF=3; partition `tenant-a` is replicated across three nodes A, B, and C. One replica may temporarily lose connectivity, a mutation may arrive late, or two clients may write nearly concurrently:

~~~text
                   Coordinator
                       |
                WRITE status=PAID
                 ts=1700000000000200
                   /   |    \
                  v    v     x
                  A    B     C (down)
                 PAID PAID  NEW
                 ts=...0200  ts=...0100

           Later, C comes back online
                  /    |     \
              A: PAID B: PAID C: NEW
                  \    |     /
                  Read / repair
                        |
                Reconcile by timestamp
                        |
                  PAID beats NEW
~~~

**LWW is a data reconciliation rule when multiple versions exist**, allowing replicas to converge once they receive the relevant mutations. It does not turn a multi-node operation into a global ACID transaction, nor does it make all replicas identical immediately after every write.

### 2.1. Three Concepts Easily Confused

| Concept | Meaning in Cassandra | Example |
|---|---|---|
| **Order requests arrive at a node** | Network or thread processing order; may differ across replicas | A receives W1 then W2; C receives W2 then W1 |
| **Write timestamp** | Logical time value attached to a mutation/cell, typically **microseconds since epoch** in CQL | W1=1000, W2=2000 |
| **Final live value** | Reconciliation outcome per Cassandra timestamps, tombstones, and data rules | W2 wins because 2000 > 1000 |

If W2 arrives **before** W1 at replica C, C must still retain W2 when both mutations target the same cell scope and W2's timestamp is larger. Thus "last-write-wins" is best understood as **highest-timestamp-wins** for regular data.

## 3. Unit of Reconciliation: Mostly Per-Cell, Not Per-Row

For Cassandra regular columns, a mutation carries a write timestamp for each written value. When a row receives UPDATEs on two columns at different times, each column can have its own timestamp.

Example row:

~~~text
PRIMARY KEY: (tenant_id='tenant-a', order_id=1111...)

Replica A                         Replica B
--------------------------------  --------------------------------
status='PAID', ts=300              status='NEW', ts=100
amount=150,   ts=120              amount=200, ts=250
note='sent',  ts=180              note='sent', ts=180

Valid reconciliation:
  status = 'PAID'  (A's 300 > B's 100)
  amount = 200    (B's 250 > A's 120)
  note   = 'sent' (same value/timestamp on both)
~~~

The result can be **a single row combining values from multiple replicas**. There is no simplistic rule like "node A's whole row beats node B's" or "the replica with more newer columns wins."

This aligns with the **CQL wide-column** model, with an important business consequence: if `status` and `amount` must change together as an indivisible state transition, **do not assume two independent UPDATEs form an atomic isolated transaction**. Cassandra provides certain partition-scoped atomicity guarantees for single mutations/batches, which differ from relational ACID transactions with isolation and conditional checks.

### 3.1. Basic Reconciliation Rules

For the **same cell/identifier**, setting aside special variants like counters:

1. A mutation with a **larger write timestamp** usually prevails.
2. A **tombstone** shadows live data within its scope if the tombstone's timestamp is **greater than or equal to** the write timestamp of the data being deleted.
3. On **equal timestamps**, Cassandra applies internal deterministic tie-break rules where a tombstone takes precedence over a live cell within the same scope; two live cells with identical timestamps do not follow "whichever request arrived last wins."
4. **TTL** and expiration time determine whether a value remains live or has transitioned to a deleted state; do not look at timestamps alone while ignoring lifetime.
5. The reconciled outcome may be persisted via read repair / anti-entropy repair so replicas converge, provided those mechanisms actually run and still retain the required metadata.

Conceptual algorithm for a single cell:

~~~text
reconcile(cellX on A, B, C):
    collect relevant versions/tombstones
    prefer larger write timestamp
    if timestamps tie: apply Cassandra tie-breaker
    evaluate tombstones by scope and TTL/liveness
    return valid final state
~~~

**Do not re-implement reconciliation on the client by comparing `WRITETIME(col)` alone**: row tombstones, partition/range tombstones, liveness, and equal-timestamp edge cases must be handled completely by the storage engine.

### 3.2. Exceptions to Understand

- **Counter columns** store and merge via counter contexts rather than simple LWW overwrite rules like text/int columns; CQL also restricts `USING TIMESTAMP` on counters.
- **Non-frozen collections** can contain multiple elements with per-element deletion metadata; **frozen collections** are handled differently since they are stored as a single value. Never assume a collection always has a single timestamp.
- **Row/partition/range tombstones** shadow multiple cells, so "the highest timestamp of `status`" alone does not determine whether the row appears.
- **Lightweight transactions** provide a conditional update path based on Paxos; they solve a different problem class than regular writes and LWW.

## 4. Read Reconciliation: ONE Can Read Stale, QUORUM Can Reconcile

Consider three replicas A/B/C holding the same partition:

~~~text
T0:
  A=status NEW, ts=100
  B=status NEW, ts=100
  C=status NEW, ts=100

T1:
  UPDATE status PAID, ts=200, CL=QUORUM
  A=status PAID, ts=200   -> ACK
  B=status PAID, ts=200   -> ACK
  C=status NEW,  ts=100   -> missed

T2:
  SELECT status CL=ONE, hits C
    -> may see NEW (stale).

  SELECT status CL=QUORUM, answers from a replica pair
    -> with RF=3, any two-replica pair includes at least one
       replica that ACKed ts=200 (within the same replica set and
       barring other mutations/failures).
    -> reconcile: PAID(ts=200) beats NEW(ts=100).
~~~

When reading across multiple replicas, Cassandra can use **full-data responses** and **digest responses** to detect mismatches, then fetch needed data and reconcile. Exact read mechanics depend on version, query type, speculative retry, and read repair policy.

### 4.1. Why the Quorum Formula Is Only Part of the Answer

With RF=3 (full replicas) in one DC:

| CL | Responses Needed | Consequence |
|---|---:|---|
| `ONE` | 1 | Higher read/write availability during node failures; can see stale data |
| `QUORUM` | 2 | Read and write response sets under the same RF intersect |
| `ALL` | 3 | Requires every replica to respond; easily unavailable when a node is down |

The **R + W > RF** formula helps analyze responding replica sets, subject to key assumptions:

- Reads and writes operate on the **same replica set and consistency scope**.
- No higher-timestamp concurrent write or unresolved conflict intervenes.
- Coordinators and clients do not mistake a timeout for a guaranteed failed write.
- Examined replicas still retain enough metadata to reconcile; GC'd tombstones introduce separate zombie risks.
- On multi-DC clusters, `LOCAL_QUORUM` uses the **local DC's** RF only; it cannot imply "visible across all DCs."

Quorum **does not establish global wall-clock ordering** for regular UPDATEs. A request arriving later with a smaller timestamp still loses to an earlier completed write with a larger timestamp.

### 4.2. Read Repair vs. Periodic Repair

Upon detecting a digest mismatch, Cassandra can repair discrepancies within the read data scope. Starting in Cassandra 4.0, tables have a `read_repair` option such as `BLOCKING` or `NONE` (check your exact version); `BLOCKING` can repair read data before returning depending on CL.

**Read repair is scoped to queries actually executed.** It does not replace **anti-entropy repair across all token ranges**, which is needed to heal partitions rarely read or sitting on newly recovered replicas.

~~~text
Read QUORUM hits mismatch
     |
     +-> reconcile to return result
     +-> may perform read repair per version/config

Nodetool / scheduled repair:
     |
     +-> scans and compares token ranges
     +-> synchronizes differences even for unread partitions
~~~

## 5. Write Path: Why Doesn't One Mutation Reach All Replicas Simultaneously?

Cassandra uses the replication strategy to choose natural replicas for a token range. The coordinator sends writes according to the requested CL. A request can complete once enough responses arrive **before every replica has received it**.

~~~text
                      WRITE W1
                        |
                 Coordinator
                 /    |     \
                A     B      C
              ACK   ACK    timeout
                \    /
               QUORUM succeeded

While C is unavailable:
  A and B hold the new version.
  C may still hold the old version.
  Hints/repair are needed to help C catch up.
~~~

If an older mutation arrives after a newer mutation on C, **timestamp reconciliation** protects the newer value. For example:

~~~text
Timestamps:
  W1: status NEW,  ts=100
  W2: status PAID, ts=200

Network arrival order at C:
  Receives W2 first -> PAID
  Receives W1 later -> stays PAID, because 100 < 200
~~~

**Hinted handoff** can store mutations for briefly interrupted replicas; **anti-entropy repair** compares replicas when run. Neither mechanism guarantees every mutation is delivered in all situations simply because a write CL returned success.

## 6. Timestamps: "New" to Cassandra May Not Mean "New" to Users

### 6.1. CQL Timestamps Are in Microseconds

CQL's `USING TIMESTAMP` expects an integer representing **microseconds since the Unix epoch**, not the milliseconds used by many Java/JavaScript APIs.

~~~sql
-- Correct CQL unit: epoch microseconds.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`WRITETIME(status)` returns the timestamp of the **currently live cell** when the column supports the function:

~~~sql
SELECT status,
       WRITETIME(status) AS status_write_ts,
       amount,
       WRITETIME(amount) AS amount_write_ts
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Note that `WRITETIME` does not read full mutation history. If a value was deleted, the function does not give you a complete tombstone history; diagnosis requires combining logs/tracing, metadata, audits, and version-appropriate tools.

### 6.2. Who Assigns the Timestamp?

A request omitting `USING TIMESTAMP` still receives a timestamp from the **driver and/or coordinator** mechanism depending on version/configuration. Java Driver 4.x includes a client-side timestamp generator; when not setting timestamps explicitly, do not assume every write uses the coordinator's clock. Inspect your driver configuration before explaining a conflict.

Different timestamp sources introduce risks:

| Source | Risk to Consider |
|---|---|
| OS clocks across nodes | **Clock skew** between machines |
| Java driver client-side timestamping | Instances with skewed clocks or restarts |
| Application `USING TIMESTAMP` | Wrong units, hardcoded numbers, future timestamps, stale replays |
| Imports, restores, CDC replays | Rewriting old data much later with original timestamps |
| Multiple services writing the same cell | Timestamp races unrelated to business order |

**Future timestamps** are especially dangerous. If a client writes `status='PAID'` with a timestamp hours in the future, valid UPDATEs or DELETEs from other clients cannot win until real time catches up past that future value. Raising CL will not fix timestamp ordering bugs.

### 6.3. Situations Often Misattributed as "Lost Writes"

| Symptom | Possible Explanation |
|---|---|
| UPDATE returns OK, yet SELECT still sees old value | New UPDATE arrived later with a **lower** timestamp than the existing cell |
| Writes from service B always beat service A | B's clock runs ahead; B's timestamps are always larger |
| DELETE succeeded, yet value still exists | Higher-timestamp live mutation exists, or read hit a replica missing the delete |
| Some columns updated, others did not | Each cell has its own timestamp and mutation history |
| A value reappears after repair | A replica with a higher write timestamp synced, or a needed tombstone was lost |

Never blame all of the above on LWW without checking **write timestamps, tombstones, CL, replica health, node clocks, and write history**.

## 7. How DELETE, TTL, and Tombstones Participate in Reconciliation

DELETE is also a timestamped mutation, representing a **deletion marker** rather than a live value.

~~~text
Replica A: status='PAID', ts=100
Replica B: tombstone status, ts=200
Replica C: status='PAID', ts=100

Reconciliation:
  tombstone ts=200 shadows status ts=100
  -> returns no value for status.
~~~

If a valid write `status='REFUNDED'` arrives with timestamp `ts=300`, it beats tombstone `ts=200` under LWW and reappears. That is a **valid newer write**, distinct from zombie data coming from a stale replica.

### 7.1. DELETE by Scope

- **Cell tombstone** shadows a single cell.
- **Row tombstone** shadows cells in a row by timestamp/scope.
- **Range tombstone** shadows multiple clustering rows across a slice.
- **Partition tombstone** shadows a partition by timestamp.

A query showing `WRITETIME(status)=300` is not enough to prove `status` will appear if a higher-timestamp row or partition tombstone exists. To compute the exact result, Cassandra combines **liveness, tombstones, and multiple SSTables**, rather than just comparing two numbers.

### 7.2. TTL Expires Values

TTL is stored alongside the value. Once expired, the cell is no longer live data; reads evaluate the expiration/tombstone accordingly. Because SSTables are immutable, expired data may stay on disk until compaction and garbage-collection conditions permit removal.

~~~sql
UPDATE lww_lab.orders
USING TTL 300
SET note = 'temporary'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT note, TTL(note), WRITETIME(note)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`TTL(note)` returns **remaining lifetime in seconds** within the function's supported scope; it is not the write timestamp. Do not use TTL as an automatic tool to resolve conflicts on other fields.

### 7.3. Zombie Risk When Tombstones Are Purged Before Repair

When a replica misses a DELETE and is not repaired before tombstones on healthy replicas are purged after `gc_grace_seconds` and eligible compaction, old data can **reappear**. LWW cannot infer deletion intent if the higher-timestamp deletion marker has vanished from all repairable replicas.

~~~text
Day 0: A/B receive DELETE ts=200; C only holds status ts=100.
Within grace: repair can deliver tombstone ts=200 to C.
After grace + valid purge: A/B no longer hold the tombstone.
C returns with status ts=100; repair no longer has ts=200 to compare.
-> Old data may be treated as live and spread to A/B.
~~~

Therefore, **repair schedules must finish covering data before grace expires**, and nodes offline past grace must be evaluated/rebuilt per runbook instead of arbitrarily reintroducing old SSTables.

## 8. Tie-Breaking When Timestamps Are Identical

Two writes sharing the exact same timestamp is a special case:

~~~text
W1: status='NEW',  ts=500
W2: status='PAID', ts=500
~~~

Cassandra has **deterministic** tie-break rules for equal timestamps so replicas converge. When a live cell and a tombstone share the same timestamp/scope, **the tombstone wins**. For two live cells with the same timestamp and different values, the storage engine applies an internal deterministic tie-breaker based on serialized values and metadata, having nothing to do with "last request" in user wall-clock time.

Therefore:

- **Do not** intentionally issue two writes with the same timestamp and predict the winner from network order.
- **Do not** use equal timestamps as a way to simulate a transaction.
- **Do not** depend on byte-level tie-breaking details as business logic, especially with multiple cell types/collections.
- If you must guarantee "transition NEW → PAID only while current state is still NEW," use a **conditional update/LWT** or proper serialization rather than relying on timestamp comparison.

## 9. LWW and Lightweight Transactions (LWT) Solve Different Problems

LWW lets **regular** mutations converge across divergent replicas or near-concurrent writes. When business logic requires a **compare-and-set** condition—such as "only move an order from NEW to PAID if it is still NEW"—LWW cannot prevent two clients from both believing they succeeded.

Illustrative LWT example:

~~~sql
UPDATE lww_lab.orders
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111
IF status = 'NEW';
~~~

Conditional statements use the **Paxos** consensus protocol. The CQL result includes an `[applied]` column:

- `[applied] = true`: condition held, mutation was accepted.
- `[applied] = false`: condition no longer held; the application should read current state and decide whether to retry or report a conflict.

LWT consistency choices also include **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) and the regular consistency level for the commit phase; choose according to topology and requirements. LWT takes more round trips than a regular UPDATE, so benchmark it.

| Requirement | Suitable Approach | Why |
|---|---|---|
| Write state logs tolerant of eventual convergence | Regular UPDATE + appropriate CL, repair | Simple, high performance; timestamps settle conflicts |
| Allow only one client to transition state if unchanged | UPDATE ... IF ... (LWT) | Condition checked via Paxos |
| Create a single unique record by primary key | INSERT ... IF NOT EXISTS (LWT) | Reduces risk of two clients writing conflicting records on the same key |
| Maintain invariants across multiple partitions/tables | Dedicated transaction/orchestration design | LWT does not turn the whole cluster into a multi-table ACID database |
| Business event order independent of clocks | Controlled sequence/version or event sourcing | Clock timestamps do not capture business causality |

**Never casually combine `USING TIMESTAMP` with `IF` mutations**: Cassandra does not support user-supplied timestamps in the same way for conditional statements. Let LWT determine validity and design reads/writes per version docs.

## 10. CQL Lab: A Later Write Can Still Lose

**Environment:** an Apache Cassandra lab cluster with at least 3 nodes in one DC hypothetically named `dc1`, `cqlsh`, and `nodetool` access; steps do not require killing nodes. Use `dc1` only if that is your cluster's actual DC name; otherwise match your topology.

### Step 1 — Create Keyspace and Table by Partition Key

~~~sql
CREATE KEYSPACE IF NOT EXISTS lww_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3'
};

CREATE TABLE IF NOT EXISTS lww_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    amount int,
    note text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Each row is keyed by (`tenant_id`, `order_id`). The replica set is chosen by the hash of **`tenant_id`** and the replication strategy; `order_id` is a clustering key. With tiny lab data, this illustrates reading timestamps—not a universal partition key pattern for every production system.

### Step 2 — Write Initial Values with a Fixed Timestamp

~~~sql
CONSISTENCY QUORUM;

INSERT INTO lww_lab.orders
    (tenant_id, order_id, status, amount, note)
VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW',
    100,
    'created'
)
USING TIMESTAMP 1700000000000100;

SELECT status, WRITETIME(status) AS status_ts,
       amount, WRITETIME(amount) AS amount_ts
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Expected:** `status='NEW'`, `amount=100`, both with write timestamp `1700000000000100`. This is an illustrative past timestamp, not advice to hardcode timestamps in real applications.

### Step 3 — Mutation with Higher Timestamp Arrives First

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000300
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Sent afterward, yet write timestamp is LOWER.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PENDING'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Expected:** Remains `PAID` with timestamp `1700000000000300`. The `PENDING` UPDATE was issued **later** yet lost because of its lower timestamp. This proves "LWW" is a **timestamp-order** rule, not terminal execution order.

### Step 4 — Two Columns Win at Different Timestamps

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000250
SET amount = 150
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000150
SET note = 'checked'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status),
       amount, WRITETIME(amount),
       note, WRITETIME(note)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Expected:** `status=PAID` (`...0300`), `amount=150` (`...0250`), `note=checked` (`...0150`). Different timestamps demonstrate that reconciliation largely happens **per cell**.

### Step 5 — Tombstone Beats Older Data

~~~sql
DELETE status
FROM lww_lab.orders
USING TIMESTAMP 1700000000000400
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Old write after DELETE, timestamp still lower than tombstone.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000350
SET status = 'OLD-STATUS'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, amount, note
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Expected:** `status=null` (due to tombstone), while `amount=150` and `note=checked` remain live. This is a **single-column** DELETE, not a whole-row DELETE.

### Step 6 — Writing Newer Than Tombstone Is Valid Behavior

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000500
SET status = 'REOPENED'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status), amount
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Expected:** `REOPENED` has timestamp `...0500`, larger than tombstone `...0400`. This is a **valid newer write** beating a delete, not necessarily zombie data.

### Step 7 — Observing CL and Replicas

~~~bash
nodetool status
nodetool getendpoints lww_lab orders tenant-a
~~~

`getendpoints` shows the **expected natural replicas**, not physical contents inside each SSTable. In a lab where node manipulation is allowed, you can disconnect and recover a replica to compare `ONE` vs. `QUORUM`, though **you do not need to force network partitions** to confirm the timestamp rules in earlier steps.

### Step 8 — Distinguishing Read Repair from Periodic Repair

~~~sql
TRACING ON;

SELECT status, WRITETIME(status)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Tracing can reveal participating replicas and reconciliation/read repair activity depending on version; tracing adds overhead, so enable it only briefly in the lab.

When running repair on a test cluster with clear orchestration:

~~~bash
# Run on schedule across EACH relevant node/DC,
# to cover all primary token ranges.
nodetool repair --full -pr lww_lab orders
~~~

A single command on one node with `-pr` **does not cover the entire cluster**. Repair converges replicas, yet it does not rewrite business timestamps into your desired order: **the highest-timestamp value still wins**.

## 11. Java Driver: Inspecting WRITETIME and Avoiding Timestamp Conflicts

In Cassandra Java Driver 4.x, an application can read a cell's timestamp to investigate shadowed writes. Example method taking a reusable application-scoped `CqlSession`:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class OrderVersionReader {
    public static Long statusWriteTimeMicros(
            CqlSession session, String tenantId, UUID orderId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT status, WRITETIME(status) AS status_ts " +
                "FROM lww_lab.orders WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(query).one();
        if (row == null || row.isNull("status_ts")) {
            return null; // No live status cell.
        }
        return row.getLong("status_ts"); // CQL returns epoch microseconds.
    }
}
~~~

With RF=3 in one DC, `LOCAL_QUORUM` requires two responses. Across multiple DCs, it contacts replicas only in the local DC. `WRITETIME` values provide evidence, **not** a substitute for investigating tombstones or application events.

### 11.1. Assign Timestamps Explicitly Only with a Coordinated Mechanism

To reproduce conflicts in a lab from Java, a prepared statement can bind a CQL timestamp:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.UUID;

public final class LabTimestampWriter {
    public static void updateWithControlledTimestamp(
            CqlSession session, long epochMicros,
            String tenantId, UUID orderId, String status) {
        PreparedStatement statement = session.prepare(
                "UPDATE lww_lab.orders USING TIMESTAMP ? " +
                "SET status = ? WHERE tenant_id = ? AND order_id = ?");

        BoundStatement bound = statement.bind(
                epochMicros, status, tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(bound);
    }
}
~~~

**Warning:** Timestamps must be in **microseconds**, not `System.currentTimeMillis()` (milliseconds). The method above is for controlled testing/replay; production apps should normally rely on a properly configured timestamp generator while keeping machine clocks synchronized. If assigning timestamps manually for business logic, design an ordering generator **that cannot conflict across writers**.

### 11.2. When Conditional State Guarantees Are Required

A Java service can use a prepared conditional statement:

~~~java
PreparedStatement conditional = session.prepare(
    "UPDATE lww_lab.orders SET status = ? " +
    "WHERE tenant_id = ? AND order_id = ? IF status = ?");

Row result = session.execute(
    conditional.bind("PAID", "tenant-a", orderId, "NEW")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL))
    .one();

boolean applied = result != null && result.getBoolean("[applied]");
~~~

This snippet sits **inside a method that already holds** `session` and `orderId`, illustrating how to check LWT's `[applied]`. Choose `SERIAL`/`LOCAL_SERIAL` to match your topology and understand Paxos overhead. LWT does not automatically provide global multi-partition transactions.

## 12. Runbook for Checking Replica Divergence and LWW Bugs

### Step 1 — Identify Symptoms and Scope

Record keyspace/table, partition key, clustering key, mismatched column, business timestamp, WRITE/DELETE timing, DC, and CL. Never label something generic "replication lag" without facts on replicas or write timestamps.

| Diagnostic Question | How to Collect |
|---|---|
| What timestamp did the client actually write with? | CQL `WRITETIME` for live cells, driver/app logs, audit timestamps |
| Are multiple writers racing on one cell? | Request IDs, service instances, event chronology |
| Which nodes/replicas participate? | `nodetool getendpoints`, topology, `nodetool status` |
| Which CLs are used for reads and writes? | CQL/statement config, driver config, selective query tracing |
| Are tombstones or TTLs involved? | Schema `gc_grace_seconds`, TTLs, DELETE statements, compaction/repair logs |
| Is there clock skew or a future timestamp? | NTP/clock monitoring, epoch micros vs. millis |
| Was a node isolated or did repair fail? | Hints, repair job coverage, streaming errors |
| Are batches, counters, collections, or LWT used? | Query shape, table schema, and specific feature usage |

### Step 2 — Classify the Failure Mode Accurately

| Observation | Likely Cause | Appropriate Action |
|---|---|---|
| `ONE` sees old, `QUORUM` sees new | Replicas out of sync | Inspect hints/read repair; run scoped repair |
| All CLs see "old" value right after UPDATE | New timestamp lower than existing cell | Check timestamp generator, clock skew, imports/replays |
| DELETE succeeds, yet cell remains | Higher-timestamp live write, insufficient CL, or replica missed delete | Analyze tombstone vs. live cell, timestamps, and CL |
| Deleted row returns after downtime/compaction | Possible zombie due to purged tombstone | Investigate grace/repair/restore before rewriting |
| Two columns in one row come from two versions | Per-cell LWW and separate mutations | Review invariants; consolidate into one mutation or use LWT |
| Two clients change state concurrently, one overwrites | Concurrent regular writes | Use conditional writes/versioning if CAS is needed |
| QUORUM reads work, yet two DCs have not converged | `LOCAL_QUORUM` stays within local DC, or cross-DC repair failed | Verify per-DC RF/CL and repair schedule |

### Step 3 — Avoid "Fixing" with Huge Artificial Timestamps

If a cell carries a future timestamp, writing `USING TIMESTAMP 9999999999999999` to force a win **can make things worse**: future normal mutations will struggle to overwrite that value. Trace the bad timestamp source, identify the right data, and plan controlled remediation aligned with real time and the source of truth.

Likewise, **running repair when data already holds wrong business timestamps** only spreads the **wrong higher-timestamp version** to other replicas. Repair makes replicas **identical**; it has no authority to decide which value is business-correct.

### Step 4 — Verify After Remediation

1. Review logs to confirm the faulty timestamp source was stopped or fixed.
2. Read the same test keys across relevant CLs/DCs, comparing `WRITETIME` and live values.
3. Check tombstones/TTLs for DELETE scenarios, ensuring repair covered affected replicas.
4. Monitor read/write p95/p99 latency, timeouts, hints, and repair status during the next cycle.
5. If zombies appeared, reconcile against business logs to ensure stale records stop spreading.

## 13. Common Misconceptions

| Misconception | Correct Fact to Remember |
|---|---|
| "Last-write-wins means the UPDATE sent last always wins." | The mutation with the **larger write timestamp** wins per reconciliation rules. |
| "All columns in a row share one timestamp." | Cells can be written by separate mutations with distinct timestamps. |
| "QUORUM means all three replicas match after every write." | At RF=3, QUORUM needs two ACKs; the remaining replica may be stale. |
| "The coordinator assigns timestamps in every application." | Drivers can assign timestamps client-side depending on config/version. |
| "`USING TIMESTAMP` uses milliseconds." | CQL requires **microseconds**. |
| "Read repair completely replaces periodic repair." | Read repair only heals queried/detected data, not all ranges. |
| "Repair picks the business-correct data." | Repair converges using existing data and timestamps; bad timestamps can still win. |
| "DELETE simply deletes rows straight out of SSTables." | DELETE writes a tombstone; read reconciliation must account for deletion markers. |
| "Once a tombstone is GC'd, every replica knows about the delete." | A replica that missed the DELETE may keep old data, causing zombies. |
| "Equal timestamps mean the last request wins." | Tie-breaking is a deterministic internal rule, not network arrival order. |
| "LWT is just a regular UPDATE with an extra WHERE clause." | LWT uses Paxos for conditional mutations, distinct from regular writes. |
| "Raising CL fixes clock skew." | CL controls ACK counts; it does not alter mutation timestamps. |

## 14. Reasoning Exercises

**Q1.** A holds `status=NEW, ts=100` and B holds `status=PAID, ts=200`. Which value wins and why?  
*Guidance:* PAID wins because its timestamp is larger, regardless of request arrival order at each node.

**Q2.** At RF=3, a QUORUM write succeeds on A/B while C misses it. What can a `SELECT ONE` from C return?  
*Guidance:* The stale value; QUORUM success does not mean every replica was updated.

**Q3.** In the same row, A has `status ts=300` and B has `amount ts=400`. Can a read return both?  
*Guidance:* Yes, via per-cell reconciliation; business invariants must be designed accordingly.

**Q4.** A later UPDATE uses timestamp 1000, while an earlier UPDATE used timestamp 2000. Which UPDATE wins for the same cell?  
*Guidance:* The mutation with timestamp 2000.

**Q5.** Does DELETE `status` at `ts=500` shadow `status` at `ts=500`?  
*Guidance:* Yes, tombstones take precedence on matching timestamps/scopes.

**Q6.** Why can a WRITE with a future timestamp cause valid DELETEs to fail?  
*Guidance:* A DELETE with a lower timestamp cannot shadow a live cell carrying a higher timestamp.

**Q7.** Does a quorum read replace periodic repair when an app reads only 10% of partitions?  
*Guidance:* No; unread partitions can remain divergent.

**Q8.** A client wants to transition `NEW → PAID` only if no other worker already changed the state. What should it use?  
*Guidance:* Conditional update/LWT or a verified coordination/versioning mechanism.

**Q9.** Why can running repair after tombstones are purged create zombies?  
*Guidance:* High-timestamp deletion metadata is gone; a replica with stale data looks valid.

**Q10.** A Java service passes `System.currentTimeMillis()` directly into CQL `USING TIMESTAMP`. What is wrong?  
*Guidance:* Milliseconds differ from microseconds, distorting timestamp ordering and easily shadowing normal mutations.

## 15. Summary Diagram

~~~text
Multiple replicas receive mutations in different orders
                     |
                     v
           Cassandra read / repair
                     |
           Reconcile cell by cell
                     |
          Compare write timestamps
           /                    \
  Timestamps differ        Timestamps equal
  -> larger wins           -> internal tie-breaker
           \                    /
            \                  /
     Evaluate tombstones, TTL, and liveness
                     |
                     v
                Valid value
                     |
      Read repair / periodic repair
           help replicas converge

However:
  + CL does not fix clocks or bad timestamps.
  + Repair does not decide business correctness.
  + Early tombstone purge can resurrect old data.
  + LWT/Paxos is needed for conditional concurrent updates.
~~~

**Core principle:** Apache Cassandra's LWW is a **cell-level write-timestamp and tombstone reconciliation rule** that enables eventual replica convergence. It does not mean "last wall-clock request wins," does not replace read/write consistency guarantees, and does not replace anti-entropy repair. Understanding this helps Java applications choose appropriate timestamps, CLs, schemas, and update patterns for real distributed workloads.

## References

- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinators, replication, CL, hinted handoff, read repair, and reconciliation.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `USING TIMESTAMP`, `WRITETIME`, UPDATE/DELETE, TTL, and IF conditions.
- [Apache Cassandra — Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — replication strategies, keyspaces/tables, and `read_repair`.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, full/incremental repair, and primary ranges.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — `gc_grace_seconds`, zombie data, and compaction.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — memtables/SSTables, mutation timestamps, and compaction.
- [Apache Cassandra — Lightweight transactions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html#lightweight-transactions) — conditional writes, Paxos, and serial consistency.
