# Packaging Stored Procedures with Error Contracts and Testing

A stored procedure can encapsulate a data workflow into a single stable entry point: validating inputs, locking rows, updating records, and returning results. However, a procedure is only easy to integrate when the application knows exactly which parameters are required, how results are returned, how business errors differ from system errors, who owns the transaction, and which privileges execute when the procedure runs.

This lab builds the `reserve_inventory` procedure to reserve stock. The procedure accepts a product ID and quantity, locks the inventory record, rejects invalid or under-stocked requests, updates the quantity, and returns remaining stock. Later sections test success paths, errors, rollbacks, concurrency, and permissions from a Java application.

## 1. Designing the Contract Before Writing SQL

A procedure contract is the interface between the database and the caller. It needs to be as stable as an API:

| Component | `reserve_inventory` Contract |
|---|---|
| Name | `reserve_inventory` |
| Input `p_sku_id` | Required positive SKU ID referencing an inventory row |
| Input `p_quantity` | Required quantity to reserve, strictly greater than 0 |
| Output `p_remaining` | Remaining available quantity after a successful reservation |
| Success | Procedure completes normally and output contains a value |
| Non-existent SKU | SQLSTATE `45000`, application error code `30002` |
| Invalid quantity | SQLSTATE `45000`, application error code `30001` |
| Insufficient stock | SQLSTATE `45000`, application error code `30003` |
| Unexpected SQL error | Preserve original SQLSTATE and error code for the caller to handle |
| Transaction | Caller owns the transaction; procedure never issues `COMMIT` or `ROLLBACK` |
| Privileges | `SQL SECURITY INVOKER`; caller requires execute and table privileges |

Separate business errors from infrastructure failures. `INSUFFICIENT_STOCK` is an expected business outcome; deadlocks, dropped connections, or disk errors are incidents requiring different retry and alerting policies. Never return a generic "operation failed" message for everything.

### Error code conventions

MySQL allows procedures to raise application-defined errors via `SIGNAL SQLSTATE '45000'`. You can attach `MYSQL_ERRNO` so callers distinguish specific cases:

| MYSQL_ERRNO | SQLSTATE | Business Code | Meaning |
|---:|---|---|---|
| 30001 | `45000` | `INVALID_QUANTITY` | Quantity is NULL or non-positive |
| 30002 | `45000` | `SKU_NOT_FOUND` | No matching SKU exists |
| 30003 | `45000` | `INSUFFICIENT_STOCK` | Available stock is below requested quantity |

Choose a dedicated application error range, document it, and avoid colliding with native MySQL error codes handled by your stack. Applications should branch on SQLSTATE and vendor error code; `MESSAGE_TEXT` is for diagnostics and should not be the sole branching key because wording may evolve.

## 2. Creating the Lab Schema

We use InnoDB for transactions and row-level locking. The `inventory` table has one row per SKU:

```sql
CREATE DATABASE IF NOT EXISTS warehouse_demo;
USE warehouse_demo;

CREATE TABLE inventory (
  sku_id BIGINT UNSIGNED NOT NULL,
  available_qty BIGINT NOT NULL,
  updated_at TIMESTAMP(6) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sku_id),
  CONSTRAINT chk_inventory_nonnegative
    CHECK (available_qty >= 0)
) ENGINE=InnoDB;

INSERT INTO inventory (sku_id, available_qty)
VALUES (1001, 12), (1002, 0), (1003, 4);
```

MySQL enforces `CHECK` constraints starting in version 8.0.16. Even with the constraint, the procedure must still validate business conditions and update atomically. Constraints are the final line of defense for data integrity, not a substitute for API validation.

Verify the initial data:

```sql
SELECT sku_id, available_qty
FROM inventory
ORDER BY sku_id;
```

## 3. Writing the Procedure with SIGNAL, Handlers, and RESIGNAL

The procedure uses `SELECT ... FOR UPDATE` to lock the inventory row inside the caller's transaction. A `NOT FOUND` handler detects missing SKUs. Other SQL exceptions propagate naturally to the caller; a later section covers using `GET DIAGNOSTICS` and `RESIGNAL` when a routine needs a handler for cleanup.

In the MySQL command-line client, `DELIMITER` is a client directive to change the statement terminator when defining a routine containing internal `;` characters. It is not a SQL statement sent to the server. GUIs or migration tools may submit scripts differently; never include `DELIMITER` inside JDBC statements.

```sql
DELIMITER //

CREATE PROCEDURE reserve_inventory(
  IN p_sku_id BIGINT,
  IN p_quantity BIGINT,
  OUT p_remaining BIGINT
)
SQL SECURITY INVOKER
MODIFIES SQL DATA
BEGIN
  DECLARE v_available BIGINT DEFAULT NULL;
  DECLARE v_not_found BOOLEAN DEFAULT FALSE;

  DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_not_found = TRUE;

  SET p_remaining = NULL;

  IF p_sku_id IS NULL OR p_sku_id <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30002,
          MESSAGE_TEXT = 'SKU_NOT_FOUND';
  END IF;

  IF p_quantity IS NULL OR p_quantity <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30001,
          MESSAGE_TEXT = 'INVALID_QUANTITY';
  END IF;

  SELECT available_qty
    INTO v_available
  FROM inventory
  WHERE sku_id = p_sku_id
  FOR UPDATE;

  IF v_not_found THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30002,
          MESSAGE_TEXT = 'SKU_NOT_FOUND';
  END IF;

  IF v_available < p_quantity THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30003,
          MESSAGE_TEXT = 'INSUFFICIENT_STOCK';
  END IF;

  UPDATE inventory
  SET available_qty = available_qty - p_quantity
  WHERE sku_id = p_sku_id;

  SET p_remaining = v_available - p_quantity;
END//

DELIMITER ;
```

Local variables must be declared before handlers and executable statements. `CONTINUE HANDLER FOR NOT FOUND` merely flags that no row was found; the procedure explicitly raises the business error after inspecting the flag. Other SQL exceptions propagate directly to the caller because the procedure does not intercept them.

Do not insert an error log into an audit table inside the same transaction and expect it to survive after the caller rolls back: that audit insert will be rolled back too. If persistent error auditing is required, use out-of-band logging outside the transaction or a separate recording mechanism with clear transaction boundaries.

## 4. Why Does the Procedure Require the Caller's Transaction?

`SELECT ... FOR UPDATE` locks the row to prevent two transactions from reading the same stale stock quantity and both deducting stock. Locks are only held for the duration of a transaction. If the caller runs in autocommit mode and the procedure does not open a transaction, the lock acquired by `SELECT` can be released as soon as the statement completes before the subsequent `UPDATE` executes.

Therefore, the procedure contract requires the caller to start a transaction before calling and commit only when the procedure succeeds:

```sql
START TRANSACTION;
CALL reserve_inventory(1001, 3, @remaining);
SELECT @remaining AS remaining_qty;
COMMIT;
```

If `CALL` raises an error, the caller must `ROLLBACK` the transaction instead of committing. In a SQL client, execute `ROLLBACK` after receiving an error; in Java, place rollback inside the exception handler. The snippet above shows the happy path, not an automated script handling both branches.

Because the procedure does not execute `START TRANSACTION`, `COMMIT`, or `ROLLBACK`, it can participate inside a broader order transaction. The caller can verify prices, insert an order, reserve inventory, and insert order items in a single transaction. If any step fails, the caller rolls back the entire unit of work.

Never invoke `COMMIT` inside a shared procedure if the contract assigns transaction ownership to the caller. Calling `COMMIT` inside a routine commits the caller's outer transaction as well, breaking atomicity of the surrounding business workflow.

### Rollback scope

Rollback only undoes transactional InnoDB changes within the current transaction. DDL statements such as `CREATE TABLE` or `ALTER TABLE` trigger implicit commits; changes on non-transactional tables and external side effects are likewise not rolled back as the caller might expect. Business procedures should stick to DML and avoid mixing DDL into order-processing transactions.

## 5. SIGNAL, RESIGNAL, and Handler Types

### SIGNAL: raising an intentional business error

`SIGNAL` terminates execution flow with a condition. Example:

```sql
SIGNAL SQLSTATE '45000'
  SET MYSQL_ERRNO = 30003,
      MESSAGE_TEXT = 'INSUFFICIENT_STOCK';
```

`45000` is the SQLSTATE reserved for unhandled user-defined exceptions. `MYSQL_ERRNO` and `MESSAGE_TEXT` supply the code and text for application classification. Never expose internal details like hostnames, SQL containing sensitive data, or secrets in error messages.

### RESIGNAL: preserving or augmenting the active error

`RESIGNAL` is only valid inside a handler to re-raise the condition currently being handled. Simple form:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
  RESIGNAL;
END;
```

Use `RESIGNAL` instead of raising a fresh `SIGNAL SQLSTATE '45000'` when you want to preserve original errors such as duplicate keys, deadlocks, or constraint violations. Raising a generic new error strips the original SQLSTATE and vendor code needed by the caller to decide between retrying and failing.

When a routine needs to perform cleanup or capture diagnostics before propagating an error, use the following pattern. Local variables must be declared before handlers in the actual block:

```sql
DECLARE v_state CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
  GET DIAGNOSTICS CONDITION 1
    v_state = RETURNED_SQLSTATE,
    v_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;

  -- Perform cleanup owned by this routine here.
  -- Then re-raise the original condition so the caller can still classify the error.
  RESIGNAL;
END;
```

Do not add handlers solely to wrap every error into a single generic code. If the routine requires no cleanup, let SQL errors propagate untouched; if persistent auditing is needed, remember rows written in the same transaction roll back with the business data.

### EXIT vs. CONTINUE

| Handler | Behavior |
|---|---|
| `CONTINUE` | Handles the condition and resumes execution at the statement following the one that raised the condition |
| `EXIT` | Terminates the `BEGIN ... END` block where the handler is declared |

`NOT FOUND` occurs when `SELECT ... INTO` returns no rows or a cursor reaches the end of its data. For cursor loops, set a flag inside a `CONTINUE HANDLER FOR NOT FOUND` and exit the loop when the flag turns true. `SQLEXCEPTION` excludes SQLSTATE classes `00`, `01`, and `02`; therefore handle `SQLWARNING` and `NOT FOUND` separately if the procedure depends on them.

### GET DIAGNOSTICS

`GET DIAGNOSTICS` reads condition details from the diagnostics area, such as SQLSTATE, error number, and message:

```sql
GET DIAGNOSTICS CONDITION 1
  v_sqlstate = RETURNED_SQLSTATE,
  v_mysql_errno = MYSQL_ERRNO,
  v_message = MESSAGE_TEXT;
```

Condition 1 is the first condition in the diagnostics area. When multiple conditions or warnings exist, check the condition count and inspect the relevant condition. Never rely on message text as your sole stable contract, as wording can vary across versions or locales.

## 6. Testing Directly with a SQL Client

Before wiring up Spring Boot, verify the procedure with reproducible scenarios. Every successful call must run inside a transaction:

```sql
START TRANSACTION;
CALL reserve_inventory(1001, 2, @remaining);
SELECT @remaining AS remaining_qty;
COMMIT;

SELECT sku_id, available_qty
FROM inventory
WHERE sku_id = 1001;
```

Starting from 12, the remaining result must be 10. Check both the output parameter and the actual table value after commit.

Error cases:

```sql
-- Invalid quantity: SQLSTATE 45000, MYSQL_ERRNO 30001
START TRANSACTION;
CALL reserve_inventory(1001, 0, @remaining);
ROLLBACK;

-- Non-existent SKU: SQLSTATE 45000, MYSQL_ERRNO 30002
START TRANSACTION;
CALL reserve_inventory(999999, 1, @remaining);
ROLLBACK;

-- Insufficient stock: SQLSTATE 45000, MYSQL_ERRNO 30003
START TRANSACTION;
CALL reserve_inventory(1002, 1, @remaining);
ROLLBACK;
```

In an interactive client, each failing `CALL` returns control to the client; run `ROLLBACK` on the open transaction before executing the next case. Some GUIs halt script execution on error, so run each case individually or use an automated test harness that always rolls back in the error branch.

Inspect the procedure and its definition:

```sql
SHOW CREATE PROCEDURE reserve_inventory\G

SELECT
  ROUTINE_NAME,
  SECURITY_TYPE,
  SQL_DATA_ACCESS,
  DEFINER
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'warehouse_demo'
  AND ROUTINE_NAME = 'reserve_inventory';
```

## 7. Testing the Error Contract in Java/JDBC

JDBC surfaces stored procedure errors via `SQLException` or its subclasses. For business errors raised via `SIGNAL`, inspect `SQLState` and the vendor error code rather than comparing full message strings.

Example calling the procedure and managing the transaction:

```java
long reserveInventory(DataSource dataSource, long skuId, long quantity)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            long remaining;
            try (CallableStatement call = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                call.setLong(1, skuId);
                call.setLong(2, quantity);
                call.registerOutParameter(3, Types.BIGINT);
                call.execute();
                remaining = call.getLong(3);
            }

            connection.commit();
            return remaining;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        }
    }
}
```

This example focuses on the JDBC boundary. In Spring, let a `@Transactional` service method own the transaction and invoke the procedure via `JdbcTemplate`, `SimpleJdbcCall`, or a `CallableStatement` bound to the same transaction connection. Do not open a separate connection inside a procedure wrapper if it needs to share a transaction with JPA.

Asserting the error:

```java
SQLException error = assertThrows(SQLException.class, () ->
    reserveInventory(dataSource, 1002L, 1L)
);

assertEquals("45000", error.getSQLState());
assertEquals(30003, error.getErrorCode());
```

In some framework layers, exceptions may be wrapped in `DataAccessException` or another wrapper. In that case, walk the cause chain to locate the underlying `SQLException` and check `SQLState` and vendor error code there. Drivers or frameworks can surface exceptions differently; tests should pin the connector version and verify actual behavior.

Do not assert against the entire `getMessage()` string since it may include table names, SQL fragments, or version-specific phrasing. For custom errors, you can check a short token if it is explicitly committed in the contract.

### Indeterminate COMMIT outcomes and idempotency

If the connection drops right during `COMMIT`, the application may not know whether the server committed the transaction. Immediately calling the procedure again with a fresh request could deduct stock a second time. Calling `rollback()` on a broken socket does not prove the transaction was not committed.

In a checkout workflow, store a stable idempotency key alongside the order in the very same transaction containing the procedure call:

```sql
CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id BINARY(16) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (order_id),
  UNIQUE KEY uq_orders_request_id (request_id)
) ENGINE=InnoDB;
```

Upon receiving a retry of the same request, the application queries `request_id` on a fresh connection. If the order already exists, return the stored outcome; only if it does not exist, run the transaction again with the same key. Duplicate key handling must verify the matching request payload rather than blindly ignoring errors. Because both the order and the inventory deduction commit in the same InnoDB transaction, this key tells the caller whether the previous attempt completed.

## 8. Testing Rollback and Atomicity

Construct a multi-step transaction: insert an order record, call `reserve_inventory`, and deliberately raise an error in a subsequent step. After rolling back, confirm both order and inventory remain in their pre-transaction states.

Scenario:

1. Read initial stock for SKU 1001.
2. Start a transaction.
3. Insert a pending order row.
4. Call the procedure to deduct inventory.
5. Intentionally fail the order-item insert step, or trigger a caller rollback.
6. Verify the order does not exist and stock is unchanged.

This is why the procedure does not commit on its own. If the procedure committed right after deducting inventory, the outer transaction could not atomically roll back the entire order.

Also test when the procedure raises an error prior to updating. Caller rollback must still behave cleanly with zero partial changes left in the `inventory` table.

## 9. Testing Concurrency and Row Locking

Suppose SKU 1001 has 10 units. Two concurrent requests each try to reserve 7 units. The only valid outcome is one request succeeding while the other receives `INSUFFICIENT_STOCK`, leaving final stock non-negative.

Test design:

1. Open two independent JDBC connections.
2. Start a separate transaction on each connection.
3. Use a barrier/latch in the test harness so both workers call the procedure nearly simultaneously.
4. The first worker acquires the row lock; the second worker waits.
5. The first worker deducts 7 and commits.
6. The second worker resumes, reads the updated quantity of 3, and receives the insufficient-stock error.
7. The second caller rolls back.
8. Assert remaining stock is 3, non-negative, and only one reservation succeeded.

Never use `Thread.sleep()` as the primary synchronization mechanism. Use `CountDownLatch`, `CyclicBarrier`, or equivalent primitives to coordinate when the two transactions start.

`SELECT ... FOR UPDATE` protects properly only when the two workers use separate transactions and the first transaction has not committed before the second worker performs its locking read. If a test accidentally executes both calls on the same connection or under autocommit, it fails to simulate the concurrency being verified.

### Deadlocks and lock wait timeouts

When transactions lock multiple SKUs in different orders, a deadlock can arise. MySQL picks a victim transaction and returns an error; the application must roll back that transaction and may retry the entire unit of work within bounded attempts.

Lock wait timeouts differ from deadlocks. Under common InnoDB defaults, a lock wait timeout typically rolls back only the timed-out statement rather than the whole transaction; the application must explicitly roll back the transaction per contract before retrying. Check `innodb_rollback_on_timeout` and your actual server configuration behavior.

Never retry just the failed `UPDATE` after a deadlock and continue the old transaction. Retrying must start a fresh transaction and replay the entire atomic business operation.

## 10. EXECUTE Privileges and SQL SECURITY

Stored procedures have two primary security models:

| Mode | Privileges Used at Runtime | Caller Requirements |
|---|---|---|
| `SQL SECURITY INVOKER` | Privileges of the account invoking the procedure | `EXECUTE` plus privileges on tables/views accessed by the routine |
| `SQL SECURITY DEFINER` | Privileges of the account declared as definer | Typically `EXECUTE`; the routine executes operations using the definer's privileges |

Our current procedure uses `SQL SECURITY INVOKER`. The caller must hold required privileges on `warehouse_demo.inventory`:

```sql
GRANT EXECUTE
ON PROCEDURE warehouse_demo.reserve_inventory
TO 'orders_app'@'10.20.%';

GRANT SELECT, UPDATE
ON warehouse_demo.inventory
TO 'orders_app'@'10.20.%';
```

If you want to hide direct table access and expose only a controlled operation to callers, consider `SQL SECURITY DEFINER`. In that case:

- Use a dedicated definer account with the minimum privileges required by the routine.
- Never use personal accounts or full-admin accounts as the definer.
- Keep the definer account intact across migrations, restores, and DR environments.
- Inspect `SHOW CREATE PROCEDURE` and `DEFINER` after deployment.
- Be cautious with dynamic SQL and any input capable of influencing the executed statement.

A `DEFINER` routine can become a privilege escalation path if callers can inject unintended SQL control. On managed MySQL services, providers may also restrict setting definers or require special accounts; verify platform rules before adopting this model.

## 11. Dynamic SQL and Injection Prevention

Never concatenate caller input directly into dynamic SQL. Use parameter binding for values. For table/column names or sort directions, parameter markers cannot replace identifiers; validate inputs against an allowlist before interpolating them into the statement.

Unsafe example:

```sql
-- Do not do this with untrusted input
SET @sql = CONCAT(
  'SELECT * FROM orders WHERE customer_id = ',
  p_customer_id
);
```

If dynamic SQL is truly unavoidable, allowlist identifiers and bind values via placeholders. Prepared statements inside stored programs have scoping limits for local variables; values typically must be copied into user variables before `EXECUTE ... USING`. User variables are session-scoped, so manage their names and state carefully when using connection pools.

When a procedure operates on a fixed table and fixed set of columns like `reserve_inventory`, dynamic SQL is unnecessary. Static SQL is easier to test, easier to grant privileges for, and carries lower risk.

## 12. Rules for Returning Stable Results

Stored procedures can return data via OUT/INOUT parameters or result sets. Choose one clear contract per routine:

- OUT parameters suit a small, fixed set of scalar values.
- Result sets suit returning multiple rows or query datasets.
- Never leave debug `SELECT` statements inside procedures, as they emit extra result sets that can confuse JDBC callers.
- Clearly specify column names, data types, column order, and nullability when returning result sets.
- Never alter signatures or output semantics without coordinating application versions.

MySQL does not support procedure overloading by creating multiple procedures with the same name and different signatures. When introducing breaking contract changes, create a versioned name such as `reserve_inventory_v2`, roll out updated callers, and deprecate the old version on schedule.

Avoid using output parameters to return errors alongside SQL exceptions unless callers follow a strict documented convention. For errors, raise an exception; on success, return outputs. This avoids ambiguous half-success/half-error states.

## 13. Testing Privileges with a Realistic Runtime Account

Testing as a DBA account hides permission defects. Create an account mirroring runtime privileges and execute the procedure with it.

Checks:

1. Runtime account can invoke the procedure when granted `EXECUTE`.
2. With `SQL SECURITY INVOKER`, the account holds necessary `SELECT`/`UPDATE` privileges.
3. Revoking `UPDATE` causes the privilege test to fail as expected.
4. Runtime account lacks `CREATE`, `ALTER`, or `DROP` if not needed.
5. With `DEFINER`, callers cannot access tables outside the routine's scope using the definer's privileges.
6. After a restore or staging deploy, definer and grants remain valid.

Verify:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.%';
SHOW CREATE PROCEDURE warehouse_demo.reserve_inventory\G
```

Never grant `GRANT ALL ON *.*` to a test account merely to make tests pass. Test under least privilege; otherwise tests will miss permission failures until production deployment.

## 14. Required Test Suite

| Category | Test Case | Expected Result |
|---|---|---|
| Success | Existing SKU, positive quantity, sufficient stock | OUT returns new stock; table updates only after commit |
| Validation | Quantity equal to 0 or negative | SQLSTATE `45000`, code `30001` |
| Validation | SKU is NULL or 0 | SQLSTATE `45000`, code `30002` |
| Not Found | SKU missing from table | SQLSTATE `45000`, code `30002` |
| Business | Stock lower than requested quantity | SQLSTATE `45000`, code `30003`; stock unchanged |
| Rollback | Caller rolls back after procedure succeeds | Stock reverts to initial value |
| Atomicity | Subsequent order step fails | Both order and inventory roll back |
| Concurrency | Two transactions reserve more than available stock | Only valid requests succeed; stock stays non-negative |
| Lock | Another transaction holds row lock too long | Timeout classified and transaction rolled back |
| Deadlock | Two transactions lock multiple rows in opposite orders | One transaction chosen as victim; bounded full-transaction retry |
| Permission | Caller lacks `EXECUTE` or table privileges | Rejected per configured SQL SECURITY mode |
| Compatibility | Caller uses production JDBC driver | OUT parameters and SQLState/vendor code parsed accurately |

Run tests against the target MySQL version, InnoDB, and real schema migrations. H2 or mocks are fine for outer unit logic, yet they cannot prove `SIGNAL`, row locks, MySQL diagnostics, or stored procedure semantics.

## 15. Diagnosing Test Failures

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Procedure fails to create | Wrong declaration order, handler syntax, or client delimiter | Read DDL error; ensure `DECLARE` precedes executable statements |
| Caller gets generic error instead of original error | Handler raises a new `SIGNAL` overwriting initial condition | Use `RESIGNAL` to preserve original SQLSTATE/vendor code |
| SKU exists yet reports NOT FOUND | Schema/parameter mapping mismatch or query uses wrong condition | Inspect key types, active schema, and fixture data |
| Two requests oversell stock | Missing transaction or locking read releases lock before commit | Check autocommit, separate connections, and `FOR UPDATE` |
| Order rolled back yet inventory still decreased | Procedure committed internally or used a different connection | Return transaction ownership to caller on the same connection |
| Privilege test passes as DBA but fails at runtime | Test account holds broader privileges than the application | Run with the runtime account and inspect `SHOW GRANTS` |
| JDBC fails to read OUT parameter | Wrong register index/order, JDBC type, or extra result sets | Check signature and `CallableStatement`; remove debug SELECTs |
| Error audit vanishes after rollback | Audit log written inside the rolled-back transaction | Move logging outside the transaction or use a separate audit design |
| Retries create duplicate reservations | Retries lack an idempotency key or unverified commit outcome | Use a unique request ID and query state before re-running |

During investigations, capture `SHOW CREATE PROCEDURE`, SQLSTATE, vendor error code, transaction isolation, autocommit state, grants, and logs from both connections in concurrency tests. Do not capture only message text, as it is insufficient to reproduce root causes.

## 16. Routine Deployment Workflow

A stored procedure is a database API, so it must pass through the same migration pipeline as schema changes:

1. Review signature, input validation, outputs, and error code contract.
2. Review transaction ownership and every `COMMIT`/`ROLLBACK` path.
3. Review SQL SECURITY, definer, grants, and any dynamic SQL.
4. Create the routine via versioned migrations; never manually patch production and forget to commit to the repository.
5. Run tests on real MySQL covering success, errors, rollback, privileges, and concurrency.
6. Deploy backward-compatible routine updates before deploying new callers when compatibility is required.
7. Monitor SQLSTATE/vendor error rates and execution latency post-deploy.
8. Drop old procedures only after confirming zero remaining callers.

Note: replacing a routine via `DROP PROCEDURE` followed by `CREATE PROCEDURE` creates a brief window where callers cannot invoke the procedure, and DDL triggers implicit commits. Pick deployment strategies, windows, and rollout order suited to your migration tooling and MySQL service compatibility.

## 17. End-to-End Practice Scenario

A checkout service needs to create an order and reserve stock. Requirements: two requests must never collectively reserve more than available stock, business errors must return stable codes, and all changes must roll back if inserting order items fails.

**Step 1 — Prepare schema.** Create `inventory` with a primary key on `sku_id`, InnoDB, and a non-negative constraint. Load a SKU with 12 units.

**Step 2 — Create procedure.** Define `reserve_inventory` with two inputs, one output, `SIGNAL` for three business errors, and a `NOT FOUND` handler; let other SQL exceptions propagate to the caller.

**Step 3 — Define transaction boundary.** The service starts a transaction, inserts a pending order, calls the procedure on the same connection, inserts order items, and commits. If any step fails, the service rolls back the entire transaction.

**Step 4 — Test contract.** Call the procedure over JDBC; verify success returns the OUT parameter, and invalid quantity, missing SKU, and insufficient stock yield exact SQLState and vendor codes.

**Step 5 — Test rollback.** Deliberately fail the order-item write after reserving; verify neither the order nor inventory changes after rollback.

**Step 6 — Test concurrency.** Use two connections to reserve 7 units each from a SKU with 10 units. Only one transaction commits; the other receives insufficient stock; final stock equals 3.

**Step 7 — Test privileges.** Run with a runtime account granted only `EXECUTE`, `SELECT`, and `UPDATE`; verify no DDL or global privileges are required.

**Step 8 — Deploy and observe.** Add the procedure migration to the pipeline and monitor error rates by code, deadlocks, lock waits, latency, and retry counts.

## 18. Pre-Production Checklist

- [ ] Signature, parameter types, nullability, and outputs are documented.
- [ ] Business errors have stable SQLSTATE and `MYSQL_ERRNO` codes.
- [ ] `SIGNAL` is used for expected errors; `RESIGNAL` preserves unexpected SQL errors when needed.
- [ ] `NOT FOUND`, `SQLWARNING`, and `SQLEXCEPTION` are handled with proper semantics.
- [ ] Handlers never swallow errors or return false success results.
- [ ] Transaction ownership is explicit; the procedure never commits caller transactions outside contract.
- [ ] Locking reads run inside transactions with proper lock retention scope.
- [ ] Rollback is tested across the full business workflow.
- [ ] Concurrency tests use independent connections and transactions.
- [ ] Deadlocks and lock timeouts are classified; bounded full-transaction retries are configured.
- [ ] Runtime account follows least privilege; SQL SECURITY and definer are reviewed.
- [ ] Dynamic SQL is avoided or safely allowlists identifiers and binds values.
- [ ] Result sets and OUT parameters emit zero out-of-contract debug output.
- [ ] JDBC tests assert SQLState/vendor codes rather than relying on full message strings.
- [ ] Migrations are versioned with safe rollout ordering and caller compatibility.
- [ ] Auditing/logging has clear transaction boundaries and never leaks sensitive data.

Reliable stored procedures must be designed like contractual APIs: explicit parameters, stable outputs, classifiable errors, single transaction ownership, and least-privilege execution. Combining `SIGNAL`, `RESIGNAL`, diagnostics, locking reads, and testing against real MySQL ensures applications handle both business errors and concurrency hazards cleanly without leaving partial data behind.
