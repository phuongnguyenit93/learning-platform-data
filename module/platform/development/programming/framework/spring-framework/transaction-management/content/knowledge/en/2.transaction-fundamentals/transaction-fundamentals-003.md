# Auto-Commit and Multiple Statements on the Same Connection

> **Context:** Spring Framework — Transaction Management → Transaction Fundamentals. This lesson explains why multiple SQL statements executed over the same JDBC `Connection` can still belong to different transactions, how to control `commit`/`rollback`, and how Spring manages transaction boundaries.

## 1. Distinguishing connection, statement, and transaction

Three related concepts that are not synonymous:

- **Connection (JDBC `Connection`):** the session an application uses to send SQL to the database. One connection can execute many statements over time.
- **Statement (SQL statement):** a `SELECT`, `INSERT`, `UPDATE`, `DELETE`... operation executed through `Statement` or `PreparedStatement`.
- **Transaction:** a unit of work confirmed with `COMMIT` or discarded with `ROLLBACK`. When the database and operations support transactions, changes in the same transaction are committed together or rolled back together.

**The same `Connection` does not mean the same transaction.** Transaction boundaries depend on auto-commit mode, `commit()`/`rollback()` calls, or a transaction manager (such as Spring). One `Connection` can sequentially serve transactions T1, T2, and T3.

Consider a business operation transferring 30 monetary units between two accounts with initial balances A = 100 and B = 100:

```sql
UPDATE accounts SET balance = balance - 30 WHERE id = 1;
UPDATE accounts SET balance = balance + 30 WHERE id = 2;
```

The business invariant is that the sum A + B remains 200 if the whole transfer succeeds. If the debit statement succeeds and commits while the credit statement fails, A = 70 and B = 100: invalid data. Therefore, **both statements must share one transaction**, not just one connection.

## 2. What does auto-commit in JDBC actually do?

By the JDBC contract, a newly created `Connection` defaults to `autoCommit = true`; application code can check with `connection.getAutoCommit()`. With `autoCommit = true`, **each completed SQL statement is committed as its own transaction**. This is the JDBC rule; when using a connection pool or Spring, the connection state you obtain may already have been reconfigured, so never guess its actual state.

```java
boolean enabled = connection.getAutoCommit();
connection.setAutoCommit(true);  // Each statement is a separate transaction.
connection.setAutoCommit(false); // The application must explicitly commit/rollback.
```

The snippet above illustrates the API of an existing `Connection`, not a standalone runnable Java program.

### Two statements on the same connection, auto-commit enabled

```text
Connection C1, autoCommit = true

UPDATE A = A - 30  ── succeeded ── COMMIT T1
UPDATE B = B + 30  ── error ────── T2 not committed
                                      |
Result: T1 still persists; rolling back T2 cannot undo T1.
```

In that situation, calling `rollback()` after the error **cannot reverse the first already-committed statement**. Moreover, JDBC does not permit calling `commit()`/`rollback()` while the connection is in auto-commit mode (the driver throws an API error). You must disable auto-commit *before* executing statements belonging to a single unit of work.

### Two statements on the same connection, auto-commit disabled

```text
Connection C1, autoCommit = false

Start transaction T1 when SQL work begins
    |
    +-- UPDATE A = A - 30 ── succeeded (not yet committed)
    |
    +-- UPDATE B = B + 30 ── succeeded (not yet committed)
    |
    +-- COMMIT ──────────── both changes are confirmed

If the second statement fails:
    +-- ROLLBACK ────────── undoes the first change as well
```

When `autoCommit = false`, statements executed after a commit/rollback boundary belong to the next transaction according to JDBC/DBMS mechanics; each `executeUpdate()` call is not an independent transaction.

### When exactly does auto-commit happen?

JDBC defines when a statement completes:

| Operation type | When is the statement considered complete for auto-commit? |
| --- | --- |
| `INSERT`, `UPDATE`, `DELETE` | When the operation finishes executing. |
| `SELECT` returning a `ResultSet` | When the associated `ResultSet` has been closed. |
| `CallableStatement` or multi-result statements | After all associated `ResultSet`s have been closed and all results/update counts/output parameters have been retrieved. |

This detail matters when holding a `ResultSet` open for a long time: executing `executeQuery()` does not mean the auto-commit transaction always ends right at that call. Use `try-with-resources` to close resources promptly.

## 3. Comparison table of commonly confused scenarios

| Scenario | Same connection? | One transaction for both SQLs? | If the second SQL fails |
| --- | --- | --- | --- |
| JDBC `autoCommit=true`, execute 2 `UPDATE`s | Yes | **No** | First SQL is already committed if it completed successfully |
| JDBC `autoCommit=false`, 2 `UPDATE`s, then `commit()` | Yes | **Yes** | Call `rollback()` before commit to discard both |
| JDBC `autoCommit=false` but `commit()` after the first SQL | Yes | **No** | First SQL is already committed |
| 2 independent `Connection`s, each committing on its own | No | **No** | No shared rollback via local JDBC |
| Spring `@Transactional` active, both JDBC ops use the right datasource/tx manager | Spring manages the transaction-bound connection | **Yes**, with appropriate propagation | Rolled back per the transaction manager's policy |

Auto-commit mode does not determine the **isolation level** (`READ_COMMITTED`, `REPEATABLE_READ`, ...) nor does it solve deadlocks, lost updates, or concurrency issues. Atomicity and isolation are two separate aspects.

## 4. Running a complete JDBC example on Java 17+

The example uses an **H2 in-memory database** so it can run standalone without installing a database server. H2 is an external JDBC driver outside the JDK; Java SE only provides `java.sql` APIs and does not bundle the H2 driver.

Create `AutoCommitDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class AutoCommitDemo {
    // DB_CLOSE_DELAY=-1 keeps the in-memory database alive when
    // all connections close, until the JVM exits.
    private static final String URL =
            "jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1";

    public static void main(String[] args) throws SQLException {
        initialize();

        demoAutoCommit();
        resetBalances();

        demoRollback();
        demoCommit();
    }

    private static Connection open() throws SQLException {
        return DriverManager.getConnection(URL, "sa", "");
    }

    private static void initialize() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL CHECK (balance >= 0)
                    )
                    """);
            s.executeUpdate("""
                    INSERT INTO accounts (id, balance)
                    VALUES (1, 100), (2, 100)
                    """);
        }
    }

    private static void resetBalances() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("UPDATE accounts SET balance = 100");
        }
    }

    private static void demoAutoCommit() throws SQLException {
        try (Connection c = open()) {
            // Newly created connection from DriverManager: autoCommit = true.
            try {
                adjustBalance(c, 1, -30);
                insertDuplicateId(c); // Intentionally violates PRIMARY KEY.
            } catch (SQLException expected) {
                System.out.println("Auto-commit: second statement failed");
            }
        }
        printBalances("After error with auto-commit");
    }

    private static void demoRollback() throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                adjustBalance(c, 1, -30);
                insertDuplicateId(c); // Causes an error in the same transaction.
                c.commit();           // Never reaches here.
            } catch (SQLException expected) {
                c.rollback();
                System.out.println("Manual transaction: ROLLBACK");
            }
        }
        printBalances("After rollback");
    }

    private static void demoCommit() throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                adjustBalance(c, 1, -30);
                adjustBalance(c, 2, 30);
                c.commit();
                System.out.println("Manual transaction: COMMIT");
            } catch (SQLException error) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
        printBalances("After commit");
    }

    private static void adjustBalance(
            Connection c, int accountId, int delta)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
            p.setInt(1, delta);
            p.setInt(2, accountId);

            if (p.executeUpdate() != 1) {
                throw new SQLException("Unknown account: " + accountId);
            }
        }
    }

    private static void insertDuplicateId(Connection c)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO accounts (id, balance) VALUES (1, 999)")) {
            p.executeUpdate(); // id=1 already exists, so H2 throws SQLException.
        }
    }

    private static void printBalances(String label)
            throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(
                     "SELECT id, balance FROM accounts ORDER BY id")) {
            if (!rs.next()) {
                throw new SQLException("Missing account 1");
            }
            int a = rs.getInt("balance");

            if (!rs.next()) {
                throw new SQLException("Missing account 2");
            }
            int b = rs.getInt("balance");

            System.out.printf("%s: A=%d, B=%d%n", label, a, b);
        }
    }
}
```

**Prepare the driver** using Maven with Internet access (or manually download `h2-2.3.232.jar` from Maven Central):

```bash
mvn dependency:copy -Dartifact=com.h2database:h2:2.3.232 -DoutputDirectory=.
javac -encoding UTF-8 -cp h2-2.3.232.jar AutoCommitDemo.java
```

Run on **Windows PowerShell/CMD** (classpath uses `;`):

```powershell
java -cp ".;h2-2.3.232.jar" AutoCommitDemo
```

Run on **Linux/macOS** (classpath uses `:`):

```bash
java -cp ".:h2-2.3.232.jar" AutoCommitDemo
```

Expected output:

```text
Auto-commit: second statement failed
After error with auto-commit: A=70, B=100
Manual transaction: ROLLBACK
After rollback: A=100, B=100
Manual transaction: COMMIT
After commit: A=70, B=130
```

**Analysis of each run:**

1. `demoAutoCommit()` uses a new connection with auto-commit enabled. `adjustBalance()` reduces A to 70 and is committed. `insertDuplicateId()` intentionally violates the primary key and throws `SQLException`. Even though both statements use the same `c`, the first change persists.
2. `resetBalances()` resets both accounts to 100 so the next two experiments share the same starting point.
3. `demoRollback()` disables auto-commit before updating A. The error in the second statement triggers `rollback()`, returning A to 100; B is unchanged.
4. `demoCommit()` updates both A and B and then calls `commit()` once: A = 70, B = 130. `printBalances()` uses another connection to observe the confirmed data.

**Example limitations:** `int` values are used for small balances to illustrate transactions; in real-world monetary domains, use an appropriate decimal type (such as `DECIMAL` in SQL and `BigDecimal` in Java), rounding rules, balance checks, and anti-duplicate-processing policies.

## 5. Safe manual JDBC transaction management pattern

With plain JDBC, the common pattern is: acquire connection → disable auto-commit → run all operations → commit on success → roll back on error → close resources. Control the transaction at **only one place that owns the transaction boundary**.

```java
// Function outline: dataSource, debit(), and credit() are declared
// in the application; this snippet is not a standalone program.
void transfer(javax.sql.DataSource dataSource) throws SQLException {
    try (Connection c = dataSource.getConnection()) {
        boolean previousAutoCommit = c.getAutoCommit();

        try {
            c.setAutoCommit(false);
            debit(c);
            credit(c);
            c.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                c.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            // Only restore after the transaction has committed/rolled back.
            if (c.getAutoCommit() != previousAutoCommit) {
                c.setAutoCommit(previousAutoCommit);
            }
        }
    }
}
```

**Usage conditions:** the pattern above is for code that **self-manages** an independent JDBC connection outside a Spring-managed transaction. `debit(c)` and `credit(c)` must use the exact parameter `c`; if each method calls `dataSource.getConnection()` on its own, they may run on different connections/transactions. In production, clearly design error handling when rollback or state restoration fails; do not let cleanup errors mask the root cause.

Two important pitfalls:

- **Do not re-enable auto-commit before rolling back.** Per JDBC, changing auto-commit mode while a transaction is active causes the transaction to commit. Thus, calling `setAutoCommit(true)` in `finally` before `rollback()` can turn a failed transaction into a committed one.
- **Do not rely on `close()` to automatically roll back.** JDBC does not specify a single uniform outcome when closing a connection with an active transaction; always finish the transaction explicitly before returning the connection to the pool or closing it.

If a transaction encounters `SQLException` and code catches and **swallows the error**, control flow can proceed straight to `commit()`. Always define which errors require rollback and rethrow or mark rollback appropriately.

## 6. How does Spring manage auto-commit and connections?

In a Spring application using JDBC, `@Transactional` establishes transaction boundaries **at method calls through a Spring proxy** (in default proxy mode). An appropriate `PlatformTransactionManager`, such as `JdbcTransactionManager` or `DataSourceTransactionManager`, coordinates acquiring the connection, configuring transaction state, committing/rolling back, and cleaning up when the method finishes.

When a JDBC transaction is active on the same `DataSource`, `JdbcTemplate` uses `DataSourceUtils` to participate in the connection bound to the current transaction. Consequently, multiple `jdbcTemplate.update(...)` calls inside a `@Transactional` method can run within **the same physical transaction**. This mechanism does not mean every statement across every datasource or every connection in the application shares one transaction.

### Spring JDBC example: one transfer is one transaction

This is a service class intended for a **Spring application already configured** with a `DataSource`, `JdbcTemplate`, transaction management, and table `accounts(id, balance)`. It cannot run standalone without the Spring environment and database.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
                """
                UPDATE accounts
                SET balance = balance - ?
                WHERE id = ? AND balance >= ?
                """,
                amount, fromId, amount);

        if (debited != 1) {
            throw new IllegalStateException(
                    "Source account missing or insufficient balance");
        }

        int credited = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);

        if (credited != 1) {
            throw new IllegalStateException(
                    "Destination account missing");
        }
    }
}
```

When another bean calls `transferService.transfer(...)` through the Spring proxy, the manager starts or joins a transaction before running the method body. If both `UPDATE`s succeed and the method ends normally, the transaction is committed. If the second statement updates zero rows, the code throws `IllegalStateException`; by default Spring marks rollback for runtime exceptions, so both updates are rolled back.

The return value of `JdbcTemplate.update` is the number of affected rows. Checking `!= 1` prevents a very common business bug: SQL executes without throwing an exception yet updates no target row; without checking, half of the operation could still be committed.

**Why not call `connection.setAutoCommit(false)` manually here?** When Spring owns the transaction, the transaction manager must own starting and ending it. Calling `commit()`/`rollback()` or changing auto-commit directly in the repository layer can break Spring's coordinated boundaries.

### Conditions for `@Transactional` to actually take effect

1. **The call must pass through the proxy.** In regular proxy mode, only calls from another bean to a Spring-managed method are intercepted. Calling `this.transfer(...)` within the same object (*self-invocation*) does not automatically trigger transaction advice for the target method.
2. **Resources must participate in the right manager.** `JdbcTemplate` must use the `DataSource` managed by the transaction manager. Manually opening a connection with `DriverManager.getConnection(...)`, or fetching another connection outside the transaction mechanism, will not automatically join the current Spring transaction.
3. **Propagation can change boundaries.** Default `Propagation.REQUIRED` joins an existing transaction or creates a new one if none exists. `REQUIRES_NEW` creates its own transaction and suspends the outer one; you cannot assume two consecutive service method calls always share one transaction.
4. **Rollback rules must be understood accurately.** `@Transactional` defaults to rolling back on `RuntimeException` and `Error`; checked `Exception`s do not automatically trigger rollback. You can configure `rollbackFor = Exception.class` as needed. Catching an error and returning normally allows Spring to commit, unless the transaction was marked rollback-only or configured otherwise.
5. **Do not mix transaction models.** This imperative JDBC example applies to Spring's thread-bound transactions. R2DBC/reactive binds transactions to the reactive context and cannot be reasoned about identically to thread-bound JDBC connections.

A single database transaction does not automatically roll back external side effects such as HTTP calls, sending emails, or writing to an independent data system not coordinated in the same transaction.

## 7. Common cases that break atomicity

### Calling `commit()` mid-way

```java
connection.setAutoCommit(false);
debit(connection);
connection.commit(); // T1 has ended.
credit(connection);   // Belongs to the next transaction.
connection.rollback(); // Only rolls back the uncommitted part of T2.
```

Illustrative code only; `debit`/`credit` are hypothetical functions receiving the same connection. Calling `commit()` between two operations splits the business action into two transactions regardless of whether the connection stays the same.

### Using two different connections

```java
try (Connection c1 = dataSource.getConnection();
     Connection c2 = dataSource.getConnection()) {
    // c1 and c2 are independently acquired connections.
    // committing c1 does not automatically commit/roll back c2.
}
```

Two logical connections in certain environments might be specially managed by the container, but **you must never assume** they belong to the same local JDBC transaction. In plain JDBC, to keep multiple statements in one transaction, pass the same connection and control commit at a shared point; in Spring, rely on the framework's transaction participation mechanism.

### Catching an error and still committing

```java
connection.setAutoCommit(false);
debit(connection);
try {
    credit(connection);
} catch (SQLException ignored) {
    // Wrong: the error was ignored.
}
connection.commit(); // May confirm only the debit operation.
```

Not every `SQLException` automatically rolls back the entire transaction. Some DBMSs put the transaction into an error state requiring rollback; that still **does not** replace an explicit error-handling policy in the application.

### Confusing `executeBatch()` with a transaction

`executeBatch()` groups statements to send/execute more efficiently, yet **batching does not guarantee atomicity of the entire batch across all modes/drivers/DBMSs**. `autoCommit=true` and `BatchUpdateException` can lead to partially executed states depending on the driver and database. If the whole batch must succeed or fail together, place it inside an application- or Spring-managed transaction and handle rollback.

### Confusing a transaction with an HTTP request

A single request may invoke multiple repositories, datasources, or services. An HTTP request is **not automatically** one database transaction. Transaction scope should align with the business unit requiring atomicity and avoid holding transactions open across slow network operations unnecessarily.

## 8. Inspection and troubleshooting

When half the data changes despite two SQL statements running back-to-back, check in order:

1. **Is one connection actually participating?** In plain JDBC, trace the connection object passed to each DAO. In Spring, verify the same `DataSource`/transaction manager and proper use of `JdbcTemplate` or `DataSourceUtils`.
2. **What is auto-commit at execution time?** `getAutoCommit()` helps diagnose plain JDBC; avoid directly mutating the state of a Spring-managed connection just to test.
3. **Did `commit` or an `autoCommit` change happen early?** Look for mid-way `commit()` calls, self-committing helpers, `setAutoCommit(true)` before rollback, and library mechanisms creating separate transactions.
4. **Was `@Transactional` actually intercepted?** Check how the bean is instantiated/called, self-invocation, transaction management configuration, propagation, and manager.
5. **Did the error escape the boundary?** Check caught/swallowed exceptions, checked exceptions and rollback rules, or branches returning normally after an error.
6. **Did the operation actually affect the expected rows?** Check update counts, database constraints, and `WHERE` clauses. No exception does not guarantee the expected change occurred.
7. **Do the database and operation support transactions?** Certain DDLs, storage engines, or non-database operations have their own commit/rollback rules. Check the specific DBMS documentation before claiming every SQL statement can roll back.
8. **Is there contention between transactions?** If operations do not error yet produce wrong results concurrently, inspect isolation levels, locking, lost updates, deadlocks, and business-level retry strategies.

### Minimum test scenarios

- **Success:** both debit and credit complete; total balance before/after is unchanged and both changes are visible after commit.
- **Error on the second statement:** intentionally trigger a SQL error or throw a runtime exception; verify both balances remain unchanged after rollback.
- **Destination account not found:** `UPDATE` returns 0; verify the debit is not committed.
- **Nested service calls:** verify desired propagation (e.g., `REQUIRED` vs. `REQUIRES_NEW`).
- **Two concurrent requests:** protect balance invariants and separately test isolation/locking policies; atomicity of each transaction alone does not solve all race conditions.

## 9. Takeaways

- **A connection is an execution channel for SQL; a transaction is a commit/rollback boundary.** They are not synonymous.
- **`autoCommit=true`:** each completed statement auto-commits, even if all run on the same connection.
- **`autoCommit=false`:** multiple statements can belong to the same transaction; you must explicitly call `commit()` or `rollback()`.
- **A business operation with interdependent steps** needs a shared transaction; rollback must be verified with real failure cases.
- **In Spring:** place `@Transactional` at the appropriate service boundary, use DAOs/`JdbcTemplate` participating in the right transaction manager, and understand proxy, propagation, and exception rules.

## References

- [Java SE 17 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): auto-commit, statement completion, `commit`, `rollback`, and `setAutoCommit`.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `JdbcTemplate`, and transaction-bound connections.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation, and rollback defaults.
