# Replica and Coordinator Roles When Any Node Receives a Request

## 1. The Problem to Understand

In Apache Cassandra, a client can send a read or write request to **any Cassandra node that is up and accepting connections**. The node receiving the request acts as the **coordinator** for *that request*. Meanwhile, a partition's data is stored on another set of nodes called **replicas**. Therefore, the node receiving the query is not necessarily a node holding the data.

This is a core piece of Cassandra's distributed, decentralized architecture. Understanding accurately how a coordinator orchestrates replicas explains how partition keys govern data placement, how replication factor works, and why consistency levels affect latency, availability, and read/write consistency.

After this lesson, learners can:

- Distinguish **coordinator** (a per-request role) from **replica** (a per-partition and topology role).
- Describe how a node receiving a request locates replicas from the partition key, token, and replication configuration.
- Trace the write path, read path, and how Cassandra counts acknowledgments per consistency level.
- Explain behavior when the coordinator or certain replicas fail, especially with `LOCAL_QUORUM`.
- Choose how to submit queries from CQL/Java and diagnose request paths.

**Example scope:** uses standard *full replicas* and regular read/write queries; transient replication is excluded. Lightweight transactions (LWTs) are noted separately because they involve an extra consensus phase.

## 2. Two Distinct Roles

| Concept | Definition | Key takeaway |
| --- | --- | --- |
| **Coordinator** | The node that directly receives a request from a client and orchestrates execution of that request. | Every request has one coordinator; any reachable node can act as one. |
| **Replica** | A node chosen by the replication strategy to hold a copy of a partition. | A node may be a replica for partition A while not for partition B. |
| **Partition key** | One or more columns in the primary key used to identify the partition. | Rows sharing the same partition key are placed under the same token and replica group. |
| **Token** | Output of the partitioning function computed from the partition key, typically via `Murmur3Partitioner`. | Tokens determine positions on the data distribution ring. |
| **Replication factor (RF)** | Target number of data copies configured per data center (with `NetworkTopologyStrategy`). | RF sets *how many* replicas store data, not the minimum acknowledgments for a request to succeed. |
| **Consistency level (CL)** | Acknowledgment threshold the coordinator must satisfy for a request. | CL affects availability, latency, and read/write results. |

A single node **can be both coordinator and replica** if it belongs to the queried partition's replica set; in that case, it performs its own replica work locally. If it is not in the replica set, it still serves as coordinator and forwards the request to the proper replicas.

### Example of a Coordinator That Is Not a Replica

~~~mermaid
flowchart LR
    Client["Java client / cqlsh"] -->|"Request for account_id = a-42"| N4["Node N4: coordinator"]
    N4 -->|"Mutation or read request"| N1["Node N1: replica"]
    N4 -->|"Mutation or read request"| N2["Node N2: replica"]
    N4 -->|"Mutation or read request"| N3["Node N3: replica"]
    N4 -.->|"Does not need to store this partition"| Note["N4 is not a replica"]
~~~

Suppose RF = 3 and the partition for `account_id = 'a-42'` is replicated on N1, N2, and N3. If the client connects to N4, **N4 is the coordinator**, while **N1–N3 are replicas**. If the client connects to N2, N2 acts as both coordinator and one of the replicas. Choosing a coordinator does not change where the partition is stored.

> Cassandra has no fixed *primary/leader* node for all ordinary reads and writes. Replicas are determined by token and topology; coordinator is a temporary per-request role, not data ownership.

## 3. What Happens When Any Node Receives a Request?

For an operation targeting **one specific partition**, the coordinator follows a general workflow:

1. **Receive and validate the request.** A client or driver sends CQL to a live node. That node handles authentication, authorization, and query planning per statement type.
2. **Identify the partition.** For a query with a partition key, the coordinator computes the token from the partition key components using the cluster's partitioner. For instance, `PRIMARY KEY ((account_id), event_time)` has `account_id` as its partition key.
3. **Locate the replica set.** From token ring metadata, data center/rack topology, and the keyspace's replication strategy, the coordinator learns which nodes store that partition. With `NetworkTopologyStrategy`, replica selection is computed per data center.
4. **Coordinate the request.** The coordinator sends read/write messages to the required replicas—handling work locally if it is itself a replica—while managing timeouts and responses.
5. **Enforce consistency level.** The coordinator returns success only once the operation's CL condition is satisfied; if available replicas or timely responses are insufficient, it returns the corresponding error.

Crucial distinction: **the driver picks the node receiving the request; Cassandra determines the partition's replica set**. A driver supporting *token-aware routing* generally prefers a replica in the client's local data center to avoid an extra hop, yet requests remain completely valid when a non-replica node acts as coordinator. *Contact points* in driver configuration are mainly for cluster discovery, not an exclusive list of allowed coordinators.

If a query spans multiple partitions, the coordinator may have to coordinate multiple replica groups; you cannot reason about the entire query's execution path as if it targeted a single partition.

## 4. **Write** Path: Coordinator Sends Mutations to Replicas

Example: a cluster has one data center `dc1`, RF = 3, the partition is held by N1, N2, and N3; N4 receives an `INSERT` with CL = `LOCAL_QUORUM`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant K as N4 / Coordinator
    participant R1 as N1 / Replica
    participant R2 as N2 / Replica
    participant R3 as N3 / Replica
    C->>K: INSERT, LOCAL_QUORUM
    K->>R1: Mutation
    K->>R2: Mutation
    K->>R3: Mutation
    R1-->>K: Acknowledgement
    R2-->>K: Acknowledgement
    K-->>C: Success (2/3 local replicas satisfied)
    Note over K,R3: Third replica may finish after client response
    R3-->>K: Acknowledgement (if it arrives in time)
~~~

Explanation:

1. The coordinator plans the mutation and sends it to the partition's replicas (directly or via cross-DC forwarding when spanning multiple data centers). A normal write targets **the entire replica set**, even if only a subset of acknowledgments is needed for CL.
2. Each replica receives the mutation, updates its **commit log** and **memtable** along the write path, and returns an acknowledgment. Exactly when commit logs sync to disk depends on commit-log sync configuration; do not interpret an ACK as meaning SSTables have already been flushed to disk.
3. With RF = 3 in `dc1`, `LOCAL_QUORUM` requires **2 acknowledgments from replicas in `dc1`**. Once N1 and N2 acknowledge successfully, N4 can return success to the client, even if N3 has not yet replied.
4. If a replica temporarily misses a write, the coordinator may store a **hint** when conditions permit; hints replay data once the replica recovers. Hinted handoff does not replace **anti-entropy repair** for long-term convergence.

Key takeaway: **succeeding at a given CL does not mean every replica had already acknowledged by the time the client received the result**.

### Write Acknowledgment Thresholds with RF = 3, Single Data Center

| Write CL | Minimum replicas required to ACK | If only N1, N2 remain up |
| --- | ---: | --- |
| `ONE` / `LOCAL_ONE` | 1 | Can succeed |
| `QUORUM` / `LOCAL_QUORUM` | 2 | Can succeed |
| `ALL` | 3 | Insufficient replicas to succeed |

The coordinator **does not count as a fourth replica**. If N4 does not own the partition, an ACK from N4 does not count toward the CL threshold. In this single-DC model, `QUORUM` and `LOCAL_QUORUM` both require two replicas, though they can differ in multi-DC keyspaces.

## 5. **Read** Path: Coordinator Reconciles Results from Replicas

Reading is not simply asking any single node and returning the first payload received. The coordinator must collect enough responses to meet CL and may reconcile data across replicas.

1. The client sends a `SELECT` with the partition key and consistency level.
2. The coordinator identifies the replica set. On the normal read path, it may request **full data** from one replica and **digests** (checksums used for comparison) from the other replicas needed for CL; the exact plan depends on Cassandra version, state, and optimizations.
3. If the responses match, the coordinator returns the data to the client once CL is satisfied.
4. If digests mismatch, the coordinator fetches enough data to **reconcile** versions by timestamp/tombstone and may trigger **read repair**, depending on version and table configuration. This incurs extra round-trips and higher latency.

For example, with RF = 3 and `LOCAL_QUORUM`: N4 may query N1 and N2. N1 returns full data; N2 returns a digest. If they match, N4 returns the data; if they differ, N4 fetches, merges, and resolves the discrepancy via Cassandra's reconciliation mechanism.

`ONE` or `LOCAL_ONE` generally minimizes response waiting, at the risk of reading an un-updated replica. `QUORUM` or `LOCAL_QUORUM` improves visibility of quorum-acknowledged writes, at the cost of extra responses and occasional read repair.

The common rule **W + R > RF** (e.g., RF = 3, write 2 and read 2) states that the two acknowledging replica sets share at least one overlapping node in a simple model. This is an intuition for designing consistency, **not a promise of linearizability for all operations**: concurrent writes, conflicting timestamps, clock skew, tombstones, failures, and DC scopes must all be considered. Cassandra resolves ordinary data conflicts primarily by timestamp rather than maintaining a single leader that serializes every write.

## 6. How Consistency Level Changes Requirements on Replicas

CL applies **per request**; it does not transfer partition ownership and does not change the keyspace's RF.

| Consistency level | Practical meaning | Scope |
| --- | --- | --- |
| `ONE` | Requires 1 suitable replica response for read/write. | May use a replica outside the coordinator's data center. |
| `LOCAL_ONE` | Requires 1 replica response in the coordinator's data center. | Useful when regional latency is prioritized. |
| `QUORUM` | Requires majority of **total RF**: `floor(total_RF / 2) + 1`. | Computed across all data centers holding replicas. |
| `LOCAL_QUORUM` | Requires majority of **RF in the local data center**. | Commonly used to avoid depending on remote DC responses. |
| `ALL` | Requires responses from all relevant full replicas. | Fails if even one replica is unresponsive. |
| `EACH_QUORUM` | Write must achieve quorum in **each** data center. | Used for writes; not a standard read consistency level. |
| `ANY` | Write can be acknowledged even if only a hint is stored on the receiving node, depending on case. | Write-only; does not guarantee a replica already holds readable data immediately. |
| `SERIAL`, `LOCAL_SERIAL` | Consistency level for the **serial/Paxos phase** of lightweight transactions. | Does not directly replace regular read/write CLs. |

### Two-Data-Center Example

A keyspace uses `NetworkTopologyStrategy` with RF(`dc1`) = 3 and RF(`dc2`) = 3. A request arrives at a coordinator in `dc1`:

| CL | Condition for write success in example |
| --- | --- |
| `LOCAL_ONE` | 1 replica in `dc1` responds. |
| `LOCAL_QUORUM` | 2 of 3 replicas in `dc1` respond. |
| `QUORUM` | 4 of 6 total replicas respond. |
| `EACH_QUORUM` | At least 2 replicas in **each** of `dc1` and `dc2` respond. |
| `ALL` | All 6 replicas respond. |

With `LOCAL_QUORUM`, the write is still forwarded to replicas in `dc2`, yet the coordinator **does not wait on `dc2`** before returning success. Meanwhile, if two replicas in `dc1` are unavailable, `LOCAL_QUORUM` fails even if all of `dc2` is healthy. Therefore, configure the Java driver's local data center to match the application's location; `LOCAL_` is interpreted relative to the **coordinator's** data center.

## 7. When Nodes or Networks Fail

| Scenario | Typical behavior | Conclusion |
| --- | --- | --- |
| Chosen coordinator goes down **before receiving request** | Driver can pick another live node per retry/load-balancing policy. | No fixed coordinator; client must manage connections and timeouts. |
| Coordinator dies **after sending writes** but before replying | Some replicas may have applied the mutation while client sees timeout or disconnect. | Write outcome can be **unknown from client view**; retries must consider idempotency. |
| N3 down, N1 and N2 up, RF = 3, CL = `LOCAL_QUORUM` | Two live replicas can satisfy both reads and writes. | One failed replica does not necessarily fail requests. |
| Only N1 up, RF = 3, CL = `LOCAL_QUORUM` | Fewer than 2 replicas available to meet CL. | Request fails even though coordinator is alive. |
| One replica slow but not yet marked dead | Coordinator may wait until timeout, or use appropriate speculative retry on reads. | Latency depends on replicas and network, not just coordinator health. |
| Recovered replica missed some writes | Hints can deliver part of them; repair compares and syncs replicas. | Never rely on hinted handoff as the sole convergence guarantee. |

**Distinguish two common errors:**

- **Unavailable:** the coordinator determines upfront that currently available replicas are insufficient to satisfy CL.
- **Read/Write timeout:** the coordinator waited for execution but did not receive enough valid responses within the time limit. A write may have succeeded on some replicas even though the client timed out.

Never blindly retry every write. Upsert-style writes with stable keys and values are easier to handle on retry than operations with side effects like counter updates or list appends. The driver must mark statement **idempotency** accurately and apply an appropriate retry policy.

### Hinted Handoff, Read Repair, and Anti-Entropy Repair Differ

- **Hinted handoff:** replays missed mutations to a temporarily unavailable replica within configuration and hint-window limits.
- **Read repair:** detects and can fix discrepancies when a read touches out-of-sync replicas; exact behavior depends on version, table, and consistency level.
- **Anti-entropy repair:** runs to compare and synchronize data broadly across replicas; vital for long-term consistency, especially for tombstones and rarely read data.
- **Compaction:** organizes/merges SSTables on individual nodes; **does not replace repair across replicas**.

## 8. CQL Practice: Observing Coordinator and Replicas via One Partition

Assume a cluster with a data center named `dc1` and **at least three Cassandra nodes** in that data center. Use the following keyspace and table to group events by account:

~~~sql
CREATE KEYSPACE IF NOT EXISTS webshop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS webshop.events_by_account (
  account_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((account_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`account_id` is the partition key, while `event_time` and `event_id` are clustering columns. Rows with the same `account_id` belong to one partition and use the same replica set. This also exemplifies **query-driven table design**: querying an account's event history routes directly by partition key.

In `cqlsh`, run:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO webshop.events_by_account
  (account_id, event_time, event_id, event_type)
VALUES
  ('a-42', '2026-01-01T10:00:00Z',
   550e8400-e29b-41d4-a716-446655440000, 'checkout');

SELECT event_time, event_id, event_type
FROM webshop.events_by_account
WHERE account_id = 'a-42'
LIMIT 20;

TRACING OFF;
~~~

`CONSISTENCY` and `TRACING` are **`cqlsh` control commands**, not CQL syntax sent verbatim through the Java driver. Trace output can show which endpoints the coordinator contacted, message timestamps, and per-phase latencies; exact trace events vary by version. Repeat the query from different nodes and compare: **the coordinator can change, while the partition's replica set remains fundamentally governed by token and replication** (barring topology changes).

In operations, cross-check `nodetool status` to view node/DC states alongside read/write timeouts and latency metrics. Never conclude a node is a replica merely because it serves as a contact point or coordinator. In production, weigh tracing overhead and query volume before enabling traces.

## 9. From a Java Application: Setting Consistency Level per Statement

The example below uses the **Apache Cassandra Java Driver 4.x** API. The driver discovers topology from contact points, routes requests to suitable nodes, and the receiving node acts as coordinator.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;

public class ReadAccountEvents {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "SELECT event_time, event_id, event_type " +
                    "FROM webshop.events_by_account " +
                    "WHERE account_id = ? LIMIT 20");

            BoundStatement request = prepared.bind("a-42")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet rows = session.execute(request);
            for (Row row : rows) {
                System.out.println(row.getString("event_type"));
            }
        }
    }
}
~~~

- `withLocalDatacenter("dc1")` instructs the driver to prefer routing to nodes in `dc1`, where the app is meant to operate. The value must match the real data center name.
- `LOCAL_QUORUM` is set on the statement to require sufficient responses from local data center replicas. It **does not force the contact point to be a replica**.
- Binding the partition key with a prepared statement lets the driver derive the routing key for token-aware routing. Execution is still handled by the coordinator, even after driver node-selection optimization.
- For real cluster deployments, provide reachable contact points and configure authentication/TLS and timeouts per environment; `127.0.0.1` is only for a local lab.

## 10. Self-Check Questions

**Scenario A.** RF = 3 in `dc1`. N4 receives a `LOCAL_QUORUM` write for a partition stored on N1, N2, and N3. N1 and N2 ACK; N3 has not replied. Does the request succeed? **Yes**, because two local responses suffice. N4 remains solely the coordinator and does not become a fourth replica.

**Scenario B.** Same topology; N1 is up, while N2 and N3 are unavailable. A client sends a `LOCAL_QUORUM` read to N4. Can the request succeed? **Requirements not met**: only one local replica remains whereas two are required. Switching the coordinator to N1 does not create a new replica.

**Scenario C.** Keyspace has RF = 3 in `dc1` and RF = 3 in `dc2`; coordinator is in `dc1`. Two replicas in `dc1` are down, while all three replicas in `dc2` are up. Does a `LOCAL_QUORUM` write succeed? **No**: two ACKs within `dc1` are required; replicas in `dc2` cannot make up for missing local ACKs.

**Scenario D.** The driver sends the same partition key to two different coordinators. Is data automatically replicated to two different replica sets? **No**. The replica set is computed from token, topology, and replication strategy; the coordinator is chosen per request.

## 11. Design and Troubleshooting Takeaways

1. **The coordinator answers for the request; replicas are responsible for storing the partition.** Both roles can coexist on one node without being synonymous.
2. **Partition key determines token; token plus replication strategy determine replicas.** A solid partition key avoids hotspots and scatter queries; picking a different coordinator will not fix a flawed partition key.
3. **RF sets copy count; CL sets required responses.** A write succeeding at quorum does not imply all copies have caught up.
4. **Coordinator failure and replica failure mean different things.** Clients can lose the response even after partial writes were applied; retries must account for idempotency.
5. **`LOCAL_QUORUM` depends on the coordinator's data center.** Set local DC and routing to match application placement to meet latency and fault-domain goals.
6. **Hints, read repair, and anti-entropy repair address different situations.** Never treat one mechanism as a drop-in replacement for all others.

When analyzing a Cassandra request, answer in order: **which partition key? which token? which replicas in each data center? which node is acting as coordinator? how many ACKs does CL require? which replicas actually responded?** This sequence explains most timeouts, writes still succeeding when a node fails, or stale reads when lowering consistency level.
