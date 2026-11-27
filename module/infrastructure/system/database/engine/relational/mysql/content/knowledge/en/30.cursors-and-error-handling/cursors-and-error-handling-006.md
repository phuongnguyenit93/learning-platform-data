# SQLSTATE, MySQL Error Codes, and Named Conditions

When an SQL statement fails, MySQL provides several pieces of information to identify the cause: SQLSTATE, the numeric MySQL error code, and a descriptive message. These three pieces of information are related, yet none replaces the others. SQLSTATE describes the error category per the SQL standard; the numeric error code identifies the specific MySQL error; and the message explains the situation in more human-readable text.

Inside stored programs, you can use those values directly in handlers or declare named conditions to make source code easier to understand. Named conditions replace hard-to-remember numbers or repeated SQLSTATE strings with clear business names. When you need to raise a business-defined error, use SIGNAL with an appropriate SQLSTATE; when you need to read the error that just occurred, use GET DIAGNOSTICS.

This lesson focuses on SQLSTATE structure, distinguishing SQLSTATE from MySQL error codes, common codes, declaring and scoping named conditions, combining conditions with handlers, SIGNAL/RESIGNAL, and reading error information from the diagnostics area.

## 1. Three Error Identification Elements

When MySQL raises a condition, the key details include:

| Element | Meaning | Example |
|---|---|---|
| SQLSTATE | 5-character status code representing the SQL category/state | 23000, 42000, 45000 |
| MySQL error code | MySQL-specific integer identifying a particular error | 1062, 1064, 1213 |
| MESSAGE_TEXT | Error description message | Duplicate entry, syntax error |

For example, when inserting a duplicate unique key value, MySQL typically returns:

- SQLSTATE: 23000
- MySQL error code: 1062
- Message: Duplicate entry ...

SQLSTATE 23000 indicates an integrity constraint violation. Code 1062 is more specific: duplicate key. Therefore, an application can handle by SQLSTATE when it only needs to know this is an integrity constraint error, or by code 1062 when it needs to distinguish a duplicate key from other integrity errors.

Do not parse `MESSAGE_TEXT` strings to drive business logic. Message text can change across versions, locales, table/column names, and input data. Use SQLSTATE or MySQL error codes for routing handling logic; use `MESSAGE_TEXT` primarily for logging and diagnostics.

## 2. How Is SQLSTATE Structured?

SQLSTATE is a string of exactly 5 characters. The first two characters identify the class, and the last three characters identify the subclass within that class.

```text
SQLSTATE = CC SSS
            |  |
            |  +-- Subclass: detailed state within the class
            +----- Class: state category
```

Examples:

- 23000: class 23, integrity constraint violation.
- 42000: class 42, syntax error or access rule violation.
- 40001: class 40, transaction rollback.
- 02000: class 02, no data.
- 45000: class 45, user-defined exception in MySQL.

SQLSTATE is a character code, not an integer. When comparing or declaring, wrap it in single quotes:

```sql
DECLARE duplicate_state CONDITION
    FOR SQLSTATE '23000';
```

Do not drop leading zeros. For example, `02000` must remain all 5 characters.

### 2.1. Common Classes

| Class | Category Name | Typical Situations |
|---|---|---|
| 00 | Successful completion | Statement completed successfully |
| 01 | Warning | Statement completed with a warning |
| 02 | No data | No rows or data not found; commonly seen when cursor FETCH runs out of rows |
| 08 | Connection exception | Connection error |
| 21 | Cardinality violation | Row/value count violation for the context |
| 22 | Data exception | Data error or data conversion error |
| 23 | Integrity constraint violation | Primary key, unique key, foreign key, or check constraint violation |
| 24 | Invalid cursor state | Invalid cursor state |
| 25 | Invalid transaction state | Invalid transaction state |
| 28 | Invalid authorization specification | Invalid credentials or privileges |
| 40 | Transaction rollback | Transaction rolled back, e.g., deadlock |
| 42 | Syntax error or access rule violation | Syntax error or access rule violation |
| HY | General error | Implementation-defined general error class |

These are representative classes to guide diagnostics, not an exhaustive list of all SQLSTATE values. When you need the exact state of a specific error, read the actual value from the diagnostics area or MySQL documentation.

### 2.2. Three Special Classes in Handler Declarations

MySQL provides three shorthand condition classes commonly used in DECLARE HANDLER:

| Shorthand | Scope |
|---|---|
| SQLWARNING | Conditions in class 01 |
| NOT FOUND | Conditions in class 02 |
| SQLEXCEPTION | Classes other than 00, 01, and 02 |

Example:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

In cursor processing, NOT FOUND is commonly used to detect when FETCH has no more rows. This handler is shorthand for class 02 conditions; it does not mean every empty result in every SELECT statement produces the same behavior.

### 2.3. SQLSTATE 00000 and SQLSTATE 45000

`00000` indicates successful completion, not an error. Do not use SQLSTATE class 00 to raise errors with SIGNAL.

`45000` is the general SQLSTATE for user-defined exceptions in MySQL. It is the standard choice when a routine needs to report a business rule violation that does not directly correspond to a specific server error:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Amount must be greater than 0';
```

The application can receive SQLSTATE 45000 and the message supplied by the routine to handle it according to the agreed contract.

## 3. What Is a MySQL Error Code?

A MySQL error code is an integer identifying a specific server-generated error. These codes are published in the Server Error Reference and typically have symbolic names such as `ER_DUP_ENTRY` or `ER_PARSE_ERROR` in MySQL source code/documentation.

Examples of common codes:

| MySQL Error Code | Common Error Name | Typical SQLSTATE | Meaning |
|---:|---|---|---|
| 1062 | ER_DUP_ENTRY | 23000 | Duplicate value in a unique index |
| 1048 | ER_BAD_NULL_ERROR | 23000 | Assigning NULL to a NOT NULL column |
| 1452 | ER_NO_REFERENCED_ROW_2 | 23000 | No matching parent row for a foreign key |
| 1064 | ER_PARSE_ERROR | 42000 | Invalid SQL syntax |
| 1054 | ER_BAD_FIELD_ERROR | 42S22 | Referenced column does not exist |
| 1146 | ER_NO_SUCH_TABLE | 42S02 | Table does not exist |
| 1213 | ER_LOCK_DEADLOCK | 40001 | Transaction chosen as deadlock victim |

The pairs above are typical MySQL examples. When diagnosing an actual error, obtain both SQLSTATE and MYSQL_ERRNO from the running server version rather than inferring solely from message text.

### 3.1. Why Are Both SQLSTATE and Error Codes Needed?

SQLSTATE is general and convenient for handling errors by category. MySQL error codes are more specific but tied to the MySQL implementation.

Examples:

- Catching SQLSTATE 23000 covers many integrity constraint errors.
- Catching error code 1062 targets only duplicate keys.
- Catching SQLSTATE 40001 helps identify transaction rollbacks in the serialization/deadlock category.
- Catching error code 1213 targets MySQL-reported deadlocks.

Choose specificity according to your needs. If logic must react differently to a duplicate key vs. a foreign key violation, use specific error codes or separate specific conditions. If all integrity errors share the same handling, consider an appropriate SQLSTATE.

### 3.2. Do Not Treat SQLSTATE as a MySQL Numeric Code

SQLSTATE and MySQL error codes have different types and value domains:

```sql
-- Declare by SQLSTATE: 5-character string
DECLARE integrity_error CONDITION
    FOR SQLSTATE '23000';

-- Declare by MySQL error code: integer
DECLARE duplicate_key CONDITION
    FOR 1062;
```

Do not write `SQLSTATE 1062`, and do not write `FOR '1062'` to represent a MySQL error code. Use the proper SQLSTATE string form or integer error code.

## 4. What Is a Named Condition?

A named condition is a name declared by the routine author to represent a SQLSTATE or a MySQL error code. Syntax:

```sql
DECLARE condition_name CONDITION
    FOR condition_value;
```

Where `condition_value` takes one of two forms:

```sql
SQLSTATE [VALUE] 'sqlstate_value'
```

or:

```sql
mysql_error_code
```

Example:

```sql
DECLARE no_data CONDITION
    FOR SQLSTATE '02000';

DECLARE duplicate_key CONDITION
    FOR 1062;
```

After declaration, the condition name can be used in handler declarations:

```sql
DECLARE CONTINUE HANDLER FOR no_data
    SET v_done = TRUE;

DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

Named conditions make routines easier to read. Maintainers can immediately understand `duplicate_key` as a duplicate key error without memorizing code 1062 everywhere.

## 5. Declaring Conditions by SQLSTATE

When you want to handle by SQL state group or raise a business error, declare a condition by SQLSTATE:

```sql
DECLARE invalid_amount CONDITION
    FOR SQLSTATE '45000';
```

This condition can be used in a handler:

```sql
DECLARE EXIT HANDLER FOR invalid_amount
BEGIN
    SET p_result = 'INVALID_AMOUNT';
END;
```

It can also be used with SIGNAL to raise the corresponding condition:

```sql
SIGNAL invalid_amount
    SET MESSAGE_TEXT = 'Amount must be greater than zero';
```

For SIGNAL and RESIGNAL, a condition name must be declared and bound to a SQLSTATE. A condition name declared for a MySQL error code is only for matching conditions in handler declarations; do not use it like a SQLSTATE condition to raise errors via SIGNAL.

### 5.1. SQLSTATE VALUE Is Optional

These two forms are equivalent:

```sql
DECLARE invalid_amount CONDITION
    FOR SQLSTATE '45000';

DECLARE invalid_amount CONDITION
    FOR SQLSTATE VALUE '45000';
```

The `VALUE` keyword is optional. Use either the form with `VALUE` or without `VALUE` consistently within the same codebase.

## 6. Declaring Conditions by MySQL Error Code

When you need to handle a specific MySQL error, declare a condition by integer:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
```

Then use the condition name in a handler:

```sql
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

This is equivalent to declaring a handler directly by error code:

```sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate = TRUE;
```

Named conditions clarify intent and avoid repeating magic numbers. Direct numeric usage remains valid, but large routines are usually easier to maintain when conditions are named.

### 6.1. One Error Code Is Not a Whole SQLSTATE Class

For example, 1062 maps to SQLSTATE 23000, but that does not mean SQLSTATE 23000 represents only error 1062. Multiple integrity errors can share the same SQLSTATE class/value per server rules.

If you declare:

```sql
DECLARE integrity_violation CONDITION
    FOR SQLSTATE '23000';
```

the handler for `integrity_violation` handles conditions with SQLSTATE equal to `'23000'`. If you need to handle every state in class 23, MySQL does not allow wildcards like `23xxx` in DECLARE CONDITION; choose specific SQLSTATE values or design handlers according to actual requirements.

## 7. DECLARE Placement and Condition Scope

Conditions are declared in the declaration section of a `BEGIN ... END` compound block. All declarations must precede the block's executable statements.

Declaration order in a block:

1. Local variables and conditions.
2. Cursors.
3. Handlers.

Example:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE no_data CONDITION
        FOR SQLSTATE '02000';
    DECLARE duplicate_key CONDITION
        FOR 1062;

    DECLARE cur_orders CURSOR FOR
        SELECT id FROM orders;

    DECLARE CONTINUE HANDLER FOR no_data
        SET v_done = TRUE;

    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    -- Executable statements start here
END
```

Do not place DECLARE CONDITION after a SET, SELECT, or INSERT statement. Do not place handler declarations before cursor declarations.

### 7.1. Condition Name Scope

A condition is scoped to the block where it is declared and any nested inner blocks. An outer block does not automatically see a name declared solely inside a child block.

Example:

```sql
main: BEGIN
    DECLARE duplicate_key CONDITION FOR 1062;

    BEGIN
        DECLARE CONTINUE HANDLER FOR duplicate_key
            SET v_duplicate = TRUE;

        -- Child block can reference the parent block's condition
    END;
END main
```

A condition declared in a parent block can be referenced inside an in-scope child block. Use distinct condition names across nested blocks so reading and handler behavior remain unambiguous.

## 8. Combining Named Conditions with Handlers

A named condition only identifies a condition. The `DECLARE CONDITION` statement itself does not handle errors. To handle a condition, you must declare a handler.

Example catching a duplicate key:

```sql
DELIMITER //

CREATE PROCEDURE add_customer(
    IN p_email VARCHAR(255),
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_key CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    INSERT INTO customers(email)
    VALUES (p_email);

    IF v_duplicate THEN
        SET p_result = 'DUPLICATE';
    ELSE
        SET p_result = 'CREATED';
    END IF;
END//

DELIMITER ;
```

When INSERT raises error 1062, the CONTINUE handler sets `v_duplicate` to TRUE and resumes after the INSERT statement. The subsequent IF assigns the appropriate result.

Note: a handler for 1062 catches every duplicate-key violation occurring within the handler's scope, not just `email` if the table has multiple unique keys. To restrict scope, place the INSERT inside a child block and declare the handler in that child block. If the routine should return an error instead of translating it into a status, use an EXIT handler or RESIGNAL per your designed contract.

### 8.1. Distinguishing CONTINUE and EXIT

| Handler Type | After the handler runs |
|---|---|
| CONTINUE | Resumes execution at the position after the statement that raised the condition |
| EXIT | Exits the `BEGIN ... END` block containing the handler |

A named condition does not dictate CONTINUE or EXIT. That behavior is determined by the declared handler type.

## 9. Named Conditions for Business Errors

You can define a condition with SQLSTATE 45000 so a routine can report input validation errors:

```sql
DELIMITER //

CREATE PROCEDURE create_payment(
    IN p_amount DECIMAL(12,2)
)
BEGIN
    DECLARE invalid_amount CONDITION
        FOR SQLSTATE '45000';

    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL invalid_amount
            SET MESSAGE_TEXT = 'Payment amount must be positive';
    END IF;

    INSERT INTO payments(amount)
    VALUES (p_amount);
END//

DELIMITER ;
```

When input is invalid, SIGNAL raises SQLSTATE 45000 with MESSAGE_TEXT. The INSERT statement is not executed after SIGNAL in normal execution flow.

Do not use SQLSTATE 00000 to report errors. Likewise, do not pick a specific system SQLSTATE belonging to another error just to reuse an existing code when the routine is reporting a custom business rule violation.

## 10. SIGNAL and RESIGNAL

SIGNAL actively raises a condition. You can specify a SQLSTATE directly or a condition name declared for a SQLSTATE:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Business rule rejected the operation';
```

Or:

```sql
DECLARE invalid_state CONDITION
    FOR SQLSTATE '45000';

SIGNAL invalid_state
    SET MESSAGE_TEXT = 'Business rule rejected the operation';
```

RESIGNAL is used inside a handler to re-raise the condition that triggered the handler, or re-raise it with modified attributes:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    -- Record info or perform cleanup
    RESIGNAL;
END;
```

Without modifying the condition, RESIGNAL lets the caller continue receiving the original error. If you modify MESSAGE_TEXT or other signal information items, the caller receives the condition adjusted per RESIGNAL.

### 10.1. Do Not Confuse SIGNAL with DECLARE CONDITION

| Statement | Function |
|---|---|
| DECLARE ... CONDITION | Names a SQLSTATE or MySQL error code |
| DECLARE ... HANDLER | Registers behavior when a condition occurs |
| SIGNAL | Proactively raises a condition |
| RESIGNAL | Re-raises a condition inside a handler |

Declaring a condition neither raises an error nor catches an error by itself. Choose the right statement for each purpose.

## 11. Reading Error Details with GET DIAGNOSTICS

After a statement generates a condition, MySQL stores details in the diagnostics area. GET DIAGNOSTICS reads fields from this area.

Three important fields when investigating errors:

| Diagnostics Item | Information |
|---|---|
| RETURNED_SQLSTATE | SQLSTATE of the condition |
| MYSQL_ERRNO | MySQL error code |
| MESSAGE_TEXT | Error message |

Inside a handler, GET STACKED DIAGNOSTICS reads the diagnostics area saved when the handler was triggered:

```sql
GET STACKED DIAGNOSTICS CONDITION 1
    v_sqlstate = RETURNED_SQLSTATE,
    v_mysql_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;
```

GET STACKED DIAGNOSTICS can only be used inside a handler. GET CURRENT DIAGNOSTICS reads the current diagnostics area; subsequent statements inside the handler can generate new conditions, so STACKED is usually appropriate when retrieving the condition that activated the handler.

### 11.1. Example Capturing an Error and Calling RESIGNAL

```sql
DELIMITER //

CREATE PROCEDURE insert_payment(
    IN p_amount DECIMAL(12,2),
    OUT p_sqlstate CHAR(5),
    OUT p_mysql_errno INT,
    OUT p_message VARCHAR(128)
)
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_mysql_errno INT;
    DECLARE v_message VARCHAR(128);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_mysql_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        SET p_sqlstate = v_sqlstate;
        SET p_mysql_errno = v_mysql_errno;
        SET p_message = v_message;

        RESIGNAL;
    END;

    INSERT INTO payments(amount)
    VALUES (p_amount);
END//

DELIMITER ;
```

The handler reads the failing condition before running other statements, assigns the three values to OUT parameters, and calls RESIGNAL so the caller still receives the error. Depending on the client/driver and how a CALL ending in an error behaves, reading OUT parameters after a failed CALL may vary; if the application requires a stable result contract, verify driver behavior and consider returning info via logging/observability at the appropriate layer.

### 11.2. Diagnostics Area with Multiple Conditions

One statement can generate multiple warnings or conditions. The statement information item `NUMBER` reports the count of conditions in the diagnostics area; `ROW_COUNT` reports the affected row count in statement context.

Example reading condition count:

```sql
GET DIAGNOSTICS
    v_condition_count = NUMBER,
    v_row_count = ROW_COUNT;
```

To read a specific condition, use:

```sql
GET DIAGNOSTICS CONDITION 1
    v_sqlstate = RETURNED_SQLSTATE,
    v_mysql_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;
```

The condition number is an index into the diagnostics area. When a statement produces multiple warnings/errors, do not assume condition 1 always holds everything you need; read `NUMBER` and inspect the conditions relevant to your diagnostics goal.

## 12. Choosing Error-Catching Granularity: Error Code, SQLSTATE, or Shorthand?

| Declaration Form | When to Use |
|---|---|
| MySQL error code, e.g., 1062 | Handling a single specific MySQL error |
| Specific SQLSTATE, e.g., 23000 | Handling a specific SQL state |
| SQLWARNING | Handling the class 01 warning group |
| NOT FOUND | Handling the class 02 no-data group, commonly used with cursors |
| SQLEXCEPTION | Handling the remaining error group when fine-grained distinction is unnecessary |
| Named condition | When you want expressive source code and reusable conditions |

Example:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

Compared to:

```sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate = TRUE;
```

Both handle the same error code. The named condition form is easier to read when a routine has many handlers or a condition is referenced in multiple places.

## 13. Real-World Scenarios

### 13.1. Duplicate Key

Scenario: an application creates an account with an email that already exists.

- Common MySQL error code: 1062.
- Common SQLSTATE: 23000.
- Handling: return a duplicate status or translate into a specific business error.

Do not catch all of SQLEXCEPTION and return DUPLICATE, as that can mask connection errors, syntax errors, deadlocks, or other data errors.

### 13.2. Foreign Key Violation

Scenario: adding an order with a nonexistent `customer_id`.

- Common MySQL error code: 1452.
- Common SQLSTATE: 23000.
- Handling: return an invalid reference error or re-validate input data.

SQLSTATE 23000 is the same as the duplicate key example, yet the error code differs. If business logic needs to distinguish the two cases, use specific error codes.

### 13.3. Nonexistent Table or Column

Examples:

- 1146 / 42S02: table does not exist.
- 1054 / 42S22: unknown column.

These errors usually indicate schema, migration, or SQL statements are out of sync. Do not turn them into "data not found" messages because they are structural or deployment errors.

### 13.4. Deadlock

MySQL error code 1213 commonly accompanies SQLSTATE 40001. A transaction chosen as a victim should be retried under a bounded policy, re-executing the entire transaction from the beginning.

Do not retry only the single failing UPDATE statement if the preceding transaction was rolled back. Design retries with backoff, an attempt limit, and ensure operations have appropriate idempotency.

## 14. Common Misconceptions

| Misconception | Reality |
|---|---|
| SQLSTATE and error code are the same | SQLSTATE is a 5-character string; MySQL error code is an integer |
| One SQLSTATE corresponds to only one MySQL error code | Multiple specific errors can share the same SQLSTATE |
| 23000 means only duplicate key | It is the integrity constraint state; includes foreign key violations and others |
| MESSAGE_TEXT is stable for application parsing | Message text depends on version, data, and locale; do not use it as a logic key |
| DECLARE CONDITION catches errors by itself | It only defines a name; DECLARE HANDLER is required to handle it |
| A condition bound to an error code can be SIGNALed directly | Condition names used with SIGNAL/RESIGNAL must be bound to a SQLSTATE |
| SQLSTATE 00000 is used to raise success errors | 00000 is successful completion; do not use it to signal errors |
| SQLSTATE 23xxx is a valid wildcard | DECLARE CONDITION requires a concrete SQLSTATE; no class wildcards exist |
| NOT FOUND means only an empty table | It is a class 02 condition; commonly occurs when cursor FETCH runs out of rows |
| GET DIAGNOSTICS and GET STACKED DIAGNOSTICS are identical | STACKED reads the diagnostics area that activated the handler; valid only inside a handler |
| Catching SQLEXCEPTION is always safest | Overly broad handlers can hide errors that callers must handle separately |

## 15. Condition and Handler Design Checklist

- Have you decided whether to handle by SQLSTATE or specific MySQL error code?
- Do you need to distinguish errors sharing the same SQLSTATE by their error codes?
- Does the condition name accurately express the error meaning?
- Is the condition declared in the right block and before any handler?
- Are variable/condition, cursor, and handler declarations in the proper order?
- Are condition names used with SIGNAL bound to a SQLSTATE?
- Is SQLSTATE exactly 5 characters and not class 00 when raising an error?
- Do CONTINUE and EXIT handlers produce the desired execution behavior?
- Are you catching SQLEXCEPTION too broadly and accidentally masking errors?
- Are you using MESSAGE_TEXT for logging rather than logic parsing?
- Inside handlers, is GET STACKED DIAGNOSTICS called before running other statements?
- Are RETURNED_SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT recorded when needed for diagnostics?
- If handling deadlocks, does the retry logic re-run the entire transaction?
- Have you tested duplicate key, foreign key violation, NULL, no data, and unexpected errors?

## 16. Practice Exercises

### Exercise 1 — Reading SQLSTATE and MySQL Error Codes

Given these cases: duplicate key, foreign key violation, syntax error, unknown table, and deadlock. Look up the corresponding SQLSTATE, MySQL error code, and description in the MySQL Server Error Reference. Note which cases share a SQLSTATE.

### Exercise 2 — Naming a Condition

Write a procedure to add a customer. Declare a `duplicate_key` condition for error code 1062 and an appropriate handler. Return status `DUPLICATE` when the email already exists; return `CREATED` when the INSERT succeeds.

### Exercise 3 — Raising a Business Error

Write a procedure accepting a monetary amount. Declare `invalid_amount` for SQLSTATE 45000. Use `SIGNAL invalid_amount` when the value is NULL or non-positive; provide a clear MESSAGE_TEXT.

### Exercise 4 — Reading Diagnostics

Write an EXIT handler for SQLEXCEPTION. Use GET STACKED DIAGNOSTICS to read RETURNED_SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT, then RESIGNAL the original error.

### Exercise 5 — Choosing Handler Scope

A routine can encounter duplicate key, foreign key violation, and deadlock. Propose named conditions and appropriate handlers for each error; explain which cases should return an error to the caller and which can be mapped to a business status.

## 17. Official References

- [MySQL 9.7 — Condition Handling](https://dev.mysql.com/doc/refman/9.7/en/condition-handling.html)
- [MySQL 9.7 — DECLARE ... CONDITION](https://dev.mysql.com/doc/refman/9.7/en/declare-condition.html)
- [MySQL 9.7 — DECLARE ... HANDLER](https://dev.mysql.com/doc/refman/9.7/en/declare-handler.html)
- [MySQL 9.7 — SIGNAL Statement](https://dev.mysql.com/doc/refman/9.7/en/signal.html)
- [MySQL 9.7 — RESIGNAL Statement](https://dev.mysql.com/doc/refman/9.7/en/resignal.html)
- [MySQL 9.7 — GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/9.7/en/get-diagnostics.html)
- [MySQL 9.7 — Server Error Reference](https://dev.mysql.com/doc/mysql-errors/9.7/en/server-error-reference.html)
- [MySQL 9.7 — Error Message Elements](https://dev.mysql.com/doc/mysql-errors/9.7/en/error-message-elements.html)
- [MySQL 8.0 — Condition Handling](https://dev.mysql.com/doc/refman/8.0/en/condition-handling.html)

## Conclusion

SQLSTATE, MySQL error codes, and MESSAGE_TEXT provide three distinct levels of information about a condition. SQLSTATE is 5 characters and categorizes by class/subclass; the error code is a MySQL-specific integer identifying the exact error; MESSAGE_TEXT is for reading and logging. DECLARE CONDITION assigns a name to a SQLSTATE or error code to make handlers easier to read, though it does not catch errors itself. Use SIGNAL to raise business errors with an appropriate SQLSTATE, RESIGNAL to forward errors inside handlers, and GET STACKED DIAGNOSTICS to inspect the condition that triggered the handler. Choose sufficiently specific error-catching scopes, avoid parsing message text, and always preserve SQLSTATE/error code details for proper diagnostics and handling.
