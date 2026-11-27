# Autocommit and Transaction Boundaries in PostgreSQL Tools and Applications

When you run two consecutive `UPDATE` statements in a SQL tool, they may be committed **one statement at a time**. However, when a Java application calls `connection.setAutoCommit(false)` and executes those exact same two statements on **one connection**, the results are only committed when the application calls `commit()`. If either statement fails, the application can call `rollback()` to discard the entire group.

This difference determines the correctness of many business operations. Consider transferring 100 currency units from account A to account B:

~~~text
Step 1: A = A - 100
Step 2: B = B + 100

Desired outcome:
  Success -> BOTH steps are recorded.
  Failure -> NEITHER step is recorded.
~~~

If Step 1 commits on its own and the connection drops before Step 2, the total balance across the two accounts becomes wrong. If both run inside the **same transaction**, PostgreSQL protects the atomicity of the data changes.

This lesson focuses on **autocommit and transaction boundaries** in PostgreSQL: standalone statements, `BEGIN`/`COMMIT`/`ROLLBACK`, two separate sessions, how statements execute in `psql` and GUI tools, JDBC, connection pools, Spring, Python, and Node.js. Later sections explain errors that put a transaction into the aborted state, savepoints, DDL, locking, isolation, network failures during commit, and how to detect `idle in transaction`.

## 1. Distinguishing Statement, Transaction, Connection, and Session

| Concept | Meaning |
| --- | --- |
| **Statement** | A single SQL command such as `UPDATE ...` or `SELECT ...` |
| **Transaction** | A unit of work that PostgreSQL commits or rolls back |
| **Connection/session** | A connection to PostgreSQL, which carries its own transaction state |
| **Autocommit** | Client/driver policy for finalizing transactions for standalone statements |
| **Connection pool** | Mechanism from which applications borrow and return connections; it does not automatically merge multiple connections into one transaction |

A normal PostgreSQL transaction is bound to **a single connection**. Opening a transaction on Connection A does not mean Connection B participates in that transaction.

~~~text
Connection A
    BEGIN
      UPDATE row X
      INSERT audit
    COMMIT

Connection B
    SELECT ...
    -- Different transaction; does not automatically belong to A's BEGIN.
~~~

A single connection can execute many transactions **sequentially** over its lifetime. A transaction is not synonymous with a connection session.

### 1.1. Explicit Transaction Boundaries

~~~sql
BEGIN;

UPDATE some_table SET ... WHERE ...;
INSERT INTO audit_log (...) VALUES (...);

COMMIT;
~~~

If the work should not be saved:

~~~sql
ROLLBACK;
~~~

Diagram:

~~~text
                 BEGIN
                   |
           +-------v--------+
           | SQL 1          |
           | SQL 2          |
           | SQL 3          |
           +-------+--------+
                   |
            +------+------+
            |             |
          COMMIT        ROLLBACK
            |             |
      Save changes   Discard uncommitted
      of transaction      changes
~~~

### 1.2. Transactions and ACID

**Atomicity** is the main focus here: transactional changes inside a transaction are either committed together or rolled back together. Additionally, **Consistency** ties to constraints and data rules, **Isolation** controls how concurrent transactions affect one another, and **Durability** relates to how PostgreSQL protects committed outcomes according to system configuration.

Transaction atomicity **does not replace** business validation: an `UPDATE` that succeeds yet affects **0 rows** can still leave a business operation missing a critical step.

## 2. What Does Autocommit Actually Mean?

In many clients, **autocommit enabled** means SQL statements executed **individually outside an explicit transaction** are committed as soon as each statement completes successfully.

~~~text
AUTOCOMMIT ON, three separate statements:

UPDATE A;      -> transaction #1 -> COMMIT
UPDATE B;      -> transaction #2 -> COMMIT
INSERT audit;  -> transaction #3 -> COMMIT
~~~

When all three operations must belong to the same unit:

~~~text
BEGIN
  UPDATE A
  UPDATE B
  INSERT audit
COMMIT or ROLLBACK
~~~

### 2.1. One Statement Can Modify Multiple Rows

~~~sql
UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id IN (1, 2, 3);
~~~

Even without writing `BEGIN`, PostgreSQL still executes that `UPDATE` within **an implicit transaction** if it runs as a standalone statement. It does not create a separate transaction for each modified row.

The core distinction is **one statement affecting 3 rows** versus **3 separate statements**.

### 2.2. Autocommit Is Not a Universal SQL Server Setting

Do not use the following syntax as a general way to disable autocommit in PostgreSQL:

~~~sql
-- Not a universal PostgreSQL command to control autocommit:
SET autocommit = off;
~~~

The mode is controlled by the client tool or driver:

| Tool/Library | Common Management Mechanism |
| --- | --- |
| `psql` | Client variable `\set AUTOCOMMIT on/off` |
| JDBC | `Connection.setAutoCommit(true/false)` |
| GUI tools | Auto-commit or Manual commit button/option |
| Spring | Transaction manager and `@Transactional` |
| Python psycopg 3 | Autocommit attribute and transaction context |
| Node.js `pg` | `BEGIN`/`COMMIT` on the same client |

Changing the mode in one tool **does not automatically change the mode in any other tool**.

### 2.3. Autocommit ON Still Allows BEGIN

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;
COMMIT;
~~~

This is still **one explicit transaction**, provided those commands are sent to the exact same session and the tool does not alter boundaries otherwise. Having autocommit enabled does not force PostgreSQL to commit between statements inside a valid `BEGIN ... COMMIT` block.

## 3. Preparing Lab Data

Run these commands only on a **lab database**. The tables and balances in this lesson are dummy data for learning transactions, not a production payment model.

### 3.1. Creating the Schema and Two Tables

~~~sql
CREATE SCHEMA tx_lab;

CREATE TABLE tx_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14, 2) NOT NULL CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tx_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account integer NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    to_account integer NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_account <> to_account)
);
~~~

`numeric(14,2)` is suitable for illustrating decimal addition/subtraction; `CHECK (balance >= 0)` prevents storing negative balances. A real financial system also requires a ledger, concurrency rules, idempotency, and reconciliation.

### 3.2. Loading Data

~~~sql
INSERT INTO tx_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (1, 'Lan', 1000.00),
    (2, 'Minh', 500.00),
    (3, 'Chi', 200.00);

SELECT account_id, owner_name, balance
FROM tx_lab.accounts
ORDER BY account_id;
~~~

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | Lan | 1000.00 |
| 2 | Minh | 500.00 |
| 3 | Chi | 200.00 |

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

The initial total is **1700.00**. When transferring money **only between these lab accounts**, this total must remain unchanged.

> Examples with `ROLLBACK` are designed not to persist changes. If you intentionally commit an experiment, subsequent balances will differ from the initial dataset.

## 4. When Two UPDATEs Auto-Commit Independently

Suppose an application sends these two statements **separately** in autocommit mode:

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;
~~~

Dangerous scenario:

~~~text
UPDATE account 1 -> COMMIT succeeds
                  |
           connection lost
                  |
UPDATE account 2 -> never executed
~~~

If the application loses its connection between the two statements, Lan's account has already been debited 100 while Minh has not been credited. This is a **transaction boundary bug**.

Do not try to solve this by unconditionally "retrying both statements": the debit may have **already committed**, and retrying would debit a second time.

### 4.1. Wrapping the Whole Business Operation in a Transaction

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100,
    updated_at = now()
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100,
    updated_at = now()
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 100);

ROLLBACK;
~~~

While the transaction is open, that same connection reads Lan at **900.00**, Minh at **600.00**, and a new transfer record. After `ROLLBACK`, all three transactional changes are discarded.

To persist them, replace `ROLLBACK` with `COMMIT` **only after every business condition has been verified**.

### 4.2. The "0 Rows Updated" Problem

~~~sql
UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 999;
~~~

If account 999 does not exist, the statement succeeds syntactically yet **modifies zero rows**. The transaction does not automatically know this is a business failure.

The application must check:

- Does the source account exist?
- Is the balance sufficient?
- Does the destination account exist?
- Did each statement affect the expected number of rows?
- Did the audit/ledger insert succeed?
- Is duplicate/idempotency handling required?

Only **COMMIT** when all conditions are satisfied.

## 5. BEGIN, COMMIT, and ROLLBACK

### 5.1. BEGIN or START TRANSACTION

~~~sql
BEGIN;
~~~

or:

~~~sql
START TRANSACTION;
~~~

Both open a transaction block under standard PostgreSQL semantics.

### 5.2. COMMIT

~~~sql
COMMIT;
~~~

Instructs PostgreSQL to end the transaction and persist its transactional changes if valid. **A successful commit** is different from "an `UPDATE` statement returned success."

### 5.3. ROLLBACK

~~~sql
ROLLBACK;
~~~

Discards the current transaction's uncommitted changes. Once `COMMIT` has succeeded, calling `ROLLBACK` in a new transaction **does not undo the earlier commit**.

### 5.4. Safe Test Transaction Pattern

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = 777
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Inside the transaction you see `777.00`, and after rollback you see `200.00` again assuming no other committed changes occurred.

## 6. Two Sessions: Are Uncommitted Changes Visible?

Open **two independent PostgreSQL connections**. Call them Session A and Session B.

### Session A

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = 777
WHERE account_id = 3;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Session A sees **777.00**. **Do not commit yet.**

### Session B

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Under standard `READ COMMITTED`, Session B still sees **200.00** because A's change is uncommitted.

### Session A

~~~sql
ROLLBACK;
~~~

After rollback, both connections see the committed value from before the experiment.

### Trying a Real COMMIT

In Session A, you can test:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 777 WHERE account_id = 3;
COMMIT;
~~~

After A commits, a new `SELECT` in B under `READ COMMITTED` can see **777.00**. In the lab only, restore the data to its previous state:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 200 WHERE account_id = 3;
COMMIT;
~~~

**Never edit production balances to "reset" them with manual UPDATEs.** This is strictly a synthetic schema experiment.

## 7. Autocommit Is Distinct from Isolation Level

Two independent questions:

1. **Transaction boundaries:** which statements commit or roll back together?
2. **Isolation:** under what rules does a transaction see data from other transactions and handle concurrency?

PostgreSQL normally defaults to `READ COMMITTED`. At this level, a `SELECT` statement sees a snapshot as of the start of that statement. Therefore:

~~~text
Session B: SELECT -> balance = 200
Session A: COMMIT balance = 777
Session B: SELECT -> balance = 777
~~~

Session B's two `SELECT` statements **can** see different values even inside the **same `BEGIN ISOLATION LEVEL READ COMMITTED`** block, because the read snapshot is chosen per statement.

### 7.1. REPEATABLE READ

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
-- Another session can COMMIT a change here.
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
COMMIT;
~~~

In PostgreSQL's `REPEATABLE READ`, normal read queries use a stable transaction snapshot, unlike `READ COMMITTED`. Higher isolation can also produce concurrency errors during write operations. **`BEGIN` does not implicitly mean `REPEATABLE READ`.**

### 7.2. Isolation Does Not Replace Atomicity

Even if you raise the isolation level, if two `UPDATE` statements belong to **two separate transactions** due to autocommit, they can still commit independently. Raising isolation does not replace grouping business operations within the same transaction boundary.

## 8. psql: The Client AUTOCOMMIT Variable

`psql` usually enables autocommit by default: standalone statements outside `BEGIN` are finalized as soon as they succeed.

Inspect/set the psql variable:

~~~text
\echo :AUTOCOMMIT
\set AUTOCOMMIT on
\set AUTOCOMMIT off
~~~

These are **psql meta-commands**, not SQL statements sent over JDBC. Do not place them inside a normal SQL statement.

### 8.1. AUTOCOMMIT on

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
~~~

When executed standalone, psql does not keep a transaction open waiting for you to type `COMMIT`. If you need multiple statements together:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;
COMMIT;
~~~

### 8.2. AUTOCOMMIT off

~~~text
\set AUTOCOMMIT off
~~~

In this mode, psql automatically opens a transaction before eligible SQL statements when no transaction block is active, then waits for an explicit **`COMMIT` or `ROLLBACK`**.

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;

SELECT account_id, updated_at
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

The two statements before `ROLLBACK` belong to the same transaction under this client mode.

### 8.3. Switching Back to on Does Not Discard an Open Transaction

~~~text
\set AUTOCOMMIT on
~~~

Do not use this as a substitute for `COMMIT` or `ROLLBACK` on an open transaction. Explicitly end the transaction before switching modes to avoid state confusion.

### 8.4. The psql Prompt

With the default prompt, you may see:

~~~text
labdb=>   ready for a command
labdb=*>  inside an active transaction block
labdb=!>  transaction is in an aborted/error state
~~~

Prompts can be customized, so treat this as a **helpful indicator**, not the sole verification API.

## 9. Failed Transactions and SQLSTATE 25P02

Deliberately triggering an error:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 1;

-- Violates CHECK (balance >= 0).
SELECT * FROM tx_lab.accounts;
~~~

After the CHECK violation, the transaction enters the **aborted** state. The subsequent `SELECT` is rejected with a message like:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
~~~

SQLSTATE **`25P02`** indicates the transaction has already failed; it is **not the root cause**. The root cause in this example is the `CHECK` violation.

Proper recovery:

~~~sql
ROLLBACK;
~~~

You cannot simply fix the `UPDATE` and keep going once a transaction is aborted; PostgreSQL still requires resetting the transaction state.

### 9.1. Key SQLSTATE Codes

| SQLSTATE | Situation |
| --- | --- |
| `23505` | UNIQUE violation |
| `23503` | FOREIGN KEY violation |
| `23514` | CHECK violation |
| `25P02` | Transaction already in failed state |
| `40P01` | Deadlock |
| `40001` | Serialization failure |

Errors can also surface **at `COMMIT`** when deferrable constraints are used, even if all preceding DML statements returned success.

## 10. SAVEPOINT: Partial Recovery Within a Transaction

`SAVEPOINT` marks a position so you can roll back part of a transaction without necessarily discarding earlier work.

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 1;

SAVEPOINT before_optional_step;

UPDATE tx_lab.accounts
SET balance = -100
WHERE account_id = 2;

-- CHECK error; transaction needs recovery.
ROLLBACK TO SAVEPOINT before_optional_step;

UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 3;

ROLLBACK; -- Discard everything to leave the lab clean.
~~~

`ROLLBACK TO SAVEPOINT` undoes operations after the savepoint and lets the transaction continue in a valid state.

### 10.1. RELEASE SAVEPOINT Is Not COMMIT

~~~sql
BEGIN;
SAVEPOINT mark1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
RELEASE SAVEPOINT mark1;
ROLLBACK;
~~~

`RELEASE SAVEPOINT` destroys the savepoint marker; it does not commit the outer transaction. Because `ROLLBACK` runs at the end, the `UPDATE` is still discarded.

### 10.2. Nested BEGIN Does Not Create Two Independent Transactions

~~~sql
BEGIN;
BEGIN;
~~~

does not create an independent nested transaction that can commit on its own. PostgreSQL supports savepoints for partial rollback. Frameworks may simulate "nested" transactions using savepoints, yet you must still understand the enclosing outer transaction.

## 11. Running SQL Files with psql

Suppose `changes.sql` contains multiple statements:

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;

UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;

UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 3;
~~~

When running `psql -f changes.sql` with default autocommit, each standalone statement may commit sequentially. If the third statement fails, the first two may already be saved.

### 11.1. ON_ERROR_STOP Does Not Create a Transaction

~~~text
psql -X -v ON_ERROR_STOP=1 -d lab_db -f changes.sql
~~~

`ON_ERROR_STOP` tells `psql` to stop reading the script upon encountering an error; it does not turn individually committed statements into an atomic block.

### 11.2. --single-transaction

~~~text
psql -X -v ON_ERROR_STOP=1 --single-transaction -d lab_db -f changes.sql
~~~

The `-1` or `--single-transaction` option tells `psql` to wrap the file or eligible command sections in a single transaction. Combining it with `ON_ERROR_STOP=1` makes the script halt and roll back on error instead of leaving earlier steps independently committed.

**Condition:** the script must not break boundaries with conflicting `COMMIT`/`ROLLBACK` commands and must not contain statements **forbidden inside a transaction block**.

### 11.3. Watch How Clients Send Multiple SQL Statements

Multiple statements sent in **a single protocol query message** can have different implicit transaction semantics than sending **each statement as a separate message**. Therefore, do not assume from the number of semicolons in a file or `-c` string that transaction boundaries behave identically.

When business atomicity is required, use explicit `BEGIN ... COMMIT` or a well-defined transaction option suited to the tool.

## 12. Transactions in GUI Tools

Tools such as pgAdmin, DBeaver, or other SQL editors usually provide **Auto-commit** and **Manual commit** options, though exact behavior depends on version, connection settings, and Execute Statement vs. Execute Script modes.

Verification steps before touching real data:

1. Verify which **connection/database** is active.
2. Check whether the tool is in autocommit or manual commit mode.
3. Run `BEGIN; UPDATE ...; SELECT ...;` on a lab table.
4. Query the same row from **another connection**.
5. Run `ROLLBACK;` on the original connection.
6. Confirm the balance returned to its prior value.

### 12.1. Opening Multiple Tabs Does Not Mean Sharing a Transaction

Two tabs may use different connections. Clicking Commit in one tab does not guarantee committing an open transaction in another tab.

### 12.2. Never Click Commit Just to Dismiss a Warning

If a GUI warns about "uncommitted changes," verify which commands were run and whether the data meets all conditions. `COMMIT` is a business decision, not a dialog-dismissal button.

### 12.3. Closing a Connection Before Committing

When a PostgreSQL connection actually terminates, an uncommitted transaction does not become committed. Still, do not rely on closing tabs as a rollback strategy; the tool may keep connections alive in an internal pool or session. Issue `ROLLBACK` explicitly.

## 13. JDBC: Autocommit on Connection

By the JDBC specification, new connections usually start with **autocommit true**. However, a pool or framework may hand the application a connection configured under its own policy.

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());
}
~~~

To group multiple statements:

~~~java
connection.setAutoCommit(false);

try {
    // SQL 1, SQL 2, SQL 3 on the same connection.
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

In production code, handle rollback errors as well and ensure the connection is returned to the pool. Do not arbitrarily mix `setAutoCommit(false)` with raw SQL `BEGIN`/`COMMIT` managed by another framework.

### 13.1. JDBC Transfer with Row-Count Checks

Example using Java 15+ text blocks and a configured `DataSource`:

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(int from, int to, BigDecimal amount)
            throws SQLException {
        if (from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection conn = dataSource.getConnection()) {
            boolean oldAutoCommit = conn.getAutoCommit();
            conn.setAutoCommit(false);
            try {
                String debitSql = """
                    UPDATE tx_lab.accounts
                    SET balance = balance - ?, updated_at = now()
                    WHERE account_id = ? AND balance >= ?
                    """;

                try (PreparedStatement debit =
                         conn.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setInt(2, from);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new SQLException("No eligible source account");
                    }
                }

                String creditSql = """
                    UPDATE tx_lab.accounts
                    SET balance = balance + ?, updated_at = now()
                    WHERE account_id = ?
                    """;

                try (PreparedStatement credit =
                         conn.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setInt(2, to);
                    if (credit.executeUpdate() != 1) {
                        throw new SQLException("Destination not found");
                    }
                }

                String insertSql = """
                    INSERT INTO tx_lab.transfers
                        (from_account, to_account, amount)
                    VALUES (?, ?, ?)
                    """;

                try (PreparedStatement audit =
                         conn.prepareStatement(insertSql)) {
                    audit.setInt(1, from);
                    audit.setInt(2, to);
                    audit.setBigDecimal(3, amount);
                    audit.executeUpdate();
                }

                conn.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                if (!conn.isClosed()) {
                    conn.setAutoCommit(oldAutoCommit);
                }
            }
        }
    }
}
~~~

Here:

- Every `PreparedStatement` uses the **same `conn`**.
- `setAutoCommit(false)` runs before any write statements.
- The debit enforces `balance >= amount` **inside the UPDATE**.
- The application verifies affected row counts for both debit and credit.
- Commit runs only after both updates and the audit insert succeed.
- On exception, the code attempts rollback and rethrows the error.

**This is a teaching example, not a production banking system.** Real systems also need idempotency keys, an immutable ledger, locking/lock-ordering, bounded retries, reconciliation, and handling of uncertain commit outcomes.

### 13.2. Be Careful When Re-Enabling autoCommit

Under JDBC semantics, switching `autoCommit=false` to `true` **while a transaction is active** can commit that transaction. Never use `setAutoCommit(true)` as a way to "discard changes." Always commit or roll back **before restoring connection state**.

In the example, `finally` attempts to restore the previous mode. In production systems, cleanup can also throw an exception; manage secondary errors so they do not mask the root error, and follow the contract of your connection pool.

### 13.3. Errors at Commit Time

If a transaction involves deferrable constraints, errors can surface at `conn.commit()`. Do not catch exceptions only around `executeUpdate()` and assume success. A connection failure right when sending `COMMIT` can also leave the application **uncertain whether the commit succeeded or not**.

## 14. Connection Pools: Borrowing One Connection for One Transaction

~~~text
HTTP request
    |
Service method
    |
borrow connection
    |
begin / autoCommit(false)
    |
UPDATE + UPDATE + INSERT
    |
COMMIT or ROLLBACK
    |
return connection to pool
~~~

Incorrect design:

~~~java
debitRepository.debit(from, amount);    // connection A
creditRepository.credit(to, amount);   // connection B
auditRepository.record(from, to, amount); // connection C
~~~

If each helper opens its own connection in autocommit mode without a coordinating transaction manager, these three commands can run as **three separate transactions**.

Two sound approaches:

1. Manual JDBC: pass the **same connection** across repositories/helpers.
2. Transaction manager/framework: ensure operations bind to the **same transaction and DataSource** via the framework's mechanism.

**Never return a connection to the pool without explicitly committing or rolling back.** Abandoned transactions can hold locks and snapshots, stalling other requests. Do not rely solely on pool auto-cleanup.

## 15. Spring @Transactional

In Spring with a properly configured transaction manager, `@Transactional` typically defines the **boundary of a business method**:

~~~java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int from, int to, BigDecimal amount) {
        if (from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update("""
            UPDATE tx_lab.accounts
            SET balance = balance - ?
            WHERE account_id = ? AND balance >= ?
            """, amount, from, amount);
        if (debited != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int credited = jdbc.update("""
            UPDATE tx_lab.accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """, amount, to);
        if (credited != 1) {
            throw new IllegalStateException("Destination missing");
        }

        jdbc.update("""
            INSERT INTO tx_lab.transfers
                (from_account, to_account, amount)
            VALUES (?, ?, ?)
            """, from, to, amount);
    }
}
~~~

With Spring transaction infrastructure properly configured, calling the method through the appropriate interception mechanism runs it within one transaction: committing on completion or rolling back when an exception matches the rollback rules.

### 15.1. Common Pitfalls

- **Self-invocation:** calling another `@Transactional` method inside the same object may bypass the proxy in standard Spring proxy mode.
- **Wrong transaction manager/DataSource:** operations hitting a different DataSource may not participate in the managed transaction.
- **Swallowing exceptions:** if code catches an error and returns normally, the transaction manager may treat the method as successful and try to commit.
- **Checked exceptions:** default rules normally roll back on `RuntimeException`/`Error`, not checked exceptions unless configured otherwise.

Example declaring a broader policy:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importBatch() throws Exception {
    // ...
}
~~~

### 15.2. REQUIRED and REQUIRES_NEW

| Propagation | High-Level Meaning |
| --- | --- |
| `REQUIRED` | Join the existing transaction or create a new one if none exists |
| `REQUIRES_NEW` | Start a new independent transaction, potentially suspending the outer transaction |

If an audit step uses `REQUIRES_NEW`, the audit entry can **commit separately** even if the outer business transaction rolls back. This may be intentional by design, though it is **no longer part of the same unit of atomicity**.

### 15.3. JPA Flush Is Not Commit

An ORM/JPA provider can send SQL during `flush()` before the transaction ends. Other sessions still cannot see the data, and a later error can roll it back. Distinguish **entity state**, **SQL flush**, and **PostgreSQL commit**.

## 16. Node.js with pg

With Node.js `pg`, you must borrow **one client** and use it for the entire transaction:

~~~javascript
const client = await pool.connect();

try {
  await client.query("BEGIN");

  const debit = await client.query(
    "UPDATE tx_lab.accounts " +
    "SET balance = balance - $1 " +
    "WHERE account_id = $2 AND balance >= $1",
    [100, 1]
  );
  if (debit.rowCount !== 1) {
    throw new Error("Debit failed");
  }

  const credit = await client.query(
    "UPDATE tx_lab.accounts " +
    "SET balance = balance + $1 WHERE account_id = $2",
    [100, 2]
  );
  if (credit.rowCount !== 1) {
    throw new Error("Credit failed");
  }

  await client.query(
    "INSERT INTO tx_lab.transfers " +
    "(from_account, to_account, amount) VALUES ($1, $2, $3)",
    [1, 2, 100]
  );

  await client.query("COMMIT");
} catch (error) {
  try {
    await client.query("ROLLBACK");
  } catch (rollbackError) {
    // Log cleanup error; the connection may no longer be reusable.
  }
  throw error;
} finally {
  client.release();
}
~~~

Do not do this:

~~~javascript
// Wrong pattern if you want a shared transaction:
await pool.query("BEGIN");
await pool.query("UPDATE ...");
await pool.query("COMMIT");
~~~

Each `pool.query` call can check out a different connection. You cannot rely on it to stay inside the same transaction.

## 17. Python psycopg 3

**psycopg 3** defaults to `autocommit=False`, unlike JDBC's default. Even a `SELECT` can start a transaction and leave the session open if the application does not commit or roll back.

~~~python
import psycopg

dsn = "postgresql://app_user:secret@localhost:5432/lab_db"

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tx_lab.accounts " +
            "SET updated_at = now() WHERE account_id = %s",
            (1,),
        )
    # Normal exit from connection context: commits.
    # On exception: rolls back via context manager semantics.
~~~

Example opening an explicit transaction block on an autocommit connection:

~~~python
with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tx_lab.accounts "
                "SET updated_at = now() WHERE account_id = %s",
                (1,),
            )
~~~

When a transaction is already open, nested transaction blocks may use savepoints depending on library state/semantics. Do not assume every `conn.transaction()` context always creates an independent top-level database transaction.

### Quick Comparison Across Environments

| Environment | Key Point to Remember |
| --- | --- |
| psql | AUTOCOMMIT is usually on |
| JDBC | Connections by JDBC spec usually start with autocommit true |
| psycopg 3 | Connections default to autocommit false |
| Node pg | Explicit transactions require borrowing a single client |
| Spring | Transaction manager, proxy, propagation, and exception policy govern behavior |

**Never copy autocommit assumptions blindly across languages.**

## 18. SELECT FOR UPDATE Needs an Open Transaction

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Verify conditions and update on the same connection.
UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 1;

COMMIT;
~~~

`SELECT FOR UPDATE` locks rows to coordinate concurrency. The lock is held until the end of the transaction.

### If Each Statement Autocommits

~~~text
SELECT ... FOR UPDATE;  -> transaction ends, lock is released
Application computes
UPDATE ...;             -> new transaction
~~~

In this case, the `SELECT`'s lock no longer protects the subsequent `UPDATE` step. Place the entire sequence inside one transaction whenever locks must span multiple statements.

### 18.1. Not Every Operation Needs a Separate SELECT FOR UPDATE

A conditional update:

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
~~~

also uses PostgreSQL's locking/update mechanism and can often enforce the balance check directly within the statement. Evaluate real workloads, isolation levels, and competing operations rather than adding overly broad locks.

### 18.2. Reducing Deadlocks with Lock Ordering

If Transaction A locks account 1 then 2 while B locks 2 then 1, a deadlock can occur. You generally need a consistent **lock acquisition order**, such as ascending ID order, plus proper handling/retries for aborted transactions.

## 19. DDL Inside Transactions

PostgreSQL supports rolling back many schema changes:

~~~sql
BEGIN;

CREATE TABLE tx_lab.temporary_demo (
    id integer PRIMARY KEY
);

INSERT INTO tx_lab.temporary_demo(id)
VALUES (1);

ROLLBACK;
~~~

After rollback, `temporary_demo` does not exist if it did not exist beforehand. However, **not every PostgreSQL command can run inside a transaction block**.

Examples:

~~~sql
-- Commands with transaction block restrictions:
CREATE DATABASE some_database;
VACUUM tx_lab.accounts;
CREATE INDEX CONCURRENTLY idx_accounts_owner
    ON tx_lab.accounts(owner_name);
~~~

`CREATE INDEX CONCURRENTLY` avoids certain write blocks compared to a standard index build, yet **cannot run inside a normal transaction block**. Migration tools that wrap an entire script in a transaction can cause this command to fail.

### 19.1. TRUNCATE Also Requires Caution

PostgreSQL can roll back `TRUNCATE` inside an appropriate transaction, yet it acquires strong locks and has different visibility characteristics than `DELETE`. Never treat "can be rolled back" as an excuse to run `TRUNCATE` casually in production.

### 19.2. Migration Boundaries

Before deploying a migration, verify:

1. Does the tool automatically open a transaction around each file?
2. If the fifth statement fails, did the first four already commit?
3. Does the script contain its own `COMMIT`/`ROLLBACK`?
4. Are there commands that must run outside a transaction block?
5. Can it be safely re-run if interrupted mid-way?

## 20. What Does Not Roll Back Like Table Data?

The atomicity of a PostgreSQL transaction does not cover every external or non-transactional side effect.

### 20.1. Sequences and Identity Columns Can Have Gaps

In `tx_lab.transfers`, `transfer_id` uses identity/sequence generation.

~~~sql
BEGIN;

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 1)
RETURNING transfer_id;

ROLLBACK;
~~~

The inserted row is rolled back, but the sequence number already allocated **does not roll back like table rows**. Therefore, IDs can have gaps. Never treat gap-free ID sequences as an invariant enforced by transactions.

### 20.2. Email, HTTP, Filesystem

~~~text
BEGIN
  UPDATE orders SET status='PAID'
  Send "payment succeeded" email -> already sent!
  INSERT audit -> fails
ROLLBACK
~~~

A PostgreSQL rollback **does not recall emails**, undo completed HTTP requests, or revert files written outside the database.

A common pattern is the **transactional outbox**:

~~~text
BEGIN
  UPDATE business data
  INSERT outbox event row
COMMIT
        |
        v
  Worker sends email/message
  and retries idempotently
~~~

### 20.3. Uncertain Commit Outcome on Connection Loss

If the application sends `COMMIT` and loses the network before receiving a response, two cases are possible:

1. The server had not processed the commit yet; the transaction rolled back when the connection terminated.
2. The server committed successfully, but the response never reached the application.

The application cannot reliably distinguish these from a network exception alone. For monetary or non-idempotent operations, use **unique request IDs, status tables, lookups, and reconciliation** instead of blindly retrying a debit.

## 21. Detecting Idle in Transaction

A session with an open transaction that is not currently running SQL enters the **`idle in transaction`** state. Prolonged time in this state can:

- Hold locks, blocking other sessions.
- Hold back the snapshot/transaction horizon, hurting VACUUM and causing bloat.
- Tie up pool connections.
- Produce hard-to-diagnose behavior from abandoned transactions.

### 21.1. Inspecting pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
~~~

Privileges to read details of other users' sessions may be restricted. `xact_start` and transaction duration help pinpoint sessions needing investigation.

### 21.2. Appropriate Timeouts

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

In a lab environment or where operational policy permits:

~~~sql
SET idle_in_transaction_session_timeout = '30s';
~~~

This parameter terminates sessions that stay idle inside a transaction for too long. **Do not apply a 30-second default blindly to every production workload**; timeouts can kill legitimate active workflows and applications must handle the disconnection.

| Parameter | Target |
| --- | --- |
| `statement_timeout` | Bounds statement execution duration |
| `lock_timeout` | Bounds lock wait duration |
| `idle_in_transaction_session_timeout` | Bounds idle duration while inside a transaction |

Timeouts are a secondary safety net, **not a replacement** for proper commit/rollback in application code.

## 22. Keeping Transactions Short and Properly Scoped

Problematic pattern:

~~~text
BEGIN
  UPDATE DB
  external HTTP call (takes 20 seconds)
  render file (takes 15 seconds)
  send email
  UPDATE DB
COMMIT
~~~

The transaction holds resources while waiting on external side effects, and those side effects do not roll back with the DB anyway.

Better organization:

1. Validate and prepare data before opening the transaction whenever possible.
2. Open the transaction right before the DB operations requiring atomicity.
3. Write business data and outbox rows in the same transaction.
4. Commit or roll back as soon as practical.
5. Execute email, messaging, file rendering, and HTTP calls outside the transaction via reliable, idempotent delivery.

**A longer transaction does not make a business workflow safer just because it packs more steps inside.**

## 23. Boundaries for Application Scenarios

### 23.1. Placing an Order

~~~text
BEGIN
  Check and reserve inventory with safe update/locking
  INSERT orders
  INSERT order_items
  INSERT outbox "OrderCreated"
COMMIT
~~~

PostgreSQL changes that belong together stay in one transaction; an outbox worker sends notifications after commit.

### 23.2. Updating Order Status

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 123
  AND status = 'PENDING';

-- Must verify exactly one row was updated.
INSERT INTO order_status_history (...) VALUES (...);

COMMIT;
~~~

This pattern illustrates the concept; these table/column names were not created in the lab. If `UPDATE` affects 0 rows, application logic must choose rollback/conflict/idempotency rather than blindly inserting a success audit row.

### 23.3. Batch Import

A 100,000-row batch in one transaction means **either the entire batch commits or rolls back**. Splitting into 100 transactions of 1,000 rows enables checkpoint/resume, though if batch 73 fails, the first 72 batches have already committed.

Choose boundaries based on integrity requirements, lock/WAL cost, resumability, and expected user semantics.

### 23.4. Stored Procedures

In PostgreSQL, regular functions cannot issue `COMMIT`/`ROLLBACK` like a client. Procedures invoked via `CALL` can perform transaction control **in permitted contexts**, subject to call-stack and outer transaction-block restrictions. Never assume a procedure can always commit when invoked inside an application's `BEGIN`.

## 24. Common Mistakes

### Mistake 1. Disabling Autocommit and Forgetting Commit/Rollback

The connection keeps the transaction open, potentially holding locks and becoming `idle in transaction`. Every exit path from a function needs explicit cleanup.

### Mistake 2. Two Independent UPDATEs for One Business Operation

The first statement can commit before the second fails. Group them in one transaction and verify affected row counts.

### Mistake 3. BEGIN on Connection A, COMMIT on Connection B

Two connections have separate transaction states. You cannot commit A's transaction through B.

### Mistake 4. Seeing Your Own Changes and Assuming They Are Committed

A session can read its own uncommitted changes. Use a separate session to verify external visibility.

### Mistake 5. Trying to Continue After a Transaction Is Aborted

After an error, `25P02` appears on subsequent statements until you roll back or revert to a valid savepoint.

### Mistake 6. Using setAutoCommit(true) to "Cancel"

In JDBC, switching from false to true while a transaction is active can commit it. Always roll back explicitly.

### Mistake 7. Calling pool.query for Each Statement in Node pg

The pool can hand out different connections. Use `pool.connect()` and keep one client until the end.

### Mistake 8. Assuming @Transactional Always Applies

Self-invocation, wrong transaction manager/DataSource, or swallowed exceptions can yield wrong boundaries.

### Mistake 9. Thinking JPA Flush Equals Commit

Flushed SQL is still uncommitted, and a later error can roll back the transaction.

### Mistake 10. Running SELECT FOR UPDATE as a Standalone Statement

The lock is released as soon as that statement auto-commits, leaving the subsequent UPDATE unprotected.

### Mistake 11. Script with ON_ERROR_STOP but No Transaction

Stopping early does not roll back earlier auto-committed statements. Use `-1` or explicit transaction boundaries where appropriate.

### Mistake 12. Putting Transaction-Forbidden Commands in a -1 Script

`CREATE DATABASE`, `VACUUM`, and `CREATE INDEX CONCURRENTLY` have transaction block restrictions.

### Mistake 13. Expecting Rollback to Undo Emails and Sequences

Rollback applies to transactional PostgreSQL table/row data; external side effects and sequences behave differently.

### Mistake 14. Blindly Retrying After a Network Error on COMMIT

The commit outcome may be unknown. Use idempotency keys and reconciliation.

### Mistake 15. Long Transactions Wrapping Network Calls

They hold locks and connections for extended periods, causing bloat and wait queues. Consider outbox and tight boundaries.

## 25. Hands-On Exercises

Run these in `tx_lab`. For exercises that intentionally alter balances, end with `ROLLBACK` to preserve sample data or reset the lab cleanly.

### Exercise 1. Autocommit

Explain why two `UPDATE` statements run separately in `psql` with AUTOCOMMIT on do not automatically form one transaction.

### Exercise 2. One Statement Modifying Multiple Rows

Does `UPDATE accounts SET updated_at=now() WHERE account_id IN (1,2)` create one transaction per row?

### Exercise 3. BEGIN/ROLLBACK

Write a transaction that changes account 3's balance to 777, reads it inside the transaction, and then rolls back. Predict the value after rollback.

### Exercise 4. Fund Transfer

Write two `UPDATE`s and one audit `INSERT` in the same transaction to transfer 100 from account 1 to 2. List the conditions to verify before committing.

### Exercise 5. Two Sessions

Session A has an uncommitted UPDATE. Does Session B under READ COMMITTED see the old or new value? When can B see the new value?

### Exercise 6. Isolation

Can two SELECTs in the same READ COMMITTED transaction return different results? What about REPEATABLE READ for normal snapshot reads?

### Exercise 7. psql Autocommit

Write the meta-commands to turn AUTOCOMMIT on/off and the SQL command used to abort a transaction.

### Exercise 8. Running a SQL File

Write the command to execute `changes.sql` via psql, halting on error and running the script in a single transaction if valid.

### Exercise 9. 25P02

Why is a SELECT rejected after an UPDATE violates a CHECK constraint in the same transaction? How do you continue?

### Exercise 10. SAVEPOINT

Write a transaction with a savepoint, intentionally violate `balance>=0`, roll back to the savepoint, perform a valid update, and then roll back the whole lab transaction.

### Exercise 11. JDBC

Which JDBC API disables autocommit? Why must all three PreparedStatements use the same Connection?

### Exercise 12. setAutoCommit(true)

Why shouldn't you use this instead of rollback when a transaction is still open?

### Exercise 13. Connection Pool

Why can three helpers sharing one DataSource still commit independently if each helper borrows its own connection?

### Exercise 14. Spring

Give two situations where `@Transactional` does not apply as expected. If code catches an error and returns success, what is the risk?

### Exercise 15. Node.js

Write the skeleton `pool.connect()` → `BEGIN` → SQL → `COMMIT`/`ROLLBACK` on a single client.

### Exercise 16. SELECT FOR UPDATE

Does the lock from SELECT FOR UPDATE stay held until the next UPDATE statement if each statement auto-commits?

### Exercise 17. Transactional DDL

Can CREATE TABLE be rolled back? Name at least two commands that cannot run inside a normal transaction block.

### Exercise 18. Sequences

Why can a `transfer_id` be skipped even when its INSERT rolled back?

### Exercise 19. Email and Outbox

Is an email sent inside a transaction automatically recalled on rollback? Propose an alternative design.

### Exercise 20. Idle in Transaction

Write a `pg_stat_activity` query to find sessions idle in transaction, showing transaction age. State two risks.

### Exercise 21. Uncertain Commit

An application sends COMMIT and loses the network; should it unconditionally retry the transfer?

### Exercise 22. Designing Boundaries

An API creates an order, reserves inventory, writes an audit record, and sends an email. Which steps belong in the same PostgreSQL transaction, and which should be separated post-commit?

## 26. Suggested Solutions

### Exercises 1–2

With autocommit on, standalone statements outside `BEGIN` are typically committed individually. However, a single `UPDATE` modifying multiple rows is still **one atomic statement**, not one commit per row.

### Exercise 3

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 777 WHERE account_id = 3;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
ROLLBACK;
~~~

After rollback, the balance returns to **200.00** assuming no other committed changes occurred.

### Exercise 4

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1 AND balance >= 100;
-- Must confirm 1 row updated.

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;
-- Must confirm 1 row updated.

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 100);

ROLLBACK; -- Experiment: do not persist lab balance changes.
~~~

In production, replace `ROLLBACK` with `COMMIT` **only if application code has verified both UPDATEs, the audit insert, and all business rules**. The raw SQL above does not check affected rows on its own.

### Exercises 5–6

Session B under READ COMMITTED does not see A's uncommitted change. After A commits, a new read statement can see it. Under READ COMMITTED, two SELECTs in the same transaction can also see different values; under REPEATABLE READ, normal read snapshots remain stable within the transaction.

### Exercise 7

~~~text
\set AUTOCOMMIT on
\set AUTOCOMMIT off
~~~

Abort the transaction with `ROLLBACK;`.

### Exercise 8

~~~text
psql -X -v ON_ERROR_STOP=1 -1 -d lab_db -f changes.sql
~~~

`ON_ERROR_STOP` stops the script on error; `-1` wraps the script in a transaction if the script/commands support it.

### Exercise 9

After a failing statement, the transaction is marked failed; `25P02` appears on subsequent commands. Use `ROLLBACK;` or `ROLLBACK TO SAVEPOINT` created before the error.

### Exercise 10

~~~sql
BEGIN;
SAVEPOINT before_bad;

UPDATE tx_lab.accounts SET balance=-1 WHERE account_id=1;
-- CHECK error.

ROLLBACK TO SAVEPOINT before_bad;
UPDATE tx_lab.accounts SET updated_at=now() WHERE account_id=2;
ROLLBACK;
~~~

### Exercises 11–13

JDBC `setAutoCommit(false)`, `commit()`, `rollback()`. All statements must share the same connection. Switching `autoCommit=false` to `true` while a transaction is active can commit, so **roll back first**. Three helpers borrowing three connections can run three independent transactions even when sharing one pool.

### Exercise 14

For example, self-invocation bypassing the proxy, or operating on a DataSource not managed by that transaction manager. If exceptions are swallowed, the framework may treat the method as successful and commit.

### Exercise 15

~~~javascript
const client = await pool.connect();
try {
  await client.query("BEGIN");
  await client.query(
    "UPDATE tx_lab.accounts SET updated_at=now() WHERE account_id=$1",
    [1]
  );
  await client.query("COMMIT");
} catch (e) {
  try { await client.query("ROLLBACK"); } catch (_) {}
  throw e;
} finally {
  client.release();
}
~~~

### Exercise 16

No. Once the SELECT statement's transaction commits, the lock no longer protects a separate subsequent UPDATE.

### Exercise 17

PostgreSQL has transactional DDL; many `CREATE TABLE` commands can be rolled back. `CREATE DATABASE`, `VACUUM`, and `CREATE INDEX CONCURRENTLY` cannot run inside a normal transaction block.

### Exercise 18

Allocated sequence/identity numbers do not roll back like inserted rows; IDs can have gaps.

### Exercise 19

Emails do not roll back automatically. Write business data and an outbox event in the same DB transaction; a worker sends the email after commit with idempotency safeguards.

### Exercise 20

~~~sql
SELECT
    pid, application_name, state,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

Risks include prolonged locks, VACUUM/bloat issues, and connection pool exhaustion.

### Exercise 21

Do not retry unconditionally. The server may have committed while the response was lost; use request IDs/idempotency, status lookups, and reconciliation.

### Exercise 22

Order creation, inventory adjustment, and audit/outbox inserts belong in one PostgreSQL transaction when atomicity is needed. External emails are sent post-commit via a worker/outbox rather than directly inside the transaction.

## 27. Quick Reference Table

| Need | Syntax / API |
| --- | --- |
| Open transaction | `BEGIN;` or `START TRANSACTION;` |
| Commit | `COMMIT;` |
| Abort transaction | `ROLLBACK;` |
| Create recovery marker | `SAVEPOINT mark;` |
| Roll back to marker | `ROLLBACK TO SAVEPOINT mark;` |
| Remove marker | `RELEASE SAVEPOINT mark;` |
| Choose isolation | `BEGIN ISOLATION LEVEL READ COMMITTED;` |
| psql toggle autocommit | `\set AUTOCOMMIT on/off` |
| psql stop script on error | `-v ON_ERROR_STOP=1` |
| psql single transaction for script | `-1` / `--single-transaction` |
| JDBC start manual management | `connection.setAutoCommit(false)` |
| JDBC finish | `connection.commit()` / `connection.rollback()` |
| JDBC read mode | `connection.getAutoCommit()` |
| Spring transaction | `@Transactional` + appropriate transaction manager |
| Node pg | `pool.connect()` and the same `client` |
| psycopg 3 | `with conn.transaction():` |
| Lock rows | `SELECT ... FOR UPDATE` inside an appropriate transaction |
| Inspect sessions | `pg_stat_activity`, `state`, `xact_start` |
| Idle-in-transaction timeout | `idle_in_transaction_session_timeout` |

## 28. Pre-Production Checklist

| Question | Why It Matters |
| --- | --- |
| What business unit must commit together? | Defines the transaction boundary |
| What is the client/driver autocommit default? | Prevents unintended commits |
| Do all statements share the same connection? | PostgreSQL transactions are session-bound |
| Who manages commit/rollback? | Avoids conflicts across SQL, JDBC, and frameworks |
| Does the code verify rows affected? | Prevents committing an incomplete operation |
| Do exceptions trigger rollback? | Prevents frameworks from committing on swallowed errors |
| Are errors at COMMIT handled? | Deferred constraints and network errors can appear late |
| Are idempotency keys persisted? | Prevents duplicate processing on retries |
| Are appropriate locks held? | Prevents races and deadlocks |
| Are there DDLs unsupported in transaction blocks? | Prevents mid-migration failures |
| Are emails/HTTP calls made inside the transaction? | DB rollback does not undo external side effects |
| Is the transaction too long? | Reduces locks, MVCC bloat, and pool exhaustion |
| Is `idle in transaction` monitored? | Detects abandoned connections |
| Tested with two sessions? | Confirms uncommitted changes aren't mistaken for committed |

## 29. Summary

**Autocommit** describes how a tool or driver finalizes standalone statements; **transaction boundaries** decide which PostgreSQL operations must **commit or roll back together**. PostgreSQL still executes every statement within a transaction context, but that does not mean multiple separately sent statements automatically form an atomic business operation.

Three points to remember:

1. **A business unit requiring atomicity must run in one transaction on the same connection.** Use `BEGIN ... COMMIT` in SQL, `setAutoCommit(false)` in JDBC, or a proper framework transaction manager.
2. **Only commit when every business condition holds.** Verify affected row counts, constraints, concurrency errors, and commit-time exceptions; roll back whenever needed.
3. **PostgreSQL transactions do not cover systems outside the database.** Email, HTTP, filesystems, and sequences behave differently; use outbox, idempotency, and reconciliation to handle them safely.

When designing a workflow, ask: **"If a later step fails, is the earlier step allowed to remain?"** If the answer is **no**, the related PostgreSQL changes belong in the same transaction on the same connection, with a clear rollback path and no unnecessary time spent open.
