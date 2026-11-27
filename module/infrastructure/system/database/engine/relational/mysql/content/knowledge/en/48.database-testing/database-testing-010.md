# Testing Stored Procedures/Functions, Triggers, and Events

## Objectives

After this lesson, you will be able to:

- Identify the behaviors that must be tested for stored procedures, stored functions, triggers, and events in MySQL.
- Create repeatable test fixtures and data while isolating side effects between tests.
- Verify results, side effects, `SQLSTATE` errors, execution privileges, and transaction behavior.
- Call stored procedures with `IN`, `OUT`, and `INOUT` parameters from SQL and Java JDBC.
- Test triggers by running DML that fires them and verifying audit data.
- Test the Event Scheduler by decoupling business logic from the schedule and inspecting event status.
- Run tests against real MySQL in an isolated environment and integrate them into CI pipelines.

## 1. Why Must Stored Objects Be Tested?

MySQL does not only execute SQL statements sent directly by an application. A database can contain stored procedures, functions, triggers, and events. These objects run logic inside the server, often invoked indirectly through an SQL statement or on a schedule.

Each object type has a distinct trigger mechanism and responsibility:

| Object | Trigger mechanism | What must be verified |
|---|---|---|
| Stored procedure | Application or user calls `CALL` | Parameters, result sets, data mutations, errors, and transactions |
| Stored function | Invoked within an SQL expression | Return value, `NULL`, data types, determinism, and errors |
| Trigger | Fires automatically on `INSERT`, `UPDATE`, or `DELETE` on a table | Side effects, audit data, before/after change rules, and rollback |
| Event | Event Scheduler fires on schedule | Schedule, status, `DEFINER` privileges, invoked logic, and repeat execution |

A `CREATE PROCEDURE` statement succeeding only proves MySQL accepted the definition at creation time. It does not prove the procedure handles data correctly, returns the right results, or works with the application's privileges. Likewise, a trigger may be created successfully yet never have fired in tests; an event may be `ENABLED` while the scheduler is turned off.

Testing these objects must cover both **direct results** and **indirect side effects**. For instance, calling a fund-transfer procedure requires verifying both account balances, history records, invalid-amount handling, and transaction state on error.

## 2. Building an Isolated Test Environment

Prefer running tests on a dedicated test MySQL instance or a database/schema created specifically for each test suite. Never use a production database or a shared schema containing user data.

A solid test environment has these traits:

- Uses the exact MySQL major/minor version planned for deployment, or explicitly documents version differences.
- Builds the schema from the project's real migrations.
- Uses an account with privileges matching the application, scoped strictly to the test schema.
- Fixtures are seeded from a clean state and are reproducible.
- Does not depend on preexisting data or test execution order.
- Disables unrelated events to avoid unexpected background side effects.
- Captures logs, `SQLSTATE`, and query outputs when tests fail.

Never substitute H2 for MySQL and treat the results as equivalent. MySQL's routine, trigger, and event syntax, data types, transactions, SQL mode, and locking behavior can differ. H2 can be helpful for simple repository tests, but tests verifying MySQL objects must run on MySQL.

### 2.1. Initializing the Test Schema

Example schema for the practice exercises:

~~~sql
CREATE DATABASE IF NOT EXISTS routine_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE routine_test;

CREATE TABLE account (
    account_id BIGINT NOT NULL PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    CONSTRAINT chk_account_balance_nonnegative
      CHECK (balance >= 0)
) ENGINE=InnoDB;

CREATE TABLE transfer_audit (
    audit_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    old_balance DECIMAL(15, 2) NOT NULL,
    new_balance DECIMAL(15, 2) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE expired_session (
    session_id BIGINT NOT NULL PRIMARY KEY,
    expires_at DATETIME NOT NULL,
    cleaned_at DATETIME NULL
) ENGINE=InnoDB;
~~~

This is a compact schema for testing procedures, functions, triggers, and events. In real projects, obtain DDL from the application's migrations so you test the exact deployed structure.

### 2.2. Fixtures and Cleanup

Fixtures are input data prepared before a test. Each test should know its exact initial state:

~~~sql
DELETE FROM transfer_audit;
DELETE FROM account;

INSERT INTO account(account_id, owner_name, balance)
VALUES
  (101, 'Lan', 1000.00),
  (202, 'Minh', 500.00);
~~~

For repeatable tests, delete data by test-specific identifier keys or roll back the transaction if the object under test does not commit on its own. Never use `TRUNCATE` for cleanup inside a transaction expecting rollback, because DDL like `TRUNCATE TABLE` triggers an implicit commit in MySQL.

Tests must not depend on execution order. If test A leaves behind an audit row, test B must not assume the audit table is empty unless B prepares its own fixtures or runs an explicit cleanup mechanism.

## 3. Testing Stored Procedures

Stored procedures are invoked with `CALL`. A procedure can accept `IN` parameters, return values via `OUT`/`INOUT`, return one or more result sets, modify data, and raise errors using `SIGNAL`.

When testing a procedure, specify:

- Valid, boundary, and invalid input parameters.
- `OUT`/`INOUT` values after execution.
- Returned result sets, row counts, and contents.
- Data inserted, updated, or deleted.
- Behavior when records are not found.
- Behavior on constraint violations or SQL exceptions.
- Whether the transaction is controlled by the procedure or the caller.
- Required privileges of the calling user and `DEFINER`.

### 3.1. Creating the Sample Procedure

The following procedure transfers funds between two accounts. It validates the amount, source/destination accounts, and balance before updating.

~~~sql
DELIMITER //

CREATE PROCEDURE transfer_money(
    IN p_from BIGINT,
    IN p_to BIGINT,
    IN p_amount DECIMAL(15, 2),
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_from_balance DECIMAL(15, 2);
    DECLARE v_to_balance DECIMAL(15, 2);
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;

    IF p_from IS NULL OR p_to IS NULL THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Account identifiers are required';
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Amount must be positive';
    END IF;

    IF p_from = p_to THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Source and destination must differ';
    END IF;

    SET v_not_found = FALSE;
    SELECT balance
      INTO v_from_balance
      FROM account
     WHERE account_id = p_from
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Source account not found';
    END IF;

    SET v_not_found = FALSE;
    SELECT balance
      INTO v_to_balance
      FROM account
     WHERE account_id = p_to
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Destination account not found';
    END IF;

    IF v_from_balance < p_amount THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Insufficient funds';
    END IF;

    UPDATE account
       SET balance = balance - p_amount
     WHERE account_id = p_from;

    UPDATE account
       SET balance = balance + p_amount
     WHERE account_id = p_to;

    SET p_result = 'TRANSFERRED';
END//

DELIMITER ;
~~~

The sample procedure does not call `START TRANSACTION`, `COMMIT`, or `ROLLBACK`. It executes inside the caller's transaction if the caller opened one; if the caller uses autocommit, changes inside `CALL` belong to the session-managed statement transaction. To test atomicity, the caller should open an explicit transaction.

The `CONTINUE HANDLER FOR NOT FOUND` sets a flag when `SELECT ... INTO` finds no row. The procedure checks that flag after each `SELECT` and raises a custom business `SQLSTATE`. Because `balance` is declared `NOT NULL`, this flag cleanly distinguishes a missing account from a valid balance value.

### 3.2. Testing the Success Case

Prepare fixtures and call the procedure:

~~~sql
START TRANSACTION;

CALL transfer_money(101, 202, 125.00, @result);

SELECT @result AS transfer_result;

SELECT account_id, balance
FROM account
WHERE account_id IN (101, 202)
ORDER BY account_id;

ROLLBACK;
~~~

Expected result inside the transaction:

| account_id | Balance before | Balance after `CALL` |
|---:|---:|---:|
| 101 | 1000.00 | 875.00 |
| 202 | 500.00 | 625.00 |

`@result` must be `TRANSFERRED`. After `ROLLBACK`, querying from another session must still show balances of `1000.00` and `500.00`. This test verifies both the procedure's output and that it does not commit on its own.

### 3.3. Testing Invalid Inputs

Cases to include:

| Case | Sample input | Expected result |
|---|---|---|
| Zero amount | `0.00` | `SQLSTATE 45000`, balances unchanged |
| Negative amount | `-10.00` | `SQLSTATE 45000`, balances unchanged |
| `NULL` amount | `NULL` | `SQLSTATE 45000` |
| Same account | `101 -> 101` | `SQLSTATE 45000` |
| Missing source account | `999 -> 202` | Error handled per procedure contract |
| Missing destination account | `101 -> 999` | Error handled per procedure contract |
| Insufficient funds | `101 -> 202`, amount > balance | `SQLSTATE 45000` |

For every error case, do not check only the exception. Verify there are no unintended side effects, balances remain intact, and the transaction can be rolled back.

Error test example:

~~~sql
START TRANSACTION;

CALL transfer_money(101, 202, -10.00, @result);

-- The CALL statement is expected to raise SQLSTATE 45000.
-- The client inspects the error and rolls back the transaction.
ROLLBACK;
~~~

Depending on execution mode, the `mysql` CLI client may halt script execution on an error statement. In test automation, catch the error in the client/framework, assert `SQLSTATE`, and always clean up the transaction in a `finally`/teardown block.

### 3.4. Testing Transactions and Mid-Execution Errors

A procedure may update multiple tables. If the second statement fails after the first already ran, the caller must know whether the transaction remains active or rolled back. In InnoDB, an ordinary SQL error does not automatically roll back the entire transaction in all cases.

Procedure design and tests must clarify:

- Whether the procedure opens/commits transactions itself.
- Whether the procedure uses an `EXIT HANDLER` to `ROLLBACK` and `RESIGNAL`.
- How far the caller is responsible for commit/rollback.
- Whether the procedure can be called inside a larger caller transaction.

If a procedure manages its own transaction with `COMMIT`/`ROLLBACK`, do not invoke it inside a caller transaction expected to roll back atomically. Test the transaction contract by inducing errors at each critical step and inspecting data afterward.

## 4. Testing Stored Functions

A stored function returns a single value and can be used inside SQL expressions. Function tests typically focus on:

- Return values for valid inputs.
- Lower bounds, upper bounds, `NULL`, and invalid values.
- Rounding rules and data types.
- Determinism if the function is expected to be deterministic.
- Allowed or prohibited side effects.
- How SQL mode, collation, and time zone affect results.

### 4.1. Creating the Sample Function

Example function calculating a 2% service fee:

~~~sql
DELIMITER //

CREATE FUNCTION calculate_fee(
    p_amount DECIMAL(15, 2)
)
RETURNS DECIMAL(15, 2)
DETERMINISTIC
CONTAINS SQL
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Amount must be nonnegative';
    END IF;

    RETURN ROUND(p_amount * 0.02, 2);
END//

DELIMITER ;
~~~

The function declares `DETERMINISTIC` because identical inputs must produce identical outputs without reading mutable state. `CONTAINS SQL` fits because the body uses `SIGNAL` without reading or writing tables. These characteristics must reflect real behavior; never declare them merely to make `CREATE` succeed.

### 4.2. Testing Values and Boundaries

~~~sql
SELECT calculate_fee(100.00) AS fee_100;
SELECT calculate_fee(0.00) AS fee_zero;
SELECT calculate_fee(123.45) AS fee_fraction;
~~~

Expected results:

| Input | Result |
|---:|---:|
| 100.00 | 2.00 |
| 0.00 | 0.00 |
| 123.45 | 2.47 |

Calling the function with `NULL` or negative numbers must raise `SQLSTATE 45000`. When testing decimals, use `DECIMAL`/`BigDecimal` rather than `FLOAT`/`DOUBLE` to avoid binary floating-point rounding inaccuracies.

### 4.4. Constraints to Account For When Writing Tests

Because a stored function acts as an SQL expression, it cannot return arbitrary result sets like a procedure. Functions also face restrictions on transaction control and certain dynamic SQL operations. Therefore:

- Verify functions via return values in `SELECT`, `WHERE` predicates, or projections.
- Do not design functions to call `COMMIT`/`ROLLBACK` or return multiple result sets.
- If logic needs multiple writes, multiple outputs, or transaction control, consider a stored procedure.
- When a function reads tables, test privileges, concurrent data changes, and per-row invocation cost.

### 4.3. Testing Functions in Real Queries

A function may behave properly when called once yet cause unexpected behavior in larger queries. Test how the application invokes it:

~~~sql
SELECT
    account_id,
    balance,
    calculate_fee(balance) AS estimated_fee
FROM account
ORDER BY account_id;
~~~

Evaluate invocation count, execution plans, and query impact. A function called per row can increase CPU usage or block certain optimizations. Never hide heavy logic inside a function solely to make an SQL statement look shorter.

## 5. Testing Triggers

Triggers fire automatically on DML operations against a table. Triggers can be defined for `BEFORE` or `AFTER` `INSERT`, `UPDATE`, or `DELETE`.

When testing a trigger, execute real DML on the target table and verify:

- `NEW` values are mutated properly in `BEFORE` triggers.
- Side effects are recorded properly in `AFTER` triggers.
- The trigger runs once per affected row under MySQL's row-level semantics.
- The trigger handles `NULL`, boundary data, and skip conditions.
- Errors inside the trigger abort the originating statement as expected.
- Transaction rollback undoes side effects on InnoDB tables.
- The trigger does not conflict with foreign keys, constraints, or other triggers.

MySQL triggers are row-level triggers; there is no statement-level trigger syntax as in some other RDBMSs.

### 5.1. Creating an Audit Trigger

Trigger logging balance changes:

~~~sql
DELIMITER //

CREATE TRIGGER trg_account_balance_audit
AFTER UPDATE ON account
FOR EACH ROW
BEGIN
    IF NOT (OLD.balance <=> NEW.balance) THEN
        INSERT INTO transfer_audit(
            account_id,
            old_balance,
            new_balance
        )
        VALUES (
            NEW.account_id,
            OLD.balance,
            NEW.balance
        );
    END IF;
END//

DELIMITER ;
~~~

The trigger uses `<=>` for `NULL`-safe comparison. Because `balance` is `NOT NULL`, `<>` would work too, yet `NULL`-safe comparison keeps the condition resilient if the schema ever changes.

### 5.2. Testing Triggers on UPDATE

Prepare data and run an update:

~~~sql
DELETE FROM transfer_audit;

UPDATE account
SET balance = balance + 25.00
WHERE account_id = 101;

SELECT account_id, old_balance, new_balance
FROM transfer_audit
WHERE account_id = 101
ORDER BY audit_id;
~~~

Expect one audit row with `old_balance=1000.00` and `new_balance=1025.00`.

Next, update with the same value:

~~~sql
UPDATE account
SET balance = balance
WHERE account_id = 101;
~~~

No new audit row should be created if the value did not change. This test verifies the trigger's internal condition, not merely that the trigger exists.

### 5.3. Testing Side-Effect Rollback

Because both `account` and `transfer_audit` use InnoDB, side effects produced by the trigger share the same transaction as the triggering statement:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance + 10.00
WHERE account_id = 101;

SELECT COUNT(*) AS audit_inside_transaction
FROM transfer_audit
WHERE account_id = 101;

ROLLBACK;
~~~

Inside the transaction, the audit row appears. After rollback, both the balance and the audit row must revert to their pre-transaction state. If the audit table used a non-transactional engine, side effects would not roll back with the primary table; therefore, the storage engine of every involved table is part of the test contract.

### 5.4. Testing Triggers Aborting Statements

Create a trigger or test condition causing the trigger to raise an error:

~~~sql
DELIMITER //

CREATE TRIGGER trg_account_reject_negative
BEFORE UPDATE ON account
FOR EACH ROW
BEGIN
    IF NEW.balance < 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Balance cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

Test:

~~~sql
UPDATE account
SET balance = -1.00
WHERE account_id = 101;
~~~

Expect the statement to fail with `SQLSTATE 45000`, the balance to remain unchanged, and no audit row to be generated. This is a vital test because a trigger error can break application DML even when the outer SQL looks valid.

Never define multiple triggers for the same timing/event without checking execution order. Modern MySQL versions support multiple triggers on the same timing and event, but execution order must be explicitly declared/verified using `FOLLOWS` or `PRECEDES` when dependencies exist. Ideally, minimize order dependencies by designing independent triggers.

### 5.5. Paths That Do Not Fire Triggers

Tests must simulate actual execution paths. Triggers fire on `INSERT`, `UPDATE`, or `DELETE` against the target table, yet certain MySQL mechanisms bypass triggers in ways test authors may not expect:

- Foreign key cascade actions such as `ON DELETE CASCADE` or `ON UPDATE CASCADE` do not fire triggers on child tables.
- Direct DML on the child table still fires its triggers.
- A multi-row DML statement fires the trigger once per affected row.

If auditing or business logic relies on changes caused by foreign key cascades, never assume child-table triggers will capture them. Test the real behavior and design auditing at the proper layer.

## 6. Testing Events and the Event Scheduler

An event is an object executed by the MySQL Event Scheduler at a specific time or on a recurring schedule. Events can call procedures, update tables, or run maintenance tasks.

Two parts must be tested separately:

1. **Task logic:** the procedure or statements executed by the event.
2. **Scheduling mechanism:** the event is created properly, its status is `ENABLED`, the scheduler is running, execution timing is valid, and `DEFINER` holds the necessary privileges.

Do not use long wall-clock waits in unit tests to verify business logic. Extract task logic into a stored procedure that can be invoked directly, test that procedure deterministically, and add a dedicated integration test to verify the Event Scheduler.

### 6.1. Creating the Expired-Session Cleanup Procedure

~~~sql
DELIMITER //

CREATE PROCEDURE clean_expired_sessions()
BEGIN
    UPDATE expired_session
       SET cleaned_at = CURRENT_TIMESTAMP
     WHERE expires_at < CURRENT_TIMESTAMP
       AND cleaned_at IS NULL;
END//

DELIMITER ;
~~~

The procedure can be called directly in tests:

~~~sql
UPDATE expired_session
SET cleaned_at = NULL;

CALL clean_expired_sessions();

SELECT session_id, cleaned_at
FROM expired_session
ORDER BY session_id;
~~~

Fixtures should include expired sessions, non-expired sessions, and already-cleaned sessions. Expect `cleaned_at` to be populated only for expired sessions that had not yet been cleaned up.

### 6.2. Creating the Event

~~~sql
CREATE EVENT ev_clean_expired_sessions
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
ON COMPLETION PRESERVE
ENABLE
DO
    CALL clean_expired_sessions();
~~~

The event is scheduled daily and preserved after completion. Events can be created with `DISABLE` to stage them before running, or enabled during deployment. The final status must match operational intent.

### 6.3. Inspecting Event Metadata

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'routine_test'
  AND EVENT_NAME = 'ev_clean_expired_sessions';
~~~

Verify:

- The event exists in the intended schema.
- `STATUS` is `ENABLED` when expected to run.
- `DEFINER` exists and holds required privileges.
- Time zone and execution schedule match requirements.
- `LAST_EXECUTED` updates after the event actually runs.

`LAST_EXECUTED` may remain `NULL` before the first run. The Event Scheduler is not a hard real-time scheduler; execution can lag behind the scheduled time due to server load or scheduler overhead. Never write tests requiring an event to fire at an exact millisecond.

### 6.4. Checking the Event Scheduler

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';

SHOW PROCESSLIST;
~~~

`event_scheduler` must be `ON` for events to run. `OFF` means the scheduler is not executing events; `DISABLED` means the scheduler was disabled at startup and cannot be turned on dynamically via standard runtime statements.

In shared test environments, do not arbitrarily alter global `event_scheduler`, as doing so can trigger events in other schemas. Use a dedicated MySQL instance for tests. Enabling the scheduler may require appropriate administrative privileges and may be restricted by server configuration.

### 6.5. Testing Events Deterministically

To test business logic, call `clean_expired_sessions()` directly and verify data. To integration-test the scheduler:

1. Create a test event scheduled near the current time on a dedicated instance.
2. Verify the scheduler is `ON` and the event is `ENABLED`.
3. Poll data state or `LAST_EXECUTED` within a reasonable timeout.
4. Confirm side effects are accurate and occurred only as expected.
5. Disable or drop the event afterward.

Never use `DO SLEEP()` to wait for an event when you can poll a condition with a deadline. Tests must enforce a timeout so CI never hangs if the scheduler is inactive.

## 7. Testing DEFINER Privileges and SQL SECURITY

Stored routines, views, triggers, and events can execute with `DEFINER` or `INVOKER` privileges, depending on object type and security attributes.

For procedures and functions, `SQL SECURITY DEFINER` generally runs with the definer account's privileges; `SQL SECURITY INVOKER` runs with the caller's privileges. Triggers and events run in a definer context according to MySQL rules.

Privilege tests should verify at minimum:

- The application account holds `EXECUTE` on the procedures it calls.
- The application account lacks excessive direct privileges on sensitive tables when procedures act as the access gate.
- `DEFINER` exists and holds the exact required privileges.
- Unprivileged users receive the expected access errors.
- No object runs as `root` or with unnecessarily broad privileges.

Inspection example:

~~~sql
SHOW CREATE PROCEDURE routine_test.transfer_money;
SHOW CREATE FUNCTION routine_test.calculate_fee;
SHOW CREATE TRIGGER routine_test.trg_account_balance_audit;
SHOW CREATE EVENT routine_test.ev_clean_expired_sessions;
~~~

`SHOW CREATE` output confirms `DEFINER`, `SQL SECURITY`, the SQL mode stored with the routine, and the exact deployed definition. When running tests as the application user, open connections with that exact user rather than testing only as `root`.

A test passing as `root` does not prove the application has proper privileges. Conversely, if a `DEFINER` is missing after a restore or migration, routines or events can fail at runtime even though their definitions exist.

## 8. Testing from Java JDBC and Spring

Stored objects are commonly invoked by applications. Therefore, beyond direct SQL tests, verify that the driver reads `OUT` parameters, result sets, and `SQLException`s properly.

### 8.1. Calling Procedures with OUT Parameters in JDBC

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(
         "{call transfer_money(?, ?, ?, ?)}")) {

    call.setLong(1, 101L);
    call.setLong(2, 202L);
    call.setBigDecimal(3, new BigDecimal("125.00"));
    call.registerOutParameter(4, Types.VARCHAR);

    call.execute();

    String result = call.getString(4);
    assertEquals("TRANSFERRED", result);
}
~~~

If a test must verify transaction rollback, set `connection.setAutoCommit(false)`, call the procedure, read back data on the same connection, and roll back. Then use another connection to confirm data reverted to its initial state.

### 8.2. Calling Functions in JDBC

Functions can be invoked through a `SELECT` statement:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT calculate_fee(?)")) {

    statement.setBigDecimal(1, new BigDecimal("123.45"));

    try (ResultSet resultSet = statement.executeQuery()) {
        assertTrue(resultSet.next());
        assertEquals(
            0,
            new BigDecimal("2.47").compareTo(
                resultSet.getBigDecimal(1)
            )
        );
    }
}
~~~

Compare `BigDecimal` values with `compareTo()` when checking numeric equality regardless of scale. `equals()` compares scale too, so `2.0` and `2.00` are not equal under `equals()` despite having the same numeric value.

### 8.3. Testing SQLException

When a procedure, function, or trigger executes `SIGNAL`, Connector/J translates the error into an `SQLException`. Tests should assert `SQLState` instead of relying only on message text, which may vary:

~~~java
SQLException error = assertThrows(
    SQLException.class,
    () -> call.execute()
);

assertEquals("45000", error.getSQLState());
~~~

Vendor error codes and messages help with diagnostics, while `SQLSTATE` usually provides the more stable contract for custom business errors.

### 8.4. Testing Multiple Result Sets

A stored procedure can return multiple result sets. When calling via `CallableStatement`, iterate through results using `execute()`, `getResultSet()`, and `getMoreResults()`, checking update counts per the JDBC contract. Do not rely solely on `executeQuery()` when a procedure can return multiple result types.

When using Spring `JdbcTemplate` or `SimpleJdbcCall`, explicitly test parameter name mappings, SQL types, `OUT` parameters, and result set mappers. Metadata discovery can vary across drivers and servers; in deterministic tests, declare parameters explicitly when needed.

## 9. Testing Errors, Handlers, and Diagnostics

Stored programs can declare `DECLARE ... HANDLER` blocks to handle conditions. Tests must cover both the success path and handler paths.

Example procedure with a handler:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_account(
    IN p_id BIGINT,
    IN p_name VARCHAR(100),
    IN p_balance DECIMAL(15, 2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO account(account_id, owner_name, balance)
    VALUES (p_id, p_name, p_balance);

    COMMIT;
END//

DELIMITER ;
~~~

This procedure manages its own transaction. Do not invoke it inside a caller transaction that expects to retain rollback control, because the internal `START TRANSACTION`/`COMMIT` alters the session's transaction context. This is an example for testing handlers and should not be applied mechanically to every procedure.

Test cases:

- Successful insert.
- Duplicate primary key.
- `CHECK` constraint violation.
- `NULL` value in a `NOT NULL` column.
- Failure in a later step after earlier changes occurred.
- Handler rollback and `RESIGNAL` propagating the error to the caller.

If a handler swallows an error without `RESIGNAL`, the application may falsely treat the call as successful. Tests must verify the error contract the application relies on.

## 10. Inspecting Metadata and Object State

Use `information_schema` to verify objects were created:

~~~sql
SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE,
       DEFINER, SECURITY_TYPE, SQL_DATA_ACCESS
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'routine_test'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;

SELECT TRIGGER_SCHEMA, TRIGGER_NAME, EVENT_MANIPULATION,
       EVENT_OBJECT_TABLE, ACTION_TIMING, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'routine_test'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;

SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, DEFINER, LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'routine_test'
ORDER BY EVENT_NAME;
~~~

Metadata tests confirm migrations or deployments created the intended objects. However, object existence does not replace behavioral tests. A procedure can have the exact right name and `DEFINER` while containing buggy logic.

Compare `SHOW CREATE` or metadata against the expected schema version in migrations. When comparing definition checksums, normalize whitespace and volatile metadata first; do not treat formatting differences as logic changes.

## 11. Testing Migrations That Modify Stored Objects

Stored objects are part of the schema version. When modifying routines, triggers, or events, verify:

- Migrations can run from an empty database.
- Upgrade migrations from a prior version cleanly replace the object.
- `DROP ... IF EXISTS` and `CREATE` do not leave a window where the application calls a missing object during online deployment.
- `DEFINER` and privileges remain valid on the target environment.
- Routine SQL mode, character set, and collation are appropriate.
- Rollback or forward-fix migrations are clearly defined.

MySQL DDL typically causes an implicit commit. Never assume a sequence of `DROP PROCEDURE`, `CREATE PROCEDURE`, and `CREATE TRIGGER` can roll back like a regular data transaction. For live-traffic deployments, design rollout ordering so the application remains compatible throughout object replacement.

Post-migration verification example:

~~~sql
SELECT ROUTINE_NAME
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'routine_test'
  AND ROUTINE_NAME = 'transfer_money';

SHOW CREATE PROCEDURE routine_test.transfer_money;
~~~

Then run both positive and negative behavioral tests to confirm the updated logic actually works.

## 12. Testing Concurrency and Repeatability

Stored procedures and triggers are often invoked concurrently across many connections. Single-threaded tests can miss race conditions, deadlocks, and lost updates.

Scenarios to test:

- Two transactions transferring funds out of the same account simultaneously.
- Two concurrent requests updating the same row.
- Two transactions updating multiple rows in opposite lock orders.
- Triggers writing into an audit table with indexes or unique constraints.
- An event running concurrently with application tasks updating the target table.
- A procedure retried after a timeout when the caller does not know whether the prior attempt committed.

Concurrency testing cannot rely on two `UPDATE` statements in one session. You need two separate connections, synchronized start timing, and final state verification after both finish.

In the sample transfer procedure, two transactions transferring funds in opposite directions can lock accounts in opposite orders and deadlock. Reduce risk by locking accounts in a consistent `account_id` order, while ensuring the application handles deadlocks (e.g., MySQL error `1213`) by rolling back and retrying the whole transaction with bounded retries and backoff. Never retry only the final `UPDATE`.

If a procedure represents a retryable business operation, design an idempotency key or request ledger table. Write tests invoking the same request twice and verifying no duplicate side effects occur.

For audit triggers, clarify whether audit rows are generated per actual row change or per statement. In MySQL, row-level triggers run for each affected row; an `UPDATE` touching 100 rows can create 100 audit rows.

## 13. Testing Events Without Unintended Side Effects

Events can fire automatically as soon as they are enabled. During testing and deployment:

- Use dedicated event names for tests.
- Set short schedules paired with test timeouts.
- Run only on test instances/schemas.
- Prepare data with isolated test identifiers.
- Verify affected row counts and filter predicates.
- Disable or drop test events during teardown.
- Never leave test events running after the pipeline finishes.

Recurring events must be tested for idempotency. If the job runs twice, is data processed twice? If an earlier run fails halfway through, can the next run resume safely?

The Event Scheduler runs inside MySQL Server. Across server restarts, scheduler and event behavior depend on server configuration and persisted event states. Verify post-restart behavior in integration or deployment tests rather than checking only immediately after `CREATE EVENT`.

## 14. Organizing the Test Suite

A practical test suite splits into layers:

| Test layer | Scope | Examples |
|---|---|---|
| SQL behavior tests | Procedure/function/trigger logic | Valid/boundary inputs, side effects, `SQLSTATE` |
| JDBC integration tests | How the application invokes stored objects | `CallableStatement`, `OUT` params, result sets, exceptions |
| Permission tests | `INVOKER`/`DEFINER` privileges | App user can call procedure without direct table reads |
| Migration tests | Post-deploy definitions | Object existence, signature, `DEFINER`, SQL mode |
| Scheduler tests | Event Scheduler | Event enabled, executes, updates `LAST_EXECUTED`, cleanup |
| Concurrency tests | Multiple sessions | Deadlocks, lost updates, idempotency, duplicate side effects |

Not every suite needs the same cadence. Logic and JDBC tests can run on every pull request in a MySQL container. Scheduler, heavy concurrency, and upgrade tests can run in integration or nightly pipelines.

### 14.1. Using Testcontainers or a Dedicated MySQL Instance

In Java, Testcontainers can launch real MySQL for integration tests. Illustrative Maven dependency:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>
~~~

JUnit 5 example:

~~~java
@Testcontainers
class StoredProcedureIT {
    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("routine_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void procedureTransfersMoney() throws Exception {
        // Run migrations/schema fixtures on the container.
        // Call the procedure over JDBC.
        // Assert outputs and side effects.
    }
}
~~~

Image tags must be pinned to the version under test; never use `latest` in CI as results can shift unexpectedly. The sample test account and password are for disposable containers only and must never be reused in real environments.

Some event tests require special privileges or global settings. Verify whether the container image and config permit enabling the Event Scheduler. If tests cannot toggle the scheduler, still test the procedure invoked by the event and validate the scheduler in a dedicated integration environment.

### 14.2. Fixtures via Migrations

Tests should apply the same migrations that create routines, functions, triggers, and events in real deployments. Separate SQL scripts can seed test data, but never duplicate object definitions in another file—otherwise tests no longer verify the deployed artifacts.

When creating objects via test scripts, remember `DELIMITER` is a `mysql` client directive, not server-side SQL accepted by JDBC. Over JDBC, send the entire `CREATE PROCEDURE ... BEGIN ... END` statement as a single call without `DELIMITER`.

## 15. Common Testing Errors

| Error | Cause | How to fix |
|---|---|---|
| Procedure test passes as `root` but fails in app | `EXECUTE`, `DEFINER`, or table privileges differ | Run tests as the application user and check `SHOW GRANTS` |
| Trigger does not fire in tests | Test only checks metadata or touches wrong table/event | Execute real `INSERT`/`UPDATE`/`DELETE` on the target table |
| Audit row remains after rollback | Side-effect table uses non-transactional engine or test committed | Use InnoDB and verify transaction boundaries |
| Event does not run | `event_scheduler` `OFF`/`DISABLED`, event `DISABLED`, or bad `DEFINER` | Check global variable, metadata, and server logs |
| Flaky event tests | Test expects exact wall-clock timing or scheduler is busy | Use timeouts, condition polling, and decouple logic from schedule |
| JDBC fails to read `OUT` parameter | Missing SQL type registration or wrong call syntax | Use `CallableStatement` and register `OUT` before `execute` |
| `DECIMAL` comparison fails | Using `BigDecimal.equals()` across different scales | Use `compareTo()` or assert expected scale explicitly |
| Order-dependent tests | Non-independent fixtures or cleanup | Reset data by test ID or use separate schemas |
| Migration passes yet logic fails | Only checked `CREATE` success | Run behavioral tests after migration |
| Script fails at `DELIMITER` under JDBC | Sending client command to SQL server | Remove `DELIMITER` in JDBC; keep it only in `mysql` CLI scripts |

## 16. Pre-Production Testing Checklist

### Stored Procedures and Functions

- [ ] Tested valid, boundary, `NULL`, and invalid inputs.
- [ ] Verified `OUT`/`INOUT` parameters, result sets, and return values.
- [ ] Tested `SQLSTATE`, handlers, and `RESIGNAL`.
- [ ] Clarified who owns transaction management and commit/rollback.
- [ ] Checked performance when invoked across multi-row queries.

### Triggers

- [ ] Executed real DML to fire every trigger.
- [ ] Verified `OLD`/`NEW` handling and change conditions.
- [ ] Confirmed accurate audit/side-effect rows.
- [ ] Tested rollback across all involved transactional tables.
- [ ] Verified trigger errors properly fail the originating statement.
- [ ] Checked execution order when multiple triggers share an event/timing.

### Events

- [ ] Inspected event metadata, schedule, time zone, status, and `DEFINER`.
- [ ] Confirmed `Event Scheduler` is `ON` in the target environment.
- [ ] Tested the event-invoked procedure by calling it directly.
- [ ] Ran an integration test proving the scheduler actually executes the event.
- [ ] Tested recurring runs, server restarts, and cleanup.

### Application and Operations

- [ ] Executed tests on a production-compatible MySQL version.
- [ ] Invoked routines through the exact JDBC/Spring API used by the app.
- [ ] Ran tests using the application account, not only `root`.
- [ ] Verified migrations and `SHOW CREATE` after deployment.
- [ ] Maintained isolated fixtures, cleanup, and timeouts.
- [ ] Left no test events or seed data behind after the suite completes.
- [ ] Collected logs/`SQLSTATE` without exposing secrets or sensitive data.

## 17. Practice Exercise

A sales system includes:

- Procedure `transfer_money` transferring funds between two accounts.
- Function `calculate_fee` calculating fees.
- Trigger recording audit entries when balances change.
- Event `ev_clean_expired_sessions` running daily to mark expired sessions.

Build a test suite for all four objects:

1. Stand up a dedicated MySQL test instance and run migrations creating schemas/objects.
2. Write procedure tests for valid, zero, negative, insufficient-balance, and missing-account cases.
3. Verify `OUT` parameters, both account balances, and rollback at test completion.
4. Write function tests for zero, decimal, `NULL`, and negative inputs; assert `SQLSTATE`.
5. Write trigger tests using an `UPDATE`, a no-op update with identical value, and an error-inducing update; verify audit rows.
6. Roll back a transaction firing the trigger and verify neither the primary table nor the audit table retains changes.
7. Invoke the cleanup procedure directly against fixtures with expired, active, and already-cleaned sessions.
8. Create a test event scheduled near the current time, verify `Event Scheduler`, `STATUS`, and `LAST_EXECUTED`, then clean up the event.
9. Run privilege tests using the application user and inspect `DEFINER`.
10. Integrate tests into CI, pin the MySQL image, and collect logs on failure.

**Self-check questions:**

1. Why is verifying that `CREATE PROCEDURE` succeeded not enough?
2. What must be verified for a procedure with `OUT` parameters?
3. Why must trigger tests run real DML on the table?
4. Why do InnoDB trigger side effects roll back with the transaction?
5. How do functions differ from procedures in invocation and return values?
6. Why should event logic be extracted into a directly callable procedure?
7. How does `event_scheduler=OFF` differ from `DISABLED`?
8. Why can testing as `root` mask application privilege bugs?
9. Why must `DELIMITER` not be sent inside JDBC statements?
10. How do you test a recurring event without introducing duplicate side effects?

## Conclusion

Testing stored procedures, functions, triggers, and events must verify both direct outputs and side effects in a real MySQL context. Procedures require checking parameters, `OUT`/result sets, errors, and transactions; functions require checking return values and boundaries; triggers require real DML activation and rollback verification; events require testing both task logic and scheduler, schedule, and `DEFINER` configuration. Using isolated fixtures, application-equivalent privileges, post-deployment migration checks, and CI automation catches defects before stored objects impact production data.

## References

- [MySQL 8.4 Reference Manual — Stored Objects](https://dev.mysql.com/doc/refman/8.4/en/stored-objects.html)
- [MySQL 8.4 Reference Manual — Stored Procedure Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual — Stored Function Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-function.html)
- [MySQL 8.4 Reference Manual — Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/triggers.html)
- [MySQL 8.4 Reference Manual — Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/event-scheduler.html)
- [MySQL 8.4 Reference Manual — CREATE EVENT](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL Connector/J Developer Guide — CallableStatement](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
