# Conceptual Role of Logging, Locking, and MVCC

## 1. Three mechanisms solving three different concerns

A database transaction may simultaneously have to cope with **power loss/crashes**, **two users updating the same record**, and **one user reading while another is writing**. These are three related yet distinct problems:

| Mechanism | Primary question the mechanism addresses | Contribution to transactions |
| --- | --- | --- |
| **Transaction log (often tied to WAL)** | If the process dies mid-way or data in memory has not yet reached disk, how do we recover? | Foundation for crash recovery, durable commits, and recovery/undo depending on DBMS design. |
| **Locking** | When two transactions both want to modify data, who goes first? | Coordinates concurrent access, protects in-progress changes, and helps enforce isolation levels. |
| **MVCC (Multi-Version Concurrency Control)** | While data is being updated, can readers see a consistent version without waiting for every write? | Manages multiple versions to support snapshot/consistent reads and reduce read-write contention. |

Key point: **the three mechanisms are not mutually exclusive alternatives**. A DBMS like PostgreSQL or MySQL/InnoDB can use logging, locking, and data versioning *at the same time*. They are database-layer execution mechanisms. In Spring Framework, `@Transactional` primarily **defines transaction boundaries and requests commit/rollback**; Spring does not implement WAL, locking mechanisms, or MVCC itself.

To learn from concrete causes, let's use an accounts table:

~~~sql
CREATE TABLE tx_account_lab (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO tx_account_lab(id, balance) VALUES
    (1, 1000),
    (2, 500);
~~~

Suppose transaction T1 transfers 100 from account 1 to account 2: T1 must update both rows and then commit; if an error occurs, both roll back. At the same time, T2 might read or modify account 1.

### ACID viewed through the three mechanisms

- **Atomicity:** operations never leave half-committed state. Recovery, transaction state, and the engine's undo/rollback capabilities help guarantee this.
- **Consistency:** after a valid transaction, constraints/business conditions still hold. The database helps with constraints and transaction coordination, though business rules must still be designed properly.
- **Isolation:** determines how concurrent transactions are allowed to observe/affect each other. Locking, MVCC, and conflict detection are the tools used to implement it.
- **Durability:** after the DBMS confirms commit, changes are protected against crashes per its guarantees and durability configuration; WAL/redo logs are a key component.

**Do not infer a one-to-one mapping** such as "log = Atomicity, lock = Isolation, MVCC = Consistency." In practice these mechanisms collaborate, and engines implement them differently.

## 2. Transaction log: recovering from crashes

### Why not just write data pages directly?

DBMSs typically keep **data pages** in a buffer cache for fast processing. An `UPDATE` may modify a page in memory while the corresponding copy on disk is not written immediately. Forcing every statement to wait for full data-page disk writes would severely degrade performance.

The idea of **write-ahead logging (WAL)**: write the information required to **redo/recover changes** to the log under ordering rules before writing the related data pages to primary storage. When a transaction commits, the database ensures commit/redo information is sufficiently durable per configuration before reporting success to the application.

Conceptual view:

~~~text
Application: UPDATE / COMMIT
          |
          v
Database modifies data page in RAM
          |
          +--> Writes change record to log (WAL/redo)
          |       |
          |       +--> log is flushed durably per commit conditions
          |
          +--> Data page can be flushed to data file later
          |
Crash/restart --> reads recovery info --> restores valid state
~~~

This diagram is **conceptual**: ordering, log record types, undo mechanisms, and actual flush conditions differ across engines.

### Redo and undo answer two different questions

- **Redo:** a change was **committed**, yet its corresponding data page was not sufficiently written to disk—how is it recovered? The engine can replay the needed redo information.
- **Undo/rollback:** an **uncommitted or aborted** transaction made intermediate changes—how are those invalid effects removed? The engine uses old-version recovery info, transaction state, or an appropriate undo mechanism.

Do not assume *every* DBMS has two physical files named "redo.log" and "undo.log". For instance, PostgreSQL uses WAL for redo/crash recovery and manages visibility/versions for MVCC; InnoDB has a redo log alongside undo records with distinct roles. Exact recovery layout is engine-specific.

### Three points when a failure occurs

| Failure timing | Outcome to understand |
| --- | --- |
| **Before commit** | The transaction was not confirmed; upon recovery, uncommitted changes must not be exposed as valid committed data. |
| **Commit acknowledged and guaranteed durable** | Recovery must preserve the transaction outcome even if some data pages were not flushed; this is a primary purpose of redo/WAL. |
| **Connection lost right at commit** | The client may **not know** whether the commit succeeded or not. Query business status/idempotency before retrying; never guess that a lost connection means rollback. |

Sequential example:

~~~sql
BEGIN;
UPDATE tx_account_lab SET balance = balance - 100 WHERE id = 1;
UPDATE tx_account_lab SET balance = balance + 100 WHERE id = 2;
COMMIT;
~~~

If the system stops before commit, it must never recover into "account 1 lost 100 while account 2 did not receive it." If commit completed durably, the engine is responsible for recovering the committed result. **Developers do not manually read WAL to roll back**; you issue `ROLLBACK` (or let Spring decide rollback), and the database executes recovery.

**Distinguishing technical logs from business logs:**

| Database technical log | Audit log / application log |
| --- | --- |
| Used for crash recovery, replication, or internal engine mechanisms | Used to know who did what, when, and which business decision was made |
| Usually an internal format serving the engine | Designed for applications/humans to query and administer |
| Not automatically a human-readable/permanent business history | Cannot replace WAL or make transactions durable on its own |

Durability also depends on `fsync`/synchronous commit settings, hardware, and storage mechanisms. Disabling or relaxing flush guarantees trades risk of losing recently acknowledged changes on crash for performance. Never promise "zero data loss ever" solely because transactions are enabled.

## 3. Locking: coordinating when multiple transactions access the same data

### When two transactions UPDATE the same row

T1 wants to subtract 100 from account 1; T2 wants to subtract 10 also from account 1. If both wrote freely without coordination, the update order could lose changes or violate business conditions.

In many relational databases, an `UPDATE` statement must acquire **appropriate locks on the affected record or related resource**. While T1 holds a write lock on row 1, T2's competing write must typically **wait** or encounter a conflict/timeout error depending on the scenario. A simple schedule:

~~~text
Time          T1 (connection 1)                T2 (connection 2)
---------     ------------------               ------------------
t1            BEGIN
t2            UPDATE account 1 (-100)
t3                                             BEGIN
t4                                             UPDATE account 1 (-10)
t5                                             -> must wait for lock
t6            COMMIT (releases lock)
t7                                             resumes UPDATE
t8                                             COMMIT
~~~

If both statements are written relatively as `balance = balance - amount` and the sufficient-funds check is evaluated **inside SQL**, the database can serialize updates to that row appropriately. Even so, **locks cannot fix a flawed application algorithm**: if the client precomputes a balance from an old read and sends `UPDATE balance = 990`, it can still overwrite a newer change.

### Types of locks to know conceptually

- **Shared/read lock:** allows multiple concurrent readers in lock-based schemes, while preventing incompatible writes. A plain `SELECT` under MVCC does not necessarily acquire a shared row lock.
- **Exclusive/write lock:** restricts other tasks from writing/modifying the protected resource.
- **Row, table, page, key-range/predicate locks:** granularity and purpose vary by engine, SQL statement, and isolation level. Range/predicate locks also help handle cases like new rows appearing within a scanned range.
- **Locking read:** operations such as `SELECT ... FOR UPDATE` explicitly request a lock before deciding on an update; this is a read **that can wait on locks**, unlike a plain snapshot read.

Lock names and compatibility rules are engine-specific details. **Never assume every `SELECT` locks rows**, or that every lock applies only to a single row. Engines also use metadata locks and other internal lock types.

### Lock wait, timeout, and deadlock

**Lock wait:** T2 temporarily waits for T1 to release a lock. This can be normal, yet overly long transactions raise latency and exhaust connection pools.

**Deadlock:** T1 holds lock A and needs B; meanwhile T2 holds lock B and needs A:

~~~text
T1: lock A ---- waits for B
                 ^   |
                 |   v
T2: waits for A <- lock B
~~~

Neither can proceed in that order. Databases typically have deadlock detection/resolution, such as aborting one transaction and reporting an error so the caller can **retry the entire business operation** under an appropriate policy. Spring `@Transactional` **does not retry automatically**. Avoid deadlocks by keeping transactions short, updating multiple resources in a consistent order, and avoiding HTTP/network waits inside transactions.

### Pessimistic locking and optimistic version checking

When high contention is expected, the application can use **pessimistic locking** (`SELECT ... FOR UPDATE`) to reserve update rights. Another approach is **optimistic concurrency**: read a `version` column and only update if the version has not changed:

~~~sql
-- Conceptual outline: version=7 was read earlier
UPDATE inventory_item
SET quantity = quantity - 1,
    version = version + 1
WHERE id = 42 AND version = 7 AND quantity >= 1;
-- If updated rows = 0: data/version changed or stock is insufficient;
-- must handle conflict, never assume the write succeeded.
~~~

This is a syntax example on an illustrative table with columns `id, quantity, version`. **Application-level optimistic locking is not synonymous with MVCC**, even though both involve a concept of "versions."

## 4. MVCC: multiple versions for consistent reads

If strict read/write locks were taken on every operation, a long update transaction could block many read queries. **MVCC (Multi-Version Concurrency Control)** allows the database to maintain row versions so readers see a *valid snapshot*, rather than viewing in-progress modifications or blocking all read queries.

Example where account 1 has a committed balance of 1,000:

~~~text
T0: committed version            balance = 1000
T1: transaction A UPDATE -100    creates new state = 900 (uncommitted)
T2: transaction B SELECT         can read valid 1000 version
T3: A COMMIT                     900 state becomes committed
T4: a SELECT with new snapshot   can read 900
~~~

In PostgreSQL under `READ COMMITTED`, each normal `SELECT` takes its own snapshot at the start of the statement. Thus a SELECT before A commits can see 1,000; a new SELECT after A commits can see 900. Under a higher isolation level with a fixed snapshot, **the second SELECT does not necessarily see 900**: snapshot rules depend on engine and isolation level.

### Snapshots answer "which version is visible?"

The database uses transaction state/identifiers and observation timing to decide which version is visible. An **uncommitted** update by A does not become valid data for B merely because it sits in RAM.

- Readers can see versions that are **committed and match the snapshot**.
- A transaction can generally see changes **made by itself**, even uncommitted, per engine semantics.
- Once a version is no longer needed by any live snapshot, the engine can reclaim old versions/resources via its own mechanism, such as vacuum/purge.
- Long-lived transactions keep old versions alive longer in some engines, increasing storage pressure and cleanup work.

**MVCC does not mean lock-free.** MVCC generally helps **plain reads** and **writes** block each other less; yet two transactions **updating** the same row, or `SELECT ... FOR UPDATE`, still contend on locks. Some engines also use gap/next-key locks or conflict checks to enforce isolation policies.

### Does MVCC solve every concurrency anomaly?

**No.** Consistent snapshot reads on single statements do not prove an entire business workflow is safe against all concurrency anomalies.

Example of a **lost update from read-then-write logic**:

1. B reads `balance = 1000`.
2. A subtracts 100 and commits, bringing the balance to 900.
3. B uses the stale value to compute `1000 - 10 = 990` and sends `UPDATE account SET balance = 990`.
4. Under certain isolation levels/engines, B's operation can succeed after waiting out the conflict, losing A's 100 deduction.

A safer approach for balance deductions is a **relative, conditional update directly inside SQL**:

~~~sql
UPDATE tx_account_lab
SET balance = balance - 10
WHERE id = 1 AND balance >= 10;
~~~

Check the updated row count and handle `0 rows`. For more complex cases, use locking reads, optimistic version checks, appropriate isolation levels, and transaction retries upon conflict errors. **Consistent snapshot reads** and **multi-writer business invariants** are two distinct requirements.

## 5. How do the three mechanisms collaborate in one transaction?

Consider transaction A executing two `UPDATE`s to transfer 100 between accounts 1 and 2, while B wants to read and write account 1:

~~~text
               ┌─────────────────────── Database ───────────────────────┐
Spring service ─> Transaction boundary (BEGIN ... COMMIT / ROLLBACK)     │
               │                                                        │
               │  WAL / redo / recovery: preserves crash recoverability │
               │  Locks: coordinates UPDATEs & special read-write locks │
               │  MVCC: selects valid read versions according to snapshot│
               │                                                        │
               └────────────────────────────────────────────────────────┘
~~~

A conceptually accurate interpretation:

1. When A starts a transaction, the database sets up transaction context. Spring merely requests or joins the appropriate transaction.
2. When A updates rows 1 and 2, the database manages changes, recovery records, and write conflicts (potentially via row locks/version checks).
3. B's normal `SELECT` can read the older committed snapshot version instead of seeing half of A's uncommitted results.
4. If B tries to `UPDATE` the same row, it may wait for A or receive a conflict error.
5. A commits: the engine applies WAL/recovery guarantees and makes the committed state visible per its rules; write locks are released according to the transaction lifecycle.
6. A rolls back or fails: A's uncommitted changes are not left as valid committed data; other transactions proceed per engine concurrency rules.

**How much is guaranteed depends on** transaction type, isolation level, database, SQL statements, and durability settings. Never infer details like "which log file is written", "lock granularity", or "snapshot timestamp" from a Spring annotation alone.

## 6. Hands-on observation with two PostgreSQL sessions

This lab makes concrete the collaboration between **MVCC for SELECT** and **locking for UPDATE**. Use a **test** PostgreSQL database and two terminal windows opening two independent `psql` connections; never run on production data.

### One-time setup

If you have local PostgreSQL and permission to create databases:

~~~bash
createdb tx_lab
psql -d tx_lab
~~~

In the setup connection, run:

~~~sql
CREATE TABLE tx_account_lab (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO tx_account_lab(id, balance) VALUES (1, 1000), (2, 500);
~~~

Close or keep the setup connection separate. Open **two separate terminals**, both connected to the database:

~~~bash
psql -d tx_lab
~~~

### Session A: create an uncommitted update

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
UPDATE tx_account_lab
SET balance = balance - 100
WHERE id = 1;
-- Do not COMMIT at this point.
~~~

A is holding an open transaction. Under PostgreSQL's behavior, A's new result of 900 is uncommitted, and competing writes on row 1 are subject to lock coordination.

### Session B: read first, then try to update

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM tx_account_lab WHERE id = 1;
-- Expected result while A has not committed: 1000.

UPDATE tx_account_lab
SET balance = balance - 10
WHERE id = 1;
-- This UPDATE will wait while A still holds the conflict on row 1.
~~~

Observation sequence:

- `SELECT` in B still reads 1,000 from snapshot; this illustrates reading without waiting for the writer's commit.
- `UPDATE` in B **waits** because both want to modify row 1; MVCC does not eliminate write conflicts.
- **While B is waiting**, switch to terminal A and run `COMMIT;`.
- B completes its `UPDATE`; then in B run `COMMIT;` and `SELECT balance FROM tx_account_lab WHERE id = 1;`.

With this sequence and no third operation, **the final result in PostgreSQL is 890** (1,000 − 100 − 10). PostgreSQL updates based on the current row version consistent with `UPDATE` semantics under `READ COMMITTED`; the relative statement does not lose A's deduction.

**Control experiment:** use a fresh test database (or reset the balance to 1,000 after ending all transactions), have B read 1,000, and prepare `UPDATE tx_account_lab SET balance = 990 WHERE id = 1;`. Writing a **precomputed value from an old read** can overwrite A's 900 update after A commits. Read-then-write logic itself is dangerous; lock waiting alone is not enough to preserve client-side arithmetic semantics.

### Observing rollback

After all sessions have committed and no waiting transactions remain, in one session:

~~~sql
SELECT balance FROM tx_account_lab WHERE id = 1;
-- 890 from the scenario above.

BEGIN;
UPDATE tx_account_lab SET balance = balance - 50 WHERE id = 1;
ROLLBACK;

SELECT balance FROM tx_account_lab WHERE id = 1;
-- Still 890: the uncommitted UPDATE -50 was undone.
~~~

This lab demonstrates the **observable effects** of rollback, snapshots, and lock waits. It does not directly prove on-disk WAL details; to verify crash recovery mechanisms, consult official documentation and test on a system permitted to stop/restart safely.

## 7. Connecting to Spring Framework: boundaries and isolation

The illustrative code below is a **Spring service class**, requiring a Java 17+ project with Spring JDBC, Spring Transaction, `JdbcTemplate`, `DataSource`, and a `PlatformTransactionManager` matching the database. This is **not** a standalone Java program runnable with `javac` alone.

**File `src/main/java/com/example/tx/TransferService.java`:**

~~~java
package com.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE tx_account_lab " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Invalid source or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE tx_account_lab " +
            "SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Target account does not exist");
        }
    }
}
~~~

### Reading the example through the three mechanisms

- **Spring:** when a caller invokes `transfer()` **through a Spring proxy**, the transaction interceptor asks the transaction manager to start or join a transaction. Both `JdbcTemplate.update` calls participate in the managed transaction when connection configuration is consistent. Normal completion lets the transaction owner commit; an escaping unchecked exception triggers Spring's default rollback or marks rollback-only.
- **Database log/recovery:** the engine manages recoverable changes; the Java service **does not** manually write WAL.
- **Locking:** both `UPDATE`s may hold corresponding write locks. If someone concurrently updates the same accounts, waits/timeouts/deadlocks can occur; the code does not eliminate that possibility.
- **MVCC:** `SELECT`s from other transactions can read committed snapshots while the service is writing, depending on database and isolation. `@Transactional` does not explicitly execute a statement to "turn on MVCC."

**Why specify `isolation = Isolation.READ_COMMITTED`?** This is the requested isolation level **when Spring starts a new transaction** and the database/transaction manager supports it; it does not change the engine's MVCC design. If the call merely **joins an existing transaction**, isolation attributes on the inner method do not automatically change the active isolation level. You may omit this parameter to use `Isolation.DEFAULT` (database default); never take the annotation name as proof that every engine applies identical behavior.

**Default propagation:** `@Transactional` uses `REQUIRED`. A service method joining the caller's transaction may **not yet have committed** when it returns; the commit point is decided by the enclosing transaction.

**Default rollback rules:** Spring marks rollback for escaping `RuntimeException` and `Error`. Checked exceptions do not default to triggering rollback; consider `rollbackFor` if needed. Catching and swallowing errors can let the transaction exit normally and commit invalid state.

**Proxy/self-invocation:** calling `this.transfer(...)` from another method in the same bean normally bypasses the transaction interceptor in default proxy mode. Test using a real Spring-managed bean rather than instantiating the service with `new`.

**`readOnly = true` is not a lock or invariant guarantee:** it is primarily an optimization hint and may make some drivers/engines reject writes depending on configuration; it does not automatically create a long-lived snapshot or reliably forbid every `UPDATE`.

### Isolation levels are behavioral contracts, not algorithm names

| Isolation level | Practical understanding | What you must still verify yourself |
| --- | --- | --- |
| `READ UNCOMMITTED` | Weak SQL-standard level; engine implementations vary, and some engines elevate the effective level. | Do not assume dirty reads will necessarily be observed. |
| `READ COMMITTED` | Avoids reading uncommitted data; in PostgreSQL snapshots are typically **per-statement**. | Non-repeatable reads and certain read-modify-write races can still happen. |
| `REPEATABLE READ` | Aims for more stable reads within the same transaction. | Snapshot rules, locking reads, phantoms, and write conflicts differ between PostgreSQL and InnoDB. |
| `SERIALIZABLE` | Aims for outcomes equivalent to a serial execution order of committed transactions. | The database may **abort transactions** upon detecting conflicts; the application must safely retry the **entire transaction**. |

Do not apply PostgreSQL's snapshot behavior from this lab verbatim to Oracle, SQL Server, MySQL/InnoDB, or every engine version. Read the isolation/concurrency documentation for your target DBMS and test in an environment matching production configuration.

## 8. Common misconceptions

| Misconception | Accurate fact to remember |
| --- | --- |
| "With `@Transactional`, data can never be lost." | Durability depends on the database, log flushing, hardware, configuration, and transaction boundaries. |
| "WAL is a log file recording SQL statements for developers to read." | WAL/redo is an internal recovery mechanism; audit logs and application logs serve different purposes. |
| "With MVCC, all locks disappear." | Concurrent writes, locking reads, DDL, and other operations can still wait on locks. |
| "Write locks make any Java calculation on stale reads correct." | Read-modify-write can still overwrite data; use atomic SQL, version checks, or suitable isolation/locking. |
| "Snapshot read means reading the absolute latest state." | A snapshot may reflect an earlier point in time, intentionally hiding newer commits depending on isolation. |
| "Every SELECT acquires a shared row lock." | In many MVCC databases, SELECTs are served from snapshots without holding corresponding shared row locks. |
| "`SERIALIZABLE` means waiting until guaranteed to run." | The engine may abort transactions with serialization/deadlock errors and require retries. |
| "Setting isolation to the highest level is always optimal." | Higher isolation can increase contention, retries, and overhead; choose based on invariants to protect. |
| "Database transactions roll back HTTP/email/messages too." | A local database transaction does not undo external effects; use suitable coordination architectures like outbox/saga. |
| "If a transaction closed without client response, it definitely didn't commit." | This is an **uncertain** outcome for the client; check idempotency/status before retrying. |

## 9. How to choose mechanisms when designing a feature

Ask three questions in order:

1. **If a crash happens between two update steps, what must be recovered?** Group atomically related updates into the **same database transaction**, using an engine/configuration with appropriate recovery and durability. Test rollback when the second step fails.
2. **If two users modify data concurrently, what could be overwritten or violated?** Use SQL conditional checks, locks when needed, version checks, DB constraints, consistent access ordering, and retry strategies for contention errors.
3. **If one user reads while another writes, what point-in-time state must be seen?** Identify your engine's isolation and snapshot behavior. When reading in order to update, also check for lost updates/write skew; do not rely solely on "SELECT doesn't wait" or "MVCC is enough."

**Decision illustration:** in a booking system, a transaction avoids writing half an order; `UPDATE ... WHERE seats_left > 0` or an appropriate lock prevents overselling seats; MVCC lets display queries show seat counts while other transactions run, yet the displayed count can become stale before the user clicks confirm. **Checking and deducting seats must happen inside the transaction at confirmation**, never trusting screen-read numbers unconditionally.

## 10. Self-check

1. **An UPDATE finished in RAM, then the DB crashed before data pages were written, while the transaction had durably committed. Which mechanism is key?** — WAL/redo and crash recovery restore committed changes under durability guarantees.
2. **Two transactions UPDATE the same row; does MVCC ensure neither waits?** — No; writing the same row usually involves conflicts coordinated by locks or appropriate checks.
3. **Under PostgreSQL READ COMMITTED, A reduces 1,000 to 900 without committing. What does a plain SELECT in B see?** — The committed version matching its snapshot—1,000 in the lab.
4. **Why can B reading 1,000 and writing hardcoded 990 still be wrong even though UPDATE locks?** — 990 was computed from stale data and can overwrite A's update; locking only coordinates write timing.
5. **Does adding `@Transactional` automatically create MVCC?** — No. Spring configures/requests the transaction; the database determines logging, locking, versioning, and isolation mechanisms.
6. **Why can a long-running transaction slow down a system even if it mostly reads?** — It may hold snapshots/resources open for a long time, hindering old-version reclamation or increasing contention depending on the engine.

**Learning summary:** logging protects **crash recoverability**; locking coordinates **access conflicts**; MVCC enables **consistent version reads** at specific isolation levels. Spring `@Transactional` is how you declare **business boundaries** leveraging database guarantees. Understanding each mechanism's role and limits prevents both half-baked updates and subtle concurrency bugs.

### Official references

- [PostgreSQL — Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html)
- [PostgreSQL — Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)