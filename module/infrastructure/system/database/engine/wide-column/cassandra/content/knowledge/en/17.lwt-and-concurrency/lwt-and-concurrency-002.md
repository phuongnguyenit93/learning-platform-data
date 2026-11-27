# IF NOT EXISTS, IF EXISTS, and Value-Based Conditions

## 1. Lesson Objectives and Context

In Apache Cassandra, regular `INSERT` and `UPDATE` are **upserts**: they can create or modify a row without checking whether the row already exists. That works well for high-volume write workloads in the **wide-column** model, but it can violate business rules when multiple clients contend on the same key—for example, two users registering the same username, two requests booking the same seat, or two threads updating the same document version.

This lesson belongs to the **LWT and Concurrency** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It focuses on three practical CQL conditional forms: **`INSERT ... IF NOT EXISTS`**, **`UPDATE/DELETE ... IF EXISTS`**, and **`UPDATE/DELETE ... IF column = value [AND ...]`**. These statements use Paxos-based **lightweight transactions (LWT)** to evaluate conditions and decide mutations within the appropriate scope.

After completing this lesson, you will be able to:

1. Choose accurately between **create if absent**, **modify if the row exists**, and **modify if state/revision still matches**.
2. Interpret `[applied]=True/False` results and distinguish them from timeouts or indeterminate errors.
3. Design a **partition key** around uniqueness/ownership rules; understand why LWT does not create unique constraints on arbitrary columns.
4. Practice with **two competing `cqlsh` sessions**, comparing `IF EXISTS` against `IF revision = ...`.
5. Use multiple `AND` conditions and distinguish the `WHERE` clause (row identification) from the `IF` clause (data condition).
6. Use the Apache Cassandra Java Driver with prepared statements, `ResultSet.wasApplied()`, consistency levels, and serial consistency.
7. Recognize key limitations: single partition, NULL, TTL, tombstones, counters, batches, timestamps, retries, and Paxos performance.
8. Explain how LWT relates to replication factor, `LOCAL_QUORUM`, `SERIAL/LOCAL_SERIAL`, repair, and Java client connectivity.

> **Lab scope:** the main examples use **Cassandra 5.0.9 on a dedicated single Docker node** to demonstrate syntax and client races. A single node **cannot test replica fault tolerance**; RF=3 quorum conclusions apply only when three real nodes belong to the ring. Do not run this lesson's delete statements against a production system.

## 2. Decision Table: Which IF Should You Choose?

| Requirement | CQL Statement | When Condition Holds | When Condition Fails |
|---|---|---|---|
| Create only when **primary key has no row yet** | `INSERT ... IF NOT EXISTS` | Creates row, `[applied]=true` | Does not write a new row, `[applied]=false` |
| Update only when **row already exists** | `UPDATE ... IF EXISTS` | Updates regardless of current row contents | Does not upsert missing row |
| Delete only when **row already exists** | `DELETE ... IF EXISTS` | Writes delete mutation | Does not delete missing row |
| Change only when **revision matches what was read** | `UPDATE ... IF revision=7` | Updates state and revision in one conditional mutation | Does not write, returns `false` |
| Change only when **multiple values all match** | `UPDATE ... IF state='FREE' AND revision=1` | All conditions must hold | Any single mismatch rejects the mutation |
| Delete only if **owner matches** | `DELETE ... IF owner_id='alice'` | Deletes only when owner matches | Does not delete another owner's data |

The most common misconception: **`IF EXISTS` does not mean "if the row is still in the state I expect."** It only checks existence. If both A and B update **the same existing row** using `IF EXISTS`, both mutations can still be accepted. To prevent lost updates, you must **compare values/versions**.

### 2.1. Three Standard Syntax Patterns

```sql
-- INSERT: only supports checking that the row does not exist.
INSERT INTO lwt002.claims
  (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
  ('tenant-a', 'skyblue', 'alice',
   20000000-0000-4000-8000-000000000001, 1, 'ACTIVE')
IF NOT EXISTS;

-- UPDATE: requires only that the row exists.
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED'
WHERE tenant_id='tenant-a' AND seat_id='seat-001'
IF EXISTS;

-- UPDATE: requires specific row state/version.
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-001'
IF state='FREE' AND revision=1;
```

These are **illustrative** statements—do not run them until you create the keyspace, schema, and seed data in the sections below. Table and key names are chosen so the tests are reproducible.

### 2.2. Do Not Confuse Schema IF with Mutation IF

An example DDL syntax is `CREATE TABLE IF NOT EXISTS ...`, where `...` is only a placeholder notation and **not a complete runnable statement**. The actual table creation statements are written in full in section 4.3.

`CREATE TABLE IF NOT EXISTS` is **DDL syntax**: it suppresses an error if the table already exists, but **does not run Paxos LWT to inspect rows**. It does not verify that an existing table has the expected primary key, compaction strategy, or schema. By contrast, `INSERT ... IF NOT EXISTS` on a data row is a **conditional mutation** returning `[applied]`.

## 3. Core Concepts to Keep Straight

### 3.1. WHERE and IF Do Two Different Jobs

```sql
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-002'
IF state='FREE' AND revision=1;
```

In this statement:

- `WHERE tenant_id=... AND seat_id=...` identifies the **exact row** via its primary key.
- `IF state='FREE' AND revision=1` evaluates **that row's values** at the moment CAS decides.
- `SET ...` is the mutation **applied only if the condition holds**.
- No separate Java `SELECT` guarantees that state remains unchanged between reading and writing. The check must live inside the conditional CQL statement.

With a composite partition key like `PRIMARY KEY ((tenant_id, seat_id))`, both components must appear in `WHERE` to locate the partition. The `IF` clause cannot make up for a missing key component. The columns checked in `IF` are **non-primary-key data columns**; the primary key identifies the row.

### 3.2. CAS Thinking Instead of SELECT-Then-UPDATE

```mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Cassandra/Paxos
    A->>C: UPDATE K SET owner=A IF revision=1
    B->>C: UPDATE K SET owner=B IF revision=1
    C-->>A: [applied]=true
    C-->>B: [applied]=false (revision already changed)
    Note over A,B: Example outcome; winning order can flip
```

There is no guarantee that Client A always wins. If B is decided first, **B can receive `true`**. What needs to be verified is that two conflicting conditional mutations **cannot both win** a single-use revision condition when no out-of-protocol writer breaks state.

### 3.3. The Partition Key Determines the Guarantee Scope

Example rule: within each tenant, a handle may be used by only one owner. Schema design:

```sql
PRIMARY KEY ((tenant_id, handle))
```

Each `tenant_id/handle` pair is checked within the same partition. If instead you create a table with `PRIMARY KEY (owner_id)` and make `handle` a regular column, two different owners can run `IF NOT EXISTS` on **two different partitions** and both succeed; the "unique handle" invariant is still violated.

**LWT does not automatically create a unique index across all partitions or tables.** Related data must be modeled around the specific invariant and query path. Tenant-wide aggregate quotas, multi-partition transactions, or side effects on external services require additional architecture.

## 4. Setting Up the Lab Environment

### 4.1. Starting a Dedicated Single-Node Cassandra Instance

You need Docker Engine/Desktop in Linux container mode, plus sufficient host CPU/SSD and RAM for Cassandra. A machine with roughly **8 GiB total RAM or more**, allocating 4 GiB to the container and 2 GiB to JVM heap, works well for this small lab; this is not a production sizing recommendation. Host port `9328` must be unused.

Run **on a host terminal with the Docker CLI**:

```bash
docker version
docker pull cassandra:5.0.9
docker network create lwt002-net
docker volume create lwt002_node_data

docker run -d --name cassandra-lwt002 --network lwt002-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=lwt002-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack1 -p 127.0.0.1:9328:9042 -v lwt002_node_data:/var/lib/cassandra cassandra:5.0.9
```

The container, network, and volume names are isolated to this lesson. If they already exist, **verify ownership and existing data before continuing**; do not delete or reuse data from another lab. Each Cassandra node must have its own volume.

Port `9328` is published only on the **host loopback interface** because this example does not enable authentication/TLS. Do not change it to `0.0.0.0:9328:9042` on a shared machine. From **inside the container**, CQL still uses port `9042`.

### 4.2. Waiting for Cassandra Readiness

```bash
docker ps -a --filter name=cassandra-lwt002
docker logs --tail 100 cassandra-lwt002
docker exec cassandra-lwt002 nodetool status
docker exec cassandra-lwt002 nodetool statusbinary
docker exec cassandra-lwt002 cqlsh -e "SELECT cluster_name, data_center, release_version FROM system.local WHERE key='local';"
```

Proceed only when:

1. `nodetool status` shows one `UN` (*Up/Normal*) node.
2. `nodetool statusbinary` returns `running`.
3. CQL reports `cluster_name=lwt002-lab`, `data_center=dc1`, and server `5.0.9`.

A container in `Up` status does not mean Cassandra has opened native transport yet. If a command fails during bootstrap, read the logs and check again; do not delete the volume to "fix" slow startup.

### 4.3. Keyspace and Two Tables Matching the Invariants

Open `cqlsh`:

```bash
docker exec -it cassandra-lwt002 cqlsh
```

At `cqlsh>`, run:

```sql
CREATE KEYSPACE IF NOT EXISTS lwt002
WITH replication = {'class':'NetworkTopologyStrategy', 'dc1':1};

-- Table 1: only one owner per (tenant, handle).
CREATE TABLE IF NOT EXISTS lwt002.claims (
    tenant_id text,
    handle text,
    owner_id text,
    request_id uuid,
    revision int,
    state text,
    PRIMARY KEY ((tenant_id, handle))
);

-- Table 2: reservation state and version per seat.
CREATE TABLE IF NOT EXISTS lwt002.seats (
    tenant_id text,
    seat_id text,
    holder_id text,
    state text,
    revision int,
    request_id uuid,
    PRIMARY KEY ((tenant_id, seat_id))
);

DESCRIBE KEYSPACE lwt002;
DESCRIBE TABLE lwt002.claims;
DESCRIBE TABLE lwt002.seats;
```

If the keyspace or tables already existed, `IF NOT EXISTS` may **leave the existing schema unchanged**. Run `DESCRIBE` to verify the primary keys. The lab uses `RF=1` because there is only one node; in a real cluster you must choose RF per topology and CLs per requirements.

### 4.4. Setting Regular and Serial Consistency in cqlsh

In every `cqlsh` session used to test LWT, configure:

```text
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;
```

These are **`cqlsh`-specific commands**, not CQL statements sent from the Java Driver. With RF=1, `LOCAL_QUORUM` requires only one replica; `SERIAL` sets the serial/Paxos scope for conditional mutations. When scaled to RF=3 in a single DC, `LOCAL_QUORUM` requires 2 out of 3 responses.

## 5. IF NOT EXISTS: Claim Only When the Row Does Not Exist

### 5.1. First Attempt Is Allowed to Create

On `lwt002.claims`, choose an unoccupied key pair:

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-a', 'skyblue-002', 'alice',
     20000000-0000-4000-8000-000000000011, 1, 'ACTIVE')
IF NOT EXISTS;
```

In a clean lab, `cqlsh` typically displays:

```text
 [applied]
-----------
      True
```

Read back the row:

```sql
SELECT tenant_id, handle, owner_id, request_id, revision, state
FROM lwt002.claims
WHERE tenant_id='tenant-a' AND handle='skyblue-002';
```

Expect owner `alice`, `revision=1`. A `True` result means **the existence condition passed and the mutation was applied according to LWT/CL semantics**; it is not a guarantee of backups, repair, or replication to non-existent nodes.

### 5.2. Another Client Using the Same Key Must Be Rejected

Open a **second `cqlsh` session**:

```bash
docker exec -it cassandra-lwt002 cqlsh
```

Set `CONSISTENCY LOCAL_QUORUM;` and `SERIAL CONSISTENCY SERIAL;` in the new session. Then run:

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-a', 'skyblue-002', 'bob',
     20000000-0000-4000-8000-000000000012, 1, 'ACTIVE')
IF NOT EXISTS;
```

Expect `[applied]=False`. Depending on the statement and Cassandra version, an unapplied result may include **some current column values** of the row. Do not rely on the exact formatting or column ordering of that returned row; run a `SELECT` by primary key when making business decisions.

```sql
SELECT owner_id, request_id, state
FROM lwt002.claims
WHERE tenant_id='tenant-a' AND handle='skyblue-002';
```

With no other writers in the lab, the owner remains `alice`. `False` is a **business conflict**, distinct from `WriteTimeout`/`Unavailable` or network errors.

### 5.3. Changing the Tenant Changes the Uniqueness Scope

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-b', 'skyblue-002', 'bob',
     20000000-0000-4000-8000-000000000013, 1, 'ACTIVE')
IF NOT EXISTS;
```

This is a **different partition**, so it can return `True`. If the business requires a handle to be unique **system-wide**, the table schema/key above is wrong. Changing the `IF` condition cannot fix an invariant placed on the wrong primary key.

### 5.4. Two Clients Sending Truly Concurrently

In the two-window sequential walk-through, A intentionally runs before B so the outcome is predictable. When two clients concurrently send `INSERT ... IF NOT EXISTS` for the same **new key**, **one** request can receive `True` and the other `False`, provided both finish normally with no intervening `DELETE` or TTL expiration.

There is no guarantee that Alice or Bob always wins. The count of **`True`** outcomes matters more than the client name. If one request times out, it may have committed even though the client never received the response; **do not** count a timeout as `False` and conclude that only one side wrote.

### 5.5. Claim Idempotency and request_id

In your application, generate `request_id` before the first attempt, keep it identical across retries, and store it alongside the owner. If the first attempt commits but the response is lost, a retry may receive `False` because **the row created by that exact request already exists**. In that situation:

- Read by the `tenant_id/handle` key.
- Compare `owner_id` and `request_id` against the original request.
- If they match, you can treat it as **your own request having already been applied**, per your designed business rules.
- If they differ, return **conflict**.
- If verification fails due to network/consistency errors, keep the state as **UNKNOWN** rather than permanently accepting or rejecting.

If a handle can be **deleted and reassigned** while retries are in flight, `request_id` alone may not be enough. Add generation/lease/fencing tokens or logical tombstone rules to prevent **ABA**.

## 6. IF EXISTS: Protects Existence Only, Not Values

### 6.1. UPDATE IF EXISTS When the Row Has Not Been Created

On a fresh seat `seat-exists-002`:

```sql
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

When the row does not exist, the result is `[applied]=False`. No new row is created. Unlike a regular `UPDATE`, conditional `IF EXISTS` **does not upsert a missing row**.

### 6.2. Create Fixture Data and Retry

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision, request_id)
VALUES
    ('tenant-a', 'seat-exists-002', 'unassigned', 'FREE', 1,
     20000000-0000-4000-8000-000000000021);

UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

Because the row now exists, `IF EXISTS` can return `True`. However, the statement **never checked `state='FREE'` or `revision=1`**.

### 6.3. Why Can IF EXISTS Still Cause Lost Updates?

Right after A sets the seat to `RESERVED`, Client B sends:

```sql
UPDATE lwt002.seats
SET holder_id='bob', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

The row still exists, so B **can also receive `True`**, even though Alice just booked it. Reading the result:

```sql
SELECT seat_id, holder_id, state, revision
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002';
```

In an isolated sequential test, the later write typically appears under Cassandra's mutation timestamp rules, but **do not rely on strict A/B ordering to prove the invariant**. What this proves is that **both `IF EXISTS` statements can be applied**. This is a misapplication of `IF`: it only guards *that a row exists*, not *that no one else has booked the seat yet*.

| Business Goal | Does `IF EXISTS` Guarantee It? | Better Condition |
|---|---|---|
| Avoid accidentally creating an uninitialized seat | **Yes** | `IF EXISTS` |
| Reserve only a seat that is currently FREE | **No** | `IF state='FREE'` |
| Avoid overwriting a revision just incremented by someone else | **No** | `IF revision=<expected>` |
| Allow only the rightful holder to confirm the seat | **No** | `IF holder_id=<expected> AND state='RESERVED'` |

### 6.4. DELETE IF EXISTS

To test **existence-conditional deletion** without affecting other seats, create a dedicated row:

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision)
VALUES
    ('tenant-a', 'seat-delete-002', 'alice', 'RESERVED', 1);

DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-delete-002'
IF EXISTS;

DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-delete-002'
IF EXISTS;
```

Expect the first `DELETE` to return `True` and the second `False` because the row is now absent. Yet `IF EXISTS` **does not check who the owner is**: any client with write permission can still delete someone else's row if the application relies solely on existence checks.

**Note on tombstones:** Cassandra uses tombstones to represent deletions, so "row vanishes from SELECT" does not mean SSTables/disk space are immediately reclaimed. Do not run mass `DELETE` loops to test disk usage; monitor compaction, repair, and `gc_grace_seconds` per operational runbooks.

## 7. Value-Based IF: State and Revision

### 7.1. Create a Dedicated Seat for Compare-and-Set

Do not reuse `seat-exists-002` from the faulty pattern above. Create a new row:

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision, request_id)
VALUES
    ('tenant-a', 'seat-cas-002', 'unassigned', 'FREE', 1,
     20000000-0000-4000-8000-000000000031);

SELECT holder_id, state, revision
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002';
```

Expect `unassigned / FREE / 1` initially. If the row already exists in a different state, do not assume a clean fixture; pick a new key or inspect the lab volume.

### 7.2. A Attempts to Hold the Seat If Both Conditions Still Hold

```sql
UPDATE lwt002.seats
SET holder_id='alice',
    state='RESERVED',
    revision=2,
    request_id=20000000-0000-4000-8000-000000000032
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='FREE' AND revision=1;
```

If the row is still `FREE` at revision 1, Cassandra performs the conditional mutation and returns `[applied]=True`. **The entire `SET` clause applies conditionally**; there is no need for a separate `SELECT` followed by hoping the state did not change.

### 7.3. B Uses the Same Stale Condition

```sql
UPDATE lwt002.seats
SET holder_id='bob',
    state='RESERVED',
    revision=2,
    request_id=20000000-0000-4000-8000-000000000033
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='FREE' AND revision=1;
```

Expect `[applied]=False` after A succeeded, because the row is now `RESERVED/2`. Verify:

```sql
SELECT holder_id, state, revision, request_id
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002';
```

In a real race, whichever client reaches the CAS decision phase first can win; **do not hardcode an assumption that Alice always wins**. Combining `state='FREE' AND revision=1` protects both the state machine and against lost updates.

### 7.4. Next State Transition Checking Owner and Revision

On the row now owned by Alice at revision 2, try:

```sql
UPDATE lwt002.seats
SET state='CONFIRMED', revision=3
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='RESERVED' AND holder_id='alice' AND revision=2;
```

If the row matches all three conditions, expect `True`. If B had won or the row had moved past revision 2, the statement returns `False` and **must never automatically drop the `IF` clause to force the transition**.

Important point about versioning: `revision` is an **application-managed data column**, not an automatic per-row version counter maintained by Cassandra. Any writer that omits `IF` or fails to increment `revision` properly can break the invariant, even while other writers use CAS.

### 7.5. Conditional DELETE Checking Values Before Deleting

Try a stale condition expected **not to delete**:

```sql
DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF holder_id='bob' AND revision=2;
```

If A already confirmed the row with `holder_id='alice'` and `revision=3`, the result is `False`. Only if you intend to **delete this specific lab record**, inspect the current row and use the matching condition:

```sql
DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF holder_id='alice' AND state='CONFIRMED' AND revision=3;
```

Do not treat conditional `DELETE` as a complete solution for a **booking with history, refunds, or transferred ownership**. Deleting and recreating rows can cause **ABA**; design `generation`, auditing, state transitions, and idempotency to match the real domain.

## 8. Conditional Syntax and Important Pitfalls

### 8.1. IF EXISTS Is One Branch; IF column... Is Another

For `UPDATE` and `DELETE`, CQL allows:

```text
IF EXISTS

or

IF column_a = value_a AND column_b = value_b [AND ...]
```

Within a single statement, **do not write**:

```sql
-- Invalid idea/syntax; do not run:
UPDATE lwt002.seats
SET state='CONFIRMED'
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF EXISTS AND revision=2;
```

When you need to ensure both that the row exists **and** that its values match, conditioning on an **explicitly designed non-NULL value** such as `revision=2` is usually appropriate. Note, however, that in certain cases `IF column = null` on a missing row can have semantics that **create a row** when the NULL condition evaluates true; **do not use `IF col = null` as an alias for `IF EXISTS`**. Use a non-NULL state/revision or a proper existence design if the invariant requires both.

### 8.2. WHERE Must Specify the Primary Key, Not Arbitrary Filters

```sql
-- Valid: row is identified by the full composite partition key.
UPDATE lwt002.seats
SET state='RESERVED'
WHERE tenant_id='tenant-a' AND seat_id='seat-009'
IF state='FREE';

-- Invalid when seat_id is missing: no specific row to CAS.
UPDATE lwt002.seats
SET state='RESERVED'
WHERE tenant_id='tenant-a'
IF state='FREE';
```

Statements with `IF` do not turn Cassandra into a full-table search engine. If the business workflow needs to "find any seat that is still FREE," you need a **query-driven candidate lookup table/flow**, followed by CAS on a **specific seat key**.

### 8.3. Value-Based IF Supports Multiple Comparisons, Not Arbitrary SQL WHERE

For regular columns, Cassandra permits conditional comparisons according to CQL syntax and version—for example equality (`=`) and comparison operators supported by the column type. Nevertheless, this lesson favors **equality on state/revision** because correctness under concurrency is easier to reason about:

```sql
-- Easy-to-review compare-and-set pattern:
UPDATE lwt002.seats
SET revision=4
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF revision=3;
```

Do not put Java expressions, subqueries, joins, complex `OR`s, or arbitrary functions into `IF` assuming Cassandra supports them. Some collection/UDT types have specialized conditional syntax and restrictions; check **documentation for your exact server version** before using them. Conditions on **primary key** columns do not replace the role of `WHERE`.

### 8.4. NULL, Missing Columns, and Non-Existent Rows Differ

Cases you must distinguish:

| State | Example | What to Check |
|---|---|---|
| Row **does not exist** | No `seat_id='seat-100'` | `IF EXISTS` must return false |
| Row exists, a column has **no value** | `holder_id=null` on a FREE seat | `IF holder_id=null` has its own semantics, unlike `IF EXISTS` |
| Row exists, state uses a sentinel value | `holder_id='unassigned'` | CAS can compare an explicit value cleanly, easy to test |
| Row was DELETEd or TTL expired | Row is no longer live data in Cassandra | Existence/condition outcomes depend on row liveness at CAS time |

In Cassandra, `NULL` generally corresponds to deletion/absence of a cell value rather than a concrete value like zero. A condition like `IF col = null` can evaluate **true even when the row does not exist yet**, causing a conditional `UPDATE` to create a row; test on your exact server version if you use it. To protect a "modify only initialized rows" workflow, use `IF EXISTS` or explicitly initialized non-null state/revision values.

### 8.5. Conditional Mutations Cannot Accept Arbitrary Write Timestamps

**Do not** write:

```sql
-- Invalid for conditional INSERT/LWT:
INSERT INTO lwt002.claims (tenant_id, handle, owner_id)
VALUES ('tenant-a', 'bad-timestamp', 'alice')
IF NOT EXISTS
USING TIMESTAMP 1700000000000000;
```

In Cassandra, **conditional updates reject client-provided `USING TIMESTAMP`** because the CAS protocol controls mutation timestamps and condition evaluation. Never try to force timestamps to win races. If the business needs an event time, store it in a **separate timestamp column** and let CAS decide conditions on state/revision as designed.

Similarly, `TTL` can expire rows/cells and allow a claim to be re-acquired after some period. Do not use `TTL` as a **distributed lock/lease** without handling clocks, timeouts, ABA, owner states, and fencing tokens.

### 8.6. Do Not Treat LWT as a Universal Primitive for Every Table or Type

- **Counter tables** do not support normal conditional mutations like regular-column tables; do not try to combine `IF` with counter updates.
- **Conditional batches** are strictly constrained to **single-partition scope** (plus statement/table restrictions depending on Cassandra version), not SQL-style multi-partition transactions.
- **CQL batches** do not allow putting a `SELECT` in the middle to make a decision before `UPDATE`. A batch does not turn client-side read-check-write into a serializable transaction.
- Do not rely on LWT to enforce uniqueness across multiple tables or coordinate external side effects atomically.

## 9. Interpreting the [applied] Result Accurately

### 9.1. Applied vs. Unsatisfied Condition Outcomes

For `INSERT ... IF NOT EXISTS` or `UPDATE/DELETE ... IF ...`, Cassandra returns a result row containing the **`[applied]`** column.

```text
-- When the condition holds:
 [applied]
-----------
      True

-- When the condition fails:
 [applied] | ... current values (if returned by the server) ...
-----------+---------------------------------------------------
     False | ...
```

In the `False` case, **no mutation was applied by that conditional statement**. The exact set of accompanying columns in a failed result can depend on the statement and Cassandra version; data may already change immediately after the response arrives if another writer continues running. Never treat the returned row as **a locked snapshot** for subsequent decisions.

### 9.2. Timeout Does Not Mean applied=false

```text
Client sends CAS ----> Coordinator / Paxos replicas
                             |
                         Decision may be accepted
                             |
           response lost / request times out
                             X
Client receives exception, uncertain of final state.
```

| Outcome Seen by Client | Do We Know Whether Condition Held? | Application Action |
|---|---|---|
| `[applied]=True` | Yes, CAS applied per server response | Return success, record request ID/log |
| `[applied]=False` | Yes, condition was not met | Return conflict, or re-read state and make a new decision |
| Timeout/connection loss | **Uncertain** | Mark UNKNOWN, inspect row at appropriate CL, compare `request_id` |
| Query/schema error | No valid CAS outcome | Fix CQL/schema; never drop `IF` to "make it pass" |

If a claim times out, retrying the same `IF NOT EXISTS` may return `False` because **your own first attempt already committed**. Storing `request_id` in the row gives the application evidence to recognize its own request within design boundaries. If items/bookings can be deleted and reused, handle lifecycle/generations as well.

### 9.3. Do Not Confuse cqlsh Response with Affected Row Count

`[applied]=True` **does not report how many physical replicas were written**, is not a `SELECT` row count, and does not indicate operation duration. For LWT requests, record both the condition and consistency levels in test logs when comparing runs.

## 10. Regular Consistency and Serial Consistency

### 10.1. Two Controls That Must Be Configured Separately

```text
cqlsh> CONSISTENCY LOCAL_QUORUM;
cqlsh> SERIAL CONSISTENCY SERIAL;
```

- **Regular CL** (e.g., `LOCAL_QUORUM`) governs the commit/learn response phase of the mutation and regular requests.
- **Serial CL** (`SERIAL` or `LOCAL_SERIAL`) governs the Paxos phase scope of **conditional mutations**.
- In a single-DC RF=3 keyspace, `LOCAL_QUORUM` requires 2 replicas to respond. In our RF=1 lab it only needs one replica.
- `SERIAL` spans replicas across Cassandra's consensus scope; `LOCAL_SERIAL` restricts the serial phase to the **local datacenter**. When multiple DCs and clients across regions contend on the same invariant, choosing local serial while expecting a cluster-wide order may be inappropriate.

**Do not set `CONSISTENCY SERIAL` as a substitute for the regular commit consistency of a conditional write**; use `SERIAL CONSISTENCY ...` for the serial phase. In the Java Driver, set `setConsistencyLevel(...)` and `setSerialConsistencyLevel(...)` separately.

### 10.2. Quorum Overlap Alone Does Not Create CAS

Suppose RF=3:

```text
Request 1: SELECT at LOCAL_QUORUM -> state=FREE
Request 2: SELECT at LOCAL_QUORUM -> state=FREE
Request 1: regular UPDATE at LOCAL_QUORUM -> state=RESERVED
Request 2: regular UPDATE at LOCAL_QUORUM -> state=RESERVED
```

Both regular `UPDATE`s can still succeed. Quorum reads and writes **do not lock a row across two statements**. It is the `IF state='FREE' AND revision=1` clause that performs CAS to accept only one mutation against the initial state.

### 10.3. When Nodes Go Down

| RF=3, Single-DC Scenario | Regular `LOCAL_ONE` | Regular `LOCAL_QUORUM` | LWT Requiring Serial Quorum |
|---|---|---|---|
| All 3 nodes healthy | Can serve | Can serve | Can serve if responses arrive / contention isn't excessive |
| 1 node down, 2 nodes healthy | Can serve | Can serve | Can serve **if Paxos quorum and regular CL are met** |
| 2 nodes down, 1 node healthy | `ONE` requests may work | Insufficient for 2 replicas | Insufficient consensus quorum in typical setups |

This is a **replica-requirement table**, not an absolute guarantee. Latency, network partitions, disk/GC stalls, and failure detectors can still time out requests even when enough nodes are up. LWT uses Paxos and costs noticeably more than regular mutations; measure contention and keep invariant scopes tight.

## 11. Java Driver: Prepared Statements, Conditions, and Result Handling

### 11.1. Preparing the Right Java Environment

The examples below use **Java 17** and **Apache Cassandra Java Driver 4.x** (e.g., Maven `org.apache.cassandra:java-driver-core:4.19.4`). In the lab, Java can run from:

| Where Java Runs | Contact Point | Requirements |
|---|---|---|
| Host where Docker publishes port | `127.0.0.1:9328` | Host port mapped, metadata/routing reachable |
| Java container on `lwt002-net` | `cassandra-lwt002:9042` | Container name resolved via Docker DNS |
| Another machine | Routable IP/DNS to Cassandra | Auth/TLS/firewall/broadcast RPC per policy |

**Do not hardcode production addresses or passwords in Java source.** The example below reads host, port, DC, and expected cluster name from environment variables; the lab server does not enable auth/TLS. In real deployments, use least-privilege credentials/roles and verify TLS.

### 11.2. Complete Java Example: Claim If Absent

```java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class ClaimIfAbsent {
    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = required("CASSANDRA_HOST");
        int port = Integer.parseInt(required("CASSANDRA_PORT"));
        String dc = required("CASSANDRA_LOCAL_DC");
        String expectedCluster = required("EXPECTED_CLUSTER");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, port))
                .withLocalDatacenter(dc)
                .build()) {
            Row identity = session.execute(
                "SELECT cluster_name, data_center FROM system.local WHERE key='local'")
                .one();
            if (identity == null
                    || !expectedCluster.equals(identity.getString("cluster_name"))
                    || !dc.equals(identity.getString("data_center"))) {
                throw new IllegalStateException("Connected to wrong Cassandra cluster/DC");
            }

            PreparedStatement insert = session.prepare(
                "INSERT INTO lwt002.claims " +
                "(tenant_id, handle, owner_id, request_id, revision, state) " +
                "VALUES (?, ?, ?, ?, 1, 'ACTIVE') IF NOT EXISTS");

            UUID requestId = UUID.randomUUID();
            BoundStatement stmt = insert.bind(
                    "tenant-a", "java-claim-002", "java-alice", requestId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

            ResultSet result = session.execute(stmt);
            if (result.wasApplied()) {
                System.out.println("CLAIM_OK request_id=" + requestId);
            } else {
                System.out.println("CLAIM_NOT_APPLIED: inspect current owner/request_id");
            }
        }
    }
}
```

The program expects these environment variables when **running on the host**:

```text
CASSANDRA_HOST=127.0.0.1
CASSANDRA_PORT=9328
CASSANDRA_LOCAL_DC=dc1
EXPECTED_CLUSTER=lwt002-lab
```

On the first run with a fresh handle, expect `CLAIM_OK`. On the second run with the same handle, expect `CLAIM_NOT_APPLIED` — **that is a valid result**, not evidence that the driver failed to connect.

**Note:** `ResultSet.wasApplied()` is the API for reading conditional mutation outcomes; in Java Driver 4, it also returns `true` for **statements without `IF`** because those statements have no `[applied]` column. Therefore, **never call `wasApplied()` on a regular `INSERT` to infer "a new row was created."**

### 11.3. Prepared UPDATE Checking Revision

Java snippet for an existing row in the `seats` table:

```java
PreparedStatement casUpdate = session.prepare(
    "UPDATE lwt002.seats SET holder_id=?, state=?, revision=? " +
    "WHERE tenant_id=? AND seat_id=? " +
    "IF state=? AND revision=?");

BoundStatement bound = casUpdate.bind(
        "java-alice", "RESERVED", 2,
        "tenant-a", "seat-cas-002",
        "FREE", 1)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

ResultSet rs = session.execute(bound);
boolean applied = rs.wasApplied();
if (!applied) {
    // Conditional conflict; inspect the current state before deciding.
}
```

This is an **excerpt for use inside a method that already has `session`**, not a standalone Java class. Under concurrent requests, **reuse `CqlSession` and `PreparedStatement`**, while creating a bound statement with explicit parameters and CLs per request.

**Do not assume a prepared statement is automatically transactional** if its CQL lacks `IF`. Likewise, do not blindly attach `setIdempotent(true)` and auto-retry every LWT on timeout: the condition may already have been accepted and external business side effects may not be idempotent.

### 11.4. Classifying Results in the API

| Condition | Java Handling | Application Behavior |
|---|---|---|
| `wasApplied() == true` | CAS success | Return success, record request ID |
| `wasApplied() == false` | Business conflict | Optionally read row and return HTTP 409 if true conflict |
| Request timeout/exception | Unknown/technical failure | Log, bounded retry, reconcile business key and request ID |
| Wrong cluster/DC or schema | Configuration failure | **Fail closed**, never write to an unidentified cluster |

In Cassandra, **exceptions cannot safely be replaced with `false`**. If a request decided and succeeded while the response was lost, a retry may receive `false` because the row from the first attempt already exists.

## 12. BATCH, Counters, and Atomicity: Limitations

### 12.1. When Should Conditions Not Be Combined into a Batch?

Cassandra LWT operates at **partition** scope. Conditional mutations inside a `BATCH` are tightly scoped, and **you cannot use a conditional batch across multiple independent partitions** to get SQL transactions. For example, attempting to claim two handles at once:

```text
Handle A → partition K1
Handle B → partition K2
```

You cannot simply "put two `INSERT IF NOT EXISTS` statements into a `BATCH`" and expect **atomic check-and-commit across two partitions**. Either design a shared aggregate key if appropriate, or use a different transaction/coordinator architecture with the required guarantees.

In addition, **conditional batches disallow custom timestamps**, and counter/collection operations carry their own restrictions; consult docs for your exact version if you genuinely need multiple conditional mutations within one partition.

### 12.2. LWT Does Not Replace Authorization and Durability

A role with `MODIFY` privileges can still execute a regular `UPDATE` if the application or operations team allows it, breaking the invariant other clients protect with CAS. You must:

- Ensure **every write path** follows the appropriate CAS rules.
- Grant least-privilege `SELECT`/`MODIFY` permissions and verify `CassandraAuthorizer` is actually enabled.
- Enforce TLS/secret management and audit logging; never use a superuser account for applications.
- Maintain replication, repair, snapshots/backups, and monitoring in production. **LWT is not a backup** and does not protect against accidental deletes by authorized users.

### 12.3. When Not to Use LWT

| Workload | Should Every Write Use LWT? | Reason |
|---|---|---|
| Claim unique username/resource | **Usually suitable** | Needs CAS on a specific key |
| State transition with revision | **Suitable** | Prevents lost updates on an aggregate |
| Append-only telemetry events | **Usually no** | Regular writes by partition/time bucket are far more efficient |
| View/metric counters | **Not by default** | Counters have distinct semantics; avoid LWT on counters |
| Total quota across many partitions | **Not directly** | Invariant must be moved to a different synchronization scope |
| Payment + sending email + CQL | **Insufficient** | Needs outbox/saga/idempotency for external side effects |

## 13. Performance, Contention, and Operational Observability

### 13.1. Why Is IF More Expensive Than Regular Writes?

Regular writes send mutations to replicas according to regular CL. LWT must use **Paxos** so replicas coordinate on state/proposals and agree on the mutation. This adds network round trips and can trigger contention when many writers target the same partition.

Never state a fixed rule like "LWT is always N times slower": latency depends on RF, DC count, network, JVM/GC, I/O, contention, timeouts, and Cassandra version optimizations.

### 13.2. Metrics to Track

| Metric | Why It Matters |
|---|---|
| LWT attempts/s | Total rate of conditional operations |
| `applied=true` / `applied=false` | Separates successes from legitimate conflicts |
| Timeouts/unknown | Operations with uncertain outcome affecting retries |
| CAS p50/p95/p99 latency | Shows Paxos coordination cost and tail latency |
| Retry attempts/backoff | Prevents retry storms on hot keys |
| Top contended partition keys (sensitive data redacted) | Identifies hot keys needing redesign |
| RF, regular/serial CL, host/DC | Explains availability and latency behavior |
| Node logs, GC/disk/compaction/hints/repair | Distinguishes business races from infra degradation |

Lab diagnostic commands:

```bash
docker exec cassandra-lwt002 nodetool status
docker exec cassandra-lwt002 nodetool statusbinary
docker exec cassandra-lwt002 nodetool tpstats
docker exec cassandra-lwt002 nodetool compactionstats
docker logs --tail 100 cassandra-lwt002
```

These commands **do not automatically count the application's `[applied]` true/false results**. To measure those, instrument your Java/`cqlsh` test harness, tag `request_id`, and collect client-side histograms; supplement with server metrics for your exact Cassandra version.

## 14. Common Errors and How to Fix Them

| Symptom | Likely Cause | How to Isolate |
|---|---|---|
| First `INSERT IF NOT EXISTS` already returns `False` | Row already exists, stale volume, or another client won | SELECT by exact primary key; compare `owner_id`/`request_id` |
| `UPDATE IF EXISTS` returns `True` for two users | Only checks row existence, not revision/state | Replace with `IF state='FREE' AND revision=<expected>` |
| `UPDATE IF revision=1` returns `False` | Row already changed or revision was uninitialized | SELECT row/revision and handle conflict |
| `IF EXISTS AND revision=...` fails | Invalid combination of two syntax branches | Use `IF EXISTS` **or** `IF revision=...` |
| Condition fails to find expected row | Missing/wrong primary key in WHERE, wrong tenant/DC/keyspace | Check `DESCRIBE TABLE`, `system.local`, and keys |
| `IF col=null` creates row unexpectedly | NULL comparison has different semantics from existence | Use non-null state/revision or `IF EXISTS` when row must exist |
| Deleted rows still leave disk usage high | Tombstones/SSTables/compaction have not reclaimed yet | Check `tablestats`, `compactionstats`; never delete SSTable files |
| Conditional mutation fails with custom timestamp | LWT forbids `USING TIMESTAMP` | Remove custom timestamp; store event time in a separate column |
| Multi-partition conditional batch rejected | Paxos scope does not support cross-partition transactions | Redesign aggregate/transaction boundary |
| Counter table + `IF` errors | Counters do not support this conditional mutation style | Use a different table model/primitive |
| Client sees `False` after retrying a timeout | Prior attempt may have committed | Reconcile via `request_id`/owner/state; don't assume another user won |
| Java `wasApplied()` returns `true` for regular INSERT | API does not indicate new row creation for non-conditional statements | Interpret only for CQL with `IF` |
| `SERIAL`/`LOCAL_SERIAL` behaves unexpectedly | Regular vs. serial CL confused, or insufficient replicas | Verify `cqlsh`/driver settings, RF/DC, and ring |
| Java reaches contact point but fails peers | Docker broadcast RPC/IP unroutable from where app runs | Check network, local DC, driver logs |
| LWT is too slow | Hot partition, Paxos contention, network/GC/disk | Measure p95/p99, retries, key distribution; reduce contention |
| Uniqueness rule still broken | Regular writer exists or key normalization is inconsistent | Audit all write paths, key canonicalization, and RBAC |

**Effective triage order:** confirm the **invariant** → inspect `PRIMARY KEY` → verify CQL uses `IF` with the right condition → distinguish `[applied]` from exceptions → check regular/serial CL → check ring/network → analyze latency/metrics. Never replace a failing CAS statement with a regular write just to "make it pass."

## 15. Advanced Scenarios

### 15.1. "Row Exists" Does Not Mean "Right State"

Suppose an application tracks seat availability with states `FREE`, `RESERVED`, `CONFIRMED`, `CANCELLED`. If every transition used `IF EXISTS`, any existing row could jump states out of order. Build a **state machine**:

```text
FREE --IF state='FREE' AND rev=n--> RESERVED
RESERVED --IF holder=owner AND rev=n+1--> CONFIRMED
RESERVED --IF holder=owner AND rev=n+1--> CANCELLED
CONFIRMED --disallow transitioning back to FREE without refund/cancel rules
```

In practice, every transition should increment `revision` and record corresponding events/audits. Do not assume CAS on `state` alone suffices for every business flow.

### 15.2. IF NOT EXISTS Enforces Uniqueness on the **Primary Key**, Not Any Arbitrary Field

A table `users_by_id(user_id PRIMARY KEY, handle text)` only allows existence CAS by `user_id`. To make `handle` unique per tenant, you need a table `claims_by_handle(tenant_id, handle PRIMARY KEY, owner_id...)` with the proper key plus a process linking user and claim. When user data lives in another table, updating both tables can partially fail; you need sagas/compensation/reconciliation or a data model built for the requirement—never label single-row LWT as "multi-table atomic."

### 15.3. TTL Expiration or DELETE Followed by Re-Registration: ABA

```text
t0: handle K does not exist
t1: Alice INSERT IF NOT EXISTS → true (generation 1)
t2: Alice releases K (DELETE/TTL)
t3: Bob INSERT IF NOT EXISTS → true (generation 2)
t4: Alice's old retry arrives / delayed response arrives
```

The application must distinguish **current ownership** from **stale requests**. Storing `request_id` in the current row helps, but once the row is deleted it no longer retains full history. For sensitive invariants, design generations/fencing, hold periods, logical tombstone states, and an appropriate idempotency store.

### 15.4. Multiple Datacenters and Local Serial

If clients in DC A and DC B can both claim a global key, evaluate replication/topology and serial consistency scope. `LOCAL_SERIAL` only guarantees the serial phase within the local DC; for invariants that must stay consistent across multiple DCs, consider `SERIAL` and test multi-DC failures/races per official guidance. Trade-offs typically include **higher WAN latency** and sensitivity to DC outages. Never infer from a single-DC RF=1 lab that a global design is sound.

## 16. Checklist and Exercises

### 16.1. Lab Verification Checklist

| Item | PASS Evidence |
|---|---|
| Cluster readiness | `lwt002-lab`, `dc1`, one `UN` node, `statusbinary=running` |
| CQL schema | `claims` and `seats` have the right composite partition keys |
| First `IF NOT EXISTS` | `tenant-a/skyblue-002` returns `True` |
| `IF NOT EXISTS` on same key | Different owner retry returns `False`; row keeps original owner |
| Different tenant | Same handle under `tenant-b` can return `True` |
| `IF EXISTS` on missing row | Uncreated `seat-exists-002` returns `False` |
| `IF EXISTS` on existing row | Two updates from different owners can both return `True` |
| `IF state AND revision` | `seat-cas-002` A wins, B with stale revision gets `False` |
| Conditional `DELETE` | Deletes lab row when conditions match; subsequent `IF EXISTS` returns `False` |
| Java Driver | Uses prepared `IF NOT EXISTS` and interprets `wasApplied()` accurately |
| Timeout/retry | Separates conflict from UNKNOWN; has a `request_id` reconciliation plan |

### 16.2. Self-Check Questions

1. Why can a regular `INSERT` create or update a row, whereas `INSERT IF NOT EXISTS` can return `False`?
2. Does `IF NOT EXISTS` enforce uniqueness on the **primary key or on the `owner_id` column**?
3. In the claims table, why don't `tenant-a/skyblue-002` and `tenant-b/skyblue-002` contend on the same partition?
4. Two clients both run `UPDATE ... IF EXISTS` on an existing seat. Can both receive `True`? Why?
5. What does `UPDATE ... IF state='FREE' AND revision=1` protect that `IF EXISTS` does not?
6. When B receives `[applied]=False` after A bumped the revision, should B keep retrying with the same revision?
7. Why must `WHERE` contain the full primary key while `IF` contains only the values being checked?
8. Is `IF EXISTS AND revision=2` valid syntax? If not, write the correct CAS statement.
9. How does a NULL comparison differ from an existence test? Why can `IF col=null` be dangerous when a row does not exist yet?
10. Why do conditional mutations disallow custom `USING TIMESTAMP`?
11. Why must `SERIAL CONSISTENCY SERIAL` and `CONSISTENCY LOCAL_QUORUM` be understood as two distinct phases?
12. A request times out, and a retry of `IF NOT EXISTS` receives `False`. Can you conclude someone else claimed the key?
13. Why is a batch containing two conditional mutations on two partitions **not** equivalent to a SQL transaction?
14. What does Java Driver `wasApplied()` return on a regular `INSERT` without `IF`, and why must you not use it to detect row creation?
15. What additional checks are required when moving from a single-node RF=1 lab to a multi-datacenter RF=3 cluster?
16. Why does LWT not replace backups, repair, authentication/authorization, or monitoring?

**Completion criteria:** the learner can run `IF NOT EXISTS`, `IF EXISTS`, `IF state/revision`, and conditional `DELETE` tests on lab data; read `[applied]` accurately; explain why `IF EXISTS` does not prevent lost updates; describe regular vs. serial CL, UNKNOWN timeouts, and partition-scoped Paxos limits separately; and use the Java Driver with clear CAS result classification.

## 17. Cleaning Up the Lab Safely

If you want to stop the container while **keeping the data** for the next LWT lesson:

```bash
docker stop cassandra-lwt002
docker volume inspect lwt002_node_data
```

If you want to remove the **container** while keeping the named volume:

```bash
docker rm cassandra-lwt002
docker network rm lwt002-net
docker volume ls
```

If the container is still running, `docker rm` may fail; run `docker stop` first. **Never** run `docker volume rm` or `docker volume prune` while you still need the data. Recreating a node with existing data requires matching identity/compatible settings; scaling to multiple nodes also requires managing broadcast/IP addresses and tokens per runbook.

**All `DELETE`/`UPDATE` commands in this lesson apply only to the lab keyspace `lwt002`**. Never run contention experiments or delete live user records in production.

## 18. Official References

- [Apache Cassandra 5.0 — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE/DELETE IF EXISTS`, `IF condition AND ...`, Paxos, and `BATCH` syntax.
- [Apache Cassandra — CQL Language Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): data types, `PRIMARY KEY`, and schema constraints.
- [Apache Cassandra — Guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html): atomicity/isolation scope and linearizability of LWT.
- [Apache Cassandra — Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replicas, coordinators, and quorum/consistency levels.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY`, `SERIAL CONSISTENCY`, and running CQL.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): binding, prepared statements, and execution parameters.
- [Apache Cassandra Java Driver 4.19 — ResultSet](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): `wasApplied()` semantics for conditional vs. non-conditional statements.
- [Apache Cassandra Java Driver 4.19 — Statement](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): regular and serial consistency on statements.
- [Docker Hub — Cassandra Official Image](https://hub.docker.com/_/cassandra): running containers, configuration environment variables, and volume storage.
