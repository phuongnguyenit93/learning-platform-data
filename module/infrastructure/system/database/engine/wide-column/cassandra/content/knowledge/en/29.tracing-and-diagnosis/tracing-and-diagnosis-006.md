# Reading Digest Mismatches, Additional Data Reads, and Read Repair Handling

## Objectives and Context

Apache Cassandra allows data for the same **partition key** to be stored across multiple **replicas**. Thanks to the replication factor and **read/write consistency** levels, an application can continue reading and writing even when some nodes are slow or temporarily down. In exchange, at certain moments, replicas can hold different versions of the data.

When reading at a consistency level that involves multiple replicas, the **coordinator** can compare **digests** (summary hashes of response content) to check whether replicas agree for that query. If digests differ, the coordinator must **perform additional full data reads**, run **reconciliation** by timestamp/tombstones, and, depending on version and table configuration, perform **read repair**.

This lesson belongs to the **Tracing and Diagnosis** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects directly to the wide-column model, partition keys, query-driven table design, replication, consistency levels, compaction, repair, error handling, and Java application integration.

After this lesson, you will be able to:

1. Distinguish a **data request**, **digest request**, and **additional/full data request** within a single read.
2. Explain why a **digest mismatch** usually indicates replicas have not converged yet, **not automatically a disk failure or corrupted data**.
3. Understand the steps **digest comparison → full data reads → reconciliation → read repair** and the difference between `read_repair = 'BLOCKING'` and `'NONE'` in Cassandra 4.0+.
4. Use `cqlsh TRACING`, `system_traces`, logs, and `nodetool` to identify additional read costs and correlate latency.
5. Set up an RF=3 lab with a temporarily down replica, write at quorum, and use read tracing to look for evidence of divergence.
6. Use Java Driver 4.x to enable per-query tracing, capture trace IDs, and classify errors without treating a read timeout as "lost data."

> **Version Scope:** the general explanations of digests and reconciliation apply across Cassandra's read path, while exact request details, tracing events, and `read_repair` options vary by version. The `read_repair = 'BLOCKING'/'NONE'` configuration examples in this lesson target **Apache Cassandra 4.0 and later**. Verify your running version before copying administrative commands.

## 1. Three Layers to Separate When Reading

Suppose a keyspace has **RF=3** in datacenter `datacenter1`. Partition `run_id='trace-demo-01'` lives on three replicas `R1`, `R2`, and `R3`. The application sends:

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

Three independent questions need answers:

| Layer | Question | Avoid Confusing With |
| --- | --- | --- |
| **Availability/CL** | Did enough replicas respond to satisfy the read request? | That data on every replica is already identical |
| **Reconciliation** | If responses differ, which logical result must be returned? | Simply taking the row from the fastest responding replica |
| **Read repair** | Should stale replicas be repaired **on this read path**? | Cluster-wide repair or running compaction |

`LOCAL_ONE` only needs one response in the local DC, so it typically does not compare digests across multiple replicas for the same read. `LOCAL_QUORUM` at RF=3 requires two local replicas to respond; `ALL` requires all three replicas to respond. Reading across multiple replicas gives the coordinator a chance to detect divergence, though **which replicas are checked and the exact path depend on CL, replica selection strategy, speculative retry, and version**.

### Sample Data When Replicas Have Not Converged Yet

~~~text
Partition key: run_id = trace-demo-01
Clustering key: order_id = 1

R1: status = PAID,    version = 2, newer mutation
R2: status = PAID,    version = 2, newer mutation
R3: status = PENDING, version = 1, older mutation
~~~

In this example, `PENDING` on R3 **does not mean R3 is corrupted**: it may simply have been offline when version 2 was written. A local-DC quorum read hitting R1 and R2 will not necessarily detect a mismatch, because **both participating replicas hold identical data**. If R3 is included in the read group, a mismatch can occur.

## 2. What Is a Digest—and What Is It Not?

A **digest** is a summary value calculated by Cassandra over the response payload for **a specific read query**, allowing the coordinator to compare replicas without forcing all of them to transmit full result data over the network upfront.

Typically, the coordinator picks one replica for a **data request** (asking for full data), and sends **digest requests** to the other replicas needed to satisfy the consistency level. It compares the digests returned against the received data payload.

| Concept | Function |
| --- | --- |
| **Data request / full data response** | Returns the row/column data needed for reconciliation and returning to the client. |
| **Digest request / digest response** | Returns a summary to compare query content, reducing initial network transfer. |
| **Digest match** | Compared responses agree within the **query scope**. |
| **Digest mismatch** | At least two responses for the compared scope differ; more data is needed to reconcile. |
| **Read repair** | Mechanism that repairs stale replicas on the read path according to configured policy. |

**A digest is not a checksum of an entire node, SSTable, or table.** If a query only reads `order_id=1`, a matching digest does not prove other rows in the partition are in sync. Nor does it prove physical storage bytes on each replica are identical: Cassandra may hold different SSTable/memtable layouts that produce the exact same logical query result.

Therefore, **do not use a "digest match" as a substitute for `nodetool repair`**. Anti-entropy repair compares broader data ranges across replicas via its own mechanism, typically range-based comparison trees.

## 3. Read Path When Digests Match

An idealized `LOCAL_QUORUM` read path with RF=3 looks like:

~~~mermaid
sequenceDiagram
    participant Client as Java / cqlsh
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3
    Client->>C: SELECT (LOCAL_QUORUM)
    C->>R1: Data request
    C->>R2: Digest request
    R1-->>C: Full data
    R2-->>C: Digest
    Note over C: Compare digest with data
    C-->>Client: Read result (CL met)
    Note over R3: Not necessarily involved in this read
~~~

This diagram illustrates **the principle** only. The coordinator may contact more replicas to meet response-time targets, take another path under speculative retry, or handle timeouts. **Do not hardcode "R1 always gets data, R2 always gets digest"** in code or trace analysis.

### Why Does This Read Path Save Cost?

When returned rows are large, shipping full payloads from every replica upfront wastes network bandwidth and CPU. Digests optimize for the common case where replicas already agree. When digests **match**, the coordinator can finish once the CL threshold is met **without requesting extra full payloads just to resolve disagreement**.

There is still the cost of reading SSTables/memtables, decoding, applying TTLs/tombstones, and building responses. A small digest over the network **does not mean** the replica operation is free in disk I/O.

## 4. Read Path on Digest Mismatch: Additional Reads and Reconciliation

When digests differ, the coordinator **cannot simply pick one digest as right** because a digest lacks the full content needed to determine the winning values. It needs **full data responses** from the participating replicas to reconcile the data.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant C as Coordinator
    participant R1 as R1 with newer data
    participant R2 as R2 with newer data
    participant R3 as R3 with stale data
    Client->>C: SELECT (CL = ALL)
    C->>R1: Data request
    C->>R2: Digest request
    C->>R3: Digest request
    R1-->>C: PAID, version=2
    R2-->>C: Newer digest
    R3-->>C: Stale digest
    Note over C: Digest mismatch detected
    C->>R2: Additional full data request
    C->>R3: Additional full data request
    R2-->>C: PAID, version=2
    R3-->>C: PENDING, version=1
    Note over C: Reconciliation by timestamp and tombstones
    opt BLOCKING read repair when needed
        C->>R3: Mutation repairing stale data
        R3-->>C: Repair ACK per wait rules
    end
    C-->>Client: PAID, version=2 or error if CL unmet/timeout
~~~

**Four distinct steps:**

1. **Digest comparison:** detects divergence **within query responses**; lacks enough detail to know which rows/columns are stale.
2. **Additional/full data reads:** fetches content from required replicas to resolve the mismatch. Depending on the case, the coordinator may incur an extra round-trip, increasing wait time.
3. **Reconciliation:** applies Cassandra's rules for timestamps, tombstones, TTLs, and requested row/column ranges to determine the **logical result**.
4. **Read repair (if enabled):** sends repair mutations to stale replicas; whether ACKs are awaited depends on configuration. The client may wait longer when read repair is **blocking**.

Not every mismatch produces the exact same message count, event order, or latency. If one replica is slow and the additional full data reads or repair fail to finish before the request timeout, the client may receive `ReadTimeout` **even though valid data still exists**.

### Mismatch Does Not Mean Data Was Corrupted by the Query

Responses can diverge because:

- A replica recently recovered and **missed mutations** while down.
- Writes succeeded at `ONE` or `LOCAL_QUORUM`, leaving a replica outside the ACK group with stale state.
- **Tombstones/TTLs** cause logical state on replicas to temporarily differ.
- Concurrent writes/deletes occurred while a read ran mid-propagation.
- Some nodes are overloaded, delayed, streaming, applying hinted handoff, or mid-repair.

Seeing `digest mismatch` in an application trace is an **investigation lead into replica divergence**, not immediate proof of SSTable corruption, network bit-flips, or Cassandra data loss. Suspected corruption requires independent evidence from logs, disk checks, and verification tools.

## 5. Read Repair in Cassandra 4.0+: BLOCKING vs. NONE

In Cassandra versions supporting the `read_repair` table option, a table can be configured with:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'BLOCKING';
~~~

or:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'NONE';
~~~

**Cassandra 4.0+ defaults to `BLOCKING` for regular tables** unless configured otherwise. Before applying changes, check your version and the table's actual metadata. Older Cassandra 3.x guides discuss `read_repair_chance` or `dclocal_read_repair_chance`; **do not copy those legacy options to Cassandra 4.x/5.x** as if they were equivalent to `read_repair`.

### Comparison Table

| Aspect | `BLOCKING` | `NONE` |
| --- | --- | --- |
| On digest mismatch | Still fetches required full data and reconciles | **Still fetches data and reconciles**; does not ignore mismatches |
| Repairing stale replicas on read path | Coordinator issues repair mutations and **waits** for sufficient repair ACKs per read CL before returning success | Does not perform that read repair on the read path |
| Latency | Can increase due to extra read and repair-write round-trips | Avoids waiting on repair writes, yet **still incurs additional read/reconciliation cost** |
| Notable property | Supports **monotonic quorum reads** within read-repair's guarantee scope | Preserves **partition-level write atomicity** in certain read/write patterns |
| Remaining operational requirement | Does not replace full-range anti-entropy repair | Still requires anti-entropy repair; stale replicas will not heal from a SELECT alone |

**Crucial point:** `read_repair='NONE'` **does not mean the coordinator returns data from a single replica regardless of digest mismatch**, nor does it bypass the consistency level. It simply skips issuing compensating repair writes via that read-repair mechanism; reconciliation still aims to return accurate data per the read protocol and CL.

### Monotonic Quorum Reads vs. Partition-Level Write Atomicity

Why does Cassandra offer both behaviors?

Suppose an application writes multiple rows/columns within **the same partition** in a single partitioned write operation:

~~~text
Partition: run_id = batch-demo
Row 1: order_id = 10 -> PAID
Row 2: order_id = 11 -> PAID

R1/R2 receive the full mutation.
R3 misses the entire mutation and keeps old state.
~~~

Later, a query reading only `order_id=10` may detect a mismatch. With blocking read repair, Cassandra can **repair only the queried slice** on R3 without repairing `order_id=11`. This helps ensure subsequent quorum reads do not regress to stale values for that queried slice, yet **can weaken partition-level visibility atomicity** if the application later reads other parts of the same partition at a different CL.

`NONE` avoids having a narrow `SELECT` repair **part** of a partition that way; in return, it gives up the monotonic quorum read guarantee provided by blocking read repair. This is a property trade-off, **not an "enable consistency / disable consistency" switch**.

**Do not over-infer:** blocking read repair does not turn Cassandra into a serializable transactional database, does not replace LWT/`IF version` for preventing lost updates, and does not guarantee all replicas across all DCs are instantly synchronized. Choose the policy based on partition query patterns, batching behavior, and business semantics.

## 6. Observing Digest Mismatches with `cqlsh` TRACING

`TRACING` in `cqlsh` reveals execution steps of a Cassandra query: the coordinator contacting replicas, data/digest reads, and activities triggered when handling mismatches. Exact trace messages vary across versions and query types; **treat the event groups below as semantic indicators, not exact strings guaranteed to appear verbatim**.

### 6.1. Enabling and Disabling Tracing Per Session

~~~text
TRACING ON
~~~

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

~~~text
TRACING OFF
~~~

`TRACING ON`/`OFF` are **`cqlsh` commands**, not CQL. They apply to statements issued within that `cqlsh` session per client behavior. Output typically provides a **Tracing session ID** and a sequence of activities across coordinator/replicas.

### 6.2. Recognizing Event Groups

| Activity Group in Trace | Typical Meaning | What to Check |
| --- | --- | --- |
| READ setup/coordination | Coordinator picks replicas and dispatches requests | CL, chosen endpoints, topology |
| **Data request** | One replica is asked to return full data | SSTable/memtable read cost, latency |
| **Digest request** | Other replicas return query summaries | Number of responses needed for CL |
| **Digest mismatch** | Compared content differs across participating replicas | Was a replica down? low write CL? tombstones/TTL? |
| **Additional/full data request** | Coordinator needs full data instead of digests to reconcile | Extra round-trips, slow replica, or timeout |
| Reconciliation | Data/tombstones reconciled into logical result | Timestamps, TTL, concurrent writes |
| **Read repair** / mutation update | Repair writes may be sent to stale replicas | `BLOCKING` vs. `NONE`, ACKs, latency |
| Query completion or error | Whether enough responses arrived to reply to client | Total duration, timeouts, CL |

If **no mismatch line** appears in a trace, you cannot yet conclude no stale replica exists. The coordinator might not have picked the stale replica on that read, hints may have healed the difference, or trace capture may be incomplete.

### 6.3. Querying `system_traces` When Needed

Cassandra stores tracing data in the `system_traces` system keyspace. Using the tracing session UUID **printed by `cqlsh`**, you can query:

~~~sql
-- The UUID below is an example; replace it with the real tracing session ID.
SELECT session_id, coordinator, started_at, duration, request
FROM system_traces.sessions
WHERE session_id = 11111111-1111-4111-8111-111111111111;

SELECT event_id, activity, source, source_elapsed, thread
FROM system_traces.events
WHERE session_id = 11111111-1111-4111-8111-111111111111;
~~~

In the `events` table, `event_id` is a timeuuid supporting event ordering, `source` is the reporting node, and `source_elapsed` is typically microseconds relative to the tracing reference point on that source. When analyzing multiple nodes, **do not naively sum `source_elapsed` across events to get total wait time**: activities can run in parallel, measure from different points, and cross network links. Use the session's overall `duration` together with the timeline to spot bottlenecks.

Trace events may be persisted/arrive late or expire based on system configuration. Finding no rows in `system_traces` does not prove a query had no issues. Avoid heavy tracing in production: tracing incurs storage, network, and latency overhead.

## 7. RF=3 Lab: Creating Conditions for a Digest Mismatch

The following experiment requires **three Cassandra nodes in one DC**, e.g., `cass-1`, `cass-2`, `cass-3` in `datacenter1`, on Cassandra 4.0+ if testing the `read_repair` table option. Only perform this on a **lab/staging cluster where stopping nodes is permitted**.

### 7.1. Checking Topology

~~~bash
nodetool status
~~~

Expect all three nodes `UN` (*Up/Normal*) and the keyspace configured with RF=3 in the local DC. Check DC/version on the connected node via `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` only returns info for the current node; to confirm all nodes run the same version or verify exact DC names, inspect the other nodes as well. If your DC name differs from `datacenter1`, adjust the keyspace creation command accordingly.

### 7.2. Creating Schema and Writing Baseline Data

~~~sql
CREATE KEYSPACE IF NOT EXISTS tracing_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS tracing_lab.orders_by_run (
    run_id text,
    order_id int,
    status text,
    version int,
    updated_at timestamp,
    PRIMARY KEY ((run_id), order_id)
) WITH read_repair = 'BLOCKING';
~~~

`run_id` is the **partition key**, and `order_id` is the **clustering key**. Do not run `SELECT *` full-table scans: every test query targets the known partition and row. `version` is lesson metadata and **does not automatically prevent concurrent updates** under standard `UPDATE`s.

**If the table/keyspace already exists**, `IF NOT EXISTS` does not alter RF or read-repair options. Verify metadata before interpreting results:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'tracing_lab';

SELECT table_name, read_repair
FROM system_schema.tables
WHERE keyspace_name = 'tracing_lab'
  AND table_name = 'orders_by_run';
~~~

In `cqlsh`, set the write consistency level:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO tracing_lab.orders_by_run
    (run_id, order_id, status, version, updated_at)
VALUES (
    'trace-demo-01', 1, 'PENDING', 1,
    '2026-11-21T09:00:00Z'
);
~~~

Only treat the baseline as valid if the client actually **receives success** at `ALL` (all three replicas ACKed). On timeout, use a fresh run ID or re-verify before continuing.

### 7.3. Making One Replica Miss an UPDATE

In a Docker lab, assume the third node is container `cass-3`:

~~~bash
# Run in lab only; never kill a production node.
docker kill --signal=KILL cass-3
~~~

Verify the remaining two nodes are `UN` and the third node is `DN`:

~~~bash
nodetool status
~~~

Connect `cqlsh` to a live node and set:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
UPDATE tracing_lab.orders_by_run
SET status = 'PAID',
    version = 2,
    updated_at = '2026-11-21T09:05:00Z'
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

With RF=3 in one DC, `LOCAL_QUORUM` needs **2/3 replicas** to acknowledge. If the two live nodes ACK, the UPDATE succeeds even while `cass-3` still holds `PENDING`. This creates a stale replica that Cassandra must reconcile when it participates in a read.

**Do not mark the UPDATE as ACKed if `cqlsh` returns a timeout**; the mutation may still have been partially applied even though the client did not receive success.

### 7.4. Restarting the Replica and Enabling Tracing

~~~bash
docker start cass-3
nodetool status
~~~

Wait until all three nodes are `UN`, then set read consistency:

~~~text
CONSISTENCY ALL
TRACING ON
~~~

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

~~~text
TRACING OFF
~~~

**Why choose `ALL` in the lab?** When all three replicas are healthy, `ALL` forces the query to gather responses from every replica in RF=3, maximizing the chance of comparing `cass-3`'s stale copy if it has not caught up yet. With `LOCAL_QUORUM`, the coordinator might pick the two replicas that already have `PAID` and show no mismatch.

**There is no guarantee the trace will show a mismatch:** hinted handoff or another healing mechanism may update `cass-3` very quickly after restart. If the trace shows a normal read path returning `PAID`, that is still a valid result; **do not tamper with SSTable files, lower grace periods, or break topology** just to force a mismatch.

### 7.5. Interpreting Possible Observations

| Observation in Trace or Result | Cautious Interpretation |
| --- | --- |
| `PAID`, no mismatch | Participating replicas may have converged before the read, or divergence was not observed |
| `Digest mismatch` followed by full data reads | Read responses differed; coordinator had to fetch full data to reconcile |
| Mutation/read repair events present | Read path may be repairing the stale replica under `BLOCKING`; check ACKs/latency |
| `PAID` returned at `ALL` | Read completed at CL `ALL` with that logical result; **does not prove the whole cluster/table is repaired** |
| `ReadTimeout` or `Unavailable` | Query failed to complete at CL; must not be treated as "row lost" |
| `PENDING` or unexpected data | Check UPDATE ACK, timestamps, concurrent writers, schema, DC/RF, and node status |

After the read, inspect hints/repair logs and metrics if needed. **Querying the right result** reflects data observed at a specific CL and moment; proving "all replicas are fully synchronized" requires evidence of repair scope and replica state.

## 8. Hands-On Comparison of BLOCKING and NONE

To study how the configuration differs, modify only the **lab table** and use a **new run ID**, since blocking read repair from the previous round may have already fixed the divergence:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'NONE';
~~~

Repeat the steps: baseline write at `ALL`, bring one replica down, write a new version at `LOCAL_QUORUM`, bring the node back up, and read at `ALL` using run ID **`trace-demo-02`**. During this run:

- If a digest mismatch occurs, the coordinator **still reads additional data and reconciles** to return the correct logical result per CL, even with read repair set to `NONE`.
- Do not expect `NONE` to issue repair writes to the stale replica during that query.
- If no mismatch appears, hints may have already repaired it or replicas may have converged; draw no conclusions about `NONE` from a single read.
- Do not compare latencies between two reads if one hit a mismatch and the other did not. Compare under equivalent workloads and replica states across multiple samples.

Reset the lab table back to `BLOCKING` when finished comparing:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'BLOCKING';
~~~

**Caution:** changing `read_repair` is a **table-wide schema change**, not a local `cqlsh` toggle. Never flip it casually on a production table while applications may rely on either monotonic quorum reads or partition-level write atomicity. Verify schema agreement across nodes when applying DDL changes.

## 9. Reading Traces Together with Metrics, Never Isolated from Symptoms

A single digest mismatch can be a normal transient signal. It warrants deeper investigation when accompanied by **rising frequency, higher p95/p99 latency, timeouts, continuous read repair, or replicas failing to converge**.

### Ordered Checklist

1. **Identify the real query:** keyspace, table, partition key, clustering range, CL, coordinator, timestamp, trace ID, and application request ID.
2. **Read the trace:** check for data/digest requests, mismatches, additional full data reads, read repair, and which nodes responded slowly.
3. **Verify RF and topology:** `nodetool status`, DC/rack layout, any recently recovered or streaming nodes?
4. **Inspect the write path:** which CL did clients write at, were there timeouts/UNKNOWNs, pending hints, or offline nodes during writes?
5. **Inspect deleted data:** tombstones, TTLs, `gc_grace_seconds`, overdue repairs, signs of zombie data.
6. **Check resources:** disk I/O, compaction backlog, CPU, network, and per-node read/write timeouts.
7. **Determine scope:** a few partitions or many token ranges; is read-path healing enough or is anti-entropy repair needed?
8. **Document bounded conclusions:** observed events, hypotheses, supporting evidence, and follow-up monitoring.

Basic inspection commands:

~~~bash
# Run on the appropriate node; do not force compaction or repair before analyzing.
nodetool status
nodetool tablestats tracing_lab.orders_by_run
nodetool compactionstats
nodetool netstats
~~~

| Indicator | First Investigation Step | What Not to Conclude |
| --- | --- | --- |
| Occasional mismatch after restart | Hints/repair catching up; replica just recovered | "Disk is corrupted" |
| Mismatch with rising read latency | Full data round-trips, blocking repair, slow replica | "Switching CL to ONE fixes the data" |
| Repeated mismatch with one node | Undelivered hints, failing repairs, overloaded node, clock/timestamp anomaly | "One SELECT will repair the entire table" |
| `ReadTimeout` while repair runs | Slow I/O/network, missing ACKs before timeout | "Row definitely does not exist" |
| `ONE` read differs from `QUORUM` read | Diverged replica states, different replicas contacted | "QUORUM definitely repaired all replicas" |
| High tombstones/latency | TTLs, DELETEs, range scans, and compaction | "Digest mismatch is the only cause" |
| Trace shows no mismatch | Sampled replicas agreed or were already repaired | "The entire cluster has zero divergence" |

**Do not lower CL just to hide mismatches.** Reading at `LOCAL_ONE` may be faster, yet it avoids comparing multiple replicas and can return stale data. That is a freshness/availability trade-off to accept at the business layer, not a synchronization fix.

## 10. Distinguishing Read Repair from Anti-Entropy Repair

| Criterion | Read Repair | Anti-Entropy Repair |
| --- | --- | --- |
| Trigger | Divergence detected on read path; depends on table policy/version | Administrative operation, e.g., `nodetool repair` |
| Scope | Rows/columns/partition slice touched by the query | Token ranges and replicas participating in repair |
| Timing | Can fall inside user query latency | Runs in maintenance windows; consumes I/O/network |
| Effect | Repairs stale data encountered during a single read | Synchronizes data/tombstones across the repaired range |
| Limitations | Misses unqueried partitions; may not heal every replica | Cannot restore events lost on **all** replicas/sources; cannot resurrect tombstones purged everywhere |

For tables with `gc_grace_seconds`, anti-entropy repair schedules and node downtime limits must ensure **tombstones have a chance to propagate to any replica that missed a `DELETE` before being purged**. `read_repair='BLOCKING'` does not replace periodic repair, especially when many partitions are **never read by users**.

Compaction only merges SSTables **locally on one node** and never sends mutations to other replicas. A cluster can suffer high read latency from compaction/tombstones with **zero digest mismatches**; evaluate each cost source independently.

## 11. Java Driver: Enabling Tracing for a Specific Query

Java Driver 4.x allows enabling request tracing per statement. The example below reads **one partition and one clustering key** with an explicit CL and records the **tracing ID** to cross-reference `system_traces`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class DigestTraceProbe {
    public enum State { FOUND, MISSING, READ_ERROR }
    public record Outcome(State state, String status,
                          Integer version, UUID tracingId,
                          long elapsedMillis) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public DigestTraceProbe(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT status, version FROM tracing_lab.orders_by_run " +
            "WHERE run_id = ? AND order_id = ?");
    }

    public Outcome readWithTracing(String runId, int orderId) {
        BoundStatement statement = select.bind(runId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ALL)
            .setTracing(true)
            .setIdempotence(true);

        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            ExecutionInfo info = result.getExecutionInfo();
            UUID tracingId = info.getTracingId();
            Row row = result.one();
            long millis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

            if (row == null) {
                return new Outcome(
                    State.MISSING, null, null, tracingId, millis);
            }
            return new Outcome(
                State.FOUND, row.getString("status"),
                row.isNull("version") ? null : row.getInt("version"),
                tracingId, millis);
        } catch (RuntimeException error) {
            long millis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
            System.err.printf(
                "READ_ERROR run=%s order=%d type=%s timeMs=%d%n",
                runId, orderId, error.getClass().getSimpleName(), millis);
            return new Outcome(
                State.READ_ERROR, null, null, null, millis);
        }
    }
}
~~~

In real applications, reuse `CqlSession` and `PreparedStatement` instances. Enable `setTracing(true)` only for selected diagnostic requests; **never enable it across all traffic** due to tracing overhead. The driver may return a `null` tracing ID when the server omits it or the request fails; `null` is valid, so keep client request IDs/logs for lookup.

### Interpreting Java Results Properly

- `FOUND`: the query at `ALL` returned a row for the requested key; it does not mean every other partition has converged.
- `MISSING`: the query **completed successfully** with no matching row; check manifests, TTLs, DELETEs, and write status before concluding data loss.
- `READ_ERROR`: the query failed to complete; **do not fold into `MISSING`** or assume a digest mismatch.
- `elapsedMillis` is end-to-end client wall time for one call, including network/driver time; collect **multiple samples under matching load** for p95/p99.
- `tracingId` looks up server events; an enabled trace **does not guarantee** capturing background activities outside that query, such as scheduled repair.
- `setIdempotence(true)` applies to the pure read `SELECT` in this example; if replaced with CQL having side effects, re-evaluate retry safety.

**Why does the example use CL `ALL`?** In a healthy three-node lab, it increases the likelihood of observing replica divergence. In production, select CL based on SLAs, RF/DC layout, and availability; never default every query to `ALL` just to inspect more replicas.

## 12. Illustrative Incidents and Investigation Approach

### Case 1 — Unusually Slow Reads After a Replica Recovers

**Symptom:** several `SELECT` queries at `LOCAL_QUORUM` suddenly jump from tens of milliseconds to hundreds of milliseconds after a node rejoins. Traces show digest mismatches and additional full data reads.

**Plausible hypothesis:** the previously down replica holds stale data; the coordinator must read extra payloads and, under `BLOCKING`, may wait on repair writes. Inspect hints, recovery progress, compaction status, request rates, and read-repair metrics. **Do not jump to conclusions** that the partition key is broken or disks are failing.

### Case 2 — Repeated Mismatches Even Though Query Results Are Correct

**Symptom:** checking a group of partitions repeatedly shows divergence, yet `LOCAL_QUORUM` usually returns the latest value.

**Action plan:** verify the table's `read_repair` setting, participating replicas, and whether clients read across multiple DCs. Under `NONE`, a correct read **does not heal stale replicas**. If `BLOCKING` still shows mismatches, check ongoing concurrent UPDATE/DELETEs, failing/timed-out repair mutations, or replicas excluded from prior reads. Run planned anti-entropy repair if divergence spans a wide range.

### Case 3 — Read Timeout During a Digest Mismatch

**Symptom:** the trace cuts off before the coordinator returns a response; one replica failed to return full data or repair ACK in time.

**What you must never do:** report "order does not exist" or blindly replay entire business write workflows because the read failed. **Read timeout means an unknown outcome**; collect logs/traces, check CL and node health, perform bounded read retries if appropriate, and investigate load.

### Case 4 — No Mismatch Yet Business Data Is Missing

**Symptom:** an `event_id` from an upstream business system is absent in Cassandra, yet every replica returns the same empty result so digests match.

**Explanation:** digests only compare replicas over data **that actually exists** within the read scope; if an event was never successfully written to any replica, read repair cannot conjure it into existence. Reconcile against upstream event logs/manifests/outboxes and backfill using stable IDs if justified.

## 13. Drill Checklist and Self-Check Questions

**Exercise 1 — Predicting digests.** With RF=3, R1/R2 hold `PAID` and R3 holds `PENDING`. Will a `LOCAL_QUORUM` read hitting R1/R2 necessarily hit a mismatch? When reading at `ALL` with all three nodes up, what forces the coordinator to fetch additional full data?

**Exercise 2 — Trace analysis.** Run `TRACING ON` for a `SELECT` with an explicit partition key. Classify discovered events into data request, digest request, additional full data read, read repair, and completion. If no mismatch line appears, list at least three hypotheses other than "the cluster is 100% synchronized."

**Exercise 3 — BLOCKING vs. NONE.** Using two separate run IDs in the lab, test `read_repair='BLOCKING'` and `'NONE'`. Why must `NONE` still reconcile when digests differ? Why can't you compare latency from a trace with a mismatch against one without a mismatch?

**Exercise 4 — Partition-level write atomicity.** A single partitioned mutation updates two clustering rows. A query requesting only the first row triggers read repair. Explain the "partial partition repair" risk of blocking repair and why some workloads choose `NONE`.

**Exercise 5 — Read errors and missing data.** A `SELECT` at `ALL` times out, and a subsequent `SELECT` at `LOCAL_ONE` returns `PAID`. Is there enough evidence to state every replica holds `PAID`? Why must you never convert a read timeout into a `MISSING` result?

**Exercise 6 — Tombstones.** A node misses a `DELETE` and stays down longer than `gc_grace_seconds`; tombstones have already been purged on the other replicas. Why won't raising CL or issuing extra reads guarantee eliminating zombie data? Which repair/recovery steps should be considered?

**Exercise 7 — Java tracing.** From `ExecutionInfo.getTracingId()`, query `system_traces.events` and compare with client timing. Why shouldn't `source_elapsed` values be summed directly into client latency? When should tracing be turned off?

**Exercise 8 — Difference from LWT.** An application experiences lost updates when two workers concurrently modify `version`. Should you enable `read_repair='BLOCKING'` to prevent concurrent overwrites? Explain the distinct roles of `IF version = ?`, Paxos, and serial consistency in LWTs.

## Key Takeaways

**A digest mismatch indicates that compared replicas returned differing payloads for a query—not that data is lost or disks are corrupted.** The coordinator may have to send **additional full data requests**, reconcile by timestamp/tombstones, and, under `BLOCKING`, wait for read repair before completing. `NONE` still reconciles without issuing that read repair. Use tracing, topology, consistency levels, logs, and metrics to determine **scope and cost**; use planned anti-entropy repair for wide divergence and reconcile against upstream business sources when verifying truly missing data.
