# Distinguishing Regular Writes from Conditional Writes in Apache Cassandra

## 1. The Problem: Two Write Operations That Look Similar but Have Different Guarantees

Apache Cassandra is a distributed *wide-column* database: data is routed by **partition key** to replicas, and applications typically design tables around the queries they must serve. In a system where multiple applications and nodes write concurrently, the key question is: **does the write merely need to store a new value, or must it check the prior value before writing?**

- **Regular write**: `INSERT`, `UPDATE`, or `DELETE` without an `IF` clause. Cassandra accepts the mutation and distributes it to replicas according to the write consistency level. There is no cluster-wide consensus step verifying that a business condition holds.
- **Conditional write / lightweight transaction (LWT)**: `INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...`, `UPDATE ... IF EXISTS`, or `DELETE ... IF ...`. Cassandra uses the **Paxos** consensus protocol to evaluate the condition and decide whether to apply the mutation.

Both write paths can update the same table, yet they differ in **latency, throughput, conflict resolution, and the kinds of business invariants they can protect**. This lesson aims to help you choose the right write path, understand the execution order, and apply the right consistency levels from CQL or Java applications.

### A Typical Scenario

Two concurrent requests try to register the same username `minh`:

1. Request A wants to bind `minh` to account A.
2. Request B wants to bind `minh` to account B.
3. If both simply run a regular `INSERT` on the same primary key, both can receive a successful write response; the final value is determined by cell-level timestamp reconciliation rules.
4. If both run `INSERT ... IF NOT EXISTS` directly on key `minh`, only one request can win the right to create the record under the agreed LWT sequence; the other receives `[applied] = false`.

**Key takeaway:** write consistency level `QUORUM` specifies how many replicas acknowledge, but **it does not automatically turn** a regular write into a *compare-and-set* (CAS) operation.

## 2. What Steps Does a Regular Write Take?

Example simple state-lookup table:

~~~cql
CREATE TABLE order_state_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);

UPDATE order_state_by_id
SET state = 'PROCESSING', updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

A typical flow:

1. **Client sends mutation** to a node acting as **coordinator**.
2. Coordinator uses the **partition key** (here `order_id`) to identify the responsible replicas.
3. Replicas receive the mutation and execute the storage write path, typically involving the **commit log** and **memtable**; SSTables are created later upon flush.
4. Coordinator returns success once enough acknowledgments arrive per the request's **write consistency level**, such as `ONE` or `LOCAL_QUORUM`.

Cassandra does not need to read the row's current state before step 3 to decide whether the write is permitted. That is why `UPDATE` can behave as an **upsert**: a missing row can still be created.

When multiple mutations conflict on the same cell, Cassandra reconciles them using write metadata, where the **mutation timestamp** plays the deciding role via *last-write-wins*; never infer that a request sent later or acknowledged later will always provide the final value. Individual columns can also be reconciled independently, so you should not picture the entire row as always having a single winner.

**Strengths:** fewer message round trips than LWT; well suited for high write volume, event data, and state updates that do not require checking prior values.

**Limitations:** a request succeeding at `LOCAL_QUORUM` does not prove that no other request already owned the username before the update, nor that the version still matches what the client read earlier.

## 3. What Steps Does a Conditional Write Take?

Example:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid,
    claimed_at timestamp
);

INSERT INTO username_owner (username, user_id, claimed_at)
VALUES (
    'minh',
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
    toTimestamp(now())
)
IF NOT EXISTS;
~~~

The `IF NOT EXISTS` clause changes the nature of the operation: the mutation is accepted only if primary key `username = 'minh'` has no existing record in the Paxos-agreed state. The CQL result includes the special column `[applied]`:

~~~text
[applied]
-----------
True
~~~

If a competing request already created that key first, the operation returns `[applied] = false`; depending on the statement and Cassandra version, the failed result may include the existing column values for the client to inspect.

### Paxos: Separating Consensus from Storing the Mutation

LWT uses Paxos to serialize conditional operations over the same protected data scope. Conceptually, the flow looks like this:

1. **Prepare / promise:** coordinator initiates a Paxos proposal; participating replicas promise not to accept older proposals.
2. **Determine state to evaluate:** coordinator gathers Paxos state and current values, resolving any in-progress proposal if needed.
3. **Evaluate condition:** if `IF` is false, the conditional mutation is not applied; if true, proceed to propose the new value.
4. **Propose / accept:** Paxos replicas vote to accept the proposal.
5. **Commit / apply:** the chosen value enters the write path, and the coordinator returns the corresponding outcome.

This is a conceptual learning model; round-trip optimizations vary by version and runtime case. Do not use a fixed network hop count to predict every LWT.

~~~mermaid
flowchart TD
    A["Client sends mutation"] --> B{"Does statement have IF?"}
    B -->|No| C["Coordinator forwards mutation to replicas"]
    C --> D["Replicas write commit log / memtable"]
    D --> E["Enough ACKs for write CL → success"]
    B -->|Yes| F["Paxos prepare / promise"]
    F --> G["Agree on state to evaluate"]
    G --> H{"IF condition true?"}
    H -->|No| I["Return [applied] = false"]
    H -->|Yes| J["Paxos propose / accept"]
    J --> K["Commit mutation per write CL"]
    K --> L["Return [applied] = true"]
~~~

LWT provides **linearizable *compare-and-set* for conditional operations sharing the same key/partition coordinated via Paxos**. It does not provide an arbitrary ACID transaction across multiple partitions, multiple tables, or the entire system. Nor should you assume that regular writes to the same data automatically join the Paxos ordering: a write path without `IF` can break the invariant the application thinks LWT is protecting.

## 4. Direct Comparison of the Two Write Paths

| Aspect | Regular Write | Conditional Write (LWT) |
|---|---|---|
| Common syntax | `INSERT`, `UPDATE`, `DELETE` | `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, `DELETE ... IF ...` |
| Condition based on prior value | Not checked | Evaluated via Paxos before deciding |
| Consensus | No Paxos for this mutation | Uses Paxos |
| Success response | Enough ACKs per write CL | Condition applied (`[applied] = true`) and write path completed per config |
| Contention on same key | Writes may all succeed; data reconciled per Cassandra rules | Competing CAS operations are ordered; a condition can fail |
| Network cost | Generally lower | More exchanges; higher latency and contention sensitivity |
| Use cases | Logging, non-CAS state, overwritable updates | Claiming key ownership, version checks, conditional state transitions |
| Protection scope | No business predicate | Predicate over data modeled within the appropriate partition/key scope |

**Do not confuse:** raising write CL from `ONE` to `QUORUM` or `ALL` does not add an `IF` clause. The two concepts answer different questions: *how many replicas acknowledge?* versus *is the mutation allowed to happen only if the condition still holds?*

## 5. Example 1: Keeping Usernames Unique with `IF NOT EXISTS`

Suppose the table is designed so the name to protect is the partition key itself:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid,
    claimed_at timestamp
);
~~~

Two clients concurrently send:

~~~cql
-- Client A
INSERT INTO username_owner (username, user_id, claimed_at)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, toTimestamp(now()))
IF NOT EXISTS;

-- Client B
INSERT INTO username_owner (username, user_id, claimed_at)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb, toTimestamp(now()))
IF NOT EXISTS;
~~~

If both execute as LWTs on the same key with no regular writer intervening, only one request succeeds in creating the username; the other sees that the condition no longer holds. The application must inspect **`[applied]`**, rather than assuming success just because CQL did not throw an exception.

Contrast this with:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa);

INSERT INTO username_owner (username, user_id)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb);
~~~

The two regular statements perform no ownership check whatsoever. That the final stored row holds only one `user_id` **does not** mean either user received a "duplicate username" error.

### Only Choosing the Right Key Protects What Needs Protecting

If the table is defined with `PRIMARY KEY (user_id)` and `username` is just a regular column, `IF NOT EXISTS` on each `user_id` **does not stop** two different users from picking the same username. To enforce username uniqueness, you need a shared point of contention—such as the `username_owner` table keyed by `username` above.

Likewise, an LWT on one table does not atomically apply related changes in other tables. If the registration flow also writes to `user_by_id`, the application must design sequencing, retries, and compensation/reconciliation when a later step fails.

## 6. Example 2: Version-Based State Updates (Optimistic Concurrency)

Scenario: two workers both read an invoice at `version = 7`, and both want to update it. A regular "read-then-write" approach lets one worker overwrite the other's update.

~~~cql
CREATE TABLE invoice_state_by_id (
    invoice_id uuid PRIMARY KEY,
    state text,
    version int,
    updated_at timestamp
);

INSERT INTO invoice_state_by_id (invoice_id, state, version)
VALUES (22222222-2222-2222-2222-222222222222, 'PENDING', 7)
IF NOT EXISTS;
~~~

Once the client reads `version = 7`, it computes the new version and puts the expected version into the condition:

~~~cql
UPDATE invoice_state_by_id
SET state = 'PAID',
    version = 8,
    updated_at = toTimestamp(now())
WHERE invoice_id = 22222222-2222-2222-2222-222222222222
IF version = 7;
~~~

- Client A receives `[applied] = true`: the data matched the condition when LWT won, so the mutation was accepted.
- Client B, also starting from `version = 7`, receives `[applied] = false` after A's update: B must re-read, recompute, and decide whether to retry or return a conflict to the business layer.

Do not write "SELECT version then UPDATE without `IF`" expecting `QUORUM` to resolve the contention. Also do not write SQL-style `version = version + 1`: for an `int` column here, **the client computes the new version ahead of time and checks the old version via CAS**.

For pure existence checks, Cassandra also provides `UPDATE ... IF EXISTS` and `DELETE ... IF EXISTS`. Choose `IF version = ?` whenever current state/version is the invariant to protect.

## 7. Two Consistency Level Groups in LWT

Cassandra provides two related settings that serve different stages:

| Setting | Meaning | Examples |
|---|---|---|
| **Regular / write consistency** | Number of replicas required to acknowledge the mutation write/commit phase | `ONE`, `LOCAL_QUORUM`, `QUORUM` |
| **Serial consistency** | Scope of replicas participating in the LWT Paxos consensus phase | `SERIAL`, `LOCAL_SERIAL` |

With a replication factor of 3 in one datacenter, `LOCAL_QUORUM` typically requires 2 replicas in that datacenter to acknowledge. Yet those acknowledgments **do not replace the Paxos step**.

- **`SERIAL`**: coordinates the serial/Paxos phase across the relevant datacenters; suitable when cluster-wide conditional consensus is needed for the topology.
- **`LOCAL_SERIAL`**: coordinates the serial/Paxos phase only within the local datacenter; typically reduces cross-datacenter chatter. If multiple datacenters can contend on the same key concurrently, do not assume `LOCAL_SERIAL` guarantees a single cluster-wide winner.

Choose the consistency pair to match topology and requirements. In a single datacenter with RF=3, a common pair in Java is **regular = `LOCAL_QUORUM`**, **serial = `LOCAL_SERIAL`**. In multi-datacenter deployments requiring a cluster-wide invariant, evaluate `SERIAL` and the corresponding replication/commit strategy rather than blindly copying single-DC settings.

Do not use `SERIAL` or `LOCAL_SERIAL` as write CL substitutes for `QUORUM`: they apply to the **serial phase** of LWT. Reading with serial consistency can also help complete an in-flight Paxos round, but it does not turn regular mutations into CAS.

## 8. Calling LWT from Java and Handling Responses

The example uses **DataStax Java Driver 4.x**. Assume `CqlSession session` is connected to the appropriate keyspace and table `username_owner` already exists:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.util.UUID;

// Inside the username registration function; session is managed by application lifecycle.
String username = "minh";
UUID userId = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

SimpleStatement claim = SimpleStatement.builder(
        "INSERT INTO username_owner (username, user_id, claimed_at) " +
        "VALUES (?, ?, toTimestamp(now())) IF NOT EXISTS")
    .addPositionalValues(username, userId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

Row outcome = session.execute(claim).one();
if (outcome == null) {
    throw new IllegalStateException("No CAS result returned");
}

if (outcome.getBoolean("[applied]")) {
    // Username was successfully claimed by this request.
} else {
    // Username already exists: report conflict or verify retry for the same userId.
}
~~~

This snippet illustrates the consistency pair for a single datacenter. In multi-datacenter deployments, the application must choose serial consistency based on key-protection requirements across the full topology.

### Three Outcome Types to Distinguish

1. **`[applied] = true`**: the conditional comparison succeeded and the write was applied per the request's protocol.
2. **`[applied] = false`**: the condition did not hold; this is a **valid business outcome**, not automatically a system error. You can inspect who owns the key.
3. **Timeout, connection drop, or indeterminate exception**: the operation's outcome may be **unknown to the client**. The request may have been accepted on the server even though the response was lost. Never infer `applied = false` from a timeout.

When claiming a username, retry using the **same `userId`** and check the actual stored value if a retry returns `false`: if the owner equals the exact `userId` of the prior request, the app can treat it as already succeeded under business idempotency rules; if it belongs to another user, return a conflict. Never generate a fresh random user ID on every retry, and never trigger external side effects twice just because the client missed a response.

For version-based updates, retrying after a timeout requires reading/reconciling state and version before deciding how to proceed. When `IF version = 7` no longer holds, either the earlier attempt succeeded or another operation changed the row; use a `request_id` or clear business marker to tell them apart when needed.

## 9. When Should You Use Which Path?

**Prefer regular writes** when the business semantics allow upserts, newer values replace older ones, or Cassandra's reconciliation strategy is acceptable—for example, logging by unique key, append-only events (with non-colliding generated keys), telemetry updates, and recomputable cache state.

**Use LWT** when an operation depends on **current state** and multiple clients can contend: granting a unique name to only one user, transitioning `PENDING → PAID` only while still `PENDING`, or applying an update only if the version is unchanged. Always identify **which partition key is the point of contention**, as that is what enables the condition to protect the invariant.

Common design mistakes:

- **Overusing LWT for every write:** Paxos adds round trips and operational overhead; a contended hot partition can severely degrade throughput and increase latency.
- **Thinking `QUORUM` replaces `IF`:** quorum confirms replicas, not business predicates.
- **Using `IF NOT EXISTS` on the wrong key:** two values that must be unique under business rules can both succeed if they land in different partitions.
- **Mixing unconditional writes with LWT writes on protected data:** regular mutations bypass CAS ordering; ensure all write paths for the same invariant follow the same protocol.
- **Treating `LOCAL_SERIAL` as cluster-wide multi-DC protection:** explicitly decide the contention scope of requests.
- **Grouping multiple partitions into an imaginary "transaction":** LWT is not an arbitrary multi-partition ACID transaction; choose an appropriate data model or business coordination protocol.
- **Treating timeouts as definite failures:** use controlled retries and reconciliation to avoid duplicate side effects.

### Checklist Before Choosing LWT

1. Which invariant must hold: *does not exist*, *is in state X*, or *version equals N*?
2. Is that invariant represented at **a single consistent key/partition**?
3. Do all relevant update paths enforce the conditional rule?
4. Is the topology multi-datacenter, and does cross-datacenter contention occur?
5. Does the application properly handle `[applied] = false`, unknown-outcome timeouts, and idempotent retries?
6. Can the write rate and contention level tolerate Paxos latency and throughput?

## 10. Self-Check Exercises

**Scenario A.** Two producers concurrently run `UPDATE sensor_state SET value = ...` on one partition at `LOCAL_QUORUM`. Can both receive a success ACK? **Yes.** There is no CAS; the final cell value is reconciled by timestamp and Cassandra's corresponding rules.

**Scenario B.** Two users concurrently claim `username = 'minh'` in a table with `PRIMARY KEY (username)`, both using `INSERT ... IF NOT EXISTS` with appropriate serial consistency. Can both receive `[applied] = true` for the same key within a valid Paxos ordering? **No.** Once one request creates the key, the other's condition no longer holds.

**Scenario C.** An application uses `IF version = 7`, while a legacy service still runs an `UPDATE` without `IF` on the same row. Is the version invariant still guaranteed to be protected? **No.** The legacy service bypasses the conditional path.

**Scenario D.** The Java driver throws a timeout during `IF NOT EXISTS`. Should you immediately notify "registration failed" and generate a new UUID to retry? **No.** The state is uncertain; retry with the same identity and reconcile owner/version.

## 11. Summary

The regular write path optimizes for **distributing and persisting mutations** per the write consistency level; it has no awareness of business preconditions. The conditional write path with `IF` uses **Paxos** to decide *whether a mutation may execute while current state satisfies the condition*, at the cost of higher latency and coordination overhead. Modeling tables around the point of contention, distinguishing **write CL** from **serial CL**, and handling both `[applied]` and timeouts properly are the three prerequisites for using LWT safely in Cassandra/Java applications.
