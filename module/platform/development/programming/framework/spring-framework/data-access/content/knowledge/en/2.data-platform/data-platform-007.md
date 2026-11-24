# Commit, Rollback, Auto-Commit, and Transaction Boundaries

In an application using the Spring Framework for data access, multiple SQL statements often serve **a single business action**: transferring funds, creating an order with its line items, or recording multiple related changes. If the first statement succeeds and a subsequent statement fails, data can be left in a half-finished state. A transaction establishes a boundary so the database can decide **either to accept all changes belonging to the transaction, or to discard the unconfirmed changes**.

This lesson focuses on the meaning and timing of `commit`, `rollback`, and `auto-commit`, how to recognize transaction boundaries in JDBC and Spring, and common mistakes when moving from individual SQL statements to a business workflow.

## 1. Which Unit of Work Is a Transaction?

Suppose account A has 100 units and account B has 50 units. Transferring 30 units from A to B requires at least two operations:

```sql
UPDATE account SET balance = balance - 30 WHERE id = 1;
UPDATE account SET balance = balance + 30 WHERE id = 2;
```

The desired outcome is A = 70 and B = 80. If only the debit is recorded, the total balance becomes wrong. The two statements therefore belong together in **one transaction**:

1. Begin the transaction scope.
2. Execute the related operations within the same transaction context.
3. If all business conditions are met, `commit`.
4. If an error occurs or a condition fails, `rollback`.

This is the **atomicity** aspect of ACID: a transaction's changes are accepted as one unit. The remaining three properties clarify the limits of that guarantee:

- **Consistency:** data constraints and business invariants must remain satisfied; the database enforces the constraints it knows about, while the application still must check its own business rules.
- **Isolation:** concurrent transactions observe and affect each other according to the database's isolation level. A transaction does not automatically prevent all dirty reads, non-repeatable reads, or lost updates.
- **Durability:** once `commit` succeeds, the database is responsible for persisting the outcome according to the DBMS's storage guarantees and configuration.

**Important:** A database transaction controls only the resources participating in that transaction. It does not automatically recall an email already sent, an HTTP request already made, or a file already written to disk.

## 2. Commit, Rollback, and State of Changes

| Operation | Meaning | What to Remember |
| --- | --- | --- |
| `commit` | Ends the current transaction by confirming its changes. | Once commit succeeds, a `rollback` of that transaction cannot reverse the result; a compensating transaction is needed if business logic must undo it. |
| `rollback` | Discards **uncommitted** changes of the current transaction. | Does not undo already-committed transactions and does not guarantee undoing external side effects outside the DB. |
| `auto-commit = true` | JDBC commits each statement after it completes according to driver/JDBC rules. | Two consecutive `UPDATE` statements are normally **two independent transactions**. |
| `auto-commit = false` | The application controls when the transaction ends via `commit()` or `rollback()`. | Both success and failure paths must be terminated explicitly. |

In JDBC, auto-commit mode is a property of **`java.sql.Connection`**, not an application-wide switch. By default, a newly created JDBC connection starts with auto-commit enabled, unless the environment or connection-management layer intervenes. In practice, connections borrowed from a pool may have their state configured or reset before being handed to the application.

When auto-commit is enabled, JDBC commits a statement only when the statement is considered complete; for queries returning a `ResultSet`, exhausting or closing the result can affect completion timing. Therefore, do not assume every statement has already committed the instant `executeQuery()` returns.

When auto-commit is disabled, a series of statements on the **same connection** can belong to a single transaction. After `commit()` or `rollback()`, subsequent statements enter the next transaction according to how the driver/DBMS begins transactions. Two further JDBC contract details matter:

- Calling `setAutoCommit(true)` while a transaction is active **commits the current transaction**. Hence, never use it to "cancel" a failing transaction.
- Do not rely on `Connection.close()` to roll back: closing a connection with an active transaction can behave differently depending on driver and environment. Applications should call `commit`/`rollback` explicitly; pools must return connections to a clean state.

Some DBMSs perform *implicit commits* when running DDL such as `CREATE TABLE` or `ALTER TABLE`. Do not assume every DDL statement can roll back simply because the application disabled auto-commit.

## 3. Where Do Transaction Boundaries Lie?

A transaction boundary is **the scope of work sharing a single commit/rollback decision**, not merely a number of code lines or SQL statements. Conceptually:

```text
Begin transaction
  ├─ Check business conditions
  ├─ UPDATE table 1
  ├─ INSERT/UPDATE table 2
  └─ Verify write results (affected row count, constraints...)
       ├─ Success: COMMIT  → changes are confirmed
       └─ Failure: ROLLBACK → uncommitted changes are discarded
End transaction scope
```

A sound boundary typically wraps **one business operation requiring atomicity**, such as "transfer funds" or "create an order with line items." Committing right after every statement prevents the system from rolling back a multi-step operation. Conversely, stretching a transaction across slow HTTP calls or user wait times holds locks and connections open too long, increasing contention and timeouts.

Distinguish three kinds of boundaries:

- **Java call boundary:** entry and exit of a method. A Java method does not inherently create a transaction.
- **JDBC boundary:** operations actually executed on a connection under that connection's transaction mode.
- **Spring boundary:** an interceptor/`PlatformTransactionManager` starts, joins, commits, or rolls back a transaction for a method configured with `@Transactional`, binding the appropriate resource to the current execution thread.

One method can invoke multiple repositories; they share a transaction only when they participate in the same transaction manager and corresponding data source. Two connections or two data sources do not automatically form a single atomic transaction.

## 4. Complete JDBC Example: Committing on Success, Rolling Back on Downstream Failure

The example below uses **Java 17+, H2 in-memory, and JDBC**. Account data is initialized; the first transfer succeeds, while the second attempts to transfer to a nonexistent account. The debit in the second transfer rolls back because the credit step fails.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-transactions-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/TransactionDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public class TransactionDemo {
    private static final String URL =
            "jdbc:h2:mem:transaction_demo;DB_CLOSE_DELAY=-1";

    private static Connection open() throws SQLException {
        return DriverManager.getConnection(URL, "sa", "");
    }

    public static void main(String[] args) throws SQLException {
        try (Connection c = open(); Statement st = c.createStatement()) {
            st.executeUpdate(
                    "CREATE TABLE account (" +
                    "id INT PRIMARY KEY, " +
                    "balance INT NOT NULL CHECK (balance >= 0))");
            st.executeUpdate(
                    "INSERT INTO account (id, balance) VALUES (1, 100), (2, 50)");
        }

        show("Initial");
        transfer(1, 2, 30);
        show("After commit");

        try {
            transfer(1, 99, 10); // Account 99 does not exist.
        } catch (SQLException ex) {
            System.out.println("Transfer failed; rolled back");
        }
        show("After rollback");
    }

    private static void transfer(int from, int to, int amount)
            throws SQLException {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                changeBalance(c, from, -amount);
                changeBalance(c, to, amount);
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static void changeBalance(Connection c, int id, int delta)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "UPDATE account SET balance = balance + ? WHERE id = ?")) {
            ps.setInt(1, delta);
            ps.setInt(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Account not found: " + id);
            }
        }
    }

    private static void show(String title) throws SQLException {
        try (Connection c = open();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT id, balance FROM account ORDER BY id");
             ResultSet rs = ps.executeQuery()) {
            List<String> values = new ArrayList<>();
            while (rs.next()) {
                values.add(rs.getInt("id") + "=" + rs.getInt("balance"));
            }
            System.out.println(title + ": " + String.join(", ", values));
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=TransactionDemo
```

```text
Initial: 1=100, 2=50
After commit: 1=70, 2=80
Transfer failed; rolled back
After rollback: 1=70, 2=80
```

Boundary-by-boundary explanation:

1. Table creation and seed data run on a default auto-commit connection; each initialization statement is persisted on completion.
2. `transfer(1, 2, 30)` opens another connection, calls `setAutoCommit(false)`, runs two `UPDATE` statements, and calls `commit()`. Both changes are accepted together.
3. `transfer(1, 99, 10)` already subtracted 10 from account 1, yet the `UPDATE` for account 99 affects **0 rows**. The code treats that as a business failure, throws `SQLException`, and calls `rollback()` before closing the connection; account 1's balance remains 70.
4. `show` runs on a fresh connection and sees only committed data. The demo does not test isolation levels or concurrent interactions.

**Noteworthy design point:** `executeUpdate()` does not necessarily throw an exception when `WHERE` matches zero rows. To treat "account does not exist" as a failure, the application must check the affected row count. In real money transfers, you also need overdraft protection, concurrency handling, `DECIMAL` types for currency, and other domain rules; the demo uses integers to isolate commit/rollback mechanics.

## 5. What If Auto-Commit Stays On?

Consider two debit and credit operations executed sequentially on a connection with auto-commit enabled:

```java
// Illustrative snippet: c is a Connection with auto-commit = true.
debitAccount(c, fromId, amount);   // This SQL statement may already be committed.
creditAccount(c, toId, amount);    // On failure, rollback cannot undo the prior statement.
```

This is an **illustrative code snippet**, not a standalone program; `debitAccount` and `creditAccount` represent SQL operations. Once the debit statement commits on its own, a failure in the credit statement cannot roll back the earlier transaction. In fact, calling `rollback()` while the connection still has auto-commit enabled is not a valid way to undo prior statements (JDBC may throw `SQLException`).

The difference is not whether `try/catch` is present; it lies in **when data is committed** and which statements participate in the same transaction.

## 6. How Does Spring Manage Commit and Rollback?

When an application uses Spring JDBC, JPA, or another data-access layer integrated with a transaction manager, you can place the boundary on a service method with `@Transactional`. Spring opens or joins a transaction per configuration, uses the bound resource for operations, and decides commit/rollback when the call finishes.

The example below is **a service snippet in a Spring application configured with a `DataSource`, `JdbcTemplate`, and an appropriate transaction manager**; it is not a standalone runnable Java class. The `account` table here is assumed to store money in a suitable decimal numeric type.

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
        if (fromId == toId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Debit rejected");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Receiver not found");
        }
    }
}
```

In a typical configuration, another component calls `transferService.transfer(...)` **through the Spring bean/proxy**:

- If no transaction is currently active, the default `REQUIRED` propagation starts a new transaction. If an appropriate transaction already exists, the method usually joins that transaction.
- `JdbcTemplate` uses the connection bound to the active transaction; updates are not individually auto-committed as they would be on a standalone connection outside Spring.
- If the method returns normally and the interceptor owns the transaction, Spring requests a commit; if an error triggers rollback, Spring requests a rollback.
- By default, Spring rolls back when a `RuntimeException` or `Error` escapes; checked exceptions do not automatically trigger rollback unless configured (e.g., `@Transactional(rollbackFor = Exception.class)`) or marked rollback-only.
- Throwing `IllegalStateException` in the example causes both updates in the same transaction to roll back, even though the first update succeeded.

Do not call `connection.commit()`, `connection.rollback()`, or change auto-commit arbitrarily on a Spring-managed connection: doing so can corrupt the transaction boundary managed by the transaction manager.

### Conditions for `@Transactional` to Actually Take Effect

`@Transactional` **is not a SQL statement**. The annotation works only when Spring's transaction infrastructure is enabled, a transaction manager applies to the target resource, and the call passes through the proper interception mechanism.

- In standard proxy mode, a bean method calling `this.transfer(...)` on itself is **self-invocation**; this call bypasses the proxy and does not activate a new `@Transactional` boundary for the target method. An existing transaction on the caller still remains active.
- Methods not managed by Spring, or objects instantiated manually with `new`, do not receive proxy interception.
- Spring transactions are typically bound to the executing thread. Offloading work to `@Async`, manually created threads, or background workers does not automatically carry the same transaction across.
- Placing the annotation on a service does not guarantee atomic commit across two data sources or external messaging. That requires appropriate resource-coordination or consistency architecture.

When a unit of work is already inside an outer transaction, an inner `REQUIRED` method does not commit independently upon returning. The commit decision belongs to the **outer transaction boundary**. If an inner branch marks the transaction rollback-only yet the outer branch attempts to commit, Spring may throw `UnexpectedRollbackException` to prevent reporting a false success.

## 7. When an Exception Is Caught: Does the Transaction Roll Back?

Consider this scenario:

```java
@Transactional
public void placeOrder() {
    saveOrder();
    try {
        reserveInventory();
    } catch (Exception ex) {
        logFailure(ex); // Only logs and returns normally.
    }
}
```

This is an illustrative snippet. If the error is caught and the method finishes normally, the interceptor may **commit** the earlier changes; catching an exception does not automatically mean rollback. On the other hand, a child call with a transaction interceptor that already marked the transaction rollback-only can cause the outer commit to fail. The exact outcome depends on where the error originates, propagation, and how the transaction manager tracks state.

When business rules require aborting everything, allow an appropriate exception to propagate, configure `rollbackFor` for checked exceptions, or explicitly mark rollback-only via Spring's transaction API. Avoid swallowing exceptions and returning "success."

When using `TransactionTemplate` instead of annotations, the callback defines the transaction scope and can call `status.setRollbackOnly()`. This is an explicit option for programmatic transaction control; an appropriate transaction manager is still required.

## 8. Savepoints and Partial Rollback Scope

A standard `rollback()` discards uncommitted changes of the **entire transaction**. If the driver and database support savepoints, JDBC also allows rolling back to a marker inside a transaction:

```java
// Illustrative snippet inside try with c.setAutoCommit(false).
Savepoint mark = c.setSavepoint();
try {
    performOptionalWrite(c);
} catch (SQLException ex) {
    c.rollback(mark); // Discards work after the savepoint; earlier work still awaits commit.
}
c.commit();           // Still requires a final decision for the transaction.
```

`Savepoint` and `performOptionalWrite` above are parts of a larger workflow; this is not a standalone program. Rolling back to a savepoint **does not commit** work prior to it. If the overall transaction eventually rolls back, work before the savepoint is discarded too.

In Spring, `Propagation.NESTED` can rely on savepoints if the transaction manager and resource support them. `REQUIRES_NEW` uses an independent transaction that can commit on its own even if the outer transaction later rolls back. Do not treat the two mechanisms as equivalent or assume both are supported in every configuration.

## 9. Commit/Rollback Does Not Replace Concurrency Control

A successful transaction does not prove the result is right when two requests run simultaneously. For instance, two users concurrently read a balance of 100 and both decide to subtract 80; if the balance check is separate from the update statement, overwrites or invariant violations can still occur even though each transaction commits or rolls back.

In the Spring example, `WHERE balance >= ?` is embedded directly into the debit statement, combined with checking the updated row count. This reduces overdraft risk in many databases, yet applications still must understand **isolation levels, locks, lock ordering, deadlocks, retries, and data constraints** depending on the DBMS and domain model.

Terms to distinguish:

- **Uncommitted changes:** changes inside an uncommitted transaction that can still roll back; whether other transactions see them depends on isolation.
- **Committed changes:** confirmed changes; other transactions can observe them according to isolation and their snapshot/read timing.
- **Flush (JPA):** synchronizing pending SQL to the DB within a transaction, **not synonymous with commit**; a successful flush can still roll back.
- **Read-only transaction:** in Spring, usually an optimization/routing hint; do not assume it acts as a hard block against all writes across every driver and DB.

## 10. Common Mistakes and Fixes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Running two `UPDATE`s with auto-commit on and hoping `catch` undoes both | The first statement may already be committed independently | Put both in the same JDBC transaction or `@Transactional` service |
| Calling commit on success path but omitting rollback on error path | Hanging transactions can hold locks and leave connections unsafe for reuse | Roll back explicitly, even on statement failure; handle rollback errors too |
| Calling `setAutoCommit(true)` to "reset" during an active transaction | Per JDBC, this can commit pending changes | Commit/rollback first, then restore desired connection state |
| Not checking `executeUpdate()` returning `0` | No exception thrown, yet business target was not updated | Check affected row count and raise a domain error |
| Opening a manual connection alongside `JdbcTemplate` inside `@Transactional` | The new connection may not join the Spring-managed transaction | Use DAOs/repositories sharing the transaction manager and data source |
| Self-invoking a `@Transactional` method in the same bean expecting a new transaction | Call may bypass the proxy interceptor | Place boundary on a service called via bean or use `TransactionTemplate` |
| Catching exception, logging, and returning normally | Interceptor may commit earlier work | Propagate proper error, configure rollback, or mark rollback-only |
| Sending emails / calling APIs before commit assuming DB rollback recalls them | External side effects already happened | Consider outbox, idempotency, retries, or architectural compensation |
| Stretching transactions over network I/O and user waits | Holds connections and locks too long, raising contention | Keep transactions short around data operations truly needing atomicity |

## 11. Decision Rules When Designing a Data Operation

Before adding `@Transactional` or `setAutoCommit(false)`, answer these questions:

1. **Which write operations make up one business action?** If a later operation fails, must earlier writes be discarded?
2. **Do they share one resource / transaction manager?** If not, a local transaction alone cannot guarantee cross-resource atomicity.
3. **When is the outcome considered successful?** Commit only after all related checks and writes finish; never treat the presence of `try/catch` as proof of a transaction.
4. **Which errors must roll back?** Check default exceptions, checked exceptions, validation failures, and zero-affected-row conditions.
5. **Are there side effects outside the database?** If so, design for them separately rather than bundling them into a DB rollback promise.
6. **Are there concurrency risks or long-running transactions?** A correct atomic boundary still requires suitable isolation/locks and bounded transaction duration.

### Key Takeaways

- `commit` **confirms**; `rollback` **discards unconfirmed work**; both only have meaning within **the right transaction**.
- Enabling `auto-commit` fits many single-statement operations, yet does not automatically provide atomicity for a sequence of business steps.
- With JDBC, statements that must share a transaction must share the same connection inside a managed transaction scope with an explicit termination decision.
- With Spring, `@Transactional` is usually placed on the **service encapsulating the full business unit of work**, so data operations share one unified commit/rollback boundary.
- After commit, reversing business effects requires a controlled compensating change; rollback is not a time-travel or cross-system "undo" button.
