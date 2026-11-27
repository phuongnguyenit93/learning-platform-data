# Verifying Data, Queries, Latency, and Errors Before and After Upgrades

## Objective and Context

An Apache Cassandra upgrade cannot be declared successful merely because every node runs the new version and `nodetool status` shows `UN` (*Up/Normal*). Nodes can join the cluster normally while **certain records no longer read accurately**, application CQL statements become incompatible, p99 latency spikes, or timeout rates breach operational thresholds.

In the **Upgrades and Compatibility** chapter of module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, this lesson presents **repeatable verification before, during, and after upgrades**. Measurements cover four dimensions:

1. **Data:** do ACKed records still exist with accurate values at the required consistency level?
2. **Queries:** do CQL, schemas, prepared statements, paging, LWTs, and Java application reads/writes preserve semantics?
3. **Latency/resources:** do p50/p95/p99, throughput, page reads, disk I/O, CPU, compaction, repair, and network meet SLOs?
4. **Errors:** did timeouts, unavailable errors, read/write failures, protocol/driver incompatibilities, or **`UNKNOWN_WRITE`** states change post-upgrade?

This lesson connects directly to the wide-column model, partition keys, query-driven table design, per-DC replication, consistency levels, CQL, compaction, repair, error diagnosis, and Cassandra Java Driver 4.x.

After studying this lesson, you can design **pre-change baselines and PASS/FAIL criteria**, execute the same test suite at rolling upgrade checkpoints, reconcile data against a manifest, write root-caused discrepancy reports, and decide when to **halt rollout** instead of advancing by intuition.

> **Safety scope:** CQL commands and code snippets target **lab/staging**. Never upgrade or downgrade a production cluster following simplified lesson steps alone. **Supported upgrade paths, mixed-version compatibility, SSTable formats, Java runtimes, drivers, backup tools, and rollback feasibility** must be verified against official documentation for your **exact source–target version pair** and distribution. This lesson does not assume arbitrary Cassandra versions support direct upgrades or downgrades.

## 1. "Successful Upgrade" Has Multiple Layers

### 1.1. Healthy Nodes Are Not Enough

Distinguish four verification layers:

| Layer | Evidence | What cannot be inferred from that evidence alone |
| --- | --- | --- |
| **Process and ring** | Service running; nodes `UN`; gossip/schema agreement stable | Every partition/cell on every replica is identical |
| **Data and consistency** | Primary-key queries at target CL return exact manifest markers | All query shapes, paging, or LWTs are error-free |
| **Application** | CQL/Java Driver runs full business flows | p99, timeouts, and resource cost stay within SLOs |
| **Operations and recovery** | Repair/streaming/backup/restore/drills verified | Upgrade can be reversed via downgrade at any moment |

A request ACKed at `LOCAL_QUORUM` confirms only that enough **local** replicas ACKed—it does not prove the remote DC received that mutation. A quorum `SELECT` returning cleanly does not prove **all replicas across the cluster have converged**. Concluding data completeness requires specifying **expected keys, read/write types, timestamps, and replica/DC scope**.

### 1.2. Changes That Can Occur

Depending on the source–target versions, an upgrade can impact:

- **CQL and schema:** supported features, validation, indexes, query guardrails, or table option defaults.
- **Read/write path:** compaction, read repair, tombstones, page fetching, internode messaging, or metadata.
- **Client protocol:** negotiated protocol versions, authentication/TLS, contact points, and node discovery.
- **Java Driver:** binary/API compatibility, policies, codecs, timeouts, retry/speculative execution, and exception handling.
- **Resources:** CPU/heap/GC, memory, disk/compaction, internode bandwidth, streaming/repair after rolling restarts.
- **Operations:** `nodetool` commands, metric/JMX names, SSTable formats, and recovery procedures.

Do not assume any of these changes **definitely** happen in every upgrade. Every rollout needs its own **compatibility matrix** and regression suite matching the real environment.

## 2. Define PASS/FAIL Criteria Before Measuring

Before upgrading, the accountable team must lock in **the definition of success**. Post-upgrade measurements are meaningful only when compared against a same-load baseline and pre-approved thresholds.

| Item | Illustrative lab criterion | Why needed |
| --- | --- | --- |
| Ring/topology | All expected nodes `UN`; no unplanned topology changes | Detects nodes failing to rejoin or restart |
| Schema | Schema/query contracts verified at every checkpoint | Prevents prepared statement or schema errors |
| Mandatory data | 100% of critical ACKed markers `FOUND_MATCH` | Blocks ignoring corrupted or missing data |
| Business queries | 100% of predefined test cases pass | Protects query shapes, paging, LWTs, TTL/`DELETE` |
| Error rate | Within SLO budget with zero new severe error classes | Spots regressions hidden behind good p50 |
| Latency p95 | At most 1.25x baseline under equivalent conditions | Checks quality for the bulk of requests |
| Latency p99 | At most 1.5x baseline under equivalent conditions | Catches tail latency from GC/I/O/repair |
| Read/write throughput | Meets target load within error budget | Avoids testing on nearly idle clusters |
| Recovery | Verified runbooks for backup/restore and rollback/forward recovery | Prevents getting trapped in a broken state |

**Ratios like 1.25x and 1.5x are illustrative thresholds, not Cassandra standards.** Payment, telemetry, and reporting apps have distinct SLOs; never move goalposts after seeing results.

### Per-Stage Criteria

- **Before upgrade:** baseline and backup/restore complete; unresolved faults explicitly flagged.
- **After canary node:** ring, connectivity, CL, and reads/writes via the upgraded coordinator/node must PASS.
- **During mixed-version window:** queries/drivers operate across mixed coordinator and replica versions **if supported by the upgrade path**.
- **After all nodes reach the new version:** data and business logic PASS; latency/error rates measured under sustained steady load.
- **After post-upgrade maintenance:** streaming/repair/compaction/backup/restore status verified on the new version.

**Never treat "no commands printed errors" as PASS** if query results are wrong, rows are missing, or data was overwritten.

## 3. Pre-Upgrade Inventory

### 3.1. Capture Exact Context for Before/After Comparison

Pre-upgrade records should include:

| Group | What to record |
| --- | --- |
| Cluster | Cluster ID/name, datacenter/rack, node count, per-DC RF, snitch, token ownership |
| Software | Cassandra version on **every node**, JVM version, OS/container image, Java Driver version |
| Schema | Keyspaces, tables, primary/clustering keys, UDTs, indexes, materialized views if any, TTL, compaction/read-repair options |
| CQL | Top query shapes, read/write CLs, LWT/serial CLs, page sizes, batch/counter workloads |
| Data | Manifest of ACKed records, source event IDs, expected versions, tombstone/TTL cases |
| Resources | CPU/heap/GC, free disk/I/O, pending compaction, streaming/repair, network |
| Access | TLS, authentication, authorization, driver local DC, connection pools, retry budgets |
| Recovery | Off-cluster backup sets, schema exports, restore drills, rollback/forward-recovery rules |

**Never read one node's version and assign it to the whole cluster.** During a rolling upgrade, some nodes run the new version while others still run the old one. Always log `node → version → DC/rack → timestamp`.

### 3.2. Basic Observation Commands

~~~bash
# Run on an authorized admin host for the lab cluster.
nodetool status
nodetool describecluster
nodetool version
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

In `cqlsh` connected to each target node when cross-checking:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` returns metadata for **the node serving that query**, not a list of every node. Command/metric names and formats can differ between versions; consult documentation for the running release.

For a specific keyspace:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'upgrade_verify_lab';
~~~

If the keyspace does not exist yet, this query simply returns empty; never create production schemas just to run measurements.

### 3.3. Backups Are a Precondition, Not an Automatic Rollback Plan

A snapshot on the same disk volume **does not** protect against losing a node or cluster. You need backups **outside the failure domain**, file manifests/checksums, schemas, KMS/credentials, and restore drills. Never assume direct downgrades from the new version back to the old version work: SSTable formats, schemas, commit logs, protocols, and streaming states may be incompatible.

**Viable rollbacks may mean** shifting traffic back to a maintained legacy cluster, restoring to a clean cluster on a supported version, or **forward-fixing** bugs on the new version. Plan **write ownership/fencing** and reconciliation for writes arriving while two environments coexist; never create "two sources of truth" during failback.

## 4. Expected Dataset: Manifest Independent of Cassandra

### 4.1. Why Comparing Counts Is Insufficient

Suppose before upgrading you have:

~~~text
expected:
  E1 -> status=PAID,   version=3
  E2 -> status=NEW,    version=1
  E3 -> DELETE ACKed, must return no row

after:
  E1 -> status=PAID,   version=3
  E2 -> status=PAID,   version=2 (wrong)
  E3 -> no row
~~~

Live row counts before and after are **identical**, yet E2 mutated outside contract. `COUNT(*)` on large tables wastes resources and fails to pinpoint **exact mismatched IDs and values**.

A reliable manifest lives in a source **independent of the target cluster**:

| Field | Purpose |
| --- | --- |
| `test_run_id`, `event_id`, full primary key | Unambiguously identifies the row to reconcile |
| Expected columns + canonical hash | Verifies values, avoiding order/formatting drift |
| ACK/UNKNOWN, write CL, and ACK timestamp | Prevents treating write timeouts as ACKs |
| Row type | Regular, delete/tombstone, TTL, LWT, Unicode/decimal values |
| Schema contract version | Defines how types/scales/timezones are interpreted |
| Read CL, coordinator/DC, verification timestamp | Bounds the scope of conclusions |
| Outcome and error code | Separates `FOUND_MATCH`, `MISSING`, `MISMATCH`, `READ_ERROR` |

**Source of truth** can be an event log/outbox, exported source-system records, or an ACK manifest stored in an audit store. Never generate "expected" data by running `SELECT` on the cluster **after upgrading** and calling it 100% accurate.

### 4.2. Classify Outcomes to Avoid Wrong Conclusions

| Outcome | Meaning | Is it permanent data loss? |
| --- | --- | --- |
| `FOUND_MATCH` | Query completed and fields/markers match manifest | No; this is PASS for the checked key/CL |
| `MISSING_AT_CL` | Query completed yet expected row was absent | Unclear; check deletes/TTLs, replication, and source |
| `MISMATCH` | Query completed yet values differ from expected | Regression to investigate; could be concurrent writer/contract |
| `READ_ERROR` | Timeout, unavailable, failure, or other read error | **No**; unknown whether row exists |
| `UNKNOWN_WRITE` | Write lacked final ACK; may have reached some replicas | Unknown; reconcile before retrying |
| `EXPECTED_ABSENT_MATCH` | Row properly deleted/TTL-expired and query returned no row | PASS for this record type |

**Rule:** report checked keys, unverified keys, and failed/missing ACKed keys separately. Never merge `READ_ERROR` into `MISSING`, nor infer from a failed read that repair/upgrade deleted data.

### 4.3. Test Data Categories to Include

- Vietnamese UTF-8 text with diacritics and Unicode normalization per contract.
- `uuid`, `decimal`, `bigint`, UTC/offset timestamps, nulls, and empty strings.
- Small and moderately sized partitions; clustering ranges, page boundaries, and row/column projections.
- Active TTLs, freshly expired TTLs, and `DELETE` tombstones; **measured by timestamp**.
- Data written near upgrade time alongside older data spanning multiple SSTables.
- Infrequently queried partitions so you do not test only replicas accidentally healed by read repair.
- LWT `IF NOT EXISTS`/`IF version = ...` cases using **unique keys per run** so tests never overwrite production data.

For time-based checks, synchronize clocks on nodes and clients, and note millisecond precision of CQL `timestamp` vs. microsecond write timestamps.

## 5. CQL Lab: Building a Baseline with Clear Primary Keys

### 5.1. Topology Assumptions

This illustrative lab uses three Cassandra nodes in DC `datacenter1` with `NetworkTopologyStrategy` and RF=3. If your lab has one node or a different DC name, **adjust RF/CL/DC name to match real topology**—never expect RF3 `LOCAL_QUORUM` to find two replicas on a single node.

Before the lab:

~~~bash
nodetool status
~~~

Run baseline writes needing `ALL` only when **all three replicas are healthy** with no unplanned topology changes or heavy streaming.

### 5.2. Create a Dedicated Keyspace and Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS upgrade_verify_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS upgrade_verify_lab.events_by_run_day (
    run_id text,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    status text,
    version int,
    amount decimal,
    payload text,
    PRIMARY KEY ((run_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

`(run_id, event_day)` is the **composite partition key**; `event_ts` and `event_id` are clustering keys. This table intentionally holds **a small set** per run ID/day for easy reconciliation. **Never** pack millions of events under one giant `run_id` in production workloads; bucket/shard by real query patterns and volume.

`IF NOT EXISTS` does not alter existing schemas. Before interpreting results, verify actual RF and table metadata so you do not accidentally reuse a keyspace from an earlier run.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'upgrade_verify_lab';
~~~

### 5.3. Write Baseline Data

In `cqlsh` connected to a node in `datacenter1`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO upgrade_verify_lab.events_by_run_day
    (run_id, event_day, event_ts, event_id,
     status, version, amount, payload)
VALUES (
    'upgrade-lab-01', '2026-11-21',
    '2026-11-21T08:00:00.000Z',
    11111111-1111-4111-8111-111111111111,
    'PAID', 3, 123.4500, 'Đơn hàng: Cà phê'
);

INSERT INTO upgrade_verify_lab.events_by_run_day
    (run_id, event_day, event_ts, event_id,
     status, version, amount, payload)
VALUES (
    'upgrade-lab-01', '2026-11-21',
    '2026-11-21T08:05:00.000Z',
    22222222-2222-4222-8222-222222222222,
    'NEW', 1, 100.00, 'event-baseline-B'
);
~~~

Mark `ACKNOWLEDGED` in the manifest only if each `INSERT` truly succeeded at `ALL`. On timeout, **mark `UNKNOWN_WRITE`** and verify; never log ACK just to "make the baseline clean."

In production, you do not need `ALL` on every query to verify upgrades; this is simply clear in a healthy RF3 lab. Across multiple DCs, `ALL` forces waiting on every replica cluster-wide, breaking availability if any DC has a fault.

### 5.4. Two Baseline Read Patterns

Point read with **full primary key**:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT status, version, amount, payload
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T08:00:00.000Z'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

Range read by **clustering timestamp** within one partition:

~~~sql
SELECT event_ts, event_id, status, version
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
  AND event_ts >= '2026-11-21T08:00:00.000Z'
  AND event_ts <  '2026-11-21T09:00:00.000Z'
LIMIT 20;
~~~

Record **both values and ordering** of returned rows, not just row count. With `DESC` clustering order, applications rely on sort order; a query/driver bug breaking order is a regression even if all rows return.

### 5.5. Cases for `DELETE`, TTL, and LWT

Never overwrite the same primary keys repeatedly across before/after comparisons. Use a **distinct run ID** per stage, locking expected lists and timestamps.

**`DELETE` marker:** insert a row in a dedicated test run cleanly, then `DELETE` at the chosen CL:

~~~sql
DELETE FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-delete-01'
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T08:10:00.000Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;
~~~

After the `DELETE` ACKs, verification must expect **no row returned** at the appropriate timestamp/CL. However, if the row was never inserted first, `DELETE` fails to test tombstones shadowing prior data; always create a real row before deleting it.

**TTL marker:** in another run, use `INSERT ... USING TTL 120` with the start timestamp logged by the client. TTL tests are valid only when measured before and after expiration with adequate buffers; never compare two reads spaced too far apart and blame TTL expiry on "data lost by upgrade."

**LWT marker:** execute `INSERT ... IF NOT EXISTS` with an **unused key** and check `[applied]`. Re-running with the same key returns `[applied]=false` once the row exists; that is **correct semantics**, not a regression. Compare LWT commands by **initial state scenario** and appropriate serial consistency, not raw string matching alone.

## 6. Before/After Query Regression Matrix

A thorough regression suite tests more than sample SQL—it covers **the real query shapes sent by Java applications**.

| Group | Pre-upgrade test | Post-upgrade check |
| --- | --- | --- |
| **Point reads** | `WHERE` with full partition + clustering key; explicit CL | Row/fields/latency and metadata match |
| **Range reads** | Clustering range + `LIMIT` + schema-aligned `ORDER` | ID set, ordering, and page boundaries unchanged |
| **Projections** | `SELECT` explicit column lists, null/empty cases | Codec/type mappings unchanged |
| **Paging** | Controlled page size, iteration, paging state | No missing/duplicate rows reading stable sets |
| **Prepared statements** | Prepare/bind numbers, UUIDs, timestamps, decimals | Zero protocol/codec/schema errors post-rolling |
| **Writes** | `INSERT`/`UPDATE` with stable IDs, clear CL | ACK/UNKNOWN, read-after-write, and values match |
| **Conditional writes (LWT)** | `IF NOT EXISTS` / `IF version = ...` | `[applied]` and post-LWT values accurate |
| **TTL and `DELETE`** | Tests before/after expiry, tombstones | Timely expiration never mislabeled data loss |
| **Counters**, if used | Increment operations, retry semantics | Avoid blind retries or hard-coded snapshot comparisons |
| **Secondary indexes/SAI**, if used | Queries supported by version/schema | Results, latency, rebuild/index status compatible |
| **Multi-DC** | `LOCAL_ONE`/`LOCAL_QUORUM` in proper local DC | ACK scope, remote lag, failover/readback accurate |
| **Authentication/TLS** | Connect with app roles plus denied-permission cases | Driver/PKI/CQL permissions unaltered illegally |

**Never send an old pre-upgrade paging state to a new version expecting automatic compatibility** unless the version/driver pair explicitly guarantees it. Paging tokens bind to query, bind parameters, and protocol. Test **paging behavior** by reading the same stable dataset within each version, isolating cross-version token tests separately if specifically required.

### Semantic Tests and Performance Tests Are Two Distinct Exercises

In functional tests:

- For immutable records, compare **event IDs, order, fields, and data types**.
- For TTL rows, record **observation timestamps**; never expect already-expired values.
- For LWTs, use fresh keys and identical initial conditions in both stages.
- For counters, set explicit starting states and known mutation counts; avoid retries multiplying increments.
- With ongoing writes, define **cutoff windows or versioned event logs** so valid concurrent updates are not misread as regressions.

In performance tests:

- Drive equivalent request rates, partition-key distributions, read/write ratios, payloads, and CLs.
- Collect p95/p99, error rates, and node load; never substitute row counts for latency.
- Separate **warm-up, cold post-restart caches, bootstrap/streaming/compaction** from steady state.

## 7. Measuring Latency, Throughput, and Error Rates Fairly

### 7.1. Three Windows to Separate

~~~mermaid
flowchart LR
    B["Pre-upgrade steady baseline"] --> R["Rolling/mixed-version\nrestarts and warm-up"]
    R --> S["Post-upgrade steady state\npost warm-up"]
    B -. "Compare same load/SLO" .-> S
    R --> I["Report maintenance-window impact separately"]
~~~

**Never compare only "before restart" against "right when the node came up."** Upon startup, cold page caches and network/compaction/streaming skew latency. Report **rolling-window impact separately** from steady-state post-upgrade regressions.

### 7.2. Metrics to Collect

| Layer | Metrics | Meaning |
| --- | --- | --- |
| Java client | Request rate, success/error counts, p50/p95/p99, retries, speculative executions | Real user experience and load amplification |
| CQL operations | Read/write/LWT latency broken down by query shape/CL | Prevents heavy queries from masking or skewing light ones |
| Cassandra | Read/write timeouts, unavailable, failures, dropped messages | Responsiveness and overload state |
| Node | CPU, heap/GC pauses, disk latency/IOPS, network, file descriptors | Resource bottlenecks |
| SSTable/compaction | Pending compactions, tombstones/SSTables scanned per read, free disk | Read/write amplification and background load |
| Topology | Nodes `UN`/`DN`, streaming, repair/hints progress | Distinguishes regressions from recovering nodes |
| Data | Expected rows, match/missing/mismatch/read errors | Ensures speed optimizations never trade away data |

Sample at fine enough resolution and windows—e.g., 1–5 minute buckets plus full-phase aggregates—sized to your SLOs. A few dozen requests cannot yield reliable p99. Record load generation, concurrency, request mix, and collection tools for reproducibility.

### 7.3. Illustrative Numbers — Not a Cassandra Benchmark

| Metric at identical workload | Baseline | Post-upgrade | Interpretation |
| --- | ---: | ---: | --- |
| Read QPS | 1,000 | 1,000 | Same target load |
| Read p50 | 8 ms | 8 ms | Unchanged |
| Read p95 | 20 ms | 23 ms | +15% increase |
| Read p99 | 45 ms | 82 ms | ~82% increase |
| Read errors / 10,000 requests | 2 | 18 | Must classify error types |
| Average CPU | 52% | 60% | Compare per node/rack |
| Pending compactions | 5 | 220 | Potential tail-latency cause; investigate |

If the p99 limit is 1.5x baseline, the threshold is **67.5 ms**; **82 ms fails**. Never declare success just because p50 stayed at 8 ms. Moreover, if failed requests drop out of latency histograms, successful-only p99 can **hide timeouts**; always report error rates alongside latency.

### 7.4. Eliminating Comparison Bias

- Never change **queries, CL, RF, page size, retry policy, heap, JDK, and compaction strategy** at once and blame Cassandra version alone.
- If multiple components must change for compatibility, **document each change** and isolate tests where feasible.
- Never compare off-peak p95 with peak-hour p95.
- Never substitute local `cqlsh` latency on a node for Java Driver latency over the network.
- Never compare a warm-cache run against a cold post-restart run without noting it.
- Never discard timed-out requests from samples in a way that artificially lowers p99.
- In multi-DC setups, compare within the same local DC/network path; WAN latency can dwarf engine differences.

## 8. Classify Errors Rather Than Counting "5xx"

Identical total error rates can stem from completely different causes.

| Error class | Typical signs | Upgrade likelihood | First action |
| --- | --- | --- | --- |
| **Bootstrap/driver** | `NoNodeAvailable`, failed session init | Discovery, TLS/protocol, local DC, driver version | Check endpoints, versions, SSL/auth, logs |
| **Schema/query** | `InvalidQuery`, unknown column/table, prepare fail | Schema agreement, incompatible DDL/codecs | Compare schemas and query contracts |
| **`ReadTimeout`** | Coordinator lacked enough timely replies | Slow replica, compaction, network, CL | Record `READ_ERROR`; inspect nodes/traces |
| **`WriteTimeout`** | Lacked enough write ACKs in time | Slow replica/disk/network | Record `UNKNOWN_WRITE`; never retry blindly |
| **`Unavailable`** | Too few live replicas for CL | Rolling node down, topology/rack/DC | Check RF/CL and `nodetool status` |
| **`ReadFailure`/`WriteFailure`** | Replicas reported processing errors | Storage/network/version bug | Read per-node errors and timestamps |
| **Unauthorized/Auth** | Invalid roles/credentials/certs | Security config or client shift | Check TLS/roles/secret rotation |
| **Protocol/codec** | Type decode/encode error, handshake diff | Driver/Native Protocol/JDK | Compatibility matrix and integration tests |
| **Data mismatch** | Query succeeded yet marker differs | Concurrent writers, timestamp/tombstone, or regression | Check manifest, CL, repair, and write history |
| **Service/API** | HTTP 5xx before CQL ever sent | App logic, queue/cache/downstream | Separate HTTP-layer logs from Cassandra |

**A `WriteTimeout` does not guarantee the write failed to persist.** Mutations may have reached some replicas without returning an ACK to the client; never retry LWTs/counters/batches or mint new UUIDs without evaluating idempotency. For `ReadTimeout`, the read never completed, so never report the record as absent.

Log by **request ID, query shape (no PII), anonymized partition bucket/key, CL, coordinator/DC, elapsed time, retry count, exception category, and timestamp**. Never write raw passwords, tokens, or customer payloads into benchmark logs.

## 9. Java Driver 4.x: Verifying Markers and End-to-End Measurements

The following snippet assumes **Java 17, Cassandra Java Driver 4.x**, the lab table already exists, and a reusable `CqlSession` is managed by the app. It **does not create clusters or upgrade nodes**; it reads one row by full primary key, compares against an expected marker, and measures client-side timing.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class UpgradeReadProbe {
    public enum State { FOUND_MATCH, MISSING_AT_CL, MISMATCH, READ_ERROR }
    public record Expected(
        String runId,
        LocalDate eventDay,
        Instant eventTs,
        UUID eventId,
        String status,
        int version,
        BigDecimal amount,
        String payload) {}
    public record Result(
        State state, long latencyMicros,
        String coordinator, String errorType) {}

    private final CqlSession session;
    private final PreparedStatement read;

    public UpgradeReadProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT status, version, amount, payload " +
            "FROM upgrade_verify_lab.events_by_run_day " +
            "WHERE run_id = ? AND event_day = ? " +
            "AND event_ts = ? AND event_id = ?");
    }

    public Result verify(Expected expected) {
        BoundStatement statement = read.bind(
                expected.runId(), expected.eventDay(),
                expected.eventTs(), expected.eventId())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            ExecutionInfo info = result.getExecutionInfo();
            String coordinator = info.getCoordinator() == null
                ? "unknown" : info.getCoordinator().getEndPoint().toString();
            Row row = result.one();
            long elapsed = elapsedMicros(started);

            if (row == null) {
                return new Result(
                    State.MISSING_AT_CL, elapsed, coordinator, null);
            }
            BigDecimal actualAmount = row.getBigDecimal("amount");
            boolean amountMatches =
                actualAmount != null && expected.amount() != null
                && actualAmount.compareTo(expected.amount()) == 0;
            boolean matches =
                Objects.equals(expected.status(), row.getString("status"))
                && expected.version() == row.getInt("version")
                && amountMatches
                && Objects.equals(expected.payload(), row.getString("payload"));
            return new Result(
                matches ? State.FOUND_MATCH : State.MISMATCH,
                elapsed, coordinator, null);
        } catch (RuntimeException error) {
            return new Result(
                State.READ_ERROR, elapsedMicros(started),
                "unknown", error.getClass().getSimpleName());
        }
    }

    private static long elapsedMicros(long started) {
        return TimeUnit.NANOSECONDS.toMicros(System.nanoTime() - started);
    }
}
~~~

**Important details to note:**

- `LOCAL_QUORUM` requires proper RF and local DC setup. Never use one local read as proof that replicas in all DCs received a mutation.
- `getInstant()/Instant`, `UUID`, `LocalDate`, and `BigDecimal` preserve exact data-type semantics, avoiding timezone string comparisons.
- `BigDecimal.compareTo` compares **numeric value**; if contracts preserve exact **scale**, compare `scale()` or canonical representations too.
- `MISSING_AT_CL` occurs only when `SELECT` **succeeds** with zero rows; `READ_ERROR` logs exceptions separately. Expected deleted/TTL records must use their own category rather than flagging missing as failure.
- `System.nanoTime()` measures **monotonic duration**; client latency spans driver/network/server. For p95/p99, gather large samples, build histograms, and isolate errors.
- `ExecutionInfo.getCoordinator()` reports the coordinator chosen per driver info; it does not tell whether every replica participated or whether repair ran.
- The code logs only **exception class names**, never sensitive data. Production needs request IDs, metrics, retry budgets, circuit breakers/backpressure, and granular exception handling.
- `setIdempotence(true)` fits the pure `SELECT` here; **never** copy it blindly onto side-effecting mutations without an idempotency policy.

### Session Configuration for Before/After Comparison

Example connection setup in one DC:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

// Use real lab IP/hostname and configure TLS/auth from secret manager.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
        .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    UpgradeReadProbe probe = new UpgradeReadProbe(session);
    // Read Expected list from independent manifest and call probe.verify(...).
    // Collect results in a controlled metrics/audit system.
}
~~~

These addresses are private lab examples. Real apps require TLS, authentication, hostname validation, Java runtime, native protocol, and timeout settings matching the active version pair. **Reuse the session** on real request paths; never open a new session per record.

## 10. Verifying Mixed Versions During Rolling Upgrades

A **rolling upgrade** swaps one node or small group at a time to keep services online. However, not every version pair can run side-by-side; check upgrade-path/mixed-version guidance **before** starting.

### 10.1. Checkpoints

~~~mermaid
flowchart TD
    A["Lock compatibility + backups + baseline"] --> B["Canary in staging"]
    B --> C{"Queries/data/SLOs PASS?"}
    C -->|No| X["Halt, investigate, apply approved rollback/forward recovery"]
    C -->|Yes| D["Upgrade one node / small rack unit"]
    D --> E["Check node/ring/schema, data, Java, and metrics"]
    E --> F{"Mixed-version gate passed?"}
    F -->|No| X
    F -->|Yes| G["Advance node by node by failure domain"]
    G --> H["Measure steady post-upgrade state"]
    H --> I{"Go / No-Go"}
    I -->|Go| J["Monitor + verify backup/restore"]
    I -->|No-Go| X
~~~

### 10.2. Why Node Selection Order Matters

Suppose RF3 in one DC with clients using `LOCAL_QUORUM`. While **one node is down for upgrade**, the two remaining live replicas of a partition barely satisfy quorum. If a second replica fails concurrently, quorum breaks. With `ALL`, even one down node breaks affected partitions.

Across multiple DCs, compute RF and CL **per datacenter**. `LOCAL_QUORUM` from a `dc_a` coordinator cannot accept ACKs from `dc_b` to make up local quorum. Never schedule multi-node/rack stops solely from cluster-wide node counts.

Checks between every round include:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Combine Cassandra logs, Java Driver metrics, schema agreement, and synthetic CQL checks. `UN` does not mean repair/streaming finished or remote data converged.

### 10.3. Client Testing in Mixed-Version Environments

Within the window **documented as supported by release docs**, run the exact same Java Driver suite:

1. Run prepared `SELECT`s with full partition keys; log which coordinator version served them.
2. Write new markers at designed CLs; classify ACK vs. UNKNOWN.
3. Read markers back after ACK at the right CL/location and verify values.
4. Test LWTs, paging, nulls/codecs, and auth/TLS for workloads using them.
5. Compare latency/error distributions by coordinator version, node/DC, and timestamp.

Never try to force the driver to hit only the new version by passing only one new IP as a contact point. After discovery, the Java Driver routes to other nodes too. To measure per-version canaries, use controlled observability/routing with documented limitations rather than hacking production policies.

## 11. Tracing, Repair, Compaction, and Data Compatibility

When latency climbs post-upgrade, never assume "the new engine is slower." Possible causes include:

- Nodes **warming caches** and reading more SSTables from disk.
- **Compaction/streaming/repair** driving post-restart disk I/O and network load.
- **Digest mismatches/read repairs** from replicas that were down during rolling windows.
- Java Driver retries/speculative executions amplifying load when one node slows down.
- Schema/index/codec shifts or incomplete readiness across all nodes.
- Metric/stage renames making dashboards read zero or drop telemetry.

### Selective Diagnostic Command

In a `cqlsh` session for **a bounded single partition**:

~~~text
TRACING ON
~~~

~~~sql
SELECT event_ts, event_id, status, version
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Tracing reveals data vs. digest requests, extra reads, read repairs, slow replicas, and coordinator work. It adds overhead, so **never enable it broadly in production**. Correlate trace IDs with metrics/logs of the exact node/version and CL state.

### Repair Is Not a Business Data Verification Tool

`nodetool repair` runs anti-entropy across replicas within supported ranges/workflows, yet:

- It cannot recreate events **never written to any replica**.
- It does not replace expected-ID manifests or query/LWT/driver tests.
- It consumes heavy disk I/O, CPU, and network and inflates p99; never run major repairs alongside an upgrade unless planned.
- It cannot undo **tombstones purged on other replicas** if a node stayed down too long; zombie risk requires handling downtime relative to `gc_grace_seconds`.

Likewise, compaction creates **local** SSTables and never proves replicas or full app datasets match.

### SSTable Formats and Steps Never to Run Blindly

Some upgrade paths include SSTable format conversions (e.g., admin tools where supported by the release). These steps can **restrict or eliminate reverting to the old version**. Execute them only after verifying the exact runbook, securing off-cluster backups, and knowing **until when rollback remains viable**. Never paste "upgrade SSTables" into a generic checklist across arbitrary versions without checking compatibility.

## 12. Auditable Before/After Comparison Report

### 12.1. Report Template

~~~text
CHANGE_ID:                 CHG-EXAMPLE-001
CLUSTER/DC:                lab-cassandra / datacenter1
SOURCE_VERSION:            <actual version per node>
TARGET_VERSION:            <approved target version>
DRIVER/JVM_VERSION:        <actual versions>
UPGRADE_PATH_SUPPORTED:    verified / unknown / not supported
BACKUP_RESTORE_DRILL:      pass / fail / not tested
BASELINE_WINDOW:           <start UTC> .. <end UTC>
ROLLING_WINDOW:            <start UTC> .. <end UTC>
POST_STABLE_WINDOW:        <start UTC> .. <end UTC>
QUERY_SHAPES_TESTED:       ...
EXPECTED_ACKED_KEYS:       ...
FOUND_MATCH:               ...
EXPECTED_ABSENT_MATCH:     ...
MISSING_AT_CL:             ...
MISMATCH:                  ...
READ_ERROR:                ...
UNKNOWN_WRITE:             ...
P50/P95/P99_READ:          before -> after
P50/P95/P99_WRITE:         before -> after
ERROR_RATE_BY_CATEGORY:    before -> after
NODE/REPLICA_HEALTH:       ...
SCHEMA_AGREEMENT:          ...
COMPACTION/STREAMING:      ...
OPEN_GAPS:                 ...
DECISION:                  GO / NO_GO / INVESTIGATE
OWNER/APPROVAL:            ...
~~~

**All `...` fields above are placeholders**, not measured numbers. Attach test IDs, per-query-shape breakdowns, latency stats with sample sizes, node restart timestamps, and any sample exclusion reasons.

### 12.2. Hypothetical Results Example

| Item | Observation | Decision |
| --- | --- | --- |
| Ring | 3/3 nodes `UN` post-upgrade | Preliminary PASS |
| Schema/driver | 24/24 query cases succeeded | Functional PASS |
| Data | 999 `FOUND_MATCH`, 1 `MISMATCH`, 0 read errors | **Data FAIL**, investigate mismatched ID |
| p95 | 20 ms → 23 ms | PASS against 1.25x limit |
| p99 | 45 ms → 82 ms | **FAIL** against 1.5x limit |
| Errors | 2 → 18 / 10,000 requests | Classify and check against budget |
| Recovery | Backups exist, restore drill untested | **GAP**, insufficient DR evidence |

These results **fail GO criteria**, even though ring/nodes are healthy and sample CQL runs cleanly. A value mismatch might stem from concurrent writes during testing rather than the new version: **preserve IDs, expected values, write history, and CLs** to investigate. Never ignore a mismatch and continue rolling as if it passed.

### 12.3. A Helpful Flow Diagram

~~~mermaid
flowchart LR
    D["All readback results"] --> M["FOUND_MATCH"]
    D --> A["EXPECTED_ABSENT_MATCH"]
    D --> X["MISSING / MISMATCH"]
    D --> E["READ_ERROR"]
    X --> H["Investigate data/replicas/contract"]
    E --> T["Investigate timeouts/availability"]
    M --> G["Quality gate"]
    A --> G
    H --> G
    T --> G
    G --> Z{"GO / NO-GO?"}
~~~

Never compute **`FOUND_MATCH` rate over only succeeded requests** while ignoring `READ_ERROR`. Unreadable records stay in the unverified denominator yet must be **reported separately** rather than labeled missing.

## 13. Verification Runbook at Each Checkpoint

### Checkpoint A — Pre-Upgrade

1. Lock version path/compatibility, cluster topology, and SLO targets.
2. Verify off-cluster backups, decryption, and restore drills.
3. Freeze/guard against unplanned schema changes; build query catalog.
4. Measure steady baseline under representative load, capturing both successes and errors.
5. Lock expected manifest for rows/`DELETE`/TTL/LWT, recording ACK states.
6. Define fault budget: max down nodes per DC/rack, stop gates, and rollback/forward recovery.

### Checkpoint B — After Canary / First Node

1. Verify node/version/metadata and internode/driver connectivity.
2. Run **read-only regressions** first; run mutating tests only on dedicated test tables/run IDs.
3. Verify local DC CLs, schema agreement, prepared queries, paging, and TLS/auth.
4. Reconcile a set of older markers alongside newly ACKed markers.
5. Record latency and error categories per coordinator/node; watch compaction/streaming.
6. **Halt advancing** on severe mismatches, lost quorum, or error rate/p99 breaching gates.

### Checkpoint C — After Each Subsequent Node

1. Repeat the concise checklist rather than waiting until the whole cluster finishes to spot bugs.
2. Watch previously down nodes, hinted handoff/repair, schema metadata, and token placement.
3. Never advance to the next node while quorum/health or prior gates fail.
4. Log exact restart/version-switch timestamps to correlate incidents with metrics.

### Checkpoint D — After Full Cluster Upgrade

1. Wait for a **predefined steady state**, rather than imposing one fixed wait time on every cluster.
2. Run the full regression suite and reconcile data against manifest/CLs.
3. Measure p50/p95/p99, throughput, and error rates at matching load; inspect per-node resources.
4. Verify ops tools, backups, restores, repair schedules, and alerts.
5. Sign off GO only when mandatory gates PASS and open gaps have owners/decisions.

## 14. Common Diagnostic Scenarios

| Symptom | Hypotheses to separate | Evidence to collect |
| --- | --- | --- |
| Node `UN` yet `SELECT` returns wrong values | Concurrent mutation, TTL/tombstones, replica divergence, schema/codec | Manifest, CL, tracing, write history |
| Post-upgrade read tests time out | Lost quorum mid-roll, slow node, disk I/O, WAN | `status`, client errors, coordinator, node metrics |
| p99 spikes while p50 stays flat | GC pauses, compaction backlog, streaming, retries | Per-query/node p99, GC, I/O, retries |
| Query syntax rejected | Unsupported CQL feature/option, un-converged schema | Error message, schema/query catalog, version matrix |
| Java session fails to initialize | TLS/auth, native protocol, local DC, driver/runtime | Driver logs, endpoints, certificates |
| Paging drops or duplicates rows | Mutating dataset, token/page handling, query shape | Freeze dataset, paging-state contract, row IDs |
| LWT differs from baseline | Different initial state, serial CL, or real regression | `[applied]`, PK, prior state, LWT logs |
| Decimal/timestamp values differ | Scale/codec/timezone or altered source normalization | Typed readback, `BigDecimal`/`Instant`, contract |
| Remote DC misses recent writes | `LOCAL_QUORUM` only ACKs local; WAN/replication lag | DC routing, CL, hints/repair, manifest |
| Repair runs too long post-upgrade | Overly broad token ranges, resource limits, version/config | Repair logs, streaming, compaction, network |
| Rollback fails to boot | SSTable/schema/protocol changed; downgrade unsupported | Upgrade path, backups, restore validation |

### When Is Immediate NO-GO Required?

- Any mandatory ACKed record shows an unexplained `MISSING`/`MISMATCH`.
- Insufficient replicas for business CLs or unexpected multi-node disconnects.
- Critical LWT/DDL/query contracts fail, especially around financial or identity data.
- Error rates or latency breach **agreed stop thresholds**, even if passing requests stay fast.
- Backups/restores/recoverability fail change readiness criteria.
- An unsupported upgrade/mixed-version path or unviable fallback plan is discovered.

**NO-GO does not automatically mean "downgrade the node immediately."** First preserve data/manifests/logs, stabilize traffic, and choose **rollback, failover, restore, or forward-fix** per actual compatibility.

## 15. Practice Exercises

**Exercise 1 — Defining gates.** A team proposes "upgrade complete when all nodes are `UN`." Add data, query, latency/error, and restore criteria, explaining what each protects against.

**Exercise 2 — Manifest.** 100 events were ACKed pre-upgrade; post-upgrade yields 97 `FOUND_MATCH`, 1 `MISSING_AT_CL`, and 2 `READ_ERROR`. Can you conclude three events were permanently lost? What extra evidence is needed?

**Exercise 3 — Primary keys and projections.** On `events_by_run_day`, write a `SELECT` for one exact event and a 08:00–09:00 range `SELECT` within the same partition returning only `event_ts`, `event_id`, and `status`. Why avoid `ALLOW FILTERING` or full-table scans for regression checks?

**Exercise 4 — TTL/`DELETE`.** A row expires via TTL between two runs. Why is this not automatically an upgrade bug? Design a test suite covering read-before-expiry, read-after-expiry, and `DELETE` with timestamped manifests.

**Exercise 5 — LWT.** You run `INSERT ... IF NOT EXISTS` twice with the same key and the second returns `[applied]=false`. Is that a regression? Design independent pre/post tests with matching initial states.

**Exercise 6 — Tail latency.** Baseline p95=20 ms, p99=45 ms; post p95=23 ms, p99=82 ms. With gates at p95×1.25 and p99×1.5, which metric FAILS? Why inspect timeouts and compaction too?

**Exercise 7 — Mixed versions.** RF3, `LOCAL_QUORUM`, one node stopped for upgrade while another node was already down. Does that partition still have quorum? Can the next node upgrade?

**Exercise 8 — Java Driver.** Use `UpgradeReadProbe` to check 20 manifest markers at two timestamps. Collect `coordinator`, `latencyMicros`, and `FOUND_MATCH/MISMATCH/MISSING/READ_ERROR` states; compare by ID, not just row count.

**Exercise 9 — Multi-DC.** Cluster has `dc_a:3` and `dc_b:3`. A write in `dc_a` receives a `LOCAL_QUORUM` ACK pre-upgrade; an immediate read in `dc_b` misses it. Explain why this is valid, how to measure replication lag, and pre-failover checks.

**Exercise 10 — Compatibility.** You plan to change Cassandra server, JDK, and Java Driver together. How will you check compatibility matrices, regression suites, and isolate latency causes? When should changes be split into separate waves?

**Exercise 11 — Rollback.** A supported SSTable format conversion ran post-upgrade; the old binary cannot read the new format. Why can you not simply boot the old binary on the same data directory? Propose a tested restore/forward-fix plan.

**Exercise 12 — Incident report.** An API query returns 200 OK, yet one row has wrong `amount` scale/value and p99 jumped 80%. Draft a NO-GO record with data evidence, error/latency stats, timestamps, and owners without blaming the new version before ruling out concurrent writers, codecs, and background load.

## Remember

**Verifying Cassandra upgrades requires checking four dimensions fairly: data, queries, latency, and errors—at baseline, every rolling checkpoint, and steady state post-upgrade.** `UN` nodes do not prove complete data; `COUNT(*)` does not prove individual events match; good p50 cannot excuse bad p99 or timeouts; and a write timeout does not mean the mutation never landed. Prepare **an independent manifest of ACKed records**, a primary-key and CL-aligned CQL/Java regression suite, latency/error histograms broken down by query/node/DC, plus **verified backups/restores and pre-set GO/NO-GO gates**. Proceed only on evidence satisfying your contract, and verify downgrade feasibility strictly along documented version paths—never assume it.
