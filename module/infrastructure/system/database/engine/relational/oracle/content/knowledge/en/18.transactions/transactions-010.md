# SERIALIZABLE, READ ONLY, and Consistency Differences

Oracle Database supports multiple ways to control how a transaction sees data modified concurrently by other sessions. Two modes that must often be distinguished are **SERIALIZABLE** and **READ ONLY**. Both provide a consistent snapshot at the transaction level, yet their goals and allowed operations differ:

- **SERIALIZABLE** allows a transaction to read and write while preserving a consistent data view from when the transaction began. If the transaction attempts to modify a row that was changed and COMMITted by another transaction after its snapshot point, Oracle can raise ORA-08177.
- **READ ONLY** allows a transaction to execute read statements against the same transaction-level snapshot while disallowing data modifications. It suits reports composed of multiple SELECT statements that must observe the same logical point in time.
- **READ COMMITTED**, Oracle's default level, creates a fresh snapshot for each read statement. Two SELECTs in the same transaction can see two different COMMITted states if another transaction COMMITs in between.

The core point is distinguishing **statement-level snapshots** from **transaction-level snapshots**. SERIALIZABLE and READ ONLY allow reads within a transaction to see the exact same data version COMMITted as of when the transaction started; READ COMMITTED takes a new snapshot for each statement. Oracle uses MVCC and UNDO to reconstruct appropriate data versions so standard readers never have to read a writer's uncommitted changes.

This lesson presents the semantics of all three modes, two-session scenarios, handling ORA-08177, limitations of READ ONLY, impacts on locks and UNDO, and configuring transactions via JDBC and Spring.

## 1. Snapshots and Read Consistency in Oracle

A SELECT statement does not simply read each block in whatever newest state happens to exist at the instant it touches that block. Oracle provides **read consistency**: a statement reads data according to a consistent snapshot, identified by an appropriate System Change Number (SCN).

When another session UPDATEs a row without COMMITting yet:
- The session performing the UPDATE sees its own transaction's changes.
- Other standard reading sessions do not see uncommitted changes.
- Readers can use UNDO to reconstruct the previously COMMITted version.
- If the writer COMMITs while a long SELECT is already running, that SELECT continues reading according to the snapshot from when its statement began.

This mechanism belongs to **multi-version concurrency control (MVCC)**. Instead of forcing readers and writers to always wait on each other, Oracle maintains the information required so readers can see data versions matching their snapshot.

### 1.1. Two Time Concepts to Distinguish

**Statement-level snapshot** is the consistency milestone of a single SQL statement. Under READ COMMITTED, each new SELECT statement gets a new snapshot.

**Transaction-level snapshot** is a consistency milestone shared across read statements in one transaction. SERIALIZABLE and READ ONLY use this mode of reading.

Example:

~~~text
Time  ───────────────────────────────────────────────────────>

Session B (READ COMMITTED):
  SELECT #1 ── snapshot S1
                    |
Session A:          UPDATE; COMMIT
                                      |
Session B:                            SELECT #2 ── snapshot S2

S2 is newer than S1, so B can see the data A just COMMITted.
~~~

Under SERIALIZABLE or READ ONLY, B's SELECTs within the same transaction continue using the initial transaction-level snapshot, even if A COMMITs new data in between.

### 1.2. A Snapshot Does Not Mean a Session Sees Stale Data of Its Own Changes

A transaction always sees changes made by itself. A transaction-level snapshot describes visibility relative to *other* transactions' changes; it does not hide the session's own uncommitted operations.

Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

The second SELECT in the same transaction sees the balance after its own UPDATE, even though other sessions do not yet see that change.

### 1.3. UNDO Enables Reading Older Versions

When a transaction modifies data, Oracle writes the UNDO information needed to roll back and reconstruct prior versions. Readers can use UNDO to view the state at their snapshot SCN.

UNDO is not an infinite archive:
- UNDO data is reused according to configuration and workload pressure.
- Long-running transactions or queries may need older versions that have already been overwritten.
- A long SELECT may encounter ORA-01555 if Oracle no longer has enough UNDO to reconstruct the needed snapshot.

Therefore, long read transactions and heavy reports must also be designed with awareness of runtime duration, concurrent DML volume, and UNDO capacity.

## 2. READ COMMITTED: A Separate Snapshot for Each Statement

READ COMMITTED is Oracle Database's default isolation level. A SELECT sees data COMMITted as of when the statement begins. The next SELECT in the same transaction can see newer COMMITs.

~~~sql
-- Session B: READ COMMITTED
SELECT balance
FROM accounts
WHERE account_id = 1;

-- Session A UPDATEs and COMMITs.

-- Session B runs a new statement.
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

If A COMMITs between the two SELECTs, B's second query can see the new value.

### 2.1. Non-Repeatable Read

A transaction reads the same row twice and gets two different values because another transaction COMMITted in between:

~~~text
B: SELECT balance -> 1000
A: UPDATE balance = 900; COMMIT
B: SELECT balance -> 900
~~~

There is no dirty read here. B only sees 900 after A has COMMITted.

### 2.2. Phantom Rows

A first SELECT returns a set of rows. Another session inserts a new row matching the condition and COMMITs. A second SELECT can see that additional row:

~~~text
B: SELECT * FROM orders WHERE status = 'NEW' -> 5 rows
A: INSERT a NEW order; COMMIT
B: SELECT * FROM orders WHERE status = 'NEW' -> 6 rows
~~~

Each statement remains consistent at its own snapshot. READ COMMITTED does not promise that every SELECT in the same transaction will see the exact same row set.

### 2.3. READ COMMITTED Never Reads Uncommitted Data

If A UPDATEs balance from 1000 to 900 without COMMITting yet, B's standard SELECT still sees 1000. Only after A's COMMIT can a new SELECT by B see 900.

Do not call B seeing a new value in its second statement a dirty read. That value was already confirmed.

## 3. SERIALIZABLE: Consistent Snapshot at the Transaction Level

Start a SERIALIZABLE transaction with:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

This statement must execute at the beginning of the transaction, before other statements in that transaction. Afterward, the transaction:
- Sees data COMMITted prior to its snapshot point.
- Sees changes performed by itself.
- Does not automatically see new COMMITs from other sessions in subsequent reads.
- Can perform INSERT, UPDATE, and DELETE.
- Can encounter ORA-08177 if it tries to modify a row changed by another transaction after its snapshot started.

Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

-- Run additional SELECTs and DML inside the transaction.
COMMIT;
~~~

Reads in the transaction use the same transaction-level snapshot, plus changes created by the current transaction.

### 3.1. Two-Session Example

Suppose the initial COMMITted data is:

~~~text
ACCOUNT_ID = 1
BALANCE    = 1000
~~~

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B receives 1000. B's transaction snapshot has been established.

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

A COMMITs successfully.

Session B runs SELECT again:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B still sees 1000 because the SERIALIZABLE transaction keeps using its initial snapshot. Session A COMMITted 900, but that change occurred after B's snapshot.

If B COMMITs or ROLLBACKs and starts a new transaction in READ COMMITTED, a new SELECT can see 900.

### 3.2. SERIALIZABLE Does Not Lock the Entire Table

SERIALIZABLE does not mean other sessions are barred from reading or writing the entire table. Other sessions can still run their own transactions. Oracle uses snapshots and write-conflict detection to preserve consistency.

A standard SELECT inside a SERIALIZABLE transaction does not necessarily lock the rows it reads. If you need row locks to coordinate updates, see `SELECT FOR UPDATE` and dedicated locking design.

### 3.3. DML in SERIALIZABLE

SERIALIZABLE permits a transaction to write. Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

INSERT INTO transfer_log(
    transfer_id,
    account_id,
    amount
)
VALUES (7001, 1, 100);

COMMIT;
~~~

The transaction's reads use the initial snapshot, while changes made by the current transaction remain visible to itself. However, if the target row was modified and COMMITted by another transaction after the snapshot started, DML can be rejected with ORA-08177.

## 4. ORA-08177: can't serialize access for this transaction

Error ORA-08177 typically appears when a SERIALIZABLE transaction attempts to modify a row that was changed and COMMITted by another transaction after the current transaction began.

Example:

1. B starts SERIALIZABLE and reads row `ACCOUNT_ID=1` at balance 1000.
2. A UPDATEs that row to 900 and COMMITs.
3. B attempts to UPDATE the same row against the stale snapshot.

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
UPDATE accounts
SET balance = 800
WHERE account_id = 1;
~~~

Oracle can return:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Oracle prevents B from writing in a way that would break serializability of the transaction snapshot.

### 4.1. Why Should You Not Simply Re-Run the UPDATE Statement?

After ORA-08177, the current transaction holds an outdated snapshot. Merely re-running the UPDATE inside the same transaction does not fix the stale snapshot. The standard handling workflow is:
1. ROLLBACK the current transaction.
2. Start a new SERIALIZABLE transaction.
3. Re-read data from the fresh snapshot.
4. Recompute business decisions.
5. Re-execute the entire unit of work.
6. COMMIT if all conditions remain valid.

Never retry only the last SQL statement if earlier decisions were computed from the stale snapshot.

### 4.2. Retries Must Be Safe

A transaction can be retried if the business operation can safely execute again. You need:
- A bounded retry count.
- Short backoff if conflicts repeat.
- Assurance that INSERTs do not create duplicate records on retry.
- An idempotency key or unique constraint for requests that may repeat.
- No sending emails or calling external services before knowing the transaction COMMITted.
- Logging of transaction attempts and retry causes.

If a transaction already produced side effects outside the database, ROLLBACK cannot recall them. Design an outbox or compensating mechanism to synchronize state.

### 4.3. Not Every Error Is ORA-08177

A SERIALIZABLE transaction can still hit:
- Constraint errors.
- Deadlocks.
- Lock timeouts.
- ORA-01555 due to insufficient UNDO for consistent reads.
- Data or application bugs.

Only retry errors identified as transient under an explicit policy. Never blindly retry every `SQLException` indefinitely.

## 5. READ ONLY: Read-Only Transactions with a Transaction-Level Snapshot

Start a READ ONLY transaction:

~~~sql
SET TRANSACTION READ ONLY;
~~~

READ ONLY provides a consistent transaction-level snapshot, identical to the read view of SERIALIZABLE. The key difference is that READ ONLY disallows data modification.

Example of a report needing to read multiple tables and compute multiple metrics:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT SUM(amount) AS revenue
FROM orders;

SELECT COUNT(*) AS customer_count
FROM customers;

COMMIT;
~~~

SELECT statements belonging to the same READ ONLY transaction see the same snapshot. If another session COMMITs a new order between the first and second SELECT, the active report continues using its initial snapshot.

### 5.1. READ ONLY Is Not Just for One SELECT

A single SELECT under READ COMMITTED already has statement-level consistency. READ ONLY is useful when you need multiple separate SELECT statements to observe the exact same snapshot.

Example:
- Total orders report.
- Total revenue report.
- Customer count report.
- Cross-table total reconciliation.

If each SELECT ran in a separate READ COMMITTED transaction, or even in the same transaction where each statement takes a new snapshot, the numbers could reflect different points in time. READ ONLY keeps all reads in the same transaction consistent with one milestone.

### 5.2. READ ONLY Disallows DML

Inside a READ ONLY transaction, do not execute INSERT, UPDATE, or DELETE:

~~~sql
SET TRANSACTION READ ONLY;

SELECT *
FROM accounts;

-- Invalid inside a READ ONLY transaction:
UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;
~~~

Oracle rejects the data-modifying statement. If you need both reads and writes, use READ COMMITTED or SERIALIZABLE as required.

### 5.3. READ ONLY Does Not Lock Tables Against Other Sessions

While a READ ONLY transaction is running:
- Other sessions can still INSERT/UPDATE/DELETE and COMMIT.
- The READ ONLY transaction does not see changes COMMITted after its snapshot.
- Readers do not lock all data just because they use READ ONLY.
- DML in other sessions does not have to wait for a READ ONLY transaction to finish simply to modify rows being read normally.

This is why READ ONLY suits reporting running concurrently alongside write workloads.

### 5.4. Ending a READ ONLY Transaction

Either COMMIT or ROLLBACK ends a READ ONLY transaction. There is no DML in the transaction to confirm or discard, yet ending the transaction releases the snapshot and associated resources.

~~~sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount) FROM orders;
SELECT COUNT(*) FROM customers;

COMMIT;
~~~

After COMMIT, the next SELECT starts a new transaction and can see recently COMMITted changes.

## 6. Comparing READ COMMITTED, SERIALIZABLE, and READ ONLY

| Criterion | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Oracle default | Yes | No | No |
| Snapshot | Per statement | Transaction-level | Transaction-level |
| Dirty read | No | No | No |
| New SELECT sees another session's new COMMIT | Possible | No, in current transaction | No, in current transaction |
| Sees current transaction's own changes | Yes | Yes | No DML |
| Allows INSERT/UPDATE/DELETE | Yes | Yes | No |
| Can hit ORA-08177 due to write conflict | Not under this SERIALIZABLE mechanism | Yes | No writes by this transaction |
| Best suited for | Normal application transactions | Transactions needing a stable snapshot plus writes | Multi-SELECT reports sharing one snapshot |

### 6.1. READ COMMITTED

Use when:
- Each statement can read the latest state COMMITted when it starts.
- The transaction does not require all SELECTs to share one snapshot.
- You want the standard default for OLTP applications.
- Non-repeatable reads/phantoms across statements are acceptable.

### 6.2. SERIALIZABLE

Consider when:
- A unit of work needs multiple reads on the same snapshot.
- Write decisions depend on the read state.
- The application can handle ORA-08177 by rolling back and retrying the entire transaction.
- Transactions are short enough and contention is controllable.

### 6.3. READ ONLY

Consider when:
- A report needs to run multiple SELECT statements.
- Totals must reconcile as of the same logical point in time.
- The transaction needs no DML.
- The read transaction can close promptly once the report finishes.

Do not use SERIALIZABLE merely for a consistent read report if no writes are needed. READ ONLY expresses read-only intent far more cleanly.

## 7. Comparison via a Two-Session Timeline

Suppose table `ACCOUNT` starts with a COMMITted balance of 1000.

### 7.1. READ COMMITTED

Session B:

~~~sql
-- Default READ COMMITTED.
SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A:

~~~sql
UPDATE account
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance FROM account WHERE account_id = 1;
-- 900
~~~

B's two SELECTs use two different statement snapshots.

### 7.2. SERIALIZABLE

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A:

~~~sql
UPDATE account
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance FROM account WHERE account_id = 1;
-- Still 1000 within the current transaction.
~~~

After B ends its transaction:

~~~sql
COMMIT;

SELECT balance FROM account WHERE account_id = 1;
-- A new transaction in READ COMMITTED can see 900.
~~~

### 7.3. READ ONLY

Session B:

~~~sql
SET TRANSACTION READ ONLY;

SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A UPDATEs to 900 and COMMITs. Session B SELECTs again and still sees 1000. B cannot UPDATE that row inside the READ ONLY transaction. After B's COMMIT, a new SELECT can see 900.

### 7.4. Summary Table

| Point in Time | Session A | B READ COMMITTED | B SERIALIZABLE | B READ ONLY |
| --- | --- | ---: | ---: | ---: |
| Initial | No change | 1000 | 1000 | 1000 |
| A UPDATEs 900, not COMMITted | 900 | 1000 | 1000 | 1000 |
| A COMMITs | 900 | New SELECT: 900 | Next SELECT: 1000 | Next SELECT: 1000 |
| B ends transaction and runs new SELECT | 900 | 900 | 900 | 900 |

B's columns assume each SELECT starts after the corresponding event. If B was already running a statement from before A's COMMIT, that statement keeps its own snapshot even under READ COMMITTED.

## 8. Setting the Isolation Level at the Right Time

Oracle requires `SET TRANSACTION` to be used at the start of a transaction. Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT ...
UPDATE ...
COMMIT;
~~~

Or:

~~~sql
SET TRANSACTION READ ONLY;

SELECT ...
SELECT ...
COMMIT;
~~~

Do not run a SELECT or DML first and then try `SET TRANSACTION` for the same transaction:

~~~sql
SELECT COUNT(*) FROM orders;

-- Do not set isolation level in the middle of a transaction.
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

If the transaction has already begun, `SET TRANSACTION` will raise an error because it is no longer at the start of the transaction.

### 8.1. When Does a Transaction Start?

In SQL clients, a DML transaction normally starts when the session executes a transaction-initiating operation. With SERIALIZABLE/READ ONLY, `SET TRANSACTION` configures the upcoming transaction and must run before any other statements of that transaction.

In JDBC applications, `setAutoCommit(false)` typically configures the connection so multiple statements share a transaction; the actual database transaction starts when the first statement is sent. Therefore, configure isolation/READ ONLY before the first business SQL statement.

### 8.2. Do Not Mix DDL with a Transaction That Must Keep Its Snapshot

Oracle DDL follows the implicit commit rule. CREATE, ALTER, DROP, and TRUNCATE can end the preceding transaction. Never run DDL mid-way inside a SERIALIZABLE/READ ONLY transaction where you need to keep the snapshot and rollbackability intact.

Perform DDL in a separate deployment/schema migration step, outside business transactions.

## 9. READ ONLY and SELECT FOR UPDATE

`SELECT FOR UPDATE` reads rows and requests locks so the session can update safely afterward:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

This is a locking read, not a standard SELECT. It is incompatible with a READ ONLY transaction because that transaction is disallowed from modifying data and cannot be used to acquire write locks in this way.

In SERIALIZABLE, `SELECT FOR UPDATE` remains an explicit locking mechanism; understand its interaction with transaction isolation and conflicts. Do not use `SELECT FOR UPDATE` for a report that merely needs a consistent snapshot.

### 9.1. When Row Locks Are Needed, Use a Read-Write Transaction

Example checking a balance and then debiting:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;

COMMIT;
~~~

Locking the row prevents other transactions from concurrently updating the same row before the current transaction ends. In real applications, check the updated row count to confirm the debit took effect.

### 9.2. When Only a Consistent Report Is Needed, Do Not Lock Every Row

If the goal is merely reading total revenue, order count, and customer count from one snapshot, READ ONLY is far better suited. There is no need to lock every table via `SELECT FOR UPDATE` just to stop numbers from shifting between SELECTs.

## 10. SERIALIZABLE and Write-Conflict Errors

SERIALIZABLE maintains a transaction-level snapshot while still permitting writes. When two transactions update data concurrently, start times and COMMIT times of each transaction matter.

### 10.1. Both Read a Value, Both Want to Update

Suppose:
- A starts SERIALIZABLE, reads balance 1000.
- B starts READ COMMITTED, UPDATEs balance to 900, and COMMITs.
- A attempts to UPDATE balance to 800.

A is working on a stale snapshot. Oracle can raise ORA-08177 because the row was modified after A's snapshot.

### 10.2. Retry the Entire Business Operation

Execution flow:

~~~text
Start SERIALIZABLE transaction
          |
Read state and check conditions
          |
Execute DML
          |
     COMMIT succeeded?
       /          \
     Yes           No
     |              |
Return result   ORA-08177?
                    |
              Full ROLLBACK
                    |
              Bounded retry
                    |
           Re-read fresh snapshot
                    |
           Recompute decisions
~~~

On retry, re-read all input data and recompute business decisions. Never reuse decisions calculated from a stale snapshot.

### 10.3. Do Not Trigger Side Effects Before COMMIT

Unsafe example:

~~~text
SERIALIZABLE transaction
  UPDATE order
  Send "confirmed" email
  COMMIT -> ORA-08177
~~~

The database rolls back, yet the email was already sent. The user receives a confirmation notice for an unconfirmed transaction.

One design pattern is writing the event to an `OUTBOX` table inside the same transaction as the order; a separate worker reads COMMITted outbox rows and dispatches notifications. This keeps database state and events recorded atomically in one transaction, while the worker can retry delivery using an idempotency key.

## 11. SERIALIZABLE, READ ONLY, and UNDO

Transaction-level snapshots can live longer than statement-level snapshots. Meanwhile, other transactions continue performing DML and generating UNDO.

A READ ONLY report running for hours may require Oracle to reconstruct data at an old SCN. If required UNDO has already been overwritten, the query can hit:

~~~text
ORA-01555: snapshot too old
~~~

### 11.1. Common Causes

- Read queries running too long.
- Read transactions kept open too long.
- Heavy concurrent DML causing UNDO to be reused rapidly.
- UNDO tablespace/retention inadequate for the workload.
- Queries processing huge volumes or having inefficient execution plans.

### 11.2. Remediation Approaches

- Shorten READ ONLY transaction duration.
- Run reports against a replica/reporting database if architecture permits.
- Tune queries, filter precisely, and review execution plans.
- Coordinate with DBAs to size UNDO tablespace and retention.
- Avoid holding read-only transactions open while the application waits for user input or does non-DB work.
- If business rules permit, split reports into independent read units accepting separate snapshots; if the exact same snapshot is mandatory, do not split arbitrarily.

Never increase `UNDO_RETENTION` mechanically without evaluating capacity, retention guarantee, and workload. This is an operational setting requiring DBA review.

## 12. SERIALIZABLE Does Not Replace All Locking Rules and Constraints

Some business rules enforce invariants across multiple rows, such as:
- Total allocations must not exceed a quota.
- Two bookings must not overlap in time.
- Inventory must never go negative.
- Only one request may hold a resource.

SERIALIZABLE ensures reads in a transaction use a stable snapshot and checks write conflicts on modified rows. However, never use an isolation level as a substitute for:
- `PRIMARY KEY` and `UNIQUE` constraints.
- `CHECK` constraints.
- Foreign keys.
- Explicit locks when coordinating access to a row.
- Data modeling designed to represent business invariants.

Enforce critical invariants in the database with constraints whenever possible. When conditions span multiple rows or time ranges, design appropriate locking/serialization and test under real concurrency.

### 12.1. Example: Protecting Non-Negative Balances

You can add a CHECK constraint:

~~~sql
ALTER TABLE accounts
ADD CONSTRAINT ck_accounts_balance_nonnegative
CHECK (balance >= 0);
~~~

Then UPDATE:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

The application checks the affected row count. The constraint protects the invariant at the database layer even when multiple applications access it concurrently.

### 12.2. Do Not Rely on Unconditional SELECT-Then-UPDATE

If an application SELECTs a balance, checks sufficiency, and then issues an unconditional UPDATE in READ COMMITTED, another transaction can alter the balance in between. Use a conditional UPDATE and check row count, or lock the relevant row appropriately.

SERIALIZABLE can be part of a design, yet does not replace defining accurate update predicates and retry logic.

## 13. JDBC: Configuring SERIALIZABLE

JDBC supports the SERIALIZABLE isolation level via the `Connection` API:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

public final class TransactionSetup {
    public static void beginSerializable(Connection connection)
            throws SQLException {
        connection.setAutoCommit(false);
        connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE
        );
    }
}
~~~

Configuration must occur before the first business SQL statement in the transaction. Drivers and pools must be configured properly so borrowed connections carry the intended isolation level.

### 13.1. SERIALIZABLE Transaction Example

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountService {
    private final DataSource dataSource;

    public AccountService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void withdraw(long accountId, BigDecimal amount)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            connection.setTransactionIsolation(
                Connection.TRANSACTION_SERIALIZABLE
            );

            try {
                BigDecimal balance;

                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT balance FROM accounts WHERE account_id = ?")) {
                    ps.setLong(1, accountId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("Account not found");
                        }
                        balance = rs.getBigDecimal("BALANCE");
                    }
                }

                if (balance.compareTo(amount) < 0) {
                    throw new SQLException("Insufficient balance");
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE accounts " +
                        "SET balance = balance - ? " +
                        "WHERE account_id = ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, accountId);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Account update failed");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

This example illustrates transaction boundaries. A production implementation must explicitly decide ORA-08177 handling, retries, idempotency, logging, and balance rules. Conditional UPDATE or `SELECT FOR UPDATE` can be used if that is a better-fitting concurrency strategy.

### 13.2. Set Isolation Before the Transaction Starts

If the connection has already executed SQL statements inside a transaction, changing the isolation level can be rejected by the driver/database or fail to behave as expected. Configure it immediately after acquiring the connection and before the first business statement.

With connection pools, isolation levels may be reset or retained depending on configuration. Verify the pool resets connection state upon return so SERIALIZABLE does not leak into the next request.

## 14. JDBC: READ ONLY Transactions

JDBC provides `Connection.setReadOnly(boolean)`, but this is a **hint** to the driver/DBMS indicating read-only intent. Never assume calling `setReadOnly(true)` is always strictly equivalent to Oracle SQL `SET TRANSACTION READ ONLY` and always enforced by the server.

When a true READ ONLY transaction under Oracle semantics is required, configure it using an Oracle-supported mechanism before the first statement:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (var statement = connection.createStatement()) {
        statement.execute("SET TRANSACTION READ ONLY");
    }

    try {
        // Report SELECTs using the same connection/transaction.
        // Do not execute DML here.

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Points to remember:
- Use the exact same `Connection` for all report SELECTs.
- `SET TRANSACTION READ ONLY` must be the first command in the transaction.
- Do not return the connection to the pool before the transaction ends.
- Do not run DML or `SELECT FOR UPDATE` inside this transaction.
- End with COMMIT or ROLLBACK.
- Test against your application's actual Oracle JDBC driver and transaction manager.

### 14.1. Why Is setReadOnly(true) Alone Insufficient to Assume Enforcement?

The JDBC API defines a read-only connection as an optimization hint for drivers. Enforcement depends on the driver and database. If the application requires the database to reject DML within the transaction, verify how the driver/transaction manager maps that flag or explicitly execute `SET TRANSACTION READ ONLY` in the proper order.

Do not call `setReadOnly` in the middle of an open transaction and assume the active transaction's snapshot converts to READ ONLY.

## 15. Spring and Transaction Isolation

Spring manages transactions via `PlatformTransactionManager`. You can request SERIALIZABLE via annotation:

~~~java
@Service
public class ReportAwareService {

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void performConsistentUpdate() {
        // Read and write within the same transaction.
    }
}
~~~

For default READ COMMITTED transactions, specifying isolation is usually unnecessary.

### 15.1. What Is @Transactional(readOnly = true)?

~~~java
@Transactional(readOnly = true)
public ReportSummary buildReport() {
    // Multiple SELECT statements.
}
~~~

The `readOnly` attribute expresses read-only intent and can allow frameworks/drivers to optimize. However, **do not automatically equate Spring's `readOnly` attribute with Oracle's `SET TRANSACTION READ ONLY` command**. Depending on the transaction manager, JDBC driver, and configuration, `readOnly` may act merely as a hint or be handled differently.

If business requirements demand that the Oracle server enforce a read-only transaction and maintain a transaction-level snapshot, verify the exact integration behavior or explicitly execute `SET TRANSACTION READ ONLY` at transaction start over the same connection.

### 15.2. Combining @Transactional with Isolation

~~~java
@Transactional(
    isolation = Isolation.SERIALIZABLE,
    rollbackFor = Exception.class
)
public void performSerializableWork() throws Exception {
    // Unit of work capable of full retry on ORA-08177.
}
~~~

Spring isolation settings take effect when the transaction manager starts a new transaction. If a method joins an existing transaction, isolation declared on the joining method may not apply like a fresh transaction; check propagation and `validateExistingTransaction` if you want mismatches detected.

### 15.3. Self-Invocation and Proxies

In common Spring proxy setups, calling a `@Transactional` method from another method on the same instance can bypass the proxy. The annotation may then fail to take effect as expected.

Design clear service boundaries, test actual transactions, and inspect transaction manager logs rather than relying on annotations by sight alone.

### 15.4. Do Not Manually COMMIT Inside a Spring-Managed Method

When Spring's transaction manager owns the transaction, never call commit/rollback directly on the framework-managed connection. Let the transaction manager end the transaction at method boundaries or per propagation rules.

## 16. READ ONLY for Multi-SELECT Reports

Suppose a report needs three numbers:
- Total orders.
- Total revenue.
- Number of purchasing customers.

If each SELECT runs in READ COMMITTED and new orders COMMIT between statements, the three numbers can reflect different snapshots. A READ ONLY transaction can preserve one snapshot:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT SUM(amount) AS revenue
FROM orders;

SELECT COUNT(DISTINCT customer_id) AS buyer_count
FROM orders;

COMMIT;
~~~

All numbers in the same transaction observe the same COMMITted data milestone.

### 16.1. Reports and Execution Time

READ ONLY does not automatically make queries faster. It provides transaction-level consistency. Performance still depends on:
- Each SELECT's execution plan.
- Indexes and partition pruning.
- Volume of data read.
- PGA/TEMP usage.
- UNDO retention and concurrent DML rate.
- How long the transaction stays open.

A report needing a shared snapshot yet running for hours can put pressure on UNDO. Coordinate with DBAs and consider a reporting replica or snapshot/reporting pipeline.

### 16.2. Does a Single Standalone SELECT Need READ ONLY?

Not necessarily. A single SELECT under READ COMMITTED already has statement-level read consistency. READ ONLY is only needed when multiple SELECTs in the same transaction must share a snapshot or when an enforced read-only transaction is required.

### 16.3. Never Hold a Report Transaction Open While Waiting for a User

Do not open a READ ONLY transaction, run a few SELECTs, and leave the connection idle waiting for a user to click Next. The transaction-level snapshot and associated resources remain held. Run the entire report within a bounded timeframe, return results, and COMMIT.

## 17. DDL and Events Ending Transactions

Oracle DDL such as CREATE, ALTER, DROP, and TRUNCATE follow implicit commit rules. Therefore:
- Never run DDL inside an active SERIALIZABLE transaction needing its snapshot preserved.
- Never run DDL inside an open READ ONLY transaction.
- Never use ROLLBACK expecting to undo succeeded DDL.
- Perform schema migrations in their own dedicated workflow.

Example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM orders;

CREATE TABLE temp_report(id NUMBER);

-- DDL can terminate the preceding transaction via implicit commit.
~~~

Do not use this pattern in business applications. DDL is not an ordinary read/write step inside the same transaction.

Sequences also do not roll back like table data. Already issued `NEXTVAL` values are not returned on rollback; gaps in sequence numbers are normal.

## 18. Practice Dataset: Two Sessions and Three Isolation Modes

Create a sandbox table:

~~~sql
CREATE TABLE isolation_demo (
    id      NUMBER(6) PRIMARY KEY,
    balance NUMBER(12,2) NOT NULL
);

INSERT INTO isolation_demo VALUES (1, 1000);
INSERT INTO isolation_demo VALUES (2, 500);
COMMIT;
~~~

Open two separate connections, called A and B.

### 18.1. Test READ COMMITTED

Session B:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Receives 1000.

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B runs a new SELECT:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Receives 900.

### 18.2. Test SERIALIZABLE

Reset data in a separate transaction if needed:

~~~sql
UPDATE isolation_demo
SET balance = 1000
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Receives 1000.

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Still receives 1000 inside the current transaction. B ends its transaction:

~~~sql
COMMIT;
~~~

Afterward, a new SELECT in B can receive 900.

### 18.3. Test ORA-08177

Reset balance to 1000 and COMMIT.

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
UPDATE isolation_demo
SET balance = 800
WHERE id = 1;
~~~

Oracle can return ORA-08177. If the error occurs, B ROLLBACKs the entire transaction before retrying with a new transaction.

### 18.4. Test READ ONLY

Reset data and COMMIT. Session B:

~~~sql
SET TRANSACTION READ ONLY;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Session A updates and COMMITs. Session B SELECTs again and still sees the initial snapshot. If B tries an UPDATE, Oracle rejects it because the transaction is read-only.

B finishes:

~~~sql
COMMIT;
~~~

Afterward, a new SELECT can see the latest COMMITted data.

### 18.5. Clean Up the Sandbox Table

~~~sql
DROP TABLE isolation_demo PURGE;
~~~

Only drop the sandbox table created by this lesson when certain the data is no longer needed. `DROP TABLE` is DDL and follows implicit commit rules; `PURGE` bypasses the recycle bin per standard behavior.

## 19. Common Misconceptions

**SERIALIZABLE and READ ONLY are the exact same mode.** False. Both provide a transaction-level snapshot, yet SERIALIZABLE permits DML and can encounter ORA-08177; READ ONLY forbids data modification.

**READ COMMITTED preserves the same snapshot for the whole transaction.** False. Each read statement gets its own snapshot.

**SERIALIZABLE locks the entire table to preserve its snapshot.** False. Oracle uses MVCC/UNDO and write-conflict detection; it does not lock the whole table just because a transaction uses SERIALIZABLE.

**READ ONLY prevents other sessions from UPDATEing.** False. Other sessions can still write and COMMIT; the READ ONLY transaction simply continues reading its own snapshot.

**READ ONLY is only useful for a single SELECT.** False. A single SELECT already has statement consistency in READ COMMITTED; READ ONLY is useful when multiple SELECTs need the same transaction-level snapshot.

**SELECT FOR UPDATE is a normal read-only SELECT.** False. It requests row locks and is unsuitable for a READ ONLY transaction.

**SERIALIZABLE cannot error because it guarantees serializability.** False. On write conflicts, Oracle can raise ORA-08177 and the application must handle it.

**After ORA-08177, just re-run the UPDATE statement.** False. The transaction snapshot is stale; you normally must ROLLBACK and retry the entire unit of work.

**A READ ONLY transaction never needs to be ended.** False. COMMIT/ROLLBACK is required to end it and release resources.

**Connection.setReadOnly(true) is always equivalent to SET TRANSACTION READ ONLY.** False. JDBC defines it as a hint; verify driver/DBMS behavior or use Oracle's explicit mechanism when server enforcement is needed.

**@Transactional(readOnly = true) always issues SET TRANSACTION READ ONLY.** False. Spring's attribute may act as a hint depending on the transaction manager and driver.

**SERIALIZABLE eliminates all need for constraints.** False. UNIQUE, CHECK, foreign keys, and conditional UPDATEs remain essential to protect business invariants.

**READ ONLY does not use UNDO.** False. Older snapshots may require UNDO to reconstruct data versions; long read transactions can hit ORA-01555.

**Another session's COMMIT switches a SERIALIZABLE transaction to a new snapshot.** False. The transaction-level snapshot is held until the current transaction ends.

## 20. Process for Choosing an Isolation Level

Before choosing an isolation level for a business operation, answer:

1. Can each SELECT see the latest COMMITted state at its execution time?
2. Do multiple SELECTs in the same transaction need the exact same snapshot?
3. Does the transaction need to execute DML?
4. If DML is used, will write conflicts occur frequently?
5. Can the application ROLLBACK and retry the entire transaction?
6. Is the transaction long and reading large volumes of data?
7. Are there external side effects outside the database before COMMIT?
8. Can invariants be protected with constraints or conditional UPDATEs?
9. Is `SELECT FOR UPDATE` needed to lock specific rows?
10. Is there sufficient UNDO for the expected snapshot duration?

Suggestions:

| Need | Typically Suitable Choice |
| --- | --- |
| Standard OLTP, each statement reads fresh snapshot | READ COMMITTED |
| Multiple reads needing one snapshot, no writes | READ ONLY |
| Multiple reads needing one snapshot while transaction also writes | SERIALIZABLE, with ORA-08177 handling |
| Read a row then lock for update | READ COMMITTED or SERIALIZABLE combined with `SELECT FOR UPDATE` where appropriate |
| Protect non-negative balances | CHECK constraint and conditional UPDATE; isolation added by design |
| Long multi-table report needing one logical timestamp | READ ONLY or reporting snapshot/replica, with UNDO sizing |

Do not choose an isolation level just because its name sounds stronger. Choose based on read semantics, write needs, retryability, transaction duration, and actual workload.

## 21. Practice Exercises

1. Explain the difference between a statement-level snapshot and a transaction-level snapshot.
2. Under READ COMMITTED, can two SELECTs in the same transaction return different values? Describe a two-session timeline.
3. Why does a running SELECT keep seeing the old snapshot even if another session COMMITs while the query is executing?
4. Write a scenario proving Session B cannot read Session A's uncommitted UPDATE.
5. Write a READ COMMITTED scenario showing B sees changes after A's COMMIT.
6. Write the same scenario using SERIALIZABLE and explain why B's second SELECT still sees the old value.
7. How are READ ONLY and SERIALIZABLE alike?
8. Why can READ ONLY not replace SERIALIZABLE for a transaction needing UPDATE?
9. Why can SERIALIZABLE not replace READ ONLY if the goal is enforcing a read-only transaction?
10. A report has four SELECTs needing to reconcile figures at one exact moment. Why is READ ONLY suitable?
11. If another session INSERTs a new row and COMMITs between two SELECTs in READ ONLY, does the second query see the new row?
12. In what contention scenario does ORA-08177 occur?
13. After ORA-08177, why is it necessary to ROLLBACK and retry the entire unit of work?
14. Why must a retry recompute decisions from the fresh snapshot?
15. Why must you not send a confirmation email before a SERIALIZABLE transaction COMMITs successfully?
16. How does `Connection.setReadOnly(true)` differ from `SET TRANSACTION READ ONLY`?
17. In JDBC, must `autoCommit` and isolation be configured before or after the first statement?
18. Is Spring `@Transactional(readOnly = true)` equivalent by default to Oracle's `READ ONLY` command?
19. When might a SERIALIZABLE transaction need `SELECT FOR UPDATE`?
20. Why is `SELECT FOR UPDATE` unsuitable for a READ ONLY transaction?
21. How is ORA-01555 related to transaction-level snapshots and UNDO?
22. How can DDL mid-transaction affect snapshots and rollbacks?
23. An application uses SERIALIZABLE without a unique constraint on a business key. Does isolation replace the constraint?
24. Design a two-session test comparing READ COMMITTED, SERIALIZABLE, and READ ONLY.
25. A READ ONLY transaction runs for hours. Which operational risks must a DBA evaluate?

**READ COMMITTED creates a snapshot per statement; SERIALIZABLE and READ ONLY hold a snapshot at the transaction level.** SERIALIZABLE permits writes, yet requires handling conflicts via ROLLBACK and retry when encountering ORA-08177. READ ONLY permits only reads and suits multi-SELECT reports requiring a single logical point in time. Choosing the right mode, keeping transactions short, protecting invariants with constraints, and managing UNDO allow multiple sessions to run concurrently while preserving data consistency.
