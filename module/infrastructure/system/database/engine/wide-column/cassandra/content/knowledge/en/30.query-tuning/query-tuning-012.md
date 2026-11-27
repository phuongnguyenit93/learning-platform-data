# Aligning Read/Write Consistency with Business Requirements in Apache Cassandra

## 1. Why Must Consistency Be Chosen from Business Requirements?

Apache Cassandra is a distributed **wide-column** database: a partition's data is replicated across multiple nodes, and tables are typically designed around the queries they serve. When an application writes an order status and reads it back, the question is not only whether the query is fast, but **whether the read must observe the just-acknowledged write**, and what happens when a node or an entire datacenter fails.

Cassandra lets you choose a **consistency level (CL) per read or write operation**. CL determines how many replicas must respond before the coordinator considers the operation successful. CL does not change the configured replica count, nor does it create multi-partition ACID transactions. Picking CL is a deliberate trade-off among **data freshness, availability, and latency**.

Consider an e-commerce system with these flows:

- **Product catalog:** a few seconds of update propagation lag is normally acceptable; prioritize fast reads.
- **Order status:** once the API confirms transitioning to `SHIPPED`, status lookups in the same region must see the newly written change.
- **Inventory reservation:** two concurrent requests must not claim the same unit of stock.
- **Payments and ledgers:** require strict transactional invariants across multiple entities; tweaking Cassandra CL alone cannot satisfy this requirement.

This lesson translates business statements like those into testable **RF, write CL, read CL, serial CL (if using LWT), datacenter scope, and failure-handling policies**.

## 2. Distinguishing Replication Factor, Consistency Level, and Datacenter Scope

Suppose a partition has **replication factor** `RF = 3` in datacenter `dc1`. Three replicas hold copies of that partition. On writes, the coordinator sends mutations to the owning replicas; on reads, the coordinator contacts enough replicas per CL, reconciles versions when needed, and returns the winning state per Cassandra's conflict resolution.

| Term | Practical meaning | Do not confuse with |
| --- | --- | --- |
| `RF` | Number of copies of a partition per keyspace config, usually per DC under `NetworkTopologyStrategy` | Not the number of replicas required to ack every query |
| Write CL (`W`) | Number of replicas required to acknowledge a write before reporting success | Write success does not mean all replicas already have the update |
| Read CL (`R`) | Number of replicas required to satisfy a read per CL | Not a SQL-style global lock across data |
| `LOCAL_*` | Considers replicas inside the coordinator's local datacenter | Does not guarantee remote DCs have seen the write |
| Regular consistency | Quorum/ONE/ALL… for standard reads and writes | Does not serialize concurrent competing updates |
| Serial consistency | `SERIAL`/`LOCAL_SERIAL` for the Paxos phase of lightweight transactions (LWT) | Does not replace the regular CL of the LWT itself |

Commonly used CLs:

| CL | Acknowledgment condition | When appropriate / caveats |
| --- | --- | --- |
| `ANY` | **Write-only**: may be acknowledged via a hint even if zero replicas have stored the mutation yet | Prioritizes write ingestion during outages; risk of unreadability and data loss if hints never deliver; avoid for critical data |
| `ONE`, `TWO`, `THREE` | 1, 2, or 3 replicas respond respectively | Simple within one DC; verify RF is large enough |
| `LOCAL_ONE` | One replica in the local DC | Low read/write latency; returned data may be stale |
| `QUORUM` | Strict majority of **total replicas** of the partition across all DCs | With RF 3+3, requires 4 responses; typically incurs cross-DC WAN traffic |
| `LOCAL_QUORUM` | Strict majority of replicas **within the local DC** | Common choice for multi-DC apps needing regional consistency |
| `EACH_QUORUM` | **Write-only**: strict majority in **every DC** | Requires all DCs to be reachable in exchange for per-region write durability |
| `ALL` | Every replica must respond | Availability drops if one replica fails/slows; does not turn standard writes into linearizable transactions |
| `SERIAL`, `LOCAL_SERIAL` | Consistency level for the Paxos serialization phase of LWTs; `LOCAL_SERIAL` scopes to local DC | Paired with regular CL on `IF ...` / `IF NOT EXISTS` to arbitrate concurrent contention |

**Quorum math:** for `RF = N` within the target scope, quorum is `floor(N / 2) + 1`. For example, `RF(dc1) = 3` gives `LOCAL_QUORUM = 2`; if `RF(dc1) = 3` and `RF(dc2) = 3`, global `QUORUM = 4`, while `LOCAL_QUORUM` in each DC remains 2.

### Read/Write Overlap Rule

Within **one shared replica scope**, when `R + W > RF`, the read replica set and acknowledged write replica set are guaranteed to overlap in at least one replica. With `RF = 3`:

| Write CL | Read CL | `W + R > 3`? | Notes |
| --- | --- | --- | --- |
| `ONE` (1) | `ONE` (1) | No | Reads may hit a replica that has not received the latest write |
| `TWO` (2) | `TWO` (2) | Yes | Overlaps; tolerates one unavailable replica per individual operation |
| `QUORUM` (2) | `QUORUM` (2) | Yes | Equivalent to 2+2 within a single DC of RF 3 |
| `ALL` (3) | `ONE` (1) | Yes | Cheap reads, yet one failed replica breaks writes |
| `ONE` (1) | `ALL` (3) | Yes | Resilient writes, yet reads are fragile to any replica failure |

This rule helps pick a configuration that **reads acknowledged writes under normal conditions** within the same replica set, absent concurrent conflicting writes or abnormal clock skew. It is **not** an unconditional linearizability guarantee across arbitrary concurrent histories: Cassandra resolves cells by timestamp (last-write-wins), while conflicts, tombstones, retries, and clock skew still require sound design and operations. Across **multiple DCs**, you cannot blindly add `W` in one DC to `R` in another: `LOCAL_QUORUM` in `dc1` and `LOCAL_QUORUM` in `dc2` do not guarantee overlapping replica sets.

## 3. Start from the Data Contract, Then Pick CL

Before setting `CONSISTENCY LOCAL_QUORUM`, state four things clearly:

1. **Required freshness:** can reads tolerate 1–5 seconds of lag, or must they reflect acknowledged writes immediately in the same region?
2. **Scope:** do clients stay pinned to one DC or fail over freely across regions? Do multiple regions write the same key concurrently?
3. **Failure behavior:** prefer failing with an error to avoid stale reads, or allow stale reads / queued writes to stay available? Can users see a `PENDING` state?
4. **Concurrency constraints:** do you only need the latest value, or conditional logic like "update only if current version equals 7," or multi-key transactions?

From that, build a decision table—for example with `RF = 3` per DC and regional client affinity:

| Business flow | Stale-read tolerance | Suggested write / read CL | Additional controls |
| --- | --- | --- | --- |
| Catalog display, non-critical filters | Short lag acceptable | `LOCAL_ONE` / `LOCAL_ONE` | Cache TTL, async updates, monitor sync lag |
| Just-edited user profile | Must not read stale in same region | `LOCAL_QUORUM` / `LOCAL_QUORUM` | Pin clients to DC, controlled retries, handle concurrent writes |
| Order status lookup | Prioritize seeing acknowledged state | `LOCAL_QUORUM` / `LOCAL_QUORUM` | Read/write by `order_id`, align state-transition rules |
| Retryable event ingestion | Replication lag tolerable | `LOCAL_ONE` / `LOCAL_ONE` per data-loss budget | Idempotent event IDs, durable retry/buffer, monitor replica lag |
| Stock reservation on one SKU | Conflicting overwrites unacceptable | Appropriate regular CL + `LOCAL_SERIAL` for LWT in one write region | `IF` on version, single-region ownership per key; check `[applied]` result |
| Ledgers, multi-account transfers | Partial writes or balance drift unacceptable | **No regular CL pair suffices** | Use an ACID transactional store/architecture, then project read views to Cassandra if needed |

This is a **starting point for benchmarking and failure testing**, not a safe universal default. `LOCAL_ONE` may deliver great latency while failing RPO durability expectations. `LOCAL_QUORUM` adds coordination wait and can time out when replicas drop; verify p99 on real topology and load.

## 4. Example: Configuring Consistency for Order Status

Suppose a service spans two datacenters `dc1` and `dc2`, each with three replicas for the keyspace. DC names must match the cluster's actual names. The app reads and writes order status primarily in `dc1`, keyed by `order_id`.

```sql
CREATE KEYSPACE commerce
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};

CREATE TABLE commerce.order_status_by_id (
  order_id uuid PRIMARY KEY,
  status text,
  version int,
  updated_at timestamp
);
```

The table is designed around **partition key `order_id`**. CL never fixes missing partition keys, heavy `ALLOW FILTERING`, oversized partitions, or hot partitions; consistency tuning must go hand in hand with query-driven table design.

In `cqlsh`, test regular CL for a session:

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO commerce.order_status_by_id
  (order_id, status, version, updated_at)
VALUES
  (11111111-1111-1111-1111-111111111111, 'CREATED', 1, toTimestamp(now()));

SELECT status, version, updated_at
FROM commerce.order_status_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

When both writes and reads use `LOCAL_QUORUM` in `dc1`, each operation needs at least two `dc1` replicas to respond. After an acknowledged write, reads in the same DC intersect. However, if traffic fails over to `dc2` before replication arrives, a `LOCAL_QUORUM` read in `dc2` **can still return stale data**. Failover design must specify whether replication lag is acceptable, whether writes pause, how reconciliation runs, or how regional key ownership works.

### Handling Two Concurrent Competing Updates: LWT

Suppose two workers both attempt to advance version 1 to 2. Two standard `UPDATE`s at `LOCAL_QUORUM` do not enforce "only one worker wins." Within one partition, use a **lightweight transaction (LWT)**:

```sql
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY LOCAL_SERIAL;

UPDATE commerce.order_status_by_id
SET status = 'PAID', version = 2, updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-1111-1111-111111111111
IF version = 1;
```

The response returns column `[applied]`: `true` means the conditional update succeeded, `false` means the condition no longer held; a `false` branch **must never** be treated as an applied update. LWT uses Paxos, adding network rounds and latency, so reserve it for genuine contention. With `LOCAL_SERIAL`, designate **one DC to own competing updates for a key**; if invariants must hold across multiple DCs simultaneously, evaluate global `SERIAL`, cross-region write routing, and its latency/availability cost. Single-partition LWT does not create atomic multi-partition transactions.

### Applying Per-Statement CL from Java

This example uses Java Driver 4.x (`com.datastax.oss.driver.api`). `CqlSession` is initialized with the appropriate local datacenter and contact points and should be reused rather than opened per request.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class OrderStatusRepository {
    private final CqlSession session;

    public OrderStatusRepository(CqlSession session) {
        this.session = session;
    }

    public boolean moveFromCreatedToPaid(UUID orderId) {
        SimpleStatement conditionalUpdate = SimpleStatement.builder(
                "UPDATE commerce.order_status_by_id " +
                "SET status = ?, version = ? WHERE order_id = ? IF version = ?")
            .addPositionalValues("PAID", 2, orderId, 1)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
            .build();

        ResultSet result = session.execute(conditionalUpdate);
        return result.wasApplied();
    }

    public String findStatus(UUID orderId) {
        SimpleStatement lookup = SimpleStatement.builder(
                "SELECT status FROM commerce.order_status_by_id WHERE order_id = ?")
            .addPositionalValue(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        var row = session.execute(lookup).one();
        return row == null ? null : row.getString("status");
    }
}
```

The method returns `false` when the CAS condition was not met; the business layer should re-read current state and decide whether to report conflict or recompute. If a request **times out**, you cannot assume the mutation did not happen; inspect current status by ID/version or run reconciliation before retrying non-idempotent operations. Under high load, prefer prepared statements, intentional timeout/retry policies, and per-statement metrics.

## 5. Failure Analysis Before Locking In a Policy

| Scenario | Impact with RF 3, `LOCAL_QUORUM` read/write in one DC | Application action |
| --- | --- | --- |
| One local replica is down or slow | Remaining two replicas can still meet quorum; latency may rise | Monitor latency, timeouts, and recovery |
| Two replicas in the same DC are unavailable | Local quorum cannot be met; reads/writes at this CL fail | Return controlled errors; never silently drop CL if stale data is unacceptable |
| Write succeeded on replicas, yet client lost connection before ACK | Client cannot tell whether the write applied | Use request IDs, idempotent writes, read-backs, or reconciliation |
| `dc1` acknowledged write; client immediately switches to `dc2` | `LOCAL_QUORUM` in `dc2` may still read stale data | Enforce regional pinning or explicit failover + sync workflow |
| Multiple writers update the same cell concurrently | Winner depends on timestamp and conflict resolution | Use versioning/CAS or restrict writers per partition |
| Replica missed mutations and later rejoins | Temporary divergence; hints/read repair help only partially | Maintain scheduled repair and monitor progress; never treat compaction as repair |

**Never automatically downgrade CL just to turn errors into successes.** For example, falling back from a timed-out `LOCAL_QUORUM` write to `LOCAL_ONE` makes the API report success while violating the read-your-writes guarantee. If the product explicitly supports a degraded mode, define the altered contract clearly (e.g., "request accepted, processing"), along with reconciliation and recovery.

### Roles of Hints, Repair, Read Repair, and Compaction

- **Hinted handoff** replays mutations missed by temporarily unavailable replicas within a bounded window. Hints do not replace durable replica storage and cannot guarantee convergence across extended outages.
- **Read repair** heals divergence spotted on actively read partitions per Cassandra version and config. Do not rely on read traffic alone to heal all partitions.
- **Anti-entropy repair** (e.g., running `nodetool repair` per cluster schedule) synchronizes missed data across replicas—essential wherever deletes/tombstones and `gc_grace_seconds` apply.
- **Compaction** merges SSTables, reorganizes storage, and purges eligible tombstones safely; it **never** replaces replica synchronization. Choose compaction strategy by read/write/TTL profile, not as a consistency knob.

These mechanisms govern durability and convergence over time, yet cannot rescue a mischosen CL or uncoordinated concurrent writes.

## 6. Testing and Measurement Methodology

To validate your choices, build an environment matching production RF and topology, using realistic partition keys, record sizes, and read/write ratios. Track results separately per DC and per CL.

1. **Read-after-write test:** write in `dc1`, wait for ACK, then read immediately in both `dc1` and `dc2`; repeat under load to measure latency and stale-read rates across CL pairs.
2. **Replica-loss test:** take down one and then two replicas in the same DC in a test cluster; measure success rates and p95/p99 read/write latency at `LOCAL_ONE` vs. `LOCAL_QUORUM`.
3. **Write-timeout test:** inject failures after partial replica writes; verify the app does not assume "not written," avoids duplicate events, and reconciles cleanly.
4. **Concurrent-write test:** have two workers update the same `order_id`; compare blind updates vs. `IF version = ?`, confirming only one LWT returns `[applied] = true` for the same expected version.
5. **Cross-region failover test:** sever inter-DC links, write in the allowed DC, and simulate reads/failover in the peer DC; verify alignment with stated RPO, consistency rules, and recovery runbooks.
6. **Post-test observability:** measure timeouts, unavailables, read/write latency, speculative/retry traffic, tombstones/partition sizes, replica status, repair lag, and actual data divergence.

There is no fixed "staleness in seconds" guaranteed by `LOCAL_ONE`, nor is availability guaranteed by quorum math alone. Real outcomes depend on replica placement, network RTT, load, Cassandra version, query design, and driver error handling.

## 7. Quick Decision Matrix

Before shipping a business flow to production, answer these questions:

| Question | If the answer is… | Direction |
| --- | --- | --- |
| Tolerate brief stale reads? | Yes | Evaluate `LOCAL_ONE` plus caching/reconciliation |
| Must see acknowledged writes in the same DC? | Yes | Pick a CL pair with `R + W > RF` in the same scope, typically `LOCAL_QUORUM`/`LOCAL_QUORUM` at RF 3 |
| Can clients switch DCs right after writing? | Yes | Do not rely solely on two `LOCAL_QUORUM`s; define write ownership, failover rules, or cross-DC quorum if feasible |
| Many requests contend on the same key? | Yes | Use conditional writes and single-partition LWT if latency allows; scope `SERIAL`/`LOCAL_SERIAL` |
| Must update multiple partitions atomically? | Yes | Redesign transaction boundaries or choose a storage system supporting required transactions |
| Not enough replicas to satisfy committed CL? | Yes | Return errors/alerts and follow a business-approved degraded flow instead of silently lowering CL |

**Applied exercise:** With `RF(dc1) = RF(dc2) = 3`, an API updates a shipping address in `dc1` at `LOCAL_QUORUM`, while the mobile app may immediately read in `dc2` at `LOCAL_QUORUM`. Explain why stale addresses can still appear, propose two mitigation policies (e.g., regional pinning vs. failover with reconciliation), and outline a test simulating an inter-DC link break to verify the user contract. If addresses must be globally consistent immediately after every update, assess the cost of cross-DC quorum and writer coordination too.

**Takeaway:** Consistency is part of your **API contract**. Define how much staleness and failure the business tolerates, choose RF/CL within the right scope, reserve LWT for real contention, test failovers, and keep repair running. Never use consistency levels to compensate for flawed partition keys, unsafe retries, or mismatched transactional expectations.
