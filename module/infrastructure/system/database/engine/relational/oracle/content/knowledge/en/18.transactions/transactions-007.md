# Tool/JDBC Autocommit and the Risk of Splitting Transactions in Oracle

A business operation often consists of multiple SQL statements that must be treated as **one atomic unit of work**. For example, a money transfer must debit the source account and credit the destination account; placing an order may need to insert the order, order items, and decrement inventory; approving a record may need to update status and write history. If each SQL statement commits immediately after running, an error halfway through can leave the data only half-updated.

This is the primary risk of **autocommit** when using a SQL client or JDBC. In Oracle, transaction boundaries are managed by the database, but tools and applications decide when to send `COMMIT`/`ROLLBACK`, whether auto-commit mode is enabled, and whether statements actually execute on the same connection/session.

This lesson focuses on:

- What autocommit means in SQL clients and JDBC.
- Why a multi-statement business operation can get split into multiple transactions.
- Managing transactions with `setAutoCommit(false)`, `commit()`, and `rollback()`.
- `SAVEPOINT`, DDL implicit commit, and connection pool effects.
- Error scenarios, retries, batches, framework transactions, and testing commit boundaries.

## 1. What Is a Transaction and Why Are Clear Boundaries Needed?

A **transaction** is a database unit of work comprising one or more statements processed as a single whole. Transactions are commonly described using the four ACID properties:

| Property | Practical Meaning |
|---|---|
| Atomicity | All changes of the transaction are committed, or uncommitted changes are rolled back |
| Consistency | The transaction must preserve the system's data constraints and rules |
| Isolation | Concurrent transactions must not observe intermediate states in ways that violate the chosen isolation level |
| Durability | After a successful commit, the database guarantees durable storage of changes according to system configuration/guarantees |

For example, transferring 100 currency units from account A to B involves two statements:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;
```

These two statements must belong to **the same transaction**. If the debit statement succeeds while the credit statement fails, the application must be able to roll back both changes. If the debit statement already committed separately, a subsequent `ROLLBACK` cannot undo the committed change.

```text
One money transfer operation
          |
          v
    Debit account A
          |
          v
    Credit account B
          |
          v
    Both succeeded?
        /       \
      Yes        No
      |           |
      v           v
    COMMIT     ROLLBACK
```

**Autocommit can alter transaction boundaries**: each completed statement gets committed individually, causing the two steps above to no longer be atomic as the business logic requires.

## 2. How Are Transactions Started and Ended in Oracle?

Oracle manages transactions within a database session. A transaction can consist of multiple DML statements such as `INSERT`, `UPDATE`, `DELETE`, and `MERGE`. Uncommitted changes belong solely to the current transaction.

Common control commands:

```sql
COMMIT;
ROLLBACK;
SAVEPOINT before_optional_step;
ROLLBACK TO before_optional_step;
```

- `COMMIT`: ends the current transaction and confirms the changes.
- `ROLLBACK`: discards uncommitted changes of the current transaction.
- `SAVEPOINT name`: marks a position inside a transaction.
- `ROLLBACK TO name`: discards changes after the savepoint while keeping the transaction open to continue.

Oracle does not require a `BEGIN TRANSACTION` statement in the syntax used by some other DBMSs. Transactions are managed by the database within the session; DML starts or joins the current transaction. The keyword `BEGIN` in `BEGIN ... END;` is PL/SQL block syntax—it **does not create an independent transaction** and does not auto-commit at the end of the block.

### 2.1. How Are Uncommitted Changes Observed?

Within a session, a user sees changes made by their own transaction. Other sessions generally see the committed version via Oracle's read consistency mechanism, and do not see the first session's uncommitted DML changes.

Two-session verification example:

**Session A:**

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;
-- Not committed yet.
```

**Session B:**

```sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;
```

Session B reads the previously committed data, while Session A sees its own updated balance. When Session A runs `COMMIT`, subsequent queries in Session B can see the new value.

This also means that if a SQL client auto-commits after the `UPDATE` statement, Session B sees the new data immediately once the statement finishes. A user might think they were just "testing a statement," yet the change has already been confirmed.

### 2.2. Rollback Only Affects Uncommitted Work

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

COMMIT;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
```

After the snippet above, the first update is retained because it committed. The second update is discarded because it remained in an uncommitted transaction. `ROLLBACK` cannot undo a transaction that already ended with `COMMIT`.

### 2.3. Statement Atomicity Is Not Transaction Atomicity

Oracle guarantees atomicity at the level of **a single statement**: if an `UPDATE` fails mid-execution, the database undoes the effects of that statement itself. However, this does not mean all earlier statements in the transaction also roll back automatically.

Example:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

-- Suppose the next statement fails due to a constraint violation.
INSERT INTO lab_transfer_log (transfer_id, note)
VALUES (NULL, 'missing required id');
```

If the `INSERT` fails, the `INSERT`'s effect is undone. The preceding `UPDATE` remains in the transaction and can still be committed later if the application does not proactively roll back. Therefore, exception handling must explicitly decide whether to roll back **the entire business operation**.

## 3. What Is Autocommit?

**Autocommit** is a mode in which a tool/driver automatically commits after a statement completes according to its rules, instead of waiting for the application or user to call `COMMIT` explicitly.

From a business perspective, distinguish:

- **Autocommit enabled:** each completed statement forms a separate commit boundary under the active mode.
- **Autocommit disabled:** statements can join the same transaction until `COMMIT` or `ROLLBACK` is called (or another event ends the transaction, such as DDL in Oracle).

Autocommit is a property of **the tool/connection**, not a table constraint. Against the same database, two sessions may be operating under different commit modes.

### 3.1. Why Is Autocommit Convenient?

Autocommit suits standalone operations, such as:

- Running a simple `INSERT` to load one test row.
- Running an independent `UPDATE` whose result is already determined.
- Executing read-only queries; SELECT creates no DML changes requiring commit.
- Executing administrative commands where the tool/database has its own transaction rules.

Users do not have to remember to press `COMMIT` after each standalone operation. However, when multiple statements serve a single business flow, autocommit can inadvertently split the transaction.

### 3.2. Autocommit Does Not Mean "Everything in a Script Is One Transaction"

A script may contain multiple SQL statements:

```sql
UPDATE orders SET status = 'APPROVED' WHERE order_id = 1001;
INSERT INTO order_audit (order_id, action_name)
VALUES (1001, 'APPROVED');
UPDATE inventory SET reserved_qty = reserved_qty + 1 WHERE product_id = 501;
```

If the tool autocommits per statement, the three statements can become three separate transactions. If the third statement fails, the first two changes may already be committed. Clicking "Run Script" or "Execute" does not automatically guarantee all statements share one transaction; you must know how the tool submits statements and handles commits.

## 4. Client/Tool-Side Autocommit

A SQL client is a program connecting to Oracle to run SQL/PLSQL. Tools may offer options like Auto Commit, Commit after each statement, Manual Commit, or Commit/Rollback buttons. Option names, default values, and behavior can vary by tool version, worksheet/script execution mode, and connection type.

Never assume all SQL clients enable or disable autocommit by default. Before running a script with DML, verify the current configuration and observe your own session's transaction state.

### 4.1. When Autocommit Is Enabled

For example, a user runs:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;
```

If the tool commits each statement after execution:

1. The debit statement finishes and is committed.
2. The credit statement runs afterward.
3. If the second statement fails, the first statement remains committed.

The user cannot restore atomicity by clicking Rollback afterward, because the first transaction already ended.

### 4.2. When Autocommit Is Disabled

If the tool keeps the transaction open:

```sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

-- Confirm only after both steps succeed.
COMMIT;
```

If one statement fails and the business flow cannot proceed:

```sql
ROLLBACK;
```

The transaction's uncommitted DML changes are discarded. However, having autocommit off does not automatically guarantee a script is safe: the script might still contain `COMMIT`, DDL causing implicit commit, a self-committing procedure call, or switch to another session.

### 4.3. Multi-Statement Scripts and Statement-by-Statement Execution

Some tools allow running:

- A single highlighted statement.
- The entire worksheet contents.
- A script through a script runner.
- A PL/SQL block.

These modes can send SQL to the database differently. Determine whether the tool enables autocommit on the connection, inserts an automatic commit after the script, and whether the script has its own `COMMIT`/`ROLLBACK` commands. Do not assume one button click corresponds to one transaction.

### 4.4. Verifying with Two Sessions

A practical verification is opening two independent sessions to the same schema:

1. Session A runs an `UPDATE` without committing.
2. Session B reads that row.
3. Observe Session B still sees the previously committed data.
4. Session A commits.
5. Session B reads again and sees the new change.

If Session B sees the new value immediately after A's statement finishes, check autocommit or a commit performed elsewhere. Test on lab tables—never use a real business table to "test whether rollback works."

## 5. Autocommit in JDBC

JDBC manages transactions through `java.sql.Connection`. **A newly created `Connection` typically starts with auto-commit enabled (`true`) per the JDBC contract.** When auto-commit is enabled, statements commit upon completion according to driver/JDBC rules. When a business operation spans multiple statements, the application must disable auto-commit to group statements into one transaction.

Key APIs:

```java
connection.getAutoCommit();
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
connection.setSavepoint();
connection.rollback(savepoint);
```

### 5.1. Default Auto-Commit

Example:

```java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance - ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 1L);
        ps.executeUpdate();
    }
}
```

If `getAutoCommit()` returns `true`, the standalone `UPDATE` is committed automatically upon completion. If the application continues executing another `UPDATE` on the same connection, the second statement does not retroactively join the already committed transaction of the first statement.

### 5.2. Disabling Autocommit and Committing Explicitly

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance - ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 1L);
        ps.executeUpdate();
    }

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE lab_accounts SET balance = balance + ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("100.00"));
        ps.setLong(2, 2L);
        ps.executeUpdate();
    }

    connection.commit();
}
```

Both `UPDATE` statements execute within the connection's same transaction and commit only after both finish. However, the snippet above still needs error handling with rollback; merely calling `setAutoCommit(false)` and letting the connection close is not complete error handling.

### 5.3. Rollback on Error

Basic transaction management pattern:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Execute all statements belonging to the same business operation.
        updateAccountA(connection);
        updateAccountB(connection);
        insertTransferAudit(connection);

        // Commit only after all steps succeed.
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
```

This pattern demonstrates key principles:

- All statements of the business operation share one `Connection`.
- Do not commit between steps.
- On error, roll back uncommitted work.
- If rollback also fails, attach the rollback error as a suppressed exception so the original cause is not masked.
- Close the connection only after the transaction has been explicitly committed or rolled back.

In production applications, separate SQL logic into methods accepting the active connection, or let a transaction framework manage connections. Avoid having each method open a new connection if they must share the same transaction.

### 5.4. Checking Affected Row Counts

An `UPDATE` without syntax errors can still update **0 rows** due to a wrong ID or missing data. That does not automatically throw an exception. For a money transfer, you must verify row counts:

```java
int updated = statement.executeUpdate();
if (updated != 1) {
    throw new SQLException("Expected exactly one account row, updated=" + updated);
}
```

If the row count is wrong, throw an error so the transaction flow rolls back. Never equate "no SQLException" with business success.

### 5.5. Changing autoCommit Can Commit the Current Transaction

Per the JDBC contract, calling `setAutoCommit(...)` while a transaction is active—when the auto-commit value actually changes—commits the current transaction. Thus, the following snippet is dangerous:

```java
connection.setAutoCommit(false);
updateAccountA(connection);

// Dangerous: changing modes can commit the active transaction.
connection.setAutoCommit(true);

updateAccountB(connection);
```

Switching `false` to `true` can commit `updateAccountA`'s changes before `updateAccountB` even runs. Do not use `setAutoCommit(true)` as a way to "clean state" mid-business-flow. Always finish cleanly with `commit()` or `rollback()`, then let the pool/framework restore connection state per its contract.

## 6. Complete Example: Safe Money Transfer vs. Split-Transaction Bug

### 6.1. Create Lab Tables

Only run the following DDL in an authorized **DEV/TEST** schema after confirming the target database/service:

```sql
CREATE TABLE lab_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(14, 2) NOT NULL,
    CONSTRAINT ck_lab_accounts_balance CHECK (balance >= 0)
);

INSERT INTO lab_accounts VALUES (1, 'Account A', 1000.00);
INSERT INTO lab_accounts VALUES (2, 'Account B', 500.00);
COMMIT;
```

The `CHECK (balance >= 0)` constraint makes the database reject negative balances. It does not replace validating transfer amounts and updated row counts in the application.

### 6.2. Wrong Approach: Autocommit Enabled per Step

Suppose the application executes two statements on a connection with `autoCommit = true`:

```java
connection.setAutoCommit(true);

try (PreparedStatement debit = connection.prepareStatement(
        "UPDATE lab_accounts " +
        "SET balance = balance - ? " +
        "WHERE account_id = ? AND balance >= ?")) {
    debit.setBigDecimal(1, new BigDecimal("100.00"));
    debit.setLong(2, 1L);
    debit.setBigDecimal(3, new BigDecimal("100.00"));
    debit.executeUpdate(); // This statement may already be committed.
}

try (PreparedStatement credit = connection.prepareStatement(
        "UPDATE lab_accounts SET balance = balance + ? WHERE account_id = ?")) {
    credit.setBigDecimal(1, new BigDecimal("100.00"));
    credit.setLong(2, 999L); // Destination account does not exist.
    int rows = credit.executeUpdate(); // No SQL error, yet updates 0 rows.
}
```

Consequences:

1. Account A is debited 100 and the first statement is committed.
2. The second statement updates 0 rows because ID 999 does not exist.
3. No exception is automatically thrown just because updated rows equal 0.
4. Money left account A without being credited to account B.

Even if the application detects `rows == 0` and calls `rollback()`, rollback cannot undo the already committed debit statement.

### 6.3. Right Approach: One Transaction for the Entire Transfer

```java
public void transfer(
        DataSource dataSource,
        long fromAccountId,
        long toAccountId,
        BigDecimal amount
) throws SQLException {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (fromAccountId == toAccountId) {
        throw new IllegalArgumentException("source and destination must differ");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            int debited;
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE lab_accounts " +
                    "SET balance = balance - ? " +
                    "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);
                debited = debit.executeUpdate();
            }

            if (debited != 1) {
                throw new SQLException("Source account missing or insufficient funds");
            }

            int credited;
            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE lab_accounts " +
                    "SET balance = balance + ? " +
                    "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);
                credited = credit.executeUpdate();
            }

            if (credited != 1) {
                throw new SQLException("Destination account does not exist");
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
```

Here both updates share the same connection, auto-commit is off, row counts are verified, and a single commit happens at the end. If the destination account does not exist, the exception triggers rollback and the source account's balance is restored.

### 6.4. Concurrent Edge Cases Must Still Be Handled

Transactions ensure statements commit/roll back together, yet business logic must still handle concurrency:

- Two concurrent requests transferring from the same account can contend on updating its balance.
- The `balance >= amount` condition in `UPDATE` checks the balance at update time and reduces the risk of overdrafting.
- `CHECK (balance >= 0)` acts as the final database safeguard.
- Lock ordering must be defined when two transactions transfer in opposite directions to reduce deadlock risk.
- For retryable requests, include a transaction ID/idempotency key to prevent transferring twice when a client misses the response.

Disabling autocommit is necessary for atomicity across two statements, yet does not automatically solve all concurrency or retry issues.

## 7. SAVEPOINT: Partial Rollback Without Splitting the Transaction

`SAVEPOINT` lets you mark a point inside a transaction. You can roll back work after that point while preserving changes before the savepoint in the same transaction.

```sql
UPDATE lab_accounts
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE lab_accounts
SET balance = balance + 50
WHERE account_id = 2;

-- If a secondary credit step fails, roll back to the savepoint.
ROLLBACK TO after_debit;

-- After re-evaluating logic, decide whether to COMMIT or ROLLBACK the whole transaction.
```

In the example above, `ROLLBACK TO after_debit` only discards changes after the savepoint; the debit statement before the savepoint remains in the transaction. If the goal is an atomic transfer, you must not commit the debit afterward. Savepoints do not replace the final business commit/rollback decision.

### 7.1. Savepoints in JDBC

```java
connection.setAutoCommit(false);

try {
    updateRequiredData(connection);

    Savepoint optionalStep = connection.setSavepoint("OPTIONAL_STEP");
    try {
        updateOptionalData(connection);
    } catch (SQLException optionalError) {
        connection.rollback(optionalStep);
        recordOptionalFailureInMemory(optionalError);
    }

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
}
```

This pattern fits when an optional step can be skipped while mandatory steps remain valid. Do not use savepoints to mask failures of mandatory steps; partial rollback decisions must derive from explicit business rules.

## 8. DDL in Oracle Triggers Implicit Commit

Another major pitfall: **DDL in Oracle can terminate a transaction on its own**, regardless of whether JDBC `autoCommit` is `true` or `false`.

Common DDL statements:

```sql
CREATE TABLE ...;
ALTER TABLE ...;
DROP TABLE ...;
TRUNCATE TABLE ...;
CREATE INDEX ...;
```

Oracle performs an implicit commit before valid DDL and after successful DDL according to database transaction rules. Therefore:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

CREATE TABLE lab_temp_note (note_id NUMBER);

ROLLBACK;
```

You cannot expect the final `ROLLBACK` to undo the first `UPDATE`; the DML transaction was already committed before the DDL ran. Successful DDL also commits afterward. This is an Oracle rule, independent of whether the user disabled autocommit in JDBC.

### 8.1. DDL Cannot Be Rolled Back Like Regular DML

After running:

```sql
CREATE TABLE lab_temp_note (note_id NUMBER);
```

you cannot use `ROLLBACK` to remove the newly created table. To remove it, you must run another DDL command:

```sql
DROP TABLE lab_temp_note PURGE;
```

This is a new DDL operation with its own transaction semantics. Never place DDL between DML steps requiring atomicity unless commit boundaries are explicitly designed.

### 8.2. Schema Migrations and Data Transactions

Do not bundle schema changes and business data updates into a single transaction expecting to roll everything back. A migration typically needs its own workflow:

1. Prepare and verify schema changes.
2. Execute DDL, accounting for implicit commit.
3. Run data backfill/transformation in batches with appropriate checkpoints.
4. Verify results and application compatibility.
5. Maintain a rollback/forward-fix plan for both schema and data.

Oracle DDL cannot be undone via ordinary rollback like an uncommitted `UPDATE`. For significant changes, version migrations and design compensating/forward migrations.

## 9. JDBC, Connection Pools, and Transaction Boundaries

In server applications, a `DataSource` normally provides connections from a connection pool. The `Connection` an application receives may be a logical handle pointing to a reused physical database session.

### 9.1. One Transaction Must Use the Same Connection

Example of an incorrect transaction boundary:

```java
updateAccountA(dataSource); // Method opens connection A, commits/closes.
updateAccountB(dataSource); // Method opens connection B, commits/closes.
```

The two methods can use two distinct sessions. Even when connecting to the same database and schema, they do not automatically join a shared transaction.

A better pattern is passing the active connection:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateAccountA(connection);
        updateAccountB(connection);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
```

The helpers `updateAccountA` and `updateAccountB` merely execute statements on the passed-in connection; they do not open their own connections, commit, or close the caller's connection.

### 9.2. Returning a Connection to the Pool While a Transaction Is Open

Do not rely on `Connection.close()` automatically rolling back identically across all drivers/pools. JDBC recommends applications end transactions via `commit()` or `rollback()` before closing a connection; closing a connection with an active transaction has implementation-dependent outcomes.

With a connection pool, `close()` normally returns the logical connection to the pool rather than closing the physical session. Pools may roll back/reset state upon reuse, yet applications must still manage transactions explicitly. Never let a request return a connection to the pool without knowing whether the transaction committed or rolled back.

### 9.3. Connection State Can Leak to Subsequent Requests

Besides autocommit, connections carry state such as isolation level, schema, read-only mode, client info, NLS/session settings, and savepoints. Pools/frameworks typically reset some state, but never assume every custom modification is automatically restored.

A request that disables autocommit and returns a connection to the pool improperly can cause the next request to inherit unintended state. Do the following:

- Let the transaction manager/pool manage state when using a framework.
- Always commit/roll back explicitly.
- Do not manually change autocommit on a framework-managed connection unless instructed.
- Inspect pool reset/validation settings when investigating session-state bugs.

## 10. Spring and Transaction Frameworks

In Java applications using Spring, it is generally best to let the **transaction manager** control connections and transactions instead of calling `setAutoCommit`, `commit`, and `rollback` in every method.

Conceptual example:

```java
@Service
public class TransferService {
    private final AccountRepository accountRepository;
    private final TransferAuditRepository auditRepository;

    public TransferService(
            AccountRepository accountRepository,
            TransferAuditRepository auditRepository) {
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        accountRepository.debit(fromId, amount);
        accountRepository.credit(toId, amount);
        auditRepository.insert(fromId, toId, amount);
    }
}
```

With proper transaction manager configuration, the repositories participate in the same transaction managed for the method. When the method finishes normally, the transaction manager commits; when an exception matching rollback rules occurs, the transaction manager rolls back.

### 10.1. Things to Watch With @Transactional

- Repositories must share the same transaction manager/resource; opening an independent connection manually can escape the active transaction.
- `@Transactional` is typically applied via proxies; calling a transactional method from another method in the same object (self-invocation) may bypass the proxy unexpectedly.
- By default Spring usually rolls back on `RuntimeException` and `Error`; checked exceptions do not necessarily trigger rollback unless `rollbackFor` is configured appropriately.
- Never call `connection.commit()` directly on a framework-managed connection; it can break transaction boundaries.
- Never call `setAutoCommit(true)` inside a transactional method.
- Oracle DDL still performs implicit commit; an annotation cannot make DDL behave like rollbackable DML.

Example specifying rollback for checked exceptions:

```java
@Transactional(rollbackFor = Exception.class)
public void createOrder(CreateOrderCommand command) throws Exception {
    orderRepository.insert(command);
    inventoryRepository.reserve(command.items());
    auditRepository.insert(command);
}
```

This is an illustrative example. Check your project's actual transaction manager, datasource, and exception rules before applying.

## 11. JDBC Batching and Partial Success Risk

JDBC supports batching to send multiple executions of the same prepared statement:

```java
String sql = "INSERT INTO lab_import_rows (row_id, value_text) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (ImportRow row : rows) {
        ps.setLong(1, row.id());
        ps.setString(2, row.value());
        ps.addBatch();
    }
    int[] counts = ps.executeBatch();
}
```

Batching reduces round-trips and can improve throughput, yet **batching does not define business boundaries by itself**. If the entire batch must succeed or retain zero rows, manage the transaction explicitly:

```java
connection.setAutoCommit(false);
try {
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO lab_import_rows (row_id, value_text) VALUES (?, ?)")) {
        for (ImportRow row : rows) {
            ps.setLong(1, row.id());
            ps.setString(2, row.value());
            ps.addBatch();
        }
        ps.executeBatch();
    }
    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
}
```

When `executeBatch()` fails, the driver may throw `BatchUpdateException` with update counts for executed/processed commands. How drivers handle remaining commands in the batch can vary; read your driver documentation and never infer that "if batch throws an exception, everything rolls back automatically." With auto-commit disabled, the application can roll back the uncommitted transaction to revert the batch's DML to the pre-transaction state.

If a batch is very large, you can split it into chunked transactions to bound undo/redo, lock duration, and recovery time. In doing so, accept that each chunk is a **separate commit unit**; design checkpoints, restarts, and idempotency for the import.

## 12. Splitting Transactions: Business Risks

Splitting an operation into multiple transactions may be necessary for long-running batches, but doing so unintentionally creates half-finished states.

### 12.1. Related Data Falls Out of Sync

Example of creating an order:

1. Insert `ORDERS` and commit.
2. Insert `ORDER_ITEMS` and commit.
3. Decrement inventory and commit.
4. Recording payment fails.

The database may retain the order and line items with decremented inventory and no payment. If business rules require those steps to be atomic, this is an invalid state.

### 12.2. Overall Invariants Are Violated

A transaction may need to maintain invariants such as:

- Total debits equal total credits.
- Inventory quantity is non-negative.
- A confirmed order must have at least one line item.
- Payment status and order status must be consistent.
- An idempotency key is processed only once.

Committing between steps allows intermediate states to violate invariants or be observed by other systems.

### 12.3. Rollback Cannot Reach Past Prior Commits

When step 3 fails, `ROLLBACK` only undoes the current transaction. Steps 1 and 2 that already committed remain. To fix them, the application must run a **compensating action** or a controlled data-correction process.

### 12.4. Retries Can Duplicate Business Effects

Suppose an application sends a transfer request, the database commits successfully, and the network drops before the client receives the response. The client does not know whether the commit succeeded and resends the request. Without an idempotency key, money may be transferred twice.

A common design is storing `REQUEST_ID`/idempotency key with a unique constraint in the same transaction as the business operation. Duplicate requests can look up the previously processed result instead of executing again. Clearly define behavior when a request is still in-flight or when a commit result was not received by the client.

### 12.5. Overly Long Transactions Also Carry Risks

Bundling everything into a massive long-running transaction is not good either. Prolonged transactions can:

- Hold row locks longer and block other sessions.
- Increase the volume of undo that must be retained for rollback/read consistency.
- Increase contention, deadlocks, or timeouts.
- Make rollback after failure time-consuming.
- Hold connection pool slots longer, reducing capacity for other requests.

The solution is identifying the exact **atomic unit of business work**—neither committing every statement indiscriminately nor holding transactions open while waiting for users, calling external APIs, or doing unnecessary long processing.

## 13. When Is Splitting Transactions into Batches Reasonable?

Certain large jobs should not hold a single transaction for hours—such as importing millions of records, backfilling data, or periodic syncing. You can split into chunks, provided you design recovery rules.

A chunked import workflow might include:

1. Read a batch of data with clear keys/offsets.
2. Write the batch data and checkpoint state in the same transaction.
3. Commit the batch.
4. Move to the next batch.
5. On failure, resume only from the committed checkpoint; operations must be idempotent.

Hypothetical checkpoint table example:

```sql
CREATE TABLE import_checkpoint (
    job_id          VARCHAR2(80 CHAR) PRIMARY KEY,
    last_row_id     NUMBER NOT NULL,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

In each chunk, update both data and checkpoint in the same transaction:

```sql
-- Chunk data DML.
INSERT INTO target_rows (row_id, value_text)
SELECT row_id, value_text
FROM staging_rows
WHERE row_id > :last_row_id
  AND row_id <= :next_row_id;

-- Checkpoint DML in the same transaction.
UPDATE import_checkpoint
SET last_row_id = :next_row_id,
    updated_at = SYSTIMESTAMP
WHERE job_id = :job_id;

COMMIT;
```

If inserting data and updating the checkpoint are not in the same transaction, two bugs can occur:

- Data committed while checkpoint did not update: re-running can create duplicates.
- Checkpoint committed while data did not commit: the job skips unwritten data.

If `TARGET_ROWS` has an appropriate unique key, `MERGE`/upsert or idempotent mechanisms can make re-runs safer. Ensure checkpoints and data commit together.

## 14. DDL, Procedures, and Database-Side Transaction Control

Client-side autocommit is not the only thing that can end a transaction. Statements or code running inside the database can also alter boundaries.

### 14.1. Procedures Containing COMMIT

Example procedure:

```sql
CREATE OR REPLACE PROCEDURE approve_order(p_order_id NUMBER) AS
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit(order_id, action_name)
    VALUES (p_order_id, 'APPROVED');

    COMMIT;
END;
/
```

This procedure commits on its own. If an application calls it in the middle of a larger transaction, the `COMMIT` inside the procedure commits earlier changes in **the same session/transaction**, not just the procedure's two statements. The caller loses the ability to roll back the entire business operation as intended.

In designs where the caller manages transactions, procedures should generally perform DML **without committing themselves**, unless the contract explicitly specifies the procedure owns the transaction. Commit boundaries should be managed consistently at one layer.

### 14.2. Autonomous Transactions Are Separate Transactions

PL/SQL provides `PRAGMA AUTONOMOUS_TRANSACTION` to create a transaction independent of the calling transaction. It is typically used for specialized logging/auditing that must persist even when the main transaction rolls back.

Conceptual example:

```sql
CREATE OR REPLACE PROCEDURE write_error_log(p_message VARCHAR2) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);
    COMMIT;
END;
/
```

The log is committed independently; rolling back the calling transaction does not erase that log. This can be useful, yet can also create an audit record for a business action that ultimately never committed. Do not use autonomous transactions to "bypass" rollback for steps that must stay atomic.

### 14.3. Triggers and Transactions

Standard triggers execute inside the triggering transaction; DML inside the trigger joins that transaction. If the trigger raises an error, the triggering statement can fail and its effects are undone. Never use a trigger to silently commit part of a business operation; independent transactions inside triggers require special mechanisms and explicit design.

## 15. Transactions Spanning Multiple Databases or External Services

A JDBC `Connection` manages a transaction within one database resource. If a business flow writes to Oracle and then calls a REST API, sends an email, or writes to another database, Oracle's `commit()`/rollback **does not automatically roll back** actions already performed in external systems.

Design options include:

- **Outbox pattern:** write business data and an outbox event in the same Oracle transaction; a worker dispatches events after commit.
- **Saga/compensation:** break long workflows into steps with compensating actions when a later step fails.
- **Distributed/XA transactions:** used when resources support it and the system truly requires a distributed transaction; evaluate cost, operations, and recovery capabilities.

Simple outbox example:

```sql
INSERT INTO orders(order_id, status, total_amount)
VALUES (:order_id, 'CREATED', :total_amount);

INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload, status)
VALUES (:event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING');

COMMIT;
```

The worker only reads committed events and sends them to other systems. If sending succeeds but the worker crashes before marking sent, the event may be resent; consumers need idempotency. The outbox guarantees order data and the event are written together in Oracle, rather than turning a REST call into part of the Oracle transaction.

## 16. How to Inspect and Diagnose Autocommit

When discovering partially updated data, locate the actual transaction boundaries instead of inspecting only individual SQL statements.

### 16.1. Checking on the JDBC Side

Log/inspect:

```java
boolean autoCommit = connection.getAutoCommit();
DatabaseMetaData metadata = connection.getMetaData();

System.out.println("autoCommit=" + autoCommit);
System.out.println("driver=" + metadata.getDriverName());
System.out.println("driverVersion=" + metadata.getDriverVersion());
System.out.println("database=" + metadata.getDatabaseProductName());
```

Do not check a single connection at startup and assume every request shares the same state. Connection pools, frameworks, and other code can change connection state. Log transaction boundaries at the service layer or use appropriate tracing while avoiding sensitive data.

### 16.2. Checking Oracle Sessions

DBAs or appropriately privileged users can observe sessions, active transactions, and locks via views such as `V$SESSION`, `V$TRANSACTION`, `V$LOCK`, or `GV$` views in RAC environments. Access to these views is typically restricted; normal applications should not be granted DBA privileges merely to inspect transactions.

Conceptual example for privileged users:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.module,
       s.action,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
LEFT JOIN v$transaction t
       ON t.addr = s.taddr
WHERE s.username = USER;
```

Specific views and columns should be verified against your database version and privileges. Do not run administrative queries under unprivileged application accounts.

### 16.3. Recording Transaction Boundaries in Application Logs

Useful logs should include:

- Business correlation ID or idempotency key.
- Service/method name and transaction manager.
- DML step success/failure at a level that avoids exposing sensitive data.
- Transaction start and end timestamps.
- Commit/rollback outcome and root exception.
- Database service, module/action if configured.

Never log passwords, tokens, full account data, or SQL containing sensitive information. When an error occurs after sending COMMIT but before receiving the response, commit status may be unknown on the client side; look up status via business key/idempotency key.

## 17. Safe Transaction Design Checklist

Before enabling autocommit or splitting a business flow into multiple transactions, answer:

1. Which statements comprise one business operation?
2. Which changes must commit together or roll back together?
3. Do all statements run on the same JDBC connection/session?
4. Is autocommit currently `true` or `false`? Who owns this setting: the application, framework, or pool?
5. Are there any `COMMIT`, `ROLLBACK`, DDL statements, or self-committing procedures mid-flow?
6. When a statement updates 0 rows or violates a constraint, does code roll back the entire business operation?
7. Can a batch partially succeed? Are checkpoints/idempotency present when chunking?
8. Is the connection committed/rolled back before returning to the pool?
9. Could retrying after a timeout or disconnect execute the business operation twice?
10. Are external systems called while a database transaction remains open for too long?

## 18. Oracle SQL and JDBC Practice

Practice exercises use a dummy table `LAB_ACCOUNTS`. Run only on an authorized **DEV/TEST** schema and the right PDB/service. Never use real accounts or test rollback on production data.

### Exercise 1 — Observe an Uncommitted Transaction

Open two sessions A and B to the same schema. In Session A:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;
```

Do not commit yet. In Session B:

```sql
SELECT balance
FROM lab_accounts
WHERE account_id = 1;
```

Note that Session B sees the previously committed balance. Return to A, run `COMMIT`, and read again in B.

### Exercise 2 — Roll Back the Full Transaction

In Session A:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK;
```

Check both account balances. Both uncommitted changes must be undone.

### Exercise 3 — Demonstrate Splitting a Transaction

Only in the lab, enable autocommit in your active tool or run two separate statements with a commit between them:

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;
COMMIT;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 999;
COMMIT;
```

Confirm the second statement updates 0 rows while the first already committed. Afterward restore lab data using a controlled compensating operation or reset the lab table; never run this example on real accounts.

### Exercise 4 — SAVEPOINT

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

SAVEPOINT after_first_change;

UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK TO after_first_change;

ROLLBACK;
```

Observe that `ROLLBACK TO` undoes the step after the savepoint; the final `ROLLBACK` undoes the remainder of the transaction.

### Exercise 5 — DDL Causing Implicit Commit

In a dedicated lab schema, run:

```sql
UPDATE lab_accounts
SET balance = balance - 5
WHERE account_id = 1;

CREATE TABLE lab_ddl_marker (marker_id NUMBER);

ROLLBACK;
```

Check the change in `LAB_ACCOUNTS`: the DML before DDL was committed before the DDL ran, so the final rollback does not undo it. Clean up the marker table with separate DDL once done.

### Exercise 6 — JDBC autoCommit

Write a small Java program:

1. Obtain a connection from `DataSource`.
2. Print `getAutoCommit()`.
3. Execute two update statements on the same connection.
4. Test running with `true`, then `false`.
5. With `false`, call `commit()` after both steps; test making the second step fail and calling `rollback()`.
6. Compare balances after each run.

Make sure to reset lab data between runs and never alter shared pool settings of a real application.

### Exercise 7 — Different Connections

Open two connections in Java. Run one DML on connection A and a related DML on connection B, with autocommit disabled on both. Try committing A and rolling back B. Explain why rolling back B cannot undo the committed change on A and why two connections do not form one atomic transaction.

### Cleaning Up Lab Data

Only once you confirm these are the tables you created in DEV/TEST and no one else uses them:

```sql
DROP TABLE lab_accounts PURGE;
DROP TABLE lab_ddl_marker PURGE;
```

`DROP TABLE ... PURGE` removes the table and data without placing it in the recycle bin; this is DDL with implicit commit. Do not run on production or any table outside the practice scope.

## 19. Review Questions

**Q1.** What does enabled autocommit mean for a JDBC connection?

**Answer:** Each statement is committed automatically upon completion per JDBC/driver rules; consecutive statements do not automatically form a shared business transaction.

**Q2.** What is the default `autoCommit` of a new JDBC connection?

**Answer:** `true` per the JDBC contract, unless a framework/pool or application code changes the setting before use.

**Q3.** To make two UPDATE statements commit or roll back together, what must you do?

**Answer:** Use the same connection, disable autocommit, execute both statements, verify results, then call `commit()` or `rollback()`.

**Q4.** If the first UPDATE already autocommitted and the second fails, can ROLLBACK undo the first?

**Answer:** No. The first transaction already ended with a commit.

**Q5.** Does Oracle allow rolling back DDL like an uncommitted UPDATE?

**Answer:** No. DDL triggers implicit commits per Oracle rules; normal rollback cannot undo DDL or DML committed prior to it.

**Q6.** How does SAVEPOINT differ from COMMIT?

**Answer:** SAVEPOINT merely marks a position inside a transaction; ROLLBACK TO discards work after that point while keeping the transaction open. COMMIT ends the transaction and confirms changes.

**Q7.** Why must repository methods share the same connection within a transaction?

**Answer:** Each connection/session has its own transaction. Another connection does not automatically join the current connection's transaction.

**Q8.** If an INSERT fails inside a multi-statement transaction, does Oracle automatically roll back all preceding statements?

**Answer:** No. Oracle rolls back the effects of the failed statement; earlier uncommitted statements remain in the transaction, and the application must decide to roll back the whole operation when business logic fails.

**Q9.** Why should you avoid calling `setAutoCommit(true)` mid-transaction?

**Answer:** Changing auto-commit mode inside a transaction can commit the active transaction per the JDBC contract.

**Q10.** A request loses connection after sending COMMIT without receiving a response. Can you conclude the transaction rolled back?

**Answer:** No. The commit may have succeeded while the response was lost. Look up status via business key/idempotency key before retrying.

**Q11.** Is splitting an import into multiple chunks always wrong?

**Answer:** No. It can be necessary for large batches, yet each chunk is a separate transaction; checkpoints, idempotency, and a recovery workflow are required.

**Q12.** Does `@Transactional` automatically make Oracle DDL rollbackable?

**Answer:** No. DDL still follows Oracle's implicit commit behavior.

## Conclusion

**Enabled autocommit can turn every individual SQL statement into its own transaction.** While convenient for standalone operations, it is dangerous when a business workflow requires multiple statements to succeed or fail together. With JDBC, new connections default to auto-commit enabled; to group multiple statements, disable it with `setAutoCommit(false)`, reuse the same connection, check affected row counts, and commit once or roll back everything on error.

Transaction boundaries can also be altered by Oracle DDL implicit commits, self-committing procedures, separate connections, frameworks/pools, or retries after lost responses. `SAVEPOINT` supports partial rollback within the same transaction; splitting batches into multiple transactions should only be done with proper checkpoints and safe re-run mechanisms. Clearly define the atomic unit of work, manage connections and commit/rollback at one consistent layer, and test mid-flight failure scenarios before promoting data flows to production.

## References

- [Oracle Database 19c — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transactions, commit, rollback, savepoints, and read consistency.
- [Oracle Database 19c — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): ending transactions and confirming changes.
- [Oracle Database 19c — ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html): rolling back full transactions or to savepoints.
- [Oracle Database 19c — SAVEPOINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SAVEPOINT.html): creating savepoints inside a transaction.
- [Oracle Database 19c — DDL Statements](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Types-of-SQL-Statements.html): DDL/DML classification and transaction implications.
- [Java JDBC API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): `getAutoCommit`, `setAutoCommit`, `commit`, `rollback`, savepoints, and connection management.
