# Data Reconciliation, Business Invariants, and Post-Restore Metrics

> **Chapter:** Backup and Recovery  
> **Scope:** Apache Cassandra — a *wide-column* distributed database storing data in SSTables, replicating by token/rack/datacenter, and serving CQL through the Java Driver. This lesson focuses on **verifying correctness after recovery**, not merely putting files back onto a cluster.
>
> **Learning objectives:** Establish a recovery point and expected dataset; reconcile completeness by partition/token range; inspect TTLs, tombstones, timestamps, and relationships across denormalized tables; define business invariants; measure RPO, RTO, latency, and divergence rates; and make a *go/no-go* decision before opening traffic.

## 1. Restore Reports Success Yet the Application Can Still Be Wrong

Suppose a Cassandra cluster storing orders loses several nodes. Operations restores from SSTable snapshots and streams data into a new cluster. Tools report zero errors, `nodetool status` shows every node `UN` (*Up/Normal*), and the Java application connects cleanly.

However, when canary traffic opens:

- Some orders show status `PAID` yet lack their corresponding payment event.
- `orders_by_id` has an order, while `orders_by_customer_day` serving the customer order list is missing it.
- A pre-incident `DELETE` was not fully reflected, causing deleted records to reappear.
- TTL data expired, yet the reconciliation report misflags it as "data loss."
- Data from after the snapshot timestamp is missing, and the team does not know whether the RPO target was breached.

**Technical restore success differs from business correctness.** You must prove all five simultaneously:

1. **Scope completeness:** required partitions/token ranges actually hold data.
2. **Right data versions:** values, timestamps, TTLs, and deletion markers reflect recovery policy.
3. **Valid business relationships:** projections, event histories, and state records do not contradict each other outside agreed consistency bounds.
4. **Serviceability:** Java/CQL queries matching access patterns hit desired consistency levels, latency, and availability.
5. **Matches recovery targets:** data loss and downtime are transparently measured against RPO/RTO.

```text
Snapshot / backup / log replay / streaming
                  |
                  v
     Files and replicas report restore done
                  |
                  v
    Storage-level and token-range reconciliation
                  |
                  v
         CQL data-level reconciliation
                  |
                  v
    Check business invariants, TTL,
    deletes, projections, and transaction flows
                  |
                  v
      App canary + p95/p99 + RPO/RTO
                  |
                  v
         Go / no-go / rollback decision
```

One successful `SELECT` on one partition **does not replace** all of these steps.

## 2. First Establish: "Recover to What Point in Time?"

Cassandra is a distributed system with multiple replicas and query-driven tables. A local snapshot on one node does not automatically form an **atomic cluster-wide image**. Nodes may snapshot at different instants, receive mutations at different CLs, and have in-flight writes when snapshots start.

Therefore, before reconciling, define the **recovery contract**:

| Field | Meaning | Illustrative Example |
| --- | --- | --- |
| `T_restore_target` | Business data point desired for recovery | 14:00 UTC |
| `T_snapshot` | Snapshot timestamp(s) and per-replica states | 13:45–13:47 UTC |
| Replayable logs / CDC | Up to what time post-snapshot mutations can replay | Available up to 13:58 UTC |
| Quorum / replica condition | Does the source cover mutations ACKed per CL? | Must verify by RF/DC |
| Scope | Keyspaces, tables, token ranges, DCs, business domain | Orders and payment events |
| Accepted exclusions | Changes outside the recovery boundary | Excludes writes after 13:58 |
| TTL / delete policy | How expired/deleted data must be evaluated | Evaluated against real wall-clock read time |
| Reference source | Manifests, ledgers, independent event systems, audit logs | Watermarked event manifest |

### Snapshots Are Not Cross-Table Point-in-Time Transactions

An order may be written to `orders_by_id` at 13:46:30 and projection `orders_by_customer_day` at 13:46:31. If snapshots of those two tables/replicas fall in between, restored state can contain one record while missing the other—**even though every SSTable is valid**.

If a unified recovery point across tables is needed, engineer an application workflow: writer controls, verifiable checkpoints/watermarks, complete backup/CDC capture, and post-restore reconciliation. Never assume "snapshotted at 13:46" guarantees a multi-partition transaction was captured atomically.

### Separate Three Timestamps

- **Business event time:** `event_time`/`created_at`; may be client-supplied, late-arriving, or backfilled.
- **Cassandra mutation timestamp:** used during reconciliation when competing versions/tombstones collide; can differ from event time.
- **Backup / restore time:** when snapshots, replays, or loads occurred; **not automatically** the write timestamp of imported data.

Pick a reconciliation cutoff that **your data sources can actually prove**. Without post-snapshot logs, never claim you recovered all mutations up to incident onset.

## 3. Measure RPO and RTO After Verification, Not When Processes Exit

**RPO (Recovery Point Objective)** is the business-acceptable data loss measured in time. **RTO (Recovery Time Objective)** is the allowed service restoration time.

Example:

```text
13:52  Last business event verified as recovered.
14:00  Incident begins disrupting service.
14:20  Start building cluster from snapshots.
15:05  Streaming reports completion.
15:40  Data reconciliation and invariants pass; canary meets SLOs.
15:50  Open production traffic and confirm stability.

Illustrative data-loss window: 14:00 - 13:52 = 8 minutes.
Service recovery time:         15:50 - 14:00 = 110 minutes.
```

These numbers are illustrative only. In reality, "seeing one late event" is not proof every earlier event recovered. You need **continuous checkpoints and manifests covering the full scope** to bound potential data loss. When unproven, report `RPO=unknown` or a **qualified range**—never invent an exact figure.

**Never stop the RTO clock at 15:05:** finishing streaming while data/canaries remain unverified does not mean the service is restored to SLOs.

### Numbers That Must Be Reported Separately

| Metric | Never Confuse With | Evidence |
| --- | --- | --- |
| Backup age | Achieved RPO | Snapshot timeline, log replay, watermark |
| Streaming duration | Actual RTO | Loader / rebuild logs |
| Validated recovery point | Backup file creation date | Manifest and event coverage up to cutoff |
| Service recovery time | Time first node turns `UN` | Data validation + API SLOs + cutover |
| Restore completeness | GiB transferred cleanly | Range, partition, and external-source checks |

## 4. Designing a "Source of Truth" for Reconciliation

If the restored Cassandra table is used **to validate itself**, you prove only internal self-consistency, not that it matches what ought to exist.

The reference source should stay **independent of the cluster being restored**, respecting privacy and security policies:

- Operational backup manifests: schema/version, token ranges, SSTable inventory, checksums, and checkpoints.
- Application audit/event ledger (when available), stored in a separate failure domain from Cassandra.
- Deterministically replayable changelogs with event IDs and watermarks.
- Accounting/payment reports or independent upstream business systems.
- Pre-incident benchmark key/test suites: hot customers, paid orders, deleted orders, TTL records, and boundary cases.

**Not every system has an independent ledger.** When lacking one, state the lower evidence tier explicitly: e.g., file integrity and partition coverage match the SSTable manifest, without proving "zero ACKed orders were lost."

### What Should a Good Manifest Contain?

**Illustrative format** example, not a default Cassandra schema:

```json
{
  "restore_id": "restore-lab-2026-11-21-a",
  "target_cluster": "cassandra-dr-lab",
  "source_cluster": "cassandra-primary-lab",
  "checkpoint_utc": "2026-11-21T13:58:00Z",
  "keyspace": "lab",
  "tables": ["orders_by_id", "orders_by_customer_day",
             "payment_events_by_order"],
  "partitioner": "org.apache.cassandra.dht.Murmur3Partitioner",
  "rf_by_dc": {"dc1": 3},
  "expected_token_ranges": "see-signed-range-inventory",
  "sstable_manifest": "see-signed-file-inventory",
  "business_event_watermark": "payment-event-seq-000200",
  "excluded_mutations_after_checkpoint": true
}
```

Fields such as `expected_token_ranges` and `sstable_manifest` here are **references** to inventory artifacts, not assertions that those strings themselves hold full proof. Manifests need tamper controls, creation timestamps, and strict access controls; avoid storing unnecessary sensitive customer data.

## 5. Four Reconciliation Layers: Files, Replicas, Logical Data, and Business

| Layer | Core Question | Verification Check | Limitation |
| --- | --- | --- | --- |
| **Files and backups** | Are all files/components present for the right snapshot? | Inventory, hashes/checksums, SSTable metadata | Intact files do not prove valid business state |
| **Token ranges and replicas** | Did data reach all required ranges/replicas? | Topology, streaming logs, coverage, and repair history | Converged replicas can still all miss a mutation |
| **Logical CQL data** | Are keys, columns, values, TTLs, timestamps, and deletes right? | Partition-key queries, manifest cross-check, bounded samples/scans | Samples do not prove the entire table |
| **Business invariants** | Are order states, payments, projections, and balances valid? | Multi-table and ledger cross-checks, rule evaluation | Requires understanding write flows and cross-table consistency boundaries |

Optimize cost by progressing **from broad to deep**: verify source integrity and coverage first, then logical reconciliation by range/bucket, and finally high-risk business invariants.

### SSTable Checksums Do Not Replace Business Checksums

A matching SHA-256 hash on `Data.db` proves copied bytes match the hashed source. It **does not** prove:

- Source files held all necessary data.
- Tombstones remain alive to shadow old data.
- The target cluster schema interprets columns accurately.
- Business joins/projections do not contradict each other.
- All live replicas currently hold identical values.

Conversely, when reconciling logical values post-import, **do not demand target SSTable hashes equal source SSTable hashes**: compaction, format, compression, token placement, and SSTable layout can differ while logical data matches identically.

## 6. Illustrative Table Model for Verification

Suppose a demo business rules that each order has one canonical state record, one customer listing projection, and one payment event history. These tables serve **distinct query patterns**, not a relational model with automatic foreign keys.

### Canonical State Table by Order ID

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_day date,
    created_at timestamp,
    status text,
    total decimal,
    updated_at timestamp,
    last_event_id uuid
);
```

### Order Listing Projection by Customer / Day

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    total decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

### Payment Event History by Order

```cql
CREATE TABLE IF NOT EXISTS lab.payment_events_by_order (
    order_id uuid,
    event_time timestamp,
    payment_event_id uuid,
    outcome text,
    amount decimal,
    PRIMARY KEY ((order_id), event_time, payment_event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, payment_event_id ASC);
```

Examples run only in a **pre-existing `lab` keyspace in a learning environment**. In production, schemas must fit query/partition sizes, RF/DC, and real payment flows. These examples do not claim Cassandra provides ACID transactions across three tables.

### Seeding Lab Sample Data

```cql
INSERT INTO lab.orders_by_id
    (order_id, customer_id, order_day, created_at, status,
     total, updated_at, last_event_id)
VALUES (
    11111111-1111-4111-8111-111111111111,
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T10:00:00Z',
    'PAID',
    250.00,
    '2026-11-21T10:05:00Z',
    33333333-3333-4333-8333-333333333333
);

INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, total)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T10:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'PAID',
    250.00
);

INSERT INTO lab.payment_events_by_order
    (order_id, event_time, payment_event_id, outcome, amount)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T10:05:00Z',
    33333333-3333-4333-8333-333333333333,
    'CAPTURED',
    250.00
);
```

In this demo, **business rules explicitly specify one payment per order, no installments, and no refunds**; under these rules, `PAID` pairs with a `CAPTURED` event matching the order total. Real systems with partial captures, refunds, or multi-currency need different invariants; never treat this example as a universal accounting rule.

## 7. Reconciling Keys, Partitions, and Token Ranges

### Step A — Establish Which Keys Should Exist

Use the manifest locked at `T_restore_target` or a proven checkpoint to build the list of **expected keys**.

Never take a `SELECT` from the restored table itself as your sole list—if a partition went missing, it will not appear in that list and will silently escape verification.

Sample groups should include:

- Hot keys and rarely read cold keys.
- Customers with small and large partitions across diverse tokens.
- Orders created right before the checkpoint.
- Records updated multiple times.
- Cancelled/deleted orders; **absence** must also be verified.
- TTL records nearing expiration.
- Data from nodes/DCs that previously experienced failures.

### Step B — Read by Exact Partition Key

```cql
SELECT order_id, customer_id, order_day, created_at,
       status, total, updated_at, last_event_id
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Cross-check against manifest/ledger: present or absent, exact values, timestamps, and state. A lone `SELECT` at `LOCAL_ONE` does not prove replicas agree. Pick a CL matching RF and verification goals; when validating across DCs, verify explicitly with awareness of local DC and replication.

### Step C — Ranges Must Be Covered

Cassandra assigns tokens from partition keys. When sourcing snapshots from multiple nodes, the inventory must confirm:

- Which token ranges were covered by source snapshots.
- Which ranges streamed to target replicas.
- Which nodes/DCs were ever offline or failed to complete restore.
- Whether every expected range holds a **passing verification result**.

Never treat `UN` node counts as proof of full token-range coverage, and never assume one snapshot on an RF=3 node represents the entire keyspace.

### Step D — Do Not Abuse Full-Table `COUNT(*)`

```cql
-- Avoid full-table scans on massive tables as a recovery test:
SELECT COUNT(*) FROM lab.orders_by_id;
```

Cassandra maintains no automatically updated, cheap metadata row counter per table. Full-table `COUNT(*)` reads massive amounts of data, driving heavy I/O and timeouts—especially right after streaming/compaction.

Instead use source manifests, token/bucket inventories, rate-limited bounded scan jobs, or verified external business reports. If using `COUNT(*)` in a tiny lab table, recognize it is **only a secondary sanity check**, proving nothing about individual values.

## 8. Business Invariants: What Must Hold After Restore

An **invariant** is a business condition that must hold in any valid system state. Cassandra does not enforce foreign keys or unique constraints across all partitions; applications must design writes, projection sync, and reconciliation.

For the demo system above, we can define:

| ID | Invariant | How to Check |
| --- | --- | --- |
| INV-01 | Every `order_id` in the manifest has a canonical state matching the recovery point | Query `orders_by_id` and compare against expected |
| INV-02 | `total` is non-negative; `customer_id` and required keys are valid | Check types, values, and domain bounds |
| INV-03 | If status is `PAID`, a matching `CAPTURED` event exists with `last_event_id` and `amount = total` per demo model | Read payment history and cross-check |
| INV-04 | Listing projection matches canonical `status`, `total`, keys, and creation timestamp at checkpoint | Read both tables by respective primary keys |
| INV-05 | Keys deleted/cancelled per manifest and domain policy must not unexpectedly reappear | Query negative keys and inspect tombstone/replay history |
| INV-06 | Zero payment events ACKed before checkpoint are missing | Compare against independent ledger/event manifest |
| INV-07 | Published financial totals match the valid transaction set | Compare against approved ledger totals |

This is an **illustrative contract**. Real workloads may permit `PAID` before projections catch up within an eventual-consistency window; in that case, establish a **checkpoint/quiescence and convergence SLA** before flagging violations.

### Do Not Turn Eventual Consistency into False Alarms

An application may write the canonical table first and update projections asynchronously. Normally, the two can lag by seconds or minutes. To verify post-restore:

1. Pick a **watermark** showing which events all consumers have applied.
2. Wait for projections/consumers to reach that watermark, or run a designed backfill/reconciliation job.
3. Compare records within the **converged** boundary.
4. Separate "expected pending per design" from "mismatch beyond convergence SLA."

If snapshots fell between the two writes, reconciliation repairs the projection; never rely on Cassandra repair alone to synthesize business projections that were never written.

## 9. CQL Queries Reconciling Each Invariant

### Checking Canonical State and Projection

```cql
SELECT order_id, customer_id, order_day, created_at, status, total
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

```cql
SELECT order_id, status, total
FROM lab.orders_by_customer_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T10:00:00Z'
  AND order_id = 11111111-1111-4111-8111-111111111111;
```

Because the projection uses composite partition key `(customer_id, order_day)`, verification binds both partition components and matching clustering keys. **Never use `ALLOW FILTERING` to simulate general joins**; cross-table reconciliation belongs in verification tooling/application code.

### Checking Payment Events

```cql
SELECT payment_event_id, event_time, outcome, amount
FROM lab.payment_events_by_order
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Compare `last_event_id`, `outcome`, and `amount` against demo rules. Clustering `ORDER BY` and `LIMIT` help fetch recent events, yet proving **all events ACKed before checkpoint exist** requires reading beyond just the top five events.

### Checking Cell Timestamps and TTLs

```cql
SELECT status, WRITETIME(status), TTL(status),
       total, WRITETIME(total), TTL(total)
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` reveals the timestamp of eligible cells; `TTL` returns remaining seconds when set. If a column **has no TTL**, `TTL()` returns `null`—never interpret that as "expired." Check exact syntax/column-type support against your Cassandra version.

**Do timestamps change on restore?** With SSTable bulk loading, old timestamp metadata is generally preserved per format/loader mechanics. With ETL rewriting via new CQL writes, client/server may assign fresh timestamps. Both behave differently when merging against target values—always know which path you used.

## 10. TTL: Always Ask "Should This Exist Now?"

TTLs are a classic reconciliation pitfall. Suppose an event is written on Day D with a 7-day TTL and snapshotted on D+2. When restored on D+10, its logical TTL has expired.

**Do not count that event as "lost during restore"** simply because it is absent on D+10. Conversely, if policy demands retaining history past expiry, TTL-backed SSTable snapshots cannot meet retention rules—use a separate archival store per policy.

Distinguish cases:

| Case | Expectation After Restore |
| --- | --- |
| Non-TTL cell, undeleted, within checkpoint | Must remain present if in recovery scope |
| TTL cell, unexpired at check time | Should remain; verify expiration metadata and replicas |
| TTL cell, expired before check time | Expected absent from live reads |
| Cell validly `DELETE`d before checkpoint | Must not resurrect from older versions |
| Cell written after checkpoint with no log replay | Outside committed recovery scope; counts toward RPO |

### Watch `default_time_to_live` vs. Per-Cell TTLs

Tables may define a default TTL, while specific mutations pass `USING TTL`. Expiration deadlines can vary cell by cell within the same row. When comparing source and target, **never infer an entire row's lifetime from a single column's TTL**.

When cells expire, expiry/tombstone metadata can persist in SSTables until compaction qualifies to purge them; files remaining on disk do not mean cells should appear in CQL output.

## 11. Tombstones and the Risk of "Resurrecting" Data

Cassandra writes deletion markers (**tombstones**) so old versions stay hidden. Deleting does not instantaneously wipe copies across disks and replicas.

Imagine:

```text
T1: R1/R2/R3 hold order X = 'CANCELLED'.
T2: App runs DELETE order X; R1/R2 receive tombstone.
    R3 is offline and keeps the old version.
T3: Past grace, tombstones on R1/R2 are GC'd when eligible.
T4: Restore/repair mixes stale R3 with data lacking the tombstone.
    Order X risks reappearing ("zombie data").
```

`gc_grace_seconds` protects tombstones for a window so replicas that missed deletes can still be repaired. Tombstones qualify for purging only when both age and SSTable conditions hold; **passing grace does not mean instant automatic purging**.

After restore, verify:

- Were any source replicas offline longer than grace?
- Do snapshots retain complete tombstone/deletion history?
- Did the restore mix data from sources with differing repair states?
- Did any deleted record in the manifest reappear?
- Is there a safe repair plan and trusted source to rebuild replicas?

**Never rely on a late `nodetool repair` as an absolute guarantee.** If a critical tombstone was lost across healthy sources, repair cannot deduce business deletions. You may need to rebuild/restore from a trusted source and apply controlled data fixes with an audit trail.

## 12. Timestamps, Last-Write-Wins, and Post-Checkpoint Mutations

Cassandra typically reconciles cell versions using timestamps and tie-break rules. A later-imported SSTable is not necessarily "newer" than target data.

```text
Restored SSTable:
  order X = PENDING, cell timestamp 100

Target cluster already holds:
  order X = PAID, cell timestamp 200

If merged cleanly:
  timestamp 200 wins on read path.
```

`100` and `200` are illustrative comparison timestamps, not real Unix CQL timestamps. When timestamps tie, Cassandra applies secondary tie-breakers; never build reconciliation around "whichever file copied last wins."

### Difference Between "Keep Newest" and "Restore Exact Checkpoint"

If **point-in-time recovery at T=13:58** is required, data written after T **does not belong in the target state** even with higher timestamps. Loading an old snapshot into a table already holding newer writes does not roll the table back to T.

Pick an explicit strategy:

- Restore into a **brand-new empty table/cluster**, then cut over.
- Controlled replay of mutations per cutoff with clear old/new conflict rules.
- Use ETL/backfill when transforming schemas, enforcing idempotency and reconciliation.

**Bulk import ≠ table-wide rollback**, and **repair ≠ time travel**.

## 13. Count Reconciliation: Why Total Row Counts Mislead

Comparing "source had 5 million rows, target has 4.99 million" is insufficient to claim 10,000 rows were lost, because:

- Some TTL records expired by check time.
- Source and target snapshots represent slightly different times.
- Some records were validly `DELETE`d per policy.
- One table is a projection lagging slightly at the checkpoint.
- Counting queries missed token ranges or timed out.
- Multi-row/multi-cell tables can match row counts while holding wrong column values.

### Metrics Needing Explicit Definitions

| Metric | Suggested Definition | Must Accompany |
| --- | --- | --- |
| **Expected active keys** | Keys expected live per checkpoint and TTL/delete rules | Manifest + check timestamp |
| **Missing keys** | Expected keys absent from verification queries | Sample vs. full scope, CL, retries |
| **Unexpected keys** | Keys that should not exist yet are readable | Deleted/expired/source-of-truth check |
| **Value mismatch** | Same key, critical columns diverge from expected | Canonicalization rules |
| **Projection mismatch** | Query table disagrees with canonical table at checkpoint | Convergence watermark |
| **Invariant violations** | Breaches of defined business rules | Severity and blast radius |
| **Verified token coverage** | Fraction of ranges with passing check evidence | Denominator and source inventory |
| **Reconciliation lag** | Age of backlog needing repair, or watermark skew | Clocks and convergence SLA |
| **Performance degradation** | p95/p99/error rate breaching baseline/SLO post-restore | Load, CL, RF, DC |

With a verified set of expected live keys, you can compute:

```text
Completeness = verified_expected_keys / total_expected_live_keys

Example: 9,980 / 10,000 = 99.8%
Missing expected keys = 20
```

This number holds **strictly within the verified set**. If 10,000 is a *sample*, never report "the whole table is 99.8% complete" as direct measurement; label it **sample completeness** with confidence bounds/sampling methodology if extrapolating statistically.

### Inspect Critical Segments, Not Just Totals

Two systems both missing 20 orders:

- System A missed 20 cancelled test orders.
- System B missed 20 paid-but-unshipped orders.

The percentages match, yet **business risk is completely different**. Reports must segment by financial/severity tier and invariants: payments, access permissions, in-flight orders, erasure-mandated records, and idempotency keys.

## 14. Content Reconciliation with Hashes: Requires Canonicalization

You can hash logical contents across a partition/bucket for fast comparison, but only when **both sides agree on exact data representation**:

- Row ordering determined strictly by partition/clustering keys.
- `decimal` normalized per business rules (`250.0` vs. `250.00` equivalent financially).
- `timestamp` normalized to exact timezone and precision units.
- `uuid` formatted consistently.
- `null` clearly distinguished from empty strings.
- Maps/sets sorted deterministically before hashing; lists preserve meaningful order.
- Out-of-contract columns excluded consistently.
- TTLs and timestamps included in hashes if the contract requires **exact metadata**, not only visible CQL values.

```text
Illustrative canonical record:

order_id=11111111-1111-4111-8111-111111111111
customer_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
status=PAID
total_minor_units=25000
created_at_utc=2026-11-21T10:00:00.000Z

SHA-256(canonical_bytes) -> hash for logical comparison
```

Never equate "matching hashes" with "full table proven right" when token ranges or input keys are missing. Hashes also do not pinpoint which column diverged; mismatches require drilling down to keys/cells.

**Never require source SSTable file hashes to equal target SSTable file hashes as a logical check:** compaction and replica layout alter physical files.

## 15. Reconciling via Java Driver 4.x Against an Independent Manifest

The Java Driver is ideal for verifying **real business queries** at target consistency levels and local datacenters. The snippet below checks an expected record taken from an **off-cluster manifest**—never generate expected records from the restored table itself.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RestoreOrderVerifier {

    public record ExpectedOrder(
        UUID orderId,
        UUID customerId,
        LocalDate orderDay,
        Instant createdAt,
        String status,
        BigDecimal total
    ) {}

    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement projection;

    public RestoreOrderVerifier(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, order_day, created_at, status, total " +
            "FROM lab.orders_by_id WHERE order_id = ?"
        );
        this.projection = session.prepare(
            "SELECT status, total FROM lab.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? " +
            "AND created_at = ? AND order_id = ?"
        );
    }

    private Row one(PreparedStatement query, Object... values) {
        BoundStatement statement = query.bind(values)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);
        return session.execute(statement).one();
    }

    public void verify(ExpectedOrder expected) {
        Row canonical = one(byId, expected.orderId());
        if (canonical == null) {
            throw new IllegalStateException(
                "MISSING_CANONICAL " + expected.orderId());
        }

        if (!expected.customerId().equals(
                canonical.getUuid("customer_id")) ||
            !expected.orderDay().equals(
                canonical.getLocalDate("order_day")) ||
            !expected.createdAt().equals(
                canonical.getInstant("created_at")) ||
            !expected.status().equals(
                canonical.getString("status")) ||
            canonical.isNull("total") ||
            expected.total().compareTo(
                canonical.getBigDecimal("total")) != 0) {
            throw new IllegalStateException(
                "CANONICAL_MISMATCH " + expected.orderId());
        }

        Row listItem = one(
            projection,
            expected.customerId(),
            expected.orderDay(),
            expected.createdAt(),
            expected.orderId()
        );

        if (listItem == null ||
            !expected.status().equals(listItem.getString("status")) ||
            listItem.isNull("total") ||
            expected.total().compareTo(
                listItem.getBigDecimal("total")) != 0) {
            throw new IllegalStateException(
                "PROJECTION_MISMATCH " + expected.orderId());
        }
    }
}
```

This example targets **Java 17 or releases supporting `record`**. On older Java versions, replace `record` with an ordinary immutable class. Tables must exist with the schemas above; `CqlSession` needs proper auth, contact points, local DC, and sufficient RF for `LOCAL_QUORUM`.

Notes:

- `BigDecimal.compareTo` compares numeric monetary value, avoiding treating `250.0` as unequal to `250.00` unless domain rules demand identical scale.
- `Instant`/`LocalDate` must use the exact timezone and bucketing rules as writers.
- `setIdempotent(true)` fits read-only `SELECT`s; do not blindly enable speculative execution.
- `LOCAL_QUORUM` checks quorum only inside the coordinator's DC; validating multiple DCs requires running sessions/checks configured for each DC.
- Throwing on the first mismatch suits a demo; production batch checks must collect **totals, error buckets, anonymized keys, bounded retries, and summary reports**.
- Avoid logging full customer payloads, secret identifiers, or sensitive payment amounts.
- This snippet does not check `payment_events_by_order`; payment invariants need a separate read/check by `order_id` and `last_event_id`.

### When Reconciling Deleted Keys

Manifests must retain **keys that must not exist**. Verify by key:

```cql
SELECT order_id, status
FROM lab.orders_by_id
WHERE order_id = 44444444-4444-4444-8444-444444444444;
```

Returning zero rows reflects only the active CL at that instant; it does not prove every replica holds the tombstone. If an unexpected row appears, halt cutover for that data flow and investigate snapshot/TTL/delete/repair history before arbitrarily deleting it again.

## 16. Multi-Datacenter Checks and Consistency Levels

Suppose a keyspace uses `NetworkTopologyStrategy` with RF=3 in `dc1` and RF=3 in `dc2`.

A Java app in `dc1` reading `LOCAL_QUORUM` receives two `dc1` replica responses. An app in `dc2` also reads `LOCAL_QUORUM`, from `dc2`'s replica set.

**Two local quorums in different DCs have zero mandatory overlap.** Thus new data in `dc1` might not yet appear in `dc2` if replication had not finished before checkpoint/restore.

Reconciliation plans should:

1. Verify actual schema, RF, and datacenter/rack topology.
2. Confirm which DCs are in restore scope and which checkpoint applies to each.
3. Run business queries from clients pinned to the **right local DC** for each region.
4. Compare values against manifests and check cross-DC skew on critical keys.
5. Inspect repair/streaming history and incomplete ranges prior to cutover.
6. Explicitly record the CL used; never treat a `SELECT ONE` as proof replicas converge.

### Repair Does Not Replace Business Reconciliation

Anti-entropy repair reconciles replicas owning the same token ranges. It **does not know** that `PAID` requires a `CAPTURED` event in another table. If all three replicas hold the exact same broken projection, repair succeeds cleanly while business invariants remain violated.

Conversely, if three replicas diverge due to unsynced mutations, querying one partition through one coordinator can return varying results depending on CL and chosen replica. Address **both replica consistency and business consistency**.

## 17. Post-Restore Metrics: What Must the Dashboard Answer?

| Group | Metrics and How to Measure | Dependent Decision Threshold |
| --- | --- | --- |
| **Coverage** | % of token ranges restored/reconciled vs. inventory | Must cover 100% of mandatory scope before cutover |
| **Completeness** | Expected live keys, missing keys per manifest | Business tolerance; financial data is typically strict |
| **Extraneous data** | Unexpected / resurrected deleted keys | Deletion policy, compliance, severity |
| **Value accuracy** | Value mismatches per column/partition group | Canonicalization contract |
| **Projection** | Mismatch between canonical table and query-first tables | Watermark and convergence SLA |
| **Invariants** | Count/rate of INV-01…INV-07 violations | Business policy and risk tier |
| **Actual RPO** | Proven recovered checkpoint vs. incident time | Committed RPO; report unknown if proof lacks |
| **Actual RTO** | From disruption onset until data/traffic criteria pass | Committed RTO |
| **Resources** | Disk headroom, SSTable counts, compaction backlog, CPU/GC | Post-restore operational stability |
| **Application** | p95/p99 latency, timeouts, error rate, throughput by DC/query | Canary/ramp-up SLOs |
| **Post-checks** | Repair coverage, streaming errors, reconciliation backlog | Avoid lingering drift after cutover |

### Sample Post-Restore Report

```text
Restore ID: restore-lab-2026-11-21-a
Target checkpoint: 13:58 UTC
Source completeness evidence: 100% expected ranges inventoried
Destination coverage: 100% required ranges validated
Expected live keys checked: 10,000 (manifest verification scope)
Missing keys: 0
Unexpected deleted keys: 0
Value mismatch: 0
Projection mismatch after watermark: 0
Critical business invariant violations: 0
Restored watermark: 13:58 UTC (evidenced)
Business p99 at canary load: within approved SLO
RPO/RTO: reported with actual incident and cutover timestamps
Status: eligible for go/no-go review
```

Values illustrate a **report template**, not real cluster results. If only 10,000 random samples out of 10 million keys were checked, the report must say **10,000 sampled keys checked**, never "100% of data verified."

## 18. Post-Restore Performance: Accurate Data May Still Not Be Ready to Serve

Right after SSTable loading or rebuilds, nodes may still be:

- Receiving remaining data streams.
- Compacting many SSTables.
- Repairing to reconcile replicas.
- Warming OS page caches.
- Serving concurrent incoming application load.

A cluster with accurate data but thin disk headroom, deep compaction queues, or long GC pauses can still breach SLOs.

Check each relevant node:

```bash
nodetool status
nodetool tablestats lab.orders_by_id
nodetool tablestats lab.orders_by_customer_day
nodetool compactionstats
nodetool tpstats
nodetool netstats
```

Also watch CPU, disk read/write await, network saturation, JVM GC pauses, and free space. You can enable CQL tracing on **sample queries**:

```cql
TRACING ON;

SELECT order_id, status, total
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Tracing adds overhead; never enable it 100% in production just for reconciliation. `nodetool status` showing `UN` likewise **does not prove p99 latency or data correctness**.

### Compare Equivalent Workloads

Compare pre- and post-restore under:

- Identical query shapes and hot/cold partition distributions.
- Identical consistency levels, RF, and local DC.
- Representative read/write traffic including order state-transition workflows.
- Identical timeout/error rules and p95/p99 collection windows.
- Cache warm-up and compaction backlog tracking.

Never boast "p99 dropped 50% after restore" if the test load held less data or CL dropped from `QUORUM` to `ONE`.

## 19. Post-Restore Remediation Approaches and Their Limits

| Divergence | Do Not Do | Potentially Fitting Approach |
| --- | --- | --- |
| Missing subset of token ranges | Assume `UN` nodes suffice | Identify sources/ranges, stream missing slices from trusted source, re-verify |
| Replicas diverged | Run unplanned cluster-wide full repair | Scope repair properly, honoring tombstone and version safety |
| Projection missing while canonical table intact | Expect repair to invent unwritten projection rows | Backfill/rebuild projection **from canonical source** using checkpoints |
| Order `PAID` missing payment event | Fabricate fake events to clean up reports | Check independent ledger, determine real transaction, apply business resolution |
| Deleted record reappeared | Bulk-delete without root-cause analysis | Investigate tombstones/replicas/history, remediate with audit trail |
| Snapshot missing post-checkpoint mutations | Claim RPO=0 | Use provable logs/CDC or transparently report data loss |
| Data accurate yet p99 high | Merely bump driver timeouts | Inspect compaction, caching, disk, CPU, queries, and load |
| New column type decodes wrongly | Rename SSTable files to force load | Transform schema/data via compatible ETL |

### Fix Errors at the Right Layer

- **Replica repair:** reconciles copies of the same partition; never detects cross-table invariants.
- **Projection backfill:** rebuilds query-driven tables from canonical sources; write-heavy and requires idempotency.
- **Event / CDC replay:** reapplies missed mutations if logs are truly complete and replay-safe.
- **Restore another backup:** required when sources lack data or snapshots corrupted; cannot conjure records from absent bytes.
- **Business remediation:** requires audited workflows, never ad-hoc edits just to make one CQL test match.

Every fix must record **evidence source, affected keys/ranges, timestamps, and pre/post checks**.

## 20. Specific Risks for Counters, LWTs, Indexes, and CDC

### Counters

Cassandra counters have non-idempotent mutation semantics compared to ordinary integers; duplicate replays or improper restores skew totals. Never assume "replaying the same counter delta" is idempotent. Reconcile business balances/counters against source ledgers and follow version-supported migration/restore runbooks.

### LWT and Consensus State

If business orders rely on `IF` or `INSERT ... IF NOT EXISTS`, table data and consensus-related state carry specific recovery constraints. Never treat an SSTable restore as guaranteeing prior compare-and-set transactions are serialized onto a new cluster. Design cutover, prevent dual-writers, and restore invariants from the source of truth.

### Secondary Indexes, SAI, and Materialized Views

Separately test query paths relying on secondary indexes, Storage-Attached Indexes (SAI), or materialized views if used. A passing primary-key `SELECT` does not prove indexes/views are built and synced. Rebuild/backfill behavior varies by release—include explicit validation steps.

### CDC and Downstream Systems

Bulk SSTable restores/streaming do not automatically emit **CDC events** like ordinary CQL writes. If downstream services must receive missed events, run a **replay/backfill plan with event IDs and deduplication** to avoid duplicate side effects (e.g., double-charging).

An event existing inside an SSTable **does not mean** downstream consumers processed it. Downstream reconciliation is part of the end-to-end recovery contract.

## 21. Cutover Control and Dual-Write Prevention

A common mistake is letting both the source cluster and recovery cluster **accept writes simultaneously** before locking a single source of truth. Under Cassandra last-write-wins, timestamp reconciliation does not automatically resolve business conflicts.

Before shifting traffic:

1. Lock which system owns writes; prevent unintended split-brain or dual-writers.
2. Lock recovery checkpoints/watermarks.
3. Complete data imports and ordered/idempotent log replays.
4. Reconcile critical invariants and projections up to the watermark.
5. Run bounded read/write canaries with proper Java Driver local DC/CL.
6. Monitor p99, error rates, repair/streaming, and fresh post-cutover data.
7. Maintain a rollback plan evaluated **for writes occurring post-cutover**—not merely flipping DNS.

If new writes hit the recovery cluster after cutover, rolling back to the old cluster can **lose those new writes** without a sync/replay strategy. That too is an RPO issue to report transparently.

## 22. Phased Reconciliation Runbook

### Phase A — Lock Scope and Sources

1. Record incident timestamp, checkpoint, RPO/RTO targets, and service scope.
2. Gather schema/version/partitioner/RF/DC, snapshots, and log/CDC inventories.
3. Confirm sources cover all token ranges; record checksums and immutable backup locations.
4. Define expected live/deleted key contract with TTL/timestamp semantics.
5. Align on business invariants and severity levels that permit or block cutover.

### Phase B — Restore and Technical Checks

6. Restore schemas and data per version-specific runbooks; never alter primary keys arbitrarily.
7. Verify streaming/restore completion per node/range, not merely process exit codes.
8. Inspect node health, disk/compaction, RF/DC, and queryable data.
9. Log failed ranges, retries, and replicas lacking completion evidence.

### Phase C — Data and Business Reconciliation

10. Reconcile keys/partitions against independent manifests; verify all mandatory ranges.
11. Compare values, TTL/`WRITETIME` metadata, and deleted key sets.
12. Check projections against checkpoints/watermarks and convergence SLAs.
13. Run INV-01…INV-07 checks; classify critical vs. noncritical findings.
14. Remediate divergences via trusted sources and appropriate backfill/replay/repair, then re-verify.
15. Report evidenced RPO; if independent sources are lacking, state evidence limits openly.

### Phase D — Go/No-Go and Post-Checks

16. Canary Java/CQL using expected local DC/CL; measure p95/p99 and timeouts under realistic load.
17. Confirm zero blockers on financial data, erasures, security, and source coverage.
18. Make the go/no-go decision jointly with business and operations owners.
19. Ramp traffic in stages while tracking invariant violations and reconciliation backlogs.
20. Archive actual RTO report, evidence, residual gaps, follow-up actions, and rollback plan.

### Sample Go/No-Go Criteria

| Category | Go When | No-Go When |
| --- | --- | --- |
| Backup / source | Mandatory token ranges backed by trusted sources | Unexplained coverage gaps |
| Data correctness | Critical keys/values match manifest | Missing paid orders or resurrected critical deletes |
| Invariants | Zero unresolved critical violations | `PAID` lacks payment evidence per demo contract |
| Projections | Converged to watermark / within approved SLA | Mismatches exceed convergence window |
| RPO | Measured and within approved limit | RPO exceeded or unknown yet claimed passing |
| RTO / service | Canary meets SLOs and cutover path ready | p99/errors breach limits; compaction/disk uncontrolled |
| Recovery plan | Clear rollback and new-write management | Uncontrolled dual-writes across source and target |

No single universal threshold fits every industry; sign off thresholds according to business risk and legal mandates.

## 23. Post-Restore Diagnostic Scenarios

### A — Valid Snapshots Yet Pre-Checkpoint Orders Missing

**Symptom:** file hashes match, yet some `order_id`s in the independent manifest cannot be read.

**Check:** token-range coverage, whether source nodes were snapshotted, original write CL, unflushed mutations sitting in commit logs, and available replay depth.

**Action:** supplement missing sources or valid replays if available; never use global `COUNT(*)` to hide gaps in specific ranges.

### B — Listing Projection Missing While Canonical Table Is Complete

**Symptom:** `orders_by_id` holds the row; `orders_by_customer_day` lacks it.

**Check:** projection update flow, snapshot timing, consumer watermarks, and multi-table write failures.

**Action:** backfill the projection from the canonical table per checkpoint using idempotent logic and re-verify. Repairing projection replicas cannot invent mutations that were never written.

### C — Deleted Row Reappears

**Symptom:** an order marked "deleted" in the manifest returns an old value after restore.

**Check:** stale snapshot sources, tombstones, `gc_grace_seconds`, offline replicas, and deletion timestamp.

**Action:** pause cutover for the affected scope; determine truth from authoritative sources, then reapply deletion/remediation with an audit trail.

### D — TTL Records Flagged Missing After Long-Delayed Restore

**Symptom:** large volumes of short-lived records are absent; reconciliation flags "missing."

**Check:** did the expected set filter TTLs by verification time? Did restore preserve expiry metadata? Was the data actually meant for long-term storage?

**Action:** align measurement logic with TTL deadlines; never arbitrarily extend TTLs just to turn tests green.

### E — RPO Calculated from Snapshot Time Yet Actual Loss Is Worse

**Symptom:** snapshot taken at 13:50, yet events ACKed earlier are missing.

**Check:** snapshot captured only one replica, insufficient flushing, offline nodes, CL, log backups, and token coverage.

**Action:** recalculate evidenced checkpoints and add missing sources; never cite "latest snapshot timestamp" as exact RPO when coverage is incomplete.

### F — Restore Finished, Data Accurate, Yet APIs Time Out

**Symptom:** canary p99 spikes; `tpstats` pending tasks, disk await, and compaction backlogs run high.

**Check:** post-load SSTable count, background streaming/repair, GC/CPU, CL, and coordinator routing.

**Action:** throttle background work / scale storage and re-measure; never open full traffic merely because data checks passed.

### G — Two DCs Read the Same Key and Return Different States

**Symptom:** `LOCAL_QUORUM` in `dc1` reads `PAID`, while `dc2` reads `PENDING`.

**Check:** per-DC checkpoints, replication lag, streaming/repair coverage, and source-of-truth timestamps.

**Action:** verify true state from ledger, coordinate targeted repair/recovery—do not simply increase driver timeouts.

### H — SSTable Hashes Differ After Compaction

**Symptom:** target file hashes differ from source hashes even though sample key `SELECT`s match.

**Explanation:** compaction, SSTable packaging, compression, and metadata can differ. Never infer data loss from differing file hashes in a pipeline rebuilding physical SSTables.

**Action:** use logical row/cell comparisons and token coverage, keeping file hashes solely to verify source staging copies.

## 24. Misconceptions to Avoid

**"`nodetool status` showing `UN` means restore is complete."** False. Membership/gossip does not prove data accuracy or completeness.

**"`sstableloader` exiting cleanly means the whole system is restored."** False. It loads only the files provided; sources may still miss token ranges or mutations.

**"One node's snapshot is an atomic cluster-wide snapshot."** False. A node holds only its replica ranges and its own capture timestamp.

**"RPO equals the gap between incident time and backup file timestamp."** Insufficient. You must prove ACKed mutations were captured and sources cover up to that cutoff.

**"RTO ends when streaming hits 100%."** False. The service must meet all defined data and SLO criteria.

**"TTL data not appearing means restore failed."** Not necessarily. It may have expired per policy.

**"Newest import file timestamp beats all target values."** False. Cassandra reconciles by mutation/tombstone timestamps, not file copy time.

**"Repair fixes every mismatch across denormalized tables."** False. Repair reconciles replicas of the same dataset; it never populates business projections that missed writes.

**"Two `LOCAL_QUORUM` reads in two DCs always match immediately."** There is no mandatory quorum overlap between two local DCs.

**"Matching total row counts proves data is accurate."** False. You can miss key A and hold extra key B, or have wrong values/timestamps/deletes.

**"Source and target SSTable hashes must match."** False whenever SSTable rebuilding/compaction alters physical layout.

**"Matching hashes on a few sample partitions prove 100% recovery."** False. Samples prove only tested partitions; separate coverage verification is needed.

**"`PAID` without a payment event can be fixed by fabricating an event."** False. Verify ledgers and follow audited business remediation workflows.

**"Rollback is just flipping DNS back to the old cluster."** False. Writes hitting after cutover can be lost without replay/sync strategies.

## 25. Exercises and Interview Questions

1. Why does a file/SSTable-level restore succeed yet fail to prove business invariants hold?
2. Distinguish `T_snapshot`, `T_restore_target`, and business event time.
3. Does a snapshot on one RF=3 node cover the whole keyspace? What must be checked?
4. In the example, snapshot is at 13:45, log replay reaches 13:58, and incident hits at 14:00. Can you claim RPO=2 minutes if one token range lacked backups? Why?
5. Why keep an independent manifest/ledger instead of generating expected keys from the restored table itself?
6. Explain why equal total row counts do not prove keys and values are accurate.
7. Data with a 7-day TTL is restored after 10 days. Should it be counted as missing? What does that depend on?
8. Why can a row `DELETE`d prior to checkpoint resurrect when mixing stale replicas?
9. How do `gc_grace_seconds` and repair protect tombstones? When is a late repair insufficient?
10. `orders_by_id` is right while the customer projection table is missing rows. Does repair rebuild it? What is the fix?
11. In the demo model, how do you verify via CQL that `PAID` has a `CAPTURED` payment?
12. When a system supports refunds or partial captures, how must the "captured amount = order total" invariant change?
13. Why is `BigDecimal.compareTo` helpful when comparing monetary values from two sources?
14. When computing logical hashes, how should you canonicalize timestamps, nulls, collections, and row order?
15. Do `LOCAL_QUORUM` in `dc1` and `LOCAL_QUORUM` in `dc2` have mandatory replica overlap?
16. How do you set projection convergence targets without reporting normal eventual lag as a restore failure?
17. A canary reads accurate data yet read p99 breaches SLOs. Should you open full traffic?
18. Why is full-table `COUNT(*)` both expensive and no substitute for manifest coverage?
19. What extra post-restore checks are needed for counters, LWTs, SAI/materialized views, and CDC?
20. If only 10,000 sample partitions out of 10 million were verified, how must the completeness report state it?
21. Distinguish *target RPO*, *evidenced RPO*, and *actual RTO*.
22. If both source and target clusters accept writes after cutover, what consistency risks arise?
23. If deleted orders reappear, why shouldn't you immediately run `DELETE` across millions of keys before investigating?
24. Design a post-restore metrics table covering coverage, missing, unexpected, projection mismatch, invariant violations, p99, and RPO/RTO.
25. Propose three non-negotiable **no-go** conditions for a hypothetical payment system.

## 26. End-of-Lesson Decision Flowchart

```text
        FILE RESTORE / STREAMING / REBUILD REPORTS DONE
                           |
                           v
       Do sources/manifests cover all token ranges?
                    |               |
                   No              Yes
                    |               |
           Recover missing       v
           or report gap    Are checkpoint and RPO evidenced?
                                    |             |
                                   No            Yes
                                    |             |
                             State limits         v
                             and investigate  Reconcile keys/values/
                                              TTLs/deletes/timestamps
                                                  |
                                         +--------+---------+
                                         |                  |
                                       Wrong              Right
                                         |                  |
                                  Controlled fix            v
                                         |          Check projections +
                                         |          invariants at cutoff
                                         |                  |
                                         +-------+----------+
                                                 |
                                             Passing?
                                          +------+------+
                                          |             |
                                         No            Yes
                                          |             |
                                  No-go / repair     Java Canary
                                  / backfill         CL, DC, p99
                                                        |
                                                  SLO met?
                                                    |        |
                                                   No       Yes
                                                    |        |
                                                  No-go      v
                                                     Go/no-go review,
                                                     staged cutover,
                                                     post-restore monitoring
```

**Remember:** **Restoring is bringing bytes back; recovery finishes only when data is accurate, complete, contract-consistent, and able to serve the business.** Cassandra supports multiple replicas, SSTables, and query-driven tables, requiring reconciliation across **token ranges, partition keys, timestamps, TTLs, tombstones, projections, and invariants**. Measure **evidenced RPO, RTO until service resumes, critical data errors, and post-restore p95/p99 latency**. Success is never a single "stream completed" line, but a traffic cutover decision grounded in complete, auditable evidence.
