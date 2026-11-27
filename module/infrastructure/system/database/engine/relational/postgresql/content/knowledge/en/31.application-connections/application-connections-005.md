# Managing Autocommit, Commit, Rollback, and JDBC Resources in PostgreSQL

A business operation often requires multiple SQL statements to succeed **together** or fail **together**. For example, transferring 125.00 from account A to B must debit A's balance, credit B's balance, and record a ledger entry. If the debit succeeds and the credit fails, the system must never persist a state where money vanishes.

In Java, JDBC provides `Connection` to control PostgreSQL transactions, `PreparedStatement` to send parameterized SQL, and `ResultSet` to read rows. Three method groups are especially critical:

~~~java
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
~~~

And an inseparable operational rule:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {
    // Use statement.
} // Resources are closed in reverse order.
~~~

**However, closing a connection is not a substitute for deliberately calling `rollback()`.** Forgetting to roll back on error, returning a connection with leftover transaction state to a pool, or enabling autocommit at the wrong time can cause non-atomic data, long-held locks, `idle in transaction` sessions, and hard-to-reproduce bugs.

~~~text
Java Application
   |
   +-- DataSource / connection pool
   |         |
   |         v
   |      Connection (a leased PostgreSQL session)
   |         |
   |         +-- setAutoCommit(false)
   |         +-- PreparedStatement 1: debit
   |         +-- PreparedStatement 2: credit
   |         +-- PreparedStatement 3: insert ledger
   |         |
   |         +-- All succeeded? ------- Yes ---> commit()
   |         |                           |
   |         |                           No ---> rollback()
   |         |
   |         +-- close() -> return connection to pool
   |
   +-- Never share the same Connection concurrently across threads arbitrarily
~~~

This lesson belongs to the **Application Connections** chapter of the *Database Engine Relational PostgreSQL* module, focusing on how JDBC applications manage **autocommit**, `commit`/`rollback` boundaries, PostgreSQL aborted transaction state, savepoints, JDBC resources, connection pools, isolation, timeouts, transfer implementation, and practical testing.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the roles of `Connection`, `Statement`/`PreparedStatement`, `ResultSet`, and `DataSource`.
2. Explain JDBC default autocommit and per-statement transaction boundaries.
3. Use `setAutoCommit(false)`, `commit()`, and `rollback()` properly for multi-statement business operations.
4. Understand that `setAutoCommit(true)` can commit an active transaction when switched from `false`.
5. Recognize SQL errors that put a PostgreSQL transaction into an aborted state and how to recover.
6. Use `try-with-resources` to close connections, statements, and result sets properly.
7. Ensure rollback occurs on both `SQLException` and runtime exceptions within a unit of work.
8. Understand the limits of rollback when `commit()` fails due to a lost connection.
9. Apply `Savepoint` for recoverable sub-steps without aborting the entire transaction.
10. Implement a money transfer checking affected row counts, locks, transactions, and ledger logging.
11. Understand how pools hand connections to the next caller and why transaction state must never leak.
12. Set isolation, read-only mode, and timeouts at the proper connection/transaction scope.
13. Understand how batches, streaming `ResultSet`s, fetch size, and cursors affect transaction duration.
14. Know when Spring `@Transactional` manages transactions instead of manual JDBC.
15. Observe `pg_stat_activity`, `pg_locks`, and common `SQLSTATE` codes when diagnosing incidents.

## 2. Which Layer Is JDBC?

JDBC (*Java Database Connectivity*) is the Java API for database access via a matching driver. When working with PostgreSQL, applications typically use the PostgreSQL JDBC Driver (**PGJDBC**).

### 2.1. Overall Architecture

~~~text
Java service
   |
   +-- JDBC API: java.sql.*, javax.sql.DataSource
   |       |
   |       v
   |   PostgreSQL JDBC Driver
   |       |
   |       v
   |   TCP/TLS connection
   |       |
   |       v
   |   PostgreSQL backend/session
   |       |
   |       +-- transaction
   |       +-- locks
   |       +-- MVCC snapshot
   |       +-- SQL execution
~~~

### 2.2. `DataSource`

`DataSource` is the interface that hands out `Connection`s. In production applications, an implementation such as a connection pool typically hands out a **logical connection handle** per lease.

### 2.3. `Connection`

`Connection` represents the communication context with the database: autocommit, isolation, read-only mode, transactions, and session-scoped resources.

### 2.4. `PreparedStatement`

`PreparedStatement` holds SQL with placeholders and binds parameters, separating data from SQL syntax and preventing user input concatenation.

### 2.5. `ResultSet`

`ResultSet` iterates over returned rows. It is tied to the `Statement` and `Connection` that created it; never return the connection to a pool while the `ResultSet` still needs to be read.

### 2.6. The JDBC API Does Not Decide Business Rules

JDBC provides the primitives to form a transaction. You must still decide:

- Which SQL statements must be atomic together?
- When is the transaction eligible to commit?
- When must it roll back?
- Which errors are retryable?
- How long may locks and snapshots be held?

## 3. Creating a PostgreSQL Connection via JDBC

With PGJDBC on the classpath, a basic connection can be created via:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class PgConnectionDemo {
    public static void main(String[] args) throws SQLException {
        String url =
            "jdbc:postgresql://db.example.internal:5432/appdb";

        Properties props = new Properties();
        props.setProperty("user", "app_user");
        props.setProperty("password", System.getenv("DB_PASSWORD"));
        props.setProperty("sslmode", "verify-full");
        props.setProperty(
            "sslrootcert", "/etc/app/certs/pg-ca.crt"
        );

        try (Connection connection =
                 DriverManager.getConnection(url, props)) {
            System.out.println(
                "AutoCommit: " + connection.getAutoCommit()
            );
        }
    }
}
~~~

Addresses, CA paths, users, and databases are illustrative; use properly managed real endpoints and secrets. If the password environment variable is missing, the application should fail fast with a clear configuration error.

### 3.1. Do Not Expose Passwords

Never hardcode passwords in source control, connection logs, or URLs printed to the console. Use a secret manager or appropriate secret injection mechanism.

### 3.2. TLS and Server Verification

`sslmode=verify-full` verifies the CA and PostgreSQL hostname. It does not replace user authentication or transaction logic.

### 3.3. Connections Have Cost

Each physical connection spawns/uses a PostgreSQL backend/session and consumes resources. In multi-request applications, using a properly sized pool is far better than opening a new TCP connection for every SQL statement.

### 3.4. Drivers and Frameworks Differ

These examples use plain JDBC to make the rules explicit. Spring/JPA may manage connections and transactions on your behalf; avoid mixing the two models haphazardly.

## 4. What Is Autocommit?

In JDBC, a newly created connection normally starts in state:

~~~java
connection.getAutoCommit(); // Usually: true
~~~

When autocommit is enabled, **each individual SQL statement** is treated as its own transaction unit per JDBC/driver rules; the transaction commits once the statement is considered complete.

### 4.1. Example of Two Non-Atomic Statements

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Assume connection.getAutoCommit() == true.

    try (PreparedStatement debit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance - 100 " +
            "WHERE account_id = 1")) {
        debit.executeUpdate();
    }

    // If an error occurs here, the first UPDATE may already be committed.

    try (PreparedStatement credit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance + 100 " +
            "WHERE account_id = 2")) {
        credit.executeUpdate();
    }
}
~~~

If the debit `UPDATE` finishes and the credit `UPDATE` fails, the two SQL statements are not part of a single application-controlled transaction.

### 4.2. "One SQL Statement" Is Atomic by Itself

PostgreSQL guarantees transaction atomicity for an individual statement within its scope. The issue here is **multiple statements needing to succeed together**, not a single `UPDATE` half-writing a row.

### 4.3. Completion of `SELECT` and `ResultSet`

Under JDBC, autocommit happens when the statement completes; for statements returning a `ResultSet`, completion relates to consuming/closing the `ResultSet` per driver semantics. Do not assume that merely because `executeQuery()` returned, all server resources have already been released.

### 4.4. JDBC Autocommit Is Not a Server-Side PostgreSQL GUC

`setAutoCommit(...)` is an operation on the **JDBC `Connection`**, not equivalent to running `SET autocommit=off` on the PostgreSQL server. The driver manages transaction boundaries and sends the appropriate protocol/SQL commands.

### 4.5. Verify Rather Than Assuming

Never assume a pooled connection's state from memory. Pools or frameworks can configure defaults; call `getAutoCommit()` when debugging or explicitly follow the managing layer's contract.

## 5. Disabling Autocommit for Multi-Statement Transactions

~~~java
connection.setAutoCommit(false);
~~~

From this point, subsequent statements belong to a transaction that the application explicitly ends via:

~~~java
connection.commit();
~~~

or:

~~~java
connection.rollback();
~~~

### 5.1. Standard Flow

~~~text
Acquire Connection
      |
      v
setAutoCommit(false)
      |
      v
Statement A
      |
      v
Statement B
      |
      v
Statement C
      |
      +---- All succeeded ---------> commit()
      |
      +---- A step failed ---------> rollback()
      |
      v
Close resources / return connection to pool
~~~

### 5.2. Do Not Delay Commit Indefinitely

While a transaction is active, it can hold locks, snapshots, and PostgreSQL resources. Waiting on an external API or sleeping between two statements causes `idle in transaction` and degrades concurrency.

### 5.3. Do Not Commit Each Step of the Same Operation

If three steps must be atomic, calling `commit()` after each step defeats rolling everything back if the final step fails.

### 5.4. Avoid Switching Connections Mid-Operation

A transaction belongs to **one specific connection/session**. If the debit runs on connection A and the credit runs on connection B, calling `rollback()` on A will not roll back B.

## 6. SQL `BEGIN` vs. `setAutoCommit(false)`

In `psql`, you typically write:

~~~sql
BEGIN;
UPDATE ...;
UPDATE ...;
COMMIT;
~~~

In JDBC, use the transaction API:

~~~java
connection.setAutoCommit(false);
// statements
connection.commit();
~~~

### 6.1. Let the Driver Control Transaction Boundaries

PGJDBC typically emits the transaction start command when the first statement runs under `autocommit=false`. There is not necessarily an active server transaction the instant Java calls `setAutoCommit(false)` before any SQL runs.

### 6.2. Do Not Mix Manual `BEGIN`/`COMMIT` With the JDBC API

Avoid:

~~~java
connection.setAutoCommit(false);
statement.execute("BEGIN");
// ...
statement.execute("COMMIT");
connection.rollback();
~~~

Sending raw `BEGIN`/`COMMIT` alongside JDBC `commit()`/`rollback()` makes driver state and program intent hard to track and prone to warnings or unexpected behavior.

### 6.3. Each Transaction Has One Clear Owner

Pick **one owner**: manual JDBC, a framework transaction manager, or an explicit coordinator API; never let multiple layers commit over each other.

## 7. What Does `commit()` Mean?

~~~java
connection.commit();
~~~

With autocommit disabled, `commit()` tells PostgreSQL to finish the current transaction by committing it. On success, changes take effect per transaction semantics and become visible to other transactions according to their isolation levels and snapshots.

### 7.1. Commit Does Not Mean Every Client Sees It Instantly

Another transaction in `REPEATABLE READ` continues reading its older snapshot. Replicas may also have replication lag. Commit guarantees durability/visibility per PostgreSQL semantics; never assume every observer sees the update simultaneously.

### 7.2. Never Call `commit()` When Autocommit Is True

Per the JDBC contract, `commit()` is used only when autocommit is off; calling it when autocommit is true can throw `SQLException`.

### 7.3. One Commit Ends Only the Current Transaction

After `commit()`, the connection remains in `autocommit=false` unless changed. The next statement starts a new transaction. `commit()` does not re-enable autocommit.

### 7.4. Commit Is a Business Decision

Call `commit()` only after verifying:

- Expected `UPDATE`/`DELETE` row counts match.
- No constraint violations occurred.
- Required ledger/outbox `INSERT`s succeeded.
- No validation error requires failing the transaction.

## 8. What Does `rollback()` Mean?

~~~java
connection.rollback();
~~~

`rollback()` discards uncommitted changes made within the current transaction per PostgreSQL semantics.

### 8.1. Example Failure on the Final Step

~~~text
BEGIN transaction
  UPDATE A: debit 100
  UPDATE B: credit 100
  INSERT ledger: fails
ROLLBACK
~~~

Result: neither the balance changes nor the ledger insert in that transaction are committed.

### 8.2. Rollback Does Not Undo Already-Committed Transactions

If code committed the debit in an earlier transaction, rolling back a later transaction cannot undo that prior debit. Fixing it requires an explicitly designed and audited compensating transaction.

### 8.3. Rollback Does Not Rewind Sequences

`nextval`/identity sequences in PostgreSQL do not roll back allocated numbers. Gaps in `transfer_id` after rollbacks are normal, not evidence of missing money.

### 8.4. Rollback Does Not Undo External Side Effects

Emails, HTTP calls, or messages dispatched to other systems can still persist. Use a transactional outbox, idempotency, or proper orchestration rather than calling external services mid-transaction and expecting DB rollback to undo them.

## 9. `setAutoCommit(true)` Can Commit Unexpectedly

This is an important trap:

~~~java
connection.setAutoCommit(false);

// Perform some changes...

connection.setAutoCommit(true);
~~~

Per JDBC, toggling autocommit **while a transaction is active** commits the active transaction when the mode changes. Switching from `false` to `true` is **not a neutral cleanup**.

### 9.1. Dangerous Example

~~~java
connection.setAutoCommit(false);
updateAccount(connection);

// Missing explicit commit()/rollback():
connection.setAutoCommit(true);
~~~

The final call can commit pending changes even though business logic did not complete.

### 9.2. Safe Sequence

~~~java
connection.setAutoCommit(false);
try {
    doWork(connection);
    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        ex.addSuppressed(rollbackFailure);
    }
    throw ex;
}
~~~

Only restore autocommit if the application **truly owns the connection**, knows the transaction has ended cleanly, and is not managed by an external transaction manager.

### 9.3. Pools Usually Manage Their Own Reset

When borrowing from a pool, normally let the pool reset `autoCommit`/`isolation`/`readOnly` per its contract. Avoid unconditional `finally { setAutoCommit(true); }` blocks when the transaction might still be in an error state.

### 9.4. If Manual Reset Is Needed

Finish the transaction first via a successful `commit()` or `rollback()`, then reset in controlled logic. If rollback fails because the connection is broken, discard the connection rather than forcing mode changes to return it to the pool.

## 10. Closing Resources: `try-with-resources`

JDBC resources must be closed properly:

~~~java
String sql =
    "SELECT account_id, balance FROM accounts " +
    "WHERE account_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("account_id");
            java.math.BigDecimal balance =
                rs.getBigDecimal("balance");
            System.out.println(id + ": " + balance);
        }
    }
}
~~~

### 10.1. Closing in Reverse Order

In the example, `ResultSet` closes first, then `PreparedStatement`, and finally `Connection`.

### 10.2. Close `ResultSet` Promptly

Query results can hold cursors, buffers, server resources, or statement references. Read and close them within a tight scope.

### 10.3. Close `Statement`

`PreparedStatement.close()` releases statement resources per the driver. Do not retain thousands of open statements longer than the request/transaction requires.

### 10.4. Close `Connection`

On a direct physical connection, `close()` terminates the session/resources. On a pooled connection, `close()` on the handle normally **returns it to the pool** without immediately closing TCP.

### 10.5. Never Retain a `ResultSet` After the Connection Closes

~~~java
ResultSet rs;
try (Connection conn = dataSource.getConnection()) {
    // ...
}
// Using rs here is a lifecycle design bug.
~~~

Return fully materialized DTOs/value objects from repository methods, never a `ResultSet` outliving its connection scope.

## 11. `close()` Does Not Replace `rollback()`

An unsafe pattern:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    updateAccount(connection);
    // An error is thrown before commit.
}
~~~

### 11.1. JDBC and Driver/Pool Lifecycle Details

Behavior when closing a connection with an active transaction depends on driver and pool implementation details. Some pools roll back/reset before returning the connection. **Never rely on that as business logic**; explicitly call `rollback()` whenever a transaction is not committed.

### 11.2. Practical Reasons

If code implicitly relies on `close()`:

- It becomes fragile across differences between pooled and raw connections.
- Transaction failures become harder to log cleanly.
- Preserving the root exception alongside cleanup failures becomes harder.
- Switching drivers or pools can silently change behavior.

### 11.3. Rule

**Every application-managed transaction must have an explicit path to `commit()` or `rollback()`.** Close resources afterward.

## 12. Basic Safe JDBC Transaction Pattern

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransactionExample {
    private final DataSource dataSource;

    public TransactionExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void performBusinessOperation() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                firstStatement(connection);
                secondStatement(connection);
                thirdStatement(connection);

                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    private void firstStatement(Connection c)
            throws SQLException {
        // SQL statement with result verification.
    }

    private void secondStatement(Connection c)
            throws SQLException {
        // Next step on the SAME connection.
    }

    private void thirdStatement(Connection c)
            throws SQLException {
        // Persist business result/ledger before commit.
    }
}
~~~

### 12.1. Roles of the Two `try` Blocks

The outer `try-with-resources` guarantees closing the connection. The inner `try/catch` decides **commit vs. rollback**.

### 12.2. Catching `RuntimeException`

Business validation, mapping, or Java logic errors can throw runtime exceptions. Omitting them could let the transaction fall through to closing the connection without an explicit rollback.

### 12.3. Preserving the Original Exception

If rollback also fails, `ex.addSuppressed(rollbackFailure)` preserves the original failure as the primary cause while keeping cleanup failure diagnostics.

### 12.4. Never Swallow `SQLException`

Code like:

~~~java
catch (SQLException ex) {
    connection.rollback();
    return; // Hides the failure!
}
~~~

makes callers think the operation succeeded. If you intentionally translate errors into a domain result, explicitly represent the failure state rather than silently returning.

### 12.5. When `commit()` Fails Due to Connection Loss

The `catch` block can still attempt `rollback()` to clean up if the connection remains usable. Yet if the client lost the commit response due to a disconnect, **you cannot always know whether the server committed**. This is an *ambiguous commit outcome* and must be handled explicitly in critical workflows.

## 13. Creating the Transfer Practice Schema

The following examples are for a **lab database**, never run on real financial data.

### 13.1. Create Schema

~~~sql
CREATE SCHEMA jdbc_lab;
~~~

### 13.2. Create Accounts Table

~~~sql
CREATE TABLE jdbc_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
~~~

### 13.3. Create Transfers Ledger Table

~~~sql
CREATE TABLE jdbc_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    from_account_id bigint NOT NULL
        REFERENCES jdbc_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES jdbc_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    CHECK (from_account_id <> to_account_id)
);
~~~

### 13.4. Insert Two Accounts

~~~sql
INSERT INTO jdbc_lab.accounts (
    account_id, owner_name, balance
) VALUES
    (1001, 'Lan',  500.00),
    (1002, 'Minh', 150.00);
~~~

Initial total balance is **650.00**.

### 13.5. Verify Data

~~~sql
SELECT account_id, owner_name, balance
FROM jdbc_lab.accounts
ORDER BY account_id;

SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;
~~~

In this lab, internal transfers have no fee: if successful, the sum of 650.00 must be conserved.

## 14. Atomicity Requirements for a Transfer

A transaction transferring 125.00 from Lan (1001) to Minh (1002) must:

1. Validate positive amount and distinct account IDs.
2. Verify both accounts exist.
3. Prevent debiting when funds are insufficient.
4. Debit 125.00 from account 1001.
5. Credit 125.00 to account 1002.
6. Insert one row into `transfers`.
7. **Commit once** after all steps succeed.
8. **Roll back everything** if any step fails.

### 14.1. Invariant Condition

\[
\text{balance}_{1001} + \text{balance}_{1002}
= 650.00
\]

before and after a successful internal transfer, assuming no other operations or concurrent transactions alter balances.

### 14.2. State After Transferring 125.00

| Account | Before | After |
| --- | ---: | ---: |
| Lan (1001) | 500.00 | 375.00 |
| Minh (1002) | 150.00 | 275.00 |
| Total | 650.00 | 650.00 |

### 14.3. Conditional Update SQL

~~~sql
UPDATE jdbc_lab.accounts
SET balance = balance - 125.00,
    updated_at = clock_timestamp()
WHERE account_id = 1001
  AND balance >= 125.00;
~~~

If the `UPDATE` affects **0 rows**, either the account does not exist or funds are insufficient. Never assume a statement completing without an exception succeeded in debiting funds.

## 15. Java Transfer Code Using Exactly One `Connection`

The code below demonstrates an atomic transfer method using plain JDBC.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long transfer(
            long fromAccountId,
            long toAccountId,
            BigDecimal amount
    ) throws SQLException {
        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException(
                "Source and destination must differ"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }
        BigDecimal normalizedAmount =
            amount.setScale(2, RoundingMode.UNNECESSARY);

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                lockBothAccounts(
                    connection, fromAccountId, toAccountId
                );
                debit(connection, fromAccountId, normalizedAmount);
                credit(connection, toAccountId, normalizedAmount);
                long transferId = insertTransfer(
                    connection,
                    fromAccountId,
                    toAccountId,
                    normalizedAmount
                );

                connection.commit();
                return transferId;
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    private static void lockBothAccounts(
            Connection connection,
            long fromId,
            long toId
    ) throws SQLException {
        String sql =
            "SELECT account_id " +
            "FROM jdbc_lab.accounts " +
            "WHERE account_id IN (?, ?) " +
            "ORDER BY account_id FOR UPDATE";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, fromId);
            ps.setLong(2, toId);

            int count = 0;
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    count++;
                }
            }
            if (count != 2) {
                throw new IllegalArgumentException(
                    "One or both accounts do not exist"
                );
            }
        }
    }

    private static void debit(
            Connection connection,
            long fromId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance - ?, " +
            "    updated_at = clock_timestamp() " +
            "WHERE account_id = ? AND balance >= ?";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, fromId);
            ps.setBigDecimal(3, amount);

            if (ps.executeUpdate() != 1) {
                throw new IllegalArgumentException(
                    "Insufficient funds"
                );
            }
        }
    }

    private static void credit(
            Connection connection,
            long toId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance + ?, " +
            "    updated_at = clock_timestamp() " +
            "WHERE account_id = ?";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, toId);

            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException(
                    "Destination account disappeared"
                );
            }
        }
    }

    private static long insertTransfer(
            Connection connection,
            long fromId,
            long toId,
            BigDecimal amount
    ) throws SQLException {
        String sql =
            "INSERT INTO jdbc_lab.transfers " +
            "(from_account_id, to_account_id, amount) " +
            "VALUES (?, ?, ?) RETURNING transfer_id";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, fromId);
            ps.setLong(2, toId);
            ps.setBigDecimal(3, amount);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "No transfer_id was returned"
                    );
                }
                return rs.getLong(1);
            }
        }
    }
}
~~~

### 15.1. This Is a PostgreSQL JDBC Example

`RETURNING transfer_id` is convenient PostgreSQL syntax to fetch the ID after `INSERT`. If cross-RDBMS portability is required, consider `getGeneratedKeys()` with verified driver behavior.

### 15.2. One Connection for the Entire Operation

All helpers receive the same `Connection connection`; no helper calls `dataSource.getConnection()`. If each helper leased a separate connection, the operation would no longer be atomic.

### 15.3. Locking Accounts

`SELECT ... FOR UPDATE` acquires row-level locks so concurrent transactions cannot arbitrarily mutate the same accounts. `ORDER BY account_id` establishes a deterministic lock order in this example; a production design should maintain consistent lock ordering across **all update paths** to minimize deadlocks.

### 15.4. Checking Affected Row Counts

`executeUpdate()` returns the number of affected rows. If debit or credit does not update exactly one row, throw an error so the transaction rolls back.

### 15.5. Use `BigDecimal` for Money

`numeric(14,2)` pairs with `BigDecimal`, avoiding binary floating-point error from `double`. `RoundingMode.UNNECESSARY` in this example rejects amounts having more than 2 decimal places requiring rounding.

### 15.6. Arithmetic `UPDATE` Prevents Simple Lost Updates

`balance = balance - ?`/`+ ?` computes relative to the locked database row value, which is safer than reading the balance into Java, computing locally, and overwriting with an absolute stale value under concurrency.

### 15.7. This Example Is Not Yet a Production Payment System

Real financial systems also need idempotency keys, immutable ledgers, double-entry accounting, limits, principal authorization, auditing, duplicate-retry prevention, and ambiguous-commit reconciliation. This lab specifically illustrates **transaction boundaries and resource management**.

## 16. Running the Transfer and Inspecting Results

Usage example:

~~~java
TransferRepository repository =
    new TransferRepository(dataSource);

long id = repository.transfer(
    1001L,
    1002L,
    new BigDecimal("125.00")
);

System.out.println("Transfer ID: " + id);
~~~

### 16.1. Verify Balances

~~~sql
SELECT account_id, balance
FROM jdbc_lab.accounts
ORDER BY account_id;
~~~

Assuming no other transactions ran:

~~~text
1001  375.00
1002  275.00
~~~

### 16.2. Verify Ledger

~~~sql
SELECT
    transfer_id,
    from_account_id,
    to_account_id,
    amount,
    created_at
FROM jdbc_lab.transfers
ORDER BY transfer_id DESC;
~~~

### 16.3. Verify Total

~~~sql
SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;
~~~

Expect 650.00 after a successful internal transfer.

### 16.4. Re-Running Has Real Side Effects

Every call to `transfer(...)` executes **a new transfer** without idempotency. Do not run it repeatedly expecting balances to match the first table.

## 17. Testing Rollback on Insufficient Funds

Suppose the source account has 375.00; try transferring 900.00.

~~~java
try {
    repository.transfer(
        1001L, 1002L, new BigDecimal("900.00")
    );
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}
~~~

### 17.1. Debit Condition Fails

~~~sql
WHERE account_id = ? AND balance >= ?
~~~

matches 0 rows, `executeUpdate()` returns 0, and Java throws an exception.

### 17.2. Rollback

The catch block calls `connection.rollback()`. Even when no writes occurred, rollback cleanly closes the transaction.

### 17.3. No Ledger Entry

The `INSERT` into `transfers` never ran, so no new ledger record exists. For failures occurring after debit/credit, rollback likewise discards uncommitted changes from the transaction.

### 17.4. Business Errors Are Not Always `SQLException`

In this example, insufficient funds throws `IllegalArgumentException`. That is why the pattern catches `RuntimeException` as well for rollback, rather than catching `SQLException` alone.

## 18. Testing Failure After Debiting

An important test is simulating failure **after updating the source account**, before committing.

### 18.1. Illustrative Flow

~~~text
setAutoCommit(false)
  -> UPDATE source balance -= 50
  -> UPDATE destination balance += 50
  -> INSERT ledger fails
  -> rollback()
  -> both source and destination remain at pre-transaction values
~~~

### 18.2. Do Not Force Errors by Dropping Real Tables

In automated tests, use transaction/test seams or constraint-violating data in a **lab** database. Never alter production schemas to force errors for testing.

### 18.3. Assertions Must Check Both Sides

A rollback test must verify not only that `transfers` has no new row, but also that both source and destination balances are unchanged.

### 18.4. Sequence IDs May Still Advance

If the ledger `INSERT` allocates an identity value before failing/rolling back, the ID can leave a gap. Tests must not demand gapless sequences.

## 19. PostgreSQL Aborted Transactions and `SQLSTATE 25P02`

In PostgreSQL, when a statement raises an error inside a normal transaction, the transaction enters an **aborted** state.

### 19.1. Example Under JDBC `autocommit=false`

~~~sql
BEGIN;

INSERT INTO jdbc_lab.accounts (
    account_id, owner_name, balance
) VALUES (
    1001, 'Duplicate ID', 1.00
);

SELECT * FROM jdbc_lab.accounts;
~~~

The `INSERT` violates the primary key (if ID 1001 already exists). The subsequent `SELECT` inside the same transaction fails with an error like:

~~~text
current transaction is aborted,
commands ignored until end of transaction block
~~~

The associated `SQLSTATE` is `25P02`.

### 19.2. Do Not Keep Sending Statements Expecting Self-Recovery

JDBC code that catches `SQLException` and sends another `UPDATE` on the same connection without rolling back will just receive `25P02` errors.

### 19.3. Basic Recovery Path

~~~java
try {
    executeWork(connection);
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

### 19.4. Savepoints Are a Controlled Option

If the error occurred in an **explicitly optional** step, `rollback(savepoint)` restores the transaction to a usable state without rolling back the whole transaction. Never use it to ignore errors that invalidate the overall business operation.

### 19.5. In `psql`

Once a transaction is aborted, run `ROLLBACK` (or roll back to a savepoint created before the error) instead of trying to run further `SELECT`s as if nothing happened.

## 20. What Is a `Savepoint`?

A `Savepoint` marks a point inside a transaction, allowing partial rollback of work performed after that mark.

~~~java
connection.setAutoCommit(false);

Savepoint savepoint = connection.setSavepoint("optional_step");
// ...
connection.rollback(savepoint);
~~~

### 20.1. Does Not Replace `commit()`

Rolling back to a savepoint does not commit the transaction. The overall transaction still requires `commit()` or `rollback()`.

### 20.2. Not for `autocommit=true`

Savepoints belong to application-managed transactions; disable autocommit first.

### 20.3. Right Use Case

A flow:

~~~text
Create order
  |
  +-- Write core order      (required)
  |
  +-- SAVEPOINT extras
          |
          +-- Write extra tag (optional)
          +-- Error?
                |
                +-- ROLLBACK TO extras
  |
  +-- COMMIT core order
~~~

is valid only when business requirements explicitly permit missing the optional tag.

## 21. JDBC `Savepoint` Example

~~~java
import java.sql.Connection;
import java.sql.Savepoint;
import java.sql.SQLException;
import javax.sql.DataSource;

public void createOrderWithOptionalTag(DataSource ds)
        throws SQLException {
    try (Connection connection = ds.getConnection()) {
        connection.setAutoCommit(false);

        try {
            insertRequiredOrder(connection);

            Savepoint sp =
                connection.setSavepoint("before_optional_tag");

            try {
                insertOptionalTag(connection);
            } catch (SQLException optionalError) {
                connection.rollback(sp);
                // Safely log optional error.
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
~~~

Both helpers are business methods to implement receiving the **same `Connection`**; the snippet illustrates the transaction/savepoint handling scaffold.

### 21.1. Why Rolling Back to Savepoint Matters

In PostgreSQL, after a failing statement, the transaction normally aborts. `rollback(sp)` discards the failed sub-step's effects and allows the transaction to proceed.

### 21.2. If `rollback(sp)` Also Fails

An exception from `rollback(sp)` propagates to the outer catch, where the application attempts to roll back the entire transaction. Never swallow this failure because the connection may no longer be trustworthy.

### 21.3. Releasing Savepoints

JDBC offers `releaseSavepoint(sp)` to release a savepoint when no longer needed. After rolling back to a savepoint, check your driver's lifecycle semantics before calling release; avoid accumulating thousands of unnecessary savepoints.

### 21.4. Savepoints Have Overhead

Creating savepoints and subtransactions is not free. Never create a savepoint per row across a million-row batch just to avoid proper upfront validation.

### 21.5. Required Failures Must Never Be Ignored

If writing the core order fails, never roll back just that step and commit the rest. Business rules must dictate which steps are optional.

## 22. Full `rollback()` vs. `rollback(savepoint)`

| Operation | Scope | Transaction After Operation |
| --- | --- | --- |
| `rollback()` | Entire uncommitted transaction | Ended; a new transaction may start |
| `rollback(savepoint)` | Changes made after the savepoint | Transaction continues from the saved point |
| `commit()` | Commits entire transaction | Ended successfully |
| `releaseSavepoint(sp)` | Discards savepoint marker | Does not commit or roll back transaction |

### 22.1. Never `rollback(savepoint)` After `commit()`

Once committed, savepoints from the ended transaction are no longer valid.

### 22.2. Savepoints and `SQLSTATE` Exceptions

A `23505` or `23503` error in a PostgreSQL transaction normally aborts the transaction; rolling back to a savepoint created **before the error** is how controlled recovery works.

### 22.3. Never Use Savepoints to Fake Partial Success

If a transfer must debit, credit, and write the ledger atomically, a ledger failure is not optional. Never roll back only the ledger `INSERT` and commit the debit/credit.

## 23. `SQLSTATE` in JDBC Applications

`SQLException` exposes the code:

~~~java
String sqlState = exception.getSQLState();
~~~

Common PostgreSQL codes:

| SQLSTATE | Common Meaning | Recommended Response |
| --- | --- | --- |
| `23505` | Unique violation | Check constraint/idempotency; do not retry blindly |
| `23503` | Foreign key violation | Fix data or operation order |
| `23514` | Check constraint violation | Fix input/business rule |
| `25P02` | Transaction is aborted | Roll back fully or to a savepoint |
| `40001` | Serialization failure | Retry the entire transaction if appropriate |
| `40P01` | Deadlock detected | Roll back; may retry the full operation |
| `55P03` | Lock not available | Handle lock timeout / `NOWAIT` |
| `57014` | Query canceled | Handle timeout/cancellation and transaction state |
| `08006` | Connection failure | Connection may be broken; commit outcome may be uncertain |

### 23.1. Do Not Rely on Text Messages

Error wording varies by language, locale, and server version. `SQLSTATE` and structured exception metadata are far more stable for classification.

### 23.2. Constraint Names Aid Diagnosis

With PGJDBC, some errors expose detailed PostgreSQL metadata via driver APIs; when you need to identify the violated constraint, use structured metadata if available rather than regex-parsing message strings.

### 23.3. Never Retry Every `SQLException`

A `23514` caused by a negative amount will fail 100 times in a row. Retries must target transient errors with an explicit strategy—such as serialization/deadlock—and enforce a retry limit.

## 24. Safe Transaction Retries

PostgreSQL can throw `40001` when `SERIALIZABLE` detects a conflict, or `40P01` on deadlock.

### 24.1. Retry the **Entire** Transaction

~~~text
Attempt 1:
   BEGIN -> SELECT -> UPDATE -> error 40001 -> ROLLBACK

Attempt 2:
   New BEGIN -> re-SELECT -> re-UPDATE -> COMMIT
~~~

Never retry only the final `UPDATE` on an aborted transaction.

### 24.2. Every Attempt Starts With a Clean Transaction

Lease a fresh connection or ensure the existing one rolled back cleanly and is safe to reuse. Never continue from an uncertain error state.

### 24.3. Backoff and Bounds

For instance, cap at 3 attempts with controlled backoff and jitter; if still failing, return a clear error. Avoid causing a *retry storm* when the database is already overloaded.

### 24.4. Retries and Side Effects

If a transaction calls external systems, retries can dispatch duplicate requests. Use idempotency keys, outboxes, or architectures that decouple external side effects.

### 24.5. Transaction Succeeds While Commit Response Drops

When connectivity drops right at commit, the client cannot always know whether the server committed. Retrying a "transfer" with a new ID can transfer twice. Use a unique business request ID and check transaction status before deciding to retry.

## 25. Ambiguous Commit and Idempotency

Suppose:

~~~text
Client sends COMMIT
    |
    +-- PostgreSQL committed
    |
    +-- Network drops before client receives OK
~~~

The application sees a connection error, yet **the server may have already committed**.

### 25.1. `rollback()` Does Not Undo an Already-Committed Transaction

If the commit completed, calling `rollback()` on the old or a new connection cannot cancel the committed transaction.

### 25.2. Idempotency Key

A production transfer should carry a system-issued `business_request_id` with a `UNIQUE` constraint:

~~~sql
-- Illustrative schema extension in the lab schema:
-- ALTER TABLE jdbc_lab.transfers
-- ADD COLUMN business_request_id uuid UNIQUE;
~~~

Retry logic must look up the transaction by the stable request ID and compare business parameters, never generating a fresh ID on each retry.

### 25.3. Do Not Immediately Treat a Retry Unique Violation as an Error

If the request ID already exists and parameters match, an earlier attempt may have committed. Query status and align with the API contract to return a consistent result.

### 25.4. An Idempotency Key Alone Is Not Enough

The application must still handle concurrent races on the same key, transaction boundaries, and result mapping. A `UNIQUE` constraint is one building block, not the entire solution.

## 26. Transaction Isolation and JDBC

JDBC provides:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Common levels:

| JDBC Constant | PostgreSQL Equivalent / Notes |
| --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | PostgreSQL executes with `READ COMMITTED` semantics |
| `TRANSACTION_READ_COMMITTED` | Common PostgreSQL default |
| `TRANSACTION_REPEATABLE_READ` | Stable transaction snapshot, with its own conflict error rules |
| `TRANSACTION_SERIALIZABLE` | Strongest isolation; can raise `40001` requiring retry |

### 26.1. `READ COMMITTED`

Each statement sees a fresh snapshot of transactions committed before that statement starts. Two `SELECT`s in the same transaction can observe different rows if concurrent commits happen in between.

### 26.2. `REPEATABLE READ`

Normal reads inside the transaction share a consistent snapshot, though concurrent updates to the same row can raise serialization conflicts per PostgreSQL semantics.

### 26.3. `SERIALIZABLE`

Prevents concurrency anomalies that simple locks miss, yet the application must **retry the entire transaction** whenever the server raises a serialization failure.

### 26.4. Set Isolation Before the Transaction Truly Starts

JDBC leaves mid-transaction isolation changes implementation-dependent. With PGJDBC, set isolation **before the first statement of the transaction**, or via your transaction manager API.

### 26.5. Isolation Does Not Fix Broken Transaction Boundaries

Using `SERIALIZABLE` will not fix a debit running on one connection and a credit running in a separate transaction on another connection.

## 27. Example Setting Isolation

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE
    );
    connection.setAutoCommit(false);

    try {
        performOperation(connection);
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

### 27.1. Watch Out With Pooled Connections

If you alter isolation on a pooled connection, ensure the pool/framework resets state cleanly. Otherwise a later request may accidentally inherit `SERIALIZABLE` and suffer unexpected conflicts or overhead.

### 27.2. Reading the Current State

~~~java
int isolation = connection.getTransactionIsolation();
~~~

### 27.3. Do Not Call `setTransactionIsolation` Arbitrarily Inside Repositories

When Spring already manages a transaction, changing isolation inside a lower-level repository can conflict with the transaction manager and ongoing work.

## 28. Read-Only Transactions

JDBC provides:

~~~java
connection.setReadOnly(true);
~~~

### 28.1. Intent

Marks the connection/transaction as expected to be read-only. The driver/database can use this hint or enforce read-only policies accordingly.

### 28.2. Not a Security Permission Boundary

`setReadOnly(true)` does not replace PostgreSQL role privileges. A role with write privileges must still be restricted using `GRANT`, RLS, and database policies.

### 28.3. Set Before Starting the Transaction

PGJDBC has specific configuration details on how read-only applies per connection/transaction. Set it before statements execute in the transaction and never toggle it mid-transaction unless supported by a framework contract.

### 28.4. Remember Pool Resets

A read-only flag can affect the next request if the pool fails to reset it. Prefer managing it via the transaction manager or connection pool rather than mutating it covertly inside a SQL helper.

## 29. Statement Timeouts and Transaction Timeouts

A query waiting on locks or scanning huge tables can stall a request for a long time.

### 29.1. JDBC `Statement.setQueryTimeout`

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT count(*) FROM jdbc_lab.transfers"
         )) {
    ps.setQueryTimeout(5); // Unit: seconds.
    try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        long count = rs.getLong(1);
    }
}
~~~

### 29.2. PostgreSQL `statement_timeout`

You can set a transaction-local setting inside the transaction:

~~~sql
SET LOCAL statement_timeout = '5s';
~~~

`SET LOCAL` applies only within the current transaction; once the transaction ends, it does not remain active at that scope.

### 29.3. `lock_timeout`

~~~sql
SET LOCAL lock_timeout = '2s';
~~~

limits lock-wait duration per PostgreSQL policy. It does not bound total query computation time.

### 29.4. `idle_in_transaction_session_timeout`

~~~sql
SET LOCAL idle_in_transaction_session_timeout = '30s';
~~~

terminates a session if left `idle in transaction` too long. It is a guardrail, not a substitute for committing or rolling back promptly.

### 29.5. Timeouts Can Abort the Transaction

When a statement inside a transaction is canceled by a timeout, the PostgreSQL transaction typically must be rolled back before continuing. Never just catch the exception and send another statement.

### 29.6. Distinguishing Timeouts

| Timeout | Protects Against |
| --- | --- |
| Connection acquisition timeout (pool) | Waiting for a free connection |
| TCP connect timeout | Establishing the network connection |
| Socket read timeout | Reading server responses |
| JDBC query timeout | Statement execution duration per driver |
| PostgreSQL `statement_timeout` | SQL execution duration on the server |
| `lock_timeout` | Waiting to acquire a lock |
| `idle_in_transaction_session_timeout` | Session left idle inside an open transaction |

No single timeout covers all phases.

## 30. Setting `SET LOCAL` via JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SET LOCAL statement_timeout = '5s'"
                 )) {
            ps.execute();
        }

        runBusinessSql(connection);
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

### 30.1. `SET LOCAL` Inside a Transaction

Must be used once transaction management is active so the setting stays transaction-scoped and never leaks through the connection pool.

### 30.2. Avoid SQL Injection in `SET LOCAL`

Application-controlled fixed settings can use explicit literals. If dynamic, validate strictly and use appropriate setting mechanisms; never concatenate untrusted input.

### 30.3. `setQueryTimeout` and `statement_timeout` Can Coexist

They operate at different layers. When both are set, understand which one may cancel the statement first and how the connection/transaction reacts.

## 31. Connection Pools: Borrowing and Returning

In server applications:

~~~text
Pool holding physical PostgreSQL connections
   |
Request A --- getConnection() ---> Logical Connection A
   |                                 |
   +---- transaction / SQL ----------+
   |
   +---- close() --------------> return to pool

Request B --- getConnection() ---> Logical Connection B
~~~

### 31.1. `close()` Usually Returns to the Pool

`Connection.close()` on a pooled handle normally returns the connection to the pool; the underlying socket/backend stays open.

### 31.2. Never Store a `Connection` in a Singleton

Avoid keeping a shared long-lived `Connection` in a singleton/bean or sharing it across requests. Each unit of work should lease a connection within an explicit scope.

### 31.3. Never Borrow a Connection and Forget `close()`

If every request leases a connection without closing it, the pool exhausts and subsequent requests block or time out.

### 31.4. Do Not Hold a Connection Across External Network Calls

Holding a connection and transaction open during a multi-second HTTP call ties up pool slots, holds locks, and hurts throughput.

### 31.5. Larger Pools Are Not Always Better

Every connection consumes PostgreSQL resources. Too many connections increase context switching, lock contention, and memory pressure; size pools based on workload, CPU, PostgreSQL limits, and wait times.

## 32. Lifecycle Example With `DataSource`

~~~java
public BigDecimal readBalance(
        DataSource dataSource,
        long accountId
) throws SQLException {
    String sql =
        "SELECT balance FROM jdbc_lab.accounts " +
        "WHERE account_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setLong(1, accountId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return null;
            }
            return rs.getBigDecimal(1);
        }
    }
}
~~~

### 32.1. A Simple `SELECT` Can Use Default Autocommit

Not every query needs autocommit disabled. If a standalone `SELECT` does not need a shared snapshot or locks across multiple statements, the default connection mode works fine.

### 32.2. Do Not Reset Modes You Did Not Change

Read-only examples that never change `autoCommit` or `isolation` mutate less state on pooled connections and are simpler to maintain.

### 32.3. One Repository Calling Another Can Break Boundaries

If every repository method leases and closes its own connection, calling two methods from a service does not create a shared transaction. Pass the `Connection`/transaction context or use a framework transaction manager.

## 33. Risk of Leaking Connection State in a Pool

Session/connection attributes that can affect the next borrower:

- Autocommit.
- Isolation level.
- Read-only flag.
- Schema / `search_path`.
- Session-level `SET` commands.
- Scoped prepared statements, temporary tables, or advisory locks.
- Unfinished transactions.

### 33.1. What Does a Pool Reset?

Connection pools typically reset tracked JDBC states. However, **never assume arbitrary SQL session variables are automatically restored** if the application runs `SET search_path`/`SET ROLE` or creates temp objects.

### 33.2. Prefer Transaction-Local Changes

Where supported, use `SET LOCAL` instead of session-level `SET` to confine effects to the transaction.

### 33.3. Watch Out for Session Advisory Locks

Session-level advisory locks persist across transactions and attach to the physical connection. Returning a connection to the pool without unlocking affects subsequent borrowers.

### 33.4. Configure Pool Baselines Explicitly

Pools should enforce clear baselines for autocommit, isolation, read-only mode, lifetime, and acquisition timeouts. Never tweak them arbitrarily inside individual repository methods.

## 34. JDBC Batching Inside a Transaction

Batching reduces JDBC/network round trips when inserting many rows:

~~~java
String sql =
    "INSERT INTO jdbc_lab.accounts " +
    "(account_id, owner_name, balance) VALUES (?, ?, ?)";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            for (int i = 0; i < 100; i++) {
                ps.setLong(1, 2000L + i);
                ps.setString(2, "Lab-" + i);
                ps.setBigDecimal(3, new BigDecimal("10.00"));
                ps.addBatch();
            }
            ps.executeBatch();
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
~~~

### 34.1. Batching Does Not Define Transaction Boundaries

`executeBatch()` does not replace `commit()`. With autocommit enabled, atomicity across batch items may not match all-or-nothing business expectations.

### 34.2. `BatchUpdateException`

When part of a batch fails, JDBC can throw `BatchUpdateException` with update counts for individual items. If **all-or-nothing** is required, roll back the transaction rather than assuming earlier items should stay committed.

### 34.3. PostgreSQL Transaction Constraints

Once a SQL error occurs in a transaction, it aborts; roll back fully or to a savepoint before sending any further SQL.

### 34.4. Oversized Batches

Batching millions of rows in one transaction spikes memory, WAL, lock duration, and transaction lifetime. Chunk batches appropriately based on atomicity needs, data volume, and system limits.

### 34.5. Splitting Into Multiple Transactions

You give up single-transaction atomicity across the whole import. Design explicit checkpoints/restarts, idempotency, and a clear "partially imported" state.

## 35. Streaming `ResultSet` and `fetchSize`

When reading millions of rows, letting the driver buffer the entire `ResultSet` in memory can exhaust the heap.

PGJDBC supports cursor-based fetching under specific conditions, typically including autocommit disabled and an appropriate `ResultSet` type.

~~~java
String sql =
    "SELECT transfer_id, amount " +
    "FROM jdbc_lab.transfers ORDER BY transfer_id";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     sql,
                     ResultSet.TYPE_FORWARD_ONLY,
                     ResultSet.CONCUR_READ_ONLY
                 )) {
            ps.setFetchSize(500);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong(1);
                    BigDecimal amount = rs.getBigDecimal(2);
                    processRow(id, amount);
                }
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
~~~

`processRow(...)` is a hypothetical application method, not a JDBC API.

### 35.1. Why Must Autocommit Be Off?

In PostgreSQL/PGJDBC cursor-based fetching, cursors are bound to a transaction; if the transaction ends immediately after the statement starts, multi-batch cursor fetching cannot continue as expected.

### 35.2. Finish Reading Before Committing

Never commit or close the connection while still iterating a `ResultSet`/cursor. Finish reading and close the `ResultSet` first, then commit or roll back.

### 35.3. Streaming Does Not Justify Unbounded Transactions

A `while (rs.next())` loop taking 30 minutes holds a transaction and snapshot open, increasing vacuum pressure and pinning a connection. For slow per-row processing, prefer keyset pagination or decoupling the query from external processing.

### 35.4. `fetchSize` Is Not `LIMIT`

`setFetchSize(500)` hints how many rows to fetch per round trip; it does not cap total returned rows at 500. The query can still return millions of rows.

### 35.5. Never Make Network Calls Inside a Long Streaming Loop

If `processRow(...)` makes an HTTP call per row, the transaction stays idle/slow for a long time. Use a separate queue or out-of-transaction batching.

## 36. Cursor vs. Keyset Pagination?

Two ways to process large datasets:

| Approach | Advantage | Trade-Off |
| --- | --- | --- |
| Cursor / `fetchSize` | Sequential iteration API; preserves snapshot consistency | Holds connection/transaction open across long scans |
| Keyset pagination | Short transaction per page; easy to retry/checkpoint | Requires a stable sort key and handling concurrent changes |

### 36.1. Keyset Illustration

~~~sql
SELECT transfer_id, amount
FROM jdbc_lab.transfers
WHERE transfer_id > :last_seen_id
ORDER BY transfer_id
LIMIT 500;
~~~

`:last_seen_id` is an illustrative placeholder for layers supporting named parameters; plain JDBC uses `?`.

### 36.2. Do Not Promise Whole-Dataset Snapshot Across Multi-Transaction Pages

If each page runs in a new transaction, source data can change between pages. Define consistency requirements upfront.

### 36.3. Design for Purpose

Exporting a consistent point-in-time snapshot fits a bounded cursor inside a controlled transaction; checkpointed batch jobs over millions of orders often fit keyset pagination with idempotency.

## 37. Connections and Thread Safety

Never share an active transactional `Connection` across multiple threads without strict synchronization and explicit driver-contract support.

### 37.1. Why Is It Dangerous?

Two threads sharing one connection can:

- Interleave SQL into the **same transaction**.
- Commit or roll back each other's work.
- Race on `Statement`/`ResultSet` state.
- Corrupt session variables unpredictably.

### 37.2. One Transaction Context per Unit of Work

In request-response services, a transaction serves one request/operation at a time. Frameworks bind connections to threads or async contexts via dedicated mechanisms.

### 37.3. Never Pass a `Connection` to Unbounded Async Callbacks

A callback executing after the resource scope closes cannot use a handle already returned to the pool. Background jobs must open their own scoped transactions.

## 38. Spring `@Transactional` vs. Manual JDBC

In Spring applications, a transaction manager usually handles connections and transactions via proxies/context.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        int debited = jdbc.update(
            "UPDATE jdbc_lab.accounts " +
            "SET balance = balance - ? " +
            "WHERE account_id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE jdbc_lab.accounts SET balance = balance + ? " +
            "WHERE account_id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Unknown destination");
        }

        jdbc.update(
            "INSERT INTO jdbc_lab.transfers " +
            "(from_account_id, to_account_id, amount) " +
            "VALUES (?, ?, ?)",
            fromId, toId, amount
        );
    }
}
~~~

This is a short illustrative sample comparing **who owns the transaction boundary**; it omits input validation, ordered locking, idempotency, and retries from the full JDBC lab example.

### 38.1. Spring Controls Commit and Rollback

With `@Transactional` active via a proxy and matching transaction manager, Spring commits when the method returns normally or rolls back per exception rules.

### 38.2. Never Call `Connection.commit()` Manually

Manually calling `commit()` on a connection participating in a Spring transaction breaks the framework contract and ends the transaction prematurely.

### 38.3. Never Bypass the Transaction Manager With Standalone `DriverManager` Calls

If a repository calls `DriverManager.getConnection()` directly, it will not share Spring's transaction with `JdbcTemplate`. Use transaction-manager-aware resource APIs.

### 38.4. Spring Rollback Rules

By default, Spring rolls back on `RuntimeException` and `Error`, not on checked exceptions unless configured (e.g. `rollbackFor=Exception.class`). Know your transaction manager's and version's exact rules.

### 38.5. Self-Invocation

In standard proxy-based setups, calling another `@Transactional` method on `this` bypasses the proxy, so the transaction interceptor does not trigger as expected.

### 38.6. Propagation

`REQUIRED` and `REQUIRES_NEW` have different semantics for joining vs. starting a transaction. `REQUIRES_NEW` can require an extra concurrent connection and cause pool pressure if nested carelessly.

## 39. When to Use `TransactionTemplate`?

When you want explicit programmatic transaction boundaries in Spring without manually driving `Connection`:

~~~java
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

public class TransferServiceExplicit {
    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    public TransferServiceExplicit(
            TransactionTemplate tx,
            JdbcTemplate jdbc
    ) {
        this.tx = tx;
        this.jdbc = jdbc;
    }

    public void doWork() {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE jdbc_lab.accounts " +
                "SET updated_at = clock_timestamp() " +
                "WHERE account_id = ?",
                1001L
            );
        });
    }
}
~~~

### 39.1. `TransactionTemplate` Does Not Need Manual `commit()`

It delegates to the transaction manager; the callback runs inside a managed transaction scope and the framework commits or rolls back appropriately.

### 39.2. Do Not Mix Owners

Never use `TransactionTemplate` while also calling `connection.setAutoCommit(false)`/`commit()` on a framework-managed connection unless specifically designed for an explicit contract.

### 39.3. Keep Business Logic Inside Transactions Short

Even though Spring cleans up resources, a `@Transactional` method can still hold locks and snapshots too long if it makes HTTP calls, sleeps, or runs heavy CPU work inside.

## 40. Observing Transactions From PostgreSQL

JDBC issues such as missing commits/rollbacks show up on PostgreSQL via `pg_stat_activity`.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_prefix
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
~~~

### 40.1. `state = idle in transaction`

An `idle in transaction` session has started a transaction and is waiting for the client to send the next command. It can hold locks/snapshots and impede vacuum.

### 40.2. `xact_start`

Shows when the current transaction began, helping spot overly long open transactions. Do not confuse it with when the HTTP request started.

### 40.3. `application_name`

Set `application_name` in connection parameters to distinguish Java services/workers in monitoring—for example via PGJDBC's `ApplicationName` property where supported.

### 40.4. Query Text May Contain Sensitive Data

Restrict monitoring privileges and handle logs carefully. Never expose raw `pg_stat_activity.query` to public dashboards.

### 40.5. Do Not Kill Backends Recklessly

`pg_terminate_backend(pid)` triggers application errors and transaction rollbacks; use it only following operational runbooks when impact is understood.

## 41. Monitoring Locks

~~~sql
SELECT
    l.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.pid, l.granted, l.mode;
~~~

### 41.1. Understand `locktype`

A transaction may hold relation locks, `transactionid` locks, or other lock types. Not every lock wait is a "table lock" blocking an entire table.

### 41.2. Blockers and Blocked Sessions

Use `pg_blocking_pids(pid)` to find process IDs blocking a backend:

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database();
~~~

### 41.3. The Root Cause May Be in Java

A connection that calls `setAutoCommit(false)` and then waits on an HTTP callback without committing or rolling back holds locks far longer than intended. Fixing the application flow matters more than raising `lock_timeout`.

## 42. Monitoring Commit and Rollback Rates

`pg_stat_database` tracks counters:

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

### 42.1. These Are Cumulative Counters

Counters do not tell you "over the last minute" unless sampled at two timestamps. They can also be reset, so handle `stats_reset` when computing rates.

### 42.2. One Rollback Does Not Always Equal a Bug

Rollbacks can result from user cancellations, validation failures, deadlock retries, or intentional business checks. A spike in rollback rate is a signal to classify, not direct proof of corruption.

### 42.3. Pair With Application Metrics

Track:

- Transaction duration p50/p95/p99.
- Transaction commits and rollbacks by business operation.
- Pool active/idle/waiting connections.
- `SQLSTATE` breakdown.
- Deadlocks and lock waits.
- `idle in transaction` sessions exceeding thresholds.

## 43. Testing Transaction Boundaries

A strong test verifies more than whether a Java method throws an exception.

### 43.1. Happy Path

Transfer 125.00: both balances match expectations, ledger has one new row, total sum is conserved.

### 43.2. Insufficient Funds

Transfer more than balance: debit updates 0 rows, both balances stay unchanged, no ledger row is written.

### 43.3. Destination Missing

Transfer to a non-existent account: operation fails, source loses no funds.

### 43.4. Ledger Failure

Ledger insert hits a constraint violation: debit and credit both roll back.

### 43.5. Concurrent Transfers

Two threads/transactions transfer from the same account totaling more than its balance: balance must never go negative or create money. Verify locks, update counts, and retry logic.

### 43.6. Deadlock/Serialization

Generate controlled contention to verify the application rolls back and retries the **entire transaction** cleanly.

### 43.7. Unknown Commit Outcome

Simulate connection drops around commit and verify idempotency/reconciliation. Never claim a simple unit test reproduces exact network commit timing deterministically.

### 43.8. Resource Leakage

Simulate requests throwing exceptions; active pool connections must return to baseline after the scope exits instead of climbing endlessly.

## 44. Unit Tests vs. Integration Tests

### 44.1. Unit Tests

Mocking repositories/`DataSource` verifies control flow, yet mocks cannot faithfully simulate PostgreSQL transaction semantics, locks, `SQLSTATE`, or driver behavior.

### 44.2. Integration Tests

Running against a real PostgreSQL instance (e.g., in a test container) verifies:

- SQL syntax and constraints.
- Commit and rollback.
- Aborted transactions (`25P02`).
- Savepoints.
- Locks and isolation.
- PGJDBC behavior.

### 44.3. Do Not Rely Solely on `@Transactional` Rollback Tests

An integration test automatically rolled back by the framework after every test can mask production bugs where code forgets to commit, or behave differently from real commits. Also test actual committed transactions.

### 44.4. Do Not Share Mutable Test Data Arbitrarily Across Parallel Workers

Concurrent tests can make total-balance assertions flaky. Use isolated fixtures, transactions, or test schemas.

## 45. Common Anti-Patterns

### Mistake 1. Leaving `autocommit=true`, Running Multiple SQLs, and Expecting Atomicity

Each statement can commit separately. Disable autocommit or use a transaction manager.

### Mistake 2. Forgetting `commit()`

Uncommitted changes do not become durable merely because a Java method returns.

### Mistake 3. Forgetting `rollback()` on Exception

The transaction can remain active or aborted until the connection is cleaned up; never depend on pool cleanup.

### Mistake 4. Unconditional `setAutoCommit(true)` in `finally`

Can commit an active transaction unexpectedly even when business logic failed.

### Mistake 5. Treating `close()` as Business Commit/Rollback

`close()` releases/returns the resource; your code must decide the transaction outcome first.

### Mistake 6. Each Helper Opening Its Own `Connection`

Debit and credit end up in two separate transactions.

### Mistake 7. Ignoring `executeUpdate()` Return Counts

An `UPDATE` affecting 0 rows completes without throwing an exception. Never assume funds were debited solely because no `SQLException` occurred.

### Mistake 8. Using `double` for Money

`double` introduces binary rounding errors. Use `BigDecimal` and `numeric` with explicit rounding rules.

### Mistake 9. Concatenating Input Strings Into SQL

Creates SQL injection risks. Use `PreparedStatement` with placeholders.

### Mistake 10. Catching `SQLException` and Continuing on an Aborted Transaction

PostgreSQL returns `25P02` for subsequent statements; roll back fully or to a savepoint.

### Mistake 11. Using `Savepoint` Instead of `commit()`

Savepoints only enable partial rollback; they do not commit business work.

### Mistake 12. Catching an Optional Error Without `rollback(savepoint)`

The transaction remains aborted in PostgreSQL even though Java caught the exception.

### Mistake 13. Committing After a Mandatory Step Fails

For instance, committing balance updates when the ledger insert failed breaks invariants.

### Mistake 14. Calling `commit()` Inside Framework `@Transactional`

Prematurely commits before the framework completes its unit of work.

### Mistake 15. Using Standalone `DriverManager` Inside a Spring Transaction

The new connection does not join the active Spring transaction context.

### Mistake 16. Changing Isolation/Read-Only Mid-Transaction

Behavior depends on the driver and breaks transaction contracts.

### Mistake 17. Failing to Reset Pooled Connection State

Later requests inherit non-baseline `autoCommit`/`readOnly`/isolation/`search_path`.

### Mistake 18. Returning `ResultSet` Beyond `Connection` Scope

Resources are already closed and cannot be safely read after the method returns.

### Mistake 19. Not Closing `PreparedStatement`

Retains JDBC resources and can contribute to memory/server-state leaks.

### Mistake 20. Holding a `Connection` While Waiting on HTTP

Ties up pool capacity and extends transaction/lock lifetimes.

### Mistake 21. Sharing a `Connection` Across Threads

Transactions and statements from concurrent requests interleave, committing or rolling back each other's work.

### Mistake 22. Setting Timeouts Without Rolling Back After Cancellation

The transaction can enter an aborted state after `57014`; never continue as if nothing failed.

### Mistake 23. Calling `setFetchSize(500)` Thinking It Caps Total Results to 500

Fetch size controls batch streaming, not SQL `LIMIT`.

### Mistake 24. Streaming Millions of Rows Inside a Long-Lived Transaction

Holds snapshots and connections open, impacting pools, vacuum, and locks.

### Mistake 25. Retrying Only One Statement After `40001`

Must roll back and retry the entire transaction and all business decisions.

### Mistake 26. Retrying a Transfer When Commit Outcome Is Unknown

Can transfer twice. Requires idempotency/reconciliation.

### Mistake 27. Relying on Gapless Sequences to Verify Correctness

Sequences do not roll back; gaps occur normally without losing data.

### Mistake 28. Assuming `SERIALIZABLE` Fixes Multi-Connection Transaction Mistakes

Isolation never repairs broken transaction boundaries.

### Mistake 29. Treating `setReadOnly(true)` as Complete Access Security

`setReadOnly(true)` does not replace `GRANT`/RLS.

### Mistake 30. Inflating Pool Size to Hide a Connection Leak

Only delays pool exhaustion while overloading PostgreSQL. Fix the resource lifecycle.

## 46. Practice Exercises

Exercises are based on the `jdbc_lab` schema or sample code in this lesson. Any exercise involving transfer writes must run on a **lab** database, never against real accounts.

### Exercise 1. JDBC Resources

List the roles of `DataSource`, `Connection`, `PreparedStatement`, and `ResultSet`.

### Exercise 2. Default Autocommit

If `getAutoCommit()` is true, do two consecutive `UPDATE`s automatically form one atomic transaction?

### Exercise 3. Disabling Autocommit

Write Java code to turn off autocommit on a `Connection`.

### Exercise 4. Commit

Which JDBC call commits a transaction? After `commit()`, does `autocommit=false` automatically switch back to `true`?

### Exercise 5. Rollback

Write a `catch` block that preserves the original exception and records any rollback failure as a suppressed exception.

### Exercise 6. Switching `autoCommit`

Why can `setAutoCommit(true)` inside a `finally` block be dangerous?

### Exercise 7. One Connection

Why must debit, credit, and ledger insert in a transfer share the same `Connection`?

### Exercise 8. `PreparedStatement`

Write an `UPDATE` statement updating an account's balance using placeholders instead of concatenating IDs or amounts.

### Exercise 9. `executeUpdate`

If an `UPDATE` with `WHERE balance >= ?` returns 0 rows, how should the program interpret it?

### Exercise 10. Money Type

Why use `BigDecimal` and PostgreSQL `numeric` for money instead of `double`?

### Exercise 11. Lab SQL

Write SQL to sum all balances and list the most recent transfers.

### Exercise 12. Success

Starting from balances (500, 150), after transferring 125 from 1001 to 1002, what is the expected state?

### Exercise 13. Insufficient Funds

Transfer 900 from account 1001 when its balance is 375. How does the `debit` code handle this?

### Exercise 14. Ledger Failure

If the ledger `INSERT` fails after debit and credit, what are the source and destination balances after rollback?

### Exercise 15. `try-with-resources`

Write code opening a `Connection`, `PreparedStatement`, and `ResultSet` with proper scoped closing.

### Exercise 16. `ResultSet` Scope

Why should a repository not return a `ResultSet` after closing the connection?

### Exercise 17. Pool `close()`

What does `connection.close()` normally mean on a pooled connection handle?

### Exercise 18. Pool Leak

If 100 requests acquire connections without closing them, what symptoms occur?

### Exercise 19. PostgreSQL `25P02`

A transaction raises a unique violation, and the next `SELECT` reports `25P02`. What is the basic recovery command?

### Exercise 20. `Savepoint`

Write Java code that sets a savepoint and rolls back only the sub-step.

### Exercise 21. Optional Step

When is it valid to call `rollback(savepoint)` and still commit the overall transaction?

### Exercise 22. `SERIALIZABLE`

Why might a `SERIALIZABLE` transaction need to be retried upon encountering `40001`?

### Exercise 23. `READ UNCOMMITTED`

Under which isolation semantics does PostgreSQL execute `READ UNCOMMITTED`?

### Exercise 24. `SQLSTATE`

Distinguish `23505`, `40P01`, `40001`, and `25P02`.

### Exercise 25. Retry

Why can you not retry only the last `UPDATE` after a transaction hits a serialization failure?

### Exercise 26. Ambiguous Commit

The client loses network connectivity right after sending `COMMIT`. Can you be certain the server did not commit?

### Exercise 27. Idempotency

Why is `business_request_id UNIQUE` helpful when a money transfer must be retried?

### Exercise 28. Timeouts

State the differences among `setQueryTimeout`, `lock_timeout`, and pool acquisition timeout.

### Exercise 29. `SET LOCAL`

Write SQL setting `statement_timeout=5s` only for the current transaction.

### Exercise 30. Streaming

Why does PGJDBC cursor streaming typically require `setAutoCommit(false)` and `setFetchSize(500)`?

### Exercise 31. `FetchSize`

Does `setFetchSize(500)` mean the query returns at most 500 rows?

### Exercise 32. Thread Safety

Why should two concurrent requests never share one transactional `Connection`?

### Exercise 33. Spring `@Transactional`

Inside a Spring `@Transactional` method, should you call `connection.commit()` manually?

### Exercise 34. Spring Self-Invocation

Why might calling `this.innerTransactionalMethod()` fail to start a new transaction in proxy-based Spring?

### Exercise 35. Monitoring

Write SQL to find `idle in transaction` sessions and their transaction start times.

### Exercise 36. Lock Wait

Write SQL listing `pid` and `pg_blocking_pids(pid)` to investigate lock waits.

### Exercise 37. `pg_stat_database`

Which two counters track cumulative commits and rollbacks in a database?

### Exercise 38. Batch

Does `executeBatch()` eliminate the need for `commit()` when autocommit is false?

### Exercise 39. Read-Only

Does `setReadOnly(true)` replace `GRANT` and RLS?

### Exercise 40. Design

List at least eight items for a checklist covering safe transaction and JDBC resource management in a production service.

## 47. Reference Solutions

### Exercises 1–2. Resources and Autocommit

`DataSource` provides `Connection`s, `Connection` manages session/transactions, `PreparedStatement` binds SQL parameters, and `ResultSet` reads rows. With `autocommit=true`, two `UPDATE`s typically commit separately; atomicity across both is not guaranteed.

### Exercises 3–4. Disabling Autocommit and Committing

~~~java
connection.setAutoCommit(false);
// Execute statements for one unit of work.
connection.commit();
~~~

After `commit()`, the connection stays in `autocommit=false` until changed or reset by the pool/framework per contract.

### Exercise 5. Rollback Preserving Errors

~~~java
catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
}
~~~

### Exercise 6. `setAutoCommit(true)`

Switching from `false` to `true` while a transaction is active can commit that transaction. Never use it unconditionally as cleanup when a transaction has not yet been terminated.

### Exercise 7. One Connection

A PostgreSQL transaction is bound to a single connection/backend. Rolling back on connection A will not undo SQL committed on connection B.

### Exercise 8. Parameterized `UPDATE`

~~~java
String sql =
    "UPDATE jdbc_lab.accounts " +
    "SET balance = balance - ? " +
    "WHERE account_id = ? AND balance >= ?";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setLong(2, accountId);
    ps.setBigDecimal(3, amount);
    int updated = ps.executeUpdate();
}
~~~

### Exercises 9–10. Update Counts and Money

`0` rows means the `WHERE` condition was unmet or the row does not exist, requiring business error handling rather than committing silently. `BigDecimal` avoids binary floating-point error from `double` and aligns with `numeric`.

### Exercise 11. Lab Queries

~~~sql
SELECT sum(balance) AS total_balance
FROM jdbc_lab.accounts;

SELECT transfer_id, from_account_id,
       to_account_id, amount
FROM jdbc_lab.transfers
ORDER BY transfer_id DESC;
~~~

### Exercises 12–14. Transactions

Successful transfer of 125: source 375.00, destination 275.00, total 650.00, and one ledger row. With insufficient funds, debit updates 0 rows and throws; if ledger fails, rollback undoes both uncommitted debit and credit.

### Exercise 15. Closing Resources

~~~java
try (Connection conn = ds.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT balance FROM jdbc_lab.accounts " +
         "WHERE account_id = ?"
     )) {
    ps.setLong(1, 1001L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            BigDecimal balance = rs.getBigDecimal(1);
        }
    }
}
~~~

### Exercises 16–18. Pool Lifecycle

`ResultSet` requires a valid `Statement` and `Connection`. `close()` on a pooled handle normally returns the connection to the pool. Forgetting `close()` exhausts free connections, causing requests to wait or time out.

### Exercise 19. Aborted Transaction

~~~java
connection.rollback();
~~~

Or roll back to a savepoint created before the error if business rules allow. Never continue executing SQL on an aborted transaction.

### Exercises 20–21. Savepoint

~~~java
Savepoint sp = connection.setSavepoint();
try {
    insertOptionalRecord(connection);
} catch (SQLException ex) {
    connection.rollback(sp);
}
~~~

You can then commit the main transaction **only if** the optional step is allowed to fail without violating business correctness.

### Exercises 22–23. Isolation

`SERIALIZABLE` can detect conflicts and raise `40001`, requiring rollback and full-transaction retry. PostgreSQL handles `READ UNCOMMITTED` with `READ COMMITTED` semantics.

### Exercise 24. `SQLSTATE`

`23505`: unique violation; `40P01`: deadlock; `40001`: serialization failure; `25P02`: transaction aborted.

### Exercises 25–27. Retries and Idempotency

After `40001`, the old transaction cannot commit, so it must restart from the beginning and re-evaluate decisions from fresh reads. When a commit response is lost, the server may have already succeeded; a stable request ID with a `UNIQUE` constraint enables status checking/reconciliation and prevents double execution.

### Exercise 28. Timeouts

`setQueryTimeout` bounds statement execution in the driver; `lock_timeout` bounds lock waiting in PostgreSQL; pool acquisition timeout bounds waiting to borrow a connection.

### Exercise 29. `SET LOCAL`

~~~sql
SET LOCAL statement_timeout = '5s';
~~~

Runs inside a transaction without persisting as a session setting for the next pool borrower.

### Exercises 30–31. Streaming

PGJDBC cursor-based fetching generally requires a transaction to keep the cursor alive and a positive `fetchSize` to pull rows in chunks. `setFetchSize(500)` is not `LIMIT 500`; it does not cap total rows.

### Exercise 32. Connection Threads

Two requests sharing one connection can share a transaction, causing one to commit/roll back the other's work and race on `Statement`/`ResultSet`.

### Exercises 33–34. Spring

Never call `commit()` manually inside a Spring-managed transaction. In proxy-based Spring, self-invocation `this.method()` bypasses the proxy so the called method's `@Transactional` interceptor does not run.

### Exercise 35. `idle in transaction`

~~~sql
SELECT pid, application_name, xact_start,
       state, wait_event_type, wait_event
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

### Exercise 36. Blocking PIDs

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
~~~

### Exercise 37. Commit/Rollback Counters

~~~sql
SELECT xact_commit, xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
~~~

### Exercise 38. Batch

No. With `autocommit=false`, `executeBatch()` still requires `commit()` or `rollback()` per business logic.

### Exercise 39. Read-Only

No. `setReadOnly(true)` is a JDBC state/hint applied by PostgreSQL/driver in context; it does not replace security grants or RLS.

### Exercise 40. Checklist

One solid set: (1) business boundaries; (2) single `Connection`; (3) explicit autocommit; (4) single `commit()`; (5) rollback on error; (6) check update counts; (7) `PreparedStatement`; (8) `try-with-resources`; (9) pool reset; (10) timeouts; (11) isolation/locks; (12) idempotency; (13) `SQLSTATE`/retries; (14) `idle in transaction` monitoring; (15) integration tests.

## 48. Quick Reference Table

| Need | JDBC / SQL |
| --- | --- |
| Check autocommit | `connection.getAutoCommit()` |
| Group statements in a transaction | `connection.setAutoCommit(false)` |
| Commit transaction | `connection.commit()` |
| Roll back full transaction | `connection.rollback()` |
| Create savepoint | `connection.setSavepoint()` |
| Roll back work after savepoint | `connection.rollback(savepoint)` |
| Release savepoint | `connection.releaseSavepoint(savepoint)` |
| Read isolation level | `connection.getTransactionIsolation()` |
| Set isolation level | `connection.setTransactionIsolation(...)` |
| Mark read-only | `connection.setReadOnly(true)` |
| Close resources safely | `try (...) { ... }` |
| Bind SQL parameters | `PreparedStatement` + `setLong`/`setBigDecimal` |
| DML affected row count | `executeUpdate()` |
| Read `SQLSTATE` | `SQLException.getSQLState()` |
| Return PostgreSQL values from `INSERT` | `INSERT ... RETURNING` + `executeQuery()` |
| Lock a row | `SELECT ... FOR UPDATE` |
| Limit JDBC query time | `Statement.setQueryTimeout(seconds)` |
| Limit server query time per transaction | `SET LOCAL statement_timeout` |
| Limit lock wait time | `SET LOCAL lock_timeout` |
| Prevent long `idle in transaction` | `idle_in_transaction_session_timeout` |
| Batching | `addBatch()`/`executeBatch()` |
| Chunked streaming/fetching | `setFetchSize(n)` + `autocommit=false` per PGJDBC |
| Spring transaction management | `@Transactional` / `TransactionTemplate` |
| Inspect sessions/transactions | `pg_stat_activity` |
| Inspect locks | `pg_locks` / `pg_blocking_pids()` |
| Inspect total commits/rollbacks | `pg_stat_database` |
| Retry serialization failure | `SQLSTATE` `40001`, retry full transaction |
| Retry deadlock | `SQLSTATE` `40P01`, roll back and bounded retry |
| Aborted transaction | `SQLSTATE` `25P02` |

## 49. Production JDBC Transaction Deployment Checklist

1. **Which statements belong to one business unit?** Is full atomicity required?
2. Do all those statements run on the **same `Connection`**?
3. Is autocommit enabled/disabled by the single transaction owner?
4. Is there a single `commit()` path when all steps succeed?
5. Is there a `rollback()` path for both `SQLException` and runtime business failures?
6. Are rollback exceptions handled without masking the original cause?
7. Is unconditional `setAutoCommit(true)` avoided while a transaction is active?
8. Is `try-with-resources` used for `Connection`/`Statement`/`ResultSet`?
9. Are `ResultSet` or `Connection` never returned beyond their managed lifecycle?
10. Are `executeUpdate()` counts verified against expected row counts?
11. Is parameterized SQL used instead of string concatenation?
12. Is `BigDecimal` with scale/range validation used for monetary amounts?
13. Are DB `CHECK`/`FK`/`UNIQUE` constraints in place to back invariants?
14. Is lock ordering consistent across competing transactions?
15. Does the isolation level match requirements, with retries for `40001`?
16. Is `SQLSTATE` `25P02` handled cleanly after SQL errors?
17. Are savepoints restricted to genuinely optional steps?
18. Is idempotency implemented for operations that must not execute twice?
19. Are ambiguous commit outcomes on connection loss handled?
20. Are pool limits sized properly and monitored for active/idle/waiting/leaks?
21. Does the pool/framework reset `autoCommit`/`isolation`/`readOnly`/session state?
22. Are network calls and heavy CPU work kept outside open transactions?
23. Are timeouts set across pool, network, query, and lock layers?
24. Do streaming `ResultSet`s have reasonable transaction durations and fetch sizes?
25. Is sharing a `Connection` across threads prevented?
26. When using Spring, is transaction ownership clear (framework vs. manual JDBC)?
27. Are Spring self-invocation, exception rollback, and propagation behaviors tested?
28. Are `application_name` and observability configured for JDBC sessions?
29. Are alerts configured for `idle in transaction` and long-running transactions?
30. Are there integration tests for commit, rollback, deadlocks, and resource cleanup?

## 50. Summary

Managing transactions over JDBC is more than calling `setAutoCommit(false)`, `commit()`, and `rollback()`. You must define **business boundaries**, keep all statements on **one `Connection`**, handle errors that put PostgreSQL transactions into an aborted state, and close resources promptly.

Core principles:

1. **`autocommit=true`** fits independent statements, yet does not guarantee atomicity across multi-statement business operations.
2. **`autocommit=false`** lets the application commit or roll back a group of SQL statements together. Every exit path must be explicit; never treat `Connection.close()` or `setAutoCommit(true)` as substitutes for transaction decisions.
3. **Rollback on error** must cover both SQL exceptions and runtime business exceptions; after a SQL error in PostgreSQL, the transaction can enter `25P02` until rolled back fully or to a savepoint.
4. **`try-with-resources`** protects the lifecycles of `ResultSet`, `PreparedStatement`, and `Connection`, which is critical with connection pools. Resource cleanup and transaction outcome are **two distinct responsibilities**.
5. **Concurrency and retries** still require deliberate design: row locking, isolation, deadlock/serialization errors, idempotency, and ambiguous commit outcomes are not solved automatically by the JDBC API.
6. **Framework transaction managers** such as Spring must own commit/rollback when used; never mix them carelessly with manual JDBC transaction calls.

When reviewing database code, ask: **"Which changes must succeed together?", "Who owns this `Connection` and transaction?", "Does every error path roll back before returning the `Connection`?", and "If connectivity drops right at `COMMIT`, can the business logic check status and retry without executing twice?"** Answering those four questions cleanly is the foundation for building Java–PostgreSQL applications that preserve data integrity, stay observable, and withstand real-world failures.
