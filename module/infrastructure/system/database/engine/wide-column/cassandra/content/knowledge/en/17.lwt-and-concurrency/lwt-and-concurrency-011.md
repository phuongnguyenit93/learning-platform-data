# Mixing Regular Writes with LWT and Its Impact on Correctness in Apache Cassandra

## 1. Why Is This a Correctness Problem, Not Just a Performance Problem?

In Apache Cassandra—a distributed **wide-column** database—applications typically design tables around queries, use **partition keys** to route data to replicas, and choose **consistency levels** for reads and writes. In the **LWT and Concurrency** chapter, an easily overlooked risk is: **some applications use statements with `IF` to protect state, while other applications still write directly to that exact same data**.

The two operation types serve different purposes:

- **Regular write:** `INSERT`, `UPDATE`, or `DELETE` without `IF`. The coordinator sends the mutation to replicas and waits for enough acknowledgments per the write consistency level; no predicate on current values has to hold.
- **Conditional write (lightweight transaction, LWT):** statements such as `INSERT ... IF NOT EXISTS`, `UPDATE ... IF status = 'OPEN'`, or `DELETE ... IF version = 3`. The **Paxos** phase orchestrates a *compare-and-set* (CAS) decision; the client receives `[applied] = true` or `false`.

When all operations contending on an invariant go through LWT and are properly routed and configured for consensus, Cassandra can order the relevant CAS operations. However, **a regular write does not join the CAS ordering merely by targeting the same table, same key, same consistency level, or running at the same time**.

> Design rule: for LWT to enforce a business rule, **every write path capable of modifying data on which that rule depends must obey the rule**. Adding `IF` in only one place in the application is not enough.

## 2. Understanding the Difference Between the Two Write Paths Accurately

A regular mutation only needs enough replica acknowledgments. If two clients update the same cell, Cassandra reconciles values by mutation timestamp and related rules, rather than guaranteeing *whichever got ACKed last wins*. Cells can also be reconciled individually: `status` can come from one mutation while `version` comes from another.

With LWT, the coordinator participates in the Paxos protocol to determine whether the `IF` condition holds and accept or reject the conditional mutation. **Serial consistency** determines the consensus scope; **regular write consistency** governs commit/write acknowledgments. LWT provides *linearizable* ordering for compliant conditional operations over the same protected scope—**not arbitrary ACID transactions across multiple partitions**.

Key point to remember: **Paxos does not prevent a client from sending a regular mutation to the same row while an LWT is executing**. A regular mutation is not forced to check `IF` or participate in Paxos decisions. Therefore, you cannot deduce correctness of the full write history from LWT results alone.

| Property | LWT on Protected Data | Regular Write on Same Data |
|---|---|---|
| Evaluates current predicate before accepting? | Yes, via `IF` and Paxos | No |
| Returns `[applied]`? | Yes | No |
| Joins ordering of CAS operations on the same key? | Yes, when configured/scoped properly | No |
| Can be ACKed while violating another LWT's rule? | If condition fails, `[applied] = false` | Yes |
| Does raising write CL to `QUORUM` add CAS? | Unnecessary since `IF` is already present | No |
| Same-cell values stored/reconciled on replicas? | Still subject to Cassandra storage mechanics | Still subject to Cassandra storage mechanics |

## 3. Counterexample: A Correct LWT Still Leads to Wrong State

Suppose a reservation service must maintain the invariant:

**When `status = 'HELD'` and `version = 1`, there must be an owner; cancellations may run only under a policy that checks state/version.**

The table is designed around lookup by `reservation_id`:

~~~cql
CREATE TABLE reservation_by_id (
    reservation_id uuid PRIMARY KEY,
    status text,
    version int,
    holder_id uuid,
    updated_at timestamp
);
~~~

Initial data is seeded **before contending requests arrive**:

~~~cql
INSERT INTO reservation_by_id
    (reservation_id, status, version)
VALUES
    (11111111-1111-1111-1111-111111111111, 'OPEN', 0);
~~~

### 3.1. New Service Uses LWT

A user attempts to hold the slot:

~~~cql
UPDATE reservation_by_id
SET status = 'HELD',
    version = 1,
    holder_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

If it receives `[applied] = true`, LWT accepted the state transition because the condition held at its consensus point.

### 3.2. Legacy Service Still Uses Regular Writes

An old job or cancellation API still executes:

~~~cql
UPDATE reservation_by_id
SET status = 'CANCELLED'
WHERE reservation_id = 11111111-1111-1111-1111-111111111111;
~~~

Without `IF`, this statement checks neither `status` nor `version`; a high write CL does not add the missing condition.

### 3.3. What Can Happen?

Suppose the hold LWT succeeds and the cancel mutation has a winning timestamp on the **`status` cell**. The resulting stored row can look like:

| Column | Value |
|---|---|
| `status` | `CANCELLED` |
| `version` | `1` |
| `holder_id` | `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` |

The reservation client received `[applied] = true`; the cancellation service also received a write success ACK. Yet the combined final column values can violate the reservation workflow rule that the team believed `IF` protected.

If a legacy service also writes `version = 0` directly, a winning timestamp can roll `version` back to 0, causing a later CAS to evaluate against a state that does not reflect business progress. You cannot use request arrival order at coordinators or ACK order to prove safety because Cassandra reconciles mutations by its own rules.

~~~mermaid
sequenceDiagram
    participant A as New Service
    participant C as Cassandra
    participant B as Legacy Service
    Note over A,B: Initial: OPEN, version=0
    A->>C: UPDATE ... IF status='OPEN' AND version=0
    C-->>A: [applied] = true
    B->>C: UPDATE status='CANCELLED' (no IF)
    C-->>B: ACK per write CL
    Note over A,B: Can end with CANCELLED, version=1, holder=A
~~~

This diagram shows **one possible execution schedule**, not a guarantee that this exact result always appears. Which statement wins on each cell depends on mutations, timestamps, and specific distributed conditions.

## 4. Misconceptions That Lead to Concurrency Bugs

### Misconception 1: "LWT locks the row, so regular writes have to wait"

LWT does not provide an application-wide lock that every Cassandra writer is forced to obey. It runs Paxos consensus among replicas for conditional operations. Regular writes do not queue behind an LWT until it finishes.

**Consequence:** you can receive `[applied] = true` while a regular mutation still alters the protected data immediately afterward or races while the LWT is in flight.

### Misconception 2: "If both statements use `QUORUM`, they cannot conflict"

`QUORUM` (or `LOCAL_QUORUM` in the right topology) answers **how many replicas must acknowledge**. It does not answer **whether a state change is permitted given the old state**. Both requests can reach quorum without ever checking the same predicate.

**Consequence:** raising the consistency level may improve observability/convergence properties, but does not substitute for CAS.

### Misconception 3: "`SERIAL` or `LOCAL_SERIAL` automatically guards all partition access"

Serial consistency applies to the **Paxos phase** of LWTs and certain serial reads. A mutation without `IF` does not become a conditional mutation just because the application uses LWT elsewhere.

**Consequence:** a system that properly sets `SERIAL` for reservation claims while still letting an admin API update the same field directly can have its invariant broken.

### Misconception 4: "If replicas eventually converge, the data will be valid"

Repair, read repair (depending on version and config), hinted handoff, compaction, and anti-entropy mechanisms handle **replica and storage consistency**. They have no idea that `status='CANCELLED'` paired with the current `holder_id` is invalid under business rules.

**Consequence:** the system can converge on **the exact same state across replicas, yet be wrong from a business standpoint**.

### Misconception 5: "CQL `BATCH` solves all races"

A batch does not force other writers on the same partition to join Paxos. Batching also does not create a transaction with arbitrary isolation and conditions across multiple partitions. To protect an invariant, you must identify the single-partition scope, valid conditional statements, and **every participating writer**.

## 5. When Is Mixing Two Write Paths Truly Dangerous?

Not every mix of regular mutations and LWTs on the same **table** is a bug. You must determine whether they touch **the same invariant**.

| Scenario | Assessment |
|---|---|
| LWT checks `version` and updates `status`; legacy service updates `status` without `IF` | Dangerous: bypasses state-transition rules |
| LWT claims `username`; import job writes `username_owner` directly | Dangerous: can hijack ownership or overwrite |
| LWT updates `status` and `version`; job modifies `version` directly | Dangerous: invalidates version checks |
| LWT protects `status`; a command writes only independent data unrelated to conditions and invariants | Potentially acceptable, but true independence must be proven |
| Regular writes to different partitions sharing no business constraint | Usually do not conflict directly with CAS on the partition under study |
| Placing a unique field in two partitions and running separate LWTs per partition | Insufficient to guarantee global uniqueness |

**Audit rule:** ask *"Can a regular mutation alter any field in a way that invalidates an `IF` condition, a post-CAS action, or a state-transition rule?"* If yes, the two write paths cannot be considered safe when running concurrently.

### Uniqueness Scenario: `IF NOT EXISTS` Still Broken

Table:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid
);
~~~

New signup API uses:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Yet an import task uses:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb);
~~~

The import task skips `IF NOT EXISTS`. If its mutation wins on the `user_id` cell, the final owner may no longer be the user whom the API just told registration succeeded. The invariant *"once a name is granted, nobody else can take it under the same API rules"* failed because one write path bypassed the protocol.

Do not use `IF NOT EXISTS` on a `user_id` key expecting uniqueness of `username`: two different users land in two different partitions. **The partition key must represent the exact entity under contention.**

## 6. Protecting the Invariant Under a Single Consistent Write Protocol

### 6.1. Enforce Transition Rules at the Write Point

When holding a reservation, use a condition reflecting both status and version:

~~~cql
UPDATE reservation_by_id
SET status = 'HELD',
    version = 1,
    holder_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

When cancelling, the new service must also obey the agreed rule—for instance, **only cancel an unclaimed slot**:

~~~cql
UPDATE reservation_by_id
SET status = 'CANCELLED',
    version = 1
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

When both calls start from `OPEN, version=0` and both participate in Paxos with the proper scope, **only one transition can apply successfully**; the other receives `[applied] = false` and must handle the conflict.

You do not always have to check both status and version: which predicate suffices depends on domain semantics. Still, having some write paths use `IF` while others update protected fields without `IF` cannot deliver that guarantee.

### 6.2. Align Every Writer Touching the Invariant

Inventory every actor capable of editing protected columns: public APIs, scheduled jobs, backfills, import/export, ops scripts, message consumers, legacy services, and admin tools. Then:

1. **Document the invariant explicitly:** e.g., a slot has at most one holder and may only transition `OPEN → HELD` or `OPEN → CANCELLED`.
2. **Establish the single consensus point:** use one partition keyed by `reservation_id`, or a table keyed by the business key requiring uniqueness such as `username`.
3. **Route all mutations affecting the invariant through appropriate `IF` CQL:** including maintenance tasks and admin portals.
4. **Prevent backdoor writes via convention and architecture controls:** centralize writes in a shared DAO/service, restrict write permissions for jobs that do not need them, and audit CQL statements modifying critical fields.
5. **Handle conflicts properly:** `[applied] = false` means a condition failed, not a replica error; read/reconcile data and return a business error or recompute the operation.
6. **Monitor the migration:** detect non-`IF` mutations touching protected fields, audit application logs, and reconcile invalid states.

For fields **truly independent** of predicates and invariants, regular writes can be a reasonable choice to avoid Paxos overhead; the prerequisite is proving independence rather than merely occupying a different column.

### 6.3. Do Not Assume Partial Rollouts Are Immediately Safe

Migrating from regular writes to LWT must account for the phase where two application versions run side by side:

~~~text
Before migration:     A regular write, B regular write
Partial rollout:      A uses LWT, B still regular write  <-- danger window
After migration:      A uses LWT, B uses LWT
~~~

During the middle window, the system can still violate the invariant. A controlled migration routes all writers through a unified update gateway or pauses write flows touching the invariant, drains in-flight requests, reconciles existing data, and resumes traffic under the new protocol. Exact sequencing depends on system architecture and availability requirements.

**Data already corrupted prior to migration does not heal itself merely because new requests use LWT.** Audit and resolve duplicate owners, invalid states, and skewed versions.

## 7. Java Application: Placing Conditions on the Exact Write Statement

The example uses **DataStax Java Driver 4.x**, with `CqlSession session` connected to the keyspace and `reservation_by_id` already created. Every service updating status should call a single API requiring `expectedVersion` and `expectedStatus`; never allow callers to execute arbitrary `UPDATE ... SET status = ? WHERE ...` when it affects the invariant.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

// Prepare once and reuse the PreparedStatement across the service.
PreparedStatement hold = session.prepare(
    "UPDATE reservation_by_id " +
    "SET status = ?, version = ?, holder_id = ? " +
    "WHERE reservation_id = ? " +
    "IF status = ? AND version = ?"
);

UUID reservationId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");
UUID userId =
    UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
int expectedVersion = 0;

BoundStatement statement = hold.bind(
        "HELD", expectedVersion + 1, userId,
        reservationId, "OPEN", expectedVersion)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

Row result = session.execute(statement).one();
if (result == null) {
    throw new IllegalStateException("No CAS response returned");
}

if (result.getBoolean("[applied]")) {
    // Success: reservation hold accepted.
} else {
    // Conflict: read current state and handle per business rules.
}
~~~

This configuration illustrates **a single datacenter with suitable replication**, typically RF=3. `LOCAL_QUORUM` is the write consistency; `LOCAL_SERIAL` is the serial consistency for Paxos. When multiple datacenters can contend on keys concurrently, design serial consistency scope (considering `SERIAL`) and replication strategy per system requirements. **Proper consistency settings cannot save a writer that omits `IF`.**

Never build a "faster" sibling API using regular writes to change `status` under high load. If LWT latency becomes a bottleneck, examine contention levels, partitioning, and business requirements instead of silently dropping guards.

### 7.1. Three Outcomes Applications Must Distinguish

| Response from Cassandra | Meaning to Client | Handling |
|---|---|---|
| `[applied] = true` | Condition accepted; LWT mutation completed per request protocol | Process business success |
| `[applied] = false` | Condition did not hold | Read/reconcile state, return conflict, or recompute operation |
| Timeout / connection error | Uncertain whether result was applied | Reconcile, controlled retry, preserve request identity |

A timeout does not mean the condition failed. If resending the operation after a timeout, distinguish **a retry of the same business request** from a different update command—for instance, by storing an `operation_id` or transition markers sufficient to detect whether the prior execution already succeeded; never charge twice, send duplicate notifications, or emit duplicate events merely because an ACK was missed.

### 7.2. Read-Then-Write Without `IF` Still Races

This pseudocode **does not** replace CAS:

~~~java
// UNSAFE when multiple writers exist:
Row current = session.execute(readState).one();
if ("OPEN".equals(current.getString("status"))) {
    session.execute(
        SimpleStatement.newInstance(
            "UPDATE reservation_by_id SET status = 'HELD' " +
            "WHERE reservation_id = ?", reservationId));
}
~~~

Another writer can modify the row **after `SELECT` and before `UPDATE`**. Even if both `SELECT` and `UPDATE` use `QUORUM`, no atomic condition requires the value at write time to still be `OPEN`. Replace it with a single `UPDATE ... IF status = 'OPEN'` (and `version` if needed).

## 8. Impact of Data Modeling and Multi-Table Operations

In Cassandra, the same business entity is often denormalized into multiple query-specific tables. For instance, a registration service might maintain:

- `username_owner` keyed by `username` to claim unique names.
- `user_by_id` keyed by `user_id` to look up user profiles.

LWT on `username_owner` protects only the condition on that designed contention point. It does not turn the follow-up write to `user_by_id` into a global transaction. If writing the profile fails after claiming the name, you need retries, a completion workflow, or proper reconciliation/compensation.

A dangerous mixed-write-path bug occurs when a job edits `username_owner` using regular updates merely to "sync" from `user_by_id`. That job can overwrite CAS results from the registration API. Explicitly define **which table/partition is the source of truth for ownership** and who is allowed to modify it.

Distinguish two layers of correctness:

1. **Concurrency correctness at the decision point:** every change affecting the predicate obeys CAS.
2. **Cross-table and multi-step workflow correctness:** retries/idempotency and reconciliation ensure all tables update along a valid progression.

LWT solves the first layer when used consistently; the second layer still requires application design.

## 9. Observing, Testing, and Remediating Systems with Mixed Write Paths

### Warning Signs to Investigate

- Two requests both receive "claim succeeded," or one request succeeds yet the owner unexpectedly changes afterward.
- `status` and `version` do not correspond to the same valid state transition.
- `[applied] = false` rate spikes abnormally, especially after introducing a new worker/batch job.
- Issues surface after a partial deployment, running a backfill, or activating a legacy job.
- Manual data fixes cause a valid LWT executed right before to lose effect.

Never rely solely on these signals to conclude root cause: they can also stem from data modeling flaws, app versions, timestamps, retries, or other operations. Inspect the **actual CQL queries** and every producer writing to the same key.

### Intentional Concurrency Testing

Build an integration test on an appropriate Cassandra environment using the same `reservation_id`:

1. Initialize state to `OPEN, version=0`.
2. Have N clients concurrently send two conflicting CAS updates (`HELD` and `CANCELLED`) with the same condition.
3. Verify that across trials contending cleanly on the same initial state, **at most one** mutation from `OPEN, version=0` receives `[applied] = true`.
4. Replace one client with an `UPDATE ... SET status = ...` lacking `IF`; observe that this write returns no `[applied]` column and can produce states outside application rules.
5. Re-run with simulated timeouts/network failures; verify the app does not falsely report "definite failure" or repeat side effects.

Tests do not prove every possible production interleaving, yet they catch missing conditions early. Another key safeguard is scanning the codebase for every `INSERT`/`UPDATE`/`DELETE` targeting critical state tables and putting them through design review.

### When Invalid Data Already Exists

First identify and stop or fix **the writer bypassing the rule**. Then build a remediation procedure based on the business source of truth: reconcile owner, state, version, operation IDs, and related steps. If you repair via direct regular updates on protected fields while LWT traffic is still running, the repair process itself can reintroduce bugs. Use coordinated repair workflows for hot data or freeze relevant mutations during remediation.

Repair and compaction serve replica storage and synchronization; they **do not replace** business-logic data remediation.

## 10. Scenario Exercises

**Exercise 1.** A system has a table keyed by `username`. The new API calls `INSERT ... IF NOT EXISTS`, while an import script runs regular `INSERT` on the same usernames. Can stable uniqueness/ownership be guaranteed?

**Answer:** No. Because the import script ignores CAS, it can overwrite `user_id`; every path modifying ownership must follow the same protocol.

**Exercise 2.** Service A uses `UPDATE ... IF version = 4`, Service B uses a regular `UPDATE`, and both use `QUORUM`. Does setting `QUORUM` on both fix the race?

**Answer:** No. Quorum sets only the ACK threshold; it does not add compare-and-set semantics to B's statement.

**Exercise 3.** An analytics job updates an isolated `last_seen_at` column that is never part of predicates, affects no invariants, and is not used by services to decide state transitions. Must every `last_seen_at` update use LWT?

**Answer:** Not necessarily. Regular writes can be used if you verify the column is genuinely independent of the protected rules and other queries will not misinterpret it as part of an atomic state snapshot.

**Exercise 4.** After all services switch to LWT, some rows still have `version=0` despite `status='HELD'`. Do current LWTs automatically repair those old rows?

**Answer:** No. Identify the historical root cause and reconcile the data; new CAS operations do not self-heal pre-existing invalid states.

## 11. Summary of Operational Rules

- **Guard the right invariant:** use `IF` at the contention point represented by an appropriate key/partition.
- **Guard every entry point:** all producers capable of modifying invariant fields must use the same protocol; never mix regular writes into those competing paths.
- **Do not confuse consistency with conditions:** `ONE`, `LOCAL_QUORUM`, and `QUORUM` govern ACKs; `SERIAL` and `LOCAL_SERIAL` govern the Paxos phase and do not force regular writes into CAS.
- **Handle conflicts and timeouts:** `[applied] = false` means the condition failed; timeouts can leave indeterminate results requiring controlled retries/reconciliation.
- **Close the full workflow:** if data is denormalized across tables or systems, add idempotency, compensation, and reconciliation strategies.

**Conclusion:** LWT is not a universal lock wrapped around an entire Cassandra table. Conditional guarantees hold only when all write paths capable of breaking the same invariant are designed together. Even a single writer still issuing regular mutations against protected data can let **both the LWT and the regular write report success while driving the system into an invalid state**.
