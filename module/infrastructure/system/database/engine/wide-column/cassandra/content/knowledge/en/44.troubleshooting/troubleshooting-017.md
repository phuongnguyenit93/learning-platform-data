# Deleted Data Reappearing or Unexpected TTL Behavior

> **Chapter:** Troubleshooting  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Diagnosing tombstones, TTL, timestamps, `gc_grace_seconds`, replicas missing deletes, repairs, compaction, and Java read/write paths in Apache Cassandra.

## 1. Opening Scenario: `DELETE` Executed Yet the API Still Sees Data

Operations receives three seemingly similar incident reports:

- **Report A:** An order was `DELETE`d on Monday. After a Cassandra node returned from a multi-day outage, some queries started reading the old order again.
- **Report B:** A session was `INSERT`ed with a 120-second TTL. Two minutes later, the API still returns the session row even though the **state** column is gone.
- **Report C:** A row was `DELETE`d at 10:00, disappeared from `SELECT`, then reappeared at 10:03—while all replicas stayed healthy with zero repair running.

Never immediately lump all three together as "Cassandra failed to delete". They likely have **three completely distinct causes**:

1. **Zombie data:** Tombstones suppressed the older row until compaction purged them before a replica holding old data received the delete.
2. **Per-cell TTL:** Certain columns carried a TTL and expired while other columns (or row liveness) lacked that TTL, so `SELECT` still returns a row.
3. **New write/timestamp or alternate read source:** A writer re-created the row after `DELETE`, a mutation arrived with a higher write timestamp than the tombstone, or a cache/materialized view/denormalized table stayed out of sync.

Resolving this requires tracing the **partition key, deleted columns, mutation timestamps, TTL at write time, consistency level, RF/DC topology, replica downtime, and tombstone age**. Checking a single `SELECT` or seeing "delete succeeded" in app logs is never enough.

### Learning Outcomes

After this lesson, you can:

1. Explain **tombstones, `gc_grace_seconds`, TTL, compaction, repair**, and the exact conditions creating zombie data.
2. Distinguish **logical `DELETE`**, **TTL expiration**, **tombstone purge**, and **overwrites with newer timestamps**.
3. Use CQL **`TTL(column)`**, **`WRITETIME(column)`**, schema metadata, and partition-key queries to investigate.
4. Understand **per-cell TTL**, table **`default_time_to_live`**, un-updated columns, and writes that reset or clear TTL.
5. Follow a diagnostic runbook for resurrected data without destroying forensic evidence or overloading disks.
6. Correlate Cassandra node logs, repair/compaction history, and Java Driver telemetry.
7. Design lab tests for TTLs, delete–reinsert races, replica downtime, and consistency-level read behavior.
8. Make disciplined **PAUSE / STOP / RESTORE / RECONCILE** calls whenever data integrity or privacy is at risk.

> **Safety:** Never slash `gc_grace_seconds`, launch blind full repairs, force compaction, change RF/DC, kill nodes, or wipe production data to reproduce bugs. Such actions require version-verified review, runbooks, backups, and change approvals. CQL examples belong strictly in labs or staging with synthetic data.

## 2. Four Distinct Stages in the Data Lifecycle

~~~mermaid
flowchart LR
    A["Write data"] --> B["DELETE or TTL expires"]
    B --> C["Tombstones / expired cells evaluated on reads"]
    C --> D["Replicas sync and run repair"]
    D --> E["Compaction may purge when safe"]
~~~

**T1 — Write:** Cassandra records mutations alongside write timestamps, liveness info, and optional TTLs, distributing them across replicas by partition key and replication strategy.

**T2 — Logical deletion:** On `DELETE`, Cassandra writes a **tombstone** carrying a timestamp so replicas know older values are dead. On TTL writes, the cell **expires at a timestamp fixed at write time**; expiration becomes logically effective before SSTable files change on disk.

**T3 — Replica synchronization:** Replicas can diverge temporarily during outages, network splits, or low-CL operations. Scheduled repairs and convergence mechanisms reconcile them.

**T4 — Purge:** Once grace periods pass and compaction confirms safety prerequisites, obsolete cells and tombstones can be dropped during SSTable compaction. **`gc_grace_seconds` is not an exact deletion timer**, and compaction is not a business transaction.

### 2.1. Tombstones Are Not Proof Cassandra Failed to Delete

Tombstones preserve delete correctness across replicas. If Replica A receives a `DELETE` while B sits `DOWN`, A must retain the delete marker long enough so returning Replica B cannot resurrect stale data.

Tombstones do carry cost: scanning numerous dead/expired cells alongside uncompacted SSTables drives up **read p99 latency**. The objective is never "purge all tombstones instantly", but rather **preserving safe grace windows, synchronizing replicas cleanly, and controlling tombstone volume**.

### 2.2. TTL Expiration Does Not Free Disk Immediately

Once a TTL expires:

- The cell stops returning as live data in queries.
- Underlying SSTables still physically store the record and expiration/tombstone metadata.
- Free filesystem bytes will not jump right when TTL crosses zero.
- Compaction reclaims expired data later once safety criteria hold.
- Mass simultaneous expirations create **tombstone read pressure**, especially on TTL-heavy tables or TWCS misalignments.

Never cite **unchanged disk usage** as proof TTL is broken; inspect query visibility, `TTL()`, and `WRITETIME()` metadata instead.

## 3. Write Timestamps Decide Which Value Wins

Cassandra resolves competing mutations using write timestamps (microseconds in standard CQL/APIs). A `DELETE` carries a timestamp; a subsequent `INSERT`/`UPDATE` carrying a higher timestamp legitimately **re-creates** the row. That is normal LWW behavior—not replica zombie resurrection.

~~~text
T0: INSERT order K, state='OPEN', timestamp=100
T1: DELETE order K, timestamp=200
T2: SELECT order K -> absent

T3: INSERT order K, state='OPEN', timestamp=300
T4: SELECT order K -> returns row

This obeys timestamp rules cleanly: write at 300 beats delete at 200.
~~~

### 3.1. "Executed Later" Does Not Guarantee a Higher Timestamp

Suppose Java code supplies explicit timestamps or hosts suffer clock skew:

~~~text
Initial write: timestamp=500
Later DELETE:  timestamp=400

Result: value at timestamp 500 still beats tombstone at 400.
~~~

Wall-clock sequence from a user's perspective differs from Cassandra's **write timestamp**. Clock skew, manual `USING TIMESTAMP`, replays, or backfills invert expected ordering easily.

**Never "fix" this by picking giant future timestamps.** A future timestamp blocks legitimate updates indefinitely. Fix clock sync, timestamp sources, and versioning contracts—or use LWTs when true compare-and-set invariants apply.

### 3.2. Ties and Tie-Breaking Rules

If a `DELETE` and `INSERT` share the **exact same timestamp**, Cassandra follows deterministic internal tie-breaking rules between tombstones and live cells. Never build domain correctness by letting writers generate matching timestamps and hoping network arrival decides winners.

Whenever strict ordering matters, rely on operation IDs and optimistic versioning rather than timestamps as locks. Check release-specific rules if you ever investigate exact-timestamp collisions.

### 3.3. Replays and Backfills Silently Re-Creating Deleted Rows

Frequent culprits to audit:

- Kafka consumers re-consuming older events and inserting identical primary keys.
- Scheduled backfills reading stale upstream snapshots.
- Sync jobs copying from secondary denormalized tables back into deleted rows.
- Cache warmers or reconcilers implementing "re-create if row missing".
- Clients retrying timed-out requests with fresh timestamps.
- Multi-DC services writing stale updates before deletes arrive cross-region.
- Backups or SSTable loads imported without reconciling newer deletes.

Never stop after searching logs for **`DELETE`**—audit **every writer capable of issuing `INSERT`/`UPDATE` on that primary key** after deletion time.

## 4. Zombie Data: Tombstones Gone Before Old Replicas Sync

Classic "deleted yet returned" scenario:

- Keyspace runs **RF = 3** in one DC; replicas A, B, C own partition K.
- C goes **DOWN** prior to `DELETE`, missing the tombstone.
- `DELETE` succeeds at **`LOCAL_QUORUM`** on A and B.
- C remains DOWN for an extended period while repairs miss that partition/tombstone.
- Once eligible, compaction on A and B **purges** the tombstone.
- C rejoins holding old K; absent a guarding tombstone during reads or repairs, stale K **resurfaces and spreads**.

~~~mermaid
sequenceDiagram
    participant J as Java client
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C (DOWN)
    J->>A: DELETE K, CL=LOCAL_QUORUM
    A->>A: Write tombstone
    A->>B: Replicate DELETE mutation
    B->>B: Write tombstone
    B-->>J: Quorum ACK (illustrative)
    Note over A,B: Tombstone retained within grace window
    Note over C: C still holds stale value K
    Note over A,B: After grace + eligible compaction, tombstone purges
    C-->>A: C returns carrying stale K
    Note over A,C: Absent delete marker, stale data can resurrect
~~~

This diagram **simplifies** coordinator/replica steps to highlight data semantics; it neither maps every packet nor promises zombie occurrence on every outage. Actual resurrection requires tombstone purge + missed sync + read/streaming contact.

### 4.1. `gc_grace_seconds` Is the Anti-Zombie Safety Window

**`gc_grace_seconds`** is a table property setting how long tombstones remain protected prior to compaction purge eligibility. **10 days = 864,000 seconds** is a common historical configuration—**always inspect the live table setting** rather than assuming defaults across clusters or versions.

Short `gc_grace_seconds`, prolonged outages, or neglected repairs elevate zombie risk. Conversely, setting grace ultra-long bloats tombstone retention, disk space, and read latency.

**Core rule:** never lower `gc_grace_seconds` just to "free disk fast" unless guaranteed repairs and availability prevent missed deletes. Size grace around **worst-case outage windows, repair cadence, recovery SLAs, topology, TTL/compaction strategy, and Cassandra release**.

### 4.2. Passing `gc_grace_seconds` Does Not Auto-Erase Tombstones Instantly

Actual purging still depends on:

- Whether tombstone/cell age passed grace.
- Compaction strategy and when eligible compactions actually run.
- SSTable overlap holding older shadowed versions that keep tombstones pinned.
- Unrepaired or missing replica conditions per version/strategy.
- Operational repair state and release safety checks.

Therefore:

- **Tombstones lingering past grace** do not automatically indicate a bug.
- **Zero tombstones seen in one SSTable** does not prove all replicas were repaired.
- **Forcing compaction to drop tombstones** is never a data recovery method.
- **Letting outages exceed grace** without repair coverage escalates risk rapidly.

### 4.3. Repair Must Cover Scope on Time

Repair is not a backup. Scheduled anti-entropy repairs across token ranges ensure replicas receive missed updates and tombstones **well within the grace window**—including buffers for outages, retries, and multi-DC latency.

A log reading "repair completed" for **one table, one subrange, or one DC** never guarantees cluster-wide coverage. Log uncovered ranges explicitly whenever repairs run partially or fail.

> **Version note:** Newer Cassandra releases and compaction strategies vary in incremental repair and tombstone purge optimizations. Never run blanket repairs assuming universal safety without verifying your exact version, full vs. incremental mode, DC/range scope, and recently DOWN nodes.

## 5. TTL Is Per-Cell—Not Automatic Row Deletion

### 5.1. TTL Clock Starts at Mutation Write Time

When CQL writes a column with **`USING TTL 120`**, expiration derives from **seconds elapsed since server mutation write time**. This is independent of:

- Application timestamp columns like **`created_at`**.
- Redis HTTP session TTLs or JWT `exp` claims.
- Backup or compaction timestamps.
- Client response receipt timing.

Writing a row at `T0` whose `created_at` column holds `T0 - 1 day` with `USING TTL 120` **does not** expire the row immediately—Cassandra never computes TTLs from user timestamp columns.

### 5.2. Individual Columns Can Carry Different TTLs

Consider three non-key columns:

~~~text
Partition key: (tenant_id, order_id)
state            : TTL 120 seconds
last_activity_at : No TTL
amount           : No TTL
~~~

After 120 seconds, `state` expires while `last_activity_at` and `amount` remain alive. A primary-key `SELECT` still returns the row with **`state = null`**.

Whenever someone claims "TTL didn't delete the row", ask:

1. Did `INSERT`/`UPDATE` attach TTL to **every non-key column** or just a subset?
2. Did any follow-up `UPDATE` write columns **without specifying TTL**?
3. Does the table define `default_time_to_live`, or do writers override it?
4. Do static columns, collections, UDTs, or row liveness markers keep the row alive?
5. Are reads inspecting **`SELECT *`**, ORM entities, or HTTP caches when declaring "row exists"?

Never shout "Cassandra ignores TTL" merely because one expired column leaves sibling non-TTL columns visible.

### 5.3. Rewriting a Column Resets Its TTL

Example:

~~~text
T0: UPDATE state='ACTIVE' USING TTL 120
T0+80s: UPDATE state='ACTIVE' USING TTL 120
T0+130s: SELECT state
~~~

The second write creates a **fresh mutation**, extending `state`'s lifetime past the original boundary. Client retries or periodic heartbeats continuously push expiration out.

Conversely, issuing an `UPDATE` with no TTL clause on a table whose default TTL is 0 writes a **permanent non-expiring cell**. **`USING TTL 0`** explicitly clears expiration on written columns—verify interactions carefully against `default_time_to_live` in your Cassandra release.

### 5.4. Table Default TTL

A table may set **`default_time_to_live`**. When > 0, mutations omitting `USING TTL` inherit that table default per CQL rules.

Common traps:

- One code path relies on `USING TTL 600` while another trusts a mismatched `default_time_to_live`.
- A schema migration alters table default TTL, leaving older and newer rows expiring under conflicting rules.
- One microservice passes `USING TTL 0` expecting permanent storage while another still supplies `TTL 600`.
- ORM repositories call full-entity `save()`/`upsert()`, silently rewriting previously expired columns.
- Frequent `UPDATE`s refresh active columns while untouched columns quietly hit their original expiration.

**Never infer a row's effective expiration solely from current table defaults.** Trace **real mutation history** and exact CQL queries executed.

### 5.5. Primary Keys Do Not Expire Independently as Data Cells

Partition and clustering columns define row identity and placement; TTL attaches to non-PK cells (and row liveness markers created via `INSERT`). Row visibility depends on liveness markers and live non-key cells—never design logic assuming "primary-key column TTL".

To expire an entire logical session cleanly as one unit, **write all columns together under matching TTLs**, block un-TTL'd partial updates, and always check an explicit domain **`expires_at`** field regardless of storage compaction lag.

## 6. Lab Data Model: Query-First Orders and Sessions

Using a single-DC RF=3 lab keyspace:

~~~sql
-- Run solely on a lab cluster with at least 3 suitable nodes in dc1.
CREATE KEYSPACE IF NOT EXISTS ttl_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

-- Order history keyed by tenant and day.
CREATE TABLE IF NOT EXISTS ttl_lab.orders_by_tenant_day (
    tenant_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    state text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

-- Logical session keyed by tenant and session ID.
CREATE TABLE IF NOT EXISTS ttl_lab.sessions_by_id (
    tenant_id uuid,
    session_id uuid,
    owner_token text,
    state text,
    issued_at timestamp,
    expires_at timestamp,
    PRIMARY KEY ((tenant_id, session_id))
);
~~~

**Design notes:**

- `orders_by_tenant_day` uses composite partition key `(tenant_id, order_day)`; deleting one specific order demands specifying full clustering keys `created_at` and `order_id`.
- This schema serves tenant-daily queries, not global lookups by `order_id`. Deleting from this table **never automatically removes** rows in any companion lookup table.
- `sessions_by_id` partitions cleanly by `(tenant_id, session_id)`, simplifying key-scoped TTL tests; always evaluate cardinality and traffic in real workloads.
- Never use `ALLOW FILTERING` for keyspace-wide forensic scans; test using tracked deterministic keys.
- RF=3 and `LOCAL_QUORUM` require a genuine multi-node lab—never extrapolate multi-node guarantees from single-node RF=1 containers.

### 6.1. `INSERT` Session With TTL

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'test-owner-A', 'ACTIVE',
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:02:00Z'
) USING TTL 120;
~~~

`expires_at` here is purely application metadata; **Cassandra never inspects `expires_at` to drive expiration**. Even with hardcoded past dates inside `issued_at`/`expires_at`, `USING TTL 120` counts 120 seconds from the **actual server mutation time**.

When hard deadlines matter, compute remaining TTL relative to an immutable **`expires_at`** deadline at write time, enforce `expires_at` explicitly in domain authorization logic, and never extend TTL on retries past that deadline.

### 6.2. Querying Remaining TTL and Write Timestamps

~~~sql
SELECT owner_token, state, issued_at, expires_at,
       TTL(state) AS state_ttl_left,
       WRITETIME(state) AS state_write_us
FROM ttl_lab.sessions_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

**Interpretation:**

- **`TTL(state)`** returns remaining seconds on cell `state` if a TTL exists, or **`null`** if the cell carries no TTL (or is null).
- **`WRITETIME(state)`** returns the cell's write timestamp in **microseconds**.
- Once expired, `SELECT` omits dead cells/rows; expired tombstones aren't read via normal CQL queries.
- Checking `TTL(state)` alone proves nothing about `owner_token`, `issued_at`, or `expires_at`.

> **Caveat:** `TTL()` and `WRITETIME()` have CQL type restrictions (e.g., counters and certain multi-cell collections); verify against your exact column definitions and release.

### 6.3. Updating One Column Without TTL

Illustrating `state` expiring while another column persists:

~~~sql
-- Rewrites owner_token without TTL when table default_time_to_live = 0.
UPDATE ttl_lab.sessions_by_id
SET owner_token = 'persistent-owner'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

Run after the TTL `INSERT` on a table without default TTL, `owner_token` survives after `state` expires—leaving the row returning partial columns rather than disappearing. In real apps, never mutate session ownership without authorization checks; this is strictly a schema demo.

### 6.4. Deleting an Order With Full Keys

~~~sql
DELETE FROM ttl_lab.orders_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T08:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

Never assume a broad `DELETE` mentioning only `tenant_id` (or partial clustering keys) deletes just one order: Cassandra supports partition/range deletes that generate range tombstones across swaths of rows. Always capture key readbacks before deleting; accidental broad deletes flood tombstones and risk availability.

### 6.5. Deleting a Session

~~~sql
DELETE FROM ttl_lab.sessions_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

This issues a logical `DELETE` tombstone, never forcing immediate SSTable erasure. Never treat running `nodetool compact` after every `DELETE` as mandatory application hygiene.

## 7. Inspecting Schema Metadata Before Changing Hypotheses

Useful read-only schema checks:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'ttl_lab';

SELECT keyspace_name, table_name,
       gc_grace_seconds, default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'ttl_lab'
  AND table_name = 'sessions_by_id';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'ttl_lab'
  AND table_name = 'sessions_by_id';
~~~

**Cross-check live reality:**

- **`gc_grace_seconds`** on the **exact** target table, not a sibling table.
- **`default_time_to_live`** and compaction strategy details.
- Exact partition/clustering keys, data types, and schema agreement.
- Replication strategy, per-DC RF, driver local DC, and read/write CLs.
- Whether recent schema alters actually converged across every node.

**`system_schema` queries return only the coordinator's local schema view**; resolve any schema disagreement before running DDL or repair commands.

## 8. Decision Tree: Where Is the Data Living?

~~~mermaid
flowchart TD
    A["API sees deleted data"] --> B{"Direct PK SELECT on exact table sees it?"}
    B -->|No| C["Check caches, denormalized tables, search indexes, API mappings"]
    B -->|Yes| D{"Does row/cell hold active TTL?"}
    D -->|Positive TTL| E["Check latest write: TTL refresh, default TTL, expiry source"]
    D -->|Null / no TTL| F["Check non-TTL columns, row liveness, recent writes"]
    D -->|Not visible / expired| G["Check mismatched key or cache/CL divergence"]
    E --> H{"Any INSERT/UPDATE after DELETE or expiry?"}
    F --> H
    H -->|Yes| I["Audit write timestamps, retries, backfills, CDC/consumers"]
    H -->|Unclear| J["Audit replica downtime, repair coverage, gc_grace, compaction"]
    J --> K{"High zombie risk?"}
    K -->|Yes| L["PAUSE destructive purges/ops; escalate & reconcile"]
    K -->|Insufficient proof| M["Hold UNKNOWN; collect more logs, metrics, and lab tests"]
~~~

**Priority order:** rule out **wrong read source**, **partial-column TTL**, and **legitimate newer writes** before declaring zombie resurrection. Many "reappearing row" tickets turn out to be a stale cache or companion lookup table.

### 8.1. Correlate One Key, One Table, One Projection

For `(tenant_id, session_id)` using identical bound queries, capture:

- Exact keyspace and table queried by the Java service.
- Target DC, coordinator, and CL of the request.
- Exact selected columns and whether the result was **row null vs. field null**.
- Visible `TTL()` and `WRITETIME()` values.
- UTC timestamp, clock skew bounds, and driver request timeouts.
- Latest write/delete IDs from audit/CDC/event logs.

Never compare an API serving an `orders` projection against a `DELETE` executed solely on `orders_by_tenant_day`—confirm every denormalized read model cleans up together.

### 8.2. Separating "Row Null" From "Field Null"

Sample outcomes:

~~~text
Case 1:
SELECT ... WHERE full primary key => 0 rows
=> Row absent for this query at this CL and timestamp.

Case 2:
SELECT ... => 1 row, state = null, owner_token = 'A'
=> state cell expired or deleted, while sibling columns keep row alive.

Case 3:
SELECT ... => 1 row, state = 'ACTIVE', TTL(state) = null
=> Live non-TTL cell; check un-TTL'd writes, defaults, and mutation logs.

Case 4:
API returns state='ACTIVE' while direct CQL PK SELECT returns 0 rows
=> Audit caches, read models, search indexes, projections, and routing.
~~~

Each check provides **query-scoped evidence**, not instant proof across every replica in every DC. Confirm cluster-wide state via CL alignment and broader reconciliation.

## 9. Symptom-to-Cause Matrix

| Symptom | Candidate causes | How to verify |
|---|---|---|
| Row returns after long node outage | Tombstone purged while stale replica held old row (**zombie**) | Outage duration, repair coverage, `gc_grace`, compaction, versions |
| Row returns minutes after `DELETE` on healthy cluster | New writer, retry, backfill, higher timestamp | Audit/CDC/app logs, `WRITETIME(cell)`, request IDs |
| `DELETE` succeeded yet another endpoint sees row | Reading cache, search index, or another table | Match keyspaces/tables/PKs, invalidation hooks, dual-writes |
| TTL 120s yet `state` stays `ACTIVE` much longer | Heartbeat refreshed TTL, clock skew, mismatched effective TTL | Track `TTL(state)` over time, `WRITETIME`, writer logs |
| `TTL(state)` is `null` despite live value | Non-TTL writer, `TTL 0`, schema mismatch | Inspect historical CQL, `default_time_to_live`, ORM saves |
| `state` is `null` yet row still returns | Sibling column or row liveness without matching TTL | Select all columns and inspect per-column `TTL()` |
| Disk stays full after expiration | Uncompacted SSTables/tombstones or snapshot hardlinks | Compaction backlog, disk free, active snapshots |
| TTL test passes on RF=1 yet fails multi-DC | CL/DC mismatch, alternate writers, lag, node faults | RF/DC, local DC, CL, multi-node queries, mutation logs |
| Row differs between `LOCAL_ONE` and `LOCAL_QUORUM` | Temporary replica lag or differing read paths | Node health, replica tokens, repair/streaming progress |
| Stale state returns post-compaction | Zombie data or stale cache/projection | Direct PK `SELECT`, reinsert logs, repair/grace timeline |
| Session expires earlier than expected | Short default TTL, clock skew, backdated timestamp | `TTL()` right post-insert, `expires_at`, NTP sync |
| Session never expires | Writer omits TTL, uses `TTL 0`, continuous refresh, permanent columns | Live CQL trace, table options, per-column `TTL()` |

**No lone metric or `SELECT` diagnoses every case.** Construct a complete mutation, outage, and schema timeline.

## 10. Java Driver 4.x: Read Probe for TTL and Write Timestamps

A Java tool can inspect **one known fixture row** by full primary key without table scans.

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TtlReadProbe {
    private final CqlSession session;
    private final PreparedStatement query;

    public TtlReadProbe(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT state, owner_token, " +
            "TTL(state) AS ttl_left, " +
            "WRITETIME(state) AS write_us " +
            "FROM ttl_lab.sessions_by_id " +
            "WHERE tenant_id = ? AND session_id = ?");
    }

    public Observation read(UUID tenantId, UUID sessionId) {
        BoundStatement statement = query
            .bind(tenantId, sessionId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(statement).one();
        if (row == null) {
            return new Observation(
                false, null, null, null, null);
        }

        return new Observation(
            true,
            row.getString("state"),
            row.getString("owner_token"),
            row.isNull("ttl_left")
                ? null : row.getInt("ttl_left"),
            row.isNull("write_us")
                ? null : row.getLong("write_us"));
    }

    public static final class Observation {
        public final boolean rowReturned;
        public final String state;
        public final String owner;
        public final Integer stateTtlSeconds;
        public final Long stateWriteTimestampMicros;

        Observation(boolean rowReturned,
                String state, String owner,
                Integer stateTtlSeconds,
                Long stateWriteTimestampMicros) {
            this.rowReturned = rowReturned;
            this.state = state;
            this.owner = owner;
            this.stateTtlSeconds = stateTtlSeconds;
            this.stateWriteTimestampMicros =
                stateWriteTimestampMicros;
        }
    }

    public static void main(String[] args) {
        // Lab only; configure TLS, auth, and live DC in production.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            TtlReadProbe probe = new TtlReadProbe(session);
            Observation o = probe.read(
                UUID.fromString(
                    "11111111-1111-4111-8111-111111111111"),
                UUID.fromString(
                    "22222222-2222-4222-8222-222222222222"));

            System.out.println(
                "rowReturned=" + o.rowReturned +
                ", statePresent=" + (o.state != null) +
                ", ttlSeconds=" + o.stateTtlSeconds +
                ", writeMicros=" + o.stateWriteTimestampMicros);
        }
    }
}
~~~

### 10.1. Interpreting Output Correctly

- **`rowReturned = false`:** query returned zero rows; does not distinguish a tombstone from a key never written.
- **`state = null`:** cell is absent or expired, though sibling columns kept the row visible.
- **`stateTtlSeconds > 0`:** cell retains active TTL remaining at read time.
- **`stateTtlSeconds = null` with non-null `state`:** cell has no active TTL—check non-TTL writes or defaults rather than assuming expiration.
- **`stateWriteTimestampMicros`:** write timestamp of the returned live cell—not a `DELETE` tombstone timestamp. Normal CQL cannot inspect purged/shadowed history.
- **Falling TTL:** proves TTL countdown on those sampled reads, not across untouched columns or replicas.

Examples assume `LOCAL_QUORUM` on an RF=3 lab. Single-node labs must match RF/CL appropriately with limits noted. Never change production CL stealthily mid-triage.

### 10.2. Avoid Over-Extrapolating From Point Probes

One `SELECT` never exposes hidden SSTable tombstones. Real zombie forensics require **delete event logs/CDC/audit trails, repair/compaction history, outage logs, topology views, and specialized isolated DBA SSTable tools**.

Never inspect or edit raw SSTables directly on production nodes just because CQL didn't show a tombstone—take forensics onto isolated snapshot/backup copies with version-matched tools.

### 10.3. Java Driver Read Errors Do Not Equal TTL Expiration

Probes throwing `DriverTimeoutException`, `ReadTimeoutException`, `AllNodesFailedException`, or `UnavailableException` must report **`ERROR` / `UNKNOWN`**, never "row missing".

~~~text
Correct:
  Query succeeds, row == null -> ABSENT_AT_THIS_READ
  Query succeeds, row != null -> OBSERVED_ROW
  Query times out / fails     -> UNKNOWN_READ_RESULT

Incorrect:
  catch (Exception e) { return null; }
  => Tricks application into thinking session expired while DB timed out.
~~~

This matters doubly for sensitive authorization checks: a database timeout never proves an access lease was cleanly revoked.

## 11. Clocks, TTL Deadlines, and Retries

### 11.1. TTL Is Not an Authoritative Domain Expiry Gate

If an app executes:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (?, ?, ?, ?, ?, ?)
USING TTL ?;
~~~

then **TTL counts from actual mutation execution**, ignoring `expires_at`. Retrying the identical query 90 seconds later with `TTL=120` silently **extends cell life** beyond "120 seconds from original issuance".

For strict business deadlines:

1. Fix **`expires_at`** once when starting the logical operation.
2. On retries, compute **remaining TTL** `(expires_at - now)` rather than passing static 120s again.
3. Preserve stable request IDs, payloads, and write-ordering rules.
4. Check **`expires_at` explicitly** in authorization logic; never treat Cassandra TTL as the sole access-control enforcement layer.
5. Reject retries whose remaining TTL is already `<= 0`—never pass `0` accidentally (which means no TTL!) or round up to 1s if unauthorized.
6. Track NTP/clock skew across clients, coordinators, and replicas.

TTL is a storage retention tool, not a skew-proof stopwatch.

### 11.2. Maximum TTL Bounds and Far-Future Timestamps

Cassandra releases impose maximum representable expiration/timestamp limits and overflow policies. Never assume multi-decade TTL values behave uniformly across upgrades and versions.

**Runbook:** if CQL throws invalid TTL or expiration overflow errors, record exact Cassandra version, sanitized error message, table options, and requested expiration. Never casually pass `USING TTL 0` or arbitrary numbers to silence errors without checking retention policies.

### 11.3. Time Zones in Java Applications

CQL `timestamp` stores an instant, yet logs/UIs format local time zones. `08:00Z` renders as `15:00` in `Asia/Ho_Chi_Minh`. Parsing bugs or zone-less `LocalDateTime` objects make teams mistake time-zone offsets for "TTL expiring 7 hours early/late".

Standardize every incident timeline on **`Instant` / UTC**. Remember **`TTL()` returns remaining seconds** independent of display zones, whereas formatting `expires_at` is purely presentation logic.

### 11.4. Clock Skew and Future Timestamps

Cassandra relies on timestamps for both TTL and LWW write resolution. Host clock drift or client-supplied future timestamps trigger baffling symptoms (such as older values defeating newer `DELETE`s). Query `WRITETIME(col)` and compare against UTC timelines to spot skew—and engage host ops for NTP repair rather than manually jumping clocks on live nodes.

## 12. `gc_grace_seconds`, Repair Cadence, and Replica Outage Risk

### 12.1. Three Durations to Evaluate Together

Never size `gc_grace_seconds` solely from "too many tombstones" or "1-day data TTL". Weigh:

| Duration | Meaning | Consequence if ignored |
|---|---|---|
| **`T_down_max`** | Longest a replica can remain offline/unreachable before intervention | Stale data returns unchecked |
| **`T_repair_coverage`** | Time needed for repairs to complete successfully across target ranges/replicas | "Cron triggered" masks failed coverage |
| **`T_grace`** | Tombstone retention grace window on the table | Risk of premature purge vs. excessive bloat |

Operational principle: **verified repair coverage must finish safely before tombstones purge**, leaving margin for outages, retries, job failures, and WAN delays. Never reduce this to one universal formula across all versions and compaction strategies.

**Hypothetical** example:

~~~text
gc_grace_seconds = 864000 (10 days)
scheduled repair runs every 7 days
node C stays DOWN 12 days; scheduled repairs skip C
C returns after tombstones became purge-eligible

Zombie risk exists despite a "weekly repair" schedule.
~~~

Always ask: did repairs **succeed across all natural replicas and ranges**, with zero skipped or failed segments? A cron job named "weekly repair" protects nothing for a node offline past grace.

### 12.2. Why You Shouldn't blindly Set `gc_grace_seconds = 0` on TTL Tables

Setting zero or tiny grace makes tombstones purge-eligible immediately, risking resurrection whenever replicas miss explicit `DELETE`s or TTL transitions diverge across nodes. Specific append-only TWCS designs sometimes tune grace aggressively—yet only under **strict preconditions on replica uptime, immutability, zero explicit deletes, and verified ops procedures**.

**Never blindly copy blog recommendations into mixed production tables.** Audit deletes, late writes, retries, outages, and multi-DC topology thoroughly first.

### 12.3. Raising `gc_grace_seconds` Post-Incident Does Not Resurrect Lost Tombstones

Valid CQL syntax example:

~~~sql
-- SYNTAX ILLUSTRATION ONLY; DO NOT RUN BLINDLY MID-INCIDENT.
ALTER TABLE ttl_lab.sessions_by_id
WITH gc_grace_seconds = 864000;
~~~

Increasing grace **after tombstones have already purged** cannot restore erased tombstones; lowering grace does not stop active writers from re-inserting rows. Always confirm schema agreement after any approved `ALTER TABLE`.

### 12.4. Hinted Handoff and Read Repair Do Not Replace Scheduled Repair

Do not rely solely on hints or read repair to deliver deletes prior to compaction purges:

- Hints obey `max_hint_window` and best-effort limits, missing extended outages.
- Read repair heals only partitions actively queried at qualifying CLs—untouched rows drift silently.
- A successful `LOCAL_QUORUM` `SELECT` proves nothing about the third replica's tombstone state.
- Full/incremental anti-entropy repairs demand explicit scope tracking and verification.

**Evaluate repair posture by verified coverage evidence**, never assumptions that "Cassandra syncs itself automatically".

## 13. Compaction and Tombstones: Why Deletes Don't Shrink Disk Right Away

Cassandra appends tombstones into memtables/SSTables—a `DELETE` never opens old SSTables to erase bytes in place. Compaction merges SSTables later and drops tombstones only once overlap and safety guards confirm zero shadowed live versions remain elsewhere.

### 13.1. Targeted Compaction Telemetry

Inspect:

- Table **SSTable count**.
- Used/free disk space and flush/compaction throughput.
- **Pending compaction tasks** and active compaction nodes.
- Tombstone warnings, scanned tombstones, and read p95/p99.
- Snapshot/backup hardlinks pinning obsolete SSTables on disk.
- Competing repair/streaming I/O.
- Active compaction strategy (`STCS`/`LCS`/`TWCS`, etc.) and Cassandra release.

**Never trigger forced major compaction mid-incident just to "clear leftover tombstones".** Major compaction drains I/O/CPU/space, worsens p99, and cannot guarantee purging overlapped/unrepaired state safely.

### 13.2. TWCS, TTL, and Late-Arriving Writes

**TimeWindowCompactionStrategy (TWCS)** buckets SSTables by time windows for uniform TTL datasets. However, **late writes, out-of-order timestamps, explicit updates to old partitions, or mixed TTLs** violate pure window isolation and pin SSTables across buckets.

Example:

~~~text
Window 1 holds events written with 7-day TTL.
A late backfill writes into historical keys/cells.
New DELETEs/UPDATEs carry newer timestamps into newer SSTables.
SSTables overlap across windows, blocking single-SSTable drops.
~~~

Never assume "after 7 days TWCS auto-deletes entire SSTables cleanly" if late writes or overlapping deletes exist. Verify SSTable overlap and release behavior directly.

### 13.3. Tombstone Read Pressure vs. Resurrected Data

| Symptom | Investigation track |
|---|---|
| `SELECT` returns `DELETE`d rows | Newer writer, stale replica/zombie, CL, cache, or projection |
| `SELECT` returns 0 rows yet p99 spikes | Tombstone scanning, SSTable count, partition bloat, compaction I/O |
| TTL expired yet disk stays high | Uncompacted expired SSTables or pinned snapshots |
| Data reappears right after compaction | Possible purged tombstones + returning stale replica; check timeline/repair |
| Disk spikes right after `ALTER` compaction | Active SSTable rewrite overhead requiring temporary headroom |

Use this table as directional leads—always confirm against outage windows, logs, and exact query traces.

## 14. RF/DC, Consistency Levels, and Stale Data on Reads

Suppose `NetworkTopologyStrategy` configures `RF=3` in `dc1`:

- **`LOCAL_ONE`** queries one local replica; if that replica missed a `DELETE`, reads can return stale data while healthy peers hold tombstones.
- **`LOCAL_QUORUM`** requires 2/3 local replicas; stronger consistency, yet still subject to timing, retries, concurrent writers, and topology edge cases.
- **`ALL`** contacts all replicas and slashes availability during outages—it never repairs zombie data after tombstones purged.
- **`SERIAL`/`LOCAL_SERIAL`** applies to LWT/Paxos reads, not ordinary `SELECT`/`DELETE`s unless explicitly designed.

**Quorum intersections depend strictly on assumptions.** Guarantees hold across RF, CL, non-concurrent writes, synced clocks, local DC bounds, and matching schemas—two `LOCAL_QUORUM` pools in separate DCs never guarantee mutual overlap globally.

### 14.1. Raising Read CL Cannot Invent Lost Tombstones

Once healthy replicas purged tombstones and a stale node returns carrying old values, bumping CL to `ALL` cannot recreate erased tombstones. Restoring truth requires:

- Audit logs, CDC streams, or outboxes confirming `DELETE` execution.
- Point-in-time backups/snapshots used strictly for forensic verification or controlled recovery.
- Authoritative business ledgers (order status, deletion ledger).
- Deterministic idempotent reconciliation with clear timestamps/versions.
- Isolating or rebuilding the stale replica per recovery runbooks.

**Repair makes replicas converge—it cannot tell a valid row apart from a zombie row.** Without external proof, repair may propagate stale data everywhere instead of deleting it.

### 14.2. Never Extrapolate From One Java Service's Local DC to All Regions

Service A in `dc1` may use `LOCAL_QUORUM` cleanly while Service B in `dc2` reads/writes differently across laggy WAN links. On reports of "intermittent stale reads", record:

- Service instance/region and driver `localDatacenter`.
- Contact points and selected coordinator.
- Executed normal CL (and serial CL if LWT).
- Per-DC replication factors.
- Node health, repair state, and event UTC timestamps.
- Hashed/anonymized business key.

Never cross-route traffic between DCs or change CL mid-incident without verifying data residency and staleness contracts.

## 15. Safe Read-Only Inspection Commands Before Intervening

Run version-appropriate read-only commands where authorized:

~~~bash
# Node health, DC/rack topology, DOWN/UP/JOINING states.
nodetool status

# Local node status, load, uptime, and resources.
nodetool info

# Thread pool active, pending, and dropped queues.
nodetool tpstats

# Active compactions and pending background tasks.
nodetool compactionstats

# Active streaming sessions and network transfers (if supported).
nodetool netstats

# Table stats (SSTables, reads, tombstone counts per release).
nodetool tablestats ttl_lab.sessions_by_id

# Partition/row size distributions (where supported).
nodetool tablehistograms ttl_lab sessions_by_id

# Snapshots holding hardlinks to older SSTables.
nodetool listsnapshots
~~~

Also collect:

- Per-node server logs: tombstone warnings, repair failures, node `DOWN`/`UP`, compaction errors.
- Repair job logs/schedules: covered ranges/DCs/tables, successes, skipped/failed ranges, and timestamps.
- Disk free/await/IOPS, network packet loss, GC/heap/native RSS, CPU.
- Java Driver/app logs: query shapes, CL, timeouts/retries, DC, correlation IDs, and downstream calls.
- Audit/CDC/event logs: last `INSERT`/`UPDATE`/`DELETE` on the logical key.
- Backup manifests and restore records whenever zombie resurrection is suspected.

**Never run `nodetool repair`, `cleanup`, `compact`, `rebuild`, `decommission`, or `clearsnapshot` just to "check status".** Every one alters state, load, or retention—especially clearing snapshots prior to confirming isolated backups destroys recovery points.

### 15.1. Incident Timeline Template

~~~yaml
incident:
  id: "ttl-zombie-lab-2026-11"
  table: "ttl_lab.sessions_by_id"
  key_reference: "<approved-hashed-key>"
  first_reported_utc: "<time>"
topology:
  rf_by_dc: "dc1:3"
  read_cl: "LOCAL_QUORUM"
  write_cl: "LOCAL_QUORUM"
schema:
  gc_grace_seconds: "<observed>"
  default_time_to_live: "<observed>"
  compaction: "<observed>"
timeline:
  last_known_write: "<time + logical ID>"
  delete_or_ttl_expected: "<time>"
  replica_downtime: "<duration / nodes>"
  last_successful_repair_coverage: "<scope and time>"
  compaction_period: "<time range>"
  reappearance_observed: "<time>"
diagnostics:
  ttl_and_writetime: "<observed if still visible>"
  writer_reinsert_evidence: "<found/none/not_checked>"
  cache_projection_checked: "<yes/no>"
decision:
  classification: "UNKNOWN_PENDING_EVIDENCE"
  next_action: "preserve evidence and compare sources"
~~~

This is a custom reporting template—**not Cassandra config or real incident data**. Mark unmeasured fields `NOT_MEASURED` rather than fabricating repair timestamps or guesses.

## 16. Incident Runbook: Preserve Data Before Tuning

### 16.1. Minutes 0–5: Assess Risk and Lock Evidence

1. **Assess sensitivity:** financial ledgers, PII records, legally mandated privacy deletions, or synthetic test rows? Trigger privacy/compliance workflows immediately if mandated deletes resurfaced.
2. **Pin UTC markers:** delete time, expected TTL expiry, reappearance observation, node `DOWN`/`UP`, deploys/backfills.
3. **Verify source:** does the API serve directly from Cassandra, HTTP caches, or secondary read models? Check exact keyspace/table/PK.
4. **Capture schema & CL:** `gc_grace_seconds`, `default_time_to_live`, compaction, per-DC RF, and read/write CLs.
5. **Preserve evidence:** audit/CDC/app logs, request IDs, ring states, repair history, snapshot manifests. Never wipe snapshots, tombstones, or force compaction prior to gathering proof.
6. **Contain writers:** if a replay job or projection consumer is actively re-creating deleted rows, pause that source cleanly per runbook.
7. **Never spam infinite delete loops**, forge massive future timestamps, or kill nodes just because one `SELECT` returns stale rows.

### 16.2. Minutes 5–15: Form Hypotheses

| Evidence | Candidate hypothesis | How to verify |
|---|---|---|
| `TTL(state)` positive and climbing again | Write refreshing TTL | `WRITETIME`, app logs, client retries |
| `TTL(state)` null while `state` stays live | Non-TTL cell or rewritten without TTL | Default TTL, `TTL 0`, ORM upserts |
| `state` null while `owner_token` persists | Per-cell TTL keeping row alive | Query sibling columns and their TTLs |
| Reappeared row carries write timestamp > `DELETE` | Replay/reinsert with fresher timestamp | Audit/CDC/producer logs |
| Node DOWN > `gc_grace`, repairs lagged/missed | Zombie risk | Repair coverage, outage length, compaction logs |
| Direct `SELECT` absent while API returns row | Stale cache, index, or companion table | API routing, read models, invalidation hooks |
| Different results across DCs or CLs | Replica divergence or region-local writers | RF/DC, CL, node health |
| TTL expired yet disk unchanged | Unpurged SSTables or pinned snapshots | Compaction stats, filesystem accounting |
| `DELETE` timed out | Unknown outcome | Request IDs, replica logs, reconciliation |

**Hypotheses are not confirmed root causes.** A node sitting `DOWN` longer than grace only flags risk—never proves tombstones actually purged or resurrected from that replica.

### 16.3. Minutes 15–30: Choose the Safe Track

**Track A — Code/config TTL mismatch:** Fix writer CQL and `expires_at` contracts; add integration tests. Never purge bulk data without verified scope.

**Track B — Reinsert/replay writer:** Pause or patch replay consumers and backfills; add request ID/version guards and clean up secondary tables. Never touch `gc_grace_seconds` when valid newer timestamps wrote the row.

**Track C — Suspected zombie data:** Engage DBA/SRE, lock backups/evidence, audit repair coverage and grace timelines, and reconcile authoritative state or isolate stale replicas per runbook. **Never run blind repair** across divergent tombstones—it can spread zombie rows globally.

**Track D — Cache or projection lag:** Fix cache invalidation, CDC consumers, or projections per retention contracts—never run Cassandra compaction expecting it to clear Redis or Elasticsearch.

### 16.4. STOP and ESCALATE Gates

- Legally/policy deleted data remains visible or propagates externally.
- Missing quorum, multi-DC divergence, or stale node returning after prolonged outage.
- Partial/failed repair coverage or missing delete audit trails.
- Critical disk shortage or compaction/tombstone storms violating API SLOs.
- Proposed intervention alters RF, retention/compaction, topology, or drops backups.
- Wide-scale restore or bulk data repair required.
- Unable to bound the set of impacted logical keys.

Upon hitting any gate, **PAUSE state-changing or evidence-destroying actions**, notify the incident commander, and recover methodically—never bump timeouts or lower CL to mask incidents.

### 16.5. Incident Closure Criteria

1. **Root cause** evidenced and underlying defective writer/config fixed.
2. Impacted business keys identified and reconciled within accepted scope.
3. Writers, caches, and projections no longer resurrect deleted rows.
4. RF/DC, repair coverage, and cluster health back within safety thresholds.
5. TTL/deletion checks verified across a window long enough to cover retries and recovered nodes.
6. Read/write SLOs, disk headroom, GC, and compaction healthy.
7. Postmortem archives full timeline, mitigations, backup checks, and regression tests.

**One `SELECT` returning 0 rows after an ad-hoc `DELETE` never closes the incident cleanly.**

## 17. Four Concrete Diagnostic Case Studies

### Case A — 120s TTL Yet API Still Returns Session After 15 Minutes

**Hypothetical evidence:**

~~~text
10:00 UTC: INSERT session USING TTL 120
10:01:20 UTC: heartbeat UPDATE owner_token (omits TTL)
10:03 UTC: SELECT state = null, owner_token = 'A'
10:15 UTC: API reports "session exists"
~~~

**Diagnosis:** `state` expired cleanly at 120s, yet the non-TTL heartbeat write to `owner_token` kept the row alive. Treating "row exists" as "session valid" broke the domain contract.

**Remediation:** Enforce `expires_at` checks in authorization logic, ensure heartbeats preserve TTLs or stay consistent with deadlines, and add mixed-TTL integration tests. Never force compaction here—valid live cells kept the row present.

### Case B — Clean `DELETE`, Re-Inserted Three Minutes Later

**Hypothetical evidence:**

~~~text
10:00 UTC: DELETE order K, write timestamp = 500000000
10:03 UTC: replay consumer INSERTs K, write timestamp = 600000000
10:03:01 UTC: SELECT K -> returns row
Nodes: All UP; zero outages or failed repairs
~~~

**Diagnosis:** Cassandra behaved accurately under LWW: a **new write** arrived carrying a higher timestamp than `DELETE`. This is not `gc_grace` zombie resurrection.

**Remediation:** Stop/fix the replay consumer, enforce deletion ledgers or monotonic version/LWT fencing, and clean up projections. Never lower grace, run major compaction, or bump CL over a newer write.

### Case C — Long Replica Outage With Incomplete Repair

**Hypothetical evidence:**

~~~text
Day 1: Replica C goes DOWN.
Day 2: DELETE K ACKs at LOCAL_QUORUM on A + B.
Day 10: Partial repair runs, missing token ranges holding K.
Day 13: A/B compact after gc_grace elapses.
Day 14: C rejoins still holding old K.
Day 15: Reads intermittently return old K.
~~~

**Diagnosis:** Timeline strongly matches **zombie risk**, though you must verify compaction actually purged tombstones, inspect C's timestamps, and rule out newer writers before concluding solely from "C down 14 days".

**Remediation:** Lock logs/backups, engage DBAs to audit repair coverage and deletion truth sources, and isolate/reconcile stale replicas cleanly—recall repair alone cannot deduce deleted intent once tombstones vanish.

### Case D — Row Gone From Cassandra, API Still Serves Document

**Hypothetical evidence:**

~~~text
Direct CQL SELECT (exact keyspace/table/PK): 0 rows
Cache or search index: still holds old document
API response: still returns document
~~~

**Diagnosis:** Cassandra already shows the row absent; downstream caches, search indexes, or lagging CDC projections failed invalidation. Continue verifying CL/replica posture briefly, but do not blame compaction.

**Remediation:** Repair cache invalidation, projection consumers, and downstream retention policies—never run `nodetool repair` expecting Cassandra to evict Redis keys or search docs.

## 18. CQL Lab Drills: Per-Cell TTL vs. Reinsertion

### 18.1. Drill 1 — All Non-Key Cells Carry TTL

Using **fresh `tenant_id` and `session_id` keys** in `sessions_by_id` inside staging/lab only, insert all columns with TTL:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (
    44444444-4444-4444-8444-444444444444,
    55555555-5555-4555-8555-555555555555,
    'lab-owner', 'ACTIVE',
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:01:00Z'
) USING TTL 8;
~~~

Check immediately:

~~~sql
SELECT state, owner_token,
       TTL(state) AS ttl_state,
       TTL(owner_token) AS ttl_owner
FROM ttl_lab.sessions_by_id
WHERE tenant_id = 44444444-4444-4444-8444-444444444444
  AND session_id = 55555555-5555-4555-8555-555555555555;
~~~

Expect matching ~8s countdowns across written non-key cells, returning **0 rows** once the window + buffer elapses (absent newer writes). Never fail the drill merely because disk usage stayed flat.

### 18.2. Drill 2 — Updating One Column Without TTL

Create a fresh TTL=8 session as above, then inside the 8s window run:

~~~sql
UPDATE ttl_lab.sessions_by_id
SET owner_token = 'persistent-owner'
WHERE tenant_id = 44444444-4444-4444-8444-444444444444
  AND session_id = 55555555-5555-4555-8555-555555555555;
~~~

**Note:** Always generate unique keys per run rather than reusing expired fixtures, assuming table `default_time_to_live = 0`.

Once `state` expires, queries return **`state = null`** alongside **`owner_token = 'persistent-owner'`**, keeping the row visible—exposing why per-column TTL never guarantees whole-row deletion.

### 18.3. Drill 3 — Reinsert Following `DELETE`

On a fresh fixture key:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'first', 'ACTIVE');

DELETE FROM ttl_lab.sessions_by_id
WHERE tenant_id = ? AND session_id = ?;

INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'second', 'ACTIVE');
~~~

With strictly increasing mutation timestamps, `SELECT` cleanly returns `owner_token='second'`—legitimate **post-delete reinsertion** needing zero replica downtime or GC cycles.

Only supply explicit timestamps in isolated labs if testing tie/order edge cases—**never** inject artificial timestamps into production.

### 18.4. Drill 4 — `DELETE` With Older Timestamp

CQL allows explicit timestamps subject to release syntax. Concept test in a lab only:

~~~sql
-- Microsecond timestamps below are strictly LAB values;
-- never send synthetic timestamps to production.
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'newer', 'ACTIVE')
USING TIMESTAMP 500000;

DELETE FROM ttl_lab.sessions_by_id
USING TIMESTAMP 400000
WHERE tenant_id = ? AND session_id = ?;
~~~

Because the `DELETE` carries a lower timestamp (400000 < 500000) for the identical PK, the live cell remains visible—demonstrating **write-timestamp ordering**, not short `gc_grace`. Keep these tiny past timestamps strictly confined to disposable test keys.

### 18.5. Never Hammer One Hot Partition During Tests

- Generate unique tenant/session keys per test run rather than piling 1,000 deletes onto one partition needlessly.
- Never run `DROP`/`TRUNCATE` or forced compaction on shared test tables.
- Use `LOCAL_QUORUM` on healthy RF=3 labs; note limits clearly if using RF=1 containers.
- Allow safe polling buffers around short TTLs rather than fragile exact millisecond sleeps.
- Treat server/driver timeouts during probes as **`INCONCLUSIVE` / `ERROR`**, never "row expired".
- Archive required evidence before cleaning up owned lab namespaces.

## 19. Java Integration Testing: TTL Expiry vs. Non-TTL Persistence

Integration tests validate **CQL-visible semantics** cleanly—never needing forced compaction or SSTable tricks. Using JUnit 5 and Java Driver 4.x against `ttl_lab.sessions_by_id`:

### 19.1. JUnit 5: Verifying Row Expiration and Column Survival

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.Test;

public class TtlSemanticsIT {
    private static CqlSession openLabSession() {
        // Adjust contact point/DC, TLS, and auth per lab cluster.
        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build();
    }

    private static Row read(
            CqlSession session, PreparedStatement select,
            UUID tenantId, UUID sessionId) {
        return session.execute(
            select.bind(tenantId, sessionId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true))
            .one();
    }

    @Test
    void allWrittenCellsExpireWithoutRefresh()
            throws Exception {
        UUID tenantId = UUID.randomUUID();
        UUID sessionId = UUID.randomUUID();
        Instant issuedAt = Instant.now();

        try (CqlSession session = openLabSession()) {
            PreparedStatement insert = session.prepare(
                "INSERT INTO ttl_lab.sessions_by_id " +
                "(tenant_id, session_id, owner_token, " +
                "state, issued_at, expires_at) " +
                "VALUES (?, ?, ?, ?, ?, ?) USING TTL ?");

            PreparedStatement select = session.prepare(
                "SELECT state, owner_token, " +
                "TTL(state) AS ttl_left " +
                "FROM ttl_lab.sessions_by_id " +
                "WHERE tenant_id = ? AND session_id = ?");

            // Short TTL test strictly for staging/lab.
            session.execute(insert.bind(
                    tenantId, sessionId, "lab-owner",
                    "ACTIVE", issuedAt,
                    issuedAt.plusSeconds(8), 8)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(false));

            Row initial =
                read(session, select, tenantId, sessionId);
            assertNotNull(initial);
            assertEquals("ACTIVE", initial.getString("state"));
            assertTrue(initial.getInt("ttl_left") > 0);

            // Poll up to 20 seconds; avoid brittle ms timing assertions.
            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(20);
            boolean gone = false;

            while (System.nanoTime() < deadline) {
                Row current =
                    read(session, select, tenantId, sessionId);
                if (current == null) {
                    gone = true;
                    break;
                }
                Thread.sleep(400); // Inside JUnit test only.
            }

            assertTrue(gone,
                "Expected fully TTL-written session to expire");
        }
    }

    @Test
    void permanentColumnCanOutliveExpiringState()
            throws Exception {
        UUID tenantId = UUID.randomUUID();
        UUID sessionId = UUID.randomUUID();
        Instant issuedAt = Instant.now();

        try (CqlSession session = openLabSession()) {
            PreparedStatement insert = session.prepare(
                "INSERT INTO ttl_lab.sessions_by_id " +
                "(tenant_id, session_id, owner_token, " +
                "state, issued_at, expires_at) " +
                "VALUES (?, ?, ?, ?, ?, ?) USING TTL ?");

            PreparedStatement updateOwner = session.prepare(
                "UPDATE ttl_lab.sessions_by_id " +
                "SET owner_token = ? " +
                "WHERE tenant_id = ? AND session_id = ?");

            PreparedStatement select = session.prepare(
                "SELECT state, owner_token " +
                "FROM ttl_lab.sessions_by_id " +
                "WHERE tenant_id = ? AND session_id = ?");

            session.execute(insert.bind(
                    tenantId, sessionId, "temporary",
                    "ACTIVE", issuedAt,
                    issuedAt.plusSeconds(8), 8)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(false));

            // Omits USING TTL on a table with default TTL = 0.
            session.execute(updateOwner
                .bind("persistent", tenantId, sessionId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM));

            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(20);
            Row observed = null;

            while (System.nanoTime() < deadline) {
                observed = read(
                    session, select, tenantId, sessionId);
                if (observed != null
                        && observed.getString("state") == null) {
                    break;
                }
                Thread.sleep(400);
            }

            assertNotNull(observed);
            assertNull(observed.getString("state"));
            assertEquals(
                "persistent",
                observed.getString("owner_token"));
        }
    }
}
~~~

### 19.2. Interpreting Test Results Within Scope

Test 1 confirms on the lab cluster that writing **all non-key cells with TTL** hides the row after expiry + buffer. Test 2 proves an **un-TTL'd column update** keeps the row alive after `state` expires.

**Never extrapolate from these two tests alone that:**

- Production RF=3 / multi-DC replicas are cleanly repaired.
- `gc_grace_seconds` safely covers prolonged outages.
- SSTable tombstones physically purged from disk.
- Application caches or search indexes cleared data.
- Every Java DAO preserves TTL and timestamps identically.

Maintain separate suites for **concurrent delete/reinsert**, **mixed TTL/default TTL**, **timeout retries**, and multi-replica faults.

### 19.3. Preventing Flaky TTL Tests

- Mint fresh UUID keys per test case; never reuse stale rows.
- Pre-create schemas cleanly rather than firing `CREATE TABLE` concurrently from worker threads.
- Pick a TTL long enough that initial `INSERT` and verification read complete comfortably, plus margin.
- Poll until deadline rather than asserting exact 8,000 ms sleep cutoffs.
- Fail/mark inconclusive on `ReadTimeout`/`Unavailable`—never interpret errors as row expiry.
- Anchor timelines to UTC timestamps and live `TTL()` probes.
- Isolate concurrent suites from shared destructive `TRUNCATE`/cleanup jobs.
- Recognize RF=1 proves CQL TTL behavior only, zero replica divergence or zombie safety.
- Disable automatic retries or speculative execution on TTL-refreshing mutations.
- Under slow CI load where TTL expires before initial read finishes, lengthen lab TTL rather than deleting assertions.

## 20. Distributed Fault Testing: Replica Missing a `DELETE`

Testing **zombie risk** shouldn't be an automated JUnit test killing cluster nodes indiscriminately. Controlled drills belong in **orchestrated staging** with clear permissions, health checks, and recovery plans.

### 20.1. Prerequisites

- Lab cluster running at least **RF=3 in one DC** with ample disk and network headroom.
- Verified backup/snapshot/restore procedures inside the lab.
- Dedicated synthetic test table holding zero PII.
- Approved runbook to toggle one replica offline/online cleanly.
- Recorded `gc_grace_seconds`, repair cadence, compaction strategy, and token ownership.
- Hard STOP gates for quorum availability, disk free, error spikes, and unintended node outages.
- Tests confined strictly to **one or a few isolated partition keys**.
- Avoid setting `gc_grace_seconds=0` reflexively just to rush zombie reproduction; emphasize **detecting stale replicas and verifying timely repairs** safely instead.

### 20.2. Safer Drill: Impaired Replica Healed Before Grace Expires

Illustrative sequence:

~~~text
T0: INSERT K and verify at target CL.
T1: Via orchestrated fault control, make one replica of K temporarily unavailable.
T2: DELETE K at sufficient CL across surviving replicas.
T3: SELECT at target CL and capture metrics/outcomes.
T4: Restore replica well within gc_grace_seconds.
T5: Run scoped repair per runbook and verify range coverage.
T6: Verify K stays absent and collect server logs.
~~~

**Goal:** validates surviving quorum availability, runbook execution, and safe catch-up inside grace—delivering high operational value without risking uncontrolled corruption.

### 20.3. Zombie Reproduction Strictly on Disposable Clusters

If reproducing genuine tombstone purge + zombie return is required, run strictly on a **disposable test cluster** using synthetic data, pre-taken snapshots, coordinated operators, and release-matched verification—collecting real compaction, repair coverage, and stale-replica logs.

**Never standardize `kill -9`, manual SSTable edits, or `gc_grace_seconds=0` as casual recipes**, and never run them near production.

### 20.4. Classifying PASS / FAIL / INCONCLUSIVE

| Observation | Verdict |
|---|---|
| `DELETE` ACKed, returning replica repaired within grace, K stays gone | **PASS** for the **tested scenario** (doesn't prove every outage duration) |
| Retry/replay consumer re-created K with fresher timestamp | **FAIL** of app versioning/idempotency—not Cassandra zombie |
| Varying reads on K mid-fault | Evaluate against CL, topology, and timeouts; may be transient or a real bug |
| Fault failed to inject or repair logs missing | **INCONCLUSIVE**—never mark PASS |
| Client timed out with unknown delete/write outcome | **UNKNOWN**—reconcile explicitly |
| Row returned post-tombstone purge and stale replica return | Confirmed zombie evidence: **STOP**, lock evidence, escalate incident |

## 21. Designing Java Apps to Prevent Resurrecting Deleted Data

### 21.1. Hard Deletes vs. Soft Deletes Carry Different Contracts

**Hard deletes** (`DELETE` CQL) write tombstones honoring timestamp order—without notifying HTTP caches, search indexes, or companion denormalized tables automatically.

**Soft deletes** flip `deleted_at` or `is_deleted` filters in queries, preserving business auditability while retaining physical payload bytes—which **violates true erasure/retention mandates** unless paired with hard cleanup. Verify legal privacy and DR rules carefully.

A controlled **deletion ledger** can safely track deletions:

~~~text
business_key
deletion_request_id
deletion_version
deletion_effective_at
projection_cleanup_status
retention_policy
~~~

These fields illustrate a **logical ledger model**, not built-in Cassandra metadata. Retention of deletion proofs themselves must be bounded cleanly without retaining erased PII payloads.

### 21.2. Blocking Stale Event Replay

~~~text
OrderCreated(v1)  -> INSERT K
OrderDeleted(v5)  -> DELETE K
OrderCreated(v1)  -> late consumer replay -> INSERT K (bug!)
~~~

Enforce event IDs plus monotonic versions/sequences per business key, a single source of deletion truth, strict rejection of **stale versions** following deletes, idempotent event handlers, and consistent outbox/CDC reconciliation.

**LWT/CAS** guarding a revision column on one partition enforces state transitions cleanly—remembering it never spans multi-table or message-broker boundaries atomically.

### 21.3. Never Rely on TTL Alone as an Access-Control Gate

Whenever sessions or permissions must expire by a hard deadline, enforce explicit **`expires_at`** or authority checks in application services—even if a partial CQL row lingers due to non-TTL sibling columns.

Align downstream HTTP/API caches to never exceed `expires_at`.

### 21.4. Audit TTL Behavior Across Every Code Path

Java backends often mix ORM `save()`, custom CQL queries, mappers, and batch consumers. During reviews, check:

- Does one service call `INSERT USING TTL` while another runs un-TTL'd `UPDATE`s?
- Do full-entity ORM saves overwrite previously expired columns?
- Do retry loops pass full static TTLs instead of remaining time to `expires_at`?
- Are all TTL bind values definitely in **seconds** on every non-key field?
- Do backfill/CDC/worker jobs bypass primary DAO TTL decorators?
- Do denormalized tables, caches, and search indexes clean up in lockstep with logical deletes?
- After caller timeouts, do clients replay mutations using **fresh timestamps**?

Focus on the **end-to-end data lifecycle**, not one isolated query.

### 21.5. TTL Is Not a Distributed Lock

An expiring row never guarantees single-worker lease ownership: read-then-write races, clock skew, TTL refreshes, and GC/network stalls break naive leases. Use dedicated LWT fencing/revisions with explicit `UNKNOWN` reconciliation (and never trust `setIdempotent(true)` to magically make leases safe).

## 22. Anti-Patterns When Handling `DELETE` and TTL

| Anti-pattern | Risk | Better alternative |
|---|---|---|
| "`DELETE` succeeded so all replicas erased disk bytes" | Ignores tombstones and CL | Separate logical delete, convergence, and purge |
| "`TTL 120` deletes the row regardless of other columns" | Per-cell TTL and liveness rules | Inspect every column and writer |
| "TTL expired so disk usage must drop immediately" | Compaction lag and snapshots hold SSTables | Track query visibility separately from compaction |
| "Set `gc_grace_seconds=0` to reclaim disk" | Zombie resurrection on missed deletes | Model outages, repair cadence, and version limits |
| "Force `nodetool compact` to fix zombies" | High I/O without knowing domain truth | Preserve evidence and isolate truth source |
| "Run blind repair right away" | Can spread resurrected stale data globally | Reconcile from authoritative records per DBA runbook |
| "Trust repair cron without checking range coverage" | Failed/skipped ranges miss grace | Monitor range/DC completion strictly |
| "Assume every reappearing row is a zombie" | Reinserts, caches, and per-cell TTL dominate | Diagnose via timestamps and source paths |
| "Send `DELETE` with massive future timestamp" | Blocks legitimate future writes indefinitely | Fix clock/timestamp sources and versioning |
| "Retry `INSERT` with fresh UUID after timeout" | Duplicate logical records | Reuse stable request IDs and reconcile |
| "Retry static 120s TTL after 90s lag" | Extends retention past domain SLA | Anchor to fixed `expires_at` and compute remaining TTL |
| "Check `TTL(state)` alone to conclude whole-row expiry" | Sibling columns keep row alive | Inspect all columns and mutation history |
| "Row seen in API proves row exists in primary table" | Stale cache, index, or projection | Run direct PK `SELECT` and verify downstream |
| "Reads differ across CLs so silently bump/drop CL" | Breaks consistency contracts | Keep CL documented and fix replica divergence |
| "Hunt deleted keys with `ALLOW FILTERING`" | Cluster-wide scans cause timeouts | Query strictly via known PKs and audit logs |
| "Blindly call Spring Data `save()`" | Can resurrect expired fields without TTL | Audit actual generated CQL and mappings |
| "Outage > grace automatically guarantees zombie" | Needs proof of purge and stale return | Collect compaction, repair, and mutation timeline |
| "Restore old snapshot without delete replay" | Resurrects legally deleted records | Reconcile DR cutoff, deletes, and RPO/RTO |
| "Delete primary table only, skipping denormalized views" | Data remains accessible via lookup paths | Maintain projection cleanup pipelines |
| "Wipe snapshots before verifying remote backups" | Destroys last clean recovery point | Require verified manifests and retention sign-off |

### 22.1. `DELETE` Is Not a Multi-Table Transaction

If orders live in both `orders_by_tenant_day` and `order_lookup_by_id`, issuing two separate `DELETE`s risks partial failure on timeouts—Cassandra never rolls back across independent tables.

Implement event-driven projection cleanup, idempotent retries, and reconciliation; privacy deletions in particular must inventory every table, cache, index, and archive holding the record.

### 22.2. Backups and Repairs Are Not Undo Buttons

Backups help only after verifying manifests, cutoffs, checksums, and restore drills; repair merely converges existing SSTable state without understanding domain validity. Before large-scale recovery, verify:

- Authoritative truth source, RPO/RTO cutoff, and post-snapshot valid writes.
- Newer deletion requests post-snapshot that must replay post-restore.
- Privacy/compliance scrubbing requirements before reopening reads.
- Isolation, CQL validation, and controlled traffic cutover steps.

## 23. Diagnostic Exercises and Suggested Answers

### Exercise 1 — Node `DOWN` Longer Than `gc_grace_seconds`

Table has `gc_grace_seconds=10d`. Replica C stayed `DOWN` 13 days while `DELETE K` ACKed at `LOCAL_QUORUM`. Once C rejoins, `SELECT` occasionally returns K.

**Question:** Can you declare confirmed zombie resurrection immediately?

**Answer:** Not yet. It is a **high-risk candidate**, yet you still must confirm whether compaction actually purged tombstones on healthy replicas, check repair coverage, and rule out newer timestamp reinserts or caches. Lock evidence and inspect compaction/repair/mutation timelines before restoring from authoritative sources.

### Exercise 2 — Weekly Repairs Partially Failing

Weekly repairs ran, yet the last three runs reported failed token ranges including partition K—while the team logged "weekly repair ran".

**Question:** Are tombstones safely protected before purge?

**Answer:** No. Cron triggers never prove **successful range coverage**. Inspect covered ranges, per-replica/DC status, and errors, tuning cadence, alerts, and `gc_grace_seconds` around real recovery SLAs.

### Exercise 3 — `state` Expired While Row Still Appears

`INSERT session USING TTL 120`. After 150s, CQL returns `state=null`, `owner_token='worker-A'`, `TTL(state)=null`.

**Question:** Did Cassandra malfunction on TTL?

**Answer:** No. `state` expired properly, while `owner_token` was likely written/rewritten without a TTL. Inspect per-column `TTL()`/`WRITETIME()`, background `UPDATE`s, and table `default_time_to_live`.

### Exercise 4 — Live Column Shows `TTL(column) = null`

App expects a column to carry TTL 600, yet `SELECT` returns `state='ACTIVE'` and `TTL(state)=null`.

**Question:** What are the realistic causes?

**Answer:** Another writer updated the cell without TTL (or with `USING TTL 0`), `default_time_to_live` was 0/misunderstood, or an ORM mapper rewrote all fields. Diff live table options, CQL statements, `WRITETIME()`, and writer logs.

### Exercise 5 — Session Persists Due to Heartbeat Writes

`T0`: write `state` with TTL 120. `T0+60`: heartbeat writes `state` with TTL 120. `T0+130`: `state` still returns alive.

**Question:** Is this a Cassandra bug?

**Answer:** No. The heartbeat created a new mutation resetting the 120s TTL at `T0+60`. Anchor hard deadlines to immutable **`expires_at`** and pass remaining TTL rather than renewing full 120s intervals.

### Exercise 6 — `DELETE` Carrying Lower Timestamp Than `INSERT`

An `INSERT` wrote with timestamp=900; a subsequent `DELETE` carried timestamp=800.

**Question:** Why does `SELECT` keep returning the row?

**Answer:** Cassandra evaluates mutation ordering by write timestamp, not HTTP wall-clock order; tombstone 800 loses to cell 900. Fix timestamp generation and clock sync rather than pushing fake giant future timestamps.

### Exercise 7 — Row Reappears After 2 Minutes on a Healthy Cluster

Audit logs show `DELETE` at 10:00 and a background consumer `INSERT`ing the identical PK at 10:02 with a newer timestamp.

**Question:** Investigate `gc_grace_seconds` first or the consumer writer?

**Answer:** The writer. Direct evidence shows a newer reinsert—fix consumer versioning, idempotency, and deletion ledgers rather than chasing zombie theories.

### Exercise 8 — Disk Fails to Shrink Post-TTL

A 24h-TTL table stops returning two-day-old records in `SELECT`, yet disk utilization stays high alongside large snapshot tags.

**Question:** Is TTL broken?

**Answer:** No. Logical expiration hides cells right away while SSTable bytes linger until compaction and snapshot cleanup release hardlinks. Check compaction queues, snapshot policies, and remote backup verification before clearing old snapshots.

### Exercise 9 — Does TWCS Guarantee Dropping SSTables Exactly on Day 7?

A TWCS table uses a 7-day TTL while backfills frequently insert older keys carrying newer timestamps across windows.

**Question:** Are all SSTables guaranteed erased right on day 7?

**Answer:** No. Late writes, overlapping SSTable windows, mixed TTLs, tombstone safety guards, and compaction behavior alter window reclamation. Audit actual write distributions, timestamps, and release TWCS rules.

### Exercise 10 — `LOCAL_ONE` vs. `LOCAL_QUORUM` Divergence

During an outage, Client A reads `LOCAL_ONE` and sees row K; Client B reads `LOCAL_QUORUM` and gets 0 rows.

**Question:** Does B's result prove all replicas deleted K?

**Answer:** No. Quorum succeeded across healthy deleted replicas while a lagging replica missed the delete. Inspect RF/DC, node health, repair scope, and mutation delivery without tampering silently with CL.

### Exercise 11 — Can Repair Deduce Deleted Intent After Tombstones Purge?

Tombstones purged; a stale replica holding the old order rejoins and repair begins.

**Question:** Can Cassandra repair figure out the order was supposed to stay deleted?

**Answer:** Not from SSTables alone once tombstones vanish. Repair merely synchronizes existing state; only external truth sources (audit/deletion ledgers) know deleted intent for reconciliation.

### Exercise 12 — Java Catches Timeouts as Expired Sessions

Java code catches every `SELECT` exception and returns `null`, causing API layers to assume sessions expired.

**Question:** Is that semantically sound for TTL enforcement?

**Answer:** No. Timeouts/`Unavailable`/`AllNodesFailed` yield **`UNKNOWN_READ_RESULT`**, completely distinct from a clean empty row. Return explicit errors or fail closed per security policy without falsely logging "TTL expired".

### Exercise 13 — Two Denormalized Tables for One Order

App deletes from `orders_by_tenant_day`, yet an API reading `order_lookup_by_id` keeps returning the order.

**Question:** Are unpurged tombstones to blame?

**Answer:** Unlikely. Two separate denormalized tables require synchronized deletion/projection workflows—inspect deletes, CDC consumers, and query routing per table.

### Exercise 14 — Time-Zone Display Confusion

`expires_at` stores `08:00Z`, while a UI in Vietnam displays `15:00` alongside Java logs reading `expire 08:00`, sparking complaints that TTL lagged 7 hours.

**Question:** What do you check first?

**Answer:** Normalize every timestamp onto **`Instant`/UTC**, verify UI formatting vs. UTC storage, and inspect live `TTL()` seconds directly (`TTL()` is purely relative seconds, unaffected by time zones).

### Exercise 15 — Bumping `gc_grace_seconds` After the Fact

Tombstones likely purged; a DBA suggests raising `gc_grace_seconds` from 1 day to 10 days.

**Question:** Will this restore purged tombstones?

**Answer:** No. Changing `gc_grace_seconds` protects future deletes after change control, never recreating already-purged tombstones. Reconcile business truth from ledgers and fix repair schedules going forward.

### Exercise 16 — Claiming Multi-Node Zombie Safety From One Container

A 5-second TTL test passes on a single-node RF=1 Testcontainers instance; teams claim zombie safety for RF=3 with 10-day outages.

**Question:** Is that valid evidence?

**Answer:** No. Single-node RF=1 only proves basic CQL TTL syntax; test missed deletes, repair coverage, grace windows, and compaction in real multi-node staging clusters.

### Exercise 17 — Sending a Giant-Timestamp `DELETE` to "Banish" Zombie Data

After spotting zombie/reinserted rows, an engineer issues a `DELETE` stamped years into the future.

**Question:** What is the danger?

**Answer:** Future timestamps poison valid future writes to that key, never clear downstream caches/lookup tables, and still miss offline replicas. Halt reinsert sources, reconcile versions/CLs, and repair properly.

### Exercise 18 — Restoring an Older Snapshot Over Privacy Deletions

Last week's snapshot holds Order K, deleted this week under privacy mandates. Operators propose restoring the snapshot straight to production after disk failure.

**Question:** What safeguards are mandatory?

**Answer:** Restoring blindly resurrects deleted Order K. Restore into an isolated cluster first, replay valid writes and post-snapshot privacy deletions against audit ledgers within RPO/RTO bounds, verify scrubbed state, and only then switch traffic.

## 24. Implementation and Operational Checklist

### 24.1. For Java & CQL Application Code

- [ ] Every writer uses query-aligned primary keys and preserves stable operation IDs across retries.
- [ ] Request IDs, versions, or fingerprints distinguish valid reinserts from stale replays.
- [ ] CQL `INSERT`/`UPDATE`/`DELETE` telemetry logs **query shapes** without leaking sensitive bind values.
- [ ] Clear write-timestamp discipline enforced; zero future-timestamp hacks used to defeat `DELETE`s.
- [ ] Per-column TTL writes audited alongside un-TTL'd `UPDATE`s.
- [ ] Table `default_time_to_live`, explicit `USING TTL`, and `USING TTL 0` verified per release.
- [ ] Domain expiration relies on explicit **`expires_at`** checks rather than SSTable physical purge.
- [ ] Retries keep original request IDs and compute remaining TTL instead of resetting full TTLs.
- [ ] Conditional LWT code clearly separates `applied=true`, `false`, and `UNKNOWN`.
- [ ] Driver `ReadTimeout`/`Unavailable` handled strictly as `ERROR`/`UNKNOWN`, never empty row.
- [ ] Caches, search indexes, and companion lookup tables delete/invalidate cleanly with reconciliation.
- [ ] ORM/Spring Data `save()` behavior tested directly against generated CQL.

### 24.2. For Cassandra DBAs / SREs

- [ ] Documented per-DC RF, local DC, CL contracts, and impacted token ranges.
- [ ] Inspected exact live table options (`gc_grace_seconds`, `default_time_to_live`, compaction).
- [ ] Configured node-outage alerting tracking downtime relative to `gc_grace` and repair cadence.
- [ ] Tracked repair schedules by **verified range coverage success**, not cron exit status alone.
- [ ] Assigned owners and deadlines for any skipped/failed repair ranges.
- [ ] Monitored compaction backlogs, tombstone warnings, free disk, and snapshot retention.
- [ ] Blocked impulsive forced compaction, blind repairs, or `gc_grace`/RF edits mid-incident without approval.
- [ ] Maintained off-cluster backups with verified manifests, checksums, and restore drills.
- [ ] Prepared runbooks handling stale replica returns post-extended outages and state reconciliation.
- [ ] Investigated NTP clock skew or TTL overflow errors promptly.
- [ ] Maintained unified UTC timelines correlating deploys, repairs, streams, compaction, backups, and p99.
- [ ] Never inferred data consistency or TTL correctness solely from `UN` status.

### 24.3. Before Closing an Incident

- [ ] Confirmed whether stale data came from **direct Cassandra reads vs. caches/projections**.
- [ ] Separated **null cells, empty rows, valid reinserts, and zombie data**.
- [ ] Recorded `TTL()` and `WRITETIME()` on relevant live columns where readable.
- [ ] Audited mutation logs/CDC for writes arriving after `DELETE`.
- [ ] For suspected zombies, documented concrete outage, grace, repair, and compaction proof rather than guesses.
- [ ] Identified or cleanly bounded all affected business keys.
- [ ] Verified recovery operations never erased valid deletes or re-exposed sensitive data.
- [ ] Verified passing integration tests covering per-cell TTL, mixed TTLs, retries, and delete/reinsert.
- [ ] Confirmed ring health, quorum, p99, compaction, and repairs returned within operating SLOs.
- [ ] Archived root cause, contributing factors, owners, and preventive safeguards in the postmortem.
- [ ] Recorded unproven items honestly as **`UNKNOWN`**—zero fabricated evidence.

## 25. Summary

**Deleted data reappearing** stems from multiple distinct causes: true **zombie resurrection** happens when tombstones purge before lagging replicas receive `DELETE`s, yet **fresher-timestamp `INSERT`/`UPDATE`s**, message replays/backfills, caches, denormalized lookup tables, and multi-DC/CL lag occur just as often.

**Unexpected TTL behavior** usually traces back to **per-cell TTLs**, `UPDATE`s refreshing TTLs, un-TTL'd column writes, `default_time_to_live`, server-side mutation clocks, clock skew, or misinterpreting `expires_at` vs. storage expiration. Cells disappearing from CQL do not immediately free SSTable disk space—compaction and snapshot policies control physical reclamation.

Reliable triage proceeds systematically from **exact keyspace/table/partition key → CQL `TTL()`/`WRITETIME()` → mutation/`DELETE` timelines → RF/DC and consistency levels → replica outages, repair coverage, and `gc_grace` → compaction/backups → authoritative business reconciliation**. Never drop `gc_grace`, launch blind repairs/compaction, or inject future timestamps without hard evidence and approved runbooks. With Apache Cassandra and Java applications, success means **policy-compliant data accuracy, safely converged replicas, verified retention, and zero resurrection of legitimately deleted records**.
