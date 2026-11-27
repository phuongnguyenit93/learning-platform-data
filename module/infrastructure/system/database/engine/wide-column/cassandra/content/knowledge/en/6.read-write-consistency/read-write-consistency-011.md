# Impact of Node Failures, Slow Networks, and Unavailability on Each Choice

In Apache Cassandra, whether a request succeeds or fails does not depend solely on **how many nodes in the cluster are still running**. What matters more is: **how many replicas of the exact partition, within the right datacenter scope, can respond in time to satisfy the consistency level (CL)?** A shut-down replica, a slow network link, and an isolated datacenter can produce very different outcomes even when the application sends the exact same CQL query.

This lesson belongs to the **Read/Write Consistency** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Alongside distributed architecture and the wide-column model, partition keys, query-driven table design, CQL, replication, compaction, repair, error handling, and connecting from Java applications, the content here focuses on **the impact of node failures, network latency, and unavailability on each CL choice**.

> **Critical distinction:** **`Unavailable`** generally indicates the coordinator determined there are not enough replicas *considered alive* to satisfy the CL. **`Timeout`** generally indicates the operation failed to gather enough responses or finish before the deadline. **Neither proves data has been lost, nor proves the mutation was definitely not applied.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Compute the required responding replica threshold for `ONE`, `TWO`, `THREE`, `QUORUM`, `ALL`, `LOCAL_ONE`, `LOCAL_QUORUM`, and `EACH_QUORUM`.
2. Distinguish **node down**, **network partition**, **slow network**, **overloaded replica**, and **coordinator disconnect** failures.
3. Predict which CLs can potentially succeed under specific distributions of healthy replicas.
4. Distinguish `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, replica failures, and driver-side timeouts.
5. Explain why a write request that fails its CL can still have been applied by some replicas.
6. Understand the roles of hinted handoff, read repair, anti-entropy repair, and stale read risks after an incident.
7. Practice selecting CLs in `cqlsh` and handling errors properly with Java Driver 4.x.

## 2. Prerequisites: RF, Coordinator, and Partition Replicas

First, distinguish **cluster nodes** from **a partition's target replicas**:

- **Partition key** determines the partition; token distribution and the replication strategy determine which replicas store that partition.
- **Replication factor (RF)** specifies the number of copies of each partition within a DC or configured replica scope.
- **Coordinator** is the node receiving and orchestrating the request. It can be a target replica, though it is **not required to be**.
- **Consistency level** governs *how many and which scope* of responses are required before the coordinator reports success.

Suppose a keyspace uses `NetworkTopologyStrategy`:

```text
                    Cassandra cluster

dc1 — RF = 3                    dc2 — RF = 3
  A1  A2  A3                      B1  B2  B3
  |   |   |                       |   |   |
  +---+---+---- partition P ------+---+---+

Partition P has 6 target replicas.
Coordinator C in dc1 receives the request from the application.
```

If `A3` is shut down, do not merely ask "does the cluster still have five nodes?" Ask **which DC the remaining five target replicas belong to, where the CL demands ACKs from, and which coordinator handles the request**.

**Assumptions used in the tables:** replicas are normal full replicas, topology/RF are stable, requests target the same partition, and the coordinator stays up. Counts indicate **threshold achievability in terms of numbers**; an operation can still fail due to timeouts, load, network partitioning, permissions, or other faults.

## 3. Counting Formulas and Consistency Levels to Distinguish

A strict majority of `N` replicas is:

\[
Q(N)=\left\lfloor \frac{N}{2} \right\rfloor+1
\]

With topology `dc1: RF=3`, `dc2: RF=3`:

| CL | Replicas Required to Respond | Scope | Used For |
| --- | --- | --- | --- |
| `ONE` | **1** target replica | Any eligible replica in the global set | Reads and writes |
| `TWO` | **2** target replicas | Global replica set | Reads and writes |
| `THREE` | **3** target replicas | Global replica set | Reads and writes |
| `QUORUM` | **`Q(6)=4`** | Majority of all six replicas | Reads and writes |
| `ALL` | **6** target replicas | Every replica of the partition | Reads and writes |
| `LOCAL_ONE` | **1** replica in coordinator's DC | Local DC only | Reads and writes |
| `LOCAL_QUORUM` | **`Q(3)=2`** in coordinator's DC | Local DC only | Reads and writes |
| `EACH_QUORUM` | **2 ACKs in dc1 and 2 ACKs in dc2** | Independent quorum in each DC | **Normal writes**; not used for normal reads in Cassandra OSS |
| `SERIAL` / `LOCAL_SERIAL` | Global / local Paxos quorum | Consensus scope of LWT | **Serial/LWT phase**, not a normal write CL replacing the rows above |

`ONE`, `TWO`, and `THREE` require *fixed ACK counts*; they **do not automatically scale** when RF increases. `QUORUM` and `LOCAL_QUORUM` are recalculated from the RF of the corresponding scope.

`LOCAL_ONE` is not equivalent to `ONE`: with a coordinator in `dc1`, a single response from `dc2` can satisfy `ONE`, yet **cannot** satisfy `LOCAL_ONE`. Likewise, global `QUORUM` **does not require** independent quorum in each DC, whereas `EACH_QUORUM` does.

## 4. Failure Modes and Cassandra's Response

### 4.1. Node Down or Replica Marked Down

A replica may stop running, reboot, suffer disk failure, or become unreachable. Cassandra nodes use liveness/failure-detector mechanisms to track peer status. The coordinator may know upfront that **not enough replicas are considered alive** for the CL and return an unavailable error.

For example, a single DC with RF=3 where only one replica is considered alive:

```text
R1: UP
R2: DOWN
R3: DOWN

Write/read ONE:    can reach 1 ACK
Write/read QUORUM: needs 2 ACKs -> insufficient replicas
Write/read ALL:    needs 3 ACKs -> insufficient replicas
```

This is a **threshold availability** problem. Never assume two down replicas mean their on-disk data is lost.

### 4.2. Node Up Yet Responding Slowly

A replica is still considered alive by the coordinator, yet it is:

- busy with compaction, flushing, GC, CPU, or disk I/O;
- backed up in request queues;
- experiencing high network latency or packet loss;
- processing read repair/reconciliation that takes extra time.

The coordinator can successfully dispatch the request to replicas, yet **fail to collect enough responses before the server timeout**. The client may then receive `ReadTimeoutException` or `WriteTimeoutException` instead of `UnavailableException`.

**Key point:** `Unavailable` relates to judging **there are not enough ready replicas**; `Timeout` relates to **not completing enough responses before the deadline**, even while replicas remain marked UP.

### 4.3. Network Partition or Unreachable Remote DC

One group of nodes runs normally yet cannot communicate with another group. The two groups may have differing liveness views due to network position; the exact same CL can succeed in one region while failing in another.

For example, `dc1` RF=3 is healthy while `dc2` RF=3 is isolated:

- `LOCAL_ONE` / `LOCAL_QUORUM` from a `dc1` coordinator: **can still succeed** if `dc1` replicas respond.
- Cluster-wide `QUORUM`: needs **4/6**, whereas `dc1` has at most **3** responses; **unachievable** without any response from `dc2`.
- `EACH_QUORUM` write: needs **two ACKs from `dc2`**, so it cannot succeed while that DC is unreachable.
- `ALL`: needs all six replicas, so it cannot succeed.

A network partition does not mean the cluster lost data; it changes **which replicas can participate in confirming a request at that moment**.

### 4.4. Coordinator Failure or Client Connection Loss

If the coordinator dies before replying, the client may receive a connection error or timeout **even though enough replicas are healthy**. This is a request-path/coordinator problem, not necessarily "CL too strict."

The driver may try another host per its routing/retry policy; however, on writes, the old coordinator may have already forwarded the mutation to some replicas before disconnecting. Therefore, retries must account for **idempotency**.

## 5. Single-Datacenter Matrix: RF=3 and Available Replicas

Assume three replicas for the partition in one DC; listed counts are replicas **responding before the deadline**, with the coordinator still serving requests.

| Responding Replicas | `ONE` / `LOCAL_ONE` | `TWO` | `THREE` | `QUORUM` | `LOCAL_QUORUM` | `ALL` |
| ---: | --- | --- | --- | --- | --- | --- |
| 3/3 | Achievable | Achievable | Achievable | Achievable | Achievable | Achievable |
| 2/3 | Achievable | Achievable | **Insufficient** | Achievable | Achievable | **Insufficient** |
| 1/3 | Achievable | **Insufficient** | **Insufficient** | **Insufficient** | **Insufficient** | **Insufficient** |
| 0/3 | **Insufficient** | **Insufficient** | **Insufficient** | **Insufficient** | **Insufficient** | **Insufficient** |

With RF=3, quorum needs `floor(3/2)+1=2`. `QUORUM` reads and writes meet their threshold if two replicas stay healthy, though two UP nodes do not guarantee every request succeeds: **one of the two responding too slowly can still cause a timeout**.

When 0 target replicas are available yet **a coordinator outside the replica set remains up and can store a hint**, an `ANY` write **can** succeed via hint. This is **not** true for reads and does not guarantee data already exists on replicas for reading back.

### Latency and Availability Trade-Offs

- `ONE` requires the fewest responses, generally providing good **service continuity** when only one target replica remains healthy. However, reads can see stale versions if the queried replica missed recent mutations.
- `TWO` at RF=3 can still tolerate one unresponsive replica; in return, it must wait for two responses.
- `THREE` and `ALL` at RF=3 both require all three responses; a single down/slow replica prevents meeting the threshold on time.
- `QUORUM` at RF=3 matches a two-ACK threshold, offering a common balance between read/write confirmation and fault tolerance.

**Do not infer absolute latency from CL alone:** `ONE` can still be slow if the chosen replica is overloaded; `QUORUM` can finish fast when two replicas reply promptly. Replica selection, speculative reads, batching, coordinator choice, and reconciliation time all affect actual latency.

## 6. Two-Datacenter Matrix: RF=3+3, Coordinator in dc1

Assume **numbers in the table represent partition replicas able to respond on time** in each DC. The coordinator runs in `dc1` and the network reaches the counted responders.

| dc1 Replicas | dc2 Replicas | `LOCAL_ONE` | `LOCAL_QUORUM` | Global `QUORUM` | Write `EACH_QUORUM` | `ALL` |
| ---: | ---: | --- | --- | --- | --- | --- |
| 3 | 3 | Yes | Yes | Yes (6≥4) | Yes (3≥2 and 3≥2) | Yes |
| 2 | 3 | Yes | Yes | Yes (5≥4) | Yes (2+3) | **No** |
| 1 | 3 | Yes | **No** | Yes (4≥4) | **No** | **No** |
| 3 | 0 | Yes | Yes | **No** (3<4) | **No** | **No** |
| 2 | 1 | Yes | Yes | **No** (3<4) | **No** | **No** |
| 1 | 0 | Yes | **No** | **No** | **No** | **No** |

**Reading the table:** "Yes" means **enough replicas exist within scope to potentially succeed**, not a guaranteed outcome. If the network is slow, a server errors out, or the coordinator disconnects, a request in a "Yes" cell can still time out.

### Why Does `QUORUM` Sometimes Succeed While `LOCAL_QUORUM` Fails?

In row `dc1=1, dc2=3`:

- `LOCAL_QUORUM` with a `dc1` coordinator needs **two ACKs in `dc1`**, yet only one exists → fails.
- Global `QUORUM` needs **any four ACKs across six replicas**, and can gather 1 in `dc1` and 3 in `dc2` → meets threshold.

Therefore, `QUORUM` cannot be described simply as "always stronger and harder to satisfy than `LOCAL_QUORUM`." The two levels have **different scopes**.

### Writing `EACH_QUORUM` Can Be Harder Than `QUORUM`

In the same `dc1=1, dc2=3` case, four total ACKs satisfy `QUORUM` yet **fail** `EACH_QUORUM`: `dc1` strictly requires **two ACKs**. `EACH_QUORUM` writes must always check **each DC individually**, not just sum cluster-wide nodes.

### Total Loss of dc2

If `dc1` retains three replicas while `dc2` is unreachable, an application coordinating in `dc1` generally still has **`LOCAL_ONE` or `LOCAL_QUORUM`** available. Switching from `QUORUM` to `LOCAL_QUORUM` during an outage, however, **changes the consistency scope the application receives**: locally confirmed writes do not guarantee a client in `dc2` immediately reads the mutation once that DC recovers.

**Do not automatically downgrade CL on error** if business logic demands cross-DC guarantees. Lowering CL may boost availability while altering freshness and replicated-ACK expectations.

## 7. Unbalanced RF and Non-Obvious Effects During WAN Loss

Consider two different topologies, coordinator in `dc1`.

### 7.1. RF = 3+2

`N_total=5` so `QUORUM=3`; `LOCAL_QUORUM(dc1)=2`; `LOCAL_QUORUM(dc2)=2`; `EACH_QUORUM` write needs `2 in dc1 and 2 in dc2`.

If `dc2` is isolated while all three `dc1` replicas stay up:

- Cluster-wide `QUORUM` **can achieve 3/5 solely from `dc1`**.
- `LOCAL_QUORUM` in `dc1` **can achieve 2/3**.
- `EACH_QUORUM` **fails**, since `dc2` needs 2 ACKs.
- `ALL` **fails**, since all five are needed.

Thus **not every multi-DC `QUORUM` requires a WAN ACK**; it depends on each DC's RF.

### 7.2. RF = 5+1

`N_total=6`, `QUORUM=4`, `LOCAL_QUORUM(dc1)=3`, while `EACH_QUORUM` write needs `3 in dc1 and 1 in dc2`.

If all of `dc2` loses connectivity while `dc1` retains five replicas:

- `QUORUM` **can succeed** via four ACKs in `dc1`.
- `LOCAL_QUORUM` **can succeed** via three ACKs in `dc1`.
- `EACH_QUORUM` **fails** because `dc2` has 0 ACKs.

The takeaway is that **total RF and RF distribution determine fault tolerance**, not DC count alone.

## 8. Slow Networks: How Unavailable, Timeout, and Failure Differ

### 8.1. `UnavailableException`

The coordinator checks replica states known to it and determines **not enough replicas are alive for the requested CL**. For instance, RF=3, CL=`QUORUM` needs two replicas, yet only one target replica is considered alive. The request may be rejected with `UnavailableException` **before completing the read/write path**.

This error speaks to **readiness thresholds as viewed by the coordinator**, not a claim that data never existed.

### 8.2. `ReadTimeoutException`

Enough replicas may appear alive when the request starts, yet the coordinator **fails to collect enough required read responses or fails to receive the needed data before deadline**.

For example, RF=3, `QUORUM` read: the coordinator sends requests to two UP replicas; one replies slowly or the post-digest-mismatch data fetch exceeds the timeout.

Some protocol/driver versions report responses received, responses required, and whether a data response arrived. **Do not equate "received enough digests/responses" with "already have the data to return to the client."**

### 8.3. `WriteTimeoutException`

The coordinator **failed to confirm enough write responses for the CL before the deadline**. Example RF=3, `QUORUM` write:

```text
Replica A: wrote mutation and ACKed
Replica B: may have written, yet ACK arrived late
Replica C: no response

Coordinator lacked 2 timely ACKs -> WriteTimeout
```

**Never infer "WriteTimeout means no replica wrote."** The mutation may have already been applied by one or more replicas. Retries must be designed around idempotency and business state.

### 8.4. `ReadFailureException` and `WriteFailureException`

Beyond responding slowly, a replica can **report a processing error** on the request, preventing the CL from being satisfied. Causes can include resource issues, disk errors, or data processing faults; inspect node-specific errors and metrics instead of guessing broadly.

### 8.5. Driver-Side Timeouts and Connection Errors

The driver also enforces its own deadline/request timeout. If **the driver times out**, the client may receive `DriverTimeoutException` or an aggregate host-connection/availability failure such as `AllNodesFailedException` (depending on failure path and driver). This is **not identical** to a server-side `UnavailableException`.

| Observed Error | Primary Issue | What Must NOT Be Claimed |
| --- | --- | --- |
| `UnavailableException` | Coordinator sees too few live replicas for the CL. | "Data is lost." |
| `ReadTimeoutException` | Read failed to meet response/data conditions on time. | "All replicas are down." |
| `WriteTimeoutException` | Write was not confirmed to CL before deadline. | "The mutation was definitely not written." |
| `ReadFailureException` / `WriteFailureException` | Replicas reported execution failures; CL not achieved. | "Just raising the timeout will fix it." |
| Driver/request timeout | Client did not receive a result before its own limit. | "The server did not apply the mutation." |
| Lost coordinator/host connection | Request send/receive path failed. | "The partition's replicas are all unavailable." |

**Diagnostic order:** first identify **who emitted the error** (server/coordinator vs. driver), next verify **CL + RF + local DC**, and only then evaluate timeouts, network, and node health.

## 9. Reading and Writing When Replicas Diverge After an Outage

Meeting an ACK threshold does not mean every replica holds the exact same version at that instant.

### 9.1. `ONE` Reads Can Be Stale

RF=3: a `QUORUM` write succeeded on `A,B`, while slow replica `C` has not received the mutation yet. A `ONE` read fetching data from `C` can return the older value:

```text
Write PAID:  A=PAID   B=PAID   C=CREATED
              ACK      ACK     not updated yet

Read ONE from C -> may see CREATED
```

This is a **freshness trade-off**. It is not data corruption merely because every request returned success at a low CL.

### 9.2. Quorum Reads and Writes in the Same Scope

If RF=3, a `QUORUM` write succeeds with two replicas, and a subsequent `QUORUM` read also requires two replicas. Since:

\[
R+W=2+2=4>3
\]

the write-ACK and read-response sets must intersect. When there are no concurrent writes and timestamp/reconciliation conditions hold, this provides the basis to expect the read sees the confirmed mutation.

**Important exception:** this formula applies directly only over **the same replica set**. A `LOCAL_QUORUM` write in `dc1` followed by a `LOCAL_QUORUM` read in `dc2` has no overlap guarantee, even though both use local quorum.

### 9.3. `ANY` and Hinted Handoff

`ANY` is for **writes** only. When no target replica responds yet the coordinator **stores a hint**, the write request **can still succeed**. A hint is not a target replica confirming the write; data may **not be readable** until the mutation is replayed.

Hinted handoff helps deliver missed mutations when a replica recovers, but it is only **best effort**. Prolonged node outages, lost hints, or topology changes require **anti-entropy repair** and proper operations. Compaction manages SSTables/tombstones and **does not replace repair**.

## 10. SERIAL/LOCAL_SERIAL: How Do Failures Affect LWT?

`SERIAL` and `LOCAL_SERIAL` control the **Paxos consensus** scope of lightweight transactions (LWT), such as `INSERT ... IF NOT EXISTS` or `UPDATE ... IF ...`. They **do not** replace normal write response levels.

With RF=`3+3`:

- `SERIAL` uses **cluster-wide** Paxos quorum scope, corresponding to a quorum of 6 replicas = **4**.
- `LOCAL_SERIAL` uses the **coordinator's DC** Paxos quorum scope, corresponding to a quorum of 3 replicas = **2**.
- An LWT's normal CL, such as `QUORUM` or `LOCAL_QUORUM`, is a **separate** choice from its serial CL.

If the remote DC is isolated, an LWT using global `SERIAL` may lack Paxos quorum, whereas `LOCAL_SERIAL` in the healthy DC can meet local quorum. However, **never treat two local serial quorums in two separate DCs as a single cluster-wide consensus decision**.

### An LWT Timeout Does Not Mean the Condition Was Not Applied

Paxos involves multiple exchange phases. If a client times out during the serial phase or after commit has begun, the final state may be **unknown** to the client. Retrying `INSERT ... IF NOT EXISTS` may return `[applied]=false` because **the prior attempt already created the row** while the response was lost. Preserve request identifiers and reconcile state rather than retrying blindly.

**Note:** `EACH_QUORUM` is a **normal write** CL, not a Paxos serial level. Do not substitute `EACH_QUORUM` for `SERIAL`/`LOCAL_SERIAL` when the problem requires compare-and-set.

## 11. CQL Practice: Observing the Impact of CL

Use only a **test cluster** with an actual datacenter named `dc1` and at least three nodes for RF=3. Example creating a table queried by partition key `shipment_id`:

```sql
CREATE KEYSPACE IF NOT EXISTS failure_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS failure_lab.shipment_by_id (
  shipment_id uuid PRIMARY KEY,
  status text,
  updated_at timestamp
);
```

In `cqlsh`, `CONSISTENCY` is a **shell command** applying to statements **executed after it**:

```sql
-- Requires at least 2 replicas in this DC.
CONSISTENCY QUORUM;

INSERT INTO failure_lab.shipment_by_id
    (shipment_id, status, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'CREATED',
    '2026-11-21 10:00:00+0000'
);

-- Quorum read, also requires 2 responses.
SELECT shipment_id, status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;

-- Needs only one replica, trading freshness for availability/latency.
CONSISTENCY ONE;

SELECT status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;

-- ALL requires all three replicas; avoid testing on an unstable production cluster.
CONSISTENCY ALL;

SELECT status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;
```

When all three replicas are healthy, these commands may return the same value. **One successful run does not prove all CLs share the same guarantees when failures occur.**

### A Safe Availability Experiment

In a lab with synthetic data and a known topology:

1. Verify keyspace RF, coordinator's local DC, and target replicas for the partition.
2. Measure baseline results and latency at `ONE`, `QUORUM`, and `ALL` on a healthy cluster.
3. Use a **controlled fault-simulation mechanism in the lab** to observe when **one target replica** cannot respond. Never shut down production nodes.
4. Predict beforehand: with RF=3 and 2 replicas left, `ONE`/`QUORUM` **can succeed**, while `ALL` **fails to meet its threshold**.
5. Distinguish **unavailable errors** from **timeout errors** using logs and node state; do not look only at response duration.
6. Recover the node, observe hinted handoff/repair per operational runbooks, and confirm data convergence.

Useful read-only status commands on an admin node:

```bash
nodetool status
nodetool describecluster
```

They help observe node and topology state, **not direct proof that every replica of a specific partition is synchronized**. Deep investigation requires cross-checking token/replica placement, logs, metrics, and request outcomes.

### Expanding to Two DCs

In a lab that truly has two DCs with enough nodes, change the replication strategy:

```sql
CREATE KEYSPACE IF NOT EXISTS failure_multi_dc_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};

CREATE TABLE IF NOT EXISTS failure_multi_dc_lab.shipment_by_id (
  shipment_id uuid PRIMARY KEY,
  status text
);
```

When the coordinator is in `dc1`, the thresholds are:

```text
ONE            = 1 arbitrary ACK
LOCAL_ONE      = 1 ACK from dc1
LOCAL_QUORUM   = 2 ACKs from dc1
QUORUM         = 4 total ACKs across dc1+dc2
EACH_QUORUM    = 2 ACKs dc1 AND 2 ACKs dc2 (writes only)
ALL            = 6 ACKs
```

**Do not run `SELECT` with `EACH_QUORUM` on Cassandra OSS**: it is not a valid CL for normal reads.

## 12. Java Driver 4.x: Classifying Errors Before Deciding to Retry

The example below illustrates setting normal CL per statement. The session must be initialized with contact points, authentication, and `local datacenter` matching your environment:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class ShipmentRepository {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public ShipmentRepository(CqlSession session) {
        this.session = session;
        this.write = session.prepare(
            "UPDATE failure_lab.shipment_by_id " +
            "SET status = ?, updated_at = ? WHERE shipment_id = ?");
        this.read = session.prepare(
            "SELECT status FROM failure_lab.shipment_by_id " +
            "WHERE shipment_id = ?");
    }

    public void updateStatus(
            UUID shipmentId, String status, Instant eventTime) {
        BoundStatement request = write
            .bind(status, eventTime, shipmentId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            session.execute(request);
        } catch (UnavailableException e) {
            // Not enough replicas considered alive for the CL.
            // Do not silently downgrade CL unless business rules allow it.
            throw e;
        } catch (WriteTimeoutException e) {
            // One or more replicas may have applied the mutation.
            // Do not blindly retry as a brand-new write.
            throw e;
        } catch (DriverTimeoutException e) {
            // Client-side wait expired; write outcome may be indeterminate.
            throw e;
        }
    }

    public String findStatus(UUID shipmentId) {
        BoundStatement request = read.bind(shipmentId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            Row row = session.execute(request).one();
            return row == null ? null : row.getString("status");
        } catch (UnavailableException | ReadTimeoutException e) {
            // Classify and record appropriate metrics/logs at the service layer.
            // Do not treat a read error as "shipment does not exist."
            throw e;
        }
    }
}
```

**Design note:** The example passes `eventTime` from the caller instead of generating a new value on every retry. When retrying the same mutation, you can preserve keys and payloads for reconciliation. Still, even with identical payloads, Cassandra cell timestamps and business side effects must be controlled; **never label every update idempotent without evaluating its concrete semantics**.

Depending on the driver, failures from multiple coordinators may be wrapped in an aggregate exception. Operational logging should capture **error type, CL, DC, required/available replicas, request timeout, node/coordinator, and correlation ID**, without logging sensitive customer data.

### Should You Automatically Retry?

| Situation | Cautious Handling Approach |
| --- | --- |
| `ONE` read times out due to one slow replica | Driver may try another eligible replica per policy; bound retries and monitor load. |
| `QUORUM` read unavailable | Insufficient replicas for CL; immediate continuous retries rarely help until topology recovers. |
| `QUORUM` write times out | Outcome **indeterminate**; retry only if mutation/side effects are safely designed. |
| `ANY` write succeeds via hint | Do not claim data is immediately readable; monitor convergence. |
| LWT timeout | Inspect/reconcile outcome, preserve operation ID; do not assume `[applied]=false`. |
| Slow inter-DC network causes `EACH_QUORUM` timeouts | Revisit cross-DC consistency goals before picking another CL; never downgrade silently. |

**Automatically lowering CL** to "fix timeouts" can break an API's consistency contract, especially when an endpoint promises writes confirmed across multiple DCs. Such a change must be an **explicit business decision**, not a knee-jerk technical reflex.

## 13. Production Investigation: What to Optimize First?

When errors spike in a Cassandra system, do not merely raise timeouts. Classify by layer:

| Layer | Diagnostic Questions | Appropriate Tools/Metrics |
| --- | --- | --- |
| **CL / RF** | What is the request's actual threshold? Is the CL valid for read/write? | Keyspace config, per-statement CL, DC names. |
| **Placement / liveness** | Which partition replicas are down or unreachable? | `nodetool status`, placement, failure detector, node logs. |
| **Coordinator** | Are enough coordinators near the app? Is local DC routing right? | Driver load balancing, connection metrics, host errors. |
| **Network** | Are RTT, packet loss, or WAN timeouts rising? | Network telemetry, per-DC latency, controlled tracing. |
| **Replica latency** | Are CPU, GC, disk, queues, compaction, or SSTables overloaded? | Cassandra/JVM metrics, read/write latency, pending tasks. |
| **Divergent data** | Is there a hint backlog, read repair, or incomplete repair? | Hint metrics, repair status, logs. |
| **Application** | Is there a retry storm, hot partition, or wrong partition key query? | Request rate, coordinator latency, partition distribution, driver metrics. |

### Why Partition Key Design Still Matters

If a partition is hot, all requests for that partition concentrate on a small set of replicas. Even in a cluster of hundreds of nodes, **the specific replicas serving that hot partition can overload**, causing `QUORUM` or `ONE` timeouts.

Designing tables **around queries** and picking partition keys that distribute load well is directly part of meeting CL reliably. Raising RF or lowering CL does not replace fixing hot partitions, wide scans, or broken data models.

### Watch Hints, Repair, and Tombstones

Once a replica returns, hinted handoff can help deliver missed mutations, but only within configured limits and as **best effort**. Anti-entropy repair must be operated under an appropriate policy; with deletes/tombstones, a replica missing deletions for too long combined with `gc_grace_seconds` rules also creates the risk of deleted data resurrecting.

Never treat **compaction having run** as proof that repair finished or replicas converged.

## 14. Scenario Exercises and Answers

### Exercise 1 — One Replica Down

RF=3 in one DC. Replica `R3` is down; `R1` and `R2` respond on time. Can `ONE`, `QUORUM`, and `ALL` reads meet their thresholds?

**Answer:** `ONE` needs 1 so it **can** succeed; `QUORUM` needs 2 so it **can** succeed; `ALL` needs 3 so it **lacks enough replicas**.

### Exercise 2 — Two Replicas Down

RF=3, only one target replica remains healthy. Can `ONE`, `TWO`, and `QUORUM` writes succeed based on response count?

**Answer:** `ONE` can reach 1; `TWO` and `QUORUM` both require 2 and therefore cannot.

### Exercise 3 — Node UP Yet Slow Network

RF=3, all three replicas are considered UP. A `QUORUM` write hits `WriteTimeout`. Does this contradict having enough live nodes for quorum?

**Answer:** No. Two replicas must **ACK before the deadline**, not merely be marked UP. Delays from network/disk/load can still trigger timeouts.

### Exercise 4 — Losing Remote DC

RF=3+3, coordinator in `dc1` with three healthy replicas; `dc2` is isolated. Which of `LOCAL_QUORUM`, `QUORUM`, and `EACH_QUORUM` write can succeed?

**Answer:** `LOCAL_QUORUM` can achieve 2/3 in `dc1`. `QUORUM` needs 4/6 while `dc1` has at most 3, so it fails. `EACH_QUORUM` write lacks two ACKs in `dc2`, so it fails.

### Exercise 5 — Global Quorum Achievable, Local Quorum Fails

RF=3+3, coordinator in `dc1`. Only 1 `dc1` replica and 3 `dc2` replicas can respond. Can `QUORUM` and `LOCAL_QUORUM` in `dc1` succeed?

**Answer:** `QUORUM` needs 4/6, total is 4 so it can succeed. `LOCAL_QUORUM` in `dc1` needs 2/3 local, yet only 1 is available so it fails.

### Exercise 6 — Asymmetric RF

RF=5+1, coordinator in the RF=5 DC; the other DC is completely isolated. Can `QUORUM`, `LOCAL_QUORUM`, and `EACH_QUORUM` writes succeed?

**Answer:** `QUORUM` needs 4/6, achievable in the large DC; `LOCAL_QUORUM` needs 3/5, achievable; `EACH_QUORUM` needs at least one ACK from the small DC, so it fails.

### Exercise 7 — Unavailable or Timeout?

A `QUORUM` request at RF=3 is rejected because the coordinator sees only one replica UP. Another request sees two replicas UP, yet one responds too slowly. How do the typical errors differ?

**Answer:** The first case typically raises `UnavailableException`; the second typically raises `ReadTimeoutException` or `WriteTimeoutException` depending on operation type. Liveness status and timely response delivery are two different issues.

### Exercise 8 — Retrying a Timed-Out Write

A `QUORUM` write times out while one replica may have already applied the mutation. Should you generate a new `shipment_id` and retry right away?

**Answer:** Usually no. Creating a new key can produce duplicate business records. Keep identity stable, evaluate idempotency, and reconcile outcomes.

### Exercise 9 — Reading After Write at a Low CL

RF=3, a `QUORUM` write succeeds on `R1,R2`; a `ONE` read from un-updated `R3` returns stale data. Is this a CL violation?

**Answer:** No. `W=2`, `R=1`, `W+R=3≤3`, so the two sets can be disjoint. This is the freshness trade-off of `ONE` reads.

### Exercise 10 — ANY and Hints

No target replica receives the mutation, yet the coordinator can store a hint. Does a successful `ANY` write prove an immediate `SELECT QUORUM` will see the new data?

**Answer:** No. A hint is not a target replica having written; before replay, the data may not be readable yet. Also, `ANY` is invalid for `SELECT`.

### Exercise 11 — LWT Under Network Partition

RF=3+3, clients in both DCs try to create a unique key. Each client uses `LOCAL_SERIAL` in its own DC. Can local quorum success be used to prove global consensus?

**Answer:** No. The two local Paxos sets can be disjoint. If cross-DC uniqueness is required, consider `SERIAL` scope and a uniformly enforced application protocol.

### Exercise 12 — Why Not Automatically Downgrade CL?

An API documents "write success means a quorum in every DC confirmed." During a WAN outage, the app switches from `EACH_QUORUM` to `LOCAL_ONE` silently. What is wrong?

**Answer:** `LOCAL_ONE` needs only one local replica; it **does not** confirm quorum in every DC. Silently downgrading CL breaks the published business contract even though it lets some requests succeed.

## 15. Checklist Before Selecting CL or Changing Retry Policy

Before every change, answer:

1. **Which partition key?** Where do the partition's target replicas actually reside?
2. **What is each DC's RF?** Do not use total cluster node count alone.
3. **Which DC is the coordinator in?** `LOCAL_*` CLs depend on the coordinator's DC.
4. **Is the request a read, normal write, or LWT?** `EACH_QUORUM` is not for normal reads; `SERIAL`/`LOCAL_SERIAL` are for the Paxos phase.
5. **How many ACKs does the CL require, and where?** Write down exact numerical thresholds before guessing availability.
6. **Are replicas down or merely slow?** Distinguish unavailable from timeout/failure.
7. **Might the write have partially applied?** If so, retries must be idempotent and bounded.
8. **Does lowering CL break the business contract?** Never silently reduce consistency during outages.
9. **Are there hot partitions, overload, compaction, hint backlogs, or incomplete repairs?** Do not simply raise timeouts.
10. **Was it measured and tested on the right topology?** Single-DC RF=3 results do not represent two-DC RF=3+3 behavior.

## 16. Conclusion

The impact of Cassandra failures on each consistency level comes down to **how many replicas can respond**, **datacenter scope**, and **request completion timing**. `ONE`/`LOCAL_ONE` require few responses, favoring availability and latency, yet do not guarantee reads always observe the latest update. `QUORUM` and `LOCAL_QUORUM` create overlap for matching read/write pairs, at the cost of requiring enough replicas in their respective scopes. `ALL` easily loses availability when one replica fails; `EACH_QUORUM` requires write confirmation in **every DC**, making it particularly sensitive to cross-DC outages.

**`Unavailable` is not the same as `Timeout`:** one typically reflects insufficient live replicas in the coordinator's view, while the other reflects failing to collect enough responses before deadline. For any indeterminate write error, never assume the mutation was definitely not applied. Java applications must classify errors, apply idempotent retries, monitor metrics, and run appropriate repairs. When conditional updates must be protected against contention, look to LWT/serial consistency rather than merely raising CL.

### References

- [Apache Cassandra — Dynamo, consistency, and replication](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): quorum, replicas, read/write paths, and CL satisfaction conditions.
- [Apache Cassandra — CQL and cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): the `CONSISTENCY` command during experimentation.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, operational limits, and replicas missing writes.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): role of anti-entropy repair after failures.
- [Apache Cassandra — Architecture: Failure Detection](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): liveness mechanics and replica availability in distributed architecture.
