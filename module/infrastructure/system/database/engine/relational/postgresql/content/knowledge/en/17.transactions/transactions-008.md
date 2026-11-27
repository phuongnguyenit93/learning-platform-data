# Write Skew and Business Invariant Verification in PostgreSQL

## 1. The Problem: Each Transaction Looks Valid, Yet Final Data Is Wrong

A hospital on-call scheduling system enforces this rule: **every shift must always have at least one doctor on call**.

The night shift has two doctors, An and Bình. An checks and sees two doctors on call, so she allows herself to go off call. At the exact same time, Bình also checks and sees two doctors on call, so he allows himself to go off call. Each edits only their own record. If both transactions commit successfully, the night shift is left with zero doctors on call.

This is **write skew**: concurrent transactions read an overlapping dataset to make decisions, then write to different rows; the combined committed outcome can violate a **cross-row business invariant**.

PostgreSQL provides MVCC and multiple transaction isolation levels, yet:

- `READ COMMITTED` can experience write skew.
- PostgreSQL's `REPEATABLE READ`, built on **snapshot isolation**, can still experience write skew.
- `SERIALIZABLE` uses dependency tracking to prevent successful transactions from producing non-serializable outcomes; one transaction may be aborted with SQLSTATE `40001` and must retry entirely.

What matters is not whether a single `UPDATE` looks valid in isolation, but whether **the shared rule holds across all possible concurrent transaction combinations**.

### Learning Objectives

After this lesson, you will be able to:

1. Express a business invariant as a verifiable condition.
2. Reproduce write skew across two independent PostgreSQL sessions.
3. Explain why a stable snapshot in `REPEATABLE READ` is not enough.
4. Distinguish write skew from lost updates, phantoms, and deadlocks.
5. Understand how `SERIALIZABLE`/SSI detects read–write dependencies.
6. Retry the **entire transaction** upon receiving `40001`.
7. Use a shared coordinator row lock under `READ COMMITTED`.
8. Recognize the limits of `FOR UPDATE`, advisory locks, CHECK, UNIQUE, triggers, and foreign keys.
9. Verify post-commit invariants with SQL, including shifts that have zero assignment rows.
10. Design concurrency tests using barriers and acceptance criteria.
11. Apply these lessons to booking systems, inventory, admin permissions, and Java applications.

## 2. Business Invariants Must Be Defined Precisely

An **invariant** is a condition that must hold across all valid committed states of data.

In our lab, let:

- `S` be the set of existing shifts.
- `D(s)` be the set of doctors assigned to shift `s`.
- `active_count(s)` be the count of doctors in `D(s)` where `is_on_call = TRUE`.

Invariant:

```text
For every shift s in S:
    active_count(s) >= 1
```

A valid state:

```text
Shift 1:
    DR_A: TRUE
    DR_B: TRUE
    active_count = 2
```

Another valid state:

```text
Shift 1:
    DR_A: FALSE
    DR_B: TRUE
    active_count = 1
```

An invalid state:

```text
Shift 1:
    DR_A: FALSE
    DR_B: FALSE
    active_count = 0  <-- VIOLATION
```

Distinguish **single-row conditions** from **multi-row invariants**. `CHECK (stock >= 0)` protects an inventory value within one row. However, `COUNT(*) FILTER (WHERE is_on_call) >= 1` inspects multiple rows and can be affected by transactions updating different rows.

### 2.1. Why Write the Invariant Before Writing SQL?

Because looking only at a single statement:

```sql
UPDATE doctors
SET is_on_call = FALSE
WHERE doctor_id = 'DR_A';
```

the SQL is completely valid in syntax, data types, foreign keys, and permissions. What breaks is the **combined state after concurrent transactions**, not the boolean update itself.

Writing the invariant explicitly clarifies:

- Which set of rows must be read to make a decision.
- Which transactions can interact.
- What condition must hold after commit.
- Which **business unit** must be protected by locks or isolation.
- Which state assertions tests must verify.

## 3. Preparing the Two Lab Tables

Practice only in a database where modifications are permitted. You need **two separate connections**, not two tabs sharing a single connection.

### 3.1. Creating the Schema

```sql
CREATE SCHEMA IF NOT EXISTS ws218;

CREATE TABLE ws218.shifts (
    shift_id integer PRIMARY KEY,
    shift_name text NOT NULL,
    version bigint NOT NULL DEFAULT 0
);

CREATE TABLE ws218.shift_doctors (
    shift_id integer NOT NULL
        REFERENCES ws218.shifts(shift_id),
    doctor_id text NOT NULL,
    is_on_call boolean NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
```

`shifts` stores one row representing each shift. The `version` column will be used when discussing a **coordinator lock row**.

`shift_doctors` has a composite primary key `(shift_id, doctor_id)` so each doctor has at most one assignment row per shift.

### 3.2. Initial Data

```sql
INSERT INTO ws218.shifts(shift_id, shift_name)
VALUES (1, 'Night shift');

INSERT INTO ws218.shift_doctors(
    shift_id, doctor_id, is_on_call
)
VALUES
    (1, 'DR_A', TRUE),
    (1, 'DR_B', TRUE);
```

Inspect:

```sql
SELECT shift_id, doctor_id, is_on_call
FROM ws218.shift_doctors
ORDER BY shift_id, doctor_id;
```

| shift_id | doctor_id | is_on_call |
|---:|---|---|
| 1 | DR_A | true |
| 1 | DR_B | true |

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Initial count: **2**.

If the tables already exist from an earlier lab run, do not insert duplicate keys. Use a fresh test database/schema or reset fixtures through an approved procedure. Never drop tables whose ownership is unclear.

## 4. Invariant Verification Query: Do Not Miss Empty Shifts

A query grouping only over `shift_doctors` returns no row for a shift that has zero assigned doctors. To check **every shift**, start from `shifts`:

```sql
SELECT
    s.shift_id,
    s.shift_name,
    COUNT(d.doctor_id)
      FILTER (WHERE d.is_on_call IS TRUE)
      AS active_doctors
FROM ws218.shifts AS s
LEFT JOIN ws218.shift_doctors AS d
    ON d.shift_id = s.shift_id
GROUP BY s.shift_id, s.shift_name
ORDER BY s.shift_id;
```

Initially:

| shift_id | shift_name | active_doctors |
|---:|---|---:|
| 1 | Night shift | 2 |

Filter specifically for violating shifts:

```sql
SELECT
    s.shift_id,
    s.shift_name,
    COUNT(d.doctor_id)
      FILTER (WHERE d.is_on_call IS TRUE)
      AS active_doctors
FROM ws218.shifts AS s
LEFT JOIN ws218.shift_doctors AS d
    ON d.shift_id = s.shift_id
GROUP BY s.shift_id, s.shift_name
HAVING COUNT(d.doctor_id)
         FILTER (WHERE d.is_on_call IS TRUE) = 0
ORDER BY s.shift_id;
```

When the invariant holds, this returns **0 rows**. When any shift has no active doctor, it returns a row with `active_doctors = 0`.

You can write the same check with `NOT EXISTS`:

```sql
SELECT s.shift_id, s.shift_name
FROM ws218.shifts AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM ws218.shift_doctors AS d
    WHERE d.shift_id = s.shift_id
      AND d.is_on_call IS TRUE
);
```

`NOT EXISTS` also catches shifts that have zero doctor rows at all.

**Attention:** `COUNT(*)` after a `LEFT JOIN` counts 1 for the NULL-extended row of an empty shift. Use `COUNT(d.doctor_id) FILTER (...)` or `NOT EXISTS` to get the right answer.

## 5. Under Serial Execution, Both Doctors Cannot Leave

Suppose the business logic is:

```text
BEGIN
    active_count = SELECT COUNT(*) WHERE is_on_call
    if active_count <= 1:
        refuse to let current doctor go off call
    if active_count > 1:
        UPDATE current doctor's row to FALSE
COMMIT
```

If A finishes before B:

1. A reads `count=2`, sets DR_A to FALSE, commits.
2. B reads `count=1`, gets rejected.
3. Result: DR_B remains on call.

If B finishes before A:

1. B reads `count=2`, sets DR_B to FALSE, commits.
2. A reads `count=1`, gets rejected.
3. Result: DR_A remains on call.

**No valid serial execution order allows both to leave the shift** if each transaction enforces "someone must remain on call after I leave."

Therefore, if two concurrent transactions both succeed and leave `count=0`, that outcome is a **serialization anomaly**.

## 6. Reproducing Write Skew Under REPEATABLE READ

Ensure both DR_A and DR_B are TRUE and no old lab transactions remain open.

Open two separate sessions:

- **Session A** acts for `DR_A`.
- **Session B** acts for `DR_B`.

Run **interleaved in exact order**. Running all of Session A first and then Session B is just serial execution and will not reproduce the anomaly.

### Step 1 — A Starts and Reads

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SHOW transaction_isolation;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Output:

```text
transaction_isolation = repeatable read
active_doctors = 2
```

Keep Transaction A open.

### Step 2 — B Starts and Also Reads

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Output: **2**.

Now **both A and B** have made decisions based on the initial state where two doctors are on call.

### Step 3 — A Updates DR_A's Row

**Session A:**

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE
RETURNING shift_id, doctor_id, is_on_call;
```

Output: DR_A is now FALSE inside Transaction A.

**Do not COMMIT yet.**

### Step 4 — B Updates DR_B's Row

**Session B:**

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
  AND is_on_call IS TRUE
RETURNING shift_id, doctor_id, is_on_call;
```

Output: DR_B is now FALSE inside Transaction B.

The two UPDATEs modify **two different rows**, so there is no direct same-row write conflict.

### Step 5 — Each Transaction Re-Checks Internally

**Session A:**

```sql
SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

A sees:

```text
DR_A = FALSE  (updated by A itself)
DR_B = TRUE   (according to A's snapshot)
active_doctors = 1
```

**Session B:** runs the exact same two SELECTs.

B sees:

```text
DR_A = TRUE   (according to B's snapshot)
DR_B = FALSE  (updated by B itself)
active_doctors = 1
```

**Both see the invariant satisfied** inside their own snapshot. Running an extra SELECT before COMMIT cannot fix the bug while reading an old snapshot.

### Step 6 — Both COMMIT

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
COMMIT;
```

Under this schedule in PostgreSQL `REPEATABLE READ`, **both commit successfully**.

Query from a fresh connection after both sessions finish:

```sql
SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Final result:

| doctor_id | is_on_call |
|---|---|
| DR_A | false |
| DR_B | false |

`active_doctors = 0`. **The invariant is broken.**

### Full Execution Timeline

| Step | Session A | Session B |
|---:|---|---|
| 1 | BEGIN REPEATABLE READ | — |
| 2 | SELECT count → 2 | — |
| 3 | — | BEGIN REPEATABLE READ |
| 4 | — | SELECT count → 2 |
| 5 | UPDATE DR_A → FALSE | — |
| 6 | — | UPDATE DR_B → FALSE |
| 7 | SELECT count → 1 in A's snapshot | — |
| 8 | — | SELECT count → 1 in B's snapshot |
| 9 | COMMIT | — |
| 10 | — | COMMIT |
| Afterward | **0 doctors on call** | **Invariant violated** |

The crucial condition to reproduce this is that **both initial SELECTs must execute before either transaction commits**.

## 7. Why Does PostgreSQL Allow This State?

PostgreSQL's `REPEATABLE READ` implements **snapshot isolation**:

- A transaction reads a stable snapshot starting around its first data query/modification.
- A transaction sees **its own** changes.
- A transaction does not see changes committed by other transactions after its snapshot.
- PostgreSQL prevents direct update conflicts on **the same row** in many cases.
- However, two transactions can update **two disjoint rows** and both commit.

A consistent per-transaction snapshot does not guarantee that the combined outcomes of **multiple concurrent transactions** match any valid serial schedule.

In our example, both A's and B's snapshots were valid at read time. The issue is that both **acted on information that became invalid once their commits combined**.

## 8. Read–Write Dependency Cycle

In the schedule just tested:

- A read DR_B as TRUE; B wrote DR_B to FALSE.
- B read DR_A as TRUE; A wrote DR_A to FALSE.

Diagrammed:

```text
A reads DR_B  ----(B writes DR_B)---->  B
 ^                                      |
 |                                      |
 +----(A writes DR_A)---- B reads DR_A -+

The read–write dependencies form a cycle:

           A ---- rw ----> B
           ^               |
           |               |
           +---- rw -------+
```

If A serialized before B, B would see DR_A already FALSE and refuse to leave. If B serialized before A, A would see DR_B already FALSE and refuse. **No serial order matches both "allowed to leave" decisions succeeding.**

That is why write skew is classified as a **serialization anomaly**, not simply "two writes happening too fast."

## 9. Distinguishing Write Skew from Lost Updates and Other Phenomena

| Phenomenon | Key Trait | Example |
|---|---|---|
| Dirty read | Reading uncommitted values from another transaction | Reading balance from a transaction that later rolls back |
| Nonrepeatable read | Reading the same row twice yields different values due to an intervening commit | Seeing price 100 then 120 |
| Phantom read | Re-running a predicate query gains or loses matching rows | Booking COUNT changes after a new INSERT |
| Lost update | Updates to the same entity overwrite/lose one change | Two clients edit the same stock count from a stale read |
| Write skew | Two transactions read a shared condition and update different rows | Two doctors both go off call |
| Deadlock | Transactions wait in a lock cycle | A holds lock X waiting for Y; B holds Y waiting for X |

### 9.1. Why Isn't Write Skew a Lost Update?

In our lab, A updated DR_A and B updated DR_B. Neither row was overwritten by the other's UPDATE. **Both updates persisted**, yet their combined outcome broke the rule.

### 9.2. If REPEATABLE READ Has No Phantoms, How Can Write Skew Still Happen?

PostgreSQL `REPEATABLE READ` uses snapshot isolation, so standard phantoms do not occur across multiple SELECTs in the same transaction. Yet **serialization anomalies can still occur**.

Absence of phantoms or nonrepeatable reads **is not sufficient to prove serializability**.

## 10. Isolation Levels and Write Skew Risk

PostgreSQL accepts these standard isolation levels:

| Isolation | Primary Read Behavior | Lab-Style Write Skew |
|---|---|---|
| `READ UNCOMMITTED` | Acts like READ COMMITTED in PostgreSQL | Possible |
| `READ COMMITTED` | Per-statement snapshot | Possible |
| `REPEATABLE READ` | Transaction-wide stable snapshot | Possible |
| `SERIALIZABLE` | Snapshot + serializability protection | Disallowed from both committing non-serializably |

Under `READ COMMITTED`, two transactions both reading `count=2` before either runs UPDATE can still produce write skew. If B runs SELECT after A commits, B sees `count=1` and refuses, yet **correctness must never rely on lucky timing**.

Under `REPEATABLE READ`, B's snapshot keeps seeing old data even after A commits if B's snapshot started earlier, making the risk clear.

### 10.1. Set Isolation Before Querying

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- SELECT/UPDATE inside transaction

COMMIT;
```

Or:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Subsequent queries run at the chosen level.

COMMIT;
```

You cannot acquire a snapshot, make a decision, and then raise isolation mid-transaction to "fix" that decision. Set isolation right at the transaction boundary before business queries.

## 11. Resetting Data for the Next Experiment

Only after both test transactions have finished:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = TRUE
WHERE shift_id = 1
  AND doctor_id IN ('DR_A', 'DR_B');

SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;
```

Confirm both rows are TRUE. Never reset while a lab transaction remains open; changing state mid-experiment makes results hard to interpret.

## 12. SERIALIZABLE: Blocking Write Skew with SSI

PostgreSQL uses **Serializable Snapshot Isolation (SSI)** to detect read–write dependencies that would make committed results non-serializable.

SSI does not force all transactions to wait behind a global table lock. They execute reads and writes concurrently, and one transaction receives a **serialization failure** if the combined commit schedule is unsafe.

### 12.1. Two-Session Practice

After resetting, **Session A**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Result: 2.

**Session B**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Result: 2.

**Session A**:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE;
```

**Session B**:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
  AND is_on_call IS TRUE;
```

Then try COMMIT in A and then B:

```sql
COMMIT;
```

### 12.2. Outcome

PostgreSQL **refuses to let both commit successfully** into a non-serializable schedule.

One transaction fails with an error such as:

```text
ERROR: could not serialize access due to read/write dependencies among transactions
SQLSTATE: 40001 (serialization_failure)
```

Exact message wording and timing vary; the error can trigger during a SQL statement or at `COMMIT`. **Do not assume Session A or Session B is always the victim.**

The failing transaction must be rolled back. The succeeding transaction takes one doctor off call while the other stays on call.

### 12.3. Why Does SERIALIZABLE Protect the Invariant?

SSI tracks read predicates and writes capable of invalidating previously read results. Here, A and B each read the set of active doctors and then modified what the other read.

Rather than letting both commit, PostgreSQL aborts one conflicting transaction so the committed transactions remain serializable.

**Note:** a serialization failure does not mean the database is broken; it is an active correctness-preservation mechanism.

## 13. SQLSTATE 40001 and Full-Transaction Retry

When `40001` occurs, do not re-run only the `UPDATE`. Start a **new** transaction and **re-read the count** to recompute the decision.

Why? Suppose A committed first and went off call. When B retries:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1 AND is_on_call IS TRUE;
```

The result is now **1**, not 2. B must **refuse to go off call**.

If B kept its old decision "I already saw count=2" and simply re-ran the UPDATE, the invariant would break.

### 13.1. Retry Algorithm

```text
MAX_ATTEMPTS = 3

for attempt in 1..MAX_ATTEMPTS:
    BEGIN SERIALIZABLE

    count = read active doctor count in shift

    if count <= 1:
        end transaction
        return LAST_DOCTOR_CANNOT_LEAVE

    changed = UPDATE current doctor
              WHERE is_on_call = TRUE

    if changed = 0:
        end transaction
        return NOT_ON_CALL_OR_NOT_FOUND

    COMMIT
    return SUCCESS

    if SQLSTATE 40001:
        ROLLBACK failed transaction
        bounded backoff
        retry FROM THE START (including read and decision)

    if other error:
        ROLLBACK
        handle by root cause

if retries exhausted:
    return transient contention error to caller
```

### 13.2. Errors to Distinguish

| SQLSTATE | Name | Meaning |
|---|---|---|
| `40001` | `serialization_failure` | Retry the entire transaction |
| `40P01` | `deadlock_detected` | Eligible for full-transaction retry per policy |
| `55P03` | `lock_not_available` | Lock unavailable under NOWAIT/timeout; handle separately |
| `23505` | `unique_violation` | Do not blindly retry all cases; usually a data conflict |
| `23514` | `check_violation` | CHECK constraint failed; usually requires fixing logic or data |

Inspect **SQLSTATE**, not exception message text, since wording can vary.

### 13.3. Never Retry Infinitely

Configure retry bounds, backoff (usually with jitter), request timeouts, and metrics. If contention stays excessive, inform the caller rather than looping forever.

## 14. Java/JDBC Transaction Retry Example

Core example with a configured `DataSource`. Each attempt uses a **fresh connection and transaction**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ShiftService {
    private final DataSource dataSource;

    public ShiftService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean stepOff(int shiftId, String doctorId)
            throws SQLException {

        for (int attempt = 1; attempt <= 3; attempt++) {
            try (Connection c = dataSource.getConnection()) {
                c.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);
                c.setAutoCommit(false);

                try {
                    int activeCount;
                    try (PreparedStatement ps =
                             c.prepareStatement("""
                                 SELECT COUNT(*)
                                 FROM ws218.shift_doctors
                                 WHERE shift_id = ?
                                   AND is_on_call IS TRUE
                                 """)) {
                        ps.setInt(1, shiftId);
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            activeCount = rs.getInt(1);
                        }
                    }

                    if (activeCount <= 1) {
                        c.commit();
                        return false;
                    }

                    int changed;
                    try (PreparedStatement ps =
                             c.prepareStatement("""
                                 UPDATE ws218.shift_doctors
                                 SET is_on_call = FALSE
                                 WHERE shift_id = ?
                                   AND doctor_id = ?
                                   AND is_on_call IS TRUE
                                 """)) {
                        ps.setInt(1, shiftId);
                        ps.setString(2, doctorId);
                        changed = ps.executeUpdate();
                    }

                    c.commit();
                    return changed == 1;

                } catch (SQLException ex) {
                    try {
                        c.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < 3) {
                        // Open a new transaction on the next attempt.
                        continue;
                    }
                    throw ex;
                }
            }
        }
        throw new SQLException("Failed to complete transaction");
    }
}
```

This example prioritizes demonstrating the mechanism; production systems also need:

- Authorizing the doctor and validating tenant/shift access.
- Distinguishing missing doctor, already off-call doctor, and wrong shift.
- Never returning a success response before `COMMIT`.
- Configuring the transaction manager/pool so isolation is set before queries and connection state resets cleanly upon pool return.
- Bounded retries, backoff, timeouts, and metrics.
- Idempotency/reconciliation for connection drops or ambiguous commit outcomes.
- Ensuring **every related write path** obeys the invariant.

When using a framework transaction manager, configure isolation and retries at the framework's **transaction boundary** rather than opening nested transactions inside an already managed one.

## 15. Shared Coordinator Row Lock Under READ COMMITTED

Another solution **forces all transactions modifying the same shift to contend on one shared row**, instead of editing only their own doctor row.

`ws218.shifts` already has a row for `shift_id = 1`. We use it as a **guard row**.

Workflow:

1. BEGIN under `READ COMMITTED`.
2. Run `SELECT ... FOR UPDATE` on shift row 1.
3. Once locked, **read the count in a separate SELECT**.
4. Update the doctor to FALSE only if `count > 1` and the doctor is on call.
5. COMMIT or ROLLBACK releases the lock.

### 15.1. Session A

Reset both doctors to TRUE. A runs:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM ws218.shifts
WHERE shift_id = 1
FOR UPDATE;
```

A now holds the guard row lock. Continue:

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Count=2. A is allowed to update:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE;

COMMIT;
```

### 15.2. Session B

While A has not yet committed, B runs:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM ws218.shifts
WHERE shift_id = 1
FOR UPDATE;
```

B must **wait on the guard row** locked by A.

After A commits, B acquires the lock and runs a **new SELECT**:

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Under `READ COMMITTED`, the new SELECT observes A's committed update. `Count=1`, so **B must not update DR_B**.

```sql
ROLLBACK;
```

Outcome: DR_A=FALSE, DR_B=TRUE. The invariant holds.

### 15.3. Why Does This Protocol Work?

Both transactions cannot pass the guard row lock simultaneously. B must wait for A to finish, then read a fresh statement snapshot after acquiring the lock.

**Mandatory requirement:** every writer affecting active doctor counts for that shift must lock the same guard row before deciding. If a separate batch job updates `shift_doctors` without taking that lock, the invariant can still break.

### 15.4. Caution When Applying Under REPEATABLE READ

Locking a shared row **does not refresh a REPEATABLE READ snapshot after waiting**. If B already fixed an old snapshot before A committed, and then waited on an unmodified guard row, B would still read the stale doctor count.

Therefore, the `FOR UPDATE guard → SELECT count` pattern above is tailored specifically for **READ COMMITTED**. Under REPEATABLE READ or SERIALIZABLE, you must also enforce **write conflicts or serialization retries**.

## 16. Why Locking Only DR_A and DR_B Individually Is Not Enough

A tempting mistake:

**A:**

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
FOR UPDATE;
```

**B:**

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
FOR UPDATE;
```

A and B lock **two disjoint rows**, with zero overlap forcing them to wait on each other. Both can still conclude "the other doctor is on call" from their snapshots.

If you lock the entire list of doctors for the shift:

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id
FOR UPDATE;
```

then transactions contend on the same rows. However:

- You must lock base rows, not an aggregate `SELECT COUNT(*) ... FOR UPDATE`.
- If doctors can be INSERTed/DELETEd, locking only existing rows does not necessarily protect the whole predicate.
- Use a consistent lock order to reduce deadlocks.
- Under REPEATABLE READ, snapshot and serialization error rules still apply.
- Locking many rows can be heavier than locking a single guard row.

Choose a locking granularity matching the **unit of the invariant**.

## 17. Forcing a Shared Write–Write Conflict via Guard Version

`shifts` has a `version` column. Instead of only `SELECT FOR UPDATE`, every writer can **explicitly UPDATE** the guard row:

```sql
UPDATE ws218.shifts
SET version = version + 1
WHERE shift_id = 1
RETURNING version;
```

When run at the start of the transaction:

- Under READ COMMITTED, a competing transaction waits on the same-row update; the subsequent `SELECT count` reads a fresh snapshot.
- Under REPEATABLE READ, if a snapshot is already established and another transaction modified the guard row after it, PostgreSQL raises `40001`. The application must retry the entire transaction.
- Two writers on the same shift are forced into a shared write conflict instead of touching disjoint doctor rows.

Application steps example:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE ws218.shifts
SET version = version + 1
WHERE shift_id = 1
RETURNING version;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;

-- Only if count > 1 and the doctor is on call:
-- UPDATE ws218.shift_doctors SET is_on_call=FALSE ...

COMMIT;
```

**Never run the doctor UPDATE unconditionally:** the application must branch based on the freshly read count.

Trade-offs: every writer must obey the protocol; a hot row increases contention, WAL, and bloat. Lock per shift rather than using a single global row so unrelated shifts do not block each other.

## 18. How Do Advisory Locks Fit?

PostgreSQL supports **advisory locks** keyed by application-defined integers:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT pg_advisory_xact_lock(218, 1);

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;

-- UPDATE only if count > 1.
-- COMMIT or ROLLBACK when finished.
```

`pg_advisory_xact_lock` is transaction-scoped and automatically releases when the transaction ends. `(218,1)` is just an illustrative namespace/ID pair; applications must allocate lock keys carefully to avoid collisions across features.

**Important:**

- Advisory locks are **voluntary**. Direct SQL modifying the table is not forced to acquire the lock.
- Session-level advisory locks have different lifetimes; misusing them with connection pools can hold locks far longer than intended.
- Advisory locks **do not refresh an older REPEATABLE READ snapshot**.
- When acquiring multiple locks in one transaction, enforce a consistent lock order to prevent deadlocks.
- Do not generate unbounded lock keys; lock-manager memory is finite.

## 19. What Can Constraints Protect?

Each constraint type has a distinct scope:

| Constraint / Mechanism | Typically Protects | Directly Enforces "At Least One Doctor On Call"? |
|---|---|---|
| `CHECK` | Condition on a single row | Not directly |
| `NOT NULL` | Single column non-null | No |
| `UNIQUE` | No duplicate keys, "at most one" per model | No |
| Partial UNIQUE | At most one row matching predicate | No |
| Foreign key | Valid references | Does not enforce on-call state |
| Exclusion constraint | No conflicting row pairs under declared operators | Not directly |
| COUNT-checking trigger | Encapsulates rule in DB | **Still races** without synchronization |
| SERIALIZABLE + retry | Multi-row decisions must serialize | Protects if every workflow complies |

### 19.1. Why Isn't CHECK Enough?

`CHECK (is_on_call IN (TRUE,FALSE))` only validates a single row's boolean. It knows nothing about other rows in the shift.

Putting a subquery inside a CHECK function to count other rows is not a supported/safe PostgreSQL pattern for cross-row invariants. Never hide cross-table queries inside a CHECK function assuming it is race-free under concurrent writes.

### 19.2. Why Isn't Partial UNIQUE Enough?

A partial unique index can enforce:

> Each shift has **at most one** lead doctor.

However, it cannot create a lead doctor when **zero exist**. "At most one" and "at least one" constrain opposite directions.

### 19.3. Redesigning the Schema

If the true business rule is "every shift must have one **designated responsible doctor**," you could put a `NOT NULL` doctor reference column on `shifts` backed by a foreign key.

Still, **having an assigned responsible doctor** is not identical to **having someone actively on call**. If an assigned doctor can be deactivated or marked off call in another table, the model must protect that link too. Changing schema without proving rule equivalence is insufficient.

## 20. A COUNT-Checking Trigger Can Still Suffer Write Skew

Someone might propose:

> "Write a BEFORE UPDATE trigger: if at least one doctor remains on call after this update, allow the UPDATE."

If the trigger simply runs `SELECT COUNT` over the doctors inside the transaction's snapshot:

- A's trigger sees DR_B still on call.
- B's trigger sees DR_A still on call.
- A updates DR_A; B updates DR_B.
- Both transactions still commit under REPEATABLE READ and break the invariant.

**Triggers centralize logic, yet do not automatically create serializability.** Using a trigger to enforce an invariant still requires concurrency-safe isolation, locking, or schema design—and multi-writer testing.

Even a deferred trigger or "late check" fails if its `COUNT` query reads an unsynchronized snapshot. You must prove the mechanism blocks two transactions from passing the check concurrently.

## 21. Another Example: Overbooking Capacity

Suppose a room has `capacity=1` and the bookings table is initially empty. Two parallel booking requests arrive:

```text
T_A: SELECT COUNT(*) confirmed bookings -> 0
T_B: SELECT COUNT(*) confirmed bookings -> 0

T_A: INSERT booking A (distinct ID, CONFIRMED)
T_B: INSERT booking B (distinct ID, CONFIRMED)

T_A COMMIT
T_B COMMIT

Outcome: 2 bookings in a room with capacity=1
```

Both transactions read the **predicate** "CONFIRMED bookings for this room," then INSERT two distinct rows. There is no UNIQUE collision if each booking has its own ID.

A UNIQUE constraint on `(resource_id, slot_id)` solves **one booking per named slot**. Yet the general invariant "booking count <= capacity" cannot always be reduced to uniqueness alone.

### 21.1. Moving Quota to an Atomic Single-Row Update

Alternative design:

```sql
CREATE TABLE ws218.capacity_demo (
    resource_id integer PRIMARY KEY,
    capacity integer NOT NULL CHECK (capacity >= 0),
    occupied integer NOT NULL DEFAULT 0,
    CHECK (occupied >= 0 AND occupied <= capacity)
);

INSERT INTO ws218.capacity_demo(resource_id, capacity, occupied)
VALUES (1, 1, 0);
```

Reserving a spot:

```sql
UPDATE ws218.capacity_demo
SET occupied = occupied + 1
WHERE resource_id = 1
  AND occupied < capacity
RETURNING occupied, capacity;
```

Both requests contend on **the exact same row**. The conditional UPDATE checks and increments the quota atomically under PostgreSQL's concurrency rules.

However, if a separate bookings table exists, **every booking or cancellation must update both the booking row and the quota row in the same transaction**. If the counter drifts from actual bookings, the counter's CHECK passes while real booking data is wrong.

## 22. SSI and Predicate / SIREAD Locks

PostgreSQL `SERIALIZABLE` uses SSI to track dangerous **read–write dependencies**, even when one transaction reads a predicate-matched row set and another transaction modifies that set.

Distinguish:

- **MVCC snapshot:** which row versions a transaction can see.
- **Row-level lock / FOR UPDATE:** conflicting locks that make other transactions wait when modifying/locking the same row.
- **SSI SIREAD / predicate locks:** track read ranges to detect serialization anomalies; they do not block writers up front.

Thus under SERIALIZABLE you can observe:

```text
A SELECT -> B SELECT -> A UPDATE -> B UPDATE
-> one transaction receives 40001
```

rather than every SELECT blocking the other transaction.

### 22.1. Inspecting SIREAD Locks

While an appropriate SERIALIZABLE session is active, you can inspect:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
```

Results depend on timing, query plan, privileges, and lock escalation granularity. **Never treat the presence or absence of an `SIReadLock` row as proof of invariant enforcement.** Real verification evaluates committed data state.

### 22.2. Overhead and False Positives

SSI can raise `40001` even when a human reading logs sees a schedule that "looks harmless." That is the trade-off of conservative cycle detection preventing non-serializable schedules. Applications must never ignore `40001` just because a manual check happens to show valid data.

## 23. Testing Concurrency with Two Connections and Barriers

A sequential test cannot reproduce write skew. Use two independent connections:

```text
Test runner
   |
   +---- Connection A: BEGIN
   |
   +---- Connection B: BEGIN
   |
   +---- A: SELECT count -> 2 ----+
   |                              |
   +---- B: SELECT count -> 2 ----+--> BARRIER
                                          |
                               Allow both to UPDATE
                                          |
                     A: UPDATE DR_A   B: UPDATE DR_B
                           |               |
                        COMMIT          COMMIT
                           \               /
                         Re-read committed data
                               |
                      assert active_count >= 1
```

### 23.1. Under REPEATABLE READ

The learning goal is **reproducing a schedule where both transactions commit** to demonstrate how the invariant can break. The final query can return `active_count=0`.

### 23.2. Under SERIALIZABLE

The goal is ensuring **no schedule lets both transactions commit with `count=0`**. One succeeds while the other receives `40001`. On retry, the aborted transaction re-reads the count and refuses to leave if only one doctor remains.

### 23.3. Why Not Just Use pg_sleep?

`pg_sleep` slows execution, yet does not guarantee both transactions **finished reading** before either writer ran. Fixed-sleep tests are flaky. Explicit barriers confirming "read done" and "proceed to write" yield reliable tests.

### 23.4. What to Record in Test Output?

```text
A:
  isolation:
  count before update:
  update row count:
  commit outcome:
  SQLSTATE if errored:

B:
  isolation:
  count before update:
  update row count:
  commit outcome:
  SQLSTATE if errored:

After both finish:
  committed active_count:
  invariant_holds:
```

A proper test does not assert only HTTP status codes or update counts; it asserts **post-commit invariants**.

## 24. Testing Edge Cases

Beyond two doctors leaving simultaneously, test:

- A shift starting with only **one** doctor on call → must refuse leaving.
- A shift with zero doctor rows → verification query must catch the violation rather than omitting it via GROUP BY.
- Two requests for the same doctor → distinguish no-op, missing doctor, and success.
- One request updates an existing doctor while another inserts a new doctor.
- An admin bulk action deactivating multiple doctors at once.
- A batch job bypassing the regular service API.
- A transaction rolling back after UPDATE.
- A transaction hitting `40001`, retrying, and reaching a **different** decision than its first attempt.
- Two independent shifts processed concurrently → must not suffer unnecessary global locking.
- A transaction hitting deadlock or lock timeout.
- An HTTP retry after the client lost the commit response.
- RLS or tenant filters altering which doctors a role can see.

The goal is not merely triggering one failing schedule, but verifying **every write path that can affect the invariant**.

## 25. In-Transaction Checks vs. Post-Commit Verification

Under REPEATABLE READ, A saw `count=1` and B saw `count=1`. Yet after both committed, a new session saw `count=0`.

Those are two different perspectives:

1. A transaction's private snapshot used to make decisions.
2. The shared committed state after transactions conclude.

Therefore:

- Adding an extra `SELECT COUNT` right before `COMMIT` under REPEATABLE READ **cannot prevent write skew**.
- Periodic post-commit audits can **detect** corrupted data, yet cannot **prevent** corruption.
- You need write-time protection, paired with post-commit verification to audit effectiveness.

A boolean verification query:

```sql
SELECT NOT EXISTS (
    SELECT 1
    FROM ws218.shifts AS s
    LEFT JOIN ws218.shift_doctors AS d
        ON d.shift_id = s.shift_id
    GROUP BY s.shift_id
    HAVING COUNT(d.doctor_id)
             FILTER (WHERE d.is_on_call IS TRUE) = 0
) AS invariant_holds;
```

Returning `true` means no violating shift was found in that query's snapshot. It is a point-in-time observation, not a lock preventing future violations.

## 26. Monitoring Errors, Locks, and Transactions

For production, logs and metrics should include:

- Request/correlation ID and resource/shift ID subject to privacy rules.
- Isolation level.
- Retry attempt count and COMMIT outcome.
- SQLSTATE `40001` or `40P01`.
- Transaction duration and lock wait time.
- Transactions holding locks too long.
- Rate of invariant violations caught by reconciliation queries.

Diagnostic query for waiting sessions:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 120) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Visibility depends on system privileges and timing. Never log raw sensitive transaction data indiscriminately.

### 26.1. Do Not Confuse Deadlocks with Write Skew

- **Deadlock:** a lock-wait cycle; PostgreSQL detects it and aborts one transaction.
- **Write skew:** can happen with zero lock waits because each transaction edits a different row; **an invariant can break even without deadlocks**.
- **Serialization failure:** SSI rejects a non-serializable commit schedule, which can happen without prolonged lock waits.

### 26.2. Keep Transactions Short

Never keep a transaction open while waiting on users, slow payment APIs, or synchronous email delivery. Long transactions increase contention, lock waits, stale snapshots, and retry costs.

For external side effects, use a transactional outbox and post-commit processing; never send an "off-call confirmed" notification before commit actually succeeds.

## 27. Retries and Idempotency Are Related Yet Distinct Problems

A `40001` retry means the transaction aborted and must be redone.

An HTTP retry after connection loss or timeout near `COMMIT` is trickier: the client may **not know whether the transaction committed or not**.

Systems therefore need:

- An idempotency key for business requests where appropriate.
- Binding the key to resource/tenant and payload.
- Distinguishing first request, identical retry, and payload mismatch on the same key.
- Avoiding repeating already committed side effects.
- After a serialization failure, re-running the entire read–decide–write flow in a new transaction.
- Publishing events or confirming success only once commit outcome is verified.

A `UNIQUE` constraint on an idempotency key is one piece of protection, not a replacement for full transaction coordination.

## 28. Security and Multi-Tenancy

If the tables serve multiple organizations:

```text
tenant_id, shift_id, doctor_id, is_on_call
```

then the actual invariant is:

```text
For every active (tenant_id, shift_id):
    active_count >= 1
```

Checks and updates must filter by the **exact `(tenant_id, shift_id)` pair**. Filtering only by `WHERE shift_id=1` could mix data across two tenants sharing `shift_id=1`, corrupting invariant checks or leaking data.

Ensure:

- `tenant_id` comes from authenticated context.
- Primary/foreign keys and JOINs include tenant columns when required.
- Guard locks / advisory keys are scoped per `(tenant_id, shift_id)`.
- RLS enforces access control, yet **does not by itself prevent write skew**.
- Every write path, including admin and batch jobs, obeys the invariant protocol.

## 29. Common Mistakes

### Mistake 1. Assuming REPEATABLE READ Is Always Safe

PostgreSQL REPEATABLE READ uses snapshot isolation and still permits write skew.

**Fix:** `SERIALIZABLE` + retry, or an appropriate locking/constraint mechanism.

### Mistake 2. Locking Only the Current Doctor's Row

Two transactions lock disjoint rows and still decide from stale snapshots.

**Fix:** synchronize on the unit of the invariant, such as a shift guard row.

### Mistake 3. Running SELECT COUNT Twice Thinking It Prevents Errors

Under REPEATABLE READ, both reads use the same stable snapshot and miss the other transaction's uncommitted/later commit.

**Fix:** fix the concurrency mechanism, not just the number of SELECTs.

### Mistake 4. Running SELECT FOR UPDATE on a COUNT Aggregate

An aggregate `COUNT` is not a base row that can be locked like a table row; lock base rows or a guard row instead.

### Mistake 5. Using a Guard Lock Under REPEATABLE READ Assuming It Refreshes the Snapshot

Locks do not refresh snapshots. You need write conflicts/retries or the proper READ COMMITTED protocol.

### Mistake 6. Thinking Partial UNIQUE Guarantees At Least One Doctor

`UNIQUE` enforces an **upper** bound ("at most one"), not a **lower** bound ("at least one").

### Mistake 7. Trigger Counting Doctors Without Synchronization

A trigger can also read stale snapshots and let both concurrent transactions pass.

### Mistake 8. Using SERIALIZABLE and Swallowing 40001

A failed transaction must never be reported as successful. Roll back and retry the entire decision.

### Mistake 9. Retrying Only UPDATE Without Re-Running SELECT

The prior `count=2` assumption may no longer hold.

### Mistake 10. Not Checking Committed State in Tests

A test asserting only `UPDATE 1` or HTTP 200 misses cross-row invariant violations.

### Mistake 11. Testing Only Sequentially

Without interleaved schedules, write skew never surfaces.

### Mistake 12. Using pg_sleep as a Reliable Barrier

Fixed sleeps do not prove both sessions finished reading before writing.

### Mistake 13. Counting Only on the Child Table and Skipping Empty Shifts

`GROUP BY` on `shift_doctors` produces no row for shifts with zero assignments.

**Fix:** `shifts LEFT JOIN shift_doctors` or `NOT EXISTS`.

### Mistake 14. Sending Email Before COMMIT

The transaction can roll back afterward, leaving a false notification sent.

### Mistake 15. Another Job Bypassing the Protocol

One safe API endpoint is not enough if a batch script or admin tool writes directly.

### Mistake 16. Using One Global Lock for All Shifts

Independent shifts block each other needlessly.

**Fix:** scope locks to the unit of the invariant.

## 30. Hands-On Exercises with Solutions

### Exercise 1. Write the Exact Condition

**Prompt:** every shift must have at least one doctor with TRUE.

**Solution:** `COUNT(doctor_id) FILTER (WHERE is_on_call IS TRUE) >= 1` for every shift in scope.

### Exercise 2. Why Can't Both A and B Leave Under Serial Execution?

**Solution:** after the first transaction commits, `count=1`, so the second transaction must refuse.

### Exercise 3. Do the Two UPDATEs Modify the Same Row?

**Solution:** no. A edits DR_A and B edits DR_B. Hence there is no direct same-row write–write conflict.

### Exercise 4. How Must Two Transactions Interleave Under REPEATABLE READ?

**Solution:** A `SELECT count=2`, B `SELECT count=2`, A `UPDATE DR_A`, B `UPDATE DR_B`, then both `COMMIT`. Both sessions must be independent and see two TRUE rows in their initial snapshots.

### Exercise 5. Why Does Each Session's Own SELECT After UPDATE See count=1?

**Solution:** each sees its own uncommitted change while still seeing the other doctor as TRUE in its prior snapshot.

### Exercise 6. Find Shifts with No Remaining On-Call Doctor

```sql
SELECT s.shift_id
FROM ws218.shifts AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM ws218.shift_doctors AS d
    WHERE d.shift_id = s.shift_id
      AND d.is_on_call IS TRUE
);
```

**Solution:** returns shifts lacking any TRUE doctor, including shifts with zero assignment rows.

### Exercise 7. Why Can Write Skew Occur Without a Deadlock?

**Solution:** both UPDATEs touch different rows and never wait on each other's locks, yet the invariant still breaks.

### Exercise 8. How Does SERIALIZABLE Protect Against This?

**Solution:** SSI detects non-serializable read–write dependency cycles and aborts one transaction with a serialization failure when needed.

### Exercise 9. What Must Be Retried After 40001?

**Solution:** roll back, open a new transaction, re-read `SELECT count`, recompute the decision, and only then UPDATE and COMMIT if still allowed.

### Exercise 10. What Is the Proper Sequence for Guard Row Locking?

**Solution:** `BEGIN READ COMMITTED` → `SELECT shift FOR UPDATE` → `SELECT COUNT` in a separate statement → decide → `UPDATE doctor` → `COMMIT`/`ROLLBACK`.

### Exercise 11. What If the Guard Row Is Only Locked Without Being Updated Under REPEATABLE READ?

**Solution:** the snapshot can remain stale after waiting. Do not assume READ COMMITTED behavior carries over unchanged; use write conflicts/serialization retries instead.

### Exercise 12. Is a Doctor-Counting Trigger Safe on Its Own?

**Solution:** no. A trigger alone does not stop two concurrent snapshots from both seeing the other doctor as TRUE.

### Exercise 13. If a Shift Has 0 Assignment Rows, What Does GROUP BY on the Child Table Return?

**Solution:** no group for that shift at all. Start from `shifts`/`NOT EXISTS` to catch empty shifts.

### Exercise 14. Can UNIQUE Enforce "At Most One Lead Doctor"?

**Solution:** a partial unique index per shift can enforce "at most one." However, that is **not** "at least one on call."

### Exercise 15. What Bug Occurs When Two Bookings with Different IDs Insert at capacity=1?

**Solution:** a predicate-count serialization anomaly; both transactions read `count=0` and insert distinct rows, exceeding capacity 1.

### Exercise 16. How Do You Update Quota When Stored on a Single Row?

```sql
UPDATE ws218.capacity_demo
SET occupied = occupied + 1
WHERE resource_id = 1
  AND occupied < capacity
RETURNING occupied;
```

**Solution:** condition check and quota increment run atomically on a shared row. Keep it synchronized with actual booking rows inside the same transaction.

### Exercise 17. If a Transaction Hits SQLSTATE 40P01, Is That Write Skew?

**Solution:** `40P01` is `deadlock_detected`. It is a lock-contention error, not proof of write skew. Retry the full transaction per policy.

### Exercise 18. Does Inspecting pg_locks Prove the Invariant Always Holds?

**Solution:** no. `pg_locks` is for lock diagnostics; invariants must be verified on data state and protected by a sound write protocol.

### Exercise 19. What If an Internal Job Edits Doctors Without Taking the Guard Lock?

**Solution:** it can break guarantees enforced by the main service. Every write path must obey the invariant protocol.

### Exercise 20. How Does an HTTP Retry Differ from a Serialization Retry?

**Solution:** after `40001`, the transaction definitely did not commit; after a network drop around `COMMIT`, the client may not know whether it succeeded. The latter requires idempotency and reconciliation.

## 31. Pre-Deployment Checklist

| Question | Why It Matters |
|---|---|
| Is the invariant written as an exact predicate? | Defines what valid data looks like |
| Do multiple rows jointly determine a condition? | Identifies potential write skew |
| Have all endpoints/jobs modifying the row set been mapped? | One uncoordinated writer can break data |
| What is the actual isolation level? | Do not confuse REPEATABLE READ with SERIALIZABLE |
| Was it tested with two independent connections? | Sequential tests miss anomalies |
| Were both SELECTs synchronized before UPDATE? | Reproduces the concurrent race accurately |
| If using SERIALIZABLE, is `40001` retried full-transaction? | Avoids acting on stale decisions |
| If using a guard lock, do all writers share the same lock key? | Ensures real synchronization |
| Under READ COMMITTED, is count queried after acquiring lock? | Avoids reading before the lock |
| Can inserts/deletes alter the row set? | Existing-row locks may not cover predicates |
| Can any DB constraint express the invariant directly? | Protects every writer automatically when feasible |
| Are retry caps, backoff, and SQLSTATE logging present? | Prevents hung requests and blind debugging |
| Is state re-read after all COMMITs/ROLLBACKs? | Verifies committed truth |
| Are shifts with zero doctor rows caught by verification? | Prevents false negatives |
| Are external side effects emitted before commit? | Prevents false notifications |
| Are locks scoped properly per tenant/shift? | Prevents cross-tenant leaks and excess contention |

## 32. Comparing Solutions

| Approach | Mechanism | Pros | Cons |
|---|---|---|---|
| `SERIALIZABLE + retry` | SSI blocks non-serializable schedules | Protects cross-row dependencies | Needs `40001` retries; all writers must comply |
| `READ COMMITTED + guard FOR UPDATE` | Every writer locks one shared row before reading | Easy to reason about | Requires strict protocol compliance, lock waits |
| `UPDATE guard version` | Forces shared write–write conflict | Detects stale snapshots | Extra contention, needs RR retries |
| Transaction-scoped advisory lock | Logical lock per shift | No physical guard row needed | Voluntary, does not refresh snapshots |
| Atomic single-row quota update | Check and write on the same row | Great for counters/capacities | Must stay synced with detail rows |
| Suitable DB constraints | DB rejects invalid state | Protects even non-app writers | Cannot express all multi-row rules |
| Trigger + proper protocol | DB-enforced logic | Centralizes rules | Simple COUNT triggers still race |
| Periodic verification | Detects broken invariants | Supports monitoring/reconciliation | **Does not prevent** corruption |

## 33. PostgreSQL Reference Documentation

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): comparing READ COMMITTED, REPEATABLE READ, and SERIALIZABLE, snapshots and SSI.
- [Serialization Failure Handling](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html): transaction retries and SQLSTATE `40001`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, deadlocks, advisory locks, and locking options.
- [SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): setting isolation levels at transaction boundaries.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): scope of CHECK, UNIQUE, foreign keys, and data constraints.

When applying in real environments, check your exact server version:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

## 34. Summary

Write skew occurs when **two transactions read a shared business condition, update different rows, and both commit so the condition no longer holds**.

With two doctors:

```text
Initial:   DR_A=TRUE,  DR_B=TRUE   -> active_count=2
T_A reads: active_count=2
T_B reads: active_count=2
T_A writes: DR_A=FALSE
T_B writes: DR_B=FALSE

REPEATABLE READ:
    Both transactions can COMMIT
    DR_A=FALSE, DR_B=FALSE
    active_count=0 -> VIOLATION

SERIALIZABLE:
    Cannot allow both to COMMIT into an illegal schedule
    One transaction may receive 40001
    Retry whole transaction -> read new count -> refuse leaving shift
    Final active_count stays >= 1
```

Key principles to remember:

1. **Define the invariant before writing transactions.** It often spans multiple rows or a predicate-filtered set.
2. **A consistent snapshot is not serializable.** PostgreSQL REPEATABLE READ still allows write skew.
3. **Locking only the row you edit is insufficient** when decisions depend on other rows; lock the scope of the invariant or use SERIALIZABLE.
4. **SERIALIZABLE requires handling `40001`**, rolling back and retrying the entire read–decide–write logic.
5. **A guard row under READ COMMITTED** serializes same-shift decisions if every writer locks first and reads count in a fresh statement afterward.
6. **Constraints must match semantics.** "At most one" `UNIQUE` does not replace "at least one" invariants; naive counting triggers also race.
7. **Concurrency tests need barriers**, and SQL assertions must verify committed state including empty shifts.
8. **Detection is not prevention.** Verification queries and monitoring spot bad data, while only a sound write protocol prevents write skew.
9. **Keep every write path consistent:** services, API retries, batch jobs, admin scripts, and multi-tenant flows must share one protective design.

**One sentence to remember:** write skew is not two transactions editing the same row, but two transactions trusting the same multi-row condition and editing different rows so that condition breaks after COMMIT.
