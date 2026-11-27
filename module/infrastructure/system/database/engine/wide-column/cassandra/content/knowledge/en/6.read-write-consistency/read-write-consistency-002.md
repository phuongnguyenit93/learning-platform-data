# ONE, TWO, THREE, QUORUM, and ALL in Apache Cassandra

In Apache Cassandra, the consistency levels **`ONE`, `TWO`, `THREE`, `QUORUM`, and `ALL`** answer a very practical question: **how many replicas must the coordinator wait to respond successfully before reporting the result of a read or write to the application?** This is a per-operation choice that directly affects latency, fault tolerance, and the visibility of recently written data.

This lesson belongs to the **Read/Write Consistency** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The overall goals of the module are to understand Cassandra's distributed architecture and wide-column model, design tables around queries and partition keys, and practice CQL, replication, compaction, repair, error handling, and Java connectivity. Within this lesson, we focus on **the five consistency levels based on replica counts**, how to calculate them, and their operational implications.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **replication factor (RF)** from **consistency level (CL)**.
2. Calculate the required response counts for `ONE`, `TWO`, `THREE`, `QUORUM`, and `ALL` as RF changes.
3. Determine which consistency levels can still succeed when one or more replicas do not respond.
4. Explain why read CL and write CL choices must be evaluated **together**.
5. Apply CL per statement using `cqlsh` and the Apache Cassandra Java Driver.
6. Avoid incorrect assumptions regarding quorum, datacenters, stale data, and timeouts.

## 2. The Nature of a Consistency Level

### Replicas, Coordinator, and RF

A **partition** is selected via the **partition key**. Cassandra uses data distribution metadata and the keyspace's replication strategy to determine which nodes are **replicas** for that partition.

- **Replica**: a node storing a copy of the partition.
- **Replication factor (RF)**: the configured number of replicas for a partition, typically defined per datacenter via `NetworkTopologyStrategy`.
- **Coordinator**: the node that receives the request from the client and coordinates the participating replicas.
- **Consistency level (CL)**: the response threshold the coordinator must receive for **a specific read or write** before returning success.

For example, in **a single datacenter, RF = 3**, the partition for user `U1` has three replicas:

```text
Client
   |
   v
Coordinator
   |------> Replica A
   |------> Replica B
   |------> Replica C

RF = 3: three data copies of partition U1
CL = TWO: requires 2 valid responses to report success
```

The key point: **CL does not determine how many copies are created**. With `CL=TWO`, Cassandra still attempts to send the mutation to the target replicas; it simply **does not force the client to wait for ACKs from all three replicas**. Similarly, the coordinator of a read query may contact multiple replicas, using full data and digests to compare results; **the actual number of calls may exceed the CL threshold**.

### Valid Responses on Reads and Writes

**On writes**, an ACK typically indicates that a replica has processed and accepted the mutation along Cassandra's write path. Only once enough ACKs arrive for the CL does the coordinator return success. An ACK does not mean all other replicas have finished updating.

**On reads**, the coordinator must collect enough replica responses to meet the CL, and then determine the data to return. Comparing data/digests across replicas and reconciling differing versions allows `TWO`, `THREE`, or `QUORUM` reads to detect inconsistent data better than `ONE` reads.

The CLs in this lesson can be used for **normal reads and writes**. Levels such as `ANY` (writes), `LOCAL_ONE`, `LOCAL_QUORUM`, `EACH_QUORUM`, and `SERIAL`/`LOCAL_SERIAL` serve different needs and are mentioned to avoid confusion.

## 3. Five Consistency Levels: Definitions and Formulas

Assume a partition has **N replicas** within the scope being considered. For `ONE`, `TWO`, and `THREE`, the response threshold is an **absolute number**; for `QUORUM`, the threshold depends on RF; and `ALL` requires every replica.

| Consistency level | Minimum Responses | Meaning |
| --- | ---: | --- |
| `ONE` | **1** | Only one replica needs to respond. |
| `TWO` | **2** | Two distinct replicas must respond. |
| `THREE` | **3** | Three distinct replicas must respond. |
| `QUORUM` | **⌊N/2⌋ + 1** | Requires a **strict majority** of replicas. |
| `ALL` | **N** | Must receive responses from **all replicas** of the partition. |

With a single datacenter, `N` is the RF of that datacenter. `QUORUM` is calculated as:

\[
Q = \left\lfloor \frac{RF}{2} \right\rfloor + 1
\]

Examples:

| RF | `ONE` | `TWO` | `THREE` | `QUORUM` | `ALL` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | Insufficient replicas | Insufficient replicas | **1** | **1** |
| 2 | 1 | 2 | Insufficient replicas | **2** | **2** |
| 3 | 1 | 2 | 3 | **2** | **3** |
| 4 | 1 | 2 | 3 | **3** | **4** |
| 5 | 1 | 2 | 3 | **3** | **5** |

**Important observations:**

- With **RF = 3**, `TWO` and `QUORUM` both require **2** responses; `THREE` and `ALL` both require **3**.
- With **RF = 5**, `THREE` and `QUORUM` both require **3**, whereas `TWO` only requires **2**.
- `TWO` and `THREE` keep a fixed threshold of **2** or **3**, even as RF grows; `QUORUM` and `ALL` scale with the number of replicas.
- You cannot expect `THREE` to succeed if a partition only has RF = 2. Setting a threshold higher than the configured replica count does not cause Cassandra to create extra replicas.
- `ALL` means **every replica of the partition under the replication strategy**, not every node in the entire cluster.

## 4. Reads/Writes at RF = 3: Same Data, Five Ways to Wait

Suppose the partition for account `A-101` is replicated across three replicas `R1`, `R2`, and `R3`. The application sends an update to `display_name` through a coordinator.

```mermaid
sequenceDiagram
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3
    Note over C,R3: Example RF = 3, CL = TWO
    C->>R1: Send mutation
    C->>R2: Send mutation
    C->>R3: Send mutation
    R1-->>C: ACK (1)
    R2-->>C: ACK (2)
    Note over C: 2 ACKs reached; return success
    R3-->>C: Late ACK (if any)
```

If **`R3` is slow or disconnected**, the request outcome depends on the CL:

| CL | Threshold | Outcome when `R1` and `R2` respond, `R3` does not |
| --- | ---: | --- |
| `ONE` | 1 | Can succeed after the first response. |
| `TWO` | 2 | Can succeed. |
| `THREE` | 3 | Fails to meet CL; operation fails/times out. |
| `QUORUM` | 2 | Can succeed. |
| `ALL` | 3 | Fails to meet CL; operation fails/times out. |

Suppose `R2` also stops responding, leaving only `R1`:

- `ONE` can still return success if `R1` responds before the deadline.
- `TWO`, `THREE`, `QUORUM`, and `ALL` will all fail to receive enough responses for their chosen thresholds.

With RF = 3, assuming the remaining replicas operate normally, replica fault tolerance based on the response threshold is:

| CL | Maximum replicas that can be unresponsive while still meeting CL |
| --- | ---: |
| `ONE` | **2** |
| `TWO` / `QUORUM` | **1** |
| `THREE` / `ALL` | **0** |

This is a **CL achievability** calculation: `RF - required ACKs`. It does not guarantee every read/write will succeed, because coordinator failures, network issues, disk errors, timeouts, and application errors can still occur.

### `ONE`: Prioritizing Few Responses, Accepting Stale Read Risk

`ONE` is useful when an application accepts **eventually consistent** data: writes can complete faster, and reads can succeed when only a single replica is reachable. For example, event feeds or display info that can tolerate brief update delays.

If a write was only ACKed by `R1` and a subsequent `ONE` read retrieves the value from `R3` before it catches up, the client **may see an older value**. Reading at `ONE` after a successful `ONE` write does not inherently guarantee **read-your-writes**.

### `TWO` and `THREE`: Fixed Thresholds

`TWO` requires two ACKs whether RF is 3, 4, or 5. `THREE` requires three ACKs. They are useful when you want to enforce an **absolute response count**, but their names **do not imply a majority** if RF changes.

For example, with RF = 5:

- `TWO`: 2/5 replicas, **not yet a majority**.
- `THREE`: 3/5 replicas, **exactly equal to quorum**.

Therefore, assuming "`TWO` is always equivalent to `QUORUM`" holds only in **numerical threshold** for certain configurations, such as RF = 3.

### `QUORUM`: Waiting for a Majority of Replicas

`QUORUM` requires `floor(RF / 2) + 1` ACKs in a single datacenter; this majority scales with RF. With RF = 3 it requires 2; with RF = 5 it requires 3. A quorum cannot be split into two completely disjoint groups within the same replica set.

It is this intersection property that makes `QUORUM` a popular choice for systems balancing availability with the ability to read data that was just successfully written.

### `ALL`: Waiting for Every Replica

`ALL` waits for all replicas configured for the partition. With RF = 3, all three ACKs are required; with RF = 5, all five ACKs are required. This makes a single operation's outcome sensitive to even one slow or failed replica.

`ALL` does not turn an operation into a multi-row transaction, does not eliminate concurrent update conflicts, and does not turn Cassandra into a globally locking system. It only governs the request's **response threshold**.

## 5. Data Freshness Depends on Both Write CL and Read CL

Choosing the **write** CL and **read** CL are two separate decisions. Looking only at the read CL is not enough to conclude whether the result is guaranteed to be fresh.

Let:

- `N`: total number of replicas of **the same partition within the replica set under consideration**;
- `W`: number of replicas that acknowledged a **successful write**;
- `R`: number of replicas required to respond for the **read**.

If:

\[
R + W > N
\]

then the two replica sets must **intersect at least at one replica**.

Example with **RF = 3**:

| Write CL (`W`) | Read CL (`R`) | `R + W` | Guaranteed overlap between the two sets? |
| --- | --- | ---: | --- |
| `ONE` (1) | `ONE` (1) | 2 | No. |
| `ONE` (1) | `QUORUM` (2) | 3 | No. |
| `QUORUM` (2) | `QUORUM` (2) | 4 | **Yes.** |
| `ALL` (3) | `ONE` (1) | 4 | **Yes.** |
| `ONE` (1) | `ALL` (3) | 4 | **Yes.** |
| `TWO` (2) | `THREE` (3) | 5 | **Yes.** |

Assume the write succeeded at `QUORUM`, there are no concurrent writes, and both operations use the same replica set. When reading at `QUORUM`, at least one responding replica is in the set that ACKed the write. Cassandra can use that version during reconciliation to return the result. This is the foundation of the **tunable consistency** model.

**However, overlap does not equate to general linearizability.** You must also consider concurrent write contention, timestamps, node clocks, last-write-wins reconciliation rules, failures mid-operation, and replica scope. Normal quorum reads and writes do not automatically create atomic multi-partition transactions. When you need `INSERT ... IF NOT EXISTS` or `UPDATE ... IF` to handle conditional contention, explore **lightweight transactions (LWT)** powered by Paxos.

### Illustrating Two Replica Sets

```text
RF = 3:     R1     R2     R3

W = 2:      [x]    [x]     .
R = 2:       .     [x]    [x]
                    ^
           Overlap at R2

W = 1:      [x]     .      .
R = 2:       .     [x]    [x]

           No overlap; read may be stale
```

If you read at `QUORUM` when the previous write only succeeded at `ONE`, you **cannot** argue "I read from a majority" to conclude you are guaranteed to see the new value.

## 6. How Are Replicas Counted with Multiple Datacenters?

Suppose a keyspace uses `NetworkTopologyStrategy`:

```text
dc1: RF = 3      A1  A2  A3
dc2: RF = 3      B1  B2  B3

Total replicas per partition: N = 6
```

The five CLs in this lesson do **not enforce separate local ACK counts per DC**:

| CL | Threshold for Global RF 6 | Notes |
| --- | ---: | --- |
| `ONE` | **1** | Any single eligible replica; does not require a local-DC replica. |
| `TWO` | **2** | Two replicas; does not require each DC to contribute an ACK. |
| `THREE` | **3** | Three replicas; all three could come from one DC. |
| `QUORUM` | **4** | Majority of **all six**; when each DC has three replicas, requires responses from both DCs. |
| `ALL` | **6** | Requires every replica in both DCs. |

Note: Cassandra may **prefer replicas close to the coordinator** to improve latency, but `ONE`, `TWO`, and `THREE` do **not** guarantee responses belong to the local DC. A `QUORUM` operation in a 3 + 3 setup typically waits for at least one replica in the remote DC, tying latency and availability to cross-region connectivity.

If an application runs across multiple datacenters and only wants to wait for replicas in the coordinator's datacenter, look at **`LOCAL_ONE`** and **`LOCAL_QUORUM`**. For instance, with RF = 3 in `dc1`, `LOCAL_QUORUM` needs 2 ACKs **in dc1**, whereas global `QUORUM` on a 3 + 3 topology needs 4 ACKs **across both DCs**.

Do not mechanically apply `R + W > N` when writing at `LOCAL_QUORUM` in `dc1` and reading at `LOCAL_QUORUM` in `dc2`: the two ACK groups can lie in **disjoint** DCs. Likewise, `EACH_QUORUM` is a write-specific level requiring quorum in each DC, distinct from global `QUORUM`.

## 7. Practice with CQL and `cqlsh`

Example creating a keyspace on a **single-datacenter** cluster whose actual DC name is `dc1` with at least three eligible nodes:

```sql
CREATE KEYSPACE IF NOT EXISTS consistency_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS consistency_lab.profile_by_user (
  user_id uuid PRIMARY KEY,
  display_name text,
  city text
);
```

This table is queried by partition key `user_id`. RF = 3 is set on the **keyspace**, while CL is chosen **when executing statements**.

In `cqlsh`, use the `CONSISTENCY` command to set the default CL for statements executed **subsequently in that shell session**:

```sql
CONSISTENCY ONE;

INSERT INTO consistency_lab.profile_by_user
    (user_id, display_name, city)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'An', 'Ha Noi'
);

CONSISTENCY TWO;

SELECT user_id, display_name, city
FROM consistency_lab.profile_by_user
WHERE user_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY QUORUM;

UPDATE consistency_lab.profile_by_user
SET city = 'Da Nang'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY ALL;

SELECT user_id, display_name, city
FROM consistency_lab.profile_by_user
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

With RF = 3:

- `INSERT` at `ONE`: requires one replica ACK.
- `SELECT` at `TWO`: requires two replica responses; because the prior write was only `ONE`, a non-overlapping case can occur.
- `UPDATE` at `QUORUM`: requires two replica ACKs.
- `SELECT` at `ALL`: requires all three replicas to respond; will fail if one replica cannot answer in time.

`CONSISTENCY` is a **`cqlsh` command**, not SQL syntax attached directly to `INSERT` or `SELECT`. In Java applications, the driver sets CL per statement or execution profile.

You can enable `TRACING ON;` in `cqlsh` while testing a few small queries to observe execution, though you should not assume the number of trace events or internal requests always equals the CL's minimum ACK count. Tracing adds overhead to the cluster; use a test environment when simulating node failures.

## 8. Selecting CL per Request with Java Driver 4.x

The Apache Cassandra Java Driver allows setting CL on each `Statement`. The example below uses an initialized `CqlSession` configured with the local datacenter and connected to the cluster:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.util.UUID;

public final class ProfileQueries {
    public static void updateCity(
            CqlSession session, UUID userId, String newCity) {
        SimpleStatement update = SimpleStatement.newInstance(
                "UPDATE consistency_lab.profile_by_user " +
                "SET city = ? WHERE user_id = ?",
                newCity, userId)
            .setConsistencyLevel(DefaultConsistencyLevel.QUORUM);

        session.execute(update); // RF=3 in one DC: requires 2 ACKs.
    }

    public static String findCity(CqlSession session, UUID userId) {
        SimpleStatement select = SimpleStatement.newInstance(
                "SELECT city FROM consistency_lab.profile_by_user " +
                "WHERE user_id = ?",
                userId)
            .setConsistencyLevel(DefaultConsistencyLevel.TWO);

        Row row = session.execute(select).one();
        return row == null ? null : row.getString("city");
    }
}
```

In production applications, you should use **reusable `PreparedStatement`s** to reduce statement preparation overhead, and configure timeouts/retries appropriate to the business flow. Enums in this group include `DefaultConsistencyLevel.ONE`, `TWO`, `THREE`, `QUORUM`, and `ALL`. Changing CL on a statement **does not modify the keyspace, table, or RF**.

The example above illustrates how to set CL, not a guarantee of "always read fresh immediately": when you want an intersection condition to read the latest write, evaluate write CL, read CL, and RF together. With RF = 3, `W=QUORUM=2` and `R=TWO=2` satisfy `R+W>3` if both operations target the same replica set and concurrent update assumptions hold.

## 9. What Happens When There Are Not Enough ACKs?

**Not meeting the CL response threshold** differs from **no replica processing the operation**. For example, writing at `ALL` with RF = 3:

1. `R1` receives the mutation and returns an ACK.
2. `R2` receives the mutation and returns an ACK.
3. `R3` does not respond before the deadline.
4. The client receives a timeout error because `ALL` demands three ACKs, **even though `R1` and `R2` may have already written successfully**.

Distinguish the common error groups:

| Error | Typical Meaning | Handling Approach |
| --- | --- | --- |
| `Unavailable` | Coordinator determines available replicas are fewer than the CL threshold. | Check RF, replica health, datacenter, and network. |
| `WriteTimeout` | Did not receive enough write acknowledgments within the time limit. | Do not assume the mutation was not applied; consider safe retries. |
| `ReadTimeout` | Did not receive enough read responses in time, or failed to complete the read path before deadline. | Check latency, load, replicas, timeouts, and CL. |
| `ReadFailure` / `WriteFailure` | Replicas reported errors during processing, preventing the operation from achieving CL. | Investigate logs, nodes, resources, and query path. |

If a client automatically re-writes after a timeout, issues can arise with **counters**, non-idempotent updates, or "send notification after write" logic. Design operations to be idempotent whenever possible, distinguish availability errors from timeouts, and bound your retries.

Background mechanisms like **hinted handoff** and **repair** help replicas catch up or reconcile data; **compaction** manages SSTables/tombstones. They **do not replace** choosing the right CL and do not guarantee that a failed replica will be instantaneously synchronized upon recovery.

## 10. Which Level Should You Choose in Real Scenarios?

| Scenario | Commonly Considered Level | Rationale and Limitations |
| --- | --- | --- |
| Query tolerant of stale data, needs low latency | `ONE` for reads and/or writes | Must accept eventual consistency and have a way to handle stale data. |
| RF = 3, needs balance of availability and read/write freshness | `QUORUM` for both directions | 2 ACKs each way; overlaps across the same replica set. |
| RF = 3, requires write success on all three replicas | `ALL` on write | Fails easily if one replica is slow/down; high response cost. |
| RF = 5, requires at least three replicas only | `THREE` | 3/5 is also quorum when RF = 5, but does not adapt automatically if RF changes. |
| Multi-DC, app wants to minimize cross-region latency | Consider `LOCAL_ONE`, `LOCAL_QUORUM` | The five global levels in this lesson do not express per-DC counting constraints. |
| Needs conditional updates under contention | Consider LWT with `SERIAL`/`LOCAL_SERIAL` | Raising CL usually does not substitute for atomic compare-and-set. |

These scenarios are **design starting points**, not universal rules. Verify latency, real workloads, topology, replica failures, and business expectations before deciding.

## 11. Exercises and Answers

### Exercise 1 — Threshold Calculation

A keyspace has RF = 5 in a single datacenter. Writes use `THREE`, and reads use `QUORUM`.

**Question:** How many responses does each operation require? Are the write ACK set and read response set guaranteed to overlap?

**Answer:** `THREE` requires 3 ACKs; `QUORUM` with RF = 5 also requires `floor(5/2)+1=3` responses. `3+3>5`, so the two sets must overlap if using the same replica set and the write was confirmed successful.

### Exercise 2 — One Unresponsive Replica

A DC has RF = 3. `R1` and `R2` respond normally; `R3` is disconnected.

**Question:** Can `ONE`, `TWO`, `THREE`, `QUORUM`, and `ALL` still succeed?

**Answer:** `ONE`, `TWO`, and `QUORUM` **can** succeed; `THREE` and `ALL` do not have enough responses. This applies to both normal reads and writes based on CL thresholds.

### Exercise 3 — Changing RF

A system is running RF = 3 with read CL `TWO`. After updating replication appropriately to RF = 5, the development team leaves the read CL unchanged.

**Question:** Is `TWO` still equivalent to `QUORUM`?

**Answer:** No. `TWO` still requires exactly 2 responses, whereas `QUORUM` at RF = 5 requires 3. Changing topology/RF requires reviewing consistency assumptions.

### Exercise 4 — Across Two Datacenters

`dc1` has RF = 3, and `dc2` has RF = 3. A write uses `QUORUM`.

**Question:** How many ACKs are required in total? Are 3 ACKs from `dc1` alone enough?

**Answer:** It requires `floor(6/2)+1=4` ACKs across all replicas. Only 3 ACKs from `dc1` are **not enough**; there must be at least one ACK from `dc2` in this topology.

### Exercise 5 — Write Timeout

Writing at `ALL` with RF = 3, two replicas have ACKed, and the third replica times out.

**Question:** Can we be sure the data was not written?

**Answer:** No. The write **failed to meet CL**, so the client receives an error, yet two replicas may have already applied the mutation. Retries must rely on idempotency and application policy.

## 12. Key Points to Remember

1. `ONE`, `TWO`, and `THREE` are **absolute ACK counts**: 1, 2, 3.
2. `QUORUM` is a **majority**: `floor(RF/2)+1` (or a majority of the total RF across DCs for global `QUORUM`).
3. `ALL` means **every replica of the partition**, making it highly sensitive to slow or failed replicas.
4. Write CL and read CL must be designed as **a pair**. The condition `R+W>N` describes replica set overlap within the appropriate scope, but does not by itself guarantee transactions/linearizability.
5. Choosing a higher CL can improve visibility of confirmed data, but may increase latency and failure rates; **CL does not replace replication, repair, partition-key table design, or application error handling**.

When building a Java service backed by Cassandra, start by asking: *"Given the current RF and datacenters, how many ACKs does a write need and how many responses does a read need to meet the business requirement?"* From there, choose `ONE`, `TWO`, `THREE`, `QUORUM`, or `ALL` for **each query**, and validate with replica failure scenarios and realistic load testing.
