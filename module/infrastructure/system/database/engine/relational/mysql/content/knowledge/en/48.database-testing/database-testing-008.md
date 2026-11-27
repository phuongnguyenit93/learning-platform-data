# Testing Transactions, Rollback, Autocommit, and DDL Implicit Commit

MySQL transaction testing must prove that data commits or rolls back at the right time, multiple sessions see data according to the expected isolation level, and DDL statements do not unexpectedly alter transaction boundaries. A common mistake is writing tests assuming every SQL statement inside `START TRANSACTION` can be rolled back. In MySQL, many DDL statements cause an **implicit commit**, so a `ROLLBACK` after DDL cannot undo prior committed changes or the DDL itself.

This lesson explains how to test InnoDB transactions, autocommit, savepoints, statement errors, DDL implicit commits, and the difference between atomic DDL and transaction rollback. This content belongs to the `DATABASE_MYSQL` module, connecting table design, SQL, concurrency control, and testing MySQL-backed applications.

After this lesson, you will be able to:

- Design commit and rollback test scenarios across multiple sessions.
- Distinguish autocommit from explicit transactions.
- Test savepoints and partial rollback scope.
- Understand why a statement error does not always roll back the entire transaction.
- Identify DDL statements that trigger an implicit commit.
- Distinguish atomic DDL from rollback capability via `ROLLBACK`.
- Write safe JDBC/Spring tests that avoid letting DDL break test transactions.
- Verify outcomes on InnoDB instead of inferring from H2 or mocks.

## 1. What Do Transactions Guarantee?

A transaction groups multiple data operations into a single unit of work. With InnoDB, DML changes inside a transaction can be committed together or rolled back if the transaction aborts. This preserves business invariants such as:

- Debiting account A and crediting account B must either both succeed or both fail.
- Creating an order and its line items must be recorded consistently.
- Decrementing stock and recording the outbound inventory movement must belong to one unit of work.

ACID describes the core properties:

| Property | Meaning in testing |
|---|---|
| Atomicity | Changes within the transaction commit together or roll back per engine rules |
| Consistency | Constraints and data invariants hold before and after the transaction |
| Isolation | Concurrent transactions do not observe or interfere with data outside allowed isolation levels |
| Durability | Once committed successfully, changes persist according to MySQL and infrastructure settings |

In MySQL, rollback capability depends on the storage engine. InnoDB supports transactions; non-transactional engines like MyISAM cannot roll back DML the way InnoDB does. Therefore, before writing transaction tests, verify that the tables use InnoDB.

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts', 'orders', 'order_items');
```

## 2. Preparing an Isolated Test Schema

Never run rollback or experimental DDL scenarios on production tables. Use a dedicated schema, an ephemeral database in CI, or a MySQL test container. Prepare tables before opening transactions so DDL does not unintentionally commit the test.

Example test table setup:

```sql
CREATE DATABASE IF NOT EXISTS mysql_tx_lab;
USE mysql_tx_lab;

CREATE TABLE account_probe (
    account_id BIGINT NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_account_probe_balance CHECK (balance >= 0)
) ENGINE=InnoDB;

CREATE TABLE ddl_probe (
    probe_id BIGINT NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (probe_id)
) ENGINE=InnoDB;

INSERT INTO account_probe (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
```

These `CREATE DATABASE`, `CREATE TABLE`, and initial `INSERT` statements run outside the transaction scenario under test. Seed baseline data first, then open test sessions. If using a fresh CI database per test suite, database creation and teardown can be managed in a separate setup/teardown phase.

## 3. Default Autocommit

MySQL normally enables `autocommit` by default (`@@autocommit = 1`). Without an explicit transaction, each successful statement runs as its own transaction and commits automatically.

Check:

```sql
SELECT @@SESSION.autocommit;
```

With autocommit enabled:

```sql
INSERT INTO account_probe (account_id, balance)
VALUES (3, 250.00);

ROLLBACK;
```

The `INSERT` committed when the statement finished. The subsequent `ROLLBACK` does not remove the inserted row because there is no uncommitted transaction left to undo.

Verify from another session:

```sql
SELECT account_id, balance
FROM account_probe
WHERE account_id = 3;
```

The row is readable immediately after the first statement finishes. This is the baseline test confirming autocommit is active and each standalone DML statement commits.

### 3.1. Disabling Autocommit in a Session

```sql
SET SESSION autocommit = 0;

INSERT INTO account_probe (account_id, balance)
VALUES (4, 300.00);
```

The current session sees the new row, while another session does not see uncommitted changes under normal isolation. Next:

```sql
ROLLBACK;
```

The row with `account_id = 4` is discarded. Confirm from another session:

```sql
SELECT COUNT(*)
FROM account_probe
WHERE account_id = 4;
```

Expected result is `0`.

When `autocommit=0`, the session always operates in an implicit transaction mode: after `COMMIT` or `ROLLBACK`, the current transaction ends and subsequent statements start a new transaction. End transactions when tests finish and restore session settings if connections are reused.

### 3.2. Re-Enabling Autocommit Can Commit an Open Transaction

If a session is at `autocommit=0` with uncommitted changes, switching `autocommit` from `0` to `1` commits the current transaction. Therefore, never treat `SET autocommit = 1` as a harmless cleanup step while a test expects a rollback.

```sql
SET SESSION autocommit = 0;
INSERT INTO account_probe (account_id, balance)
VALUES (5, 400.00);

-- This statement commits the current transaction.
SET SESSION autocommit = 1;
```

After the final statement runs, row `5` has committed. If you want to discard changes, call `ROLLBACK` before re-enabling autocommit.

## 4. Explicit Transactions with START TRANSACTION

With autocommit enabled, an application can start an explicit transaction:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE account_probe
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
```

Both `UPDATE` statements belong to the same InnoDB transaction. If both succeed and `COMMIT` succeeds, changes to both rows become visible to other transactions according to isolation rules. Replacing `COMMIT` with `ROLLBACK` undoes both changes.

### 4.1. Testing Rollback Across Two Sessions

Open two independent connections, called Session A and Session B. Ensure both sessions have autocommit enabled and use InnoDB.

Session A:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 50.00
WHERE account_id = 1;

SELECT balance
FROM account_probe
WHERE account_id = 1;
```

Session A sees the updated balance inside its transaction. Before A commits, run in Session B:

```sql
SELECT balance
FROM account_probe
WHERE account_id = 1;
```

Session B still sees the previously committed value. Next, in Session A:

```sql
ROLLBACK;
```

Read again from Session B. The value must remain unchanged from before the transaction. This scenario verifies both rollback behavior and that another transaction does not observe uncommitted changes.

To avoid confusion from a `REPEATABLE READ` snapshot already opened in Session B before A committed, start a new transaction in B or finish the prior read transaction before re-reading. For simple visibility tests, you can set `READ COMMITTED` on Session B before starting its transaction.

### 4.2. `START TRANSACTION` While Another Transaction Is Open

In MySQL, starting a new transaction with `START TRANSACTION` or `BEGIN` ends any active prior transaction with an implicit commit. Do not nest `START TRANSACTION` to create nested transactions.

When you need to roll back part of the work, use `SAVEPOINT` instead of opening a new transaction inside the current one.

## 5. Savepoints and Partial Rollback

A savepoint marks a position within a transaction. The application can roll back to that point while keeping changes made before the savepoint.

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 100.00
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account_probe
SET balance = balance + 100.00
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

COMMIT;
```

After commit:

- The debit of 100 on account 1 is preserved.
- The credit of 100 on account 2 is rolled back to the savepoint.

`ROLLBACK TO SAVEPOINT` does not end the transaction. `RELEASE SAVEPOINT` removes a savepoint when no longer needed. Savepoints are discarded when the transaction ends.

DDL that triggers an implicit commit destroys the ability to roll back across that boundary via savepoint. Thus, never mix DDL into savepoint scenarios when testing DML rollback.

## 6. Statement Errors vs. Full Transaction Rollback

A failing SQL statement does not always roll back the entire transaction. In InnoDB, many errors such as duplicate key failures abort only that statement; preceding statements in the transaction remain intact and the transaction can continue if the application chooses.

Example:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 25.00
WHERE account_id = 1;

-- Duplicate primary key error; only this statement fails.
INSERT INTO account_probe (account_id, balance)
VALUES (1, 999.00);

-- If the session continues and commits, the first UPDATE still commits.
COMMIT;
```

In tests, explicitly check both individual statement outcomes and the transaction state. An application can proactively roll back the whole transaction whenever any business step fails, rather than assuming MySQL automatically does so for every error.

### 6.1. Deadlock vs. Lock Wait Timeout

- When InnoDB detects a deadlock, it selects one transaction as a victim and rolls back that entire transaction. Applications typically need to retry the whole transaction under a bounded policy.
- When lock waiting exceeds `innodb_lock_wait_timeout`, by default InnoDB normally rolls back only the waiting statement, not necessarily the whole transaction. The `innodb_rollback_on_timeout` variable can change this behavior to roll back the entire transaction.

This is a critical distinction when writing error tests. Never write tests assuming lock wait timeouts and deadlocks have identical rollback scopes. Inspect the actual server configuration and check transaction state after the error.

## 7. DDL That Triggers Implicit Commit

Many DDL statements in MySQL cause an implicit commit. Common groups include:

- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.
- `CREATE INDEX`, `DROP INDEX`.
- `TRUNCATE TABLE`.
- `RENAME TABLE`.
- Many statements that create or drop databases, views, routines, triggers, and events.
- `CREATE USER`, `ALTER USER`, `DROP USER`, and many privilege-management statements.

Most of these statements commit the active transaction before executing; many also end with a commit afterward. The complete list depends on statement type and version, so consult the MySQL documentation for each statement.

### 7.1. Testing How DDL Commits Preceding DML

Prepare `ddl_probe` before starting:

```sql
START TRANSACTION;

INSERT INTO ddl_probe (probe_id, note)
VALUES (1, 'insert before alter');

ALTER TABLE ddl_probe
    ADD COLUMN category VARCHAR(30) NULL;

ROLLBACK;
```

Outcomes to verify:

- The `INSERT` is implicitly committed before `ALTER TABLE` executes.
- `ALTER TABLE` executes as a separate DDL operation and cannot be undone by the final `ROLLBACK`.
- After `ROLLBACK`, the row `probe_id = 1` still exists and the `category` column still exists.

Verify:

```sql
SELECT *
FROM ddl_probe
WHERE probe_id = 1;

SHOW CREATE TABLE ddl_probe\G
```

This scenario demonstrates that the final `ROLLBACK` neither reverts the DDL nor undoes the DML committed by the pre-DDL implicit commit.

### 7.2. `TRUNCATE TABLE` Is Not the Same as `DELETE`

`DELETE FROM table_name` is DML and can be rolled back if the table uses InnoDB, the transaction has not committed, and no implicit-commit boundary intervenes.

`TRUNCATE TABLE` is DDL in MySQL and causes an implicit commit. Never use `TRUNCATE` inside a transaction expecting a rollback to restore deleted rows.

Safe test example on a probe table:

```sql
START TRANSACTION;
DELETE FROM ddl_probe WHERE probe_id = 1;
ROLLBACK;
```

The row is restored. Replacing `DELETE` with `TRUNCATE TABLE ddl_probe` commits the truncation under DDL rules, making it impossible to undo with `ROLLBACK`.

### 7.3. Exception for TEMPORARY TABLE

`CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` are exceptions: they do not trigger an implicit commit the way regular table creation/dropping statements do. However, creating or dropping the temporary table itself cannot be rolled back. This exception does not mean every DDL statement on a temporary table is safe inside a transaction; operations such as `ALTER TABLE` must still be checked against their respective implicit-commit rules.

## 8. Atomic DDL Does Not Mean Rollbackable DDL

MySQL 8.0 supports atomic DDL for many supported operations. Atomic DDL ensures a DDL statement executes atomically against crashes such as a server failure: after recovery, metadata and corresponding storage engine changes are either fully applied or not applied at all, depending on support for that operation.

Atomic DDL is different from transactional DDL:

| Concept | What it guarantees | Can application transaction `ROLLBACK` undo it? |
|---|---|---|
| InnoDB transactional DML | Multiple data changes commit or roll back together | Yes, before commit |
| Atomic DDL | A single DDL statement is crash-atomic within supported scope | No |
| Implicit commit | Ends the current transaction at the statement boundary | Cannot roll back past a committed boundary |

For example, `ALTER TABLE` may be atomic DDL in MySQL 8.0 yet still cause an implicit commit. If `ALTER TABLE` succeeds, a subsequent `ROLLBACK` does not revert the schema back to its pre-ALTER state.

Not all DDL statements, engines, or operations share the same atomic DDL coverage. Check documentation for the exact version and statement.

## 9. Other Statements That Can Change Transaction Boundaries

Beyond DDL, watch out for these operations:

- `SET autocommit = 1` when switching from `0` to `1` commits the current transaction.
- `START TRANSACTION`/`BEGIN` while a transaction is active ends the prior transaction.
- `LOCK TABLES` can cause an implicit commit; `UNLOCK TABLES` behavior depends on the locks held.
- Many account/privilege administration statements or system operations cause implicit commits.
- Certain statements are disallowed or behave specially inside stored programs.

Before adding any statement inside a business transaction, check the implicit-commit list in the MySQL documentation. Never assume that because syntax runs inside `START TRANSACTION`, it participates in that transaction.

## 10. Testing with JDBC

JDBC provides `Connection.setAutoCommit(false)`, `commit()`, and `rollback()` to manage transactions. Example:

```java
String sql = "UPDATE account_probe "
           + "SET balance = balance - ? WHERE account_id = ?";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setBigDecimal(1, new BigDecimal("25.00"));
        statement.setLong(2, 1L);
        int updated = statement.executeUpdate();

        if (updated != 1) {
            throw new IllegalStateException("Account to update not found");
        }

        connection.commit();
    } catch (Exception exception) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            exception.addSuppressed(rollbackFailure);
        }
        throw exception;
    }
}
```

With `setAutoCommit(false)`, the JDBC connection does not auto-commit each statement. After committing or rolling back, the application must manage the next transaction explicitly. Switching autocommit back to `true` can commit the active transaction per the JDBC contract; never do this before confirming rollback or commit has completed.

### 10.1. DDL Over JDBC Still Triggers Implicit Commit

Executing DDL via `Statement.execute()` does not make DDL transactional. Example:

```java
connection.setAutoCommit(false);

try (Statement statement = connection.createStatement()) {
    statement.executeUpdate(
        "INSERT INTO ddl_probe (probe_id, note) VALUES (10, 'before ddl')"
    );

    statement.execute("ALTER TABLE ddl_probe ADD COLUMN source_tag VARCHAR(20)");

    connection.rollback();
}
```

Once the DDL succeeds, the preceding transaction has already been implicitly committed under MySQL rules. `connection.rollback()` neither deletes row `probe_id = 10` nor removes the `source_tag` column. That is why schema setup and DML rollback tests should be separated into two phases.

## 11. Testing with Spring and JPA

Spring TestContext can open a test-managed transaction for test methods annotated with `@Transactional`. By default, the test transaction rolls back after the test completes, unless configured with `@Commit`, `@Rollback(false)`, or controlled via the test transaction API.

Example:

```java
@SpringBootTest
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void updateIsRolledBackAfterTest() {
        Account account = accountRepository.findById(1L).orElseThrow();
        account.setBalance(new BigDecimal("900.00"));

        entityManager.flush();

        Account reloaded = entityManager.find(Account.class, 1L);
        assertEquals(new BigDecimal("900.00"), reloaded.getBalance());
    }
}
```

The test transaction rolls back when the test ends under default settings. `flush()` sends SQL to the database to catch constraint violations and test database behavior; it does not commit the transaction. `find()` in the same persistence context may return the already-managed entity, so if you need to verify data reloaded from the database, call `entityManager.clear()` before reloading.

### 11.1. Never Run DDL Inside a Test Transaction Relying on Rollback

If a test executes `ALTER TABLE`, `CREATE TABLE`, or `TRUNCATE TABLE` inside a test-managed transaction, MySQL's implicit commit can commit earlier test data. When the test finishes, Spring tries to roll back the transaction, yet the committed changes remain.

Therefore:

- Create schemas and tables via migrations/setup before test transactions start.
- Keep rollback tests strictly for transactional DML on InnoDB.
- Use a separate database/schema per suite or container to isolate DDL.
- When a test must verify DDL, run it separately and clean up with explicit teardown.
- Do not rely on `@Transactional` on a test to automatically clean up schema changes.

### 11.2. Testing Across Multiple Connections

A test may use two independent connections to verify visibility, locking, and commit behavior. Ensure they do not accidentally join the same Spring transaction or share a thread-bound connection.

When using `JdbcTemplate` inside a Spring-transactional test, it normally acquires the connection bound to the active transaction. To test behavior across two sessions, create two genuinely independent transactions/connections and manage commit/rollback explicitly.

## 12. Testing Rollback with Isolation and Visibility

When verifying data across two sessions, the isolation level affects read results. Session B at `REPEATABLE READ` can retain an older snapshot if it already executed a consistent read before Session A committed.

Clear scenario:

1. Session B sets `READ COMMITTED` or starts a new transaction after A commits.
2. Session A opens a transaction and updates a row.
3. Session B reads before commit and does not see the uncommitted change.
4. Session A commits.
5. Session B reads again under `READ COMMITTED` and sees the new value.
6. Repeat the scenario with Session A rolling back; Session B sees no change.

SQL preparing Session B:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

If you want to test `REPEATABLE READ`, deliberately establish a read view and verify Session B continues seeing the old snapshot within the same transaction. Never conclude a commit failed merely because a session still reads an earlier snapshot.

## 13. Testing Deadlocks and Lock Waits

Concurrency testing should produce repeatable contention scenarios. For example, two sessions updating two rows in opposite orders:

Session A:

```sql
START TRANSACTION;
UPDATE account_probe SET balance = balance - 10 WHERE account_id = 1;
-- Wait for Session B to update row 2.
UPDATE account_probe SET balance = balance + 10 WHERE account_id = 2;
```

Session B:

```sql
START TRANSACTION;
UPDATE account_probe SET balance = balance - 20 WHERE account_id = 2;
-- After B holds the lock on row 2, attempt to update row 1.
UPDATE account_probe SET balance = balance + 20 WHERE account_id = 1;
```

Coordinate the two sessions so each holds one lock before requesting the other. InnoDB can detect the deadlock and roll back one transaction. Inspect the returned error, victim transaction, and resulting data state.

To inspect the latest deadlock details:

```sql
SHOW ENGINE INNODB STATUS\G
```

When testing lock wait timeouts, set an appropriate session value in the lab:

```sql
SET SESSION innodb_lock_wait_timeout = 3;
```

Hold the lock in Session A and ask Session B to update the same row. When B times out, verify whether only the statement rolled back or whether transaction B remains active per `innodb_rollback_on_timeout`. End both transactions after the test.

## 14. Common Mistakes in Transaction Tests

| Mistake | Why it is wrong | Right approach |
|---|---|---|
| Calling `ROLLBACK` after `INSERT` with autocommit on, expecting row deletion | The `INSERT` committed when the statement ended | Disable autocommit or use `START TRANSACTION` before DML |
| Running `ALTER TABLE` then rolling back | DDL causes an implicit commit | Separate DDL from DML transactions needing rollback |
| Using MyISAM to test rollback | Engine does not support transactions | Use InnoDB and verify `ENGINE` |
| Assuming every SQL error rolls back the entire transaction | Many errors roll back only the statement; deadlocks and lock timeouts follow distinct rules | Inspect transaction state after each error type |
| Nesting `START TRANSACTION` | MySQL does not support nested transactions this way | Use savepoints or design separate transactions |
| Using `@Transactional` tests to clean up DDL | Implicit commit can leave data behind after the test | Use separate schemas and explicit teardown |
| Checking an entity again without clearing persistence context | JPA may return the managed object instead of reading the DB | Flush then clear/reload when verifying database state |
| Testing only with H2 | DDL, locking, isolation, and SQL semantics differ from MySQL | Run integration tests against real MySQL or a version-matched container |

## 15. Repeatable Transaction Testing Workflow

1. **Create an isolated environment:** dedicated schema or MySQL container per test suite.
2. **Prepare the schema:** run migrations/setup before opening test transactions.
3. **Verify the engine:** ensure tables needing rollback use InnoDB.
4. **Record baseline:** capture initial data and relevant session variables.
5. **Check autocommit:** verify `@@SESSION.autocommit` and set it appropriately in the test session.
6. **Test DML:** exercise commit and rollback with at least one explicit transaction.
7. **Test visibility:** use two independent connections with defined isolation levels.
8. **Test savepoints/errors:** verify partial rollback, statement errors, deadlocks, and lock timeouts.
9. **Test DDL separately:** verify implicit commit on a probe table; do not mix with DML rollback tests.
10. **Test the application:** verify JDBC/Spring/JPA uses the intended connections and transaction boundaries.
11. **Cleanup:** end transactions, close connections, remove test data, and restore session settings.
12. **Archive evidence:** executed SQL, before/after results, isolation level, engine, autocommit settings, and error logs.

## 16. Practice Scenario

A sales application needs to test transferring 100 currency units from account 1 to account 2. The development team wants to ensure a failure in the second step does not lose funds, and also wants to test a migration adding a notes column to the account table.

Perform in a lab environment:

1. Create a dedicated schema and two InnoDB tables with baseline data.
2. Execute both `UPDATE` statements in one transaction, commit, and verify the total balance is unchanged.
3. Run again while triggering an error before commit; roll back and verify both balances return to baseline.
4. Enable autocommit and run one `UPDATE`; call rollback afterward to prove the statement already committed.
5. Disable autocommit, update data, and roll back; verify changes do not persist.
6. Use a savepoint to roll back only the credit step while keeping the debit step, then commit to observe the outcome.
7. Trigger a duplicate key inside a transaction and verify the statement fails while the transaction can still proceed.
8. Run an `INSERT` followed by `ALTER TABLE` inside the same transaction, call rollback, and verify both the `INSERT` and DDL remain due to implicit commit.
9. Write a Spring integration test with `@Transactional`, call `flush()`, and verify data after clearing the persistence context.
10. Run DDL tests separately on a disposable schema and clean up afterward.

**Self-assessment questions:**

- When `autocommit=1`, why does `ROLLBACK` after a successful `INSERT` not delete the row?
- How can `SET autocommit=1` affect an uncommitted transaction?
- How does `ROLLBACK TO SAVEPOINT` differ from `ROLLBACK`?
- Why does a duplicate key usually not roll back the entire InnoDB transaction automatically?
- Do deadlocks and lock wait timeouts share the same rollback scope?
- Why can `ALTER TABLE` commit preceding DML even when executed between `START TRANSACTION` and `ROLLBACK`?
- How does atomic DDL differ from transactional DDL?
- Why does `@Transactional` on a test method not guarantee cleanup of DDL changes?
- How do you verify visibility across two sessions without being misled by a `REPEATABLE READ` snapshot?

## Conclusion

MySQL transaction testing must clearly establish storage engine, autocommit state, isolation level, and commit boundaries. DML on InnoDB can roll back while inside a transaction; savepoints allow partial rollbacks; statement errors do not always abort the whole transaction. Many DDL statements trigger implicit commits, and atomic DDL only protects the atomicity of a single operation against crashes rather than allowing `ROLLBACK` of DDL. Separate schema setup from DML tests, use independent connections to verify visibility, and run integration tests against real MySQL/InnoDB.
