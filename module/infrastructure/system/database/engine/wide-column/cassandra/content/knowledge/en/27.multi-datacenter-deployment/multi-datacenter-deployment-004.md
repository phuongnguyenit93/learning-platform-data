# QUORUM and EACH_QUORUM for Supported Operations in Apache Cassandra

## 1. Context: Same Word "Quorum," Different Confirmation Scopes

In Apache Cassandra, every **wide-column** table is designed around the queries the application must serve. The **partition key** determines the data's token; the **replication strategy** determines which replicas store the data in each datacenter (DC); and the **consistency level** (CL) determines the acknowledgment requirement for each read or write request.

When a cluster has only one datacenter, many examples introduce quorum simply as "a majority of replicas." When spreading data across **multiple datacenters**, the critical question becomes: **a majority across all replicas or a majority within each datacenter?**

- **`QUORUM`:** requires a quorum calculated over the **total replication factor across the DCs configured for the keyspace**. ACKs can come from DCs in any proportion, as long as the total meets the threshold.
- **`EACH_QUORUM`:** for **supported writes**, requires a quorum **in each datacenter** configured for replication. If one DC falls short of ACKs, this level fails even if the total ACK count exceeds `QUORUM`.
- **`LOCAL_QUORUM`:** requires a quorum in the coordinator/request's **local datacenter**; this is typically chosen when you want to avoid depending on WAN latency or outages on the request path.

This lesson belongs to the **Multi-Datacenter Deployment** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The goal is to know **which operations accept `QUORUM` or `EACH_QUORUM`**, compute exact ACK counts, understand the impact on availability/latency, and pick appropriate consistency levels in CQL and Java applications.

> Keep in mind from the start: **`EACH_QUORUM` is not a "stronger quorum" you can attach to every CQL statement**. In Apache Cassandra, this level is designed for **writes**, not as a valid consistency level for normal `SELECT` queries.

## 2. Foundation: Per-Datacenter Replication

### 2.1. NetworkTopologyStrategy

For multi-DC deployments, keyspaces typically use `NetworkTopologyStrategy` to declare replica counts **independently per datacenter**, instead of a single global RF:

~~~cql
CREATE KEYSPACE shop_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hanoi': 3,
    'dc_singapore': 3
}
AND durable_writes = true;
~~~

This example assumes the topology already has two DCs named exactly `dc_hanoi` and `dc_singapore`, each with at least three eligible nodes. Total RF for **a single partition** in the keyspace is **3 + 3 = 6** copies, before accounting for individual node states.

**Do not confuse RF with total cluster node count:** even if each DC has ten nodes, a partition in this example is still replicated **three times per DC**, not across every node.

Cassandra selects replicas based on the token/partition key, replication strategy, and topology (DC/rack). Snitch configuration, racks, node counts, and token distribution must align. If RF exceeds the number of nodes capable of holding replicas in a DC, the examples below will no longer reflect a healthy deployment.

### 2.2. Quorum Formulas

For a partition with total replication factor `RF_total`:

~~~text
Cluster-wide QUORUM = floor(RF_total / 2) + 1

LOCAL_QUORUM in DC i = floor(RF_i / 2) + 1

EACH_QUORUM for writes = must have at least LOCAL_QUORUM
                         in EACH DC with a declared RF_i
~~~

`floor` rounds down to the nearest integer. These formulas describe the **number of replicas required to acknowledge** in an example with valid placement; they do not account for timeouts, network failures, or overloaded nodes. Nor do they mean all remaining replicas have definitely persisted the data by the time the client gets a response.

With RF = 3 in each DC:

- `RF_total = 6`, so `QUORUM = floor(6/2)+1 = 4`.
- `LOCAL_QUORUM` in each DC requires **2/3** ACKs.
- `EACH_QUORUM` for writes requires **2 ACKs in Hanoi and 2 ACKs in Singapore**; at least 4 total, but distributed specifically per DC.

## 3. Comparing Three Key Consistency Levels

| Consistency Level | Confirmation Scope | Regular SELECT | Regular INSERT / UPDATE / DELETE | Inter-DC Link Dependency |
|---|---|---|---|---|
| `LOCAL_QUORUM` | Majority of replicas in local DC | Supported | Supported | Can avoid depending on other DCs on the critical path |
| `QUORUM` | Majority of replicas over total RF across DCs | Supported | Supported | May wait on replicas in other DCs, depending on RF/placement and ACKs |
| `EACH_QUORUM` | Majority of replicas **in each DC** | **Not supported for SELECT** | Supported for eligible writes | Must get enough ACKs from **every** required DC |

**The cells above cover regular reads/writes.** Conditional operations (LWT), counters, batches, or special features have additional rules depending on version/protocol. Do not infer from this table alone that a CL is allowed on every statement variant.

### 3.1. `QUORUM` Can Be Satisfied by `3 + 1`

With Hanoi DC (RF=3) and Singapore DC (RF=3), at least four ACKs are needed.

If **3 ACKs come from Hanoi and 1 ACK from Singapore**, a `QUORUM` request reaches the threshold of 4. However, it **does not satisfy `EACH_QUORUM`**, because Singapore only has 1/3 ACKs, below its local quorum of 2.

If **2 ACKs come from each DC**, both `QUORUM` and `EACH_QUORUM` can be satisfied.

### 3.2. `LOCAL_QUORUM` Does Not Guarantee the Other DC Has Received It

If an application sends a write through a coordinator in `dc_hanoi` at `LOCAL_QUORUM`, acknowledgments from two Hanoi replicas satisfy the CL. Singapore replicas may receive the mutation afterward via normal write/recovery paths, but **request success does not mean Singapore acknowledged quorum**.

This helps availability and local latency, provided the business tolerates a **temporary divergence window between DCs**. If strict confirmation across every DC is required at write time, evaluate `EACH_QUORUM` for writes and its trade-offs.

## 4. Outcome Table: What Per-DC ACK Counts Decide

Assume `RF_HN = 3`, `RF_SG = 3`. In the table below, each `HN + SG` entry shows how many replicas **actually ACKed the request** in the two DCs. For `LOCAL_QUORUM`, assume the local coordinator is in **Hanoi**.

| HN + SG ACKs | Total ACKs | `QUORUM` (needs 4) | `EACH_QUORUM` Write (needs 2+2) | `LOCAL_QUORUM` HN (needs 2) |
|---|---:|---|---|---|
| 3 + 1 | 4 | Met | **Not met** | Met |
| 2 + 2 | 4 | Met | Met | Met |
| 1 + 3 | 4 | Met | **Not met** | **Not met** |
| 3 + 0 | 3 | Not met | Not met | Met |
| 2 + 1 | 3 | Not met | Not met | Met |
| 1 + 2 | 3 | Not met | Not met | Not met |
| 0 + 3 | 3 | Not met | Not met | Not met |
| 3 + 3 | 6 | Met | Met | Met |

This is a **mathematical model of ACK counts**, not a guarantee that every combination above occurs in practice in the same order. Real requests also involve replica selection, timeouts, network behavior, failures, and overload. Never equate "enough nodes are UP" with "guaranteed enough ACKs in time."

### Diagram Comparing Two Ways to Reach Four Total ACKs

~~~mermaid
flowchart TD
    A["Write to keyspace RF=3 + RF=3"] --> B{"Which ACKs arrived?"}
    B --> C["Hanoi: 3, Singapore: 1"]
    B --> D["Hanoi: 2, Singapore: 2"]
    C --> E["QUORUM: MET because total = 4"]
    C --> F["EACH_QUORUM: NOT MET because SG lacks quorum"]
    D --> G["QUORUM: MET because total = 4"]
    D --> H["EACH_QUORUM: MET because each DC has 2 ACKs"]
~~~

Thus **`EACH_QUORUM` is stricter than `QUORUM` in requiring per-DC ACK distribution on multi-DC writes**, rather than simply increasing the minimum total ACK count in every configuration.

## 5. Uneven RF Case: Must Calculate Per DC

Suppose two datacenters have asymmetric replication:

~~~cql
ALTER KEYSPACE shop_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hanoi': 3,
    'dc_singapore': 2
};
~~~

This statement is **syntax illustration only**, not a recommendation to edit RF directly in production. Altering RF on a live keyspace changes data topology and requires proper repair/streaming workflows, replica placement verification, and monitoring.

With `RF_total = 3 + 2 = 5`:

- `QUORUM = floor(5/2)+1 = 3` ACKs **overall**.
- `LOCAL_QUORUM` Hanoi = `floor(3/2)+1 = 2`.
- `LOCAL_QUORUM` Singapore = `floor(2/2)+1 = 2`.
- `EACH_QUORUM` write = **at least 2 ACKs in Hanoi and 2 ACKs in Singapore**, totaling at least 4 ACKs.

Example ACKs **3 + 0**:

- `QUORUM` reaches 3.
- `EACH_QUORUM` fails because Singapore has 0 ACKs.

Example ACKs **1 + 2**:

- `QUORUM` reaches 3.
- `EACH_QUORUM` fails because Hanoi has fewer than 2.

Example ACKs **2 + 2**: both succeed.

Conclusion: **per-DC quorums cannot be computed by a single division of `RF_total`**. Every time RF changes or a replicated DC is added, recalculate the ACK matrix.

## 6. Operation Support: Essential Distinctions

### 6.1. Regular Writes: Where `EACH_QUORUM` Makes Sense

Regular mutation operations can require per-DC ACK distribution:

~~~cql
CREATE TABLE shop_global.order_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp
);

-- Run in cqlsh with a supporting topology as shown in the example.
CONSISTENCY EACH_QUORUM;

INSERT INTO shop_global.order_by_id
    (order_id, status, updated_at)
VALUES
    (11111111-1111-1111-1111-111111111111,
     'CONFIRMED',
     '2026-11-21T10:00:00Z');

UPDATE shop_global.order_by_id
SET status = 'SHIPPED',
    updated_at = '2026-11-21T10:05:00Z'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

DELETE FROM shop_global.order_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

In this example, each write requires a quorum in **every DC**. When one DC loses the ability to respond from enough replicas, writes can fail with unavailable/timeout errors. **Do not treat `EACH_QUORUM` as a transaction mechanism**: it does not enforce business preconditions or prevent two writers from updating the same cell.

### 6.2. Reads: Use `QUORUM` or `LOCAL_QUORUM`, Not `EACH_QUORUM`

To read:

~~~cql
CONSISTENCY QUORUM;

SELECT order_id, status, updated_at
FROM shop_global.order_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

`QUORUM` is a supported read level; participating replicas may span multiple DCs depending on placement and how quorum is reached.

**Never build an application that depends on `SELECT` with CL `EACH_QUORUM`.** This level is **not supported for regular reads**; even if a client tool lets you pick the consistency name, the server can reject the corresponding `SELECT` request.

If the goal is "read data that was confirmed in every DC," you must **pair write/read CLs appropriately** instead of trying to use `EACH_QUORUM` for `SELECT`.

### 6.3. Operation Scope and Caution Table

| Request Type | `QUORUM` | `EACH_QUORUM` | Key Note |
|---|---|---|---|
| Regular `SELECT` row/partition read | Supported | **Not supported** | There is no "read `EACH_QUORUM`" |
| Regular `INSERT` | Supported | Supported for writes | Confirms ACK distribution, does not enforce uniqueness |
| `UPDATE` without `IF` | Supported | Supported for writes | Timestamp/last-write-wins still applies |
| `DELETE` without `IF` | Supported | Supported for writes | Tombstones and repair still must be managed |
| `INSERT/UPDATE ... IF ...` (LWT) | Has dedicated write/commit CL rules | **Do not generalize** from regular writes | Requires `SERIAL`/`LOCAL_SERIAL` and version verification |
| Batches/counters/special operations | Check dedicated conditions | Check version rules | Do not treat ACK guarantees as ACID or CAS |

Do not turn a summary table into a blanket claim that every CQL feature supports both levels. Always check the semantics of the **actual request type** and your Cassandra version when working with counters, logged batches, LWTs, or features with distinct execution paths.

## 7. Comparing Availability During a Datacenter Outage

### 7.1. Two Datacenters at RF=3+3

If **Singapore goes down completely**, Hanoi still has at most 3 ACKs for a partition:

- `LOCAL_QUORUM` in Hanoi needs **2/3**, so it can keep serving local reads/writes while other conditions remain healthy.
- Cluster-wide `QUORUM` needs **4/6**, so it **cannot be met** with only 3 replicas in Hanoi.
- `EACH_QUORUM` write needs **2/3 in both DCs**, so it **cannot be met** either.

Therefore, in a 3+3 model, **neither `QUORUM` nor `EACH_QUORUM` survives losing an entire DC** for write requests; the difference between them still matters when **only a subset of replicas in a DC reject or delay ACKs**.

### 7.2. Three Datacenters at RF=3+3+3

If a keyspace has RF=3 in three DCs, `RF_total = 9` and `QUORUM = 5`. When one DC fails completely while the other two stay healthy, up to 6 ACKs remain available, so **`QUORUM` can still be met**.

Conversely, `EACH_QUORUM` requires quorum **in all three DCs**. If one DC stops acknowledging completely, **`EACH_QUORUM` cannot be met**.

Important conclusion: whether `QUORUM` survives a full DC outage depends on **the number of DCs and RF distribution**; you cannot state unconditionally that `QUORUM` always survives or always fails when a datacenter is lost.

### 7.3. Latency and WAN Trade-offs

- `EACH_QUORUM` forces the write path to wait for enough replicas in every DC, so **WAN latency, inter-DC links, and the slowest DC's health** can dominate request latency.
- `QUORUM` may also require cross-DC responses, though it does not mandate a separate quorum in every DC.
- `LOCAL_QUORUM` typically isolates requests from remote DC issues at the ACK level, but does not guarantee cross-DC data synchronization at return time.

Never claim `QUORUM` **always** waits on the WAN in every configuration: if a single DC has enough replicas to satisfy the global quorum, it can complete with ACKs from that DC alone. Calculate RF, placement, and request behavior before assuming latency.

## 8. Read/Write Consistency: Quorum Intersection Conditions

### 8.1. Replica-Set Intersection Rule

A common mental model is:

~~~text
If W + R > RF for the same replica scope,
then the write-acknowledged replica set and the read replica set
must intersect on at least one replica
(when topology and replica sets are stable).
~~~

Here `W` and `R` are the number of confirming replicas within **the same eligible replica set**. Intersection reasoning helps analyze whether reads see new mutations, but **does not turn Cassandra into a serializable transaction system**. Timestamps, concurrent writes, clock skew, timeouts, node health, and LWT behavior still affect outcomes.

For example, with total RF=6, a `QUORUM` write and `QUORUM` read each require 4; since `4 + 4 > 6`, the quorum sets must intersect.

### 8.2. Why a `QUORUM` Write Does Not Guarantee an Immediate `LOCAL_QUORUM` Read Sees It in Every DC

Still with Hanoi RF=3 and Singapore RF=3:

1. A `QUORUM` write can be ACKed by **3 Hanoi replicas + 1 Singapore replica**.
2. A `LOCAL_QUORUM` read in Singapore can read ACKs/data from **the two Singapore replicas that have not yet received the mutation**.
3. Because there is no guaranteed intersection between the **1 ACKed replica in Singapore** and the **2 replicas chosen for reading**, the read might miss the newly written record.

That is why a cluster-wide `QUORUM` write does not guarantee every DC has a local quorum of the new data immediately.

### 8.3. `EACH_QUORUM` Write and `LOCAL_QUORUM` Read in Each DC

With RF=3 per DC, an `EACH_QUORUM` write is ACKed by **at least two replicas in each DC**. A `LOCAL_QUORUM` read in any given DC also involves **at least two replicas**. Since `2 + 2 > 3`, the two sets intersect **within that DC**.

This is a useful property when a workload needs local-quorum reads in any DC once writes are confirmed in every DC. Still, you must account for **concurrent writes, timestamp reconciliation, timeouts, and topology changes**; quorum intersection is not equivalent to a conditional transaction.

### 8.4. Do Not Confuse LWT with Regular Write Consistency Levels

`QUORUM` or `EACH_QUORUM` only describe ACK rules for regular operations. If you need "only one client reserves the slot" or "only create the username if absent," you need **`IF NOT EXISTS` / `IF`** and **lightweight transactions (Paxos)**.

LWTs have **serial consistency** levels such as `SERIAL` and `LOCAL_SERIAL` for their consensus phase. These **are not aliases for `QUORUM` or `EACH_QUORUM`**. Especially under multi-DC contention, serial consistency scope must be designed explicitly. Never assume "`EACH_QUORUM` is cross-DC CAS."

## 9. Handling Unavailable, Timeouts, and Retries in Multi-DC

When a CL cannot be satisfied, applications can encounter different outcomes:

| Outcome | Meaning | How to Handle |
|---|---|---|
| Write succeeded | Required ACKs for the request's CL were met | Proceed per business logic; continue monitoring replicas/repair |
| `Unavailable` | Coordinator determined not enough replicas are available to satisfy CL | Inspect nodes/DCs, RF, network, and fallback policy |
| `WriteTimeout` | Insufficient ACKs arrived before the timeout | **Uncertain** how many replicas already applied the mutation |
| `ReadTimeout` | Insufficient valid responses arrived within the read timeout | Investigate slow DC, disk/network, retry within limits |
| Client-side disconnect | Unknown whether the server completed the operation | Reconcile state; avoid retries with duplicate side effects |

A timeout error **does not mean the write reached zero replicas**. If a write is simple and idempotent, the client may perform bounded retries per policy. For counter increments, non-idempotent operations, or business steps with external side effects, blind retries can corrupt state.

### Should You Automatically Downgrade `EACH_QUORUM` to `LOCAL_QUORUM` When a Remote DC Fails?

That is a **decision to alter business consistency guarantees**, not merely a timeout workaround.

- Downgrading from `EACH_QUORUM` to `LOCAL_QUORUM` lets writes keep succeeding in the local DC **while dropping the guarantee of quorum across every DC**.
- You must evaluate whether data is allowed to be updated in one DC while another DC is isolated.
- You need a recovery strategy when the DC returns: hinted handoff, repair, timestamp conflict handling, divergence detection, and write policies during network partitions.

Never configure clients to silently downgrade CL without an explicit architectural decision, observability, and runbook.

## 10. Java Driver 4.x Example

Suppose the cluster uses `NetworkTopologyStrategy` as in Section 2 and the Java app connects to `dc_hanoi`. The driver needs the **local datacenter** to select suitable nodes/routes and make `LOCAL_QUORUM` meaningful relative to the request origin.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc_hanoi")
        .build()) {

    PreparedStatement upsert = session.prepare(
        "INSERT INTO shop_global.order_by_id " +
        "(order_id, status, updated_at) VALUES (?, ?, ?)"
    );

    UUID orderId =
        UUID.fromString("11111111-1111-1111-1111-111111111111");

    // Require a quorum ACK in EACH DC for a regular mutation.
    BoundStatement writeEach = upsert.bind(
            orderId, "CONFIRMED", Instant.parse("2026-11-21T10:00:00Z"))
        .setConsistencyLevel(DefaultConsistencyLevel.EACH_QUORUM);

    session.execute(writeEach);

    PreparedStatement byId = session.prepare(
        "SELECT status, updated_at FROM shop_global.order_by_id " +
        "WHERE order_id = ?"
    );

    // Read using QUORUM; DO NOT set EACH_QUORUM on SELECT.
    BoundStatement readGlobal = byId.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.QUORUM);

    Row row = session.execute(readGlobal).one();
    if (row != null) {
        System.out.println(row.getString("status"));
    }

    // When local reads are the goal, consider LOCAL_QUORUM:
    BoundStatement readLocal = byId.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    Row localRow = session.execute(readLocal).one();
}
~~~

**Note on this example:** contact point `127.0.0.1` is illustrative only; in real deployments configure redundant contact points, authentication, TLS, and the proper local DC. `DefaultConsistencyLevel.EACH_QUORUM` is a **write CL** for regular INSERTs, not a promise that subsequent SELECTs can use `EACH_QUORUM`.

In Java services, set CL at the DAO/service or execution-profile level per API requirement instead of hardcoding one CL across all statements. For example:

- **Frequent reads in the DC closest to users:** choose `LOCAL_QUORUM` if consistency requirements permit.
- **Writes requiring quorum in every DC:** use `EACH_QUORUM`, accepting the latency and failure exposure when another DC is unavailable.
- **Reads/writes needing overall replica quorum:** use `QUORUM` when scope and WAN impact fit.

These choices must be grounded in SLAs, outage tolerance, and repair strategy—not merely a desire for "maximum consistency."

## 11. Monitoring and Operating with `QUORUM` / `EACH_QUORUM`

### 11.1. Per-DC Visibility

A useful dashboard separates:

| Area | What to Monitor | Why |
|---|---|---|
| Replica availability | UP/DOWN nodes per DC/rack, actual RF | Determine if enough ACKs exist to meet CL |
| Request metrics | Read/write p50/p95/p99 latency by CL, timeouts, unavailable | Quantify cross-DC quorum overhead |
| DC links | RTT, packet loss, throughput, connection errors | Detect when WAN dominates response time |
| Infrastructure | Disk latency, compaction, CPU, GC, dropped messages | One slow DC can stall every `EACH_QUORUM` write |
| Replica sync | Hinted handoff, repair, streaming | Catch up replicas that missed mutations beyond required ACKs |
| Data correctness | State/timestamp conflicts, data versions | Quorum does not replace business rules or CAS |

Do not monitor only the coordinator in the application's DC. Disk saturation in a remote DC can slow down or fail `EACH_QUORUM` writes even when CPU and networking in the client's local DC look completely normal.

### 11.2. Investigative Commands

~~~bash
# Check node status by datacenter/rack.
nodetool status

# Topology/cluster view from the inspected node.
nodetool describecluster

# Check load, GC/disk/compaction within operational scope.
nodetool info
nodetool compactionstats

# Check streaming during recovery or topology changes.
nodetool netstats
~~~

In `cqlsh`, inspect keyspace configuration and current CL:

~~~cql
DESCRIBE KEYSPACE shop_global;
CONSISTENCY;
~~~

When investigating real incidents, collect **the CQL query, consistency level, keyspace, partition key, per-DC RF, error timestamps, and replica states**. Never stop at "the cluster has all six nodes UP" while ignoring actual ACK distribution.

## 12. Common Design Scenarios

### 12.1. Regional API Prioritizing Latency and WAN Resilience

A system has applications in Hanoi and Singapore with data replicated across both DCs. If the product tolerates cross-DC convergence lag, `LOCAL_QUORUM` for reads/writes in the DC closest to the application avoids WAN dependence on the acknowledgment path. However, the two DCs may observe temporarily different states, especially when both write to the same entity.

### 12.2. Business Operation Requiring Quorum in Both DCs at Write Acceptance

If the requirement is **confirming the mutation on a majority of replicas in every DC before returning success**, `EACH_QUORUM` for regular writes is a candidate. Plan for the fact that losing quorum in one DC fails the request, and WAN slowdowns directly impact p99.

This level **does not** enforce concurrency invariants like "create at most one order" or "non-negative balance"; those invariants require data modeling plus CAS/LWT or an appropriate coordination mechanism.

### 12.3. Needing Global Quorum While Surviving One DC Outage

Across three DCs with RF=3 each, `QUORUM` over total RF=9 requires five ACKs. If one DC fails, the remaining two DCs hold up to six replicas and can satisfy it. `EACH_QUORUM` cannot be satisfied because it demands quorum from the lost DC. However, if applications later read at `LOCAL_QUORUM` in the recovered DC, re-evaluate quorum intersection and repair requirements.

### 12.4. Database with Asymmetric RF

If RF is `5 + 1`, total `QUORUM` is 4; the RF=5 DC alone can supply all four ACKs. That **does not mean the write completed in the RF=1 DC**. With `EACH_QUORUM`, the RF=1 DC must provide at least one ACK alongside the quorum from the RF=5 DC.

Therefore avoid saying "`QUORUM` automatically replicates synchronously to every region"; that is not what this CL means.

## 13. Self-Check Exercises

**Exercise 1.** Hanoi RF=3, Singapore RF=3. A write receives three ACKs from Hanoi and one ACK from Singapore. Which levels are satisfied: `QUORUM`, `EACH_QUORUM`, or `LOCAL_QUORUM` in Hanoi?

**Answer:** `QUORUM` is satisfied (4/6); `LOCAL_QUORUM` in Hanoi is satisfied (3/3, exceeding threshold 2); `EACH_QUORUM` is not satisfied because Singapore needs 2 ACKs.

**Exercise 2.** Hanoi RF=3, Singapore RF=2. How many ACKs are needed for `QUORUM` and `EACH_QUORUM`?

**Answer:** `QUORUM` requires 3/5 total. `EACH_QUORUM` requires 2/3 in Hanoi **and** 2/2 in Singapore, totaling at least four ACKs.

**Exercise 3.** Is setting `CONSISTENCY EACH_QUORUM` and running `SELECT` a valid way to choose a read CL?

**Answer:** No. `EACH_QUORUM` is not supported for regular reads. For `SELECT`, evaluate `QUORUM` or `LOCAL_QUORUM` depending on requirements.

**Exercise 4.** Two DCs with RF=3+3. One DC fails completely. Can a `QUORUM` write succeed with the three healthy replicas in the remaining DC?

**Answer:** No: four ACKs out of six replicas are required. `LOCAL_QUORUM` in the surviving DC can keep operating if 2/3 respond and other conditions allow.

**Exercise 5.** Three DCs with RF=3 each. One DC is completely down. Compare `QUORUM` and `EACH_QUORUM` writes.

**Answer:** `QUORUM` needs five ACKs out of nine; the six replicas in the two surviving DCs can satisfy it. `EACH_QUORUM` cannot succeed because the downed DC yields zero ACKs.

**Exercise 6.** Why doesn't a `3+1` `QUORUM` write in an RF=3+3 setup guarantee that an immediate `LOCAL_QUORUM` read in the DC with one ACK sees the new record?

**Answer:** The two replicas selected for the local read in that DC could be the two replicas that have not yet acknowledged the write, so there is no guaranteed replica intersection within that DC.

**Exercise 7.** After an `EACH_QUORUM` write timeout, an ops team wants to automatically switch to `LOCAL_QUORUM` and retry. Is this merely reducing latency?

**Answer:** No. It changes the confirmation-scope guarantee, and the timed-out write may already have been applied on some replicas. You need idempotency, outcome verification, and explicit business/runbook approval.

## 14. Summary of Operational Principles

1. **Count quorum in the right scope:** `QUORUM` uses total keyspace RF; `EACH_QUORUM` requires quorum in **every DC**; `LOCAL_QUORUM` checks only the local DC.
2. **Respect operation support:** `QUORUM` works for regular reads and writes; `EACH_QUORUM` is a **write** level, not for `SELECT`.
3. **Never confuse total ACKs with distribution:** `3+1` can meet global `QUORUM=4` yet fail `EACH_QUORUM=2+2`.
4. **Weigh WAN and availability:** requiring per-DC quorum ties availability to every DC's health; local quorum isolates request paths from remote DCs without confirming remote sync.
5. **Separate replica consistency from business invariants:** CL does not create transactions/CAS; `IF` operations use LWTs and dedicated serial consistency.
6. **Never mask timeouts with automatic CL fallbacks:** a timeout has an indeterminate outcome; retries must be controlled.
7. **Measure per datacenter:** replication, health, read/write latency, networking, hinted handoff, and repair must be monitored together.

**Conclusion:** In multi-datacenter Apache Cassandra, choosing between `QUORUM` and `EACH_QUORUM` is not picking a "stronger" number, but choosing **the scope within which the application requires enough confirming replicas**. Start with each DC's RF, supported CQL operation types, WAN outage tolerance, and regional data visibility needs; only then set the corresponding CL in CQL or the Java Driver.
