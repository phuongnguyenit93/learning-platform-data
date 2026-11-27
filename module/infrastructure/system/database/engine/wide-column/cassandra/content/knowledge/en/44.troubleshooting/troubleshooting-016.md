# LWT Contention, Conflicts, and Operations With Unknown Outcomes in Apache Cassandra

> **Chapter:** Troubleshooting  
> **Scope:** Apache Cassandra 4.1/5.x, CQL, replication/consistency levels, Java Driver 4.x, and diagnosing Paxos-based **lightweight transactions (LWT)**. Examples use synthetic data and dedicated lab environments. Never induce contention, stop nodes, change timeouts, or mutate data in production without explicit authorization and an approved runbook.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain why LWTs are required when concurrent clients compete to update the **same logical entity/partition**, instead of relying on ordinary read-then-write sequences.
2. Distinguish **normal writes**, **conditional inserts/updates/deletes**, and **serial-consistency reads**.
3. Describe Paxos conceptually: prepare/promise, propose/accept, commit/learn; and explain why additional message rounds raise latency.
4. Configure and interpret both **normal consistency level** and **serial consistency level** on a conditional write.
5. Interpret `[applied]=true`, `[applied]=false`, and explain why `false` indicates a **condition conflict** rather than a default Cassandra failure.
6. Diagnose **LWT contention** caused by hot partitions, concurrent writers, CAS retry loops, misaligned timeout budgets, client concurrency, or replica GC/disk/network slowdowns.
7. Separate **KNOWN_APPLIED**, **KNOWN_NOT_APPLIED**, and **UNKNOWN_OUTCOME** states and distinguish them from read/write availability issues.
8. Explain why `CASWriteUnknownException`, `WriteTimeoutException`, or `DriverTimeoutException` **never permits assuming** whether the mutation applied or rolled back.
9. Design **idempotency keys, operation IDs, revision fencing, and state reconciliation** to prevent duplicate orders or double charges on retries.
10. Write CQL and Java Driver 4.x code using `INSERT ... IF NOT EXISTS`, `UPDATE ... IF revision=?`, `ResultSet.wasApplied()`, normal/serial CL, and outcome-aware logging.
11. Analyze `CASRead`/`CASWrite`, `ConditionNotMet`, `ContentionHistogram`, `UnfinishedCommit`, timeouts, GC, disk, and driver retries to pinpoint root causes.
12. Build incident investigation runbooks, verification tests, LWT workload guardrails, and clear criteria for retrying, halting, or manual reconciliation.

**Module context (`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`):** Cassandra partitions data by partition key/token and uses replication factors (RF) and consistency levels (CL) to coordinate reads/writes across natural replicas. LWT layers consensus onto **conditional state transitions** within its supported scope, yet does not transform Cassandra into a global ACID SQL database. Java engineers must combine sound CQL modeling, Paxos semantics, Java Driver policies, query-first table design, network failure handling, and replica/repair operations to safeguard data correctness.

## 2. The Problem: Two Clients Check-Then-Write Together

Suppose an account has `status=PENDING` and only one client should move it to `CONFIRMED`:

~~~text
Time             Client A                 Client B
----------------------------------------------------------------
T0               SELECT status=PENDING   SELECT status=PENDING
T1               Decides to write        Decides to write
T2               UPDATE CONFIRMED        UPDATE CANCELLED
T3               ACK                     ACK

Final state depends on timestamp / last-write-wins, not on
an atomically confirmed "conditional winner".
~~~

Two normal reads followed by two normal writes **do not** compose an atomic compare-and-set (CAS). Normal Cassandra writes rely on timestamps and LWW conflict resolution across replicas; even when both clients read at `QUORUM` and write at `QUORUM`, the gap between **read → Java check → write** remains a classic TOCTOU (*time-of-check/time-of-use*) race.

Whenever domain rules require **updating only if the current state still satisfies a condition**, use conditional CQL:

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED', revision = 2
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Cassandra evaluates the condition inside LWT/Paxos to serialize competing attempts. One client receives `[applied]=true` and the other receives `[applied]=false`—yet if a client **times out before receiving a definitive reply**, the outcome remains ambiguous. That ambiguity sits at the center of this lesson.

### 2.1. When Are LWTs Appropriate?

| Requirement | Suitable for LWT? | Caveats to know |
|---|---|---|
| Reserving a unique username in a properly keyed lookup table | Generally yes | Uniqueness holds strictly for that modeled guard key/scope |
| State transitions guarded by `IF revision = n` | Yes | Heavy contention on a single partition drives up latency |
| Creating a record only if the key does not exist yet | `INSERT ... IF NOT EXISTS` | Post-timeout retries require tracking operation IDs |
| Changing state when `IF status = 'PENDING'` | Yes | Condition must target the exact row/partition |
| Non-competing append-only event log inserts | Usually unnecessary | Normal writes are faster with fewer round-trips |
| Atomic bank transfer across two partitions or two microservices | **Insufficient** | No global multi-partition or cross-service ACID transactions |
| Cluster-wide sequential ID generation via one hot partition | Technically possible, usually a severe hotspot | Throughput serializes on contended Paxos |
| End-to-end exactly-once across Kafka + Cassandra + HTTP API | LWT alone is **insufficient** | Requires idempotency/inbox/outbox/sagas and reconciliation |

**Rule:** LWT protects a **specific conditional invariant**, not a switch to "turn on stronger consistency for all `INSERT`s".

## 3. How LWT Works Conceptually

### 3.1. Consensus Beyond Simple Quorum Writes

A standard mutation at `LOCAL_QUORUM` ships to replicas and waits for ACKs, performing no serialized ballot to enforce **"value still equals `n` immediately before committing"**.

LWT runs **Paxos**. Conceptual flow:

~~~text
                  Client A: UPDATE IF revision=1
                                |
                           Coordinator
                                |
           1. PREPARE / PROMISE (ballot, existing state)
                           /    |    \
                         R1    R2    R3
                           \    |    /
                                |
              2. Evaluate condition / pick proposal
                                |
              3. PROPOSE / ACCEPT (agreed value)
                           /    |    \
                         R1    R2    R3
                           \    |    /
                                |
              4. COMMIT / LEARN (normal CL phase)
                                |
                          [applied] result
~~~

This is an **abstract pedagogical model**, not an exact wire trace for every version. Cassandra 4.1+ revamped Paxos (including fast paths), so actual round-trip counts vary by release, contention levels, and recovery state. Never hardcode "every LWT takes exactly four round trips" when budgeting latency. See [Cassandra guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html) and [Cassandra 4.1 Paxos improvements](https://cassandra.apache.org/_/blog/Cassandra-4.1-is-here.html).

### 3.2. Paxos Ballots/Proposals Are Not CQL Cell Timestamps

- **Ballot/proposal:** lets competing proposers agree on a single winning value/operation in a Paxos round.
- **CQL cell timestamp:** governs last-write-wins resolution for normal writes and storage ordering.
- **Application revision/version:** business column used in CAS predicates to guard transitions and reveal state changes.
- **Operation ID:** unique identifier of **one logical business intent**, used to reconcile timeouts.

Never substitute Java timestamps as Paxos "ballot IDs", and never expect `USING TIMESTAMP` to overpower LWT ordering rules. CQL enforces specific restrictions on conditional statements; follow the version-exact CQL contract instead of mixing custom timestamps into LWTs.

### 3.3. Linearizability Applies Strictly Within Supported Scope

LWT provides **linearizable compare-and-set** for mutations following the conditional protocol within its target partition/replica scope. It does **not** mean:

- Another code path can fire normal blind `UPDATE`s at the same row while expecting LWT serial semantics to hold.
- LWTs on Partition A and Partition B form one atomic cross-partition transaction.
- Any immediate `ONE` read guarantees observing a freshly committed LWT regardless of **normal CL**.
- Cassandra delivers cross-system transactions spanning brokers, caches, search indexes, or payment gateways.

**Design prerequisite:** every writer mutating state under a shared invariant must obey the **same LWT/versioning protocol** and partition schema. One unguarded blind writer can break the invariant for everyone.

## 4. Which CQL Statements Trigger LWT?

| CQL statement | Behavior | Uses LWT? |
|---|---|---|
| `INSERT INTO ... VALUES (...)` | Standard upsert | No |
| `INSERT INTO ... VALUES (...) IF NOT EXISTS` | Insert only if key absent | Yes |
| `UPDATE ... SET ... WHERE PK=...` | Standard upsert | No |
| `UPDATE ... SET ... WHERE PK=... IF revision=...` | Conditional CAS update | Yes |
| `UPDATE ... SET ... WHERE PK=... IF EXISTS` | Update only if row exists | Yes |
| `DELETE FROM ... WHERE PK=...` | Standard delete | No |
| `DELETE ... WHERE PK=... IF status=...` | Conditional delete | Yes |
| `BEGIN BATCH ... APPLY BATCH` | Standard logged/unlogged batch | Not Paxos by default |
| CQL-supported conditional batch on one partition | Multiple conditional mutations | Yes, tightly scoped and costly |

**You must bind the full primary key in `WHERE`** per conditional DML rules. You cannot execute something like `UPDATE table SET ... WHERE arbitrary_secondary_index=... IF ...` to lock every row of a tenant. Cassandra is a query-driven wide-column engine, not a row-locking SQL engine.

### 4.1. `INSERT IF NOT EXISTS` and the "Create Once" Invariant

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  11111111-1111-1111-1111-111111111111,
  'PENDING', 1,
  22222222-2222-2222-2222-222222222222
)
IF NOT EXISTS;
~~~

If the row already exists, Cassandra returns the **conditional result** `[applied]=false` (often alongside current column values depending on query/version). This is typically an **expected business conflict**, not a Down node or disk fault.

### 4.2. `UPDATE IF revision = n` and Optimistic Concurrency

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED',
    revision = 2,
    last_op_id = 33333333-3333-3333-3333-333333333333
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

If another writer already bumped revision to 2:

~~~text
[applied] | revision | ...
----------+----------+-----
    False |        2 | ...
~~~

Exact columns returned upon conditional failure **depend on statement form and server release**. Never hardcode logic assuming every table column always returns in the failure row; whenever full state is needed to classify conflicts, issue a **full-PK `SELECT`** at an appropriate CL and inspect version/operation IDs.

### 4.3. `IF EXISTS` Is Not a Long-Lived Distributed Mutex

~~~sql
UPDATE lwt_lab.account_state
SET status = 'SUSPENDED'
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF EXISTS;
~~~

This checks only that **the row existed at the CAS evaluation point**—it never locks the row while Java spends 5 minutes calling downstream services. Once Cassandra ACKs, LWT holds zero cross-service lock afterward.

### 4.4. Conditional Batches Carry Strict Boundaries

A conditional batch can guard multiple conditional updates **inside the same partition** per CQL rules; never assume `BEGIN BATCH` gives global multi-partition ACID transactions. If reserving uniqueness in a lookup keyspace and creating a record in **another partition**, build explicit saga, ownership, rollback, and reconciliation protocols.

## 5. Two Consistency Levels in LWT: Serial vs. Normal

Conditional writes involve two distinct consistency levels:

- **Serial consistency level (SCL):** Paxos consensus scope deciding the winning proposal/condition—typically `SERIAL` or `LOCAL_SERIAL`.
- **Normal consistency level (NCL/WCL):** ACK requirement for the **learn/commit phase** governing subsequent normal-read visibility—commonly `QUORUM` or `LOCAL_QUORUM` when visibility matters.

`cqlsh` separates them into two distinct settings:

~~~text
cqlsh> CONSISTENCY LOCAL_QUORUM;
cqlsh> SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

Setting normal CL never alters serial CL, and vice versa. In Java Driver 4.x, set **both properties** explicitly on conditional statements.

### 5.1. Choosing CLs by RF and DC Layout

Suppose `NetworkTopologyStrategy` configures RF=3 in `dc1` and RF=3 in `dc2`:

| Goal | Example serial CL | Example normal CL | Crucial caveat |
|---|---|---|---|
| Serialization scoped strictly within local DC | `LOCAL_SERIAL` | `LOCAL_QUORUM` | Local DC scope only; does not guarantee global serial order |
| Serialization spanning participating DCs | `SERIAL` | `QUORUM` (per read contract) | Cross-WAN latency/availability, replica intersection |
| Reading consistent with preceding CAS | Serial read when required | Read CL must match commit visibility | Never assume `ONE` immediately observes new LWT commits |
| Single-node RF=1 lab | `SERIAL` | `ONE` | Syntax/logic learning only; proves nothing about multi-node quorum |

**Major hazard:** Two writers in `dc1` and `dc2` hitting the same logical key with `LOCAL_SERIAL` independently **never yield global linearizability**. When invariants require global order across DCs, align all writers on a tested global serialization strategy and coordinator topology—accounting for WAN latency and failover.

### 5.2. Normal CL Shapes Post-CAS Read Visibility

`cqlsh` docs distinguish the serial phase from the commit/learn phase. Committing a conditional write at NCL=`QUORUM` sets up subsequent matching `QUORUM` reads to see that commit. Using weak normal CLs (especially `ANY` where supported) gives no guarantee a subsequent stronger normal read immediately sees the write; a **serial read** may be required to finalize pending Paxos state.

Never plug `W+R>RF` blindly from ordinary quorum math and assume every Paxos phase behaves identically to normal writes. Log **both SCL and NCL** in runbooks and traces.

### 5.3. Visualizing CLs Across Phases

~~~text
Conditional UPDATE IF revision=7
      |
      +-- SERIAL / LOCAL_SERIAL
      |     Paxos PREPARE + PROPOSE
      |     Select proposal / check expected state
      |
      +-- QUORUM / LOCAL_QUORUM / other NCL
            Commit/Learn + visibility ACKs
      |
      +-- [applied] true/false
            (only when client receives response)
~~~

In Cassandra 4.1+, Paxos fast-path optimizations alter round trips; this diagram strictly separates **consistency-level responsibilities**, not exact wire schedules.

### 5.4. `SERIAL` Reads Differ From Normal `SELECT`s

A read running at serial consistency can trigger work to **learn/complete an uncommitted Paxos round**, rather than passively reading replica values. That adds real cost. Never flip all `SELECT`s onto `SERIAL` lazily to dodge uncertainty; reserve serial reads for **reconciliation and invariants truly needing them**, with budgeted timeouts and throughput.

### 5.5. LWT and Transient Replication

Clusters using transient replication or mixed server versions introduce release-specific consensus rules; do not apply full-replica RF=3 assumptions blindly. Verify exact Cassandra release docs, feature flags, and topology, and validate on a matching multi-node test cluster.

## 6. Meaning of `[applied]`: Business Logic, Not an HTTP Status

### 6.1. Three Distinct Outcomes

~~~text
CQL result:
    [applied] = true
=> Conditional statement was applied

CQL result:
    [applied] = false
=> Condition for THAT attempt failed;
   current values may accompany the row

No definitive CQL result due to timeout / network / CAS unknown:
=> UNKNOWN_OUTCOME
   statement may have applied, may not have applied,
   or may still be completing.
~~~

**The server never returns `[applied]=null` on success to signal "unknown":** whenever no definitive CQL row returns, classify the exception/timeout as unknown in application code.

### 6.2. `[applied]=false` Is Still a Transport-Level Success

Example:

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CANCELLED', revision = 3
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

If current revision is 2, Cassandra returns:

~~~text
 [applied] | revision
-----------+----------
     False |        2
~~~

Cassandra **processed the request definitively**; never classify `[applied]=false` under `server_errors` alongside timeouts. In HTTP APIs, teams typically map it to **409 Conflict**, **412 Precondition Failed**, or an equivalent domain outcome—a deliberate API contract choice, not a built-in Cassandra mapping.

### 6.3. `[applied]=false` on Retry Can Signal Earlier Success

~~~text
Client A sends INSERT IF NOT EXISTS, operation_id=OP-7
  |
Server commits INSERT
  |
Response dropped on network before client sees it
  |
Client retries identical conditional INSERT
  |
Server finds existing row -> [applied]=false
~~~

If code blindly logs `[applied]=false` on attempt 2 as "OP-7 failed", the app **mislabels a succeeded transaction**. Always read back the row, checking `last_op_id`/request ID and expected revision to distinguish "already applied by our earlier attempt" from "won by a competing actor".

### 6.4. `ResultSet.wasApplied()` in the Java Driver

~~~java
ResultSet result = session.execute(conditionalStatement);
if (result.wasApplied()) {
    // CAS was applied for this server-confirmed attempt.
} else {
    // Condition was not satisfied.
    // Check expected current state / business conflict.
}
~~~

Per Java Driver Javadoc, `wasApplied()` reads the `[applied]` column on CQL conditional DML. Note that it **returns `true` for non-conditional queries and DDL `IF NOT EXISTS`** because no `[applied]` column is returned; **never** call `wasApplied()` on a plain `INSERT` or `CREATE TABLE` and treat it as an LWT success. [Driver ResultSet API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ResultSet.html).

### 6.5. Single-Attempt Outcomes vs. Logical Operation Outcomes

| Attempt A | Attempt B | Reconciled row | Logical conclusion |
|---|---|---|---|
| `[applied]=true` | Not needed | `last_op_id=A` | Applied in A (newer writes may follow later) |
| Timeout | `[applied]=false` | `last_op_id=A`, expected revision | Evidence A applied; B saw the created/updated row |
| Timeout | `[applied]=false` | `last_op_id=B` | Another actor won; A isn't proven "failed" without full history |
| Timeout | No retry | Row stays at old revision | Not guaranteed A isn't still in flight |
| Timeout | Timeout | State lacks metadata | **UNKNOWN**; escalate or run full reconciliation |

**Never mistake a current snapshot for complete history.** If valid `OP-B` updated state after `OP-A`, `last_op_id=B` does not prove `OP-A` *never applied*. Proving historical execution across chained transitions requires an **audit/inbox event history**.

## 7. Types of Conflicts to Distinguish

### 7.1. Business Conflict: Stale Condition

~~~text
Writer A expects revision=8
Writer B expects revision=8

A CAS: [applied]=true -> revision=9
B CAS: [applied]=false -> observed revision=9

=> Normal conflict expected under optimistic concurrency.
~~~

The service should return a clean conflict or **re-read state and re-evaluate business rules**, rather than looping forever on the stale revision. If code blindly "bumps expected revision" after every false without checking invariants, LWT degrades into disguised last-write-wins.

### 7.2. Paxos Contention: Overlapping Proposals

~~~text
Writer A PREPARE ballot A1
Writer B PREPARE ballot B1
Writer C PREPARE ballot C1
                         |
   Higher ballots supersede in-flight proposals
                         |
   Proposers retry, learn, or time out
                         |
   Latency + contention counters spike
~~~

Multiple concurrent proposers on the exact same key/partition force Paxos retries, inflate response time, and sometimes breach `cas_contention_timeout`. This is **protocol serialization resolving competition**, not data corruption.

### 7.3. Replica/Network Conflict: Dropped ACK / Ambiguous Commit

A proposer may win Paxos consensus only for the client to lose connectivity during the commit phase. The **server can still commit the mutation** while the app sees a timeout/unknown error. Quorum and serial consistency **cannot eliminate** the classic distributed systems truth: **missing ACK ≠ unapplied commit**.

### 7.4. LWW Collision From Unfenced Normal Writers

If one code path uses LWT while another updates **the exact same row** via an ordinary `UPDATE`, CAS guarantees collapse across the domain protocol. This is a **protocol violation in code**, unfixable by cranking `SERIAL` or `QUORUM` on LWT alone.

### 7.5. Cross-Partition Conflict: Guarding the Wrong Key

~~~text
Uniqueness invariant: one active subscription per customer

Broken model:
  subscriptions_by_random_id(subscription_id PRIMARY KEY)
  INSERT ... IF NOT EXISTS

Two clients generate two different subscription IDs.
Both CAS calls succeed — on completely separate partitions!
~~~

When the invariant applies per `customer_id`, model a **unique guard/lookup partition keyed by customer**, backed by a controlled multi-step coordination protocol. LWT has zero awareness that two unrelated random keys share a business constraint.

## 8. Why Do Operations End With Unknown Outcomes?

### 8.1. Timeline of a Lost Acknowledgment

~~~text
Client            Coordinator             Replicas A/B/C
  |                    |                       |
  |---- CAS request -->|                       |
  |                    |---- PREPARE/PROPOSE -->|
  |                    |<--- Paxos accepted ----|
  |                    |----- COMMIT/LEARN ---->|
  |                    |<------- ACK -----------|
  |      X network / response timeout           |
  |<---- no definitive result                   |
  |                    |                       |
  | "unknown"          | mutation may persist  |
~~~

When the client loses sight of commit/learn completion, **timeout never equals rollback**. Cassandra cannot magically convert a dropped packet into certainty on the Java side. Conversely, do not assume every timeout succeeded—failures frequently happen prior to acceptance.

### 8.2. Three Distinct Failure/Timeout Points

| Failure window | What Java observes | Safe interpretation |
|---|---|---|
| Before reaching server | Connect failure / driver deadline | **Still uncertain** whether a coordinator received a retried/multi-node attempt |
| Inside prepare/propose | Write timeout / CAS contention error | Consensus may have aborted or progressed far; check exact exception |
| Post-decision during commit/learn/reply | `CASWriteUnknownException` / timeout / socket reset | May have applied; **must reconcile** |
| Server replied `[applied]` yet packet dropped | Client timeout | Server has definitive outcome that client missed |
| Server returned `[applied]=false` cleanly | Conditional result | Resolved cleanly: predicate failed |

**Across a logical operation**, if retries or speculative attempts touched multiple coordinators, an exception on the final attempt **never** guarantees earlier attempts didn't execute. Preserve the identical operation ID across all attempts and verify against ledger/storage state.

### 8.3. Classifying Java Driver 4.x Exceptions

| Exception (Driver 4.x) | Nature | Safe action |
|---|---|---|
| `CASWriteUnknownException` | Server explicitly returned CAS outcome **unknown** | Mark `UNKNOWN`; reconcile using operation ID |
| `WriteTimeoutException` | Server write missed ACKs before deadline; exposes `WriteType` | Never assume rollback; inspect type, replicas, CL |
| `DriverTimeoutException` | Client deadline elapsed (could include pool/queue wait) | `UNKNOWN` if request might have left client |
| `WriteFailureException` | Replicas/coordinator reported write execution error(s) | Classify from evidence; never blind-replay |
| `UnavailableException` | Coordinator saw insufficient live replicas for CL | Check RF/CL/DC (watch prior attempts if retried) |
| `AllNodesFailedException` | Multiple coordinators failed | Inspect `getAllErrors()` per node and cause |
| `NoNodeAvailableException` | Zero usable coordinators in load-balancing plan | Driver topology/contact point failure |
| `InvalidQueryException` | Syntax, missing PK, bad `IF`, or schema restriction | Fail-fast; fix CQL—never retry as contention |
| `UnauthorizedException` | Missing role permissions | Fix RBAC; never lower CL |

Java Driver 4.18.1 defines `com.datastax.oss.driver.api.core.servererrors.CASWriteUnknownException` explicitly for unknown CAS states. See [CASWriteUnknownException Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/CASWriteUnknownException.html) and [Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/).

### 8.4. What Is `WriteTimeoutException.getWriteType()` Good For?

Cassandra reports the failing write phase/kind (distinguishing ordinary writes, CAS-related paths, batches, counters, etc., depending on version). Still, `WriteType` only names the **stalled mechanism**, never proving whether the transaction committed or rolled back.

~~~java
catch (WriteTimeoutException e) {
    System.err.println("writeType=" + e.getWriteType());
    System.err.println("received=" + e.getReceived());
    System.err.println("blockFor=" + e.getBlockFor());
    // DO NOT conclude rollback.
}
~~~

`received/blockFor` counts coordinator replies relative to CL requirements during failure—**not** rows written or business transactions committed. Never infer "`received=1/2` means 50% of the transaction saved".

### 8.5. Why HTTP 504 Cannot Mean "Guaranteed Failure"

An API gateway can return 504 after timing out while Cassandra commits milliseconds later. If a payment user sees 504 and clicks "Pay" again under a **fresh order ID**, the system can execute two charges. API design must enforce:

- Reusing an **idempotency key** for identical user intent.
- Returning `PENDING_VERIFICATION` or an error carrying a **lookup request ID** when uncertain.
- Never displaying "Failed—please retry" without verification proof.
- Providing an **outcome lookup endpoint** or background reconciliation worker.

### 8.6. Never Use an Immediate Short Read After Timeout as Final Proof

~~~text
CAS timeout at T0
Read ONE at T0+10ms -> old revision
Server completes pending commit at T0+20ms
Read LOCAL_QUORUM at T0+50ms -> new revision
~~~

A fast `ONE` read right after timeout can hit a lagging replica, and any instant snapshot cannot rule out an in-flight Paxos proposal finishing milliseconds later. Reliable reconciliation combines **serial reads / appropriate CL, stable operation IDs, deadlines, ownership, and audit history**—not `Thread.sleep(100)`.

## 9. Reliable Application Outcome State Machine

### 9.1. Outcome Differs From Transport Status

~~~text
                  CAS request
                      |
            +---------+---------+
            |                   |
     Definitive result      No definitive result
            |                   |
     +------+-------+           v
     |              |    UNKNOWN_OUTCOME
 [applied]=true  [applied]=false   |
     |              |             v
 APPLIED       CONDITION_NOT_MET  RECONCILE
     |              |              |
     |        Re-evaluate rule     +--> Proof operation_id matches?
     |                             |      YES -> VERIFIED_APPLIED
     |                             |
     |                             +--> Different winner/version?
     |                             |      Business/audit resolution
     |                             |
     |                             +--> Insufficient evidence?
     |                                    MANUAL_REVIEW / retry policy
     v
Persist status / emit external effects per business protocol
~~~

**Zero valid transition exists** from `UNKNOWN_OUTCOME → FAILED` merely because one `ONE` read didn't find the row yet.

### 9.2. Proposed Java Outcome Enum

~~~java
enum CasOutcome {
    APPLIED,               // Definitive server result: true
    CONDITION_NOT_MET,     // Definitive server result: false
    UNKNOWN_OUTCOME,       // No definitive result
    VERIFIED_APPLIED,      // Reconciled using op ID/version
    VERIFIED_CONFLICT,     // Another winner verified
    MANUAL_REVIEW          // Evidence remains inconclusive
}
~~~

Transition to `VERIFIED_CONFLICT` only when domain rules and audit history verify the current request lost definitively without ever applying earlier; never infer conflict solely from a later mutated snapshot when the earlier LWT could have executed prior to a subsequent transition.

### 9.3. Input Contract for Logical Operations

~~~text
logical_operation_id = stable UUID
entity_id            = stable partition key
expected_revision    = n
target_revision      = n + 1
target_state         = CONFIRMED
deadline             = end-to-end business budget
normal_cl            = LOCAL_QUORUM
serial_cl            = LOCAL_SERIAL (when local DC suffices)
attempt_id           = unique UUID per network attempt
~~~

`entity_id`, `expected_revision`, and `target_state` must **remain invariant across retries of the same logical intent**. If domain logic updates expected revision after a conflict, treat that as a **brand-new business decision**, not a network retry.

### 9.4. Outbox/Idempotency and Downstream Side Effects

Suppose LWT sets `order=PAID` in Cassandra while Java then emits to Kafka, sends email, or calls billing:

~~~text
CAS order PAID at Cassandra
     |
     +--- ACK lost / app crash
     |
Email/payment event missed (or sent twice)
~~~

LWT never spans external systems atomically. Pair it with **outbox/inbox patterns, idempotent consumers, sagas/compensations, and reconciliation** matched to event delivery semantics. Never claim `INSERT IF NOT EXISTS` buys system-wide "exactly once".

## 10. Partition Key and Revision Design to Prevent Unnecessary Contention

### 10.1. Model the Guard Partition Exactly on the Invariant

~~~sql
CREATE TABLE lwt_lab.account_state (
  account_id uuid PRIMARY KEY,
  status text,
  revision int,
  last_op_id uuid
);
~~~

Here each `account_id` maps cleanly to one partition, so competing updates to the **same account** contend on one Paxos instance without blocking unrelated accounts. If the rule is "at most one active voucher per customer", guard a partition **keyed by customer/voucher scope**, never a fresh random UUID per attempt.

### 10.2. Optimistic Revision Fencing

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED', revision = 12,
    last_op_id = 99999999-9999-9999-9999-999999999999
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 11;
~~~

Rules:

- Advance `n → n+1` strictly when the predicate holds.
- Persist `last_op_id` **inside the same conditional statement**.
- On timeout, reconcile via revision + `last_op_id`.
- Never blindly re-read and bump expected revision after `[applied]=false` without re-checking business rules.

`revision int` is illustrative; production designs must address integer bounds, initial creation, and state governance. Some domains substitute monotonic UUID/ULID version tokens to eliminate ABA issues.

### 10.3. The ABA Problem: Value Reverts Before Check Runs

~~~text
T0 status = AVAILABLE, revision=10
T1 status = RESERVED,  revision=11
T2 status = AVAILABLE, revision=12

Client A read at T0 and paused.
At T2, IF status='AVAILABLE' still evaluates true,
even though the entity underwent a full RESERVE/RELEASE cycle.
~~~

Whenever intermediate transitions matter, checking `IF status = 'AVAILABLE'` alone invites stale ABA overwrites. Adding `revision` or a monotonic state token enforced across every transition blocks ABA cleanly—making `IF revision = n` safer than bare status predicates for stateful workflows.

### 10.4. Hot Partitions and Contention Throughput Ceilings

~~~text
10,000 clients -> CAS on shared account_id=GLOBAL_COUNTER
                   |
               Single Paxos key
                   |
             Repeated conflicts
                   |
          Severe contention/latency
~~~

Sharding keys lowers contention **only if the invariant safely decomposes**. If uniqueness must hold globally across all shards, splitting the guard across shards **destroys uniqueness** unless backed by a separate coordination protocol.

### 10.5. Carefully Separating "Read Models" From "Guard Models"

~~~text
Guard table keyed by username:
  username -> owning_user_id (CAS IF NOT EXISTS)

Profile table keyed by user_id:
  user_id -> profile attributes (ordinary writes)
~~~

Crash faults between guard CAS and profile insert can leave both tables out of sync. Incorporate explicit states (`RESERVED`/`CONFIRMED`), operation IDs, reviewed TTL/lease semantics, and background reconciliation—never orphan reservations indefinitely or blindly delete guards whenever profile rows aren't visible yet.

## 11. Retry Policy: When Is Retrying Safe?

### 11.1. Core Decision Table

| Outcome | Retry immediately? | Priority action |
|---|---|---|
| `[applied]=true` | **No** | Record `APPLIED` and proceed downstream |
| `[applied]=false`, stale expected revision | Never loop on same predicate | Return conflict or re-read + re-evaluate domain rule |
| `CASWriteUnknownException` | **No blind retry** | Reconcile via operation ID + version |
| `WriteTimeoutException`/`DriverTimeoutException` on CAS | Never reflexively | Mark `UNKNOWN`; reconcile within deadline |
| `UnavailableException` pre-execution (single attempt) | Possible post-recovery (check prior attempts!) | Check RF/CL/topology |
| `InvalidQueryException` | **No** | Fix CQL, schema, or PK |
| `UnauthorizedException` | **No** | Fix RBAC permissions |
| Transient network drop, proved idempotent | Bounded only | Retry **identical logical ID** with backoff + audit |
| Still unknown once reconciliation budget expires | Never retry forever | Escalate / manual review; preserve evidence |

### 11.2. Why `setIdempotent(true)` Is Not a Magic Wand

Java Driver retry and speculative execution policies depend on the idempotence flag. Replaying a **conditional mutation** can:

- Return `[applied]=true` once and `[applied]=false` on replay.
- Trigger external application side effects even when Cassandra's state stays safe.
- Interleave unpredictably with concurrent actors.

**Never flip `setIdempotent(true)` globally on all LWTs out of habit.** Enable it only when both the CQL mutation and every downstream handler/operation ID prove safe under replay. By default, this guide keeps `setIdempotent(false)` on conditional writes and drives recovery through explicit reconciliation.

### 11.3. Speculative Execution Amplifies Contention

If the driver dispatches a **duplicate LWT attempt** to a second coordinator while attempt 1 lags, it spawns **competing Paxos ballots on the exact same partition**, escalating contention. Never enable speculative execution on non-idempotent LWTs; even when idempotent, benchmark `CASWrite.ContentionHistogram`, physical attempts, and total cost first.

### 11.4. Conditional Backoff and Jitter

Illustrative backoff schedule for a **reconciled, replay-safe logical operation**:

~~~text
attempt 1: 0ms
attempt 2: randomized 25-75ms
attempt 3: randomized 75-225ms
attempt 4: randomized 150-450ms
hard stop: max 3 retries OR 2s total budget, whichever hits first
~~~

These numbers are illustrative, not Java Driver defaults. Once a condition returned `false` because another actor won, backoff cannot change the outcome unless your workflow intentionally waits for state shifts—**never use retries to race past invariants**.

### 11.5. Aligning Server Timeouts and Client Deadlines

Relevant timeout layers:

- `cas_contention_timeout` on Cassandra: bounds how long coordinators retry contested Paxos rounds.
- `write_request_timeout` / server request timeouts: bound coordinator/replica waits.
- `basic.request.timeout` / statement `.setTimeout(...)` in Java Driver: client-side deadline.
- API gateway / HTTP timeouts: often shorter than server/driver timeouts!
- Business operation deadline: maximum time before returning or handoff to async reconciliation.

If an HTTP gateway cuts off at 800ms while Java Driver waits 3s and Cassandra keeps processing, clients abandon requests mid-commit. **Raising every timeout endlessly never resolves contention**—it bloats queued requests, heap, and latency while the bottleneck persists. Establish a consistent, phased **deadline budget** covering response and reconciliation.

In Cassandra 4.1+, the key is `cas_contention_timeout` (e.g., `1000ms` in reference configs), whereas older releases used `cas_contention_timeout_in_ms`. Inspect **effective running configs for your release** rather than copying deprecated keys. [Configuration reference](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html).

## 12. LWT-Specific Metrics and How to Read Them

Cassandra exposes `CASRead` and `CASWrite` groups under `org.apache.cassandra.metrics.ClientRequest`, providing far sharper insight than aggregate read/write QPS. See [Apache Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).

### 12.1. Metric Matrix

| Scope | Metric | Meaning | Interpretation caveat |
|---|---|---|---|
| `CASWrite` | `Latency` | Coordinator latency for conditional writes | Does not equal client HTTP p99 |
| `CASWrite` | `ContentionHistogram` | Contention attempts observed on CAS writes | Depends on sample volume and Cassandra release |
| `CASWrite` | `ConditionNotMet` | Conditional predicate evaluated false | Usually **business conflict**, not server outage |
| `CASWrite` | `UnfinishedCommit` | Prior incomplete transaction finished during CAS write | Hints at earlier contention or coordinator issues |
| `CASWrite` | `Timeouts` | Coordinator CAS write timeouts | Indicates potential unknown outcomes |
| `CASWrite` | `Failures` | Transactional write failures | Inspect server logs/causes; keep separate from `[applied]=false` |
| `CASWrite` | `Unavailables` | Insufficient live replicas for CL | Depends on RF, DC, SCL, and NCL |
| `CASRead` | `Latency` | Transactional serial reads | Distinct from normal `ReadLatency` |
| `CASRead` | `ContentionHistogram` | Contention on serial reads | Can climb alongside unfinished Paxos state |
| `CASRead` | `UnfinishedCommit` | Unfinished commits resolved during reads | Does not prove data corruption automatically |
| Table | `CasPrepare`/`CasPropose` | Server latencies of Paxos prepare/propose steps | Naming/availability varies by version |
| Driver node | `cql-messages`, errors, retries | Physical attempts and per-node pressure | One logical call can fire multiple attempts |
| OS/JVM | GC, CPU, disk await, internode RTT | Latency drivers outside Paxos contention | Paxos metrics alone never complete triage |

Exporters rarely map identical series names out of the box across every stack; JMX MBeans, Prometheus aliases, and Micrometer labels vary—**verify your real exporter endpoints** before alerting.

### 12.2. Is High `ConditionNotMet` Always a Bug?

Consider a username-reservation API:

~~~text
30 writers race for "john"
1 writer gets [applied]=true
29 writers get [applied]=false

High ConditionNotMet count,
yet business uniqueness remained intact.
~~~

Those 29 false results represent normal **domain contention**, not 29 Cassandra failures. Conversely, if one path loops 1,000 CAS/sec with identical expected revision right after getting `false`, that indicates an **application retry loop**. Monitor `condition_not_met / total_cas_writes` across query families, time windows, and traffic shifts.

### 12.3. Converting Counters to Rates and Distributions Over Time

~~~text
cas_requests_per_sec = delta(CASWrite requests) / seconds
condition_false_rate = delta(ConditionNotMet) / CAS attempts
timeout_rate         = delta(CASWrite Timeouts) / CAS attempts
contention_p95       = percentile of ContentionHistogram (if exposed)
unknown_outcomes     = application-classified timeout/unknown count
~~~

These are **logical metric definitions**, not copy-paste PromQL; exact types and resets depend on your exporter. Because server counters reset across restarts, compute `rate`/`increase` properly alongside node uptime—never compare raw lifetime totals across nodes restarted on different dates.

### 12.4. Do Not Overlook Metrics Outside Paxos

~~~text
Logical LWT calls/s
  -> driver request attempts, pool.in-flight, retries
  -> coordinator CASWrite latency, ConditionNotMet, contention
  -> per-node GC/CPU, disk/commitlog, network RTT
  -> table read/write latency and compaction backlog
  -> business outcomes + downstream duplicate detections
~~~

If `CASWrite.Latency` climbs while `ContentionHistogram` stays flat, inspect disk I/O, GC, network latency, throttling, or CL/key shifts. Conversely, heavy single-key contention can spike p99 violently while cluster-wide average CPU stays deceptively calm.

### 12.5. Timelines With Event Markers

~~~text
10:00 baseline (2 CAS/s per key; false rate 2%)
10:05 rollout app version V2
10:06 contenders/key jumps to 50
10:07 contention histogram shifts upward
10:08 client p99 climbs, CASWrite timeouts increase
10:09 API 504s + reconciliation backlog grows
10:10 HOLD rollout and rate-limit hot key
~~~

This is **synthetic illustrative telemetry**, not real cluster data. Synchronize UTC clocks across application nodes, drivers, Cassandra coordinators, and infrastructure hosts when compiling incident timelines.

## 13. Contention Hypotheses to Test Systematically

### 13.1. Single Hot Partition

Many clients compete to update the same account or order ID concurrently, especially without backoff/jitter. Verify using **privacy-safe key grouping** (HMAC/opaque buckets, zero PII in logs), per-key contender sampling, `ConditionNotMet`, and `ContentionHistogram`.

### 13.2. Distinct Operations Funneled Into One Guard Key

Example: a cluster-wide `global_sequence` partition allocating monotonic IDs. Thousands of writers queue behind one Paxos slot; adding nodes never boosts throughput on **one single partition**. Fix via batched/ranged ID leases, domain partitioning, or distributed UUIDs where global order constraints permit.

### 13.3. Client Timeout Shorter Than Realistic WAN Paxos RTT

Multi-round `SERIAL` Paxos spanning DCs naturally takes longer than `LOCAL_SERIAL`. When HTTP deadlines clip under legitimate RTTs, `UNKNOWN_OUTCOME` counts explode while Cassandra runs cleanly. Size **SCL, NCL, DC topology, network RTT**, and API deadlines cohesively.

### 13.4. Degraded Quorum Liveness or One Lagging Replica

Gossip `UN` never proves replicas reply cleanly inside prepare/propose deadlines. Disk await, GC pauses, internode queues, or WAN congestion can starve quorum even when every node stays Up—generating `CASWriteUnknownException`/timeouts rather than `ConditionNotMet`.

### 13.5. Driver Retries/Speculation Multiplying Paxos Proposals

Marking conditional writes idempotent while enabling aggressive retries or speculative execution fires parallel CAS attempts for one logical intent, creating self-inflicted contention. Compare `client logical requests/s` against `node cql-messages/s` and retry/speculation telemetry.

### 13.6. Misleading Benchmark Generators

Benchmarking only 100 hot keys triggers extreme contention unrealistic for millions of independent accounts; conversely, firing unique random UUIDs every call measures zero contention while missing real hot-order bursts. Realistic benchmarks must match production **key distributions, contenders/key, DC routing, and SCL/NCL**.

### 13.7. Repeated False Conditions Without Ballot Contention

If 10,000 requests check `IF revision=1` on a row sitting steadily at `revision=50`, they fail cheaply as stale conditions. Huge `ConditionNotMet` counts **never prove concurrent ballot collisions by themselves**; inspect `ContentionHistogram` and latencies together.

## 14. Safe Read-Only Commands Prior to Any Config Tuning

### 14.1. Inspecting Ring Health

~~~bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool tablestats lwt_lab.account_state
~~~

`nodetool` requires JMX permissions, and exact subcommands/output vary by release. Treat these strictly as **read-only diagnostics**—never fire `stop`, `compact`, `flush`, or `repair` blindly as an automatic Paxos fix.

### 14.2. Checking Replication and Topology via CQL

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'lwt_lab';

SELECT cluster_name, data_center, host_id,
       release_version
FROM system.local;
~~~

A single-node `SimpleStrategy RF=1` lab cannot model multi-node `SERIAL`/`LOCAL_SERIAL` quorums. Multi-DC production runs `NetworkTopologyStrategy` with per-DC RFs; pinpoint the **actual natural replicas** owning the contested partition (token/ring/DC/rack) so you measure the right nodes.

### 14.3. Point Read Checks Do Not Replace Metrics

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

One `SELECT` reveals current row state, **never the history of earlier CAS attempts**. Settling unknown outcomes requires expected operation IDs, revisions, CLs, timestamps, actors, and an audit ledger whenever sequential transitions follow.

### 14.4. Never Hand-Edit Paxos Internals

Cassandra stores internal Paxos state (such as `system.paxos` or newer per-release structures). **Never treat internal Paxos tables as DBA-editable state.** Never truncate/delete/mutate ballots, copy system tables between nodes, or run unverified "Paxos reset" recipes from blogs. If Paxos state appears corrupted or stuck, preserve logs and escalate to DBAs under release-verified recovery SOPs.

## 15. Comparing LWT With Related Patterns

| Mechanism | Solves well | Does NOT solve |
|---|---|---|
| Normal write at `LOCAL_QUORUM` | Durable multi-replica upserts per CL | Atomic CAS under concurrent writers |
| LWT `IF revision=n` | Optimistic atomic transitions within scoped partition | Cross-system exactly-once delivery |
| `INSERT IF NOT EXISTS` | Guarding uniqueness on **the exact same PK** | Uniqueness across unrelated partitions |
| Kafka partition ordering | Sequential consumer delivery inside a Kafka partition | CAS if other writers hit DB directly |
| Single-writer / actor per entity | Eliminates ballot contention, clarifies ownership | Crash recovery, rebalances, out-of-order replay (still need fencing!) |
| Idempotency key + ledger | Tracking and deduplicating retried intents | Atomic transition enforcement absent CAS |
| Outbox / inbox + saga | Reliable async downstream side-effect dispatch | Single cross-service ACID commit |
| Relational row locks (SQL DBs) | Broad multi-row transactional ACID | Cannot be assumed onto Cassandra CQL |

**No single tool replaces end-to-end invariant and retry architecture.** Apply LWT where atomic concurrency control is genuinely required, while asking: "Can we shrink concurrent writers hitting one partition without compromising the invariant?"

## 16. Lab A — CQL: `IF NOT EXISTS`, Revision CAS, and `[applied]`

### 16.1. Environment and Constraints

- Dedicated **single-node lab** running Cassandra 4.1 or 5.0 with `cqlsh` connected.
- Operate strictly inside a fresh `lwt_lab` keyspace; never `DROP`/`TRUNCATE` shared namespaces.
- `SimpleStrategy RF=1` with `CONSISTENCY ONE` suits single-node CQL practice and **never** tests RF=3 Paxos failover when a replica drops.
- Single-threaded execution runs deterministically; two-writer races in Section 17 require separate concurrent sessions.
- **Never inject destructive OS/network faults**; handle `UNKNOWN_OUTCOME` conceptually and in application-tier mocks without harming Cassandra hosts.

### 16.2. Creating the Entity Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS lwt_lab.account_state (
  account_id uuid PRIMARY KEY,
  status text,
  revision int,
  last_op_id uuid
);

CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
~~~

**Verify existing schemas** when re-running: `IF NOT EXISTS` skips schema changes if tables already exist differently. Multi-node production requires `NetworkTopologyStrategy` RF and matching CLs—never use RF=1 to benchmark quorum latency.

### 16.3. Initial Conditional Insert

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  11111111-1111-1111-1111-111111111111,
  'PENDING',
  1,
  22222222-2222-2222-2222-222222222222
)
IF NOT EXISTS;
~~~

When absent:

~~~text
 [applied]
-----------
      True
~~~

Re-running once the row exists:

~~~text
 [applied] | ... current values ...
-----------
     False
~~~

**`False` on retry does not prove failure.** If attempt 1 timed out yet the row holds `last_op_id=2222...` with expected state/revision, creation succeeded earlier. If another actor/ID owns the row, resolve the conflict cleanly.

### 16.4. Inspecting Initial State

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect `PENDING`, revision `1`, and creator op ID. Never run table-wide `SELECT COUNT(*)` or `ALLOW FILTERING` to inspect one account—query directly by primary key.

### 16.5. Client A Transitions Revision 1 → 2

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED',
    revision = 2,
    last_op_id = 33333333-3333-3333-3333-333333333333
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Expect `[applied]=true` provided no other actor updated it first. Then verify:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect `CONFIRMED`, `2`, `3333...`—a clean **CAS transition**, not a blind upsert.

### 16.6. Client B Attempts Stale Expected Revision

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CANCELLED',
    revision = 2,
    last_op_id = 44444444-4444-4444-4444-444444444444
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Expect `[applied]=false`; Client A's state remains untouched—the essence of optimistic concurrency:

~~~text
A: expected rev 1 -> applied true  -> current rev 2
B: expected rev 1 -> applied false (stale expectation)
~~~

Upon receiving `false`, Client B **must not blindly rewrite expected revision to 2 and force `CANCELLED`** if domain logic forbids reversing `CONFIRMED → CANCELLED`.

### 16.7. Multi-Condition CAS

~~~sql
UPDATE lwt_lab.account_state
SET status = 'FULFILLED',
    revision = 3,
    last_op_id = 55555555-5555-5555-5555-555555555555
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 2 AND status = 'CONFIRMED';
~~~

Expect `true` when prior state holds; `false` cleanly rejects stale assumptions. Always supply the **complete primary key**.

### 16.8. Never Mix Unguarded Normal `UPDATE`s Into the Protocol

~~~sql
-- Ordinary blind statement: NEVER mix into invariant tests:
-- UPDATE lwt_lab.account_state
-- SET status = 'PENDING', revision = 1
-- WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Whenever an unfenced writer bypasses CAS, tests should flag a **protocol violation**, not blame Cassandra Paxos. Enforce revision fencing or reviewed single-writer serialization across every writer.

### 16.9. Reasoning Exercise: "Missing ACK"

You do not need packet drops to think through unknown logic. Suppose Client A's `UPDATE ... IF revision=1` executed on the server while the **response vanished**. You then query:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

If `last_op_id` equals A's ID alongside matching revision/status, that gives evidence A applied **at that point**, assuming actors cannot spoof or overwrite `last_op_id` arbitrarily. Once subsequent transitions overwrite `last_op_id`, a lone row snapshot **cannot** reconstruct history—requiring audit ledgers or manual investigation.

**This is a mental exercise, not an executed fault-injection run.**

## 17. Lab B — Two Competing Clients Checking `[applied]` Properly

### 17.1. Use Two Separate `cqlsh` Sessions

In a **lab cluster**, run two `cqlsh` terminals concurrently with `CONSISTENCY ONE` and `SERIAL CONSISTENCY SERIAL`, targeting the same `account_id` and `expected_revision=10` with distinct `target_status` and `last_op_id` values.

Seed a dedicated lab row:

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
  'READY', 10,
  00000000-0000-0000-0000-000000000010
)
IF NOT EXISTS;
~~~

If reusing a lab cluster, pick a fresh unique `account_id`. **Never** reset state carelessly via `TRUNCATE` or blind normal overwrites outside LWT discipline.

### 17.2. Writer A (Terminal 1)

~~~sql
UPDATE lwt_lab.account_state
SET status='OWNED_BY_A',
    revision=11,
    last_op_id=aaaaaaaa-0000-0000-0000-000000000001
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
IF revision=10;
~~~

### 17.3. Writer B (Terminal 2)

~~~sql
UPDATE lwt_lab.account_state
SET status='OWNED_BY_B',
    revision=11,
    last_op_id=bbbbbbbb-0000-0000-0000-000000000002
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
IF revision=10;
~~~

When both run and return definitive responses cleanly, **at most one** gets `applied=true` while the other gets `false`. Under tight deadlines or heavy collisions, one might also time out (`UNKNOWN`)—so automated tests without strict control shouldn't blindly assert "always exactly one true and one false".

### 17.4. Verify Final State

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa;
~~~

Expect `revision=11` paired with exactly one winner's status and `last_op_id` (absent background writers). If both concurrent writers somehow logged `[applied]=true` on identical expected revision `10`, investigate immediately as a critical anomaly: inspect exact request IDs, schema, primary keys, SCL/normal CL, multi-DC setup, unfenced writers, and node versions before declaring engine corruption.

### 17.5. Real Ballot Contention vs. Sequential Conflicts

Running A to completion and then executing B simply creates a **sequential business conflict**—not overlapping Paxos contention. Measuring `ContentionHistogram` requires dispatching **concurrent overlapping proposals onto one partition** in a monitored staging cluster, rather than reading sequential `ConditionNotMet` counters.

### 17.6. Never Stage "Lost ACKs" in Production

Never inject iptables drops, kill coordinators, or slash production timeouts to manufacture `UNKNOWN_OUTCOME`. Exercise application-layer fault mocks for logic testing, and restrict physical network/node fault drills to isolated staging environments with full RF/CL and recovery plans.

## 18. Lab C — Java Driver 4.x: Issuing LWTs and Reading `wasApplied()`

### 18.1. Execution Prerequisites

- Java 17 and Apache Cassandra Java Driver 4.x against a single-node RF=1 lab on `127.0.0.1:9042`.
- Replace `"datacenter1"` with your real `system.local.data_center` value if different.
- The snippet sets up `lwt_lab`/`account_state` via `IF NOT EXISTS`; execute strictly on a **disposable lab** where no external test conflicts on the table.
- Generate one stable operation ID per logical intent—**never** mint a fresh operation ID on timeout retries.
- Speculative execution and automatic LWT retries remain disabled here.

Illustrative Gradle Kotlin DSL dependency:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

This dependency note is **not** a request to edit project build files. The Java code targets driver 4.18.x APIs; verify pinned versions and compile checks in a separate QA pass.

### 18.2. Standalone Java 17 Program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.CASWriteUnknownException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;

public final class LwtOutcomeLab {
    private LwtOutcomeLab() {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            session.execute(
                "CREATE KEYSPACE IF NOT EXISTS lwt_lab " +
                "WITH replication = {'class':'SimpleStrategy', " +
                "'replication_factor':1}");

            session.execute(
                "CREATE TABLE IF NOT EXISTS lwt_lab.account_state (" +
                "account_id uuid PRIMARY KEY, status text, " +
                "revision int, last_op_id uuid)");

            if (!session.checkSchemaAgreement()) {
                throw new IllegalStateException(
                    "Schema agreement required in lab");
            }

            // Fresh account per lab run.
            UUID accountId = UUID.randomUUID();
            UUID createOpId = UUID.randomUUID();
            UUID confirmOpId = UUID.randomUUID();

            PreparedStatement insert = session.prepare(
                "INSERT INTO lwt_lab.account_state " +
                "(account_id, status, revision, last_op_id) " +
                "VALUES (?, ?, ?, ?) IF NOT EXISTS");

            PreparedStatement casUpdate = session.prepare(
                "UPDATE lwt_lab.account_state " +
                "SET status=?, revision=?, last_op_id=? " +
                "WHERE account_id=? IF revision=?");

            PreparedStatement read = session.prepare(
                "SELECT status, revision, last_op_id " +
                "FROM lwt_lab.account_state WHERE account_id=?");

            BoundStatement create = insert.bind(
                    accountId, "PENDING", 1, createOpId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL)
                .setIdempotent(false)
                .setTimeout(Duration.ofSeconds(3));

            ResultSet created = session.execute(create);
            if (!created.wasApplied()) {
                throw new IllegalStateException(
                    "Unexpected conflict on fresh lab account");
            }

            BoundStatement transition = casUpdate.bind(
                    "CONFIRMED", 2, confirmOpId, accountId, 1)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL)
                .setIdempotent(false)
                .setTimeout(Duration.ofSeconds(3));

            try {
                ResultSet outcome = session.execute(transition);
                if (outcome.wasApplied()) {
                    System.out.println("APPLIED");
                } else {
                    System.out.println("CONDITION_NOT_MET");
                }
            } catch (CASWriteUnknownException
                   | WriteTimeoutException
                   | DriverTimeoutException e) {
                // Never retry with a fresh operation ID.
                System.err.println(
                    "UNKNOWN_OUTCOME type=" +
                    e.getClass().getSimpleName());
                // In production: persist UNKNOWN into a durable
                // operation ledger and schedule reconciliation.
                return;
            } catch (AllNodesFailedException e) {
                System.err.println(
                    "COORDINATOR_FAILURES; outcome needs classification");
                e.getAllErrors().forEach((node, errors) -> {
                    for (Throwable failure : errors) {
                        System.err.printf(
                            "node=%s cause=%s%n",
                            node.getHostId(),
                            failure.getClass().getSimpleName());
                    }
                });
                // An attempt may already have shipped/committed before failing;
                // never replay automatically.
                return;
            }

            BoundStatement readBack = read.bind(accountId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));

            Row row = session.execute(readBack).one();
            if (row == null
                    || !"CONFIRMED".equals(row.getString("status"))
                    || row.getInt("revision") != 2
                    || !confirmOpId.equals(row.getUuid("last_op_id"))) {
                throw new AssertionError(
                    "LWT applied response/data oracle mismatch");
            }

            System.out.println("DATA_ORACLE_PASS");

            // Illustrates repeating the identical CAS once the first
            // attempt is known applied.
            ResultSet repeated = session.execute(transition);
            if (repeated.wasApplied()) {
                throw new AssertionError(
                    "Old revision must no longer match");
            }
            System.out.println("REPEAT_CONDITION_NOT_MET");
        }
    }
}
~~~

### 18.3. Reading Expected Output Correctly

~~~text
APPLIED
DATA_ORACLE_PASS
REPEAT_CONDITION_NOT_MET
~~~

This matches **a healthy single-writer lab run**. On timeouts:

~~~text
UNKNOWN_OUTCOME type=CASWriteUnknownException
~~~

or matching timeout/aggregate error logs. This snippet **classifies and halts** without implementing a durable ledger (covered in Section 19). Never see `UNKNOWN_OUTCOME` in logs and immediately submit a fresh CAS call with a brand-new UUID.

### 18.4. An Intentional Simplification

`readBack` uses `ONE` strictly because this is a **single-node RF=1 lab** after an applied ACK; never extrapolate that a `ONE` read reconciles unknown outcomes in RF=3 multi-DC production. Production verification reads must honor normal/serial CLs, schema design, and commit visibility rules.

### 18.5. Never Generate Fresh Operation IDs Inside Retry Loops

**Wrong:**

~~~java
for (int attempt = 0; attempt < 5; attempt++) {
    UUID opId = UUID.randomUUID(); // Fresh intent on every loop iteration!
    // send CAS; catch timeout; retry blindly
}
~~~

**Identity-safe:**

~~~java
UUID opId = UUID.randomUUID(); // Generated once per logical operation.
for (int attempt = 0; attempt < maxAttempts; attempt++) {
    // Where retries are permitted, REUSE identical opId and expected revision.
    // Always reconcile UNKNOWN first rather than looping blindly.
}
~~~

This is strictly an **ID-ownership skeleton**, not a production retry handler. Post-timeout CAS calls demand reconciliation—never cite this loop as permission for blind retries.

## 19. Reconciling `UNKNOWN_OUTCOME`: Algorithm and Boundaries

### 19.1. Minimum Reconciliation Inputs

A reconciler takes `entityId`, `logicalOperationId`, `expectedRevision`, `targetRevision`, `expectedState`, serial/normal CLs, and a deadline. It promotes `UNKNOWN` to `VERIFIED_APPLIED` solely upon **trustworthy evidence**—such as finding `last_op_id`, `revision`, and `status` matching inside a protocol forbidding arbitrary `last_op_id` overwrites.

### 19.2. Using Serial Reads When Required

In `cqlsh`:

~~~text
cqlsh> CONSISTENCY SERIAL;
~~~

Followed by:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Serial reads force completion/visibility of pending Paxos rounds within serial consistency scope—yet **cannot** rewind history once a later writer mutated the row. Use sparingly, as serial reads incur higher cost than normal reads. [Cassandra cqlsh SERIAL consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).

### 19.3. Java Helper Read for Reconciliation

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

static CasOutcome checkOperation(
        CqlSession session,
        PreparedStatement readPrepared,
        UUID entityId,
        UUID expectedOpId,
        int targetRevision,
        String targetStatus) {

    BoundStatement serialRead = readPrepared.bind(entityId)
        .setConsistencyLevel(DefaultConsistencyLevel.SERIAL)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true);

    Row row = session.execute(serialRead).one();
    if (row != null
            && expectedOpId.equals(row.getUuid("last_op_id"))
            && row.getInt("revision") == targetRevision
            && targetStatus.equals(row.getString("status"))) {
        return CasOutcome.VERIFIED_APPLIED;
    }

    // Still lacks sufficient proof to declare "definitely not applied".
    return CasOutcome.UNKNOWN_OUTCOME;
}
~~~

This helper **depends on** `CasOutcome` (Section 9) and imports from Lab C; it demonstrates core check logic rather than a full daemon. Multi-DC deployments must pick `SERIAL` vs. `LOCAL_SERIAL` matching the system-wide serialization contract—never check `LOCAL_SERIAL` to assert global state. Any read timeout keeps status as `UNKNOWN` while capturing underlying errors.

### 19.4. Why an Audit Ledger Is Needed If Rows Advance Further

~~~text
T0 op A: PENDING -> CONFIRMED, revision=2, last_op=A
T1 op B: CONFIRMED -> FULFILLED, revision=3, last_op=B
T2 A's reconciler reads:
      status=FULFILLED, rev=3, last_op=B
~~~

Reconciler A **cannot** conclude A never ran: A likely succeeded, allowing B to advance afterward. Whenever multiple chained mutations can follow an unknown attempt, persist an **operation-status ledger / event audit trail** designed for consistency and idempotency. Remember that updating an account row and writing an audit log across **two partitions** is not inherently atomic—coordinate carefully so the two records never diverge silently.

### 19.5. Bounded Reconciliation With Explicit Outcomes

~~~text
UNKNOWN
  |
  | read / serial read within bounded budget
  v
Entity state matches op ID and expected version?
  | YES                 | NO
  v                     v
VERIFIED_APPLIED    Inspect operation ledger/history
                       |
                +------+-------+
                |              |
             Proof         Insufficient proof
                |              |
       VERIFIED_CONFLICT   MANUAL_REVIEW /
       or APPLIED          PENDING_VERIFICATION
~~~

Under concurrent post-unknown mutations, definitive resolution demands an audit trail rather than current row inspection alone. Cap **max attempts and total deadline**, throttle reconciler QPS, and preserve traces so recovery jobs never storm an impaired cluster.

### 19.6. End-to-End Exactly-Once Never Comes From the DB Alone

Even once Cassandra commits CAS `APPLIED`, HTTP replies can drop; even after writing a ledger row, Kafka can redeliver. Define explicit system invariants:

1. Clients preserve the identical **idempotency key** across retries of the same intent.
2. Operation IDs and expected revisions persist alongside CAS state where feasible.
3. Expose a lookup endpoint/worker for transaction status.
4. Guard every downstream side effect with inbox/outbox deduplication.
5. Retain operation records long enough to cover maximum client retry windows.
6. Route unprovable edge cases cleanly into manual review runbooks.

**Never** pair an LWT with an unrelated `INSERT INTO operation_log` across two partitions and pretend both form one atomic transaction.

## 20. Designing Integration and Fault Tests for LWT

### 20.1. Essential Test Matrix

| Test | Fixture | Expected result | What it verifies |
|---|---|---|---|
| Insert fresh key `IF NOT EXISTS` | RF=1 lab | `[applied]=true` | Conditional insert works |
| Duplicate insert same key | RF=1 lab | `[applied]=false` | Prevents duplicate record on PK |
| Two concurrent writers expecting rev `n` | Multi-threaded lab | At most one `applied=true` | Optimistic CAS protects state |
| CAS with stale revision | RF=1 lab | `False` + current revision | Business conflict ≠ timeout |
| Lost ACK after commit | App fault mock | `UNKNOWN` → verified via op ID | Refuses to misclassify as failed |
| Timeout prior to commit | App fault mock | `UNKNOWN`; no blind replay | Triggers reconciliation |
| Lagging old writer arrives post-advance | Lab concurrency | Rejects stale mutation | Revision fencing works |
| Two writers pick distinct random PKs | Lab | Both return `true` | Invariant requires shared guard key |
| Normal writer skips CAS | Isolated lab | Protocol broken | All writers must enforce fencing |
| RF=3 + `LOCAL_QUORUM`/`LOCAL_SERIAL` | Multi-node cluster | Accurate CL semantics | Multi-replica quorum behavior |
| One replica lagging/partitioned | Fault staging | Classified timeout/unknown/catch-up | Availability and RTO |
| Multi-DC `LOCAL_SERIAL` vs. `SERIAL` | Multi-DC lab | Enforces DC scope contract | Prevents false global assumptions |

**Do not require a 6-node chaos cluster on every PR** if CI lacks capacity—just recognize that single-node RF=1 tests prove **CQL syntax and conditional logic only**, never multi-replica Paxos failover or production contention.

### 20.2. JUnit 5: Verifying Lost-ACK Handling With a Fake Store

This pure Java test **does not simulate Paxos**—it proves application logic **refuses to mislabel a committed operation as failed** when replies drop.

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class UnknownOutcomeStateMachineTest {
    static final class ResponseLost extends RuntimeException {}

    static final class FakeAccount {
        int revision = 1;
        UUID lastOpId;

        // Strictly an atomic fake CAS on an in-memory Java object.
        synchronized boolean compareAndSet(
                int expected, int target, UUID operationId) {
            if (revision != expected) {
                return false;
            }
            revision = target;
            lastOpId = operationId;
            return true;
        }
    }

    @Test
    void lostReplyCannotBeTreatedAsDefiniteFailure() {
        FakeAccount store = new FakeAccount();
        UUID opId = UUID.randomUUID();

        assertThrows(ResponseLost.class, () -> {
            boolean applied = store.compareAndSet(1, 2, opId);
            assertTrue(applied);
            throw new ResponseLost(); // ACK dropped post-commit
        });

        // A naive retry checking expected=1 returns false because
        // the prior attempt ALREADY moved revision=2.
        assertFalse(store.compareAndSet(1, 2, opId));

        // Reconcile via operation ID rather than treating the
        // second attempt's false result as overall failure.
        assertEquals(2, store.revision);
        assertEquals(opId, store.lastOpId);
    }

    @Test
    void twoDistinctWritersCannotBothWinOneRevision() {
        FakeAccount store = new FakeAccount();
        UUID opA = UUID.randomUUID();
        UUID opB = UUID.randomUUID();

        boolean a = store.compareAndSet(1, 2, opA);
        boolean b = store.compareAndSet(1, 2, opB);

        assertTrue(a);
        assertFalse(b);
    }
}
~~~

**Limitation:** `synchronized` in-memory tests validate zero Cassandra distribution, driver retries, or networking—their sole job is locking **reconciliation semantics** in unit tests so nobody accidentally turns `UNKNOWN_OUTCOME` into `FAILED`.

### 20.3. Integration Testing Against Live Cassandra

In a dedicated Cassandra lab:

1. Generate a fresh entity ID in the lab table.
2. Seed revision `n` via LWT (`[applied]=true`).
3. Launch two worker threads executing `IF revision=n` with distinct operation IDs.
4. Synchronize start with a latch/barrier and capture each thread's response/exception separately.
5. Whenever both receive **definitive results**, assert **at most one** `wasApplied() == true`.
6. Read back at target CL, asserting `revision = n + 1` and the winner's op ID.
7. If timeouts/unknowns occur, never blindly assert "one true and one false"; log `UNKNOWN`, run reconciliation, and verify invariants.
8. Inspect CAS contention/timeout counters plus node GC, disk, and network health post-test.

Under RF=3, verify serial CL alignment; clients must never **silently** downgrade `SERIAL` to `LOCAL_SERIAL` on retries. Document coverage across DC, tokens, RF, and idempotency settings.

### 20.4. Common Sources of Test Flakiness

| Symptom | Root cause | Prevention |
|---|---|---|
| Old rows survive across CI runs | Hardcoded static entity IDs | Generate fresh entity/op IDs per run |
| Test claims contention yet runs serially | Missing start barrier | Use executor + countdown latch + contention metrics |
| RF=1 lab passes while RF=3 staging times out | Missing network/quorum hops | Run multi-node integration suites separately |
| Unexpected automatic driver retries | `setIdempotent(true)` or retry profile | Keep disabled / count physical attempts |
| Weak assertion checking only `row != null` | Ignoring revision and `last_op_id` | Assert full business oracle fields |
| Fault test stops non-replica node | Token placement unknown | Verify natural replicas for the test key first |
| Spurious timeouts under CI CPU throttling | Noisy shared CI runners | Dedicated workload/fault environment |
| High `[applied]=false` with zero Paxos contention | Sequential execution | Cross-check `ContentionHistogram` alongside `ConditionNotMet` |

### 20.5. Controlled Lost-ACK Chaos Drills

If teams operate fault-injection **test-only network proxies**, inject response drops *strictly on the reply path* post-CAS commit and validate:

~~~text
1. Baseline and known initial state
2. Send CAS with stable op ID
3. Proxy drops matching reply only (lab)
4. Client logs UNKNOWN_OUTCOME
5. Reconciler runs serial/CL read + verifies op ID/version
6. Transitions to VERIFIED_APPLIED or stays UNKNOWN
7. Confirm zero duplicate downstream side effects
8. Restore proxy and archive metrics
~~~

**Never assume** a proxy knows commit state with 100% precision without server/trace corroboration. Keep test harnesses crystal clear so a dropped request isn't mislabeled "lost ACK post-commit".

### 20.6. Verifying After Snapshot Restore, Repair, or Rolling Restarts

Following restores, repairs, or rolling restarts:

- Verify schema/tables/PKs, RF/CL, node statuses, and synthetic oracle reads first.
- Reconcile **historical operation IDs** from audit manifests, not merely fresh LWT calls.
- Monitor pending Paxos state/`UnfinishedCommit` and node I/O during rejoins.
- Never layer destructive fault injection atop live restores.
- While any node sits `DOWN`, healthy node agreement guarantees nothing about the returning node's local disk until rejoin/repair gates clear.

## 21. Twenty-Two Practical Troubleshooting Cases

### Case 1 — `[applied]=false` Reported as "Database Timeout"

**Signal:** HTTP 500s spike while Cassandra `ConditionNotMet` climbs and timeouts stay zero.

**Analysis:** App maps business conflict as server outage. **Fix:** Map `false` cleanly to HTTP 409/412 or domain conflict handling, track conflict metrics separately, and never raise server timeouts.

### Case 2 — Concurrent API Calls Claim Same Username

**Signal:** One succeeds (`true`) and one fails (`false`) on `INSERT IF NOT EXISTS` against the username guard key.

**Analysis:** Expected uniqueness protection working cleanly. **Fix:** Return "username taken" to the loser—never swap in random guard keys to force both through.

### Case 3 — Lost ACK Causes Duplicate Customer Payment

**Signal:** Gateway throws HTTP 504; user retries with a brand-new order ID, spawning two business intents.

**Analysis:** Cassandra may have committed CAS before the reply dropped. **Fix:** Stable idempotency keys, status lookup endpoints, reconciliation ledgers, and deduplicated side effects.

### Case 4 — Retried `INSERT IF NOT EXISTS` Returns `false` Even Though First Attempt Committed

**Signal:** Attempt 1 timed out; attempt 2 returns `false`; row already shows attempt 1's `last_op_id`.

**Analysis:** Retry `false` confirms prior creation rather than contradicting it. **Fix:** Reconcile `last_op_id` and revision to mark `VERIFIED_APPLIED`.

### Case 5 — Normal Optimistic Revision Race Blamed on Paxos Bug

**Signal:** A gets `true`, B gets `false` on identical `expected_revision=12`.

**Analysis:** CAS prevented a lost update as designed. **Fix:** Handle optimistic conflict cleanly rather than configuring infinite retries.

### Case 6 — Contention Spikes From "Retry Until `true`" Client Loop

**Signal:** `ConditionNotMet` and CAS QPS surge post-deploy, hammering one key repeatedly.

**Analysis:** Misconfigured retry policy looping on definitive condition rejections. **Fix:** Throttle, fail-fast on conflict, or re-evaluate state with bounded backoff only where domain rules allow.

### Case 7 — CAS p99 Climbs While Cluster Average CPU Looks Low

**Signal:** One hot partition absorbs heavy concurrent writers; cluster-wide CPU stays low.

**Analysis:** Serialization/ballot races focus solely onto that partition's replica set. **Fix:** Cap per-key concurrency, introduce single-writer routing, or redesign the partition/invariant.

### Case 8 — Two Concurrent Writers Pick Distinct Random Keys and Both Win

**Signal:** Both `INSERT IF NOT EXISTS` calls return `true`, violating "one active subscription per customer".

**Analysis:** LWT serializes **per partition key**; invariants scoped by customer cannot live solely on random subscription IDs. **Fix:** Introduce a customer-keyed uniqueness guard + coordinated reconciliation.

### Case 9 — `CASWriteUnknownException` Mapped to `FAILED`

**Signal:** Java exception mapper immediately declares definite failure without saving operation IDs.

**Analysis:** Exception signals **unknown outcome**, zero rollback proof. **Fix:** Map to `UNKNOWN`/`PENDING_VERIFICATION`, store durable operation records, and reconcile.

### Case 10 — Driver Timeout Shorter Than Server Paxos Processing

**Signal:** Client cuts off at 500ms while server completes CAS at 800ms.

**Analysis:** Client cancellation never aborts server consensus in flight. **Fix:** Align deadline budgets, expose status lookups, and block blind retries.

### Case 11 — Raising `cas_contention_timeout` Bloats Queues

**Signal:** Timeout errors dip initially, yet p99, in-flight requests, and memory climb with zero throughput gain.

**Analysis:** Coordinator simply spends longer fighting ballots without reducing contention. **Fix:** Curb concurrent writers per key, apply backpressure, and track CAS latency/contention histograms.

### Case 12 — Speculative Execution Doubles LWT Traffic

**Signal:** Each logical op fires multiple coordinator attempts, pushing `ContentionHistogram` upward.

**Analysis:** Speculative retries enabled on contested LWTs. **Fix:** Disable speculation on non-idempotent CAS, audit `setIdempotent`, and monitor physical vs. logical attempts.

### Case 13 — Service A Uses `SERIAL`, Service B Uses `LOCAL_SERIAL` Across DCs

**Signal:** Team expects strict global ordering while SCL configs diverge across regions.

**Analysis:** Mismatched serialization scopes break global guarantees (`LOCAL_SERIAL` stays local). **Fix:** Align global SCL policies/profiles per invariant and test multi-DC explicitly.

### Case 14 — Row Now Shows Op B; Reconciler Falsely Declares Op A Never Applied

**Signal:** Op A timed out, Op B advanced state afterward, leaving current `last_op_id=B`.

**Analysis:** Current row snapshot erases prior op markers. **Fix:** Query audit ledger/event trail; hold `UNKNOWN` whenever history lacks proof.

### Case 15 — Blind Normal `UPDATE` Corrupts LWT Workflow

**Signal:** Revisions jump backward or states drift oddly even while CAS endpoints pass tests.

**Analysis:** An unguarded writer skipped CAS/revision fencing. **Fix:** Audit every writer, DAO, and batch job; enforce CAS protocol uniformly and check `WRITETIME`.

### Case 16 — Losing One Replica Causes CAS Timeouts

**Signal:** One natural replica goes `DN`/partitioned; CAS calls time out while normal `ONE` reads still succeed.

**Analysis:** LWT serial/normal quorums demand replica counts that `ONE` ignores. **Fix:** Audit RF/CL/DC/replica health, recover node cleanly, and never slash CL blindly.

### Case 17 — All Replicas `UN` Yet Prepare/Propose Lags

**Signal:** Nodes report `UN`, yet CAS p99 climbs alongside GC pauses, disk await, or internode RTT.

**Analysis:** Gossip liveness doesn't guarantee timely Paxos RPCs; ballot contention isn't always sole cause. **Fix:** Track `CasPrepare`/`CasPropose` plus node OS/JVM bottlenecks.

### Case 18 — Reconciler Declares Failure After One `ONE` Read

**Signal:** Client CAS times out; immediate `ONE` read returns old revision.

**Analysis:** `ONE` read hit stale replica or lagged behind in-flight commit. **Fix:** Reconcile using `SERIAL`/contract CL, bounded polling, and audit trails—never equate stale snapshot with rollback.

### Case 19 — Node Rejoins `UN` Yet CAS p99 Stays Degraded

**Signal:** Node returns `UN`, yet CAS ops still trigger `UnfinishedCommit`, GC, disk, or repair overhead.

**Analysis:** Ring availability recovers before latency and backlog normalize. **Fix:** Track CAS metrics, retry/error rates, and reconciliation queues across sustained windows.

### Case 20 — Benchmark Fires 10,000 Clients at One LWT Key

**Signal:** Tiny throughput and sky-high contention lead teams to claim "Cassandra doesn't scale".

**Analysis:** Test benchmarked hot-key serialization rather than distributed partition scaling. **Fix:** Separate hot-key ceiling tests from representative key-distribution benchmarks while preserving domain invariants.

### Case 21 — Conditional Batch Treated as Multi-Partition ACID

**Signal:** App attempts atomic commits across order rows, username guards, Kafka events, and inventory partitions inside one batch.

**Analysis:** Conditional batches never provide global cross-partition or cross-system ACID. **Fix:** Design sagas, inbox/outbox, idempotency, and compensations.

### Case 22 — Duplicate Downstream Emails Even Though CAS Applied Once

**Signal:** Cassandra transitioned state cleanly once, yet crash/retries sent two customer emails.

**Analysis:** LWT protects the Cassandra row only—not post-ACK external I/O. **Fix:** Add outbox/inbox, unique message IDs, idempotent consumers, and status ledgers.

## 22. GO / HOLD / STOP Runbook for LWT Conflicts and Timeouts

### 22.1. Alert-to-Decision Flow

~~~text
ALERT: CAS p99 spike / condition_false surge /
       CASWriteUnknown / HTTP 504 / duplicate side effects
                         |
             1. Identify contract
        keyspace/table/PK/RF/DC/SCL/NCL/query family
                         |
             2. Preserve evidence
        logical_op_id, attempt IDs, timeline, errors
                         |
          +--------------+--------------+
          |                             |
   Definitive result               No definitive result
          |                             |
   [applied] true/false             UNKNOWN_OUTCOME
          |                             |
   Business state path              Quarantine / reconcile
          |                             |
          +--------------+--------------+
                         |
               3. Inspect cluster
     CASRead/CASWrite, replicas, GC/disk, driver retries
                         |
               4. Isolate cause
   contention? normal vs serial CL? hotspot? network?
                         |
               5. Mitigate safely
      throttle per key, hold rollout, heal replicas,
      fix retry policy or data-model protocol
                         |
                6. Verify outcomes
     data oracle + op ledger + SLO + zero duplicate effects
                         |
                    GO / HOLD / STOP
~~~

**Never** ramp traffic back up solely because Java timeouts vanished; inspect **Cassandra CAS telemetry and unknown-outcome reconciliation queues**. Calm p99 graphs alongside thousands of unreconciled `UNKNOWN` payments fail readiness.

### 22.2. Production Triage Preflight

1. **Scope impact:** app build, keyspace/table, query family, opaque/hashed entity IDs, UTC timestamps, local DC.
2. **Lock CL contract:** active normal CL and serial CL on statements, execution profiles, per-DC RF, transient replicas if any.
3. **Log outcome:** `[applied]` true/false vs. exception/unknown? Any driver retries or speculation?
4. **Freeze noise:** hold new deploys and pause authorized non-critical migrations or hotspot-triggering features.
5. **Protect state:** never truncate tables, hand-edit Paxos state/ballots, or force compaction/repair as a panic workaround.
6. **Baseline metrics:** `CASWrite.Latency`, `ConditionNotMet`, contention, timeouts/unknowns, GC/disk/network, driver pools/retries.
7. **Guard business state:** preserve idempotency keys, pending ledgers, and halt blind downstream side-effect replays.
8. **Assign owners:** API owner, Cassandra SRE/DBA, reconciliation owner, and release decision maker.

### 22.3. Read-Only Evidence Collection

~~~bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool tablestats <keyspace>.<table>
~~~

`<keyspace>.<table>` above is a **placeholder** for your authorized target table—never type literal angle brackets. Confirm release-specific `tablestats` syntax in your live shell.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'lwt_lab';

SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

In production, check **only the authorized key under investigation** at approved CL without substituting lab IDs or logging PII. Remember a point read shows current row state only, not complete transition history.

### 22.4. Symptom Triage Table

| Observation | Classification | First move |
|---|---|---|
| High `false`, low timeouts, steady CAS latency | Business conflicts | Audit expected revisions and API contract |
| High `false`, client loops same expected revision | Retry bug | Stop loop; add backoff + business re-evaluation |
| `ContentionHistogram` and p99 climb together | Paxos hotspot | Per-key throttling/ownership; reduce contenders |
| CAS timeouts climb + `DN` nodes or high peer RTT | Replica/network impairment | Hold; restore quorum without dropping CL |
| `CASWriteUnknownException` logged | Unknown outcome | Persist op IDs; drive ledger reconciliation |
| App timeout shorter than server processing | Deadline mismatch | Align deadline budgets; block blind replays |
| Healthy write p99 alongside duplicate emails | Cross-system side effect | Implement outbox/inbox dedupe; leave CAS alone |
| CAS failures post-mixed-version upgrade | Release compatibility skew | Pause rollout; verify version Paxos notes |
| Normal `UPDATE` collides with CAS | Protocol violation | Audit all write paths and enforce fencing |
| Healthy cluster quorum yet high CAS p99 | Contention or capacity | Inspect per-phase CAS latencies and key skew |

### 22.5. GO / HOLD / STOP Gates

| Gate | GO | HOLD | STOP / ESCALATE |
|---|---|---|---|
| **Correctness** | Current/audit state and op IDs uphold invariant | Unknowns reconciling inside budget | Broken state or duplicate irreversible side effects |
| **CAS availability** | Enough replicas for SCL/NCL; errors inside SLO | Replicas healing; thin quorum headroom | CL unavailable on critical keyspace/DC |
| **Contention** | Conflicts match business traffic; stable p99 | Contention rising, not yet saturated | Retry storm overwhelming cluster |
| **Unknown outcomes** | Backlog small, inside RTO, owned | Pending backlog with firm deadline | Missing op IDs/ledger; cannot rule out duplicates |
| **Latency** | CAS p95/p99 and timeouts inside SLO | p99 drifting or retries climbing | Serious guardrail SLO breach |
| **Topology/repair** | Node status, disk, GC, streaming healthy | Catch-up/rejoin still draining | Data-loss risk or near-full disk |

**GO** is always **scoped**: e.g., "Approved `orders.confirm` in `dc1` (RF=3, `LOCAL_SERIAL`/`LOCAL_QUORUM`) up to 500 req/s, p99 ≤ 150ms, unknown backlog cleared < 5 minutes." Example figures are **illustrative**, always replaced with real service SLOs.

### 22.6. Immediate Halt Triggers

- Proven violation of uniqueness or state-machine invariants.
- Same operation ID reused for **two distinct intents**, or retries triggering duplicate external side effects.
- Insufficient natural replicas to satisfy required CL across target token ranges.
- CAS/driver timeouts exceeding error budget with runaway `UNKNOWN` queue growth.
- Disk, commitlog, GC, or compaction faults risking data durability.
- Any proposal to hand-edit `system.paxos`, run unapproved `DROP`/`TRUNCATE`, or mass-stop nodes without a runbook.
- Fault test targeting clusters/namespaces outside the approved allowlist.

### 22.7. Node Recovery vs. Full Business Workflow Recovery

~~~text
Node C UP again                    -> topology recovered
CAS LOCAL_QUORUM starts succeeding -> functional CL recovered
CAS p99 returns to SLO             -> performance recovered
Old UNKNOWN operations reconciled  -> business outcomes recovered
Duplicate effects resolved         -> end-to-end workflow recovered
~~~

These are **five independent gates**. Never close an incident merely because `nodetool status` displays `UN` everywhere or HTTP 5xx dropped while thousands of `UNKNOWN` payments remain unreconciled.

### 22.8. Incident Report Template

~~~text
INCIDENT_ID:
UTC_FIRST_ERROR / UTC_RECOVERY:
SERVICE / RELEASE / QUERY FAMILY:
CASSANDRA VERSION / JAVA DRIVER VERSION:
KEYSPACE / TABLE / PARTITION MODEL:
RF PER DC / LOCAL_DC:
NORMAL_CL / SERIAL_CL:
OPERATION_ID (sanitized), ATTEMPT_IDS:
EXPECTED_REVISION / TARGET_REVISION / BUSINESS INVARIANT:
APPLIED_TRUE / CONDITION_FALSE / UNKNOWN COUNTS:
CASWrite CONTENTION / LATENCY / UNFINISHED_COMMIT:
CASRead METRICS / SERVER GC / DISK / NETWORK:
DRIVER RETRIES / SPECULATION / POOL-INFLIGHT:
RECONCILIATION BACKLOG / VERIFIED / MANUAL_REVIEW:
DATA ORACLE / DOWNSTREAM EFFECTS CHECK:
MITIGATION / ROLLBACK:
GO / HOLD / STOP AND OWNER:
OPEN RISKS / NEXT REVIEW UTC:
~~~

Never write raw customer account numbers, payment cards, secrets, session tokens, or `BoundStatement` parameters into shared logs. Correlate using sanitized opaque op IDs inside RBAC-protected tooling.

### 22.9. Shortcuts That Never Replace Diagnosis

**Never:**

- Raise `cas_contention_timeout` or `write_request_timeout` endlessly.
- Downgrade `LOCAL_QUORUM` to `ONE` just to turn graphs green without reviewing contracts.
- Switch `SERIAL` to `LOCAL_SERIAL` over WAN lag if the invariant requires global ordering.
- Enable blanket driver retries and speculative execution across LWTs.
- Trigger major compactions, unrelated repairs, or irrelevant cache purges.
- Mint a new operation ID on retry just to dodge `[applied]=false`.
- Delete row or ledger records on HTTP 504s while outcome stays `UNKNOWN`.

Every shortcut above either **destroys forensic evidence or widens uncertainty**. Instead: preserve operation identity, quantify contention, shed concurrent writers per key, heal replicas, and reconcile within deadlines.

## 23. LWT Production Acceptance Checklist

### 23.1. Data Modeling & Invariants

- [ ] Domain invariant stated explicitly (uniqueness, valid transitions, ownership).
- [ ] Guard key / partition key matches the exact invariant boundary.
- [ ] Zero assumptions that CAS across random distinct partitions enforces global uniqueness.
- [ ] Every writer updating that entity follows the identical LWT/fencing protocol.
- [ ] Monotonic revision or version token guards against stale writers and ABA races.
- [ ] Operation ID minted **once per logical intent**.
- [ ] `last_op_id` marker persisted atomically inside conditional mutations where feasible.
- [ ] Audit/status ledger exists whenever sequential transitions overwrite current `last_op_id`.
- [ ] Cross-partition/cross-service side effects protected via saga, outbox/inbox, and compensation.
- [ ] No global counter or hot-key LWT deployed without validated throughput sizing.

### 23.2. CQL & Driver Contract

- [ ] `INSERT IF NOT EXISTS` / `UPDATE IF` / `DELETE IF` bind full primary key and conditions.
- [ ] Normal writes clearly separated from conditional LWTs (not hidden inside ambiguous method names).
- [ ] Both normal CL and serial CL explicitly configured.
- [ ] `LOCAL_SERIAL` vs. `SERIAL` scope vetted against multi-DC topology.
- [ ] `ResultSet.wasApplied()` invoked strictly on conditional DML.
- [ ] `[applied]=false` handled explicitly as domain conflict rather than infrastructure crash.
- [ ] `CASWriteUnknownException` and write/client timeouts never mapped to definite failure.
- [ ] `setIdempotent(true)` enabled solely with formal proof rather than convention.
- [ ] Speculative execution blocked from multiplying LWT proposals outside policy.
- [ ] Retry budgets, backoff/jitter, max in-flight caps, and request deadlines aligned.

### 23.3. Reconciliation

- [ ] Durable tracking exists for every `PENDING`/`UNKNOWN` operation.
- [ ] Current row, op ID, and revision can be queried cleanly by primary key.
- [ ] Serial/contract CL reads run where needed to flush pending Paxos commits.
- [ ] Zero transitions from `UNKNOWN` to `FAILED` based solely on a single `ONE` read.
- [ ] Full ledger/history covers cases where newer ops supersede `last_op_id`.
- [ ] Unknown outcomes blocked from triggering duplicate charges, emails, or external emits.
- [ ] Permitted post-reconciliation retries reuse identical op ID and expected revision.
- [ ] Escalation and manual-review path exists when proof remains inconclusive.
- [ ] Reconciler enforces bounded retry budgets and rate limits.
- [ ] Operation record retention spans maximum client retry windows.

### 23.4. Monitoring & Capacity

- [ ] `CASRead` / `CASWrite` latencies tracked separately from normal reads/writes.
- [ ] `ConditionNotMet` tracked distinctly from infrastructure errors.
- [ ] `ContentionHistogram`, `UnfinishedCommit`, timeouts, and failures monitored.
- [ ] Breakdowns segmented by query family, DC, CL, and time window.
- [ ] Client logical requests, physical attempts, retries, and speculation compared together.
- [ ] Per-node GC, disk await, internode RTT, and stage backpressure correlated.
- [ ] Hot-key skew monitored safely without leaking PII or high-cardinality Prometheus labels.
- [ ] Benchmarks reproduce realistic contenders/key and skewed key distributions.
- [ ] CL correctness monitored alongside client p95/p99 and error budgets.
- [ ] Alert SLOs cover reconciliation backlog size and age, not solely request latency.

### 23.5. Operations & Safety

- [ ] Fault drills confined exclusively to approved lab/staging clusters.
- [ ] Zero manual tampering with Paxos internals (`system.paxos` or system tables).
- [ ] Zero node shutdowns or production RF/CL edits used to simulate contention.
- [ ] Zero `DROP`/`TRUNCATE` shortcuts on real data to "clear conflicts".
- [ ] Explicit GO/HOLD/STOP release gates and rollback owners defined.
- [ ] Topology/CL recovery separated cleanly from business-outcome reconciliation.
- [ ] No incident closed while unowned unresolved `UNKNOWN` operations linger.
- [ ] Any CL, SCL, or retry-policy change covered by integration regression tests.
- [ ] RF=1 lab limitations clearly separated from RF=3/multi-DC production proof.
- [ ] STEP 4 authors documentation only; compilation, fault runs, and STEP 6 Content QA happen in downstream review stages.

## 24. Self-Assessment Questions and Suggested Answers

**Q1.** Why can't `SELECT` then `UPDATE` at `QUORUM` replace CAS?  
**A:** A TOCTOU race exists between the Java check and normal write; ordinary writes do not enforce conditions atomically.

**Q2.** Which CQL statement inserts a row only when the key does not exist yet?  
**A:** `INSERT ... IF NOT EXISTS`.

**Q3.** Which CQL statement enforces an expected revision prior to updating?  
**A:** `UPDATE ... SET ... WHERE full_primary_key ... IF revision = n`.

**Q4.** What does `[applied]=true` tell you?  
**A:** That attempt's conditional mutation received a definitive server confirmation that it applied.

**Q5.** Does `[applied]=false` indicate a Cassandra timeout?  
**A:** No; the condition failed—typically a normal domain conflict.

**Q6.** If an LWT times out with no response, can you return "definitely rolled back"?  
**A:** No; the commit may already have applied or be completing in flight.

**Q7.** Which Java Driver method inspects the `[applied]` column?  
**A:** `ResultSet.wasApplied()` on conditional DML statements.

**Q8.** What does `wasApplied()` return on an ordinary non-conditional `INSERT`?  
**A:** `true` by API convention—it **never** proves an ordinary `INSERT` used LWT.

**Q9.** Why might retrying `INSERT IF NOT EXISTS` after a lost ACK return `false`?  
**A:** Attempt 1 actually inserted the row, so "if not exists" evaluates false on retry.

**Q10.** Does `[applied]=false` on attempt 2 prove the overall logical operation failed?  
**A:** No; attempt 1 may have succeeded before its reply dropped.

**Q11.** Which consensus protocol powers Cassandra LWT?  
**A:** Paxos.

**Q12.** Why shouldn't you hardcode "every LWT takes exactly four network round trips"?  
**A:** Cassandra 4.1+ Paxos optimizations/fast paths vary round-trip counts by release, contention, and recovery state.

**Q13.** What does serial consistency level govern?  
**A:** The Paxos consensus scope during the conditional evaluation phase.

**Q14.** What does normal CL on a conditional write govern?  
**A:** Commit/learn phase ACKs and subsequent normal read visibility guarantees.

**Q15.** Do `SERIAL` and `LOCAL_SERIAL` share the same scope?  
**A:** No; `LOCAL_SERIAL` stays scoped to the local DC and does not enforce cross-DC global serialization.

**Q16.** In multi-DC setups, do writers in separate DCs using `LOCAL_SERIAL` maintain a shared global invariant?  
**A:** Do not assume so; global invariants require a unified serialization scope and multi-DC verification.

**Q17.** If a `ONE` read right after an LWT timeout shows stale state, is that proof the write didn't apply?  
**A:** No; stale replicas or uncommitted in-flight Paxos rounds can lag behind.

**Q18.** Does `CONSISTENCY LOCAL_QUORUM` automatically change `SERIAL CONSISTENCY` in `cqlsh`?  
**A:** No; they are independent settings.

**Q19.** What extra work can a serial read perform compared with an ordinary `SELECT`?  
**A:** It helps drive/learn pending uncommitted Paxos state per consensus rules—at extra latency cost.

**Q20.** What does `CASWriteUnknownException` indicate?  
**A:** CAS commit state is indeterminate; trigger reconciliation rather than assuming rollback.

**Q21.** Does `WriteTimeoutException.getReceived()` count committed business writes?  
**A:** No; it counts coordinator replies received relative to `blockFor` before timing out.

**Q22.** Does `DriverTimeoutException` guarantee a request never reached Cassandra?  
**A:** No; the client deadline can expire after the server already executed the statement.

**Q23.** Why must an operation ID stay constant across retries?  
**A:** To correlate identical logical intent and stop duplicate records or side effects.

**Q24.** How should attempt IDs and operation IDs be generated?  
**A:** Fresh attempt ID per network call; **shared constant operation ID** across all retries of that logical operation.

**Q25.** Does `last_op_id` in the row prove every historical action that ever ran?  
**A:** No; subsequent transitions overwrite it—full history requires a separate audit ledger.

**Q26.** Why can't finding current `revision=10` prove an old timed-out operation never ran?  
**A:** Later valid transactions may have incremented past it; current state isn't full event history.

**Q27.** What is the ABA problem?  
**A:** State changing A→B→A tricks naive value-only checks (`IF status='A'`) into matching stale state; monotonic revisions prevent it.

**Q28.** Why shouldn't all LWT statements carry `setIdempotent(true)`?  
**A:** Automatic retries/speculation can flip applied outcomes and duplicate downstream effects.

**Q29.** How does speculative execution worsen LWT contention?  
**A:** A single logical write spawns competing CAS ballots across coordinators for the same key.

**Q30.** Does high `ConditionNotMet` always mean Cassandra is broken?  
**A:** No; it frequently reflects legitimate optimistic concurrency conflicts.

**Q31.** Which metrics directly measure Paxos contention?  
**A:** `CASWrite.ContentionHistogram` and `CASRead.ContentionHistogram`.

**Q32.** What does `UnfinishedCommit` count?  
**A:** Prior incomplete Paxos transactions resolved during CAS read or write execution.

**Q33.** Does `CASWrite.Latency` differ from normal `WriteLatency`?  
**A:** Yes; CAS tracks separate consensus-coordinated conditional requests.

**Q34.** Why can cluster-wide average CPU mask LWT contention?  
**A:** Contention pins only the hot partition's natural replica set while remaining cluster nodes sit lightly loaded.

**Q35.** Does adding cluster nodes automatically multiply throughput on one hot partition?  
**A:** No; every CAS on that key still serializes through the same single-partition Paxos slot.

**Q36.** Can you shard a uniqueness guard key randomly to scale faster?  
**A:** No, not if doing so breaks global uniqueness without an overarching coordination protocol.

**Q37.** What does `cas_contention_timeout` control?  
**A:** How long coordinators retry resolving Paxos contention—not a fix for hot-key overload.

**Q38.** Does cranking server timeouts sky-high guarantee higher CAS throughput?  
**A:** No; it increases queued requests, memory pressure, and delayed unknown outcomes.

**Q39.** How does `UnavailableException` differ from `[applied]=false` on LWT?  
**A:** `Unavailable` signals missing replica quorum; `[applied]=false` is a definitive condition mismatch reply.

**Q40.** Why inspect `getAllErrors()` on `AllNodesFailedException`?  
**A:** Individual coordinators fail for distinct reasons (timeouts, unknowns, routing errors).

**Q41.** If Cassandra committed the operation ID once yet emails sent twice, where is the bug?  
**A:** Missing outbox/inbox or idempotent consumer protection on external side effects; LWT doesn't span external APIs.

**Q42.** Does CAS on random `subscription_id` enforce one active subscription per customer?  
**A:** No; separate subscription UUIDs target separate partitions—guard on customer scope instead.

**Q43.** Why must fault injection know the exact natural replicas of a test key?  
**A:** Stopping a non-replica node may barely affect CAS quorum, yielding false resilience conclusions.

**Q44.** What does a single-node RF=1 lab demonstrate cleanly?  
**A:** CQL conditional syntax and basic Java Driver handling—never multi-node quorum contention or failover recovery.

**Q45.** Once restarted nodes return `UN`, can you close an incident with unreconciled `UNKNOWN` transactions?  
**A:** No; ring recovery is not business-outcome reconciliation.

**Q46.** Which evidence takes priority when reconciling `UNKNOWN` outcomes?  
**A:** Stable operation ID, expected revision/state, serial/contract-CL reads, and audit history where required.

**Q47.** What should happen when bounded retries still yield inconclusive evidence?  
**A:** Keep the record in `PENDING_VERIFICATION` / `MANUAL_REVIEW` with an owner rather than assuming failure and replaying blindly.

**Q48.** When is scaling LWT traffic back up safe post-incident?  
**A:** Once SCL/NCL/replicas hold, invariants and data oracles verify, contention/p99/errors meet SLOs, `UNKNOWN` queues drain cleanly, and downstream deduplication holds.

## 25. Summary: LWT Protects Predicates—Never Guaranteeing Client Receipt

~~~text
                   BUSINESS INTENT
             entity_id + stable operation_id
             expected_revision + target_state
                           |
                           v
                    CQL UPDATE ... IF
              SERIAL/LOCAL_SERIAL + normal CL
                           |
              +------------+-------------+
              |                          |
        Client gets reply         No definitive reply
              |                          |
       +------+-------+             UNKNOWN_OUTCOME
       |              |                   |
  applied=true    applied=false          v
       |              |             RECONCILE / AUDIT
  APPLIED       CONDITION_NOT_MET          |
       |              |              +----+----+
       |      Re-evaluate rule       |         |
       |                             |         |
       |                        PROOF       NO PROOF
       |                             |         |
       |                   VERIFIED OUTCOME  PENDING/
       |                                     MANUAL REVIEW
       +----------------------+------------------+
                              |
                   End-to-end side effects
               outbox/inbox/idempotent handlers
                              |
                  GO / HOLD / STOP gate
~~~

### 25.1. Seven Core Principles to Remember

1. **Condition conflict ≠ infrastructure error:** `[applied]=false` is often valid domain behavior—never alert or blindly retry it as a timeout.
2. **Contention carries real cost:** competing writers on one Paxos slot escalate ballot retries, tail latency, and timeouts; monitor `CASWrite` metrics, per-key skew, and physical attempts.
3. **Two CLs have distinct duties:** `SERIAL`/`LOCAL_SERIAL` governs Paxos consensus; normal `QUORUM`/`LOCAL_QUORUM`/etc. governs commit/learn visibility—size both to RF/DC and invariants.
4. **Missing ACK ≠ confirmed rollback:** `CASWriteUnknownException`, timeouts, or socket drops often follow server commits; hold `UNKNOWN` until verified.
5. **Logical operation ≠ network attempt:** preserve **constant operation IDs** and revision fencing—never mint new business IDs on retries.
6. **Current snapshot ≠ historical audit log:** newer writes overwrite `last_op_id`; maintain ledgers/audit trails wherever multi-step sequences follow.
7. **LWT does not buy system-wide exactly-once:** cross-partition invariants and external calls still demand state machines, outbox/inbox, deduplication, sagas, and reconciliation.

### 25.2. Quick Diagnostic Lookup by Signal

| Signal | Priority question | Primary direction |
|---|---|---|
| `[applied]=false` | Is expected revision/condition stale? | Business conflict and rule re-evaluation |
| Rising `ContentionHistogram` | Are too many writers racing one entity? | Throttle, serialize per key, or revisit partition design |
| Rising `CASWrite.Timeouts` | Replica/GC/network or contention? | Check RF/SCL/NCL and per-node resource health |
| `CASWriteUnknownException` | Are operation ID and durable ledger saved? | `UNKNOWN` → bounded reconciliation |
| `DriverTimeoutException` | Might the request have executed on a node? | Never blind-replay; preserve trace/unknown state |
| High `ConditionNotMet` with flat p99 | Normal domain race vs. retry loop? | Check query family and attempt-to-op ratio |
| Duplicate emails / charges | Are downstream side effects deduplicated? | Outbox/inbox and compensation logic |
| All nodes `UN` yet unknowns linger | Have pending operations reconciled? | Business-outcome recovery beyond ring health |

**Practical takeaway:** Never declare "Cassandra LWT works fine" simply because an `INSERT IF NOT EXISTS` returned `true`. Reliable production LWT architectures prove **sound invariants and partition keys, explicit serial/normal CL contracts, clear separation of `false` vs. `UNKNOWN`, preserved operation identity, contention telemetry, and deadline-bound reconciliation even when replies vanish**.

### 25.3. Lab Scope Limits and Next QA Stages

Single-node CQL and Java examples illustrate conditional semantics and Driver usage only—never proving WAN Paxos stability, replica crashes, repair/compaction stress, or cross-service workflows. Validate real fault drills in isolated staging with full RF/DC and stop/recovery guardrails. Per content workflow, **STEP 4 authors Markdown** without running Gradle, fault injection, or STEP 6 Content QA; domain experts verify versions, compilability, and case validation downstream.

## Technical References

- [Apache Cassandra — Guarantees, lightweight transactions and linearizability](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html) — Paxos/CAS foundations and consistency bounds.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `INSERT IF NOT EXISTS`, `UPDATE IF`, `DELETE IF`, and partition/row semantics.
- [Apache Cassandra — cqlsh and serial consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — separating `CONSISTENCY` vs. `SERIAL CONSISTENCY` and commit visibility.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `CASRead`/`CASWrite`, `ConditionNotMet`, `ContentionHistogram`, `UnfinishedCommit`, `CasPrepare`, and `CasPropose`.
- [Apache Cassandra — Cassandra 4.1 improvements](https://cassandra.apache.org/_/blog/Cassandra-4.1-is-here.html) — Paxos improvements and round-trip/latency evolution vs. earlier versions.
- [Apache Cassandra — cassandra.yaml 4.1](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html) — `cas_contention_timeout`, `write_request_timeout`, and server budgets.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — tokens, replicas, RF/CL, and foundational consistency.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair (distinct from clearing Paxos contention).
- [Apache Java Driver 4.18.1 — ResultSet.wasApplied Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ResultSet.html) — reading `[applied]` and behavior on non-conditional queries.
- [Apache Java Driver 4.18.1 — CASWriteUnknownException Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/CASWriteUnknownException.html) — indeterminate CAS write outcomes.
- [Apache Java Driver 4.18.1 — WriteTimeoutException Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html) — `WriteType`, `received`, and `blockFor`.
- [Apache Java Driver 4.18.1 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — idempotence, retry behavior, and timeout handling.
- [Apache Java Driver 4.18.1 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.1/core/statements/prepared/) — prepared/bound statements and reuse.
- [Apache Java Driver 4.18.1 — Request throttling](https://apache.github.io/cassandra-java-driver/4.18.1/core/throttling/) — driver backpressure, queues, and concurrency limits.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — assertions, lifecycles, and concurrency testing.
