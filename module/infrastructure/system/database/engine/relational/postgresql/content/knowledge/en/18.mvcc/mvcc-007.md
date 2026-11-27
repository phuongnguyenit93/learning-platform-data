# Serializable Snapshot Isolation and Dangerous Dependency Detection in PostgreSQL

**Serializable Snapshot Isolation (SSI)** is the mechanism PostgreSQL uses to enforce the `SERIALIZABLE` transaction isolation level in a concurrent multi-transaction environment. It combines the benefits of reading via **MVCC snapshots** with **tracking read–write dependencies** to detect execution schedules that risk not being equivalent to any serial execution order. Rather than always locking and forcing transactions to run one after another, PostgreSQL normally lets them proceed and **aborts a transaction when necessary** to preserve serializability of committed transactions.

The hard part of SSI is not the syntax:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

but rather the question: **Why can two transactions that both read committed data, both have consistent snapshots, and update different rows still be unable to both commit?** The answer lies in **dangerous structures** of dependencies between transactions.

This lesson belongs to the **MVCC** chapter of the *Database Engine Relational PostgreSQL* module. It covers snapshot isolation, serialization graphs, `rw-antidependency`, how SSI uses `SIReadLock`, two-session write skew examples, interpreting `SQLSTATE 40001`, full-transaction retries, `DEFERRABLE` read-only transactions, operational monitoring, and practice exercises.

## 1. Why Can Consistent Snapshots Still Produce Wrong Results?

Suppose a hospital has two doctors, An and Bình, and both are on call. The business rule is:

> At every moment after commit, at least one doctor must be on call.

Either doctor can go off call if at least two people are currently on call. Two concurrent transactions execute:

~~~text
Initially:
  An.on_call   = true
  Bình.on_call = true
  count(on_call = true) = 2

T1 (An requests leave)            T2 (Bình requests leave)
-------------------------------- --------------------------------
Read count = 2                   Read count = 2
An.on_call = false               Bình.on_call = false
COMMIT                           COMMIT

Result if both commit:
  An.on_call   = false
  Bình.on_call = false
  count = 0   <-- Invariant violated
~~~

Each transaction reads **a valid snapshot**; neither reads uncommitted data. T1 and T2 also update **two different rows**, so they do not necessarily contend on the same row lock.

This is **write skew**: two transactions read a shared condition yet write to different parts of the data, causing the combined changes to violate an invariant.

### 1.1. What Does Snapshot Isolation Solve?

Under PostgreSQL's `REPEATABLE READ`, a transaction uses a consistent snapshot. It prevents two normal `SELECT` queries in the same transaction from seeing different newer commits. This eliminates nonrepeatable reads and traditional phantom reads.

However, a consistent snapshot only guarantees **each transaction sees a stable slice**, not that **the combined outcome of multiple transactions** remains equivalent to serial execution.

### 1.2. What Does SERIALIZABLE Solve?

If the two transactions above ran serially:

~~~text
Order T1 -> T2:

T1 reads count = 2, lets An go off call, commits.
T2 reads count = 1, does NOT let Bình go off call.
Result: Bình stays on call.
~~~

Reversing the order T2 → T1 behaves similarly: whichever runs second observes only one doctor left and denies the request.

A schedule in which both read `count = 2` and both commit going off call is **not equivalent** to any valid serial order, assuming both transactions check the invariant before updating. SSI prevents that schedule from committing.

## 2. Reviewing MVCC and PostgreSQL Isolation Levels

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)** to manage visibility of row versions. Transactions do not have to lock the entire database on every read.

A simple diagram:

~~~text
Time s0: row X = 100  [committed]
T1 takes snapshot S1
T2 updates X = 200 and COMMITs
T1 SELECT X can still see version 100 under S1
T3 takes a new snapshot and sees version 200
~~~

This is a logical visibility model, not a complete physical heap/vacuum diagram.

### 2.1. Four Names, Three Core Behaviors

| SQL Isolation | PostgreSQL Implementation | Key Point |
|---|---|---|
| `READ UNCOMMITTED` | Like `READ COMMITTED` | No dirty reads |
| `READ COMMITTED` | Per-statement snapshot for normal queries | Each `SELECT` can see newer commits |
| `REPEATABLE READ` | Snapshot isolation | Stable snapshot; write skew still possible |
| `SERIALIZABLE` | Serializable Snapshot Isolation | Tracks conflicts and aborts if schedule is unsafe |

### 2.2. Quick Comparison

| Anomaly | READ COMMITTED | PostgreSQL REPEATABLE READ | PostgreSQL SERIALIZABLE |
|---|---|---|---|
| Dirty read | Prevented | Prevented | Prevented |
| Nonrepeatable read | Possible | Prevented in `SELECT` snapshot | Prevented in valid committed schedules |
| Traditional phantom read | Possible | Prevented in `SELECT` snapshot | Prevented |
| Cross-statement read skew | Possible | Avoided via snapshot | Avoided |
| Write skew | Possible | **Possible** | Prevents non-serializable commit schedules |
| Serialization failure `40001` | Possible in certain cases depending on mechanics | Possible on concurrent updates | **Core part of the SSI mechanism** |

`SERIALIZABLE` does not mean every operation always succeeds. It means **successfully committed transactions** must satisfy serializability. A transaction may be rejected to preserve that property.

### 2.3. When Does the Snapshot Begin?

In a `REPEATABLE READ`/`SERIALIZABLE` transaction, the appropriate snapshot is normally established when the first statement requiring a snapshot executes, **not simply when typing `BEGIN`**.

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM some_table;

COMMIT;
~~~

This SQL illustrates structure; `some_table` must exist if run verbatim. In two-session experiments, ensure the first `SELECT` has run in each session before the other transaction modifies and commits, so the snapshots you want to compare are established.

## 3. Serializability: What Does Serial Equivalence Mean?

A transaction schedule is **serial** if all operations of one transaction finish before another transaction begins its logical operations:

~~~text
Serial schedule 1:
  T1: READ -> CHECK -> WRITE -> COMMIT
  T2: READ -> CHECK -> WRITE -> COMMIT

Serial schedule 2:
  T2: READ -> CHECK -> WRITE -> COMMIT
  T1: READ -> CHECK -> WRITE -> COMMIT
~~~

In practice, PostgreSQL wants many transactions to **interleave** to increase throughput. Serializability requires the interleaved schedule's outcome to match **some** serial order.

### 3.1. Does Not Mean Physical Serialization

PostgreSQL does not force all `SERIALIZABLE` transactions into a single queue. Two non-conflicting transactions can still run concurrently and commit.

### 3.2. Does Not Mean "ID Order Equals Commit Order"

Sequences or identity columns do not represent the serial order of entire transactions. One transaction may receive an ID earlier yet commit later. Never use `id` to deduce all happens-before relationships in an application.

### 3.3. Does Not Mean Every Business Rule Is Known Automatically

If a transaction merely runs:

~~~sql
UPDATE doctors SET on_call = FALSE WHERE doctor_id = 1;
~~~

without checking whether someone else remains on call, SSI cannot invent a rule that was never expressed. Isolation protects **concurrent execution of decisions expressed in code or constraints**, not missing business logic.

## 4. Serialization Graph: Modeling Dependencies Between Transactions

To understand SSI, use a graph:

- **Vertices:** transactions.
- **Directed edges:** one transaction must precede another in an equivalent serial order because they accessed the same data in a meaningful dependency relationship.

Example:

~~~text
T1 ------> T2 ------> T3

A valid order must have:
T1 before T2, T2 before T3.
~~~

If the graph simultaneously requires:

~~~text
T1 ------> T2
^           |
|           v
+-----------+
~~~

there is a **cycle**, and vertices cannot be arranged in any serial order satisfying all edges.

### 4.1. Three Dependency Types to Know

In MVCC/serialization-graph analysis, three relationships are distinguished:

| Relationship | How to Read It | Conceptual Meaning |
|---|---|---|
| `wr` | Write → Read | T2 reads data written by T1 |
| `ww` | Write → Write | T2 writes a version/entity after T1 |
| `rw` | Read → Write | T1 reads a state without seeing a change written by T2; also called an anti-dependency |

The centerpiece of SSI is **`rw-antidependency`**.

### 4.2. Edges Are Not Simple Statement Execution Order

Graph edges are not created merely because "T1 ran a `SELECT` before T2 ran a `SELECT`." Dependencies reflect **read/write constraints over shared data or predicates**.

To reason accurately, look at which row versions were read, which data was written, and which snapshots saw those changes.

## 5. Write–Read Dependency: T2 Reads T1's Result

Conceptual example:

~~~text
T1: W(X=200), COMMIT
T2: R(X) -> 200
~~~

T2 reads the version of X created by T1. There is an edge:

~~~text
T1 --wr--> T2
~~~

In any equivalent serial order, T1 must precede T2 so T2 reads the value produced by T1.

### 5.1. Do Not Confuse wr With Dirty Read

Here T2 reads a **committed and visible version**, not an uncommitted version. PostgreSQL already disallows normal dirty reads between transactions.

### 5.2. A Single wr Alone Is Not an Error

T2 reading T1's committed value is normal behavior. It imposes an ordering constraint, not a serialization anomaly by itself.

## 6. Write–Write Dependency: Multiple Transactions Modify the Same Data

Suppose:

~~~text
T1: W(X=150), COMMIT
T2: W(X=170), COMMIT
~~~

We can express the constraint:

~~~text
T1 --ww--> T2
~~~

T2 writes after the version created by T1.

### 6.1. PostgreSQL Coordinates Same-Row Updates

Transactions updating the same row pass through row locking and concurrency checks. Under `REPEATABLE READ` or `SERIALIZABLE`, updating a row modified after the snapshot can raise an error like:

~~~text
could not serialize access due to concurrent update
SQLSTATE 40001
~~~

### 6.2. ww Does Not Solve Write Skew

In the doctors example:

~~~text
T1 writes doctor_id=1
T2 writes doctor_id=2
~~~

The two transactions do not write to **the same row**. Standard `ww`/row-lock conflict detection is not enough to catch violations of "at least one person remains on call." We need to track **`rw`-antidependencies**.

## 7. Read–Write Antidependency: The Core of SSI

An **`rw`-antidependency** occurs when T1 reads a version/state under its snapshot while T2 makes a change that T1 **does not see**. To preserve T1's read result in an equivalent serial schedule, T1 must be ordered **before** T2 with respect to that relationship.

Notation:

~~~text
T1 --rw--> T2
~~~

Example:

~~~text
Initial X = 100

T1                           T2
---------------------------- ----------------------------
BEGIN; takes snapshot S1
R(X) -> 100
                             W(X=200)
                             COMMIT
T1 does not see 200 under S1
~~~

The edge `T1 --rw--> T2` reflects that T1's snapshot does not contain the new version created by T2.

### 7.1. Why Is It Called an Anti-Dependency?

It points opposite to a normal `wr` edge:

- `wr`: T2 **reads** what T1 wrote.
- `rw`: T1 **did not read** what T2 wrote because that version fell outside T1's snapshot.

### 7.2. Impact on WHERE Clauses

T1 does not have to read a specific existing row to create an `rw`-antidependency. If T1 queries:

~~~sql
SELECT COUNT(*)
FROM reservations
WHERE room_id = 10
  AND status = 'confirmed';
~~~

and T2 `INSERT`s a row matching that predicate which T1 does not see, the two transactions can form an `rw` dependency involving the **queried row set**.

That is why PostgreSQL must track **predicate reads**, not just locks on already-existing rows.

### 7.3. A Single rw Edge Is Not Always an Error

Many normal `SERIALIZABLE` transactions have `rw` dependencies and remain completely serializable.

For example, T1 reads a configuration, and T2 updates it afterward; without another cycle-closing dependency, the schedule is equivalent to "T1 before T2."

SSI focuses on **combinations of dependencies** that pose risk, rather than aborting every time previously read data is updated.

## 8. Dangerous Structure: Two Consecutive rw Edges

In Serializable Snapshot Isolation analysis, one pattern is especially significant:

~~~text
T_in  --rw-->  T_pivot  --rw-->  T_out
                  ^
                  |
                pivot
~~~

Three transactions play three roles:

- **`T_in`**: a transaction with an anti-dependency pointing **into** the pivot.
- **`T_pivot`**: the middle transaction, having both an incoming `rw` edge and an outgoing `rw` edge.
- **`T_out`**: the transaction at the end of the structure.

This is called a **dangerous structure** — a necessary indicator of special serialization cycles that lead to anomalies under snapshot isolation.

### 8.1. Why Are Two rw Edges Important?

A cycle in a serialization graph can contain `wr`, `ww`, and `rw` edges. SSI theory proves that non-serializable cycles under snapshot isolation exhibit a pattern involving **two consecutive `rw` edges**; that gives PostgreSQL a way to detect risk without building and checking the entire historical graph naively.

### 8.2. Commit-Order Optimization Conditions

Not every pair of consecutive `rw` edges necessarily forms a cycle. The **commit order** among involved transactions also helps distinguish dangerous schedules. In particular, structures that actually produce anomalies satisfy constraints on the final transaction—often expressed as **`T_out` committing early** in the dangerous chain.

This underpins optimizations in PostgreSQL's SSI to avoid unnecessary aborts. Do not reduce the algorithm to "whenever you see two `rw` edges, roll back immediately," because the implementation also checks overlap, commit states, and read-only cases.

### 8.3. Dangerous Structures Are a Conservative Indicator

A dangerous structure **can** appear even when the full schedule is actually serializable because no path closes the cycle. When PostgreSQL aborts to prevent that risk, it may be a **false positive for an anomaly**, not a sign of corrupted data or a PostgreSQL bug.

Safety guarantees take precedence over allowing every technically serializable schedule to commit.

## 9. Write Skew Through the Lens of rw Dependencies

Return to the doctors schedule.

~~~text
Initially: An=true, Bình=true

T1 reads both doctors on call.
T2 reads both doctors on call.

T1 writes An=false.
T2 writes Bình=false.
~~~

Dependencies:

~~~text
T1 read Bình=true, and did not see T2 write Bình=false
    => T1 --rw--> T2

T2 read An=true, and did not see T1 write An=false
    => T2 --rw--> T1

Graph:
       rw
   T1 -----> T2
    ^         |
    |         |
    +---------+
        rw
~~~

This cycle proves no serial schedule can explain **both read outcomes and both writes**.

### 9.1. Two Transactions Are Enough to Form a Cycle

A dangerous structure is often drawn with three positions `T_in`, `T_pivot`, `T_out`, yet in a two-transaction cycle, the start and end roles are played by the same transaction in the dependency pattern.

Not every anomaly requires three distinct transactions.

### 9.2. Why Doesn't REPEATABLE READ Prevent It?

Each transaction sees a snapshot containing both doctors on call. Neither updates the same row, so direct update-conflict detection does not force one transaction to fail as it would on a shared row.

`REPEATABLE READ` guarantees **consistent snapshots**, not the absence of dependency cycles across multiple snapshots.

### 9.3. Why Does SERIALIZABLE Prevent It?

SSI tracks the relevant reads and writes. If both transactions try to commit the write-skew state, PostgreSQL detects the unsafe dependency structure and prevents one transaction from committing in that schedule.

Normally the application receives `SQLSTATE 40001` and must re-run the entire aborted transaction.

## 10. Detecting Predicate Dependencies: Non-Existent Rows Matter Too

A common race condition:

1. T1 asks "Does room 101 have any overlapping booking?" → none.
2. T2 also asks → none.
3. T1 `INSERT`s booking A.
4. T2 `INSERT`s booking B overlapping A's hours.
5. Both commit → double booking.

If you only lock **existing bookings**, an empty predicate has no rows to lock. The problem lies in **reading an absence** while another transaction inserts a row matching that condition.

### 10.1. Predicate Reads Are Part of the Logic

~~~sql
SELECT NOT EXISTS (
    SELECT 1
    FROM bookings
    WHERE room_id = 101
      AND status = 'confirmed'
      AND starts_at < TIMESTAMPTZ '2026-11-14 12:00+07'
      AND ends_at > TIMESTAMPTZ '2026-11-14 11:00+07'
) AS free_slot;
~~~

Inside one transaction, this `SELECT` can return `true`. That does not guarantee nobody else can `INSERT` an overlapping booking concurrently.

### 10.2. SSI Records Predicate Reads

Under `SERIALIZABLE`, PostgreSQL records read information across the appropriate data range to detect if another transaction writes into the range the first transaction observed.

If both run the same check and then `INSERT` under their own snapshots, `rw` dependencies trigger a serialization failure. Where schema design allows, an **exclusion constraint** on time ranges is also a strong way to prevent overlapping bookings, especially with many writers.

### 10.3. Row Locks Are Not Predicate Locks

~~~sql
SELECT *
FROM bookings
WHERE room_id = 101
FOR UPDATE;
~~~

This locks **the selected rows** under row-locking semantics; it does not lock all future rows that might be `INSERT`ed later. When the query returns zero rows, it does not lock a "gap" unless a separate suitable mechanism/protocol is used.

## 11. SIReadLock: How PostgreSQL Tracks What Was Read

In Serializable Snapshot Isolation, PostgreSQL uses read-tracking locks commonly shown with mode **`SIReadLock`**.

The word "lock" can be misleading because its purpose differs from pessimistic row locks used for read–modify–write blocking.

### 11.1. SIReadLock Does Not Block Writes Like FOR UPDATE

- `SELECT ... FOR UPDATE` makes other transactions wait when trying to modify locked rows.
- `SIReadLock` exists to **track read–write conflicts for serialization decisions**; it does not simply block all `UPDATE`/`INSERT`s on read data.

Thus, two `SERIALIZABLE` transactions can normally keep running, and one is aborted if dependencies form an unsafe schedule.

### 11.2. Predicate Tracking Has Granularity Levels

Depending on the query plan, scanned region, and available resources, PostgreSQL can track at the level of:

- Tuple / row.
- Page.
- Relation / table.

Coarser tracking can cause more writes to appear related to a read region, increasing the rate of serialization failures that are unnecessary from a pure business standpoint.

### 11.3. Sequential Scans Can Widen Tracking Scope

A sequential scan reading the entire table can produce broader `SIREAD` tracking than an index scan narrowing the dataset. An appropriate index can sometimes avoid conservative conflicts, though exact behavior depends on planner, data, and query.

**Never create an index solely because you saw `SIReadLock`.** Evaluate predicates, `EXPLAIN`, `40001` frequency, and write/index maintenance costs first.

### 11.4. SIREAD Locks May Still Be Needed After COMMIT

Read-tracking metadata may be retained long enough to detect dependencies with overlapping `SERIALIZABLE` transactions, rather than being released completely like a row lock as soon as the reading transaction commits.

Never assume "the transaction committed, so all its conflict-tracking marks must vanish immediately."

## 12. How Does SSI Differ From Strict Two-Phase Locking?

Another way to guarantee serializability is locking reads and writes so they wait on each other to forbid invalid schedules.

SSI takes a different approach:

| Aspect | Blocking-Based Locking | PostgreSQL SSI |
|---|---|---|
| Reading data | May require locks that block writers | Relies on MVCC snapshots |
| Writing data | Waits on locks/conflicts as usual | Still uses row locking for writes |
| Dangerous read–write patterns | May block upfront | Tracked; can trigger abort |
| New data matching a predicate | Requires predicate/range locking | Tracks predicate reads |
| Response when unsafe | Waits or deadlocks/aborts by design | Serialization failure `40001` |
| Application needs retry | Possibly, depending on error | **Required** to handle `40001` |

### 12.1. "Non-Blocking Reads/Writes" Does Not Mean "Never Waits"

PostgreSQL still uses locks for writes, DDL, foreign keys, and more. Two `SERIALIZABLE` transactions can wait on locks when updating the same row. SSI only means **predicate reads** for serializability do not simply block all writers pessimistically.

### 12.2. SSI Does Not Eliminate Deadlocks

A schedule acquiring row locks in reverse order can still deadlock, causing PostgreSQL to report `40P01`. That is distinct from serialization failure `40001`.

## 13. Two-Session Lab: Preparing Data

Practice on a **test PostgreSQL instance** with permission to create schemas. Never run in production. Open **two independent connections**, such as two `psql` terminals connected to the same database.

If schema `ssi_lab` already exists, use another database or rename the schema; **never blindly `DROP` an existing schema**.

### 13.1. Create Schema

~~~sql
CREATE SCHEMA ssi_lab;
~~~

### 13.2. Doctors Table

~~~sql
CREATE TABLE ssi_lab.doctors (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO ssi_lab.doctors (
    doctor_id, doctor_name, on_call
)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE);
~~~

Define the business invariant: `COUNT(*) FILTER (WHERE on_call) >= 1`. The table intentionally lacks a multi-row constraint protecting the invariant so write skew is observable.

### 13.3. Budget Configuration Table

~~~sql
CREATE TABLE ssi_lab.budget (
    budget_id INTEGER PRIMARY KEY,
    department TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0)
);

INSERT INTO ssi_lab.budget (budget_id, department, amount)
VALUES
    (1, 'Engineering', 1000),
    (2, 'Operations', 1000);
~~~

This table will illustrate consistent read snapshots and why multiple `SELECT`s under `READ COMMITTED` can see two different states.

### 13.4. Lab Rules

- Session A = T1, Session B = T2.
- Run in the **exact step-by-step order** described; do not paste both sides into one connection.
- Ensure both snapshot-initializing `SELECT`s finish **before any UPDATE/COMMIT** in the write skew experiments.
- If you see `ERROR` in a transaction, roll back as needed before continuing.
- Reset data only after both sessions have ended their transactions.
- If using a GUI, verify that the two tabs genuinely have two independent backend sessions.

## 14. Experiment A: Write Skew Under REPEATABLE READ

First, in a session outside the experiment transactions:

~~~sql
UPDATE ssi_lab.doctors
SET on_call = TRUE;
~~~

### 14.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Expected: 2.

-- Keep transaction A open.
~~~

### 14.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Expected: 2.

-- Keep transaction B open.
~~~

At this point, each session holds a snapshot seeing two doctors on call.

### 14.3. Session A Updates and Commits

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 14.4. Session B Updates and Commits

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

The two transactions modify **two different rows**. Under `REPEATABLE READ`, both can succeed.

### 14.5. Check the Result

~~~sql
SELECT
    doctor_id,
    doctor_name,
    on_call
FROM ssi_lab.doctors
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining_on_call
FROM ssi_lab.doctors
WHERE on_call;
~~~

If both commit, `remaining_on_call = 0`, violating the invariant.

**This is a non-serializable schedule even though neither transaction experienced a dirty read, nonrepeatable read, or phantom read.**

## 15. Experiment B: Same Schedule With SERIALIZABLE

Reset outside any transaction:

~~~sql
UPDATE ssi_lab.doctors
SET on_call = TRUE;
~~~

### 15.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Expected: 2.
~~~

### 15.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Expected: 2.
~~~

### 15.3. Session A

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 15.4. Session B

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

With this interleaving, PostgreSQL cannot let both transactions **commit successfully** without breaking serializability. One session will receive an error like:

~~~text
ERROR: could not serialize access due to read/write dependencies
       among transactions
SQLSTATE 40001
~~~

Exact message wording and timing (`UPDATE` vs. `COMMIT`) may vary; never hardcode against English error message strings.

### 15.5. How to Check SQLSTATE in psql

In `psql`, after an errored statement, you can enable verbose details:

~~~text
\set VERBOSITY verbose
~~~

Repeat the lab scenario to see `SQLSTATE` alongside the message, or have your application/JDBC driver read the error code directly.

### 15.6. Roll Back After the Error

If a transaction is in a failed state, run:

~~~sql
ROLLBACK;
~~~

Then open a new transaction. Never try to keep running `SELECT`/`UPDATE` statements inside an already-aborted transaction.

### 15.7. Final Result Must Leave Someone On Call

If A commits and B aborts, An goes off call and Bình stays on call. If B commits and A aborts, Bình goes off call and An stays on call. With a proper read-and-check invariant protocol, having both go off call cannot occur once both `SERIALIZABLE` transactions **are accepted**.

## 16. Why Was a Transaction Aborted? Drawing the Lab Graph

At the time of the two `SELECT`s:

~~~text
T1 snapshot: An=true, Bình=true
T2 snapshot: An=true, Bình=true
~~~

Afterward:

~~~text
T1 writes An=false
T2 writes Bình=false
~~~

Dependencies:

~~~text
T1 read Bình=true and did not see T2 write Bình=false
  => T1 --rw--> T2

T2 read An=true and did not see T1 write An=false
  => T2 --rw--> T1

      +-----------+
      |           v
      T1 --rw--> T2
      ^           |
      +----rw-----+
~~~

No serial order can explain both reads seeing two doctors on call **and** both updates committing under the check logic.

SSI tracks dependencies to stop cycles with this risk.

### 16.1. Why Is Merely Counting Rows Enough to Create a Dependency?

`SELECT COUNT(*) WHERE on_call` is a **predicate-based query**. The count depends on rows matching `on_call = TRUE`. Another transaction changing `TRUE → FALSE` alters the result set that serializability must protect.

### 16.2. What If One Session Only SELECTs and the Other UPDATEs?

A single `rw` edge does not automatically cause an anomaly. `SERIALIZABLE` does not mean whenever someone updates a row someone else read, one of them must fail. The structure of the overall schedule determines the risk.

### 16.3. Does READ COMMITTED Behave Differently?

Under `READ COMMITTED`, if transaction B **re-reads the condition after A commits**, it can see only one doctor remaining and stop. However, if both already checked the condition earlier, transaction B can still act on its stale decision. `READ COMMITTED` does not automatically protect that multi-row invariant.

## 17. Read-Only Transactions Can Also Participate in Serialization

A transaction that only runs `SELECT` writes zero rows yet can still be **a vertex in the dependency graph** of other transactions. Thus, "I'm only reading" does not prove every schedule involving it is serializable.

### 17.1. Multi-SELECT Reporting Under READ COMMITTED

Suppose the combined budget of two departments is 2000. Transaction T2 transfers 100 from Engineering to Operations with two `UPDATE`s in one transaction.

T1 reads Engineering before T2 commits, then reads Operations after T2 commits:

~~~text
Initially Engineering=1000, Operations=1000

T1 reads Engineering -> 1000

T2 transfers:
  Engineering -> 900
  Operations  -> 1100
  COMMIT

T1 reads Operations -> 1100
T1 sums -> 2100, a total that never existed in any committed state.
~~~

That is **read skew** between two `SELECT` statements under `READ COMMITTED`.

### 17.2. REPEATABLE READ READ ONLY

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT amount
FROM ssi_lab.budget
WHERE budget_id = 1;

SELECT amount
FROM ssi_lab.budget
WHERE budget_id = 2;

COMMIT;
~~~

Both `SELECT`s use a stable snapshot, avoiding mixing two data slices.

### 17.3. Serializable Read-Only and Indirect Dependencies

If read-only results must be equivalent to a system-wide serial order, a "consistent snapshot" alone does not capture the full requirement when multiple concurrent `SERIALIZABLE` transactions interact with complex dependencies. SSI tracks read-only transactions too and may require aborting a transaction to preserve serializability.

## 18. SERIALIZABLE READ ONLY DEFERRABLE: Waiting for a Safe Snapshot

PostgreSQL offers a special mode suited for **read-only reports** requiring a serializable snapshot:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT
    SUM(amount) AS total_budget
FROM ssi_lab.budget;

COMMIT;
~~~

### 18.1. What Does DEFERRABLE Do?

With `SERIALIZABLE`, `READ ONLY`, and `DEFERRABLE`, PostgreSQL can **wait until it obtains a safe snapshot** before executing reads. Once it has a safe snapshot, that read-only transaction avoids typical serialization failures tied to its serializable reads.

### 18.2. Enabling DEFERRABLE Does Not Make Every Transaction Faster

It may have to **wait before starting to read**, especially when many write transactions are active concurrently. It is a trade-off between startup wait time for a safe snapshot and avoiding retries on a long read-only report.

### 18.3. Applicability Conditions

`DEFERRABLE` is meaningful specifically in the **`SERIALIZABLE + READ ONLY`** combination. It does not have an equivalent effect on `READ COMMITTED` transactions or read-write transactions.

### 18.4. When Should It Be Used?

- Multi-table reports with multiple `SELECT` statements.
- Read-only data export jobs.
- Jobs willing to wait briefly at the start to avoid serialization retries.
- Work needing a snapshot guaranteed compatible with the system's serializable transactions.

If running only a tiny single `SELECT`, a simpler option may suffice depending on business correctness.

## 19. Serialization Failure: An Intentional Error, Not Corrupted Data

When PostgreSQL aborts a `SERIALIZABLE` transaction to prevent a dangerous schedule, it normally returns:

~~~text
SQLSTATE 40001
serialization_failure
~~~

This is an error **that must be handled in application design**, not treated as a random glitch to hide.

### 19.1. Where Can 40001 Occur?

- When `UPDATE`/`DELETE` encounters a row version modified after the snapshot.
- When PostgreSQL detects dangerous read–write dependencies during DML execution.
- At `COMMIT`, after prior SQL statements already succeeded.

Never catch `40001` only around the `UPDATE`; wrap **the entire transaction including `COMMIT`**.

### 19.2. Do Not Confuse 40001 With Deadlock

| SQLSTATE | Common Name | Primary Cause |
|---|---|---|
| `40001` | `serialization_failure` | Transaction cannot proceed/commit while preserving isolation guarantees |
| `40P01` | `deadlock_detected` | Transactions formed a lock-wait cycle |
| `23505` | `unique_violation` | Duplicate key / unique index violation |
| `23P01` | `exclusion_violation` | Exclusion constraint violated |
| `55P03` | `lock_not_available` | Could not acquire lock per operation options |

Some unique/exclusion errors can stem from race conditions that an application evaluates as a conflict/retry, but never **automatically retry every `23505`/`23P01`**; they may be genuinely invalid business requests.

### 19.3. High Abort Rate Does Not Mean Corrupted Data

SSI aborts exist to **prevent wrong results from committing**. If `40001` rates spike, review workload, transaction duration, query predicates, indexes, and retry policies rather than disabling serializability blindly.

## 20. Proper Retry: Re-Run the Entire Transaction

This is the single most important programming rule with SSI:

**Hit `40001` → roll back old transaction → start a new transaction → re-read data → recompute decision → write again → commit.**

### 20.1. Why Is Retrying Only the Last Statement Wrong?

In the write skew lab:

1. T1 and T2 both read `count = 2`.
2. T1 commits An going off call.
3. T2 is aborted.
4. If T2 only re-ran `UPDATE doctor_id=2 SET on_call=false` without re-reading, it would skip the "anyone else on call?" check.

It must re-read the new count, see `count = 1`, and **refuse to let the last doctor go off call**.

### 20.2. Correct Transaction Pseudocode

~~~text
max_attempts = 5

for attempt = 1..max_attempts:
    BEGIN SERIALIZABLE

    try:
        current_state = SELECT ...           # Re-read
        if not business_precondition(state):
            ROLLBACK
            return DOMAIN_REJECTED

        UPDATE ...                           # Write per fresh decision
        COMMIT                               # 40001 may occur here
        return SUCCESS

    catch sqlstate == 40001:
        ROLLBACK if transaction still open
        backoff_with_jitter(attempt)
        continue with NEW transaction

    catch other_error:
        ROLLBACK if needed
        raise

return RETRY_EXHAUSTED
~~~

### 20.3. Bounded Retries

Define:

- Maximum attempt count.
- Backoff and jitter.
- Overall request deadline.
- Metrics for retry counts.
- Alert thresholds for `40001`.
- Error behavior returned to callers when retries are exhausted.

Unbounded retries under high contention amplify load and stretch latency.

### 20.4. Side Effects Outside the Database

A transaction can roll back in PostgreSQL, yet **outbound emails, HTTP payment calls, or external notifications** do not roll back automatically.

When retrying entire transactions, external operations require idempotency and patterns like:

- Transactional outbox.
- Idempotency keys.
- Moving side effects after commit when contracts permit.
- Reconciliation if DB and external state diverge.
- Consumers processing events safely at least once.

Avoid calling a multi-second payment provider inside a transaction holding locks whenever a better workflow is possible.

## 21. Java/JDBC Example: Wrapping the Full Transaction and SQLSTATE

A simple Java example illustrating the structure; assumes `DataSource` is configured, and business preconditions and logging are defined in the application.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DoctorDutyService {
    private final DataSource dataSource;

    public DoctorDutyService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean requestLeave(int doctorId) throws SQLException {
        final int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection cn = dataSource.getConnection()) {
                cn.setAutoCommit(false);
                cn.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);

                try {
                    int count;
                    try (PreparedStatement ps = cn.prepareStatement(
                            "SELECT COUNT(*) FROM ssi_lab.doctors WHERE on_call")) {
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            count = rs.getInt(1);
                        }
                    }

                    if (count <= 1) {
                        cn.rollback();
                        return false;
                    }

                    int updated;
                    try (PreparedStatement ps = cn.prepareStatement(
                            "UPDATE ssi_lab.doctors " +
                            "SET on_call = FALSE " +
                            "WHERE doctor_id = ? AND on_call = TRUE")) {
                        ps.setInt(1, doctorId);
                        updated = ps.executeUpdate();
                    }

                    if (updated != 1) {
                        cn.rollback();
                        return false;
                    }

                    cn.commit();
                    return true;

                } catch (SQLException ex) {
                    try {
                        cn.rollback();
                    } catch (SQLException rollbackError) {
                        ex.addSuppressed(rollbackError);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < maxAttempts) {
                        // In practice: backoff/jitter + deadline + logging.
                        continue;
                    }
                    throw ex;
                }
            }
        }

        throw new SQLException("Retry limit exceeded", "40001");
    }
}
~~~

### 21.1. Practical Points for Real Applications

- `Connection.TRANSACTION_SERIALIZABLE` must map properly to PostgreSQL in the driver/datasource.
- Set isolation before running queries in the transaction.
- `commit()` sits inside the `SQLException`-handling block.
- Every retry starts a brand-new transaction and re-reads state.
- Never report success before `commit()` completes.
- With connection pools, restore `autoCommit`/isolation per pool contract; using a framework transaction abstraction is often safer than manual lifecycle management.
- Never trigger external side effects before commit without idempotency.
- Checking "does `doctorId` exist and have leave permission" requires authorization/domain validation beyond this sample.
- Implement real backoff/jitter and deadlines, not just a comment.

### 21.2. Why Not Retry a Statement Inside the Same Transaction?

Once PostgreSQL reports an error inside a transaction, it normally puts the transaction into a failed/aborted state until rollback. More importantly, the old snapshot and business decisions are no longer valid. You need a **new transaction**, not just a re-run SQL statement.

## 22. Serializable Does Not Replace Constraints

SSI is a concurrency-protection layer, yet many invariants belong directly in database constraints whenever expressible.

### 22.1. UNIQUE for Business Keys

~~~sql
CREATE TABLE ssi_lab.request_ids (
    request_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

If two writers both `INSERT` the same `request_id`, `PRIMARY KEY`/`UNIQUE` prevents duplicates. Never just `SELECT` "not found" and then `INSERT` assuming the pre-check suffices.

### 22.2. CHECK for Single-Row Invariants

~~~sql
CREATE TABLE ssi_lab.stock (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
~~~

`CHECK` enforces non-negative stock. The transaction must also ensure stock was allocated to the right order and requests are not double-processed.

### 22.3. Exclusion Constraints for Time Ranges

If a room cannot have two overlapping bookings, an exclusion constraint on a range type enforces data integrity more directly than "SELECT check then INSERT." Design range operators, indexes, required extensions, and tenant/room scope properly for your schema.

### 22.4. Multi-Row Invariants Hard to Express With CHECK

"At least one doctor on call" is an **aggregate condition across multiple rows**, which cannot be directly enforced with `CHECK (on_call IS NOT NULL)` or `CHECK (on_call IN (true, false))`.

That is a classic case where `SERIALIZABLE` transactions or a dedicated coordination protocol add real value.

### 22.5. All Write Paths Must Follow the Protocol

A `SERIALIZABLE` API that checks and updates properly can still have its invariant broken by an admin script running a blind `UPDATE` without checking conditions. `SERIALIZABLE` cannot make PostgreSQL guess a rule another writer never expressed.

Control APIs, background jobs, batch imports, and manual data fixes alike; combine least-privilege access with database constraints.

## 23. Alternatives: Single-Row Protection Does Not Always Need SSI

For some workflows, simpler patterns work better.

### 23.1. Atomic UPDATE

Decrement inventory by one if enough stock remains:

~~~sql
UPDATE ssi_lab.stock
SET quantity = quantity - 1
WHERE sku = 'BOOK-001'
  AND quantity >= 1
RETURNING sku, quantity;
~~~

This is a single conditional update coordinated by PostgreSQL's row locking. If it returns zero rows, treat the allocation as unsuccessful.

### 23.2. Optimistic Locking via Version

~~~sql
UPDATE products
SET price = 110000,
    version = version + 1
WHERE product_id = 123
  AND version = 7
RETURNING product_id, version;
~~~

This example requires a `products` table with a `version` column. If zero rows match, another writer modified the record or it no longer exists; the application must reload and decide.

### 23.3. SELECT FOR UPDATE

When you must read a row, compute business logic, and update that exact row:

~~~sql
BEGIN;

SELECT quantity
FROM ssi_lab.stock
WHERE sku = 'BOOK-001'
FOR UPDATE;

-- Check and UPDATE within the same transaction.
COMMIT;
~~~

If all writers follow the same protocol and acquire the lock before deciding, this can be simple. However, row locks **do not automatically protect conditions over rows that do not exist yet**.

### 23.4. Guard Row or Shared Resource Lock

A transaction can lock a row representing a shared resource (such as a room or doctor rota) before checking and updating multiple rows. All writers must lock the **same coordinating row** in the same order.

Under `REPEATABLE READ`, waiting on a row lock does not update an already-fixed snapshot; a guard-row protocol must be designed and tested under the right isolation level. Never toss in `FOR UPDATE` casually and declare an invariant safe.

## 24. Why Does SSI Still Have False Positives?

A **dangerous structure** is a sufficient warning for PostgreSQL to stay cautious, yet not every detected structure proves an **actual cycle occurred**.

Example:

~~~text
T1 --rw--> T2 --rw--> T3

Yet there is no path from T3 back to T1.
~~~

The full schedule may still be serializable. However, from the tracking state visible at a given moment, PostgreSQL may abort under SSI's conservative rules to guarantee safety.

### 24.1. Predicate Lock Granularity Affects False Positives

If a query only needs a small subset yet the planner picks a sequential scan of the entire table, read-tracking metadata becomes broader. Writes to unrelated rows in the same table can then trigger extra conflict detections compared to a narrower index scan.

### 24.2. False Positives Are Not Solved by Dropping Retries

When a transaction is validly aborted by SSI, the application must still roll back and retry. Unnecessary conflicts can be reduced via query/index/transaction design, though you should never expect an exact 0% `40001` rate under contending workloads.

### 24.3. Do Not Deduce Which Schedule Was Wrong From One 40001 Message

The error may include conflict details, yet the message is not a business log saying "T1 definitely corrupted data." PostgreSQL aborted the commit specifically to **prevent** that outcome.

## 25. Optimizing Transactions to Reduce Serialization Failures

When `40001` rates are high, evaluate each group of causes.

### 25.1. Keep Transactions Short

If a transaction reads data and then waits 10 seconds on an external API before writing, it overlaps with many other transactions and expands the tracked dependency graph.

Never keep a transaction open while a user fills out a form or during slow non-database tasks.

### 25.2. Read Only Data Needed for the Decision

A `SELECT *` scanning many rows and filtering in application code widens the tracked read scope unnecessarily. If an invariant only concerns one room and one time window, express that predicate directly in SQL.

### 25.3. Indexes Can Narrow Tracked Predicates

An index matching the predicate helps PostgreSQL touch a smaller region and can reduce conservative `SIREAD` conflicts. Still, an index helps only when the planner chooses it and the overall workload benefits.

### 25.4. Collapse Multi-Step Read–Modify–Write When Possible

A single `UPDATE ... WHERE ... RETURNING` is tighter and easier to coordinate than `SELECT` → app calculation → `UPDATE`. Not every multi-row rule collapses into one `UPDATE`, but look for direct options first.

### 25.5. Use READ ONLY DEFERRABLE for Suitable Reports

A read-only `SERIALIZABLE` report can accept waiting for a safe snapshot to avoid retries.

### 25.6. Increasing Retries Is Not Always the Best Optimization

If every request retries repeatedly, system load climbs. Re-examine hot predicates, write-skew design, contending writer counts, and transaction length.

## 26. Configuring Predicate Locks: Tune Only With Evidence

PostgreSQL exposes parameters controlling memory/granularity of predicate lock tracking, such as:

- `max_pred_locks_per_transaction`.
- `max_pred_locks_per_relation`.
- `max_pred_locks_per_page`.

When tracking memory slots fill up, PostgreSQL promotes tracking to coarser granularity, which can increase conservative conflicts.

### 26.1. Never Tune Parameters to "Disable SSI"

These settings are not a safety bypass to ignore dangerous dependencies. Their purpose is balancing tracking memory and granularity in measured workloads.

### 26.2. Why Is No Fixed Value Recommended?

Appropriate sizing depends on:

- Concurrent transaction count.
- Number of relations and pages read.
- Available RAM.
- Query plans.
- Scan and index types.
- Frequency of serialization failures.
- PostgreSQL version and infrastructure.

Never raise values just because you hit one `40001`. First inspect invariants, interleaving, and read scope.

### 26.3. Changes May Require Restarts and Affect the Whole Server

Some locking/memory parameters require a server restart or consistent cluster configuration. Never apply them directly in production without reading version-specific docs and load testing.

## 27. Observing SIReadLock With pg_locks

In a test environment with an open `SERIALIZABLE` transaction, from **another monitoring connection**, you can query:

~~~sql
SELECT
    l.pid,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.mode = 'SIReadLock'
ORDER BY l.pid, l.locktype, relation_name;
~~~

### 27.1. Column Meanings

| Column | Meaning |
|---|---|
| `pid` | Associated backend PID, if present |
| `locktype` | Lock/tracking object type |
| `mode` | `SIReadLock` for read tracking |
| `granted` | Status of the lock entry |
| `relation_name` | Relation name when relation OID is present |
| `page, tuple` | Details when tracking at page/tuple granularity |

### 27.2. Seeing SIReadLock Does Not Mean Blocked

`SIReadLock` records read metadata for SSI analysis. A backend is not necessarily waiting just because it holds `SIReadLock`.

To inspect **lock waits**, check `pg_stat_activity.wait_event_type`, `wait_event`, or `pg_blocking_pids` for the specific case.

### 27.3. Why Might a Tuple-Level Lock Not Appear as Expected?

The query may have scanned differently, tracking may have promoted to page/relation granularity, or the transaction/snapshot is not in the state you assumed. Never conclude SSI is disabled just because a specific tuple lock row isn't shown.

### 27.4. Stats Access May Be Privilege-Restricted

Roles without monitoring privileges may not see all details from `pg_stat_activity`. Use minimal appropriate monitoring roles instead of broad privileges just for debugging.

## 28. Tracking 40001 and Transaction Duration

A monitoring query:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Useful for spotting:

- Long-open transactions.
- `idle in transaction` sessions.
- Multiple backends waiting on locks.
- Queries holding snapshots for long durations.

### 28.1. pg_stat_database Has No Direct Counter for All 40001s

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`xact_rollback` counts rollbacks from all causes, not just SSI. `deadlocks` counts deadlocks, not serialization failures.

Therefore, to measure `40001` rates accurately:

- Capture `SQLSTATE` in the application.
- Record metrics by endpoint, transaction type, and retry attempt count.
- Inspect server logs if appropriate logging is enabled.
- Correlate with slow queries, contention, and transaction durations.

### 28.2. Alerts Should Be Impact-Based

A few serialization retries are normal in contended systems. What matters is final failure rate, p95/p99 latency, retry counts, and invariant preservation—not raw error counts alone.

## 29. EXPLAIN and Indexes Under SSI

Query plans affect read/write scope and cost.

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM ssi_lab.doctors
WHERE on_call;
~~~

`EXPLAIN` shows the estimated plan; it does not execute the query like `EXPLAIN ANALYZE`.

### 29.1. When to Review Indexes?

For example, a large `bookings` table frequently querying:

~~~sql
SELECT 1
FROM bookings
WHERE room_id = 101
  AND status = 'confirmed'
  AND starts_at < TIMESTAMPTZ '2026-11-14 12:00+07'
  AND ends_at > TIMESTAMPTZ '2026-11-14 11:00+07';
~~~

Choose indexes based on actual schema, predicates, range queries, and data distribution. Never claim a plain B-tree on `room_id` automatically optimizes every overlap query.

### 29.2. EXPLAIN ANALYZE Actually Executes

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM ssi_lab.doctors
WHERE on_call;
~~~

In a small test lab, this `SELECT` is safe. Never run `EXPLAIN ANALYZE` on DML or heavy queries thinking you are only "viewing the plan": `ANALYZE` executes the query.

### 29.3. Never Trade Correctness for Plan Speed

Adding an index can lower false positives and overhead, yet invariants still require `SERIALIZABLE` or an appropriate protocol. A faster query does not prove it avoided write skew.

## 30. When One Transaction Is SERIALIZABLE and Others Are Not

A misconception is thinking only the "important" transaction needs `SERIALIZABLE`, while other writers can do whatever they want.

If multiple paths write the same data:

- API A checks the invariant properly in a `SERIALIZABLE` transaction.
- Batch job B runs a direct `UPDATE` **without checking the invariant**.
- Script C modifies data with elevated privileges.

Then business state can still break even if the transaction schedule is serializable. A serial schedule can still **include a broken transaction**.

### 30.1. Guarantees Require All Writers to Share the Protocol

For invariants spanning multiple transactions, standardize checks, isolation levels, and permissions across every write path. Whenever possible, use database constraints to enforce consistency even if a client forgets to check.

### 30.2. Mixing Isolation Does Not Automatically Break Every Guarantee

PostgreSQL still enforces the chosen isolation semantics per transaction. The issue is that **end-to-end serializability for the whole workflow** cannot be assumed when writers operate outside the protocol. Analyze actual correctness.

## 31. SSI and Unique/Exclusion Constraints

Some concurrency errors occur when two transactions attempt to create the same key or resource:

~~~sql
INSERT INTO ssi_lab.request_ids(request_id)
VALUES ('req-001');
~~~

If another transaction inserts the same request ID, one may receive `23505` instead of `40001`, depending on timing and order.

### 31.1. Keep UNIQUE Constraints

Never drop `UNIQUE` just because you want all conflicts to surface as serialization errors. Constraints enforce uniqueness directly, independent of whether every writer performs pre-checks properly.

### 31.2. When Should You Retry 23505?

If a user tries to register a username that already exists, retrying will not change the outcome; report a conflict.

If an application generates a business key by reading and picking "next value" and hits a duplicate under concurrency, fix the key-generation protocol. Some cases can retry the **entire decision** with fresh data; never treat every unique violation as transient.

### 31.3. Exclusion Constraints

Similarly, overlapping booking intervals can raise `23P01`. The response should be "time slot already booked," not blind retries until it succeeds.

## 32. Cases SSI Cannot Solve by Itself

### 32.1. External System Calls

Sending emails, issuing invoices via an API, or charging payments happen outside PostgreSQL transactions. SSI cannot roll back external actions.

### 32.2. Rules Existing Only in the Designer's Head

If code never reads or checks the condition to protect, SSI cannot invent the invariant.

### 32.3. Pre-Existing Bad Data

SSI does not automatically repair rows already holding invalid values or tables missing constraints.

### 32.4. Wrong Access Permissions

`SERIALIZABLE` does not decide whether a request is authorized to view or edit a row. Enforce authorization in services, `GRANT`, or `RLS` per design.

### 32.5. Duplicate Client Requests

A client timing out and resending a create-order request can create two orders without an idempotency key, even when each request commits serializably.

### 32.6. Multi-Transaction Split Logic

If an application reads state in transaction A, commits, and then decides and updates in transaction B without re-checking, those steps no longer form one serializable unit.

## 33. A Tricky Example: Different Rows, Shared Total Invariant

Suppose two departments have budgets, and the rule is their combined committed budget must not exceed 3000. Initially each has 1000, leaving 1000 available.

T1 and T2 both read total 2000, then each increases a different department's budget by 800:

~~~text
Initially:
Engineering = 1000
Operations  = 1000
Total       = 2000

T1: SELECT SUM(amount) -> 2000
T2: SELECT SUM(amount) -> 2000

T1: UPDATE Engineering = 1800
T2: UPDATE Operations  = 1800

If both COMMIT:
Total = 3600 > 3000
~~~

This is write skew because both transactions checked the same sum yet modified different rows.

### 33.1. READ COMMITTED / REPEATABLE READ May Not Protect It

If both reads happen before either transaction writes and the two `UPDATE`s touch different rows, an invalid schedule can commit.

### 33.2. SERIALIZABLE + In-Transaction Check

Each transaction must:

1. `BEGIN SERIALIZABLE`.
2. Read the current sum.
3. Verify `total + requested_increment <= 3000`.
4. `UPDATE` the appropriate row.
5. `COMMIT` with `40001` handling.

On retry, the second transaction reads the sum already increased to 2800 and rejects adding 800 more.

### 33.3. Are There Alternative Data Models?

Yes. If total budget can be represented by a **single guard / `remaining_budget` row**, use an atomic update:

~~~sql
UPDATE budget_limits
SET remaining = remaining - 800
WHERE budget_key = 'company'
  AND remaining >= 800
RETURNING remaining;
~~~

This structure requires a `budget_limits` table to exist. A coordinating row with a constraint and atomic `UPDATE` can be simpler than SSI for certain rules.

Choose the design based on number of data sources, invariant complexity, and whether decisions can be centralized.

## 34. COMMIT Timing and the Impact of Dangerous Dependencies

A `SERIALIZABLE` transaction can run `SELECT`/`UPDATE` successfully and still fail at `COMMIT`.

~~~text
T1: BEGIN
T1: SELECT ...                -> succeeds
T1: UPDATE ...                -> succeeds
T2: commits a conflicting schedule
T1: COMMIT                    -> ERROR 40001
~~~

### 34.1. Never Report Success Early

Never return HTTP 200 "order placed" merely because `UPDATE` returned a row before the transaction committed. If `COMMIT` fails, the change has rolled back.

### 34.2. RETURNING Does Not Prove COMMIT Succeeded

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1
RETURNING doctor_id;
~~~

`RETURNING` reports that the `UPDATE` affected the row within the current transaction. It does not guarantee the transaction will commit successfully.

### 34.3. Savepoints Do Not Replace Full-Transaction Retries

An application can use savepoints to recover from certain in-transaction errors. However, a serialization failure invalidates decisions made from the old snapshot; safe practice is retrying the **entire transaction logic**, not rolling back to a savepoint and repeating the last SQL statement.

### 34.4. Multiple Statements in One Transaction Must Share One Connection

If an ORM runs `SELECT` on connection A and `UPDATE` on connection B outside the transaction, they are no longer part of the same SSI unit. Use a transaction manager so all checks and writes share one transaction.

## 35. Common Misconceptions About SSI

### 35.1. "SERIALIZABLE means all transactions run one by one"

False. PostgreSQL runs them concurrently and uses SSI/aborts to guarantee committed schedules are serializable.

### 35.2. "REPEATABLE READ prevents phantoms, so it is already serializable"

False. Write skew can still occur even when each transaction reads a stable snapshot.

### 35.3. "Two transactions modifying different rows cannot conflict"

False. They can read a shared invariant and create `rw`-antidependencies.

### 35.4. "Every time a read value changes, an abort is mandatory"

False. A lone `rw` edge can be completely valid; the full dependency structure determines risk.

### 35.5. "A dangerous structure always means an actual cycle"

Not necessarily. PostgreSQL detects conservatively and may abort to avoid risk even if a particular schedule was serializable.

### 35.6. "SIReadLock blocks others from writing"

False. It tracks predicate reads/conflicts; it is not `FOR UPDATE`.

### 35.7. "Seeing no tuple-level SIReadLock means SSI isn't active"

False. Tracking may be at page/relation granularity or another state; inspect plans and transactions.

### 35.8. "40001 is a PostgreSQL bug"

False. It is the intentional mechanism rejecting a transaction to uphold isolation guarantees.

### 35.9. "40001 only happens during UPDATE"

False. It can occur at `COMMIT`.

### 35.10. "Retrying only the final UPDATE is enough"

False. You must re-read and re-decide against a fresh snapshot.

### 35.11. "40001 and 40P01 are the same error"

False. One is serialization failure; the other is deadlock.

### 35.12. "Serializable automatically knows at least one doctor must be on call"

False. The checking logic must be written inside the transaction or via appropriate constraints/protocols.

### 35.13. "UNIQUE is unnecessary if SERIALIZABLE is enabled"

False. Constraints protect value sets directly across all writers.

### 35.14. "READ ONLY can never cause serialization conflicts"

Not true in all schedules. Read-only transactions can participate in dependencies; `DEFERRABLE` is the special tool when a safe snapshot is needed.

### 35.15. "DEFERRABLE makes read transactions never wait"

False. They can wait initially to acquire a safe snapshot.

### 35.16. "Indexes always eliminate 40001"

False. Indexes can narrow tracking scope and cost, not eliminate true logical conflicts.

### 35.17. "Enabling SERIALIZABLE automatically handles emails and payments"

False. External systems require idempotency, outboxes, and reconciliation.

### 35.18. "UPDATE RETURNING a row means it committed"

False. `COMMIT` can still fail.

### 35.19. "Lowering isolation to READ COMMITTED to stop retries fixes the bug"

Wrong if the invariant requires serializability. It may just allow broken schedules to commit.

### 35.20. "Every unique error should be retried"

False. Many are genuine business conflicts.

## 36. Practice Exercises

### Exercise 1 — Snapshots and Write Skew

Why can two transactions both read valid snapshots under `REPEATABLE READ` and still break a total invariant?

**Hint:** Snapshots do not protect cross-transaction dependency cycles; two transactions can write different rows.

### Exercise 2 — Dependency Graph

Draw `T1 --rw--> T2` when T1 reads an old version of X and does not see T2's modification to X.

**Hint:** T1 must precede T2 in any serial order matching that read outcome.

### Exercise 3 — wr or rw?

T1 commits `X=50`, and T2 reads `X=50`. Which relationship is this?

**Answer:** `T1 --wr--> T2`.

### Exercise 4 — ww

T1 `UPDATE`s X and commits; T2 `UPDATE`s X afterward. Describe the meaning of the `ww` relationship.

**Hint:** T2 writes a version after T1, subject to write ordering.

### Exercise 5 — Dangerous Structure

Fill in the edge labels:

~~~text
T_in --?--> T_pivot --?--> T_out
~~~

**Answer:** Two consecutive `rw`-antidependency edges.

### Exercise 6 — Does Every Two-Edge Structure Mean an Anomaly?

A schedule has `T1 --rw--> T2 --rw--> T3` with no path closing a cycle. Is the schedule definitely non-serializable?

**Hint:** No. A dangerous structure is a conservative detection signal, not complete proof of a cycle.

### Exercise 7 — Two-Doctor Write Skew

After two `REPEATABLE READ` commits, `on_call` count drops from 2 to 0. Why isn't this a same-row lost update?

**Hint:** T1 modified An and T2 modified Bình; the shared invariant was violated.

### Exercise 8 — SERIALIZABLE

What must happen if the exact same write-skew schedule is run properly under `SERIALIZABLE`?

**Hint:** Both cannot be allowed to commit successfully; one transaction can receive `40001`.

### Exercise 9 — Retry

T2 hits `40001` after reading `count=2`. Is re-running only `UPDATE Bình=false` acceptable?

**Answer:** No. Open a new transaction, re-read the count, and re-evaluate the decision.

### Exercise 10 — COMMIT

Why is catching `SQLException` only around `SELECT`/`UPDATE` and not `COMMIT` insufficient?

**Hint:** `40001` can surface at `COMMIT`.

### Exercise 11 — SIReadLock

Does `SIReadLock` necessarily block another transaction from `INSERT`ing a row matching the predicate?

**Answer:** No; it tracks dependencies for SSI.

### Exercise 12 — Empty Predicate

A `SELECT` checking "no overlapping booking" returns 0 rows. Can an `rw`-dependency arise if another transaction inserts an overlapping booking?

**Hint:** Yes; reading an absence under a predicate matters too.

### Exercise 13 — Row Lock

Why doesn't `SELECT ... FOR UPDATE WHERE booking_id = 999` automatically lock a booking that does not exist yet?

**Hint:** Row locks target selected existing rows, not all possible future rows.

### Exercise 14 — Read-Only DEFERRABLE

Which mode fits a read-only report that needs a safe serializable snapshot and can tolerate waiting?

**Answer:** `SERIALIZABLE READ ONLY DEFERRABLE`.

### Exercise 15 — READ COMMITTED and Reporting

T1 reads Engineering before T2 transfers budget, then reads Operations after T2 commits. What phenomenon is this?

**Answer:** Read skew.

### Exercise 16 — Single SELECT

Why does `SELECT SUM(amount) FROM budget` in one statement avoid read skew compared to two separate `SELECT`s under `READ COMMITTED`?

**Hint:** One normal `SELECT` uses one consistent statement snapshot.

### Exercise 17 — SQLSTATE

Match each code with its phenomenon:

| Code | Phenomenon |
|---|---|
| `40001` | ? |
| `40P01` | ? |
| `23505` | ? |
| `23P01` | ? |

**Answer:** Serialization failure, deadlock, unique violation, exclusion violation.

### Exercise 18 — Choosing a Constraint

If two bookings cannot overlap in the same room and time range, which PostgreSQL constraint is worth considering?

**Hint:** Exclusion constraint with range types and an appropriate index.

### Exercise 19 — Version Column

A UI edits orders based on an old version; propose optimistic locking.

**Hint:** `UPDATE ... SET version=version+1 WHERE id=? AND version=? RETURNING ...`.

### Exercise 20 — Inventory

Write an `UPDATE` deducting 3 units only if enough stock exists.

~~~sql
UPDATE ssi_lab.stock
SET quantity = quantity - 3
WHERE sku = 'BOOK-001'
  AND quantity >= 3
RETURNING quantity;
~~~

**Hint:** If `RETURNING` returns no row, do not treat the allocation as successful.

### Exercise 21 — Indexes and SSI

Why can adding an index matching a predicate reduce false-positive serialization failures?

**Hint:** Queries can scan a narrower range, avoiding overly broad tracking.

### Exercise 22 — No Absolute Guarantee

Should you promise "after adding the index, 40001 will never occur again"?

**Answer:** No. True conflicts can still happen.

### Exercise 23 — Long Transactions

Why shouldn't you open a `SERIALIZABLE` transaction and wait minutes for a user to review a form?

**Hint:** Increases overlap, holds snapshots, affects `VACUUM`, and increases conflicts.

### Exercise 24 — Idempotency

If `COMMIT` fails after an email was already sent, what can retrying cause?

**Hint:** Duplicate emails; use an outbox/idempotency design.

### Exercise 25 — Multiple Writers

If an API uses SSI yet a background job skips checking the invariant, is the multi-row policy guaranteed?

**Answer:** Not yet; every write path must follow the protocol or matching constraints.

### Exercise 26 — Observing SIReadLock

Write a `pg_locks` query filtering `mode='SIReadLock'` and observe `relation`/`page`/`tuple` granularity.

**Hint:** Based on the example in section 27.

### Exercise 27 — Reading Metrics

Does `pg_stat_database.deadlocks` count `40001` occurrences?

**Answer:** No. Capture `SQLSTATE` in application metrics/logs to measure serialization failures.

### Exercise 28 — 40001 vs 23505

A request tries to create an existing username. Should `23505` always be retried like `40001`?

**Hint:** No. A unique violation may be a persistent business conflict.

### Exercise 29 — Protecting Total Budget

Two transactions each add 800 on different rows after reading `total=2000` with a limit of 3000. Explain why both committing is write skew.

**Hint:** Total 3600 violates the invariant even though the two `UPDATE`s hit different rows.

### Exercise 30 — Guard Row

In the total budget case, can it be modeled as a single `remaining_budget` row using a conditional atomic `UPDATE`?

**Hint:** Yes, provided all writers follow the same protocol and data stays synchronized.

### Exercise 31 — Snapshots and BEGIN

If you run `BEGIN` Serializable and wait a few seconds before `SELECT`, is the snapshot guaranteed to be taken at `BEGIN` time?

**Answer:** No; the snapshot is normally set when the first statement needing a snapshot executes.

### Exercise 32 — Choosing Isolation Level

One API decrements stock on a single row with `CHECK` and an atomic `UPDATE`; another workflow checks a sum across many rows and updates different rows. Why shouldn't both default to the exact same strategy?

**Hint:** Invariants and conflict shapes differ; choose the simplest mechanism that proves correctness.

## 37. Workflow for Investigating a Suspected SSI Concurrency Bug

A practical workflow:

1. **Define the invariant** that must hold after `COMMIT` as a testable condition.
2. **List all transaction types** reading or modifying the relevant data.
3. **Record the actual isolation level** used by each transaction type.
4. **Sketch the interleaved schedule T1/T2/T3**, with snapshots, reads, writes, and commits.
5. **Identify `wr`, `ww`, and `rw` edges** to spot cycles or dangerous structures.
6. **Reproduce across two real connections**, never relying on sequential tests.
7. **Confirm the error `SQLSTATE`**, not just English message text.
8. **Ensure full-transaction retries**, re-checking domain preconditions.
9. **Audit external side effects / idempotency** outside the DB.
10. **Measure `40001` rates, latency, and transaction duration** in the workload.
11. **Inspect query plans and predicate read scope**, considering suitable indexes.
12. **Consider constraints / atomic updates / guard rows** if the invariant can be simplified.
13. **Ensure every writer follows the protocol**, including APIs, workers, and scripts.
14. **Keep transactions short**, avoiding external waits.
15. **Add integration tests** covering the discovered concurrent schedule.

A transaction rejected by SSI is not a consistency failure. **It is the mechanism preventing committed data from failing.** What needs improvement is how the application handles aborts and models invariants—not hiding the error.

## 38. Quick Reference Table

| Concept | Core Takeaway |
|---|---|
| MVCC | Row versions are visible per snapshot rules |
| Snapshot isolation | Each transaction reads a stable snapshot; write skew still possible |
| PostgreSQL REPEATABLE READ | Implements snapshot isolation; prevents traditional phantoms |
| PostgreSQL SERIALIZABLE | Uses SSI to ensure committed schedules are serializable |
| Serialization graph | Vertices are transactions, edges are dependencies |
| `wr` | Later transaction reads value written by earlier transaction |
| `ww` | Write-after-write ordering relationship |
| `rw` | Read did not see write from another transaction |
| `rw`-antidependency | Central focus of SSI danger detection |
| Dangerous structure | `T_in --rw--> T_pivot --rw--> T_out` |
| Cycle | No serial order can satisfy all edges |
| Write skew | Shared invariant read, different rows written, invariant broken |
| Predicate read | Reading row set matching `WHERE`, including empty sets |
| `SIReadLock` | Read tracking for SSI, not a write-blocking row lock |
| Granularity | Tuple, page, or relation level |
| False positive | Conservative abort even when concrete schedule was serializable |
| `SQLSTATE 40001` | Serialization failure; retry whole transaction |
| `SQLSTATE 40P01` | Deadlock; different cause from `40001` |
| Can `COMMIT` fail? | Yes; handle errors on `COMMIT` too |
| Proper retry | New `BEGIN` → re-read → re-decide → write → `COMMIT` |
| `READ ONLY DEFERRABLE` | Waits for a safe snapshot for Serializable read-only |
| `UNIQUE`/`CHECK`/`EXCLUDE` | Constraints directly protecting expressible invariants |
| Atomic `UPDATE` | Reduces races on single-row conditions |
| Row lock `FOR UPDATE` | Locks selected rows, not future predicate matches |
| Monitoring queries | `pg_locks`, `pg_stat_activity`, `SQLSTATE` metrics |
| Tuning | Query plans, indexes, transaction duration, predicate lock memory |
| External side effects | Need idempotency / outbox / reconciliation |
| End-to-end guarantee | Every write path must follow the invariant and protocol |

---

## Conclusion

**Serializable Snapshot Isolation** is how PostgreSQL provides **`SERIALIZABLE`** guarantees in an MVCC environment without simply locking all data to run transactions one at a time. SSI lets reads use snapshots, tracks read–write relationships, and detects **`rw`-antidependencies** that can combine into a **dangerous structure**. When a schedule risks being non-serializable, PostgreSQL aborts one transaction with **`SQLSTATE 40001`** rather than allowing conflicting changes to commit together.

The two-doctor leave example illustrates the core reason: **`REPEATABLE READ` maintains a stable snapshot yet still allows write skew** when two transactions modify different rows. SSI protects correctness by detecting cross-dependencies, even when read rows come from a predicate like `WHERE on_call=TRUE`. `SIReadLock` tracking entries are not write-blocking row locks; they help PostgreSQL evaluate dangerous schedules and can produce conservative aborts in some cases.

Applications using `SERIALIZABLE` must be built to **retry the entire transaction**, including re-reading, re-checking business preconditions, and handling errors at `COMMIT`. For read-only transactions, `SERIALIZABLE READ ONLY DEFERRABLE` is worth considering when a safe snapshot is needed. For simple invariants, constraints and atomic `UPDATE`s can outperform complex coordination; for multi-row invariants, SSI provides vital guarantees that plain snapshot isolation cannot deliver.

One final principle: **do not ask only whether each transaction read a consistent snapshot; ask whether all committed transactions can be explained by a valid serial order**. That is the exact problem SSI solves and the foundation for building safe PostgreSQL transactions under concurrent load.
