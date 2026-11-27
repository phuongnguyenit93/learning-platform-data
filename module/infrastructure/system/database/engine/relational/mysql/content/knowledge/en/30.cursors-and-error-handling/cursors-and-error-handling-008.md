# GET DIAGNOSTICS for Reading Error Information or Row Counts

GET DIAGNOSTICS is an SQL statement used to read information from MySQL's diagnostics area after a statement runs. It lets a stored program find out how many conditions the previous statement generated, how many rows it affected, or retrieve the specific SQLSTATE, error code, and error message.

In stored procedures, GET DIAGNOSTICS is commonly used to capture the affected row count after INSERT/UPDATE/DELETE and to analyze errors inside handlers. When a handler is triggered by an error, GET STACKED DIAGNOSTICS reads the condition that caused the handler to run, even if statements inside the handler have produced new diagnostics.

In the **DATABASE_MYSQL** module, cursors and error handling support multi-step server-side data flows. GET DIAGNOSTICS adds visibility into outcomes and failure causes so a procedure can log, return appropriate details, or re-raise the original error to the application.

## 1. What Is the Diagnostics Area?

After MySQL executes a statement, the server stores diagnostic information in the diagnostics area. This area has two main parts:

- **Statement information area:** general information about the statement, including the condition count and affected row count.
- **Condition information area:** details for each condition raised, such as SQLSTATE, MySQL error number, message, and related object metadata.

A condition can be an error, warning, or note. A statement may generate zero conditions, one condition, or multiple conditions.

Example:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

After the UPDATE, the statement information area indicates how many conditions were recorded and how many rows were affected. If the UPDATE produces no warnings or errors, NUMBER is typically 0; ROW_COUNT reflects the number of rows affected by the statement under MySQL semantics.

GET DIAGNOSTICS only reads diagnostic information. It does not replace handlers and does not catch errors itself. To handle an error so a procedure can continue or exit cleanly, declare a `DECLARE ... HANDLER`.

## 2. GET DIAGNOSTICS Syntax

The syntax has two main forms:

```sql
GET [CURRENT | STACKED] DIAGNOSTICS
    statement_information_item [, statement_information_item] ...;

GET [CURRENT | STACKED] DIAGNOSTICS
    CONDITION condition_number
    condition_information_item [, condition_information_item] ...;
```

You can read either statement information or condition information in a single call. Do not mix both item groups in the same GET DIAGNOSTICS statement.

If CURRENT or STACKED is omitted, MySQL defaults to CURRENT.

### 2.1. CURRENT

CURRENT refers to the current diagnostics area. Use it after a regular statement to retrieve the affected row count or conditions just generated.

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = 9002;

GET CURRENT DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

CURRENT is appropriate when you are not inside a handler or when reading diagnostics of the current statement in the execution flow.

### 2.2. STACKED

STACKED is the saved diagnostics area preserved when a handler is activated. It holds the condition that triggered the handler.

Inside a handler, use GET STACKED DIAGNOSTICS to read the original error before executing other statements such as INSERT into a log, SET variables, or calling helper routines.

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_message = MESSAGE_TEXT;
    RESIGNAL;
END;
```

STACKED is valid only within an active handler. Calling GET STACKED DIAGNOSTICS outside a handler raises an error because no valid stacked diagnostics area exists.

### 2.3. Difference Between CURRENT and STACKED

| Context | Should Read | Reason |
|---|---|---|
| Immediately after normal UPDATE/INSERT/DELETE | CURRENT | Reads diagnostics of the statement just executed |
| Inside a handler, needing the error that triggered the handler | STACKED | Preserves the original condition details |
| Inside a handler, needing conditions from a new statement inside the handler | CURRENT | Reads the handler's current diagnostics |
| Outside a handler trying to read STACKED | Invalid | No active stacked area exists |

A handler may execute multiple statements. Those statements can alter the current diagnostics area. Therefore, capture original error details from STACKED right at the start of the handler.

## 3. Reading Statement Information: NUMBER and ROW_COUNT

The statement information area has two key items.

| Item | Meaning |
|---|---|
| NUMBER | Number of conditions recorded in the statement's diagnostics area |
| ROW_COUNT | Number of rows affected according to the preceding statement |

Both can be read in a single statement:

```sql
UPDATE orders
SET status = 'PAID'
WHERE tenant_id = 42
  AND status = 'PENDING';

GET DIAGNOSTICS
    @number_of_conditions = NUMBER,
    @rows_affected = ROW_COUNT;

SELECT
    @number_of_conditions AS condition_count,
    @rows_affected AS rows_affected;
```

NUMBER is not the row count. ROW_COUNT is not the condition count. Do not swap these two items.

### 3.1. NUMBER

NUMBER indicates how many conditions are in the diagnostics area. For example, an `INSERT IGNORE` statement can produce warnings when some rows are skipped or values are adjusted.

```sql
INSERT IGNORE INTO users (user_id, email)
VALUES
    (101, 'a@example.com'),
    (101, 'duplicate@example.com');

GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

Specific values depend on data, constraints, and server warnings. If NUMBER equals 0, no conditions were recorded for that statement. If greater than 0, each condition can be read using the CONDITION clause.

### 3.2. ROW_COUNT

ROW_COUNT is useful immediately after a DML statement:

```sql
DELETE FROM sessions
WHERE expires_at < CURRENT_TIMESTAMP;

GET DIAGNOSTICS @deleted_rows = ROW_COUNT;
```

Read ROW_COUNT immediately after the statement you want to measure. Running another SQL statement before reading diagnostics can cause the values to reflect the new statement instead of the one you intended to check.

ROW_COUNT is not a general counter for all rows a SELECT might return. For normal SELECT queries, row count has specific semantics and is generally not used as the result row count. If you need to count matching rows, use `COUNT(*)` or process the result set/cursor as intended.

### 3.3. UPDATE Finding No Rows vs. UPDATE Not Changing Values

Example:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 999999;

GET DIAGNOSTICS @rows = ROW_COUNT;
```

If no matching `order_id` exists, ROW_COUNT equals 0. However, when UPDATE finds a row but assigns the exact same current value, the reported row count depends on affected-rows semantics and the client's `CLIENT_FOUND_ROWS` flag. Thus, do not always interpret `ROW_COUNT = 0` as "no row matched WHERE" if the application enables matched-rows reporting.

If business logic needs to distinguish "does not exist" from "exists but unchanged," perform an additional query or check with appropriate transactions/locking rather than relying solely on ROW_COUNT.

### 3.4. INSERT ... ON DUPLICATE KEY UPDATE

With `INSERT ... ON DUPLICATE KEY UPDATE`, the affected-row count can represent an insert, an update, or no change. Under standard MySQL semantics, each row counts as 1 when inserted, 2 when updated, and 0 when updated with unchanged values; the `CLIENT_FOUND_ROWS` flag can change the unchanged case.

```sql
INSERT INTO account_balance (account_id, balance)
VALUES (42, 1000)
ON DUPLICATE KEY UPDATE
    balance = VALUES(balance);

GET DIAGNOSTICS @affected_rows = ROW_COUNT;
```

Do not use a single number to infer exact business branches if the statement processes multiple rows or client flags influence affected rows. If you need to know whether each row was inserted or updated, design clearer API/logic.

## 4. Reading Condition Information

Condition information describes a specific condition in the diagnostics area.

Commonly used items:

| Item | Meaning |
|---|---|
| RETURNED_SQLSTATE | 5-character SQLSTATE |
| MYSQL_ERRNO | MySQL-specific error code |
| MESSAGE_TEXT | Error or warning message |
| CLASS_ORIGIN | Origin of the SQLSTATE class |
| SUBCLASS_ORIGIN | Origin of the SQLSTATE subclass |
| CONSTRAINT_SCHEMA | Schema of the related constraint |
| CONSTRAINT_NAME | Name of the related constraint |
| TABLE_NAME | Related table name if any |
| COLUMN_NAME | Related column name if any |
| CURSOR_NAME | Related cursor name if any |

Some items may be NULL or empty if the condition is not tied to a specific table, column, or constraint.

Example reading the first condition:

```sql
GET DIAGNOSTICS CONDITION 1
    @state = RETURNED_SQLSTATE,
    @errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT
    @state AS sqlstate_code,
    @errno AS mysql_error_number,
    @message AS diagnostic_message;
```

You can also read constraint metadata:

```sql
GET DIAGNOSTICS CONDITION 1
    @state = RETURNED_SQLSTATE,
    @constraint_schema = CONSTRAINT_SCHEMA,
    @constraint_name = CONSTRAINT_NAME,
    @table_name = TABLE_NAME,
    @column_name = COLUMN_NAME;
```

Do not assume every error includes constraint, table, and column names. Handle NULL values in code or when logging.

### 4.1. SQLSTATE and MYSQL_ERRNO Are Different

SQLSTATE is a standardized 5-character state code, for example:

- 23000: integrity constraint violation.
- 02000: no data.
- 01000: warning.
- 45000: application-raised state via SIGNAL.

MYSQL_ERRNO is a specific error number defined by MySQL. It is useful for distinguishing specific server errors, though generally less portable than SQLSTATE.

MESSAGE_TEXT is a message meant for diagnostics. Do not use message strings as primary logic keys because text can vary by version, locale, or context. To branch by error type, prefer SQLSTATE or MYSQL_ERRNO.

### 4.2. CONDITION 1 Is Not Always Enough

A statement can generate multiple conditions, such as a statement producing multiple warnings. Read NUMBER first to learn how many conditions exist.

```sql
GET DIAGNOSTICS @condition_count = NUMBER;
```

Then read the conditions you need to inspect:

```sql
GET DIAGNOSTICS CONDITION 1
    @state_1 = RETURNED_SQLSTATE,
    @errno_1 = MYSQL_ERRNO,
    @message_1 = MESSAGE_TEXT;
```

CONDITION 1 is the first condition by index in the diagnostics area. When multiple conditions exist, do not read only one condition and conclude you understand the whole statement. You can read CONDITION 2, CONDITION 3, etc., according to the actual count.

Distinguish the first condition from the business cause the application cares about. A statement can produce extra warnings alongside the primary error or warning. Check all relevant conditions rather than relying only on the first message.

## 5. Reading Affected Row Counts in Stored Procedures

GET DIAGNOSTICS is commonly used to return the updated row count to the application or decide the next processing branch.

Example:

```sql
DELIMITER //

CREATE PROCEDURE mark_order_paid(
    IN p_order_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_rows BIGINT DEFAULT 0;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id
      AND status = 'PENDING';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    SELECT v_rows AS affected_rows;
END//

DELIMITER ;
```

The procedure only updates orders that are PENDING. `v_rows` is captured immediately after UPDATE so it is unaffected by the trailing SELECT returning the result.

If `v_rows = 1`, the statement affected one row under affected-row semantics. If 0, no rows were counted as changed; this may be because the order does not exist, its status is no longer PENDING, or the row already had another status. If you need to distinguish these cases, add explicit checking logic.

### 5.1. Do Not Place Other Statements Between DML and GET DIAGNOSTICS

Avoid:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

SELECT CURRENT_TIMESTAMP;

GET DIAGNOSTICS v_rows = ROW_COUNT;
```

Here the diagnostics to be read must be fetched right after UPDATE. The intervening SELECT can overwrite the current diagnostics area. Clear pattern:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

GET DIAGNOSTICS v_rows = ROW_COUNT;

SELECT CURRENT_TIMESTAMP;
```

Capture the needed values into local variables before executing any other statement.

## 6. GET DIAGNOSTICS Inside an SQLWARNING Handler

You can use a handler to catch warnings and read the condition that activated the handler.

```sql
DELIMITER //

CREATE PROCEDURE inspect_warning()
BEGIN
    DECLARE v_state CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE CONTINUE HANDLER FOR SQLWARNING
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_state = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        SELECT
            v_state AS warning_sqlstate,
            v_errno AS warning_errno,
            v_message AS warning_message;
    END;

    INSERT IGNORE INTO users (user_id, email)
    VALUES (101, 'duplicate@example.com');
END//

DELIMITER ;
```

A CONTINUE handler handles the warning and then continues after the statement that caused the warning. An EXIT handler leaves the current compound statement once the handler finishes.

In real applications, do not assume an `INSERT IGNORE` only produces one warning. Multiple conditions can occur. If full details are needed, read NUMBER and inspect each condition accordingly.

## 7. GET STACKED DIAGNOSTICS Inside a SQLEXCEPTION Handler

When an error occurs, a handler can read SQLSTATE, error code, and message, and then re-raise the original error using RESIGNAL.

Example:

```sql
DELIMITER //

CREATE PROCEDURE create_order(
    IN p_order_id BIGINT UNSIGNED,
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        -- Diagnostic variables can be recorded here per logging policy.
        RESIGNAL;
    END;

    INSERT INTO orders (
        order_id,
        customer_id,
        status
    )
    VALUES (
        p_order_id,
        p_customer_id,
        'PENDING'
    );
END//

DELIMITER ;
```

The order is important:

1. The handler is triggered by SQLEXCEPTION.
2. GET STACKED DIAGNOSTICS reads the condition that triggered the handler.
3. Values are captured into local variables.
4. Optional additional processing can run.
5. RESIGNAL re-raises the original error to the caller.

If you use GET CURRENT DIAGNOSTICS after running another statement inside the handler, it may read diagnostics from that statement inside the handler instead of the initial error. STACKED is designed specifically for this scenario.

### 7.1. RESIGNAL and SIGNAL

- RESIGNAL re-raises the condition that activated the handler, either preserving the original error or modifying selected attributes per syntax.
- SIGNAL creates a new condition, typically using an application SQLSTATE such as 45000.
- GET DIAGNOSTICS only reads information; it does not raise errors and does not replace RESIGNAL/SIGNAL.

Example raising a business error:

```sql
IF p_amount <= 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Amount must be greater than zero';
END IF;
```

If a handler catches this condition, GET STACKED DIAGNOSTICS can read SQLSTATE 45000 and the specified message.

## 8. Logging Errors Without Losing the Original Error

A stored procedure can write error information into a log table. However, you must understand transaction boundaries before designing it.

Example log table:

```sql
CREATE TABLE database_error_log (
    log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    routine_name VARCHAR(128) NOT NULL,
    sqlstate_code CHAR(5),
    mysql_errno INT,
    message_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id)
) ENGINE = InnoDB;
```

Inside a handler, you can capture diagnostics and then log:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    INSERT INTO database_error_log (
        routine_name,
        sqlstate_code,
        mysql_errno,
        message_text
    )
    VALUES (
        'create_order',
        v_sqlstate,
        v_errno,
        v_message
    );

    RESIGNAL;
END;
```

This is an illustrative pattern that must be adapted to the application's transaction policy. If the log table uses InnoDB and the log INSERT runs inside the same transaction as business logic, the log can be rolled back along with the transaction. Certain errors like deadlocks can force the entire current transaction to roll back. Therefore, never assume logging inside a handler always produces a durable record.

If error logs must survive rollback, consider logging at the application layer after receiving the error/rollback, using an external logging system, or designing a log channel with a separate transaction boundary. MySQL stored programs lack general autonomous transactions to commit independently on the same connection.

### 8.1. Protecting the Original Error When Logging Fails

If the log INSERT inside a handler also fails, the new error can mask the initial error or alter control flow. Options:

- Catch logging errors separately using a nested handler.
- Do not let logging corrupt the business transaction.
- Save the original SQLSTATE/errno/message values in local variables before logging.
- Call RESIGNAL after handling logging according to defined policy.
- For durable auditing requirements, consider recording in the application or an independent logging system.

Do not treat MESSAGE_TEXT as trusted input to concatenate into dynamic SQL. Messages can contain content derived from data or environment; treat them as log data and restrict access privileges.

## 9. Reading Multiple Conditions

A statement can generate multiple warnings. GET DIAGNOSTICS can read each condition by index.

Illustrative example reading the first two conditions:

```sql
GET DIAGNOSTICS @condition_count = NUMBER;

GET DIAGNOSTICS CONDITION 1
    @state_1 = RETURNED_SQLSTATE,
    @errno_1 = MYSQL_ERRNO,
    @message_1 = MESSAGE_TEXT;

GET DIAGNOSTICS CONDITION 2
    @state_2 = RETURNED_SQLSTATE,
    @errno_2 = MYSQL_ERRNO,
    @message_2 = MESSAGE_TEXT;
```

Only run the CONDITION 2 read if NUMBER is at least 2. If reading multiple conditions, check the count first to avoid accessing a nonexistent condition.

In MySQL syntax, `condition_number` is written in the GET DIAGNOSTICS statement. Examples use literal indices to clearly show which condition is being read. Do not assume it can be replaced with a local variable in every version/syntax form.

Not every application needs to read every warning. Select operationally valuable details such as SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT; only read constraint metadata when the error involves a constraint.

## 10. Distinguishing NOT FOUND from SQL Errors

In stored programs, NOT FOUND is normally used for SQLSTATE class 02, such as `SELECT ... INTO` finding no rows or cursor FETCH reaching end of data.

Cursor example:

```sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_order_id BIGINT UNSIGNED;

DECLARE order_cursor CURSOR FOR
    SELECT order_id
    FROM orders
    ORDER BY order_id;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

NOT FOUND is not synonymous with SQLEXCEPTION. When a cursor runs out of data, the NOT FOUND handler typically sets a loop termination flag. If you want to capture the SQLSTATE or message of a NOT FOUND condition, you can use GET STACKED DIAGNOSTICS inside the corresponding handler.

A procedure can have multiple handlers for different classes. Choose handlers matching the objective:

| Condition | Common Handling |
|---|---|
| NOT FOUND | Set cursor termination flag or handle missing row |
| SQLWARNING | Record/warn and continue if appropriate |
| SQLEXCEPTION | Exit, roll back per transaction contract, or RESIGNAL |
| Specific SQLSTATE | Handle a particular business condition or special error |

Handler precedence and block scope affect which handler is chosen. Place handlers in the right compound block and prevent a NOT FOUND handler from accidentally catching unrelated `SELECT ... INTO` results.

## 11. Combining GET DIAGNOSTICS with Cursors

GET DIAGNOSTICS does not replace cursors. Cursors traverse rows in a result set one by one; diagnostics read statement status and conditions.

Example where after FETCH, a NOT FOUND handler determines the cursor has ended:

```sql
DELIMITER //

CREATE PROCEDURE list_order_ids()
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE order_cursor CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN order_cursor;

    read_loop: LOOP
        FETCH order_cursor INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SELECT v_order_id AS order_id;
    END LOOP;

    CLOSE order_cursor;
END//

DELIMITER ;
```

If you want to inspect the condition that triggered NOT FOUND, replace the single-statement handler with a block handler:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_message = MESSAGE_TEXT;
    SET v_done = TRUE;
END;
```

Note that handlers are declared after variables, conditions, and cursors in the same block. Do not place DECLARE HANDLER after executable statements in a block.

## 12. Comparing GET DIAGNOSTICS with ROW_COUNT(), SHOW WARNINGS, and SIGNAL

| Tool | Purpose |
|---|---|
| GET DIAGNOSTICS | Reads statement/condition information from the diagnostics area |
| ROW_COUNT() | Function returning affected-row count of the preceding statement |
| SHOW WARNINGS | Displays warnings/notes/errors from a statement in the client |
| DECLARE ... HANDLER | Defines behavior when a condition occurs |
| SIGNAL | Raises a new condition |
| RESIGNAL | Re-raises a condition from within a handler |

`ROW_COUNT()` example:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

SELECT ROW_COUNT();
```

`GET DIAGNOSTICS` example:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

GET DIAGNOSTICS @changed = ROW_COUNT;
```

Both can read affected-row counts. GET DIAGNOSTICS is useful when you also need NUMBER or condition metadata through the same diagnostics mechanism.

SHOW WARNINGS is suited for client-side inspection after a statement. Inside stored programs, GET DIAGNOSTICS places values into local variables for further processing.

## 13. Procedure for Diagnosing Errors in Stored Procedures

When an SQL statement in a procedure fails:

1. Identify the statement causing the error.
2. Check whether any handler in the block catches that condition.
3. Inside the handler, use GET STACKED DIAGNOSTICS before secondary statements.
4. Read RETURNED_SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT.
5. If needed, also read CONSTRAINT_NAME, TABLE_NAME, or COLUMN_NAME.
6. Decide whether the error can be recovered or requires EXIT.
7. If the caller should receive the original error, call RESIGNAL.
8. If translating to a business error, use SIGNAL with a clear SQLSTATE and message.
9. Determine whether the transaction was rolled back partially or completely.
10. Verify whether the logging destination survives rollback.

Minimal handler template:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_state = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    RESIGNAL;
END;
```

This template preserves the original error and lets MySQL return it to the caller. When adding logging or error translation, add controlled logic while always capturing diagnostics first.

## 14. Common Mistakes and Misconceptions

| Mistake | Consequence | How to Fix |
|---|---|---|
| Using GET DIAGNOSTICS to replace a handler | Errors still fail the statement/procedure | Combine with DECLARE HANDLER when handling errors |
| Using CURRENT inside a handler to read the original error after running other statements | Reads conditions from statements inside the handler | Use STACKED right at the start of the handler |
| Using STACKED outside a handler | Raises an error because no stacked area exists | Use STACKED only while a handler is active |
| Confusing NUMBER with ROW_COUNT | Misreads condition count vs. row count | NUMBER counts conditions; ROW_COUNT measures affected rows |
| Running SELECT before reading ROW_COUNT | Diagnostics may no longer belong to the measured DML | Capture ROW_COUNT immediately after DML |
| Assuming `ROW_COUNT = 0` always means no rows matched WHERE | Unchanged-value UPDATE and `CLIENT_FOUND_ROWS` behave differently | Understand affected-row semantics and perform extra checks |
| Reading only CONDITION 1 when multiple warnings exist | Misses other conditions | Read NUMBER and inspect needed conditions |
| Assuming every condition has TABLE_NAME/CONSTRAINT_NAME | Values may be NULL or empty | Handle missing metadata safely |
| Using MESSAGE_TEXT as an error code | Logic depends on mutable message text | Use SQLSTATE or MYSQL_ERRNO |
| Logging inside a transaction and assuming durability | Log can roll back with business changes | Place logging at an appropriate transaction boundary |
| Handler log error masking the original error | Caller receives the wrong root cause | Capture STACKED first, guard logging, and RESIGNAL |
| Confusing NOT FOUND with SQLEXCEPTION | Cursor end treated as a general error | Declare handlers for the proper condition classes |

## 15. Production Checklist for Using GET DIAGNOSTICS

**After DML:**

- Place GET DIAGNOSTICS immediately after INSERT/UPDATE/DELETE.
- Save ROW_COUNT to a local variable before running another statement.
- Understand the difference between matched rows and changed rows.
- Never use ROW_COUNT in place of `COUNT(*)` for SELECT result sets.
- If detecting warnings is required, read NUMBER.

**Inside Handlers:**

- Use GET STACKED DIAGNOSTICS to read the condition that triggered the handler.
- Capture SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT before secondary statements.
- Read CONDITION 1 and additional conditions if NUMBER indicates more exist.
- Distinguish NOT FOUND, SQLWARNING, and SQLEXCEPTION.
- Use RESIGNAL when the original error must be preserved.
- Use SIGNAL when raising a new business error.

**Logging and Transactions:**

- Decide whether logging shares the transaction or is independent.
- Never assume an InnoDB log INSERT survives rollback.
- Guard the handler against secondary errors during logging.
- Never interpolate error messages into dynamic SQL.
- Restrict read permissions on log tables containing sensitive details.
- Test deadlocks, constraint violations, warnings, and no-data paths.

## 16. Key Takeaways

- The diagnostics area stores statement and condition information generated by MySQL.
- GET DIAGNOSTICS reads statement information or condition information.
- NUMBER is the condition count; ROW_COUNT is the statement's affected row count.
- CONDITION n reads SQLSTATE, MYSQL_ERRNO, MESSAGE_TEXT, and related metadata.
- CURRENT reads the current diagnostics area; STACKED reads the snapshot of the condition that activated the handler.
- STACKED is valid only inside handlers; use it early to preserve the original error.
- SQLSTATE is a 5-character code; MYSQL_ERRNO is MySQL-specific; MESSAGE_TEXT is for diagnostics.
- Read ROW_COUNT immediately after DML and understand affected-row semantics.
- A statement can generate multiple conditions; read NUMBER before inspecting subsequent conditions.
- GET DIAGNOSTICS does not catch errors by itself; combine it with DECLARE HANDLER.
- RESIGNAL keeps and re-raises the original condition; SIGNAL creates a new condition.
- InnoDB logs inside the same transaction can be rolled back with the business operations.
- NOT FOUND typically serves cursor exhaustion or no-data paths; do not equate it with SQLEXCEPTION.

GET DIAGNOSTICS lets stored programs know what just happened and why an SQL statement failed. Read ROW_COUNT immediately after DML, use STACKED inside handlers, retain SQLSTATE and error codes for diagnostics, and choose clearly between continuing, raising a business error, or RESIGNALing the original error.

## References

- MySQL 8.0 Reference Manual — GET DIAGNOSTICS Statement: https://dev.mysql.com/doc/refman/8.0/en/get-diagnostics.html
- MySQL 8.0 Reference Manual — The Diagnostics Area: https://dev.mysql.com/doc/refman/8.0/en/diagnostics-area.html
- MySQL 8.0 Reference Manual — Condition Handling: https://dev.mysql.com/doc/refman/8.0/en/condition-handling.html
- MySQL 8.0 Reference Manual — DECLARE ... HANDLER Statement: https://dev.mysql.com/doc/refman/8.0/en/declare-handler.html
- MySQL 8.0 Reference Manual — RESIGNAL Statement: https://dev.mysql.com/doc/refman/8.0/en/resignal.html
- MySQL 8.0 Reference Manual — SIGNAL Statement: https://dev.mysql.com/doc/refman/8.0/en/signal.html
- MySQL 8.0 Reference Manual — ROW_COUNT() Function: https://dev.mysql.com/doc/refman/8.0/en/information-functions.html#function_row-count
