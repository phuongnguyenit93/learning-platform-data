# Optimistic Locking Using Version or Status Columns

## Lesson Objectives

In Apache Cassandra, multiple clients can read and then write to the same row nearly simultaneously. If an application reads a value, computes a change in Java, and writes back with a regular `UPDATE`, one client can **overwrite another client's result**. **Optimistic locking** solves this by permitting the update only when the data still satisfies the condition the client read or expected.

In the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this technique ties into how Cassandra distributes data by **partition key**, the **wide-column** model, query-driven table design, replication, and read/write consistency levels. The core mechanism is **Lightweight Transactions (LWT)** via CQL `IF` syntax, using a consensus protocol to process conditional updates.

After this lesson, you will be able to:

- Recognize **lost update** bugs and explain why reading/writing at `QUORUM` does not automatically prevent them.
- Choose between optimistic locking via a **`version` column** or a **`status` column** depending on the business invariant.
- Write `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, and `UPDATE ... IF status = ?`.
- Properly handle `[applied] = false`, contention, timeouts, and retries from Java.
- Understand LWT limitations when data spans multiple partitions, under heavy contention, and when exactly-once guarantees are needed.

## 1. Why Is Optimistic Locking Necessary?

Suppose an order currently has `status = 'PENDING'` and `version = 7`. Two processes both read this row:

1. Process A wants to confirm payment: transition to `PAID`.
2. Process B wants to cancel the order: transition to `CANCELLED`.
3. Both send regular `UPDATE`s based on the stale read.

Without a protective condition, both write commands can be accepted by Cassandra, and the final state depends on how the writes are reconciled. One business update can be overwritten by the other.

~~~sql
-- UNSAFE if multiple processes can update the same order.
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

UPDATE orders_by_id
SET status = 'CANCELLED'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Reading and writing at `LOCAL_QUORUM` or `QUORUM` does not turn those two statements into an **atomic read-check-write operation**. Consistency level governs replica acknowledgments; it does not replace concurrency control between clients.

Optimistic locking follows the principle:

> Read record → prepare change → write **only if** version/state still matches expectation → check result.

No application lock needs to be held for the duration of processing. If another process changed the protected value in the meantime, the conditional operation **is not applied**, and the client must decide how to handle the conflict.

## 2. Designing the Table Around the Query

Suppose a Java application looks up an order by `order_id` and transitions that order's state. Query-driven table design:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    version int,
    amount_minor bigint,
    updated_at timestamp
);
~~~

Here `order_id` is the **partition key**. All reads, checks, and state transitions in this example target a single partition. `version` is a regular application-managed integer; it is **not a `counter` type**.

Initialize an order with LWT:

~~~sql
INSERT INTO orders_by_id (order_id, status, version, amount_minor)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'PENDING',
    0,
    125000
)
IF NOT EXISTS;
~~~

If no matching row exists yet, Cassandra creates it and returns `[applied] = true`. If the row already exists, the statement does not overwrite existing values and returns `[applied] = false`. This safely prevents two processes from independently initializing a record at the same primary key.

~~~sql
SELECT status, version, amount_minor
FROM orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

An initial state created with a regular `INSERT` can also exist, but `IF NOT EXISTS` is particularly useful when creation must guard against races. Do not assume `UPDATE ... IF version = 0` will auto-create a missing row: the condition must be satisfied by existing data.

## 3. Optimistic Locking with a Version Column

Suppose a client just read `version = 0`, `status = 'PENDING'` and wants to transition to `PAID`. The client computes `newVersion = oldVersion + 1` and sends:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    version = 1,
    updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF version = 0;
~~~

LWT evaluates the condition and applies the update as a conditional operation on the target partition:

| Current Value at Check Time | Result | Meaning |
| --- | --- | --- |
| `version = 0` | `[applied] = true` | Update accepted; version becomes 1. |
| `version = 1` | `[applied] = false` | Another update incremented version, so the client's read is stale. |
| Row does not exist | `[applied] = false` | Cannot assume a version 0 record existed. |

**Cassandra does not auto-increment `int version` via `version = version + 1` like a counter.** The application must compute the new value and send both the new value and the condition matching the old value. The `IF version = oldVersion` clause is what stops an update from overwriting a modified record.

When every row-modifying operation increments `version`, this column protects multiple fields simultaneously: `status`, `amount_minor`, and other attributes. Forgetting even one regular write path that fails to update `version` breaks the optimistic locking convention. All components writing to the table must follow the same rule.

### Two Clients Competing on One Version

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Cassandra
    A->>C: SELECT (version = 7, status = PENDING)
    B->>C: SELECT (version = 7, status = PENDING)
    A->>C: UPDATE status = PAID, version = 8 IF version = 7
    C-->>A: [applied] = true
    B->>C: UPDATE status = CANCELLED, version = 8 IF version = 7
    C-->>B: [applied] = false
    B->>C: SELECT current state
    C-->>B: version = 8, status = PAID
~~~

This is **conflict detection**, not an automatic queue executing both changes one after another. Client B must check business rules before deciding whether to retry against the new version.

## 4. Optimistic Locking with a Status Column

When business logic only permits a specific state transition, conditioning on `status` can be clearer:

~~~sql
UPDATE orders_by_id
SET status = 'CANCELLED',
    version = 1
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF status = 'PENDING';
~~~

This succeeds only when the current status is `PENDING`. If already `PAID`, the client cannot cancel thanks to this condition. This is a **conditional state transition** model: the transition depends on the starting state.

However, **checking only `status`** has limitations:

- Two clients can both edit other fields without changing `status`; `IF status = 'PENDING'` can succeed sequentially for both, overwriting data.
- If a status can revert to an earlier value—such as `PENDING → REVIEW → PENDING`—a client holding a read from before the cycle still sees `PENDING` and can execute an obsolete action. This is the **ABA** problem.
- Conditioning on `status` works well when the transition itself is the invariant to protect and every allowed target state is strictly defined.

When you need to block any intervening change between read and write, check **both `version` and `status`**:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    version = 1,
    updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF version = 0 AND status = 'PENDING';
~~~

This condition checks two things: the row has not been edited since the read (`version`) **and** it is still in a state eligible for payment (`status`). When multiple flows update state, combining both expresses the invariant more clearly.

### Choosing Version vs. Status?

| Criterion | `IF version = ?` | `IF status = ?` | Combined |
| --- | --- | --- | --- |
| Primary goal | Detect any update that increments version | Guard a specific state transition | Prevent stale reads and enforce transition rules |
| Non-status fields modified | Detected if that write increments version | Not automatically detected | Detected if that write increments version |
| Prevents state-return anomalies (ABA) | Yes, when version increases monotonically | No | Yes |
| Application convention required | Every write path must update version | Every transition must obey state rules | Both conventions |

Note: `IF EXISTS` only checks whether the row exists. It does **not** check old version or state, so `IF EXISTS` alone is insufficient to prevent lost updates.

## 5. What Does LWT Do Under the Hood?

A statement with `IF` is a **Lightweight Transaction**: Cassandra coordinates a Paxos consensus round (and required phases) to decide the condition and apply the update. Competing operations in the same protected scope cannot both win if both require an old `version` value.

You must distinguish two consistency level settings on an LWT operation:

| Type | Examples | Role |
| --- | --- | --- |
| Consistency for regular read/write phase | `LOCAL_QUORUM`, `QUORUM` | Sets replica acknowledgment level for the regular write phase. |
| **Serial consistency** for condition/consensus phase | `LOCAL_SERIAL`, `SERIAL` | Sets the LWT consensus scope. |

`LOCAL_SERIAL` suits deployments where reads/writes happen within **one datacenter**. If the same partition can receive conditional updates from **multiple datacenters**, evaluate `SERIAL` and the replication model; do not assume independent local coordination in multiple DCs provides the same global protection. Check topology and client routing policies before choosing consistency.

LWT carries **multi-round communication overhead**, typically higher than regular `UPDATE`s. A primary key contested by many clients will see many `[applied] = false` outcomes, higher latency, and lower throughput. Use LWT only when concurrency conditions are genuinely required; for approximate metrics or high-throughput view counts, use a different design.

LWT protects conditional operations within an appropriate partition scope, **not arbitrary ACID transactions across multiple partitions**. A regular `SELECT` before LWT can read stale data; update correctness comes from `IF` when Cassandra processes it, not from assuming the earlier read locked the row.

Replication, compaction, and repair are all vital to operating Cassandra, but they **do not replace** `IF` clauses for resolving conflicts between concurrent business updates. Repair also cannot know which client attempted to transition an order based on a stale decision.

## 6. Handling Results and Errors Properly

When sending `UPDATE ... IF ...`, the application must distinguish three cases:

1. **`[applied] = true`:** Cassandra confirmed the condition held and the update was applied. Proceed along the success path.
2. **`[applied] = false`:** Cassandra confirmed the condition no longer holds. This is a **valid business conflict**; re-read state/version, return a concurrency error, or recompute the operation if business rules permit.
3. **Timeout, connection loss, indeterminate error:** The client **cannot conclude** whether the operation succeeded or failed. Reconcile current state and request IDs if exact status is required.

In `cqlsh`, a conditional update returns the `[applied]` column:

~~~text
 [applied]
-----------
      True
~~~

When the condition fails, the system may also return current values for the conditioned columns. Do not rely on always receiving every column in a failed response; run a `SELECT` by primary key when you need the full latest record.

### Retrying Under Contention

A typical handling flow:

~~~text
Read (version = 7, status = PENDING)
    |
    v
Check if state transition is allowed?
    |
    v
UPDATE ... SET version = 8 ... IF version = 7 AND status = 'PENDING'
    |
    +-- [applied] = true  --> Done
    |
    +-- [applied] = false --> Re-read, evaluate business rules
    |
    +-- timeout ----------> Outcome unknown, reconcile before retrying
~~~

After `[applied] = false`, **never blindly bump the version and retry forever**. For example, an already-paid order must not automatically be cancelled just because the cancellation worker fetched the new version. Retrying is valid only when the new state still permits the action; bound retry attempts, use backoff, and track contention.

Resending **the exact same statement** with `IF version = 7` after the first attempt actually succeeded can return `[applied] = false` because `version` is now 8. In that case `false` does not immediately tell you whether this client or another client made the change. If the business requires knowing whether *a specific request* was processed, store `operation_id` alongside the record in the LWT and design post-timeout reconciliation rules. A single `last_operation_id` column identifies only the most recent stored operation; it does not replace a durable idempotency log if subsequent operations follow.

**LWT does not automatically guarantee end-to-end exactly-once across systems outside Cassandra**, such as calling payment gateways, sending emails, emitting events, or updating multiple partitions. In particular, avoid calling external systems before confirming you won the state transition and having a recovery plan if the external system fails.

## 7. Java Example with Cassandra Driver 4.x

Assume `CqlSession` is configured with a valid keyspace and datacenter. The code below reads the current version, checks business rules, and sends a conditional CAS (`compare-and-set`):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class OrderStateService {
    private final CqlSession session;
    private final PreparedStatement loadOrder;
    private final PreparedStatement payIfPending;

    public OrderStateService(CqlSession session) {
        this.session = session;
        this.loadOrder = session.prepare(
            "SELECT status, version FROM orders_by_id WHERE order_id = ?");
        this.payIfPending = session.prepare(
            "UPDATE orders_by_id SET status = ?, version = ? " +
            "WHERE order_id = ? IF status = ? AND version = ?");
    }

    // true: this operation won CAS; false: row missing or conflict.
    // Timeouts propagate for the caller to handle as an indeterminate outcome.
    public boolean markPaid(UUID orderId) {
        Row current = session.execute(loadOrder.bind(orderId)).one();
        if (current == null || !"PENDING".equals(current.getString("status"))) {
            return false;
        }

        int expectedVersion = current.getInt("version");
        int nextVersion = Math.incrementExact(expectedVersion);

        BoundStatement cas = payIfPending.bind(
                "PAID", nextVersion, orderId, "PENDING", expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
            .setIdempotence(false);

        Row result = session.execute(cas).one();
        if (result == null) {
            throw new IllegalStateException("LWT returned no result");
        }
        return result.getBoolean("[applied]");
    }
}
~~~

Explanation:

- `loadOrder` fetches a snapshot to decide what action to take. No lock is held between `SELECT` and `UPDATE`.
- `payIfPending` sends **both the expected status and the expected version**. If anyone modified the row in between, the guard detects the conflict.
- `Math.incrementExact` prevents silent 32-bit integer overflow; large systems should define a version lifecycle policy or choose a sufficiently wide type.
- `LOCAL_QUORUM` and `LOCAL_SERIAL` are **illustrative settings** that must be adjusted for actual replication/topology.
- `setIdempotence(false)` makes explicit that the caller should not blindly replay on indeterminate outcomes. Even though a repeated CAS avoids overwriting due to its condition, the retry outcome can differ and must be interpreted by business logic.
- On `false`, the caller should re-read and return a conflict error, or retry only after verifying the new state is still valid.

In production, `PreparedStatement`s should be prepared once and reused; monitor timeouts, unapplied CAS counts, latency, and partition load. Avoid synchronized retry storms that amplify contention.

## 8. Common Design Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| `SELECT` then `UPDATE` without `IF` | Lost updates between concurrent clients | Use `IF version = ?` or appropriate state conditions |
| Using only `IF EXISTS` | Fails to detect that the record was modified | Compare old values in `IF` |
| Having `version` while some write paths skip updating it | CAS misses changes | Enforce the version convention across all writes |
| Using `counter` as a version | Counters are unsuitable for conditional LWTs | Use regular `int` or `bigint` and send the new value from app |
| Infinite retries after `[applied] = false` | Violates business rules and spikes load | Re-read, validate state transition, cap retries |
| Treating timeouts as definite failures | Risks processing a request twice | Reconcile using state and business identifiers |
| Using LWT on every write | Adds round trips and cuts throughput | Guard only invariants that require CAS |
| Assuming LWT protects arbitrary multi-partition sets | Violates atomicity scope | Model partitions around the invariant or use another coordinator |

## 9. Hands-On Practice

**Exercise 1 — Successful state transition.** Create `orders_by_id`, run `INSERT ... IF NOT EXISTS` from section 2, then run `UPDATE ... IF version = 0 AND status = 'PENDING'` from section 4. Verify `[applied] = true` and `SELECT` shows `status = 'PAID'`, `version = 1`.

**Exercise 2 — Detecting a stale version.** Resend the exact same `UPDATE` conditioned on `version = 0`. Observe `[applied] = false`; the row does not revert to the old version. Explain why `false` tells you **the condition at evaluation time**, not sole proof of the full submission history.

**Exercise 3 — Comparing version and status.** Create a new order. Have one client update a business field while keeping `status = 'PENDING'`; have another client run `UPDATE ... IF status = 'PENDING'`. Explain why the second operation can still be accepted. Redesign both write flows to increment and check `version`.

**Exercise 4 — Two concurrent Java clients.** Both read the same version; one tries to mark `PAID` while the other tries `CANCELLED`. Use a combined condition so only one valid transition succeeds. Count `[applied]` outcomes, read the final state, and document how the app handles the conflict.

**Exercise 5 — Failures and replication.** Simulate a client timeout after sending an LWT. Write a reconciliation procedure before retrying, and explain when `SERIAL` is needed instead of `LOCAL_SERIAL` if updates can arrive from multiple datacenters. Explain clearly why running repair cannot resolve the business decision of whether to retry.

## Summary

**Optimistic locking in Cassandra uses LWT and CQL `IF` conditions to check data at the exact moment of update.** `version` detects any change to the record; `status` guards valid state transitions; combining both expresses business rules more precisely. Always handle `[applied] = true`, `[applied] = false`, and timeouts separately, while choosing partition keys and serial consistency to match your real contention scope.
