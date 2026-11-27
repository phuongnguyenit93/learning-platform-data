# Serialization Failures and Retrying the Entire Transaction in PostgreSQL

Two users place orders simultaneously, two processes update a quota concurrently, or two administrators modify an on-call schedule at the same time: each transaction individually "sees valid data," yet **the combined outcome of concurrent execution** breaks a business rule. PostgreSQL provides transaction isolation levels to control these interactions. At `SERIALIZABLE`, the database ensures that the outcomes of committed transactions are equivalent to **some valid serial execution order**. Whenever it cannot guarantee that, PostgreSQL may **abort a transaction** with:

```text
SQLSTATE 40001 — serialization_failure
ERROR: could not serialize access due to ...
```

This is not necessarily a database failure. It is normally the **intentional data-protection mechanism working as designed** under genuine transaction contention. However, if an application catches that error and retries only the final `UPDATE`/`INSERT` statement, it may still act on a **decision computed from an obsolete snapshot** and produce corrupt data.

Accordingly, the central rule of this lesson is:

> **When encountering `serialization_failure`, `ROLLBACK` the failed transaction, start a brand-new transaction, and re-execute all work that can influence the write decision: reads, computations, precondition checks, and writes, including `COMMIT`.**

This lesson belongs to the **Transactions** chapter in the *Database Engine Relational PostgreSQL* module. You will learn:

- Why PostgreSQL raises `40001` and how it relates to MVCC, `REPEATABLE READ`, `SERIALIZABLE`, and Serializable Snapshot Isolation (SSI).
- Hands-on **write skew** testing across two `psql` windows: two transactions both see "enough doctors on duty" yet modify different rows.
- Distinguishing `40001` from deadlock `40P01`, lock timeouts, constraint errors, and already-aborted transactions.
- Designing a proper **transaction retry boundary**: restarting from reads, covering `COMMIT` errors, bounding attempts, and backing off with jitter.
- A self-contained Java/JDBC example using `DataSource`, `Connection`, `PreparedStatement`, `SQLState`, `rollback`, and `commit`.
- Additional application concerns: idempotency, HTTP/payment/email side effects, transactional outboxes, ambiguous `COMMIT` outcomes on network drops, timeouts, monitoring, and concurrency testing.

> **Version note:** Examples use transaction and SSI features of modern PostgreSQL. Serializable Snapshot Isolation has been built into PostgreSQL since version 9.1. Examples use standard PostgreSQL SQL and Java 17+; no extensions are required. Test on a practice database, never modifying production data.

---

## 1. Concept: What Does "Serializable" Guarantee?

### 1.1. Transactions and Correctness

A **transaction** groups multiple steps into one unit:

```sql
BEGIN;

-- Read data to decide.
SELECT ...;

-- Modify data based on the decision.
UPDATE ...;

COMMIT;
```

If an error occurs:

```sql
ROLLBACK;
```

`COMMIT` confirms a successful transaction's changes; `ROLLBACK` discards uncommitted changes. In practice, transaction boundaries also govern snapshots, locks, visibility, and concurrency behavior.

### 1.2. Serializability Does Not Mean "All Transactions Run One After Another"

**Serializable** is an **outcome-equivalence guarantee**: transactions may execute concurrently and overlap, provided the committed outcome can be explained as if those transactions had executed sequentially in some serial order.

Transactions do not have to commit in the order they started. PostgreSQL does not lock the entire database to run one transaction at a time.

When two contending transactions cannot both fit into any valid serial schedule, PostgreSQL **lets one succeed and forces the other to fail**, leaving the application to decide whether to retry.

### 1.3. Example Rule: "Always Keep At Least One Doctor on Duty"

Suppose two doctors, An and Bình, are both on duty:

```text
doctor_id | on_duty
----------+--------
1         | true
2         | true
```

Rule: a doctor may go off duty only if **at least one other doctor remains on duty**.

Transaction A wants to take An off duty:

1. Counts doctors on duty → 2.
2. Sees the condition is met for one doctor to leave.
3. Sets `on_duty=false` for An.

Transaction B wants to take Bình off duty:

1. Counts doctors on duty → 2.
2. Sees the condition is met for one doctor to leave.
3. Sets `on_duty=false` for Bình.

If both transactions run on concurrent snapshots, both can observe **2 doctors on duty** and edit **two different rows**. Afterward nobody is on duty: **a business invariant failure even though no two transactions modified the same row**.

This phenomenon is **write skew**. Serializable isolation is designed to reject committed schedules whose outcome matches no valid serial execution.

---

## 2. Relevant Transaction Isolation Levels

PostgreSQL supports the SQL-declared isolation levels, each with specific practical rules.

| Isolation Level | Overview in PostgreSQL | Key Point to Remember |
|---|---|---|
| `READ COMMITTED` | Each statement normally reads a fresh snapshot | Default; multi-statement read-then-decide logic can see changing data |
| `READ UNCOMMITTED` | Treated essentially as `READ COMMITTED` in PostgreSQL | No dirty reads unlike some other engines |
| `REPEATABLE READ` | Stable transaction snapshot; implements snapshot isolation | Prevents many anomalies, yet **write skew** remains possible |
| `SERIALIZABLE` | Serializable Snapshot Isolation (SSI) | Prevents non-serializable committed outcomes; may raise `40001` |

**Do not misunderstand:** PostgreSQL's `REPEATABLE READ` is strong regarding snapshot stability, yet it does not guarantee multi-row invariants when two transactions write to different rows.

### 2.1. READ COMMITTED

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT ...;
UPDATE ...;
COMMIT;
```

At this level, a `SELECT` and a subsequent `UPDATE` can see **different snapshots**. It suits many simple CRUD workloads; protecting multi-row invariants requires extra predicates, row locks, or stronger isolation.

### 2.2. REPEATABLE READ

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT ...;
UPDATE ...;
COMMIT;
```

Statements in the transaction share one consistent snapshot established per the level's rules. Still, **two transactions can read the same state and update disjoint rows**, causing write skew.

PostgreSQL can also raise **`40001` under `REPEATABLE READ`**, such as when a transaction tries to update a row already modified by a concurrent transaction after its snapshot. Never assume `40001` occurs only under `SERIALIZABLE`.

### 2.3. SERIALIZABLE

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT ...;
UPDATE ...;
COMMIT;
```

At this level, PostgreSQL tracks dangerous read–write dependencies across transactions. If committing risks creating a non-serializable schedule, the engine picks one transaction as a **serialization victim** and aborts it.

Crucial consequence: applications **must be built to catch and retry `40001`**. Never deploy `SERIALIZABLE` assuming every transaction will always commit.

### 2.4. Choosing an Isolation Level by Requirement

Not every operation needs `SERIALIZABLE`. Many problems can enforce constraints using:

- `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`.
- An atomic conditional `UPDATE ... WHERE balance >= amount`.
- `SELECT ... FOR UPDATE` on rows requiring locks.
- Exclusion constraints for overlapping ranges.
- Serializing a business resource via an explicit coordinator lock.

When rules depend on a **set of rows or search predicate**, SSI under `SERIALIZABLE` is a powerful option. Weigh correctness, contention rate, transaction duration, and application retry support.

---

## 3. MVCC and Serializable Snapshot Isolation (SSI)

### 3.1. MVCC Allows Reads and Writes to Coexist

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. Depending on its snapshot, one transaction reads the row version valid for its view while another transaction creates a newer version.

MVCC boosts concurrency, yet by itself cannot prove that **multi-row read-then-write** decisions remain serializable.

### 3.2. SSI Detects Dangerous Dependencies

SSI tracks read–write relationships among transactions. A dangerous cycle looks like:

```text
Transaction A reads dataset X
                \
                 \   Transaction B writes data that A relied on
                  \
Transaction B reads dataset Y
                \
                 \   Transaction A writes data that B relied on
                  \
      Both decisions cannot hold together
      in any serial execution order
```

SSI detects **dependency patterns that could cause anomalies** without necessarily blocking every read with locks. PostgreSQL uses predicate/`SIReadLock` tracking to record read dependencies when needed.

### 3.3. SIREAD Locks Differ from FOR UPDATE

Lock entries visible in `pg_locks` with mode `SIReadLock`:

- Serve SSI **dependency tracking**.
- Must not be confused with ordinary row locks forcing writers to wait like `SELECT FOR UPDATE`.
- Granularity (tuple, page, or relation) depends on query plans, memory limits, and internal lock management.
- Memory settings or query plans can influence conflict detection rates, including valid false-positive aborts.

**SSI does not promise every transaction reads only the absolute latest data.** It promises that committed transactions form a serializable outcome. An aborted transaction may need a **newer snapshot** on retry.

### 3.4. Serialization Failure Is Not a Deadlock

A deadlock occurs when two or more transactions **wait on each other's locks** and cannot progress. An SSI serialization failure is a **correctness-preservation mechanism** that can happen even without lock-wait cycles.

The two conditions have distinct SQLSTATEs:

```text
40001  serialization_failure
40P01  deadlock_detected
```

Both can often **be candidates for full-transaction retries**, though their root causes and contention-reduction strategies differ.

---

## 4. Creating Lab Data for Doctor On-Call Schedules

Let's build a small schema strictly for testing two concurrent transactions.

### 4.1. Creating the Table

```sql
CREATE SCHEMA IF NOT EXISTS tx_retry_lab;

CREATE TABLE tx_retry_lab.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_duty BOOLEAN NOT NULL
);
```

Insert two doctors:

```sql
INSERT INTO tx_retry_lab.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE)
ON CONFLICT (doctor_id) DO UPDATE
SET doctor_name = EXCLUDED.doctor_name,
    on_duty = EXCLUDED.on_duty;
```

`ON CONFLICT` here merely lets you re-run the seed script cleanly if the table already exists; it **does not** replace serialization and retry handling in transactions.

### 4.2. Verifying Initial State

```sql
SELECT doctor_id, doctor_name, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS on_duty_count
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Expected result:

```text
doctor_id | doctor_name | on_duty
----------+-------------+--------
1         | An          | true
2         | Bình        | true

on_duty_count = 2
```

### 4.3. Business Rule

An on-duty doctor may switch to **off-duty** only when **at least two doctors are on duty before the switch**, leaving at least one doctor remaining afterward.

High-level application logic:

```text
begin transaction
read number of on-duty doctors
if number < 2:
    do not update; finish transaction
else:
    update chosen doctor to off-duty
commit transaction
```

`CHECK (on_duty IN (true,false))` cannot enforce rules **across the whole row set**. This invariant requires multi-row coordination.

### 4.4. Preparing Two Independent psql Sessions

Open **two PostgreSQL connection windows** to the same database:

```text
Terminal A / Session A     Terminal B / Session B
----------------------     ----------------------
psql database_lab          psql database_lab
```

Substitute your lab database name for `database_lab`. Both sessions must truly be **two separate connections**; running blocks sequentially in one session produces no concurrency conflict.

Never run data-reset commands while either session still holds an active test transaction.

---

## 5. Testing Write Skew Under REPEATABLE READ

This section shows **why a stable snapshot alone is insufficient to protect multi-row rules**.

### 5.1. Reset Before the Test

From another session or while neither A nor B is inside a transaction:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE;
```

Then execute the steps **in exact interleaved order**.

### 5.2. Session A: Start and Read

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Session A sees `count_before = 2`. **Do not UPDATE or COMMIT yet.**

### 5.3. Session B: Start and Read the Same State

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Session B also sees `count_before = 2`. Both transactions pinned their snapshots before either committed a change.

### 5.4. Session A: Take An Off Duty

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1
  AND on_duty = TRUE;
```

One row updated, yet Transaction A **has not committed**.

### 5.5. Session B: Take Bình Off Duty

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

A different row updated. Because A and B modify **different `doctor_id`s**, there is no direct same-row write conflict here.

### 5.6. Session A and Session B COMMIT Sequentially

Session A:

```sql
COMMIT;
```

Session B:

```sql
COMMIT;
```

Under this `REPEATABLE READ` schedule, both transactions commit successfully because they edited disjoint rows. Inspect from a new transaction:

```sql
SELECT doctor_id, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Result:

```text
doctor_id | on_duty
----------+--------
1         | false
2         | false

remaining = 0
```

**The business rule was violated**: both doctors went off duty, even though each read two doctors on duty.

### 5.7. Why Isn't This Any Valid Serial Order?

If A ran **completely before B started**:

1. A sees 2 doctors, takes An off duty.
2. B sees only 1 doctor, **refuses** to take Bình off duty.

If B ran completely before A, the symmetric outcome occurs. No valid serial order allows **both** to pass the check and leave. `remaining=0` is a write-skew anomaly.

**Conclusion:** `REPEATABLE READ` does not automatically protect multi-row invariants checked via `SELECT COUNT(*)`.

---

## 6. Repeating the Same Experiment Under SERIALIZABLE

### 6.1. Reset Data and Close Prior Transactions

Ensure Sessions A and B ended previous transactions via `COMMIT`/`ROLLBACK`. Reset:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE;
```

### 6.2. Session A: Open SERIALIZABLE Transaction and Count

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Result `2`. **Keep Session A uncommitted.**

### 6.3. Session B: Open SERIALIZABLE Transaction and Count

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Result `2`. Both transactions read the shared rule before writing.

### 6.4. Sessions A and B Update Different Rows

Session A:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1
  AND on_duty = TRUE;
```

Session B:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

Then attempt `COMMIT` in each session:

```sql
COMMIT;
```

### 6.5. Observable Outcome

Under `SERIALIZABLE`, PostgreSQL **refuses to let both transactions commit** leaving zero doctors on duty.

Normally one transaction succeeds and the other receives:

```text
ERROR: could not serialize access due to
       read/write dependencies among transactions
SQLSTATE: 40001
```

**Do not predict in advance whether A or B will fail.** Nor assume errors happen only at `COMMIT`: depending on interleaving and conflict type, `40001` can trigger during statement execution or at commit time.

In `psql`, message wording can vary by version and locale; **`SQLSTATE 40001` is the signal programs should check**, not a hardcoded English phrase.

### 6.6. Why Must You Retry Everything?

Suppose A committed and B was rejected. B cannot reuse **2** from the old snapshot and just replay:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
```

Doing so outside the aborted transaction lets the last doctor leave **without re-checking the rule**, re-introducing the exact bug SSI prevented.

The right action is starting a **brand-new transaction B**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_now
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Now, if A took An off duty, B sees **`count_now = 1`**, decides **not to update Bình**, and runs:

```sql
COMMIT;
```

One doctor remains on duty.

### 6.7. ROLLBACK After Error

When a statement inside a transaction errors with `40001`, the transaction enters an unusable failed state. Run `ROLLBACK` before starting a new transaction. Even if the error happens **at `COMMIT`**, the failed transaction did not commit; the client must clean up state and open a fresh transaction instead of reusing logic from the failed attempt.

In applications, perform rollback safely, close/return the connection, and retry at a clean **transaction boundary**.

---

## 7. SQLSTATE 40001: Detecting Errors by Code, Not Message Text

PostgreSQL sends a five-character **SQLSTATE** identifying the error class. `40001` is **`serialization_failure`**.

### 7.1. Two Common Messages

Examples across contexts:

```text
ERROR: could not serialize access due to concurrent update
```

```text
ERROR: could not serialize access due to read/write dependencies
       among transactions
```

The exact same `40001` code can carry **different messages, details, and hints**. Never write Java like:

```java
// Avoid this:
// if (e.getMessage().contains("could not serialize")) { ... }
```

Message wording can change across versions or locales. Instead:

```java
if ("40001".equals(e.getSQLState())) {
    // Retry the entire transaction per policy.
}
```

### 7.2. Inspecting SQLSTATE in psql

In interactive `psql`, after an error:

```text
\errverbose
```

This `psql` meta-command displays full details of the most recent error, including SQLSTATE. To always show verbose fields, set `VERBOSITY verbose` in your `psql` session.

**Note:** `\errverbose` is a `psql` client command, not SQL to send over JDBC.

### 7.3. When a Transaction Is Already Aborted: SQLSTATE 25P02

Suppose a statement failed yet the app keeps sending commands inside the same transaction:

```text
ERROR: current transaction is aborted,
       commands ignored until end of transaction block
SQLSTATE: 25P02
```

Error `25P02` means **the current transaction has already failed**, not the root cause. Find the SQLSTATE **of the first error** prior to it, run `ROLLBACK`, and decide whether a full retry applies.

### 7.4. Never Treat Every Error as a Serialization Failure

| SQLSTATE | Common Name | Handling Direction |
|---|---|---|
| **`40001`** | `serialization_failure` | Retry the **entire transaction** |
| **`40P01`** | `deadlock_detected` | Also typically retry the entire transaction with backoff |
| `23505` | `unique_violation` | Check key correctness/idempotency; **do not blindly retry** |
| `23P01` | `exclusion_violation` | Inspect business conflict, e.g., overlapping schedules; do not retry by default |
| `23503` | `foreign_key_violation` | Inspect data relationships; do not retry by default |
| `55P03` | `lock_not_available` | Decide per `lock_timeout`/`NOWAIT` policy and operation needs |
| `57014` | `query_canceled` | Timeout or explicit cancel; diagnose cause |
| `25P02` | `in_failed_sql_transaction` | Rollback; locate root error first |
| `08xxx` class | Connection errors | Transaction outcome—especially after sending COMMIT—may be unknown |

**Only enable automatic retries for an explicit allowlist**, such as `40001` and possibly `40P01`. Edge cases of `23505`/`23P01` can sometimes stem from snapshot-based uniqueness checks under `SERIALIZABLE`, yet retrying them is valid only when tied to transient algorithmic key generation while still enforcing constraints properly. Never "catch every `SQLException` and retry."

---

## 8. Golden Rule: Retry the *Entire* Transaction

### 8.1. The Transaction Boundary Must Encompass the Decision

Wrong:

```text
SELECT COUNT(*) -> sees 2

BEGIN
  UPDATE doctor 2 -> error 40001
ROLLBACK

BEGIN
  UPDATE doctor 2 -> retries only the UPDATE
COMMIT
```

On the retry, the application never re-checked "at least one doctor remains on duty." That is a logic bug even if the new SQL runs without hitting `40001`.

Right:

```text
attempt 1:
    BEGIN SERIALIZABLE
    SELECT COUNT(*)              <-- read
    check condition              <-- decide
    UPDATE                       <-- write
    COMMIT                       <-- can raise 40001

if 40001:
    ROLLBACK / clean up transaction
    backoff

attempt 2:
    BEGIN NEW SERIALIZABLE
    SELECT COUNT(*) AGAIN        <-- fresh snapshot
    recompute decision
    UPDATE if still valid
    COMMIT
```

The unit to retry is the **business transaction**, not a single trailing SQL statement.

### 8.2. Which Steps Must Be Re-Executed?

Normally:

1. Start a fresh transaction and set the proper isolation level.
2. Re-read all data governing the transaction's outcome.
3. Re-evaluate all business conditions.
4. Derive row values/changes from the fresh data.
5. Execute all writes inside that transaction scope.
6. Run `COMMIT` and consider the work complete only after commit succeeds.

If decisions depend on **external configuration** or **another service's state**, establish an explicit consistency contract for those sources: PostgreSQL cannot enforce distributed serializability across external systems via DB isolation alone.

### 8.3. Why Does a Retry Often Produce a *Different* Outcome?

That is completely normal. In the doctor lab:

```text
Attempt 1 by B:
  Counted 2 -> tried to take Bình off duty -> 40001

Attempt 2 by B:
  Counted 1 -> refused taking Bình off duty -> COMMIT succeeded
```

The purpose of retrying is **not** forcing the stale answer to succeed, but **re-evaluating business logic against current reality**. A retry can validly finish with "no update made," "out of stock," or "insufficient quota."

### 8.4. SAVEPOINT Does Not Replace a New Transaction

PostgreSQL supports `SAVEPOINT` and `ROLLBACK TO SAVEPOINT`, yet that does not create a fresh outer transaction with a new snapshot to reset all SSI dependencies.

When a serialization failure tells you the transaction **cannot commit safely as executed**, never roll back one statement/branch and keep using prior reads. And once `COMMIT` fails, there is no option to "revert to a savepoint and continue" inside the rejected transaction.

**Standard strategy:** restart the entire transaction at the application boundary.

### 8.5. Every Retry Attempt Is a Fresh Transaction

Never do:

```sql
-- Wrong after a serialization failure:
-- UPDATE ...
-- UPDATE ... (retrying inside an already aborted transaction)
```

With connection pools, treat each attempt as an independent transaction ensuring zero connection state leaks from prior attempts (autocommit, isolation, session GUCs, temp objects, advisory locks, etc.).

---

## 9. Bounded Retry Loop with Backoff

Production applications need a well-defined policy instead of `while(true)`:

```text
                  +-----------------------+
                  |  Start new attempt    |
                  +-----------+-----------+
                              |
                              v
                  BEGIN SERIALIZABLE
                              |
                              v
                  Read + check business rules
                              |
                              v
                         Write data
                              |
                              v
                           COMMIT
                              |
                 +------------+-------------+
                 |                          |
             Succeeded                 SQLSTATE error
                 |                          |
                 v                          v
            Return result             ROLLBACK / cleanup
                                            |
                                +-----------+------------+
                                |                        |
                     40001 (or 40P01)               Other error
                                |                        |
                        Attempts left?              Report error
                             /     \
                           Yes      No
                           |         |
                     backoff+jitter   Report retries exhausted
                           |
                           +------> next attempt
```

### 9.1. Why Shouldn't You Retry Immediately Without Limits?

If hundreds of clients contend on the same resource and all retry instantly:

- They collide repeatedly.
- CPU, lock/WAL overhead, and connections spike.
- Latency worsens for transactions that otherwise could commit.
- A **retry storm** amplifies the overload.

Backoff slows retry frequency, while **jitter** (randomized delay) prevents clients from retrying in lockstep at the exact same instant.

### 9.2. Exponential Backoff with Jitter

Illustrative policy:

```text
maxAttempts = 5
baseDelay   = 25 ms
maxDelay    = 400 ms

After attempt 1 fails -> sleep random 0..25 ms
After attempt 2 fails -> sleep random 0..50 ms
After attempt 3 fails -> sleep random 0..100 ms
After attempt 4 fails -> sleep random 0..200 ms
After attempt 5 fails -> stop retrying
```

These numbers are **examples only**. Tune to your SLA, API latency budget, contention rate, transaction cost, and client timeouts. Never promise "5 tries always succeed."

### 9.3. Never Hold a Connection While Backing Off

When using a connection pool:

1. Roll back the failed attempt.
2. Close/return the connection to the pool per policy.
3. Sleep for backoff **outside the transaction and without holding a connection**.
4. Borrow a connection for the next attempt.

Sleeping while holding an open connection, transaction, or locks wastes resources needlessly.

### 9.4. Enforce an Overall Time Budget

Beyond `maxAttempts`, enforce the caller's overall HTTP/job **deadline**. If only 50 ms remain before client timeout and one attempt takes 500 ms, another retry is futile.

When the deadline expires, fail cleanly or hand off to an idempotent background job by design. Never loop unboundedly on a request thread.

### 9.5. Never Retry Normal Business Rejections

After a retry, a transaction may read:

```text
remaining_on_duty = 1
```

The application should return "last doctor cannot leave" as a **valid business outcome**, not treat it as `40001` and keep retrying until an UPDATE succeeds.

---

## 10. Manual SQL Pattern for a Correct Retry

When practicing in `psql`, suppose Session B hits `40001` on a statement or `COMMIT`. Recovery starts with:

```sql
-- If the old transaction is still in failed state:
ROLLBACK;

-- New attempt:
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM tx_retry_lab.on_call
WHERE on_duty;

-- Operator/app decides based on the NEW on_duty_count.
--
-- Execute only if >= 2:
-- UPDATE tx_retry_lab.on_call
-- SET on_duty = FALSE
-- WHERE doctor_id = 2
--   AND on_duty = TRUE;

COMMIT;
```

Never run an unchecked `UPDATE` thinking "the previous attempt already checked." Every snapshot-dependent decision must be re-evaluated.

### 10.1. Single-Statement SQL Does Not Eliminate All Serialization Failures

You can fold the predicate into one `UPDATE`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

UPDATE tx_retry_lab.on_call AS target
SET on_duty = FALSE
WHERE target.doctor_id = 1
  AND target.on_duty = TRUE
  AND (
      SELECT COUNT(*)
      FROM tx_retry_lab.on_call
      WHERE on_duty
  ) >= 2
RETURNING target.doctor_id;

COMMIT;
```

The aggregate subquery still depends on snapshots and read–write relationships. Under `SERIALIZABLE`, `40001` can still occur, requiring retrying the whole statement in a new transaction. Putting the rule in SQL avoids splitting decision logic away from the write, though it **does not mean conflicts can never happen**.

### 10.2. UPDATE 0 Is Not SQLSTATE 40001

If `UPDATE ... RETURNING` returns zero rows because the condition no longer holds, that is a **business result**, not a serialization failure.

```text
UPDATE 0
```

may mean the doctor already went off duty or the condition failed. Distinguish **statement succeeded with 0 matching rows** from **transaction aborted by concurrency conflict**.

---

## 11. Java/JDBC Example: Retrying the Full Transaction with a Fresh Connection

In Java, place the retry loop **outside all reads and writes**. Each attempt acquires a fresh connection/transaction, sets isolation, counts on-duty doctors, validates the rule, updates, and commits. On `40001`, roll back, close the connection, back off, and restart.

The example below uses Java 17+, JDBC, and `javax.sql.DataSource`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class DoctorScheduleService {
    private static final int MAX_ATTEMPTS = 5;
    private final DataSource dataSource;

    public DoctorScheduleService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    /**
     * true:  doctor was switched to off-duty.
     * false: unchanged because business rule no longer permits it.
     *
     * Retries the entire transaction on SQLSTATE 40001.
     */
    public boolean takeOffDuty(int doctorId)
            throws SQLException, InterruptedException {

        for (int attempt = 1;
             attempt <= MAX_ATTEMPTS;
             attempt++) {

            // Each attempt uses a fresh connection and transaction.
            try (Connection conn = dataSource.getConnection()) {
                conn.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );
                conn.setAutoCommit(false);

                try {
                    long onDutyCount = countOnDuty(conn);

                    // Business condition is RE-READ on every attempt.
                    if (onDutyCount <= 1) {
                        conn.commit();
                        return false;
                    }

                    int updated =
                        markOffDuty(conn, doctorId);

                    // 40001 can still occur inside commit().
                    conn.commit();
                    return updated == 1;

                } catch (SQLException error) {
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }

                    boolean isSerializationFailure =
                        "40001".equals(error.getSQLState());

                    if (!isSerializationFailure
                            || attempt == MAX_ATTEMPTS) {
                        throw error;
                    }
                    // Error handled for this attempt.
                    // Exiting try-with-resources closes/returns connection.
                }
            }

            // Never sleep while holding a transaction or connection.
            backoff(attempt);
        }

        // Unreachable because final attempt always returns or throws.
        throw new IllegalStateException(
            "Unexpected retry loop termination"
        );
    }

    private long countOnDuty(Connection conn)
            throws SQLException {
        String sql = """
            SELECT COUNT(*) AS on_duty_count
            FROM tx_retry_lab.on_call
            WHERE on_duty = TRUE
            """;

        try (PreparedStatement statement =
                 conn.prepareStatement(sql);
             ResultSet rs = statement.executeQuery()) {
            rs.next();
            return rs.getLong("on_duty_count");
        }
    }

    private int markOffDuty(
            Connection conn, int doctorId
    ) throws SQLException {
        String sql = """
            UPDATE tx_retry_lab.on_call
            SET on_duty = FALSE
            WHERE doctor_id = ?
              AND on_duty = TRUE
            """;

        try (PreparedStatement statement =
                 conn.prepareStatement(sql)) {
            statement.setInt(1, doctorId);
            return statement.executeUpdate();
        }
    }

    private static void backoff(int failedAttempt)
            throws InterruptedException {
        // Illustrative bounds: 25ms, 50ms, 100ms, 200ms.
        long ceiling = Math.min(
            400L,
            25L << (failedAttempt - 1)
        );
        long millis = ThreadLocalRandom
            .current()
            .nextLong(ceiling + 1);

        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
```

### 11.1. Why Does This Code Have the Right Retry Boundary?

Checklist:

| Component | Behavior |
|---|---|
| Outer `for` loop | Represents one **complete transaction attempt** |
| `dataSource.getConnection()` | Borrows connection for the current attempt |
| `setTransactionIsolation(SERIALIZABLE)` | Sets isolation level before business SQL |
| `setAutoCommit(false)` | Starts explicit transaction control |
| `countOnDuty(conn)` | **Re-read** inside every attempt |
| `markOffDuty(conn, doctorId)` | Writes only after fresh check passes |
| `conn.commit()` | Can throw `40001` and is covered inside the attempt |
| `conn.rollback()` | Aborts failed attempt cleanly |
| `getSQLState()` check | Retries only targeted error codes |
| `attempt == MAX_ATTEMPTS` | Stops retrying and propagates error |
| `backoff` outside try-with-resources | Never holds connection while sleeping |

Key rule: **never move `countOnDuty` outside the retry loop**. Reading once before the `for` loop causes every retry attempt to reuse a stale decision despite having a fresh snapshot.

### 11.2. Why Still Check `updated == 1`?

A doctor might already be `off-duty`. Then `UPDATE ... WHERE on_duty = TRUE` returns **0 rows**, a valid state. This simple example returns `false`. Production APIs can distinguish **"doctor not found," "already off-duty,"** and **"cannot leave as last doctor"** using reads **inside the transaction** if needed.

### 11.3. Limitations of This JDBC Sample

This example teaches transaction boundaries, not a full production retry library:

- No overall request deadline.
- Does not yet retry `40P01` (add per policy).
- No retry count metrics or distributed tracing.
- Each attempt borrows a connection; in real pools, ensure isolation/autocommit/session state resets cleanly before reuse.
- Does not handle external non-DB side effects.
- If `COMMIT` fails with a **dropped connection and unknown outcome**, never assume rollback as cleanly as `40001`.
- Inside a managed transaction framework, never call `commit`/`rollback` directly on a framework-owned connection.

### 11.4. Place Retries at the Proper Transaction Layer

Never put retry logic inside a single-SQL DAO when the business transaction spans multiple operations:

```text
Service:
   query account + query quota + update orders + update inventory
                                                ^
                                                |
                    Retrying only this update is WRONG.
```

Retries must sit at the **layer wrapping all operations** that collectively form the business decision.

---

## 12. Transaction Frameworks: Retries Only Work When Opening a Fresh Transaction

In Spring or similar frameworks, placing retry and transaction annotations near each other does not automatically guarantee the retry boundary is right.

### 12.1. Recommended Structure

```text
Request/API
    |
    v
RetryCoordinator                 <-- outer attempt loop
    |
    +-- attempt 1 --> TransactionalBusinessService
    |                    BEGIN SERIALIZABLE
    |                    SELECT + compute + UPDATE + COMMIT
    |                    40001 error -> transaction rolls back
    |
    +-- backoff
    |
    +-- attempt 2 --> TransactionalBusinessService
                         BEGIN NEW SERIALIZABLE
                         SELECT + recompute + UPDATE + COMMIT
```

Crucially, **every retry must enter a brand-new transaction**. If the retry runs **inside** an already open outer transaction, the second attempt reuses the stale snapshot/broken transaction.

### 12.2. Proxy and Self-Invocation Issues

In proxy/AOP frameworks, calling a `@Transactional` method from **another method on the same instance** can bypass the proxy, causing transaction annotations not to fire as expected.

When designing a retry coordinator, ensure calls into the transactional service cross the framework boundary properly, or use programmatic transactions such as a properly configured `TransactionTemplate`.

### 12.3. Avoid "Retrying Inside a Transaction"

Avoid:

```text
@Transactional                    <-- opens one transaction
method() {
    retryLoop {
        SELECT ...
        UPDATE ...
        // 40001 broke the transaction,
        // yet retryLoop stays inside the dead transaction!
    }
}
```

Prefer:

```text
retryLoop {
    @Transactional service.call() <-- each call opens a new transaction
}
```

Annotation names here are illustrative, not standalone compilable code. In Spring, also check advice ordering, rollback rules, exception translation, and propagation.

### 12.4. Exception Translation

Frameworks often wrap `SQLException` in framework exceptions. Therefore:

- Identify which framework exception maps to `40001`.
- Ensure retry wrappers preserve SQLSTATE/root causes for inspection.
- Confirm the transaction rolled back **before** retrying.
- Never retry disallowed business errors.

For example, Spring maps serialization, optimistic, and pessimistic concurrency errors to its own exception hierarchy; base retry matching on the framework and driver contract rather than assuming `e instanceof SQLException` when exceptions are wrapped.

---

## 13. Deadlock 40P01 vs. Serialization Failure 40001

### 13.1. Deadlock Example from Opposite Lock Ordering

Suppose two accounts A and B exist. Transaction T1 updates A then B; T2 updates B then A:

```text
T1 holds lock on row A          T2 holds lock on row B
T1 waits for row B              T2 waits for row A
             \                /
                  DEADLOCK
```

PostgreSQL detects the cycle and aborts one transaction with SQLSTATE **`40P01`**. That transaction must roll back and, if appropriate, retry its full logic.

### 13.2. Reducing Deadlocks

- Update multiple resources in a **consistent lock order**, e.g., ascending `account_id`.
- Keep transactions short; never make network calls while holding row locks.
- Index key lookup/lock predicates to avoid unnecessary wide scans.
- Avoid acquiring locks and then requesting additional resources in inconsistent orders across code paths.
- Catch and retry `40P01` at the **transaction boundary**, not just the deadlocked statement.

### 13.3. How Does 40001 Differ?

`40001` can happen **even with zero lock-wait cycles**. In write skew, two transactions modify **disjoint rows** while reading predicates overlapping each other's writes; SSI aborts one to preserve serializability.

**In short:** both can be transient contention failures, yet:

- `40P01`: PostgreSQL detected a **deadlock**.
- `40001`: PostgreSQL cannot let the transaction commit while preserving **serialization**.

Applications can share retry infrastructure while keeping error classification distinct for diagnostics and tuning.

---

## 14. UNIQUE, ON CONFLICT, and Errors Not to Retry Blindly

### 14.1. Not Every Concurrent Conflict Is 40001

If two requests insert the same order code under a unique constraint, one receives:

```text
SQLSTATE 23505 — unique_violation
```

This normally means **the key already exists** and the app should handle it per business rules: return "already exists," honor an idempotency key, or use `ON CONFLICT`.

### 14.2. ON CONFLICT Does Not Replace SERIALIZABLE

```sql
INSERT INTO some_table(id, value)
VALUES (10, 'demo')
ON CONFLICT (id) DO NOTHING;
```

This resolves **unique conflicts on that specific INSERT** declaratively. It does not automatically make multi-row read–write rules across the transaction serializable.

Inside a multi-statement SERIALIZABLE transaction, `40001` can still happen even if an `INSERT ... ON CONFLICT` resolved one unique collision.

### 14.3. Special Case of Unique Violation Under SERIALIZABLE

PostgreSQL documentation notes that certain unique constraint violations can stem from concurrency races that behave like serialization conflicts—for example, two transactions **reading to check keys, generating a new key, and inserting concurrently**. In specific algorithms, an application may retry the whole transaction even on `23505`.

However:

- That does **not** make every `23505` retryable.
- Distinguish user-supplied keys that genuinely collided from algorithmically generated keys that change on a fresh attempt.
- Keep database constraints to protect invariants even if pre-checks race.
- For idempotency, the **correct** response is often returning the prior request's stored result rather than inserting another row.

**Safe default policy:** auto-retry `40001`; add other SQLSTATEs only with explicit design analysis.

### 14.4. Optimistic Concurrency Differs from 40001

Version-checked update pattern:

```sql
UPDATE accounts
SET balance = balance - 100,
    version = version + 1
WHERE account_id = 5
  AND version = 12
  AND balance >= 100;
```

If `UPDATE 0`, either the version changed or funds were insufficient. Do not label that a serialization failure. Re-read and distinguish business conflicts per your optimistic-locking contract.

---

## 15. Retries and Side Effects Outside the Database

This is where many systems handle `40001` right in SQL yet **break business correctness**.

### 15.1. Sending Emails or Charging Cards Mid-Transaction

Suppose:

```text
BEGIN SERIALIZABLE
  UPDATE orders
  CALL payment gateway: charge 500,000 VND
  COMMIT -> 40001
ROLLBACK
RETRY
  UPDATE orders
  CALL payment gateway: charge 500,000 VND again
  COMMIT
```

PostgreSQL rolls back **database changes**, yet **cannot roll back the charge at the payment gateway**. Mechanically retrying the whole method double-charges the customer.

Same risk applies to:

- Sending email/SMS.
- Calling side-effecting HTTP APIs.
- Writing files or pushing events to non-transactional queues.
- Triggering physical devices.
- Transfers, shipping labels, or account activations in external systems.

### 15.2. Classifying Steps by Retryability

| Work Type | Examples | Design Approach |
|---|---|---|
| Reads and writes in the **same PostgreSQL transaction** | SELECT, UPDATE, INSERT, DELETE | Retry entire transaction |
| Pure computation without side effects | Computing limits from read rows | Recompute on each attempt |
| Calling external state-changing services | Payments, email, write APIs | Use idempotency / outbox / orchestration |
| Generating random IDs or timestamps | Request ID, batch time | Decide explicitly whether to keep stable or regenerate |
| Generating business sequence numbers | Invoice numbers, document IDs | Needs dedicated numbering and non-reuse rules |

### 15.3. Moving Side Effects After COMMIT

A simple pattern:

```text
BEGIN
  SELECT ...
  UPDATE ...
COMMIT succeeds

AFTERWARD:
  send email / notification
```

This prevents sending emails during an attempt that rolls back. However, it leaves a **reliability gap**: if the process crashes right after commit before sending the email, the email is lost.

### 15.4. Transactional Outbox

A common way to close that gap:

```text
Inside the same PostgreSQL transaction:
  1. Read + update business data
  2. INSERT a row into the outbox table
  3. COMMIT

After commit:
  Worker reads outbox
  Dispatches event / email / API call
  Marks published status
```

If the transaction hits `40001` and rolls back, **neither business data nor the outbox row** commits. The retry creates a fresh outbox row matching the recomputed business decision.

### 15.5. Sample Outbox Schema

```sql
CREATE TABLE tx_retry_lab.outbox_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
```

A transaction inserts an event:

```sql
-- Inside a transaction applying business updates:
-- INSERT INTO tx_retry_lab.outbox_events
--     (event_id, event_type, payload)
-- VALUES (
--     :stable_event_id,
--     'DoctorWentOffDuty',
--     jsonb_build_object('doctorId', :doctor_id)
-- );
```

`:stable_event_id` and `:doctor_id` are **illustrative client bind parameters**, not literal `psql` syntax.

A worker processes events after commit. The worker must handle **redelivery**, since it may publish successfully and crash before updating `published_at`. Consumers should be idempotent/deduplicate by `event_id`.

**An outbox does not automatically yield end-to-end exactly-once delivery.** It atomically links business writes to intent-to-publish records; delivery still needs retries and deduplication.

---

## 16. Idempotency: Retries Must Never Duplicate Results

### 16.1. Transaction Retries and Request Retries Are Different Layers

**Transaction retry:** the app knows PostgreSQL rejected an attempt with `40001`; the transaction never committed. Starting a fresh business transaction is safe.

**Request retry:** the client resends an HTTP request due to timeout, proxy retry, or double-click. The earlier request **may have already committed**, even though the client never saw the response.

Both need related—yet distinct—handling.

### 16.2. Stable Idempotency Key per Business Request

Suppose an order-creation API accepts:

```text
POST /orders
Idempotency-Key: 8e9c...stable-request-key
```

The server stores a `request_id` with a unique constraint alongside the outcome or created resource ID. On a repeated key, the server checks whether **that exact request** already completed rather than creating a second order.

```sql
CREATE TABLE tx_retry_lab.request_results (
    request_id UUID PRIMARY KEY,
    resource_id BIGINT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

In production, `request_id` is typically scoped per **tenant** with a payload fingerprint/hash to reject mismatched payloads on the same key. A minimal table with only `request_id` and `resource_id` illustrates uniqueness, **not a complete idempotency architecture**.

### 16.3. Where Should Keys Be Generated?

When clients send an idempotency key, keep the **same key** across all retries. Never mint a new key per attempt: if the first request committed and its response was lost, a new key fails to prevent duplicates.

For an outbox event representing one business state change, assign a stable event ID per operation or equivalent deduplication key. Distinguish **retrying the same operation** from **starting a brand-new operation**.

### 16.4. Unknown COMMIT Outcome on Network Failure

Special failure mode:

```text
Application sends COMMIT
    |
Network connection drops before response arrives
    |
Transaction may have COMMITTED or NOT COMMITTED
    |
Application DOES NOT KNOW the final outcome
```

Never assume "no response = rolled back" and re-run a non-idempotent payment or order **without idempotency**.

This **is not like `40001`** returned explicitly by PostgreSQL: with `40001`, you know the transaction aborted; with a connection drop at commit, you face an **unknown outcome**.

Handling typically requires:

- Persistent idempotency keys / operation IDs.
- Reconciliation queries after reconnecting.
- Retrying only through logic capable of detecting **already processed** operations.
- Never executing non-idempotent external side effects twice.

Do not lump `08xxx` connection errors into the same "guaranteed safe to retry" bucket as `40001`.

---

## 17. Distinguishing Retryable vs. Non-Retryable Failures in Practice

### 17.1. Serialization Failure 40001

**Cause:** PostgreSQL could not commit the transaction safely under its isolation level.

**Action:** roll back the failed transaction, retry the entire business transaction with a fresh snapshot, bounded by attempt limits.

### 17.2. Deadlock 40P01

**Cause:** cyclic lock-wait dependency.

**Action:** roll back and optionally retry the entire transaction; also audit lock ordering and access patterns.

### 17.3. Unique Violation 23505

**Cause:** key violated uniqueness.

**Action:** usually a business error or idempotency conflict; handle per business rules. Retry selectively only for well-understood algorithmic key-generation races.

### 17.4. Exclusion Violation 23P01

**Cause:** e.g., an appointment overlaps an existing booking under an exclusion constraint.

**Action:** usually inform the caller the slot is taken and ask for another slot. Retrying the exact same slot **will not resolve** the conflict while the existing booking remains.

### 17.5. Statement Timeout 57014

**Cause:** statement canceled, via `statement_timeout` or explicit cancel.

**Action:** roll back the failed transaction, investigate runtime, query plans, resources, and deadlines; retry only if time budget and cause warrant it. Never relabel as `40001`.

### 17.6. Insufficient Balance or Precondition No Longer Met

**Cause:** business logic on retry observes updated reality.

**Action:** return a clean business outcome like "insufficient quota" or "last doctor cannot leave," rather than treating it as a DB error or looping until an update succeeds.

---

## 18. Reducing Serialization Failures Through Transaction Design

Retries are mandatory under `SERIALIZABLE` contention, yet **reducing unnecessary conflicts** matters just as much.

### 18.1. Keep Transactions Short

Avoid:

```text
BEGIN SERIALIZABLE
SELECT ...
wait 30 seconds for user confirmation
call external API for 10 seconds
UPDATE ...
COMMIT
```

Long transactions hold snapshots and conflict metadata longer, raising abort rates, lock contention, and operational strain.

Gather user input and external data **before** opening the transaction, then execute only the consistent database reads/writes inside a tight transaction.

### 18.2. Optimize Decision-Making Read Queries

SSI tracks read regions. Queries scanning huge ranges due to missing indexes or filters create broader dependency footprints. For example:

```sql
SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;
```

In our two-row lab, that is trivial. In production, filtering by `tenant_id`, `shift_id`, or department narrows touched rows whenever business rules scope to that unit.

Never narrow a query just to cut conflicts if doing so breaks the business rule. **Correct read scope comes first, optimization second.**

### 18.3. Indexes May Help

If a production on-call table includes `tenant_id` and `shift_id`:

```sql
-- Illustrative index for an expanded schema:
-- CREATE INDEX on_call_shift_idx
-- ON on_call (tenant_id, shift_id, on_duty);
```

Suitable indexes reduce query cost and overly coarse predicate locks in some cases, though there is **no guarantee indexes eliminate `40001`**. Real business contention still requires retries.

### 18.4. Avoid Touching Shared Resources Unnecessarily

- Skip no-op `UPDATE`s that write unchanged values.
- Avoid giant transactions spanning unrelated resources.
- Keep a **consistent access order** when locking multiple rows.
- Partition work by tenant, shard, or key when business logic permits to reduce hot spots.
- For counters/quotas, consider a dedicated row updated atomically rather than full-table reads, watching out for hot-row bottlenecks.

### 18.5. SELECT FOR UPDATE Is a Different Trade-Off, Not "Always Safer"

```sql
SELECT *
FROM tx_retry_lab.on_call
WHERE on_duty
FOR UPDATE;
```

Locking selected rows can serialize certain designs, with trade-offs:

- Blocks concurrent processes and can introduce deadlocks.
- Does not protect **not-yet-existing rows** or arbitrary predicates under `READ COMMITTED`.
- Can sharply reduce throughput if locking large row sets.
- Still requires evaluating snapshots, lock order, and retry needs.

Never treat `SELECT FOR UPDATE` and `SERIALIZABLE` as drop-in equivalents.

### 18.6. SERIALIZABLE Does Not Fix Missing Application Logic

If code inside a transaction runs:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
```

**without reading and enforcing** "at least one doctor remains on duty," `SERIALIZABLE` cannot guess the missing business rule. Serializable ensures committed results match some serial order of **the statements actually executed**, without inventing unstated constraints.

---

## 19. Pure Read-Only Cases: READ ONLY DEFERRABLE

Some workloads only run **long read-only reports** needing a consistent snapshot without writes.

PostgreSQL supports **`SERIALIZABLE READ ONLY DEFERRABLE`**:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT doctor_id, doctor_name, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

COMMIT;
```

In this mode, PostgreSQL may **wait for a safe snapshot** up front, allowing the long read transaction to avoid SSI serialization aborts once established.

Key facts:

- `DEFERRABLE` has this safe-snapshot effect specifically when combined with `SERIALIZABLE` and `READ ONLY`.
- It is not a magic speedup for all transactions; it may pause before reading starts.
- Never use it for transactions performing `INSERT`/`UPDATE`/`DELETE`.
- Never pick it hoping to "eliminate `40001` errors" in write workflows.

It is valuable for read-only reports or snapshot exports that can tolerate an initial wait.

---

## 20. Monitoring and Diagnosing Serialization Failures

Never log a vague `"database error"` and lose context. When `40001` spikes, distinguish **normal transient contention** from **conflict-heavy transaction design**.

### 20.1. Application-Layer Metrics to Track

| Metric | Meaning |
|---|---|
| Total transaction attempts | Execution count including retries |
| `40001` count per operation | Serialization failure rate |
| `40P01` count per operation | Deadlock rate |
| Attempts until success | Retry depth distribution |
| Retry-budget exhaustion count | Transactions failing after hitting cap |
| Per-attempt latency | Single-transaction duration |
| End-to-end latency | Total time including backoff and retries |
| Long-open transaction count | Risk of pinned snapshots/locks |
| Unknown commit outcome count | Cases requiring reconciliation/idempotency |

Attach **operation/request ID**, business action, attempt number, SQLSTATE, and timing to logs; exclude PII, passwords, payment secrets, and sensitive SQL literals.

### 20.2. Inspecting Running Transactions

Operational reference query:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Visibility into other sessions depends on monitoring roles/privileges. Never run this just to dump sensitive SQL parameters into unsecured logs.

### 20.3. Inspecting Predicate Locks in SSI Context

```sql
SELECT
    pid,
    locktype,
    mode,
    relation::regclass AS relation_name,
    page,
    tuple,
    granted
FROM pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
```

This diagnostic view **does not predict which exact transaction will hit `40001`**. Query plans, read/write timing, and internal heuristics determine actual aborts.

### 20.4. EXPLAIN Does Not Simulate Concurrent Schedules

```sql
EXPLAIN
SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;
```

`EXPLAIN` shows scan plans, indexes, and estimates, yet cannot reproduce write skew across two concurrent transactions. Testing serialization failures requires **at least two connections and interleaved schedules** as in Sections 5–6.

### 20.5. Do Not Confuse Standby Conflict Stats with Primary 40001 Counts

Statistics tracking **standby recovery conflicts** measure replica query cancellations, not per-business-transaction `40001` counts on the primary.

Tracking **SQLSTATE at the application layer** directly shows how often retries occur. Server metrics assist root-cause analysis rather than replacing attempt telemetry.

---

## 21. Designing Concurrency Tests

A sequential unit test calling a service once cannot prove retry logic works. You need **genuinely overlapping transactions**.

### 21.1. Baseline Scenario: Two Doctors

1. Reset `on_duty=true` for both doctors.
2. Open **two separate connections** to the same database.
3. Start both as `SERIALIZABLE`.
4. Ensure both read `COUNT(*)=2` before either writes.
5. Have both update **different rows**.
6. Attempt to commit both.
7. Assert that both cannot commit leaving `remaining=0`.
8. On `40001`, roll back and retry the **entire logic**.
9. After retries finish, assert **`remaining >= 1`**.

### 21.2. Essential Test Cases

| Scenario | What to Prove |
|---|---|
| No contention | Transaction succeeds without retrying |
| Write skew under `REPEATABLE READ` | Multi-row invariant can break |
| Write skew under `SERIALIZABLE` | One transaction can hit `40001` |
| Retry after `40001` | Uses fresh snapshot and recomputes decision |
| `40001` at `COMMIT` | Retry boundary catches commit-time failure |
| `40P01` from opposite lock order | Rolls back and retries if allowed |
| Retry budget exhausted | Fails cleanly without infinite loops |
| Genuine `23505` | Not blindly retried |
| Client timeout after `COMMIT` | Idempotency prevents duplicates |
| External side effect | Retries do not send payments/emails twice |
| Transaction manager / proxy | Each attempt opens a genuine new transaction |
| Connection pool | No isolation/autocommit leak across requests |

### 21.3. Synchronizing Threads in Tests

In Java integration tests, use **`CountDownLatch`** or **`CyclicBarrier`** to guarantee both transactions complete `SELECT COUNT(*)` before proceeding to `UPDATE`/`COMMIT`. That reproduces write skew deterministically instead of launching two threads and hoping for lucky timing.

Never wait infinitely on a barrier if one thread errors before reaching it; configure timeouts and clean up/roll back in `finally`.

### 21.4. Assert Final Data State Instead of Counting Exceptions Alone

A sound test verifies:

```sql
SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

After all valid commits/retries finish, **`remaining >= 1`**. Counting a `40001` exception and then running broken retry logic can still corrupt data. Business correctness is the ultimate assertion.

---

## 22. Common Design Mistakes

**1. "`40001` means the database is broken."** No. It is often a mandatory guard preserving serializable outcomes.

**2. "Only `SERIALIZABLE` raises `40001`."** No. `REPEATABLE READ` can also fail with `40001` when updating a row modified after its snapshot.

**3. "`REPEATABLE READ` protects all multi-row rules."** No. Write skew remains possible.

**4. "Retry only the failing `UPDATE` statement."** Wrong. Redo **reads, decisions, and writes** in a fresh transaction.

**5. "If commit throws `40001`, just call `COMMIT` again."** Wrong. That transaction is already rejected; open a new transaction and rerun the logic.

**6. "I can keep going after `40001` inside the same transaction."** No. Roll back and clean up first.

**7. "`SAVEPOINT` refreshes a `SERIALIZABLE` snapshot."** No. Rolling back to a savepoint does not create a new outer transaction.

**8. "Retry infinitely until it succeeds."** No. Require max attempts, backoff, jitter, and deadlines.

**9. "Every `SQLException` is retryable."** No. Constraint and business failures need distinct handling.

**10. "Detect errors by matching English message strings."** No. Match SQLSTATE or explicitly mapped exceptions.

**11. "`25P02` is the root cause of a serialization failure."** Normally it is a symptom of an earlier failed statement in the transaction.

**12. "Retrying inside an outer `@Transactional` still opens a new transaction."** Not necessarily. Verify boundaries, proxies, and propagation.

**13. "With `SERIALIZABLE`, PK/UNIQUE/FK constraints aren't needed."** Wrong. Isolation never replaces constraints.

**14. "With `SERIALIZABLE`, PostgreSQL automatically knows one doctor must stay on duty."** Wrong. The transaction must execute reads/checks expressing that rule.

**15. "200 OK from an API guarantees `COMMIT` succeeded if JDBC didn't throw."** Verify actual commit execution, exception handling, transaction manager boundaries, and connection drops.

**16. "Losing connection at `COMMIT` is just like `40001`."** No. Commit outcome is **unknown**, requiring reconciliation and idempotency.

**17. "Sending an email mid-transaction is fine if it rolls back."** Wrong. Sent emails cannot be recalled.

**18. "Transactional outboxes guarantee exactly-once everywhere."** No. Consumers still must handle at-least-once delivery and deduplication.

**19. "Every request retry should mint a new idempotency key."** Wrong. Keep the key stable for the same operation.

**20. "More retries are always better."** No. Retry storms worsen contention and latency.

**21. "`Thread.sleep` while holding a connection is harmless."** No. It ties up pool connections and can prolong locks/snapshots.

**22. "`SELECT FOR UPDATE` is a free fix for all races."** No. It introduces lock contention, deadlocks, and predicate gaps.

**23. "`UPDATE 0` should always be retried."** No. It is often a valid business outcome or optimistic concurrency conflict.

**24. "`SERIALIZABLE READ ONLY DEFERRABLE` works for write transactions."** No. It is exclusively for read-only transactions.

**25. "`EXPLAIN` on one query proves there is no write skew."** No. Run multi-connection concurrency tests and invariant assertions.

**26. "Unique error `23505` is always a serialization failure to retry."** No. Classify carefully before retrying.

**27. "Only catch `40001` around `UPDATE`, not `COMMIT`."** Wrong. `40001` frequently surfaces at commit time.

**28. "Each attempt gets a new snapshot, yet I can keep the old decision in a Java variable."** Wrong. Recompute every snapshot-dependent variable.

**29. "Short transactions don't need timeout or lock monitoring."** No. High contention still causes issues; monitor continuously.

**30. "Serialization failures prove row-level locking isn't working."** No. SSI and row locks solve different concurrency problems.

---

## 23. Hands-On Exercises with Solutions

### Exercise 1 — Identifying the Error

A JDBC exception reports:

```text
SQLSTATE=40001
Message=could not serialize access due to ...
```

**Question:** What error is this and what is the primary action?

**Answer:** `serialization_failure`. Roll back/clean up the failed transaction, open a fresh transaction, and re-run **all data-dependent logic** with bounded retries and backoff.

### Exercise 2 — Can You Replay Only the Final UPDATE?

Transaction B counts 2 doctors, tries to take Bình off duty, and hits `40001`.

**Answer:** Never replay only `UPDATE doctor_id=2`. Re-read the on-duty count inside a fresh transaction; if only 1 remains, do not update.

### Exercise 3 — Comparing REPEATABLE READ and SERIALIZABLE

**Question:** Two transactions read the same two-doctor set and update disjoint rows; what can happen under `REPEATABLE READ`?

**Answer:** **Write skew**: both can commit, leaving both doctors off duty. `SERIALIZABLE` refuses to let both commit into a non-serializable outcome.

### Exercise 4 — SQL to Set Isolation Level

**Requirement:** start a read–write transaction at `SERIALIZABLE`.

**Answer:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- SELECT, business decision, UPDATE ...

COMMIT;
```

On `40001`, roll back/clean up and restart from `BEGIN`.

### Exercise 5 — Why Must Retries Re-Read COUNT?

**Answer:** `count=2` in the failed attempt belonged to an older snapshot. After another transaction commits, `count` may be 1. Reusing the stale number produces an invalid business decision.

### Exercise 6 — Failure at COMMIT

**Question:** `UPDATE` succeeded, yet `COMMIT` throws `40001`. Can you return "updated" to the client?

**Answer:** No. The transaction was rejected and changes were not committed. Retry the entire transaction or report failure if retry budget is exhausted.

### Exercise 7 — Deadlock SQLSTATE

```text
40P01
```

**Answer:** `deadlock_detected`. Roll back and optionally retry the full transaction; also audit lock ordering and shorten lock hold times.

### Exercise 8 — Do Not Retry Every Error

**Question:** A client submits an email already violating a unique constraint and gets `23505`. Should it immediately retry 10 times?

**Answer:** No. Handle existing records or idempotency rules. Retry only for carefully analyzed race conditions where a fresh attempt can legitimately change the outcome.

### Exercise 9 — Aborted Transaction

One statement throws `40001`, and the next throws `25P02`.

**Answer:** `25P02` indicates an already failed transaction. Locate the root `40001`, execute `ROLLBACK`, and start a fresh transaction.

### Exercise 10 — Retries with Backoff

**Requirement:** give two reasons for backoff and jitter.

**Answer:** Prevents clients from colliding in lockstep on retries and avoids worsening contention/load spikes during conflicts. Pair with `maxAttempts` or a deadline to prevent infinite loops.

### Exercise 11 — Where Does the Retry Loop Belong?

```text
SELECT account_balance
SELECT promotion
UPDATE wallet
INSERT order
COMMIT
```

**Answer:** Wrap **all five steps** inside one transaction attempt, and place the retry loop outside that attempt. Never retry only `INSERT order`.

### Exercise 12 — External Payment Gateway

An app calls a payment gateway before `COMMIT`, and the transaction hits `40001`.

**Answer:** PostgreSQL cannot roll back the gateway charge. Use a gateway idempotency key or proper orchestration/compensation/outbox; avoid non-idempotent side effects inside retryable transaction bodies.

### Exercise 13 — Ambiguous COMMIT Outcome

The connection drops right after sending `COMMIT`.

**Answer:** You cannot assume the transaction rolled back. Use an operation ID/idempotency key and reconciliation query to determine whether it committed before repeating any side-effecting action.

### Exercise 14 — Why Isn't SAVEPOINT Enough?

**Answer:** A savepoint does not open a fresh outer transaction with a new snapshot and clean SSI dependencies. Serialization failures require retrying the whole transaction.

### Exercise 15 — READ ONLY DEFERRABLE

**Requirement:** write a read-only transaction willing to wait for a safe snapshot.

**Answer:**

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;

COMMIT;
```

Do not use this for transactions that perform writes.

### Exercise 16 — Detecting SQLSTATE in Java

**Requirement:** write the condition to identify a serialization failure.

**Answer:**

```java
if ("40001".equals(exception.getSQLState())) {
    // Roll back and retry the entire transaction.
}
```

Never rely on `exception.getMessage()` substrings.

### Exercise 17 — Verifying the Invariant

**Question:** after testing two doctors under SERIALIZABLE with proper retries, which query checks the invariant?

**Answer:**

```sql
SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

A valid outcome requires `remaining >= 1`. Do not stop at checking "a `40001` error occurred."

### Exercise 18 — Why Isn't UPDATE 0 Always an Error?

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

**Answer:** `UPDATE 0` can simply mean the doctor was already `off-duty`; the SQL succeeded cleanly. Business logic should interpret it per requirements rather than retrying like a serialization failure.

### Exercise 19 — When Should You Avoid Using SERIALIZABLE Mechanically?

**Answer:** For operations whose invariants are cleanly enforced by constraints or a single atomic conditional update, `READ COMMITTED` with proper predicates/locks is simpler and incurs fewer aborts. Decide by correctness and workload, not whichever level sounds "strongest."

### Exercise 20 — Designing Idempotency Keys

An order-creation request is sent three times due to timeouts.

**Answer:** Use one stable request/operation ID, store the outcome tied to that ID via a unique constraint, and reconcile on repeats. Never mint a new key per retry; also verify payload match and tenant scope.

### Exercise 21 — Predicate Reads vs. Row Locks

**Question:** does `SIReadLock` force every other `UPDATE` to wait like `FOR UPDATE`?

**Answer:** No. It tracks SSI conflicts and differs from blocking row locks. `40001` can occur even when two transactions never waited on each other because they edited disjoint rows.

### Exercise 22 — Exhausted Retries

**Requirement:** design behavior after five `40001` failures.

**Answer:** After the final attempt, roll back/clean up and return a classified failure instead of looping forever. Depending on SLA and idempotency, you may queue an async retry while guaranteeing the operation never duplicates.

### Exercise 23 — RLS and Tenant Scope

**Question:** does enabling SERIALIZABLE prevent Tenant 10's transaction from updating Tenant 20's rows?

**Answer:** No. Serializable governs schedule equivalence among committed transactions, **never authorization**. You still need tenant predicates, roles/RLS, and access controls.

### Exercise 24 — Resetting the Lab

After testing, to restore both doctors:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
```

When cleaning up the schema, run **only** in a practice database after confirming nothing else depends on it:

```sql
-- Do not run in a shared database without verifying first:
-- DROP SCHEMA tx_retry_lab CASCADE;
```

---

## 24. Pre-Production Checklist Before Enabling Retries

1. **Define transaction boundaries:** encompass all reads, decisions, updates, and `COMMIT`.
2. **Choose isolation:** match `READ COMMITTED`, `REPEATABLE READ`, or `SERIALIZABLE` to each invariant.
3. **Classify by SQLSTATE:** include `40001`, and `40P01` per policy.
4. **Never retry a single statement:** retry the entire business transaction on a fresh snapshot.
5. **Roll back and clean up:** failed attempts must never leak locks or state to the next attempt.
6. **Discard stale reads:** recompute all snapshot-dependent Java variables.
7. **Cover COMMIT failures:** catch `40001` on `commit()` as well as `UPDATE`.
8. **Bound attempts/deadlines:** define fallback behavior when retry budget runs out.
9. **Backoff + jitter:** prevent retry storms and never sleep while holding connections/transactions.
10. **Guard side effects:** never duplicate emails, charges, or write API calls across retries.
11. **Enforce idempotency:** recognize repeated operations/requests cleanly.
12. **Handle unknown commit outcomes:** connection drops are not guaranteed rollbacks.
13. **Do not retry all errors:** handle constraint violations, business rejections, and timeouts separately.
14. **Emit metrics/logs:** SQLSTATE, attempt counts, operation name, latency, exhaustion rate.
15. **Test with two connections:** reproduce write skew and verify post-retry invariants.
16. **Reduce contention:** keep transactions short, scope reads properly, add indexes, order locks consistently.
17. **Verify framework proxies:** confirm every attempt genuinely starts a new transaction.
18. **Verify pooling:** ensure isolation/autocommit/session state never leaks across reused connections.
19. **Keep authorization separate:** SERIALIZABLE never replaces roles, tenant checks, or RLS.
20. **Verify business outcomes:** retries can validly return rejections after reading updated data.

---

## 25. Summary

`serialization_failure` with **SQLSTATE `40001`** is PostgreSQL's signal that **a transaction cannot continue or commit under the observed concurrent schedule** while preserving its isolation guarantee.

Key principles:

- **`REPEATABLE READ` does not stop all write skew.** Two transactions reading one set and updating disjoint rows can still break multi-row invariants.
- **`SERIALIZABLE` uses SSI** to detect non-serializable schedules and aborts conflicting transactions with `40001`.
- **Retries must start a fresh transaction and redo all reads, decisions, and writes**, never just the final SQL statement or `COMMIT`.
- **Catch errors on both statements and COMMIT**, roll back/clean up, cap retries, and apply backoff with jitter.
- **`40P01` deadlocks** can use full-transaction retries per policy; **`23505`/`23P01`** and business rejections must not be blindly retried.
- **Side effects outside the database do not roll back with PostgreSQL.** Use idempotency, transactional outboxes, or safe orchestration.
- **Connection drops during COMMIT produce unknown outcomes**, unlike explicit `40001` rejections.
- **Multi-connection tests asserting the final invariant** are what validate retry correctness—not merely catching an exception.

**Final rule:** a serialization failure is not an invitation to "force through" a decision computed in an earlier failed attempt. It tells the application to **re-read current reality, re-evaluate the decision, and commit only if the fresh decision still holds**.

### Official PostgreSQL Documentation

- [Transaction Isolation — Serializable Isolation Level](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking and Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Error Codes — SQLSTATE 40001 and 40P01](https://www.postgresql.org/docs/current/errcodes-appendix.html).
- [BEGIN](https://www.postgresql.org/docs/current/sql-begin.html), [COMMIT](https://www.postgresql.org/docs/current/sql-commit.html), and [ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html).
- [SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
