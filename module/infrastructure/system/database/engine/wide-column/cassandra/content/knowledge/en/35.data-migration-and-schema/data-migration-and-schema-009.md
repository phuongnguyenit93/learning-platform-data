# Data with TTL and Preserving Exact Expiration Times During Migration

> **Chapter:** Migration and Schema  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — exploring Apache Cassandra, the distributed wide-column model, partition keys, query-driven table design, read/write consistency, CQL practice, replication, compaction, repair, troubleshooting, and Java connectivity.

Systems using Apache Cassandra to store login sessions, IoT events, or ephemeral records often attach **TTL (Time To Live)** to values. TTL causes values to expire after a duration. If an application migrates data to a new cluster by reading rows and running `INSERT ... USING TTL 3600` again, a record that has already existed for nearly an hour gets granted **another full hour**. As a result, data outlives its original retention policy—causing business bugs, exposing data that should have expired, or inflating SSTable storage.

This lesson centers on solving one question:

> How do you make data on the target **expire near or at the exact expected source deadline**, instead of restarting the TTL clock at migration time?

Two levels of guarantees must be distinguished:

- **Preserving physical SSTable metadata**, including expirations/tombstones and timestamps, via a compatible backup/streaming path: capable of preserving intrinsic expiration times when format, schema, and mutation history conditions are met.
- **Migrating through the CQL layer**: sees only live data and **remaining** TTL. You can recompute remaining lifetime to approximate the expiration deadline, but you should not claim second-exact precision or recover purged tombstone history without supplemental metadata.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish original TTL, remaining TTL, absolute expiration deadline, and write timestamp.
2. Explain **per-cell/per-value** TTL semantics, table-level `default_time_to_live`, `USING TTL`, and `UPDATE` behavior.
3. Use `TTL(column)` and `WRITETIME(column)` to inspect CQL metadata and understand limitations when computing deadlines.
4. Compare `cqlsh/driver/DSBulk` migration against snapshots + SSTable streaming, knowing when TTL windows must not be extended.
5. Design backfill + CDC/dual-write with watermarks, resolving concurrent writes, deletes/tombstones, and idempotency.
6. Practice CQL and Java Driver 4.x to compute target TTL from remaining time, measure skew, and handle near-expiry records.
7. Build a verification checklist covering RPO/RTO, node clocks, RF/CL, topology, TTLs, tombstones, and post-cutover checks.

## 2. Four time concepts that must stay separate

### 2.1. TTL belongs to values, not one clock for the entire partition

Cassandra lets you attach TTL on CQL writes:

~~~sql
INSERT INTO sessions_by_user (user_id, session_id, token)
VALUES (11111111-1111-4111-8111-111111111111,
        22222222-2222-4222-8222-222222222222,
        'sample-not-a-real-secret')
USING TTL 3600;
~~~

This is an illustrative example—**never put real authentication tokens into logs or documentation**. TTL 3600 is a **seconds** lifetime for the values written by this mutation, not a promise that bytes are physically erased from disk at second 3600.

Each non-key column can have a different TTL history:

~~~sql
-- UPDATE changes only the TTL of the column(s) written in this mutation.
UPDATE sessions_by_user
USING TTL 300
SET last_seen_state = 'ACTIVE'
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

After this statement, `token` may still have nearly an hour left while `last_seen_state` lives only five more minutes. Never store one `row_ttl` field and apply it to every column if the source carries differing per-column TTLs.

**Primary keys are not arbitrary data cells with independently tunable TTLs.** Clustering/partition keys identify rows; row liveness markers and live cells govern read results. When migrating partial values, verify whether rows remain visible after individual cells expire rather than assuming "the whole row expires together."

### 2.2. From write time to expiration deadline

Consider an illustrative UTC timeline:

| Time | Event | Estimated remaining TTL |
|---|---|---:|
| 10:00:00 | Write cell with `TTL = 7200` seconds | 7200 seconds |
| 10:45:00 | Read data from source | 4500 seconds |
| 10:47:00 | Begin replay into target cluster | ~4380 seconds |
| 12:00:00 | Desired expiration deadline | 0 |

Writing to target at 10:47 with `USING TTL 7200` lets data live until **12:47**—an unintended 47-minute extension. Using the remaining TTL sampled at 10:45 (4500 seconds) after a 2-minute migration delay lets data live until **12:02**—still an unintended extension.

Conclusion: **TTL is a relative duration evaluated at write time**, whereas retention policies require an **absolute deadline**. A simple operational formula:

~~~text
deadline_estimated = source_observation_time + source_remaining_ttl
target_ttl_seconds  = floor(deadline_estimated - target_write_time) - safety_margin
~~~

Whenever `target_ttl_seconds <= 0`, **do not insert the expired or nearly-expired value**. Taking `floor` avoids rounding up and accidentally extending lifetime. In practice, latency also occurs between computing TTL and the target server receiving the mutation; apply a safety margin and measure skew.

### 2.3. Three non-interchangeable timestamps

| Quantity | What it is | Migration usage |
|---|---|---|
| **Write timestamp** | Microseconds used by Cassandra for mutation conflict resolution; read via `WRITETIME(column)` | Preserves mutation ordering when needed, but **cannot derive expiration deadlines** |
| **Remaining TTL** | Seconds left before the current cell expires; read via `TTL(column)` | Can estimate deadline relative to observation time |
| **Local expiration/deletion time** | Metadata governing expiration and tombstone/compaction | Crucial when migrating **SSTable metadata**; not directly exposed via ordinary CQL SELECT |

Applications can explicitly supply `USING TIMESTAMP` in the past or future. Therefore, **never compute expiration deadlines as `WRITETIME + original TTL`** unless the system carries extra provenance metadata and a verified clock model. In Cassandra, conflict-resolution write timestamps are distinct from the node clock used to compute TTL expiration on write.

### 2.4. TTL expiry does not immediately free disk space

Once TTL expires, a cell stops appearing as live data; expired metadata remains in SSTables and behaves similarly to tombstones. Physical space reclamation depends on compaction, `gc_grace_seconds`, SSTable overlap, and replica safety. **Never use whether disk usage dropped** as proof of whether a cell has logically expired.

~~~mermaid
flowchart LR
    A["Write with TTL"] --> B["Reads see live cell"]
    B --> C["TTL counts down"]
    C --> D["Deadline: cell logically expires"]
    D --> E["Tombstone/expired metadata stays in SSTables"]
    E --> F["Eligible compaction physically reclaims bytes"]
~~~

## 3. Inspecting metadata with CQL

### 3.1. TTL(column) and WRITETIME(column)

For a regular scalar column:

~~~sql
SELECT payload,
       TTL(payload) AS ttl_seconds,
       WRITETIME(payload) AS write_time_us
FROM mig_lab.events_source
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;
~~~

Expected **semantic** result (not fixed numbers):

| Field | Example | Explanation |
|---|---|---|
| `payload` | `temperature=21` | Live value at read time |
| `ttl_seconds` | 421 | 421 seconds remaining (integer-second granularity) |
| `write_time_us` | 1795249800000000 | Cell version/conflict timestamp, microseconds |

Note `TTL(column)` returns **`null`** if the value has no TTL; `null` does not mean `0`, nor does it prove a live cell exists if the value itself is null. `WRITETIME` returns the current value's write timestamp. Once a cell expires, queries stop returning it as live; you **cannot use ordinary SELECT queries to recover lost tombstones or expired cells**.

For non-frozen collections or UDTs, TTL/WRITETIME can vary across elements/fields; exact syntax and return types depend on Cassandra version and column type. A migration tool that copies `TTL(collection)` as one scalar integer easily breaks semantics. This lesson uses **scalar columns** for clarity; collections/UDTs require dedicated handling.

### 3.2. Information CQL does not fully expose

CQL returns current state at the query's consistency level—**not a complete mutation log**. When:

- Two cells in one row have different TTLs,
- A cell was `DELETE`d and only an SSTable tombstone remains,
- Records were written with backdated or future-dated timestamps,
- Replicas diverge due to Down nodes or pending repair, or
- Live updates/deletes run concurrently while paging across millions of partitions,

a single SELECT never guarantees a cluster-wide consistent point-in-time snapshot. For **strict retention** and mandatory delete history, choose a migration path preserving SSTable metadata or a properly engineered CDC/changelog rather than relying solely on `SELECT *`.

### 3.3. Clocks and resolution

TTL counts in whole seconds, and expiration metadata has SSTable-format and version limits. Java clients call `Instant.now()` on application hosts while remaining TTL comes from Cassandra replicas on the read path; clock skew, network latency, rounding, and batching introduce estimation error.

Therefore:

1. Maintain NTP/clock-drift monitoring across nodes and migration hosts.
2. Measure read start/end, replay start/end, queue latency, and cross-cluster delay.
3. Define acceptable error bounds (e.g., "never extend by more than 2 seconds," "never drop >1% of valid live records"); **never claim exact-to-the-millisecond preservation** via relative CQL TTLs.
4. When policy demands **never extending lifetimes**, apply a safety margin, skip near-expiry rows, and verify target TTLs post-write.

## 4. When to use TTL 0 or default_time_to_live?

### 4.1. Table-level default TTL

Cassandra supports the table property:

~~~sql
CREATE TABLE mig_lab.events_source (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0;
~~~

`default_time_to_live = 0` means the table **applies no default expiration**. If set to, say, `default_time_to_live = 86400`, values written without an explicit TTL receive that default per Cassandra version semantics.

Migrating to a target table with a different default TTL than the source can cause:

- Permanently stored source values to **expire** on the target.
- 1-day-expiring source values to become permanent if target default is 0 and the loader omits TTL.
- Rows/cells with differing TTLs to collapse onto one shared lifetime if the loader applies `USING TTL` statement-wide.

**Mandatory:** compare schemas and defaults before loading. Never guess `default_time_to_live` edits to "preserve TTL"—inspect actual cell-level data.

### 4.2. USING TTL 0 is not DELETE

In CQL, `USING TTL 0` means **apply no TTL** to the written value; if the table has a default TTL, `TTL=0` overrides that default for the mutation. It does **not** mean "expire immediately" or "delete value."

~~~sql
-- Example when this value should have no TTL:
INSERT INTO mig_lab.events_target
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'no-expiration'
) USING TTL 0;
~~~

When the source returns `TTL(payload) IS NULL`, verify it represents a **genuine live cell with no TTL**, not a deleted or absent cell. Then write with no TTL **intentionally**. If the target already holds older data for that key, write-timestamp preservation and version conflicts become critical.

### 4.3. Maximum TTL and the Year 2038 issue

Cassandra versions and SSTable formats impose limits on representable expiration timestamps and large TTLs; Cassandra documentation notes **2038-related expiration date overflow** behavior in specific versions. Never plan multi-decade TTLs without checking your exact release, `max_ttl`, overflow behavior, and boundary tests. For multi-year retention, use an explicitly verified retention model rather than treating huge TTL integers as a default solution.

## 5. Choosing the migration path: SSTable metadata or CQL replay?

### 5.1. Comparison table

| Migration path | Preserves original expiration? | Can change schema/partition key? | Key risks |
|---|---|---|---|
| **Snapshot/SSTable backup + compatible restore/streaming** | Preserves SSTable TTL, timestamp, and tombstone metadata | **Limited**; schema and SSTable format must match | Missing token ranges, bad snapshot timing, stale tombstones, incompatible loader |
| **`sstableloader` on valid SSTables** | Streams SSTable data with embedded metadata rather than issuing fresh CQL TTL writes | Mainly when schema/format match; partition key changes need custom design | Wrong target schema, RF/CL, missing file components, incomplete source |
| **CQL SELECT → INSERT/UPDATE** | **Not exact by default**; must compute remaining TTL minus lag | Flexible schema transforms, new partition/clustering keys | TTL resets, missing tombstones, live-write races, rows expiring mid-load |
| **CSV/JSON/DSBulk export/import** | Depends on **tool/version** mapping and TTL/timestamp preservation options | Good for tabular transforms | Exports normally capture only live values; omit TTL unless configured |
| **CDC/dual-write + backfill** | Can carry retention policies/deadlines if events include right metadata | Flexible and supports online cutover | Event ordering, duplicates, deletes, clock skew, race conditions |

**Never assume bulk tools preserve TTLs automatically.** A CSV line with `payload` and `event_time` carries no internal TTL. If a tool offers TTL or writetime options, verify **exact per-cell support and timestamp semantics** in that tool version.

### 5.2. SSTable path for preserving intrinsic metadata

SSTables already store timestamps, expirations, and tombstones, making them **better for avoiding TTL resets** when the data model stays compatible. Cassandra snapshots capture immutable SSTable files; docs describe `nodetool snapshot`, backups, and restores via `sstableloader` or SSTable workflows.

On a **lab** cluster:

~~~bash
# Run on the managed node; creates a local snapshot on that node only.
nodetool snapshot -t ttl_migration_lab mig_lab

# Inspect created snapshots.
nodetool listsnapshots
~~~

To restore to a target, copy **all SSTable components** into the matching staging path, verify schema/partitioner/format, and run a compatible `sstableloader`:

~~~bash
# Conceptual example: replace host/path with valid lab staging values.
# Check sstableloader --help on your exact tool binary.
sstableloader --nodes 192.0.2.10 /staging/mig_lab/events_source
~~~

`192.0.2.10` is a documentation-range IP, **not a live Cassandra node**. Directory/path names determine target keyspace/table per tool rules; this snippet only illustrates syntax and will not run without valid SSTables and target schema. Never place staging files inside Cassandra's live managed data directory if tool docs warn against it.

Checklist before concluding TTLs are preserved:

1. Source/target versions and SSTable formats are compatible, with matching schemas (types, keys, table metadata, compression).
2. Snapshots cover **all required token ranges** across needed replicas/nodes, accounting for ongoing writes and schema agreement.
3. Still-needed **tombstones** are not lost; choose capture points and `gc_grace_seconds` carefully.
4. Verify on the target cluster that near-expiry values **did not have their lifetimes extended** by streaming.
5. With CDC/cutover, handle mutations occurring **after the snapshot**. Static snapshots omit writes and deletes arriving during copy.

**Warning:** `sstableloader` cannot transform `(user_id)` into `(tenant_id, day_bucket)` for a redesigned schema like a SQL ETL transform. Changing the data model usually forces logical rewrites along with explicit trade-offs around exact TTL preservation.

### 5.3. CQL path when the data model must change

When changing partition keys, clustering keys, or normalizing payloads, read **live** rows and write to the new query-driven table:

- Read `TTL(column)` and, where mutation ordering is required, `WRITETIME(column)` **for every relevant column**.
- Compute target TTL from the deadline rather than copying the policy's initial TTL.
- Split cells with different TTLs into separate mutations if one `INSERT`/`UPDATE` cannot express distinct metadata.
- Skip expired cells; handle deletes/tombstones via an auxiliary changelog or load into a **clean target** with a controlled cutover.
- Pick a strategy against overwriting live writes: deterministic timestamps, CDC ordering, fencing, or write barriers at cutover.

**Fundamental limit:** once absolute expiration metadata has been lost, no CQL inference can reconstruct metadata that was never exported.

## 6. CQL algorithm: preserving approximate deadlines safely

### 6.1. One live cell

For a cell with TTL, pseudocode:

~~~text
1. source_read_started_at = clock.now()
2. SELECT value, TTL(value), WRITETIME(value) FROM source WHERE full_pk = ...
3. If row/value is no longer live -> do not insert cell into target.
4. If TTL(value) is null -> value has no TTL;
   write without TTL only if target schema and source semantics match.
5. If TTL(value) > 0:
     estimated_deadline = source_read_started_at + TTL(value)
     remaining = floor(estimated_deadline - clock.now()) - margin
     if remaining <= 0 -> skip / reconcile delete; NEVER write TTL 0
     if remaining > 0  -> write USING TTL remaining
6. Log lag, near-expiry skips, errors, and retries.
7. Read back TTL(target_value) and compare against source deadline within tolerance.
~~~

Recording `source_read_started_at` before the server reads TTL produces a **conservative estimate** (avoiding accidental extension), though it remains approximate due to coordinator/server queuing, whole-second granularity, clock skew, and write latency. For long paged scans, refresh the observation timestamp **per fetch/page**; using one `t0` across hours makes estimates overly conservative and drops valid rows.

### 6.2. Never use TTL 0 for expired cells

A very dangerous mistake:

~~~text
remaining_seconds <= 0
  -> WRITE USING TTL 0   # WRONG: TTL 0 means NO EXPIRATION!
~~~

Correct behavior:

~~~text
remaining_seconds <= 0
  -> DO NOT WRITE live value
  -> if target already holds an older version at that key, run delete/reconciliation
     via safe timestamps/CDC/fencing
~~~

Into an **empty** target table, skipping expired cells may suffice for backfill. Into a **populated** target table, skipping without removing an older copy lets the target retain data **longer than the source**. Always account for existing target state and deletion history.

### 6.3. Safety margins are trade-offs, not absolute proofs

Suppose the source reports 30 seconds remaining, client + queue + replay delay is 2 seconds, and safety margin is 2 seconds:

~~~text
estimated target TTL = floor(30 - 2) - 2 = 26 seconds
~~~

If the write applies within expectations, the target expires **slightly earlier than or close to** the source rather than extending. Yet if source/target clocks drift significantly or a request retries minutes later, the formula still fails. When deadlines **must be strictly exact**, use verified SSTable metadata streaming, or store an explicit `expires_at_utc` attribute enforced by applications/read paths (pairing with Cassandra TTL for storage cleanup).

### 6.4. Do not confuse WRITETIME with TTL

CQL supports:

~~~sql
-- Illustrative syntax for a scalar value:
INSERT INTO mig_lab.events_target (
    device_id, day_bucket, event_time, event_id, payload
) VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 300 AND TIMESTAMP 1795249800000000;
~~~

**Explanation:** `USING TIMESTAMP` sets the conflict-resolution write timestamp; `USING TTL 300` sets a **relative lifetime starting from this write**. Supplying an old `TIMESTAMP` **does not automatically** make the target expire at the source's original deadline.

In some scenarios, preserving `WRITETIME` prevents backfills from overwriting newer mutations. However, CQL SELECT does not expose row liveness markers, hidden tombstones, or differing per-cell TTLs completely; with concurrent writes/deletes, replaying old timestamps per cell **alone is insufficient** for conflict ordering. You still need CDC/ordering/fencing, version testing, and rollback plans.

## 7. CQL lab: two columns with two different TTLs

### 7.1. Prepare the test cluster

Run in a **lab cluster** on Cassandra 4.x–5.x with `cqlsh` and `nodetool`; examples assume a real datacenter named `dc1` with three nodes. On a single-node lab, adjust RF/CL accordingly rather than setting RF=3 and assuming three-node semantics.

~~~bash
nodetool status
nodetool describecluster
~~~

In `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mig_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS mig_lab.events_source (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0
  AND gc_grace_seconds = 864000;

CREATE TABLE IF NOT EXISTS mig_lab.events_target (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0
  AND gc_grace_seconds = 864000;
~~~

`IF NOT EXISTS` does not alter existing tables. Inspect actual schemas and `default_time_to_live` via:

~~~text
DESCRIBE TABLE mig_lab.events_source;
DESCRIBE TABLE mig_lab.events_target;
~~~

### 7.2. Write data with differing TTLs

~~~sql
INSERT INTO mig_lab.events_source
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 600;

UPDATE mig_lab.events_source
USING TTL 120
SET status = 'TEMPORARY'
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;

SELECT payload, status,
       TTL(payload) AS payload_ttl,
       TTL(status) AS status_ttl,
       WRITETIME(payload) AS payload_writetime,
       WRITETIME(status) AS status_writetime
FROM mig_lab.events_source
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;
~~~

Expected: `payload_ttl` starts near 600 seconds; `status_ttl` starts near 120 seconds. Both `WRITETIME` values can differ. After two minutes, `status` expires while `payload` remains live.

**Critical point:** if a loader combines both into `INSERT ... (payload, status) USING TTL 600`, `status` gets extended from 120 to 600 seconds; using `USING TTL 120` expires `payload` prematurely. For semantic fidelity, write per cell or group cells sharing a deadline while handling markers/tombstones and lag.

### 7.3. Counter-example experiment and proper experiment

**Counter-example — re-applying original TTL on target:**

~~~sql
-- Run in lab only to observe the design flaw, not as a valid migration.
INSERT INTO mig_lab.events_target
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 600;
~~~

If this runs after the source TTL has already ticked down, `TTL(payload)` on target exceeds source. This experiment is **deliberately wrong** to make TTL resets visible.

**Proper relative experiment — computing remaining TTL at load time:**

1. Read `payload_ttl` and `status_ttl` at the start of a copy pass.
2. Record timestamps for read start, read end, write start, and target ACK.
3. Compute TTL **per column** = observed source TTL minus elapsed time and safety margin, **floored** to integer seconds.
4. Execute `INSERT/UPDATE USING TTL <computed_value>` or via the Java Driver; **never** share one TTL across both columns.
5. Compare target `TTL(payload)` and `TTL(status)` against remaining time to the source deadline within test tolerances.
6. Wait past both expirations and verify `status` disappears before `payload`. Remember CQL does not prove physical byte reclamation.

Never hard-code a sampled TTL into a static CQL doc snippet and call it "exact"; TTL ticks every second and varies with migration speed. Only an instrumented application with logging/metrics measures true skew.

### 7.4. Lab recording table

| Field | Expected deadline | Source TTL at read | Target TTL post-write | Estimated skew | Pass? |
|---|---|---|---|---|---|
| `payload` | _record UTC_ | _measured sec_ | _measured sec_ | _sec_ | _fill_ |
| `status` | _record UTC_ | _measured sec_ | _measured sec_ | _sec_ | _fill_ |
| Cell without TTL (if added) | No deadline | `null` | `null` | N/A | _fill_ |
| Expired cell | Passed | No longer live | Must not resurrect | N/A | _fill_ |

Compare **deadlines**, not two raw TTL numbers read at different instants. Checking source 10 seconds later and target immediately post-write creates apparent skew from sampling times; convert both to a common UTC deadline first.

## 8. Java Driver 4.x: preserving TTL on a scalar column

### 8.1. Example preconditions

The example below covers **one row with one scalar `payload` cell**, not a full migration engine. It uses two `CqlSession` objects pre-configured with local DC, TLS, and authentication so no secrets appear in source code. Source and target share matching schemas, `default_time_to_live = 0`, and the target **has no newer writes at the copied key**.

The code reads source TTL, anchors the deadline before the read, then subtracts elapsed time and a margin. `WRITETIME(payload)` is preserved as **the timestamp in this uniform source/target example**. This demonstrates that **timestamps do not replace TTLs**, and is not a complete solution for arbitrary CDC/dual-write conflicts.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// source and target: CqlSessions initialized from secure configuration.
void migrateOnePayload(CqlSession source, CqlSession target,
                       UUID deviceId, LocalDate day, Instant eventTime, UUID eventId) {
    PreparedStatement read = source.prepare(
        "SELECT payload, TTL(payload) AS ttl_remaining, " +
        "WRITETIME(payload) AS wt_us " +
        "FROM mig_lab.events_source " +
        "WHERE device_id = ? AND day_bucket = ? " +
        "AND event_time = ? AND event_id = ?");

    PreparedStatement write = target.prepare(
        "INSERT INTO mig_lab.events_target " +
        "(device_id, day_bucket, event_time, event_id, payload) " +
        "VALUES (?, ?, ?, ?, ?) USING TTL ? AND TIMESTAMP ?");

    Instant startedAt = Instant.now(); // Conservative anchor before server reads TTL.
    Row row = source.execute(read.bind(deviceId, day, eventTime, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)).one();
    if (row == null || row.isNull("payload")) {
        // Source no longer holds a live value; reconcile target if it already exists.
        return;
    }

    String payload = row.getString("payload");
    if (row.isNull("wt_us")) {
        throw new IllegalStateException("Missing writetime for live payload");
    }
    long writeTimeUs = row.getLong("wt_us");

    final int ttlToWrite;
    if (row.isNull("ttl_remaining")) {
        ttlToWrite = 0; // Keep non-expiring cell; does NOT mean delete.
    } else {
        int sourceTtl = row.getInt("ttl_remaining");
        Instant estimatedDeadline = startedAt.plusSeconds(sourceTtl);
        long remaining = Duration.between(
                Instant.now(), estimatedDeadline).getSeconds() - 2L;

        if (remaining <= 0L) {
            // Expired or near-expiry: NEVER write TTL 0 making data permanent.
            return;
        }
        ttlToWrite = Math.toIntExact(remaining);
    }

    target.execute(write.bind(deviceId, day, eventTime, eventId,
                    payload, ttlToWrite, writeTimeUs)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM));
}
~~~

**Mandatory limits and warnings:**

- `sourceTtl` is remaining time when Cassandra observed it; `startedAt` and subtracting 2 seconds form a **conservative estimate**, not a second-exact expiration guarantee on target. Large clock skew or write-queue delays beyond the margin can still extend life unintentionally.
- `Duration.between(...).getSeconds()` truncates toward whole seconds; verify small positive TTL boundaries so `TTL=0` is never emitted accidentally.
- Preserving `writeTimeUs` models cell-version ordering, **yet** fails to copy row liveness markers, hidden tombstones, or differing TTLs on other cells. Never use this code directly for live migrations with concurrent writes.
- When source has no TTL, `ttlToWrite = 0` is valid only when policy intends permanent retention; inspect target schema/default TTL.
- On timeouts/retries, writes may already have applied on some replicas. Retrying with the same writetime but a newly recomputed TTL has subtle effects; use an explicit idempotency/CDC ordering protocol, logging, and verification checks.
- If source payloads hold sensitive data, never log raw payloads or credentials into migration logs.

### 8.2. Minimizing drift across long migrations

Across millions of rows, a real migration program needs:

1. **Bounded concurrency** across source/target to keep coordinator queues within capacity.
2. **Per-page/per-batch observation timestamps**, never one `t0` clock reused over hours.
3. End-to-end latency telemetry from read start → TTL fetch → target ACK, including p95/p99 queue lag.
4. Explicit **near-expiry** policy: skip tiny remaining TTLs while handling stale target records.
5. Proper CL/RF settings, never equating timeouts with rollbacks.
6. Release-specific TTL max bounds, overflow guards, and post-write `TTL(target_column)` checks.

Use **UTC** for deadlines and logs; never compute TTLs from local display clocks subject to DST or timezone ambiguity. While TTL seconds themselves are timezone-agnostic, CSV readers and Java parsers can misinterpret timestamps lacking clear offsets.

## 9. Backfill, CDC, and dual-write: more than copying live rows

### 9.1. Race conditions while the cluster still accepts writes

Suppose during migration:

~~~text
10:00  Backfill reads K = "V1" from source
10:01  App UPDATEs K = "V2" on source and target via dual-write
10:02  Backfill writes K = "V1" into target
~~~

If backfill uses the **current write timestamp** at 10:02, `V1` can beat `V2` even though `V2` is business-newer. Accurate TTL calculation will not save a lost update. Using old `WRITETIME` lets newer target records/tombstones win, yet **this simple trick does not cover all row markers, collections, LWTs, and deletes**.

### 9.2. Controlled cutover workflow

Typical workflow:

~~~mermaid
flowchart TD
    A["Inventory source: schema, TTL, tombstones, CL/RF"] --> B["Create target matching query model"]
    B --> C["Enable reliable CDC/outbox or dual-write"]
    C --> D["Capture watermark and begin backfill"]
    D --> E["Backfill: deadline-based TTL, overwrite guards"]
    E --> F["Replay changes by key/order to new watermark"]
    F --> G["Verify expiries, reads/writes, duplicates, deletes"]
    G --> H["Protocol-based writer fencing/cutover"]
    H --> I["Monitor and retire source after rollback window"]
~~~

**Watermarks** must reflect real mutation stream order, not `Instant.now()` on the migration host—for example, CDC offsets/commit positions or outbox sequence IDs designed for replay. Cassandra does not provide a single global CQL commit sequence across all partitions; cluster-wide total ordering must be engineered externally when needed.

With **dual-write**, the two writes can apply at different times, one side can fail, or retries can invert order; never assume dual-write forms an atomic cross-cluster transaction. You need dead-letter queues, idempotency keys, reconciliation, and divergence remediation.

### 9.3. Deletes and tombstones are a special case

A `SELECT` reads only **live** rows, omitting deletion markers left by `DELETE` or expired TTLs. If the target already contains a previously loaded value and the source deletes it, a **second backfill scan omitting that row** does not delete the value from the target.

To stay safe:

- Migrate into a **clean target** with complete mutation history, or drive explicit delete events via CDC/outbox.
- Preserve deletion timestamps and update order as required; never emit a `DELETE` tombstone with a timestamp older than a cell it must supersede.
- Track `gc_grace_seconds` and repair schedules: deleted data can resurrect if a replica misses deletes too long before compaction purges tombstones.
- For datasets with **very short TTLs**, full backfill may be unnecessary: set a retention cutoff, enable dual-write/cutover, and let old data expire naturally if business rules permit.

### 9.4. Storing business deadlines to decouple from CQL TTL

If a product requires **exact deadlines** across clusters/schemas, consider storing an explicit field:

~~~sql
-- In the new model, add an application-managed business deadline field.
ALTER TABLE mig_lab.events_target
ADD expires_at_utc timestamp;
~~~

This is an illustrative schema-design example only; do not run `ALTER` on production tables without compatibility checks. On write, the app computes `expires_at_utc` from a trusted event/policy clock—**never recomputed from raw TTL on every copy**. Reads enforce `now < expires_at_utc` to suppress expired rows while Cassandra TTL handles background storage cleanup.

**Important:** `expires_at_utc` works only if every read path and access role enforces it. Any CQL client querying the table directly bypasses API filters and can still see rows physically present before TTL cleanup; for sensitive data, enforce **storage-tier and security retention policies**, not just API filtering.

## 10. Testing correctness when migrating TTL data

### 10.1. Mandatory test matrix

| Test case | Source | Expected target | Bug to catch |
|---|---|---|---|
| Plenty of TTL left | Cell with 1h TTL, read after 10 min | Expires at or **slightly earlier** within tolerance | Re-inserting 1h TTL extends life by 10 min |
| Near expiry | 2–5 seconds remaining | Skipped or ultra-short TTL if SLA allows | Writing `USING TTL 0` makes row permanent |
| No TTL | `TTL(column) = null` on live cell | Still no TTL if retention allows | Target default TTL accidentally expires it |
| Two cells, two TTLs | `payload` 600s, `status` 120s | Each cell expires on its own schedule | Applying one TTL to entire row |
| UPDATE resets TTL | Same column rewritten while TTL active | Deadline follows **latest winning mutation** | Using old row's initial TTL |
| DELETE post-snapshot | Source deleted during cutover | Target removes value or holds matching tombstone | Select-only backfill misses deletes |
| Duplicate replay | CDC delivers duplicate | Idempotent result, no lifetime extension | Retry inflates TTL or alters timestamp |
| Concurrent writes | Target receives V2 before V1 backfill | V2 is not overwritten by V1 | Backfill using current write timestamp |
| Different RF/CL | Target has more replicas | Verified across replicas and repair | Trusting a single `CL=ONE` SELECT |
| SSTable migration | Snapshot holds expirations/tombstones | Metadata does not turn into fresh TTLs | Incompatible loader or format conversion |

### 10.2. Metrics to monitor

| Metric group | Examples | Operational value |
|---|---|---|
| Migration rate | Rows/cells/sec, bytes/s, CDC lag, queue depth | Shows whether migration keeps up with source writes |
| TTL correctness | Deadline skew, null-TTL cells, near-expiry skips | Prevents extending data or dropping too early |
| Read/write outcomes | Timeouts, retries, conflicts, duplicate replays | Detects data loss and overwrites |
| Source/target Cassandra | p50/p95/p99, `nodetool tpstats`, disk/compaction load | Protects live application SLOs |
| Tombstones | Tombstones scanned, compaction backlog, repair status | Surfaces read amplification and zombie risks |
| Data coverage | Per-token-range samples, partition counts, diff tables | Prevents missing entire token ranges |
| Clock | Node/client NTP sync offsets, drift alerts | Proves deadline estimates stay within bounds |

When reconciling `TTL(payload)`, record **the exact timestamp of each read** and convert to deadlines. Comparing a 300s source TTL read at 12:00 against a 295s target TTL read at 12:02 and claiming target expires 5s early is wrong—the samples were taken at different times.

### 10.3. How much skew is acceptable?

That is a product and security decision:

- For session caches, **expiring a few seconds early** may be acceptable; **expiring late** can pose risk.
- For multi-month telemetry TTLs, a few seconds of skew may be negligible while retention policy accuracy still matters.
- For sensitive tokens/auth/sessions, enforce expiration at the **authentication/business layer** with exact deadlines; treat Cassandra TTL as storage garbage collection, not your sole security control.
- When regulations mandate deletion at exact deadlines, recognize that logical TTLs, tombstone grace, compaction, and backup retention are distinct—design **snapshot/backup deletion** per policy too.

Never accept "0 timeouts" as a proxy for TTL correctness. A job can finish with zero errors while **every expiration deadline on target was silently extended**.

## 11. Common misconceptions

| Misconception | Why it is wrong | Correct practice |
|---|---|---|
| "Re-insert with the same TTL preserves the deadline" | TTL restarts from zero when target writes | Use deadline/remaining TTL or SSTable metadata |
| "TTL in a column is the original constant" | `TTL(column)` returns **remaining** seconds, counting down | Record read timestamp and subtract migration lag |
| "WRITETIME + TTL gives original expiration" | Write timestamp is a conflict clock and can be customized | Use original expiration metadata or observed remaining TTL |
| "TTL=0 means expire immediately" | `USING TTL 0` means **no TTL** | Skip expired cells; reconcile target if present |
| "One TTL per row is enough" | TTL is per value/cell; columns have independent clocks | Extract per-cell metadata and write separately |
| "If SELECT sees no row, target is deleted" | SELECT omits tombstones/deletes | Replay deletes via CDC/outbox or use clean target |
| "Preserving WRITETIME prevents all races" | Misses row markers/tombstones; LWTs and ordering are subtle | Use CDC ordering + fencing + reconciliation |
| "One node's snapshot holds the whole cluster" | A node holds only its token ranges and replica state | Verify RF/token/node coverage against manifest |
| "SSTable migration can change partition keys" | Streaming copies storage layout without arbitrary transforms | Remodel via CQL/ETL with explicit TTL handling |
| "Once TTL expires, disk shrinks immediately" | Expired cells/tombstones reclaim on compaction | Separate logical expiry from physical disk reclamation |
| "A CL=ONE read proves target matches source" | Replicas may still be out of sync | Read/repair at proper CL/RF and validate multi-range |
| "Matching at cutover time is enough" | Skewed TTLs only fail hours later | Validate before, at, and after expiration deadlines |

## 12. Practice scenarios

### Exercise 1 — Computing target TTL

A cell was written at source at 08:00 with an original TTL of 5400 seconds. The reader observes it at 08:30 with 3600 seconds remaining, and the target write is expected to apply at 08:31:20. Safety margin is 3 seconds. Approximately what target TTL should be used?

**Answer:** roughly `3600 - 80 - 3 = 3517` seconds (assuming synchronized clocks/observations). Writing `5400` extends life; writing `3600` still extends life by ~80 seconds.

### Exercise 2 — Two columns with differing TTLs

A row has `payload` with 500s left and `status` with 50s left. The loader puts both into `INSERT ... USING TTL 500`. What is the bug?

**Answer:** `status` is extended by ~450 seconds; after `status` expires on source, it remains alive on target. Split mutations or group cells sharing a deadline and compute each remaining TTL separately.

### Exercise 3 — TTL expires mid-migration

Source returns TTL 1 second; 4 seconds pass before target write execution. A developer sets `USING TTL 0` to avoid errors. What is the consequence?

**Answer:** TTL 0 means **no expiration**; the value becomes permanent. Do not write already-expired cells, and delete/reconcile any stale target entry via an ordered pipeline.

### Exercise 4 — Backfill after delete

Source held V1 at 10:00. At 10:01 the app DELETEd K. At 10:02 an older backfill batch writes V1 to target using the current write timestamp. What happens and how do you prevent it?

**Answer:** V1 can resurrect on target if target lacks a newer tombstone/timestamp; capture deletes via CDC, use watermarks/fencing, preserve conflict timestamps properly, and guard against backfill overwriting newer writes.

### Exercise 5 — Strict deadline

Policy mandates tokens expire at an exact UTC timestamp within 100 ms tolerance. Cassandra CQL TTL stores whole seconds and the bulk job takes minutes. Can you guarantee 100 ms accuracy using only `TTL(column)` and `INSERT USING TTL`?

**Answer:** No, you cannot guarantee 100 ms precision with those two alone. Store an explicit business deadline enforced by application logic, or use verified precision tooling/metadata; treat Cassandra TTL mainly as second-granularity storage cleanup.

### Exercise 6 — SSTables and partition key changes

Source has `PRIMARY KEY (user_id, event_time)`, target wants `PRIMARY KEY ((tenant_id, day_bucket), event_time, user_id)`. The team plans to run `sstableloader` to auto-generate new partitions while preserving TTL. Is this valid?

**Answer:** No. `sstableloader` streams storage layouts matching compatible schemas and does not perform arbitrary partition-key transformations. Use ETL/CQL with key mapping and cell retention protocols.

### Completion checklist

- [ ] Distinguish original TTL, remaining TTL, WRITETIME, and absolute deadlines.
- [ ] Know how `TTL(column)=null` on a live cell differs from `USING TTL 0` and expired cells.
- [ ] Use CQL `TTL(payload)` and `WRITETIME(payload)` without treating timestamps as deadlines.
- [ ] Understand per-cell TTL divergence, including after `UPDATE`.
- [ ] Choose SSTable streaming when preserving metadata and schemas stay compatible.
- [ ] Compute remaining TTL, migration lag, flooring, and safety margins in CQL replays.
- [ ] Never write TTL 0 for expired cells or turn deleted cells into permanent data.
- [ ] Implement CDC/dual-write, delete propagation, idempotency, and fencing for live sources.
- [ ] Measure TTL correctness via source/target deadlines rather than row counts and timeouts.
- [ ] Verify RF/CL, clock skew, tombstone grace/repair, and post-cutover expiration behavior.

## 13. References

1. Apache Cassandra Documentation — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `TTL(column)`, `WRITETIME(column)`, `USING TTL`, and `USING TIMESTAMP`.
2. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `default_time_to_live`, schemas, primary keys, and compaction options.
3. Apache Cassandra Documentation — [Backups: snapshots, incremental backups, and restore](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html).
4. Apache Cassandra Documentation — [sstableloader](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableloader.html): streaming SSTables into a target cluster.
5. Apache Cassandra Documentation — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): expired data, `gc_grace_seconds`, and reclamation.
6. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): replica synchronization and resurrection risks.
7. Apache Cassandra Java Driver — [Mapper and prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/): bound values and application queries during data migrations.
